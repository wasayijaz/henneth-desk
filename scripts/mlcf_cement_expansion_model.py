"""Deterministic 8-quarter cement capacity-expansion financial model and
valuation engine for the MLCF/PIOC industrial case (Case B).

This module is a pure-math kernel: zero network calls, zero LLM calls, zero
file writes inside the kernel functions. Every numeric input is an explicit
source- or analyst-labelled provenance record (reusing
cement_expansion_contract's provenance shape) with an availability date no
later than valuation_date -- no lookahead, no invented defaults.

Timeline
--------
The project timeline has two phases, both driven entirely by explicit,
provenance-bound schedules:

1. Construction phase (length C = len(capex_spending_schedule_pct)): capex is
   drawn per an explicit percentage schedule; each quarter's capex is
   financed debt_financing_pct/equity, and interest on the outstanding
   construction-period debt balance is capitalised (added to both PP&E and
   the debt principal -- a payment-in-kind convention) rather than expensed,
   since there is no revenue yet to expense it against.
2. Operating phase (exactly 8 quarters starting at commissioning_date_quarter):
   volume, revenue, cost, EBITDA, depreciation, finance cost, tax and PAT are
   computed from explicit per-quarter schedules. Depreciation is straight
   line over useful_life_years on the capitalised construction cost. Debt
   principal is repaid in equal instalments on the explicit
   repayment_quarters; interest accrues on the opening balance each quarter.

Accounting integrity
---------------------
Every quarter (construction and operating) satisfies, by construction:

    delta(cash + net_working_capital + net_ppe) == delta(debt + equity)

This is proven algebraically in the module tests and lets a fail-closed
consumer detect any future edit that breaks the identity.

Fail-closed gate
-----------------
evaluate_with_financial_truth_gate is the only entry point that should ever
reach a consumer. If the company's financial_truth_qualification.json row is
not qualified (per the single shared predicate in
formal_financial_engines.financial_truth_is_qualified), it returns an
identity-only envelope with status == "blocked_financial_truth_not_qualified"
and withholds every forecast/valuation number. evaluate_case (the pure
kernel) has no knowledge of financial-truth qualification and is used
directly only by the fixture/test suite.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import cement_expansion_contract as cement
from formal_financial_engines import financial_truth_is_qualified
from psx_data import STATE, load_json, save_json

MODULE_VERSION = "mlcf_cement_expansion_model_v1"
FORMULA_ID = "mlcf_cement_expansion.operating_economics_and_valuation.v1"
RESULT_SCHEMA = "mlcf_cement_expansion_model_result_v1"
OPERATING_QUARTER_COUNT = 8
CASE_LABELS = cement.CASE_LABELS
DEPRECIATION_METHODS = ("straight_line_useful_life",)

FINANCIAL_TRUTH_PATH = STATE / "company_intel" / "financial_truth_qualification.json"
OUTPUT_PATH = STATE / "company_intel" / "mlcf_cement_expansion_model.json"

# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------

_PCT_SCHEDULE_FIELDS = ("ramp_pct_schedule",)
_NONNEG_SCHEDULE_FIELDS = (
    "fuel_cost_pkr_per_ton_schedule",
    "power_cost_pkr_per_ton_schedule",
    "raw_materials_cost_pkr_per_ton_schedule",
    "fixed_operating_cost_pkr_quarterly_schedule",
)
_POSITIVE_SCHEDULE_FIELDS = ("selling_price_pkr_per_ton_schedule",)
_BOUNDED_PCT_HALF_OPEN = (
    "working_capital_pct_revenue",
    "tax_rate_pct",
    "annual_interest_rate_pct",
)
_BOUNDED_PCT_CLOSED = ("debt_financing_pct",)
_POSITIVE_SCALARS = (
    "annual_capacity_tons",
    "expansion_capex_total_pkr",
    "useful_life_years",
    "shares_outstanding",
    "exit_ev_ebitda_multiple",
    "current_market_price_pkr_per_share",
)
_NONNEG_SCALARS = ("pre_expansion_fair_value_pkr_per_share",)

_REQUIRED = (
    "commissioning_date_quarter",
    "construction_quarter_ends",
    "operating_quarter_ends",
    "annual_capacity_tons",
    "capex_spending_schedule_pct",
    "expansion_capex_total_pkr",
    "debt_financing_pct",
    "annual_interest_rate_pct",
    "repayment_quarters",
    "depreciation_method",
    "useful_life_years",
    "ramp_pct_schedule",
    "selling_price_pkr_per_ton_schedule",
    "fuel_cost_pkr_per_ton_schedule",
    "power_cost_pkr_per_ton_schedule",
    "raw_materials_cost_pkr_per_ton_schedule",
    "fixed_operating_cost_pkr_quarterly_schedule",
    "working_capital_pct_revenue",
    "tax_rate_pct",
    "shares_outstanding",
    "valuation_discount_rate_pct_annual",
    "exit_ev_ebitda_multiple",
    "current_market_price_pkr_per_share",
    "pre_expansion_fair_value_pkr_per_share",
)


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_schedule(field: str, value: Any, length: int, *, positive: bool = False,
                        pct: bool = False) -> list[str]:
    violations: list[str] = []
    if not isinstance(value, list) or len(value) != length:
        return [f"{field}: must be a list of exactly {length} values"]
    for index, item in enumerate(value):
        number = _finite(item)
        if number is None:
            violations.append(f"{field}[{index}]: must be a finite number (booleans are not numbers)")
            continue
        if positive and number <= 0.0:
            violations.append(f"{field}[{index}]: must be > 0")
        elif not positive and number < 0.0:
            violations.append(f"{field}[{index}]: must be >= 0")
        if pct and (number < 0.0 or number > 100.0):
            violations.append(f"{field}[{index}]: must be in [0, 100]")
    return violations


def _validate_quarter_ends(field: str, value: Any, length: int | None, valuation_date: date,
                            *, after: date | None = None) -> tuple[list[str], list[date]]:
    violations: list[str] = []
    if not isinstance(value, list) or (length is not None and len(value) != length) or (
        length is None and len(value) < 1
    ):
        expected = f"exactly {length}" if length is not None else "at least 1"
        return [f"{field}: must be a list of {expected} values"], []
    parsed: list[date] = []
    previous = after
    for index, item in enumerate(value):
        end = _as_date(item)
        if end is None or not cement.is_quarter_end(item):
            violations.append(f"{field}[{index}]: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
            parsed.append(None)
            continue
        if end < valuation_date:
            violations.append(f"{field}[{index}]: must be on or after valuation_date")
        if previous is not None and end <= previous:
            violations.append(f"{field}[{index}]: quarter ends must be strictly increasing")
        previous = end
        parsed.append(end)
    return violations, parsed


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return named violations; an empty list means the case is valid."""
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    violations: list[str] = []
    for field in ("symbol", "project_name", "event_ref"):
        if not _nonempty(case.get(field)):
            violations.append(f"{field}: must be a non-empty string")
    if case.get("case_label") not in CASE_LABELS:
        violations.append("case_label: must be one of bear, base, bull")
    effective = _as_date(case.get("effective_date"))
    valuation = _as_date(case.get("valuation_date"))
    if effective is None:
        violations.append("effective_date: must be an ISO date (YYYY-MM-DD)")
    if valuation is None:
        violations.append("valuation_date: must be an ISO date (YYYY-MM-DD)")
    if effective is not None and valuation is not None and effective > valuation:
        violations.append("effective_date: must be on or before valuation_date")
    try:
        json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        violations.append("case: must be JSON-serializable and finite")
    if effective is None or valuation is None:
        return violations
    inputs = case.get("inputs")
    if not isinstance(inputs, Mapping):
        violations.append("inputs: must be a mapping of field to provenance record")
        return violations
    for field in sorted(set(inputs) - set(_REQUIRED), key=str):
        violations.append(f"{field}: unknown input field")
    for field in _REQUIRED:
        if field not in inputs:
            violations.append(f"{field}: missing required input")
    for field, record in sorted(inputs.items(), key=lambda item: str(item[0])):
        if not isinstance(record, Mapping):
            violations.append(f"{field}: input must be a provenance record mapping")
            continue
        if not cement.provenance_ok(record):
            violations.append(f"{field}: provenance record must carry label_type and a complete reference")
        available_on = _as_date(record.get("available_on"))
        if available_on is None:
            violations.append(f"{field}: available_on must be an ISO date (YYYY-MM-DD)")
        elif available_on > valuation:
            violations.append(f"{field}: available_on must be on or before valuation_date")
    violations.extend(_validate_field_values(inputs, valuation))
    return violations


