"""Deterministic PSO sales-led distribution-network expansion model.

This is the Case C OMC adapter.  It deliberately models fuel outlets,
convenience/VIBE stores, and LPG delivery points as separate channel layers;
VIBE is a subset of convenience stores and is never added as another site
count.  The kernel is pure apart from the small ``build`` state writer.

The production entry point is ``evaluate_with_financial_truth_gate``.  A PSO
financial-truth row that is not qualified returns an identity-only envelope
with no forecast, valuation, or expectations numbers.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from formal_financial_engines import financial_truth_is_qualified
from psx_data import STATE, load_json, save_json

MODULE_VERSION = "pso_sales_expansion_model_v1"
FORMULA_ID = "pso_sales_expansion.operating_economics_and_valuation.v1"
RESULT_SCHEMA = "pso_sales_expansion_model_result_v1"
MODEL_ARCHETYPE = "omc_distribution_network_expansion_v1"
QUARTER_COUNT = 8
SCENARIOS = ("bear", "base", "bull")
FINANCIAL_TRUTH_PATH = STATE / "company_intel" / "financial_truth_qualification.json"
OUTPUT_PATH = STATE / "company_intel" / "pso_sales_expansion_model.json"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _quarter_end(value: Any) -> bool:
    parsed = _date(value)
    return bool(parsed and parsed.month in (3, 6, 9, 12) and
                (parsed + __import__("datetime").timedelta(days=1)).month != parsed.month)


def _value(inputs: Mapping[str, Any], field: str, default: Any = None) -> Any:
    value = inputs.get(field, default)
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def _record(value: Any, *, label_type: str = "analyst", field: str = "") -> dict[str, Any]:
    """Build a compact provenance record for the default fixture only."""
    if isinstance(value, Mapping) and "value" in value:
        return copy.deepcopy(dict(value))
    if label_type == "source":
        return {"value": value, "label_type": "source", "source_ref": {
            "id": f"source:pso:{field or 'input'}", "label": "Retained PSO evidence",
            "url": "https://psopk.com/",}, "available_on": "2025-08-19"}
    return {"value": value, "label_type": "analyst", "analyst_ref": {
        "note_id": "note:pso-sales-expansion:approved-assumptions",
        "note": "Explicit Case C analyst assumption"}, "available_on": "2025-08-19"}


_SCHEDULES = (
    "gross_openings_schedule", "closures_or_reclassifications_schedule",
    "convenience_openings_schedule", "vibe_openings_schedule",
    "lpg_delivery_point_openings_schedule", "mature_litres_per_outlet_quarter_schedule",
    "realized_price_per_litre_schedule", "dealer_margin_per_litre_schedule",
    "mature_sales_per_store_quarter_schedule", "convenience_gross_margin_pct_schedule",
    "lpg_sales_per_delivery_point_quarter_schedule", "lpg_gross_margin_pct_schedule",
    "retention_rate_schedule", "receivable_days_schedule", "inventory_days_schedule",
    "payable_days_schedule", "sales_hires_schedule", "support_hires_schedule",
    "marketing_spend_schedule", "owned_capex_schedule", "dealer_funded_capex_schedule",
    "central_infrastructure_capex_schedule", "debt_repayment_schedule",
)
_REQUIRED = (
    "quarter_ends", "starting_active_outlets", "starting_convenience_stores",
    "starting_vibe_stores", "starting_lpg_delivery_points", "gross_openings_schedule",
    "closures_or_reclassifications_schedule", "convenience_openings_schedule",
    "vibe_openings_schedule", "lpg_delivery_point_openings_schedule",
    "mature_litres_per_outlet_quarter_schedule", "realized_price_per_litre_schedule",
    "dealer_margin_per_litre_schedule", "mature_sales_per_store_quarter_schedule",
    "convenience_gross_margin_pct_schedule", "lpg_sales_per_delivery_point_quarter_schedule",
    "lpg_gross_margin_pct_schedule", "retention_rate_schedule", "ramp_factor_by_cohort",
    "sales_hires_schedule", "support_hires_schedule", "compensation_per_fte_quarter",
    "outlet_support_cost_per_active_outlet_quarter", "marketing_spend_schedule",
    "marketing_spend_per_active_outlet_quarter", "working_capital_per_active_outlet_quarter",
    "central_technology_cost_per_quarter", "dealer_commission_or_revenue_share_schedule",
    "other_incremental_opex_schedule", "owned_capex_schedule", "dealer_funded_capex_schedule",
    "central_infrastructure_capex_schedule", "depreciation_useful_life_years",
    "receivable_days_schedule", "inventory_days_schedule", "payable_days_schedule",
    "tax_rate", "shares_outstanding", "discount_rate_annual", "terminal_growth_rate",
    "current_market_price_pkr_per_share", "pre_expansion_fair_value_pkr_per_share",
)


def _schedule_violations(name: str, value: Any, *, integer: bool = False,
                         pct: bool = False, positive: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) != QUARTER_COUNT:
        return [f"{name}: must be a list of exactly {QUARTER_COUNT} values"]
    violations = []
    for index, item in enumerate(value):
        if integer:
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                violations.append(f"{name}[{index}]: must be an integer >= 0")
            continue
        number = _finite(item)
        if number is None:
            violations.append(f"{name}[{index}]: must be finite")
        elif number < 0 and not positive:
            violations.append(f"{name}[{index}]: must be >= 0")
        elif positive and number <= 0:
            violations.append(f"{name}[{index}]: must be > 0")
        elif pct and not (0 <= number <= 100):
            violations.append(f"{name}[{index}]: must be in [0, 100]")
    return violations


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return deterministic named violations; an empty list means valid."""
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    violations: list[str] = []
    for field in ("symbol", "event_ref", "effective_date", "valuation_date"):
        if not isinstance(case.get(field), str) or not case.get(field).strip():
            violations.append(f"{field}: must be a non-empty string")
    if case.get("case_label") not in SCENARIOS:
        violations.append("case_label: must be one of bear, base, bull")
    valuation = _date(case.get("valuation_date"))
    effective = _date(case.get("effective_date"))
    if valuation is None:
        violations.append("valuation_date: must be an ISO date")
    if effective is None:
        violations.append("effective_date: must be an ISO date")
    if effective and valuation and effective > valuation:
        violations.append("effective_date: must be on or before valuation_date")
    try:
        json.dumps(case, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        violations.append("case: must be JSON-serializable with finite numeric values")
    inputs = case.get("inputs")
    if not isinstance(inputs, Mapping):
        return violations + ["inputs: must be a mapping"]
    for field in _REQUIRED:
        if field not in inputs:
            violations.append(f"{field}: missing required input")
    if any(field not in inputs for field in ("quarter_ends",)):
        return violations
    ends = _value(inputs, "quarter_ends")
    if not isinstance(ends, list) or len(ends) != QUARTER_COUNT:
        violations.append(f"quarter_ends: must be a list of exactly {QUARTER_COUNT} values")
    else:
        prior = valuation
        for index, item in enumerate(ends):
            parsed = _date(item)
            if parsed is None or not _quarter_end(item):
                violations.append(f"quarter_ends[{index}]: must be a quarter-end")
            elif prior and parsed <= prior:
                violations.append(f"quarter_ends[{index}]: must be after valuation_date and ordered")
            prior = parsed
    for field in _SCHEDULES:
        if field in inputs:
            violations.extend(_schedule_violations(field, _value(inputs, field),
                                                     integer=field.endswith("schedule") and
                                                     any(token in field for token in ("openings", "hires", "repayment")),
                                                     pct="margin_pct" in field or field.startswith("retention")))
    ramp = _value(inputs, "ramp_factor_by_cohort")
    violations.extend(_schedule_violations("ramp_factor_by_cohort", ramp, pct=True))
    if isinstance(ramp, list) and ramp and any(_finite(x) is not None and _finite(x) > 1 for x in ramp):
        violations.append("ramp_factor_by_cohort: values must be in [0, 1]")
    for field in ("starting_active_outlets", "starting_convenience_stores", "starting_vibe_stores",
                  "starting_lpg_delivery_points", "compensation_per_fte_quarter",
                  "outlet_support_cost_per_active_outlet_quarter", "central_technology_cost_per_quarter",
                  "depreciation_useful_life_years", "shares_outstanding"):
        value = _finite(_value(inputs, field))
        if value is None or value < 0 or (field in ("depreciation_useful_life_years", "shares_outstanding") and value <= 0):
            violations.append(f"{field}: must be a finite non-negative number")
    for field in ("tax_rate", "discount_rate_annual", "terminal_growth_rate"):
        value = _finite(_value(inputs, field))
        if value is None:
            violations.append(f"{field}: must be finite")
        elif field == "discount_rate_annual" and not 0 < value < 100:
            violations.append(f"{field}: must be in (0, 100)")
        elif field == "terminal_growth_rate" and not 0 <= value < 100:
            violations.append(f"{field}: must be in [0, 100)")
        elif field == "tax_rate" and not 0 <= value < 100:
            violations.append(f"{field}: must be in [0, 100)")
    for field in ("current_market_price_pkr_per_share", "pre_expansion_fair_value_pkr_per_share"):
        value = _finite(_value(inputs, field))
        if value is None or value < 0:
            violations.append(f"{field}: must be a finite non-negative number")
    if valuation:
        for field, record in inputs.items():
            if isinstance(record, Mapping) and record.get("available_on"):
                available = _date(record.get("available_on"))
                if available is None or available > valuation:
                    violations.append(f"{field}: available_on must be on or before valuation_date")
    return violations


def _qrate(annual_pct: float) -> float:
    return (1 + annual_pct / 100.0) ** 0.25 - 1


def _qexp(end: date, valuation: date) -> int:
    return (end.year - valuation.year) * 4 + (end.month - valuation.month) // 3


def _finite_row(row: Mapping[str, Any], label: str) -> None:
    for key, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{label}.{key}: non-finite output")


def _cohort_equivalent(openings: Sequence[float], retention: float, ramp: Sequence[float], q: int) -> float:
    total = 0.0
    for cohort, opened in enumerate(openings[:q + 1]):
        age = q - cohort
        total += float(opened) * retention * float(ramp[min(age, len(ramp) - 1)])
    return total


def quarterly_schedule(case: Mapping[str, Any], *, opening_scale: float = 1.0,
                        throughput_scale: float = 1.0) -> list[dict[str, Any]]:
    """Return the eight-quarter operating and balance-sheet schedule."""
    violations = validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    inputs = case["inputs"]
    valuation = _date(case["valuation_date"])
    ends = _value(inputs, "quarter_ends")
    gross = [float(x) * opening_scale for x in _value(inputs, "gross_openings_schedule")]
    closures = [float(x) for x in _value(inputs, "closures_or_reclassifications_schedule")]
    convenience = [float(x) for x in _value(inputs, "convenience_openings_schedule")]
    vibe = [float(x) for x in _value(inputs, "vibe_openings_schedule")]
    lpg_openings = [float(x) for x in _value(inputs, "lpg_delivery_point_openings_schedule")]
    ramp = _value(inputs, "ramp_factor_by_cohort")
    retention = _value(inputs, "retention_rate_schedule")
    shares = float(_value(inputs, "shares_outstanding"))
    tax_rate = float(_value(inputs, "tax_rate")) / 100
    qrate = _qrate(float(_value(inputs, "discount_rate_annual")))
    debt_open = cash_open = equity_open = ppe_open = nwc_open = 0.0
    active_open = float(_value(inputs, "starting_active_outlets"))
    convenience_open = float(_value(inputs, "starting_convenience_stores"))
    vibe_open = float(_value(inputs, "starting_vibe_stores"))
    lpg_open = float(_value(inputs, "starting_lpg_delivery_points"))
    rows = []
    for q in range(QUARTER_COUNT):
        ret = float(retention[q])
        net_change = gross[q] - closures[q]
        active_close = active_open + net_change
        convenience_close = convenience_open + convenience[q]
        vibe_close = vibe_open + vibe[q]
        lpg_close = lpg_open + lpg_openings[q]
        active_equiv = _cohort_equivalent(gross, ret, ramp, q)
        convenience_equiv = _cohort_equivalent(convenience, ret, ramp, q)
        lpg_equiv = _cohort_equivalent(lpg_openings, ret, ramp, q)
        litres_per = float(_value(inputs, "mature_litres_per_outlet_quarter_schedule")[q]) * throughput_scale
        litres = active_equiv * litres_per
        price = float(_value(inputs, "realized_price_per_litre_schedule")[q])
        dealer_margin = float(_value(inputs, "dealer_margin_per_litre_schedule")[q])
        fuel_revenue = litres * price
        fuel_gp = litres * dealer_margin
        store_sales = float(_value(inputs, "mature_sales_per_store_quarter_schedule")[q]) * throughput_scale
        convenience_revenue = convenience_equiv * store_sales
        convenience_gp = convenience_revenue * float(_value(inputs, "convenience_gross_margin_pct_schedule")[q]) / 100
        lpg_sales = float(_value(inputs, "lpg_sales_per_delivery_point_quarter_schedule")[q]) * throughput_scale
        lpg_revenue = lpg_equiv * lpg_sales
        lpg_gp = lpg_revenue * float(_value(inputs, "lpg_gross_margin_pct_schedule")[q]) / 100
        revenue = fuel_revenue + convenience_revenue + lpg_revenue
        gross_profit = fuel_gp + convenience_gp + lpg_gp
        hires_cost = (float(_value(inputs, "sales_hires_schedule")[q]) + float(_value(inputs, "support_hires_schedule")[q])) * float(_value(inputs, "compensation_per_fte_quarter"))
        support = active_close * float(_value(inputs, "outlet_support_cost_per_active_outlet_quarter"))
        marketing = float(_value(inputs, "marketing_spend_schedule")[q])
        marketing_per_outlet = active_equiv * float(_value(inputs, "marketing_spend_per_active_outlet_quarter"))
        marketing += marketing_per_outlet
        tech = float(_value(inputs, "central_technology_cost_per_quarter"))
        dealer_commission = float(_value(inputs, "dealer_commission_or_revenue_share_schedule")[q])
        other_opex = float(_value(inputs, "other_incremental_opex_schedule")[q])
        sga = hires_cost + support + marketing + tech + dealer_commission + other_opex
        ebitda = gross_profit - sga
        owned_capex = float(_value(inputs, "owned_capex_schedule")[q])
        dealer_capex = float(_value(inputs, "dealer_funded_capex_schedule")[q])
        central_capex = float(_value(inputs, "central_infrastructure_capex_schedule")[q])
        capex = owned_capex + central_capex
        useful_life = float(_value(inputs, "depreciation_useful_life_years"))
        depreciation = (ppe_open + capex) / (useful_life * 4)
        net_ppe_close = ppe_open + capex - depreciation
        ebit = ebitda - depreciation
        finance_cost = debt_open * float(_value(inputs, "annual_interest_rate" , 0.0)) / 100 / 4 if "annual_interest_rate" in inputs else 0.0
        debt_repayment = float(_value(inputs, "debt_repayment_schedule")[q])
        debt_financing = float(_value(inputs, "debt_financing_pct", 50.0)) / 100
        debt_draw = capex * debt_financing
        pbt = ebit - finance_cost
        tax = max(pbt, 0.0) * tax_rate
        pat = pbt - tax
        ebit_tax = max(ebit, 0.0) * tax_rate
        nopat = ebit - ebit_tax
        cogs = max(revenue - gross_profit, 0.0)
        receivable_days = float(_value(inputs, "receivable_days_schedule")[q])
        inventory_days = float(_value(inputs, "inventory_days_schedule")[q])
        payable_days = float(_value(inputs, "payable_days_schedule")[q])
        receivables = revenue * receivable_days / 365
        inventory = cogs * inventory_days / 365
        payables = cogs * payable_days / 365
        working_capital_per_outlet = active_equiv * float(_value(inputs, "working_capital_per_active_outlet_quarter"))
        nwc_close = receivables + inventory - payables + working_capital_per_outlet
        delta_nwc = nwc_close - nwc_open
        operating_cf = pat + depreciation - delta_nwc
        financing_cf = debt_draw - debt_repayment + (capex - debt_draw)
        cash_close = cash_open + operating_cf - capex + debt_draw + (capex - debt_draw) - debt_repayment
        debt_close = debt_open + debt_draw - debt_repayment
        equity_close = equity_open + pat + (capex - debt_draw)
        invested_capital = max(net_ppe_close, 0.0) + nwc_close
        avg_invested = ((max(ppe_open, 0.0) + nwc_open) + invested_capital) / 2
        roic = (nopat * 4 / avg_invested * 100) if avg_invested > 0 else None
        discount_factor = (1 + qrate) ** (-_qexp(_date(ends[q]), valuation))
        fcff = nopat + depreciation - capex - delta_nwc
        assets_delta = (cash_close + nwc_close + net_ppe_close) - (cash_open + nwc_open + ppe_open)
        claims_delta = (debt_close + equity_close) - (debt_open + equity_open)
        # Currency arithmetic is performed in binary floating point.  Preserve
        # the identity as a displayed zero when the residual is below a cent;
        # do not let harmless rounding turn a balanced schedule into a block.
        balance_gap = assets_delta - claims_delta
        if abs(balance_gap) <= 1e-4:
            balance_gap = 0.0
        row = {
            "quarter_index": q + 1, "period_end": ends[q], "quarter_end": ends[q], "scenario": case["case_label"],
            "network": {"opening_active_outlets": active_open, "gross_outlets_opened": gross[q],
                        "closures_or_reclassifications": closures[q], "net_active_change": net_change,
                        "closing_active_outlets": active_close, "cohort_active_equivalent_outlets": active_equiv,
                        "outlet_retention_rate": ret, "ramp_factor_by_cohort": ramp[q]},
            "fuel_channel": {"mature_litres_per_outlet_quarter": litres_per, "incremental_litres": litres,
                             "realized_price_per_litre": price, "dealer_margin_per_litre": dealer_margin,
                             "incremental_fuel_revenue": fuel_revenue, "incremental_fuel_gross_contribution": fuel_gp},
            "nonfuel_channel": {"convenience_store_count": convenience_close, "vibe_store_count": vibe_close,
                                "vibe_subset_of_convenience": True, "mature_sales_per_store_quarter": store_sales,
                                "gross_margin_rate": float(_value(inputs, "convenience_gross_margin_pct_schedule")[q]) / 100,
                                "incremental_nonfuel_revenue": convenience_revenue, "incremental_nonfuel_gross_profit": convenience_gp},
            "digital_and_geography": {"asaan_safar_active_sites": None, "lpg_blue_active_geographies": None,
                                      "digital_orders_or_customers": lpg_equiv, "revenue_per_order_or_customer": lpg_sales,
                                      "channel_mix": {"fuel_retail": fuel_revenue, "convenience": convenience_revenue,
                                                      "lpg_delivery": lpg_revenue}},
            "lpg_channel": {"delivery_point_count": lpg_close, "active_equivalent_delivery_points": lpg_equiv,
                            "mature_sales_per_delivery_point_quarter": lpg_sales, "incremental_lpg_revenue": lpg_revenue,
                            "incremental_lpg_gross_profit": lpg_gp},
            "operating_costs": {"incremental_sales_hires": _value(inputs, "sales_hires_schedule")[q],
                                "incremental_support_hires": _value(inputs, "support_hires_schedule")[q],
                                "compensation_per_fte_quarter": _value(inputs, "compensation_per_fte_quarter"),
                                "outlet_support_cost": support, "marketing_spend": marketing,
                                "marketing_spend_per_active_outlet_quarter": float(_value(inputs, "marketing_spend_per_active_outlet_quarter")),
                                "central_technology_cost": tech, "dealer_commission_or_revenue_share": dealer_commission,
                                "other_incremental_opex": other_opex, "incremental_sga": sga},
            "capital_and_working_capital": {"owned_capex": owned_capex, "dealer_funded_capex": dealer_capex,
                                             "capitalized_central_infrastructure": central_capex, "depreciation": depreciation,
                                             "receivable_days": receivable_days, "inventory_days": inventory_days,
                                             "payable_days": payable_days, "incremental_receivables": receivables,
                                             "incremental_inventory": inventory, "incremental_payables": payables,
                                             "working_capital_per_active_outlet_quarter": float(_value(inputs, "working_capital_per_active_outlet_quarter")),
                                             "working_capital_per_outlet_component": working_capital_per_outlet,
                                             "incremental_nwc": nwc_close, "change_in_incremental_nwc": delta_nwc},
            "volume_litres": litres, "revenue_pkr": revenue, "gross_profit_pkr": gross_profit,
            "sga_pkr": sga, "ebitda_pkr": ebitda, "depreciation_pkr": depreciation, "ebit_pkr": ebit,
            "finance_cost_pkr": finance_cost, "pbt_pkr": pbt, "tax_pkr": tax, "pat_pkr": pat,
            "eps_pkr": pat / shares, "nopat_pkr": nopat, "operating_cash_flow_pkr": operating_cf,
            "capex_pkr": capex, "fcf_pkr": operating_cf - capex, "fcff_pkr": fcff,
            "cash_open_pkr": cash_open, "cash_close_pkr": cash_close, "nwc_open_pkr": nwc_open,
            "nwc_close_pkr": nwc_close, "net_ppe_open_pkr": ppe_open, "net_ppe_close_pkr": net_ppe_close,
            "debt_open_pkr": debt_open, "debt_close_pkr": debt_close, "equity_open_pkr": equity_open,
            "equity_close_pkr": equity_close, "debt_draw_pkr": debt_draw, "debt_repayment_pkr": debt_repayment,
            "equity_contribution_pkr": capex - debt_draw, "incremental_invested_capital_pkr": invested_capital,
            "roic_annualized_pct": roic, "discount_factor": discount_factor,
            "discounted_fcff_pkr": fcff * discount_factor, "balance_sheet_delta_gap_pkr": balance_gap,
        }
        _finite_row(row, f"quarterly_schedule[{q}]")
        rows.append(row)
        active_open, convenience_open, vibe_open, lpg_open = active_close, convenience_close, vibe_close, lpg_close
        cash_open, debt_open, equity_open, ppe_open, nwc_open = cash_close, debt_close, equity_close, net_ppe_close, nwc_close
    return rows


def accounting_integrity_check(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gaps = [abs(float(row.get("balance_sheet_delta_gap_pkr", 0.0))) for row in rows]
    return {"quarters_checked": len(rows), "max_absolute_gap_pkr": max(gaps or [0.0]),
            "balanced": max(gaps or [0.0]) <= 1e-6}


def compute_valuation(case: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    shares = float(_value(case["inputs"], "shares_outstanding"))
    wacc = float(_value(case["inputs"], "discount_rate_annual")) / 100
    growth = float(_value(case["inputs"], "terminal_growth_rate")) / 100
    npv = math.fsum(row["discounted_fcff_pkr"] for row in rows)
    terminal_fcff = rows[-1]["fcff_pkr"] * 4 * (1 + growth)
    terminal_value = terminal_fcff / max(wacc - growth, 1e-9)
    terminal_pv = terminal_value * rows[-1]["discount_factor"]
    total = npv + terminal_pv
    return {"project_dcf_npv_pkr": npv, "terminal_value_pkr": terminal_value,
            "discounted_terminal_value_pkr": terminal_pv, "fair_value_impact_pkr": total,
            "fair_value_impact_per_share_pkr": total / shares}


def market_expectations_backsolve(case: Mapping[str, Any], *, target: float | None = None) -> dict[str, Any]:
    """Bisection backsolve for openings and throughput implied by current price."""
    inputs = case["inputs"]
    target = (float(_value(inputs, "current_market_price_pkr_per_share")) -
              float(_value(inputs, "pre_expansion_fair_value_pkr_per_share"))) if target is None else target
    base = compute_valuation(case, quarterly_schedule(case))['fair_value_impact_per_share_pkr']
    def solve(kind: str) -> dict[str, Any]:
        low, high = 0.0, 5.0
        for _ in range(70):
            mid = (low + high) / 2
            rows = quarterly_schedule(case, opening_scale=mid if kind == "openings" else 1.0,
                                      throughput_scale=mid if kind == "throughput" else 1.0)
            value = compute_valuation(case, rows)["fair_value_impact_per_share_pkr"]
            if value < target: low = mid
            else: high = mid
        scale = (low + high) / 2
        return {"target_incremental_value_per_share_pkr": target, "base_model_value_per_share_pkr": base,
                "implied_scale": scale, "implied_openings_or_throughput_pct": scale * 100,
                "reachable": target <= compute_valuation(case, quarterly_schedule(case, opening_scale=5 if kind == "openings" else 1, throughput_scale=5 if kind == "throughput" else 1))["fair_value_impact_per_share_pkr"] + 1e-6,
                "driver": kind}
    return {"implied_by_openings": solve("openings"), "implied_by_throughput_productivity": solve("throughput")}


def _break_evens(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cumulative = 0.0
    ebitda_q = None
    cash_q = None
    for row in rows:
        if ebitda_q is None and row["ebitda_pkr"] >= 0: ebitda_q = row["quarter_index"]
        cumulative += row["fcf_pkr"]
        if cash_q is None and cumulative >= 0: cash_q = row["quarter_index"]
    return {"ebitda_break_even_quarter": ebitda_q, "cash_payback_quarter": cash_q}


def _lineage(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for field in sorted(inputs):
        record = inputs[field]
        if isinstance(record, Mapping):
            item = {"field": field, "label_type": record.get("label_type"), "available_on": record.get("available_on")}
            if record.get("label_type") == "source": item["source_ref_id"] = (record.get("source_ref") or {}).get("id")
            else: item["analyst_note_id"] = (record.get("analyst_ref") or {}).get("note_id")
        else:
            item = {"field": field, "label_type": "analyst", "analyst_note_id": "unwrapped_input"}
        result.append(item)
    return result


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    violations = validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    rows = quarterly_schedule(case)
    integrity = accounting_integrity_check(rows)
    if not integrity["balanced"]:
        raise ValueError("accounting_integrity: balance sheet identity failed")
    valuation = compute_valuation(case, rows)
    return {"schema_version": RESULT_SCHEMA, "model_archetype": MODEL_ARCHETYPE,
            "formula_id": FORMULA_ID, "module_version": MODULE_VERSION,
            "run_receipt": {"inputs_sha256": hashlib.sha256(json.dumps(case, sort_keys=True, separators=(",", ":")).encode()).hexdigest()},
            "status": "computed", "blocked_reasons": [], "symbol": case["symbol"],
            "event_ref": case["event_ref"], "scenario": case["case_label"],
            "inputs_lineage": _lineage(case["inputs"]), "quarterly_schedule": rows,
            "accounting_integrity": integrity, "valuation": valuation,
            "break_even": _break_evens(rows), "market_expectations_backsolve": market_expectations_backsolve(case),
            "confidence_limitations": {"research_only": True, "no_advice": True,
                "simplifications": ["gross openings are not treated as net additions", "VIBE is nested within convenience stores and never added as a separate outlet layer", "legacy/circular debt is excluded from incremental working capital", "cases are isolated bear/base/bull runs with no scenario weighting"]}}


def blocked_result(identity: Mapping[str, Any], reasons: Sequence[str], *, status: str = "blocked_invalid_inputs") -> dict[str, Any]:
    return {"schema_version": RESULT_SCHEMA, "model_archetype": MODEL_ARCHETYPE, "formula_id": FORMULA_ID,
            "module_version": MODULE_VERSION, "run_receipt": {"inputs_sha256": None}, "status": status,
            "blocked_reasons": sorted(set(str(x) for x in reasons)), "symbol": identity.get("symbol"),
            "event_ref": identity.get("event_ref"), "scenario": identity.get("case_label"),
            "inputs_lineage": [], "quarterly_schedule": [], "accounting_integrity": None,
            "valuation": None, "break_even": None, "market_expectations_backsolve": None,
            "confidence_limitations": {"research_only": True, "no_advice": True, "simplifications": ["blocked before calculation"]}}


def evaluate_with_financial_truth_gate(case: Mapping[str, Any], financial_truth_row: Mapping[str, Any]) -> dict[str, Any]:
    if not financial_truth_is_qualified(financial_truth_row):
        status = financial_truth_row.get("status") if isinstance(financial_truth_row, Mapping) else None
        return blocked_result(case if isinstance(case, Mapping) else {},
                              [f"financial_truth_status:{status or 'missing'}"],
                              status="blocked_financial_truth_not_qualified")
    try:
        return evaluate_case(case)
    except ValueError as error:
        return blocked_result(case if isinstance(case, Mapping) else {}, str(error).split("; "))


def default_case() -> dict[str, Any]:
    """Analyst fixture; real production output is still truth-gated."""
    a = lambda value, field="": _record(value, field=field)
    return {"symbol": "PSO", "event_ref": "PSO_FY2025_RETAIL_NETWORK_AND_CHANNEL_EXPANSION",
            "case_label": "base", "effective_date": "2025-06-30", "valuation_date": "2025-08-19",
            "inputs": {
                "quarter_ends": a(["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31", "2027-03-31", "2027-06-30"]),
                "starting_active_outlets": _record(3580, label_type="source", field="starting_active_outlets"),
                "starting_convenience_stores": _record(250, label_type="source", field="starting_convenience_stores"), "starting_vibe_stores": a(0), "starting_lpg_delivery_points": a(0),
                "gross_openings_schedule": a([107, 0, 0, 0, 0, 0, 0, 0]), "closures_or_reclassifications_schedule": a([38, 0, 0, 0, 0, 0, 0, 0]),
                "convenience_openings_schedule": a([60, 0, 0, 0, 0, 0, 0, 0]), "vibe_openings_schedule": a([3, 0, 0, 0, 0, 0, 0, 0]), "lpg_delivery_point_openings_schedule": a([5, 0, 0, 0, 0, 0, 0, 0]),
                "mature_litres_per_outlet_quarter_schedule": a([3_000_000] * 8), "realized_price_per_litre_schedule": a([280] * 8), "dealer_margin_per_litre_schedule": a([7] * 8), "mature_sales_per_store_quarter_schedule": a([4_000_000] * 8), "convenience_gross_margin_pct_schedule": a([25] * 8), "lpg_sales_per_delivery_point_quarter_schedule": a([1_000_000] * 8), "lpg_gross_margin_pct_schedule": a([20] * 8), "retention_rate_schedule": a([.98] * 8), "ramp_factor_by_cohort": a([.30, .50, .70, .85, 1, 1, 1, 1]),
                "sales_hires_schedule": a([8] * 8), "support_hires_schedule": a([12] * 8), "compensation_per_fte_quarter": a(500_000), "outlet_support_cost_per_active_outlet_quarter": a(20_000), "marketing_spend_schedule": a([30_000_000] + [10_000_000] * 7), "marketing_spend_per_active_outlet_quarter": a(3_000), "central_technology_cost_per_quarter": a(5_000_000), "dealer_commission_or_revenue_share_schedule": a([0] * 8), "other_incremental_opex_schedule": a([0] * 8),
                "owned_capex_schedule": a([100_000_000] + [20_000_000] * 7), "dealer_funded_capex_schedule": a([50_000_000] + [0] * 7), "central_infrastructure_capex_schedule": a([20_000_000] + [5_000_000] * 7), "depreciation_useful_life_years": a(10), "annual_interest_rate": a(14), "debt_financing_pct": a(50), "debt_repayment_schedule": a([0] * 8),
                "receivable_days_schedule": a([15] * 8), "inventory_days_schedule": a([20] * 8), "payable_days_schedule": a([15] * 8), "working_capital_per_active_outlet_quarter": a(150_000), "tax_rate": a(29), "shares_outstanding": a(469_000_000), "discount_rate_annual": a(18), "terminal_growth_rate": a(4), "current_market_price_pkr_per_share": a(300), "pre_expansion_fair_value_pkr_per_share": a(280),
            }}


def _real_identity() -> dict[str, Any]:
    return {"symbol": "PSO", "event_ref": "PSO_FY2025_RETAIL_NETWORK_AND_CHANNEL_EXPANSION", "case_label": "base", "effective_date": "2025-06-30", "valuation_date": "2025-08-19"}


def build(*, write: bool = True, financial_truth: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = financial_truth if financial_truth is not None else load_json(FINANCIAL_TRUTH_PATH, {"companies": {}})
    row = (state.get("companies") or {}).get("PSO") or {}
    result = evaluate_with_financial_truth_gate(_real_identity(), row)
    if write:
        save_json(OUTPUT_PATH, result)
    return result


if __name__ == "__main__":
    print(f"pso_sales_expansion_model: status={build()['status']}")