def _validate_field_values(inputs: Mapping[str, Any], valuation: date) -> list[str]:
    violations: list[str] = []

    def value_of(field: str) -> Any:
        record = inputs.get(field)
        return record.get("value") if isinstance(record, Mapping) else None

    capex_schedule = value_of("capex_spending_schedule_pct")
    construction_length = len(capex_schedule) if isinstance(capex_schedule, list) else None

    if not isinstance(capex_schedule, list) or not capex_schedule:
        violations.append("capex_spending_schedule_pct: must be a non-empty list of percentages")
    else:
        violations.extend(_validate_schedule("capex_spending_schedule_pct", capex_schedule,
                                              len(capex_schedule)))
        numbers = [_finite(item) for item in capex_schedule]
        if all(number is not None for number in numbers):
            total = math.fsum(numbers)
            if not math.isclose(total, 100.0, rel_tol=0.0, abs_tol=1e-6):
                violations.append(f"capex_spending_schedule_pct: must sum to 100 (got {total})")

    construction_ends_violations, construction_ends = _validate_quarter_ends(
        "construction_quarter_ends", value_of("construction_quarter_ends"),
        construction_length, valuation,
    )
    violations.extend(construction_ends_violations)

    operating_after = construction_ends[-1] if construction_ends and construction_ends[-1] else None
    operating_violations, operating_ends = _validate_quarter_ends(
        "operating_quarter_ends", value_of("operating_quarter_ends"),
        OPERATING_QUARTER_COUNT, valuation, after=operating_after,
    )
    violations.extend(operating_violations)

    commissioning = value_of("commissioning_date_quarter")
    if not cement.is_quarter_end(commissioning):
        violations.append("commissioning_date_quarter: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
    elif operating_ends and operating_ends[0] is not None and _as_date(commissioning) != operating_ends[0]:
        violations.append("commissioning_date_quarter: must equal operating_quarter_ends[0]")

    depreciation_method = value_of("depreciation_method")
    if depreciation_method not in DEPRECIATION_METHODS:
        violations.append(f"depreciation_method: must be one of {DEPRECIATION_METHODS}")

    repayment_quarters = value_of("repayment_quarters")
    if not isinstance(repayment_quarters, list) or not repayment_quarters:
        violations.append("repayment_quarters: must be a non-empty list of quarter indices")
    else:
        cleaned: list[int] = []
        for index, item in enumerate(repayment_quarters):
            if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= OPERATING_QUARTER_COUNT:
                violations.append(f"repayment_quarters[{index}]: must be an integer from 1 to {OPERATING_QUARTER_COUNT}")
            else:
                cleaned.append(item)
        if len(cleaned) != len(set(cleaned)):
            violations.append("repayment_quarters: must not contain duplicates")

    for field in _PCT_SCHEDULE_FIELDS:
        violations.extend(_validate_schedule(field, value_of(field), OPERATING_QUARTER_COUNT, pct=True))
    for field in _NONNEG_SCHEDULE_FIELDS:
        violations.extend(_validate_schedule(field, value_of(field), OPERATING_QUARTER_COUNT))
    for field in _POSITIVE_SCHEDULE_FIELDS:
        violations.extend(_validate_schedule(field, value_of(field), OPERATING_QUARTER_COUNT, positive=True))

    for field in _POSITIVE_SCALARS:
        number = _finite(value_of(field))
        if number is None:
            violations.append(f"{field}: must be a finite number (booleans are not numbers)")
        elif number <= 0.0:
            violations.append(f"{field}: must be > 0")
    for field in _NONNEG_SCALARS:
        number = _finite(value_of(field))
        if number is None:
            violations.append(f"{field}: must be a finite number (booleans are not numbers)")
        elif number < 0.0:
            violations.append(f"{field}: must be >= 0")
    for field in _BOUNDED_PCT_HALF_OPEN:
        number = _finite(value_of(field))
        if number is None:
            violations.append(f"{field}: must be a finite number (booleans are not numbers)")
        elif not (0.0 <= number < 100.0):
            violations.append(f"{field}: must be in [0, 100)")
    for field in _BOUNDED_PCT_CLOSED:
        number = _finite(value_of(field))
        if number is None:
            violations.append(f"{field}: must be a finite number (booleans are not numbers)")
        elif not (0.0 <= number <= 100.0):
            violations.append(f"{field}: must be in [0, 100]")
    discount = _finite(value_of("valuation_discount_rate_pct_annual"))
    if discount is None:
        violations.append("valuation_discount_rate_pct_annual: must be a finite number (booleans are not numbers)")
    elif not (0.0 < discount < 100.0):
        violations.append("valuation_discount_rate_pct_annual: must be in (0, 100)")

    return violations


# ---------------------------------------------------------------------------
# Deterministic kernel
# ---------------------------------------------------------------------------

def _quarterly_rate(annual_pct: float) -> float:
    return (1.0 + annual_pct / 100.0) ** 0.25 - 1.0


def _quarter_exponent(quarter_end: date, valuation_date: date) -> int:
    return 4 * (quarter_end.year - valuation_date.year) + (
        quarter_end.month // 3 - valuation_date.month // 3
    )


def _finite_row(row: Mapping[str, Any], label: str) -> None:
    for key, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{label}.{key}: non-finite output")


def construction_schedule(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Construction-phase capex draw / capitalised-interest / debt roll-forward."""
    inputs = case["inputs"]
    quarter_ends = inputs["construction_quarter_ends"]["value"]
    capex_pct = inputs["capex_spending_schedule_pct"]["value"]
    capex_total = float(inputs["expansion_capex_total_pkr"]["value"])
    debt_pct = float(inputs["debt_financing_pct"]["value"]) / 100.0
    annual_interest = float(inputs["annual_interest_rate_pct"]["value"]) / 100.0
    valuation_date = _as_date(case["valuation_date"])
    quarterly_interest = annual_interest / 4.0

    rows: list[dict[str, Any]] = []
    debt_open = 0.0
    equity_open = 0.0
    ppe_open = 0.0
    for index, pct in enumerate(capex_pct):
        capex = capex_total * float(pct) / 100.0
        debt_draw = capex * debt_pct
        equity_draw = capex - debt_draw
        capitalized_interest = debt_open * quarterly_interest
        debt_close = debt_open + debt_draw + capitalized_interest
        equity_close = equity_open + equity_draw
        ppe_close = ppe_open + capex + capitalized_interest
        quarter_end = _as_date(quarter_ends[index])
        row = {
            "phase": "construction",
            "quarter_index": index + 1,
            "quarter_end": quarter_end.isoformat(),
            "capex_pkr": capex,
            "debt_open_pkr": debt_open,
            "debt_draw_pkr": debt_draw,
            "capitalized_interest_pkr": capitalized_interest,
            "debt_repayment_pkr": 0.0,
            "debt_close_pkr": debt_close,
            "equity_draw_pkr": equity_draw,
            "equity_close_pkr": equity_close,
            "ppe_open_pkr": ppe_open,
            "ppe_close_pkr": ppe_close,
            "cash_close_pkr": 0.0,
            "net_working_capital_pkr": 0.0,
            "discount_factor": (1.0 + _quarterly_rate(float(inputs["valuation_discount_rate_pct_annual"]["value"])))
            ** (-_quarter_exponent(quarter_end, valuation_date)),
            "unlevered_fcf_pkr": -capex,
        }
        row["discounted_unlevered_fcf_pkr"] = row["unlevered_fcf_pkr"] * row["discount_factor"]
        _finite_row(row, f"construction_schedule[{index}]")
        rows.append(row)
        debt_open, equity_open, ppe_open = debt_close, equity_close, ppe_close
    return rows


def operating_schedule(case: Mapping[str, Any], construction_rows: Sequence[Mapping[str, Any]],
                        *, utilization_scale: float = 1.0,
                        commissioning_delay_quarters: int = 0) -> list[dict[str, Any]]:
    """Operating-phase volume / income-statement / cash-flow / debt roll-forward.

    utilization_scale uniformly scales the ramp schedule (capped at 100 pct
    per quarter) and commissioning_delay_quarters shifts only the discounting
    exponent (the calendar quarter used for the discount factor), used by the
    price-implied backsolve helpers. Both default to identity/no-op.
    """
    inputs = case["inputs"]
    quarter_ends = inputs["operating_quarter_ends"]["value"]
    annual_capacity = float(inputs["annual_capacity_tons"]["value"])
    capacity_per_quarter = annual_capacity / 4.0
    ramp = inputs["ramp_pct_schedule"]["value"]
    price = inputs["selling_price_pkr_per_ton_schedule"]["value"]
    fuel = inputs["fuel_cost_pkr_per_ton_schedule"]["value"]
    power = inputs["power_cost_pkr_per_ton_schedule"]["value"]
    raw_materials = inputs["raw_materials_cost_pkr_per_ton_schedule"]["value"]
    fixed_cost = inputs["fixed_operating_cost_pkr_quarterly_schedule"]["value"]
    working_capital_rate = float(inputs["working_capital_pct_revenue"]["value"]) / 100.0
    tax_rate = float(inputs["tax_rate_pct"]["value"]) / 100.0
    useful_life_years = float(inputs["useful_life_years"]["value"])
    annual_interest = float(inputs["annual_interest_rate_pct"]["value"]) / 100.0
    quarterly_interest = annual_interest / 4.0
    repayment_quarters = set(int(item) for item in inputs["repayment_quarters"]["value"])
    shares = float(inputs["shares_outstanding"]["value"])
    valuation_date = _as_date(case["valuation_date"])
    discount_rate = _quarterly_rate(float(inputs["valuation_discount_rate_pct_annual"]["value"]))

    last_construction = construction_rows[-1] if construction_rows else None
    debt_open = last_construction["debt_close_pkr"] if last_construction else 0.0
    equity_cum = last_construction["equity_close_pkr"] if last_construction else 0.0
    ppe_open = last_construction["ppe_close_pkr"] if last_construction else 0.0
    cash_open = last_construction["cash_close_pkr"] if last_construction else 0.0
    capitalized_base = ppe_open
    quarterly_depreciation = capitalized_base / (useful_life_years * 4.0) if capitalized_base > 0.0 else 0.0
    repayment_installment = debt_open / len(repayment_quarters) if repayment_quarters else 0.0
    working_capital_open = 0.0

    rows: list[dict[str, Any]] = []
    for index in range(OPERATING_QUARTER_COUNT):
        quarter_number = index + 1
        quarter_end = _as_date(quarter_ends[index])
        utilization_pct = min(float(ramp[index]) * utilization_scale, 100.0)
        volume_tons = capacity_per_quarter * utilization_pct / 100.0
        variable_cost_per_ton = float(fuel[index]) + float(power[index]) + float(raw_materials[index])
        revenue = volume_tons * float(price[index])
        variable_cost = volume_tons * variable_cost_per_ton
        gross_profit = revenue - variable_cost
        ebitda = gross_profit - float(fixed_cost[index])
        depreciation = quarterly_depreciation
        ebit = ebitda - depreciation
        interest = debt_open * quarterly_interest
        pbt = ebit - interest
        tax = max(pbt, 0.0) * tax_rate
        pat = pbt - tax
        eps_incremental = pat / shares
        nopat = ebit - max(ebit, 0.0) * tax_rate
        unlevered_fcf = nopat + depreciation
        repayment = repayment_installment if quarter_number in repayment_quarters else 0.0
        debt_close = debt_open - repayment
        working_capital = revenue * working_capital_rate
        delta_working_capital = working_capital - working_capital_open
        unlevered_fcf -= delta_working_capital
        operating_cf = pat + depreciation - delta_working_capital
        financing_cf = -repayment
        net_cf = operating_cf + financing_cf
        cash_close = cash_open + net_cf
        ppe_close = ppe_open - depreciation
        equity_close = equity_cum + pat
        exponent = _quarter_exponent(quarter_end, valuation_date) + commissioning_delay_quarters
        discount_factor = (1.0 + discount_rate) ** (-exponent)
        row = {
            "phase": "operating",
            "quarter_index": quarter_number,
            "quarter_end": quarter_end.isoformat(),
            "capacity_tons": capacity_per_quarter,
            "utilization_pct": utilization_pct,
            "volume_tons": volume_tons,
            "selling_price_pkr_per_ton": float(price[index]),
            "variable_cost_pkr_per_ton": variable_cost_per_ton,
            "revenue_pkr": revenue,
            "variable_cost_pkr": variable_cost,
            "gross_profit_pkr": gross_profit,
            "fixed_cost_pkr": float(fixed_cost[index]),
            "ebitda_pkr": ebitda,
            "depreciation_pkr": depreciation,
            "ebit_pkr": ebit,
            "finance_cost_pkr": interest,
            "profit_before_tax_pkr": pbt,
            "tax_pkr": tax,
            "profit_after_tax_pkr": pat,
            "incremental_eps_pkr": eps_incremental,
            "debt_open_pkr": debt_open,
            "debt_draw_pkr": 0.0,
            "debt_repayment_pkr": repayment,
            "debt_close_pkr": debt_close,
            "equity_close_pkr": equity_close,
            "ppe_open_pkr": ppe_open,
            "ppe_close_pkr": ppe_close,
            "net_working_capital_pkr": working_capital,
            "delta_net_working_capital_pkr": delta_working_capital,
            "operating_cash_flow_pkr": operating_cf,
            "investing_cash_flow_pkr": 0.0,
            "financing_cash_flow_pkr": financing_cf,
            "net_cash_flow_pkr": net_cf,
            "cash_open_pkr": cash_open,
            "cash_close_pkr": cash_close,
            "unlevered_fcf_pkr": unlevered_fcf,
            "discount_factor": discount_factor,
            "discounted_unlevered_fcf_pkr": unlevered_fcf * discount_factor,
        }
        _finite_row(row, f"operating_schedule[{index}]")
        rows.append(row)
        debt_open, equity_cum, ppe_open, cash_open, working_capital_open = (
            debt_close, equity_close, ppe_close, cash_close, working_capital
        )
    return rows


def accounting_integrity_check(construction_rows: Sequence[Mapping[str, Any]],
                                operating_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Verify delta(assets) == delta(liabilities + equity) every quarter."""
    max_gap = 0.0
    quarters_checked = 0
    prev_assets = 0.0
    prev_claims = 0.0
    for row in list(construction_rows) + list(operating_rows):
        assets = row["cash_close_pkr"] + row["net_working_capital_pkr"] + row["ppe_close_pkr"]
        claims = row["debt_close_pkr"] + row["equity_close_pkr"]
        gap = abs((assets - prev_assets) - (claims - prev_claims))
        max_gap = max(max_gap, gap)
        quarters_checked += 1
        prev_assets, prev_claims = assets, claims
    return {
        "quarters_checked": quarters_checked,
        "max_absolute_gap_pkr": max_gap,
        "balanced": max_gap <= 1e-6,
    }


def break_even_utilization_pct(case: Mapping[str, Any], quarter_index: int) -> dict[str, Any]:
    """Solve for the utilization pct in one operating quarter where EBITDA == 0.

    EBITDA(u) is linear in u because volume is linear in utilization: solved
    in closed form from the contribution margin, not by search.
    """
    inputs = case["inputs"]
    annual_capacity = float(inputs["annual_capacity_tons"]["value"])
    capacity_per_quarter = annual_capacity / 4.0
    index = quarter_index - 1
    price = float(inputs["selling_price_pkr_per_ton_schedule"]["value"][index])
    fuel = float(inputs["fuel_cost_pkr_per_ton_schedule"]["value"][index])
    power = float(inputs["power_cost_pkr_per_ton_schedule"]["value"][index])
    raw_materials = float(inputs["raw_materials_cost_pkr_per_ton_schedule"]["value"][index])
    fixed_cost = float(inputs["fixed_operating_cost_pkr_quarterly_schedule"]["value"][index])
    contribution_margin_per_ton = price - fuel - power - raw_materials
    if contribution_margin_per_ton <= 0.0 or capacity_per_quarter <= 0.0:
        return {
            "quarter_index": quarter_index,
            "break_even_utilization_pct": None,
            "reachable": False,
            "reason": "non-positive contribution margin per ton: no utilization level reaches EBITDA break-even",
        }
    break_even_volume = fixed_cost / contribution_margin_per_ton
    break_even_pct = break_even_volume / capacity_per_quarter * 100.0
    return {
        "quarter_index": quarter_index,
        "break_even_utilization_pct": break_even_pct,
        "reachable": 0.0 <= break_even_pct <= 100.0,
        "reason": None,
    }


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

def compute_valuation(case: Mapping[str, Any], construction_rows: Sequence[Mapping[str, Any]],
                       operating_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    inputs = case["inputs"]
    shares = float(inputs["shares_outstanding"]["value"])
    exit_multiple = float(inputs["exit_ev_ebitda_multiple"]["value"])
    all_rows = list(construction_rows) + list(operating_rows)
    try:
        project_dcf_npv = math.fsum(row["discounted_unlevered_fcf_pkr"] for row in all_rows)
    except OverflowError as error:
        raise ValueError("project_dcf_npv_pkr: non-finite output from aggregate overflow") from error
    if not math.isfinite(project_dcf_npv):
        raise ValueError("project_dcf_npv_pkr: non-finite output")

    last_operating = operating_rows[-1]
    terminal_annualized_ebitda = last_operating["ebitda_pkr"] * 4.0
    terminal_net_debt = last_operating["debt_close_pkr"] - last_operating["cash_close_pkr"]
    terminal_ev = terminal_annualized_ebitda * exit_multiple
    terminal_equity_value = terminal_ev - terminal_net_debt
    terminal_equity_value_pv = terminal_equity_value * last_operating["discount_factor"]
    if not math.isfinite(terminal_equity_value_pv):
        raise ValueError("terminal_exit_equity_value_pv_pkr: non-finite output")

    total_project_value = project_dcf_npv + terminal_equity_value_pv
    fair_value_impact_per_share = total_project_value / shares
    if not math.isfinite(fair_value_impact_per_share):
        raise ValueError("fair_value_impact_per_share_pkr: non-finite output")

    return {
        "project_dcf_npv_pkr": project_dcf_npv,
        "terminal_annualized_ebitda_pkr": terminal_annualized_ebitda,
        "terminal_net_debt_pkr": terminal_net_debt,
        "terminal_exit_ev_pkr": terminal_ev,
        "terminal_exit_equity_value_pkr": terminal_equity_value,
        "terminal_exit_equity_value_pv_pkr": terminal_equity_value_pv,
        "total_project_value_pkr": total_project_value,
        "fair_value_impact_per_share_pkr": fair_value_impact_per_share,
    }


def _fair_value_impact_for_scale(case: Mapping[str, Any], construction_rows: Sequence[Mapping[str, Any]],
                                  utilization_scale: float, delay_quarters: int = 0) -> float:
    operating_rows = operating_schedule(
        case, construction_rows,
        utilization_scale=utilization_scale, commissioning_delay_quarters=delay_quarters,
    )
    return compute_valuation(case, construction_rows, operating_rows)["fair_value_impact_per_share_pkr"]


def backsolve_utilization_scale(case: Mapping[str, Any], *, low: float = 0.0, high: float = 3.0,
                                 iterations: int = 60) -> dict[str, Any]:
    """Solve for the uniform ramp-scale factor implied by the market price.

    target = current_market_price - pre_expansion_fair_value. Monotonic
    bisection: fair value is non-decreasing in utilization scale whenever the
    per-ton contribution margin is positive in every operating quarter.
    """
    inputs = case["inputs"]
    target = (
        float(inputs["current_market_price_pkr_per_share"]["value"])
        - float(inputs["pre_expansion_fair_value_pkr_per_share"]["value"])
    )
    construction_rows = construction_schedule(case)
    value_low = _fair_value_impact_for_scale(case, construction_rows, low)
    value_high = _fair_value_impact_for_scale(case, construction_rows, high)
    if value_low > value_high:
        return {
            "target_value_per_share_pkr": target,
            "implied_utilization_scale_pct": None,
            "reachable": False,
            "reason": "fair value is not monotonic increasing in utilization scale over the search bracket (non-positive contribution margin)",
        }
    if target <= value_low:
        return {
            "target_value_per_share_pkr": target,
            "implied_utilization_scale_pct": low * 100.0,
            "reachable": target >= value_low - 1e-6,
            "reason": None if target >= value_low - 1e-6 else "implied scale is below the search floor",
        }
    if target >= value_high:
        return {
            "target_value_per_share_pkr": target,
            "implied_utilization_scale_pct": high * 100.0,
            "reachable": target <= value_high + 1e-6,
            "reason": None if target <= value_high + 1e-6 else "implied scale exceeds the search ceiling",
        }
    for _ in range(iterations):
        mid = (low + high) / 2.0
        value_mid = _fair_value_impact_for_scale(case, construction_rows, mid)
        if value_mid < target:
            low = mid
        else:
            high = mid
    return {
        "target_value_per_share_pkr": target,
        "implied_utilization_scale_pct": ((low + high) / 2.0) * 100.0,
        "reachable": True,
        "reason": None,
    }


def backsolve_commissioning_delay_quarters(case: Mapping[str, Any], *, max_delay: int = 8) -> dict[str, Any]:
    """Grid-search the integer quarter delay (0..max_delay) closest to the
    market-implied value. Delay only shifts the discounting exponent; nominal
    cash flows are unchanged (a pure timing backsolve)."""
    inputs = case["inputs"]
    target = (
        float(inputs["current_market_price_pkr_per_share"]["value"])
        - float(inputs["pre_expansion_fair_value_pkr_per_share"]["value"])
    )
    construction_rows = construction_schedule(case)
    best_delay = None
    best_value = None
    best_gap = None
    for delay in range(max_delay + 1):
        value = _fair_value_impact_for_scale(case, construction_rows, 1.0, delay_quarters=delay)
        gap = abs(value - target)
        if best_gap is None or gap < best_gap:
            best_gap, best_delay, best_value = gap, delay, value
    return {
        "target_value_per_share_pkr": target,
        "implied_commissioning_delay_quarters": best_delay,
        "implied_value_per_share_pkr": best_value,
        "absolute_gap_pkr": best_gap,
    }


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------

def _inputs_lineage(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for field in sorted(inputs, key=str):
        record = inputs[field]
        entry: dict[str, Any] = {
            "field": field,
            "value": copy.deepcopy(record.get("value")),
            "label_type": record.get("label_type"),
            "available_on": record.get("available_on"),
        }
        if record.get("label_type") == "source":
            entry["source_ref"] = copy.deepcopy(record.get("source_ref"))
        else:
            entry["analyst_ref"] = copy.deepcopy(record.get("analyst_ref"))
        entries.append(entry)
    return entries


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Pure deterministic kernel: raises ValueError for any invalid case.

    This function has no knowledge of financial-truth qualification; callers
    that must respect the fail-closed gate use
    evaluate_with_financial_truth_gate instead.
    """
    violations = validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    construction_rows = construction_schedule(case)
    operating_rows = operating_schedule(case, construction_rows)
    integrity = accounting_integrity_check(construction_rows, operating_rows)
    if not integrity["balanced"]:
        raise ValueError(f"accounting_integrity: unbalanced by {integrity['max_absolute_gap_pkr']} PKR")
    valuation = compute_valuation(case, construction_rows, operating_rows)
    break_even = [
        break_even_utilization_pct(case, row["quarter_index"]) for row in operating_rows
    ]
    price_backsolve = {
        "utilization_scale": backsolve_utilization_scale(case),
        "commissioning_delay": backsolve_commissioning_delay_quarters(case),
    }
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "module_version": MODULE_VERSION,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        },
        "status": "computed",
        "blocked_reasons": [],
        "project": {
            "symbol": case["symbol"],
            "project_name": case["project_name"],
            "event_ref": case["event_ref"],
            "case_label": case["case_label"],
            "effective_date": case["effective_date"],
            "valuation_date": case["valuation_date"],
            "commissioning_date_quarter": case["inputs"]["commissioning_date_quarter"]["value"],
            "depreciation_method": case["inputs"]["depreciation_method"]["value"],
        },
        "inputs_lineage": _inputs_lineage(case["inputs"]),
        "construction_schedule": construction_rows,
        "operating_schedule": operating_rows,
        "accounting_integrity": integrity,
        "valuation": valuation,
        "break_even_utilization": break_even,
        "price_implied_expectation_backsolve": price_backsolve,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": True,
            "simplifications": [
                "construction-phase interest is capitalised (PIK, added to PP&E and debt principal); no cash interest is paid before commissioning",
                "all expansion capex is spent during the construction phase; the operating phase has zero investing cash flow",
                "depreciation is straight-line over useful_life_years on the fully capitalised construction cost, starting at commissioning",
                "debt principal is repaid in equal instalments on the explicit repayment_quarters; no refinancing or prepayment is modeled",
                "tax is an effective cash-tax rate on positive quarterly pre-tax income for the levered income statement, and on positive EBIT for the unlevered FCF used in valuation; no loss carryforward",
                "net working capital is a percentage of incremental project revenue only; no terminal value beyond the explicit exit-multiple bridge is modeled",
                "the exit-multiple terminal value is bridged to equity by subtracting net debt (closing debt less cash) at the end of the eight-quarter operating horizon",
                "price-implied backsolves treat (current_market_price - pre_expansion_fair_value) as the market-implied incremental equity value of this project only",
                "the utilization-scale backsolve assumes fair value is monotonic in utilization over the search bracket, which requires positive per-ton contribution margin",
                "the commissioning-delay backsolve is a discrete grid search over integer quarter delays; nominal cash flows are unchanged, only discounting timing shifts",
                "cases are isolated bear/base/bull scenarios; no scenario weighting is performed",
            ],
        },
    }


def blocked_result(identity: Mapping[str, Any], reasons: list[str], *,
                    status: str = "blocked_invalid_inputs") -> dict[str, Any]:
    """Identity-only blocked envelope; no partial calculations leak."""
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "module_version": MODULE_VERSION,
        "run_receipt": {"inputs_sha256": None},
        "status": status,
        "blocked_reasons": sorted(set(str(reason) for reason in reasons)),
        "project": {
            "symbol": identity.get("symbol"),
            "project_name": identity.get("project_name"),
            "event_ref": identity.get("event_ref"),
            "case_label": identity.get("case_label"),
            "effective_date": identity.get("effective_date"),
            "valuation_date": identity.get("valuation_date"),
            "commissioning_date_quarter": None,
            "depreciation_method": None,
        },
        "inputs_lineage": [],
        "construction_schedule": [],
        "operating_schedule": [],
        "accounting_integrity": None,
        "valuation": None,
        "break_even_utilization": [],
        "price_implied_expectation_backsolve": None,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": True,
            "simplifications": ["blocked before calculation; missing, invalid, or unqualified inputs"],
        },
    }


def evaluate_with_financial_truth_gate(case: Mapping[str, Any],
                                        financial_truth_row: Mapping[str, Any]) -> dict[str, Any]:
    """The only entry point a consumer should call. Fails closed on both the
    financial-truth qualification gate and on invalid/malformed case inputs;
    never raises."""
    if not financial_truth_is_qualified(financial_truth_row):
        status = financial_truth_row.get("status") if isinstance(financial_truth_row, Mapping) else None
        return blocked_result(
            case if isinstance(case, Mapping) else {},
            [f"financial_truth_status:{status or 'missing'}"],
            status="blocked_financial_truth_not_qualified",
        )
    try:
        return evaluate_case(case)
    except ValueError as error:
        return blocked_result(
            case if isinstance(case, Mapping) else {},
            str(error).split("; "),
            status="blocked_invalid_inputs",
        )


# ---------------------------------------------------------------------------
# Build entry point
# ---------------------------------------------------------------------------

REAL_SYMBOL = "MLCF"
REAL_PROJECT_NAME = "MLCF-PIOC Expansion Integration"
REAL_EVENT_REF = "case_mlcf_pioc_control_observed_v1"
REAL_CASE_LABEL = "base"
REAL_BASELINE_DATE = "2026-08-31"


def _real_identity() -> dict[str, Any]:
    """Identity-only case shell for the real MLCF/PIOC lane.

    No project economics (capex, ramp, pricing, financing) are populated here:
    those inputs are not source-qualified for this case (see
    mlcf_pioc_case_run_adapter / build_mlcf_pioc_readiness_manifest), and the
    financial-truth gate below blocks live output before any such inputs
    would matter. Fabricating numbers to fill the schema would violate the
    desk's no-guessed-data rule, so the real lane carries identity only.
    """
    return {
        "symbol": REAL_SYMBOL,
        "project_name": REAL_PROJECT_NAME,
        "event_ref": REAL_EVENT_REF,
        "case_label": REAL_CASE_LABEL,
        "effective_date": REAL_BASELINE_DATE,
        "valuation_date": REAL_BASELINE_DATE,
    }


def build(*, write: bool = True, financial_truth: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the real MLCF/PIOC state envelope. Blocks closed unless and until
    MLCF's financial_truth_qualification.json row is qualified."""
    truth_state = financial_truth if financial_truth is not None else load_json(
        FINANCIAL_TRUTH_PATH, {"companies": {}}
    )
    truth_row = (truth_state.get("companies") or {}).get(REAL_SYMBOL) or {}
    result = evaluate_with_financial_truth_gate(_real_identity(), truth_row)
    if write:
        save_json(OUTPUT_PATH, result)
    return result


def main() -> None:
    result = build(write=True)
    print(f"mlcf_cement_expansion_model: status={result['status']}")


if __name__ == "__main__":
    main()

