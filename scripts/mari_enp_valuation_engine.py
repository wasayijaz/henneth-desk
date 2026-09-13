"""E&P exploration event risked-NAV / project-NPV kernel (MARI lane).

Deterministic research arithmetic only. No LLM, no network, no advice.
Identical inputs produce identical outputs. Valid inputs never emit NaN/null
numeric results. The retained MARI path stays fail-closed until financial
truth is qualified and every assumption is present and approved.

Risked identity (USD, then converted at explicit FX):

    P_disc = Pg * Pc
    E[NPV] = P_disc * Unrisked_NPV - (1 - P_disc) * Dry_hole_cost

Unrisked_NPV is the commercial-discovery DCF (production net of royalty,
opex and cash tax, minus exploration and development capex). Dry_hole_cost
is the after-tax exploration writeoff. Working interest scales production,
opex and capex. operator_status is required descriptive provenance and does
not change arithmetic.
"""
from __future__ import annotations

from typing import Any, Mapping
import hashlib
import json
import math
from pathlib import Path

from psx_data import ROOT, STATE, load_json, save_json

ENGINE_VERSION = "mari_enp_valuation_engine_v1"
FORMULA_ID = "enp_exploration.risked_nav.v1"
RESULT_SCHEMA = "mari_enp_valuation_engine_result_v1"
CASE_ID = "case_mari_working_interest_observed_v1"
SYMBOL = "MARI"
CASE_FAMILY = "e_and_p"
OUT = STATE / "company_intel" / "mari_enp_valuation_engine.json"

STATUS_COMPUTED = "computed"
STATUS_TRUTH = "blocked_financial_truth_not_qualified"
STATUS_MISSING = "blocked_missing_inputs"

MAX_ABS_NUMBER = 1.0e16
MAX_SCHEDULE_ROWS = 256
MAX_LIFE_QUARTERS = 80
DAYS_PER_QUARTER = 365.25 / 4.0
YEAR_FRACTION = 0.25
SCENARIOS = ("low", "base", "high")
DECLINE_MODELS = ("exponential", "hyperbolic")

REQUIRED_FIELDS = (
    "working_interest",
    "operator_status",
    "well_cost",
    "drilling_duration_months",
    "geological_success_probability",
    "commercial_success_probability",
    "recoverable_reserves",
    "oil_gas_mix",
    "initial_production",
    "decline_model",
    "decline_rate",
    "development_capex_schedule",
    "operating_cost_per_boe",
    "royalty_rate",
    "tax_rate",
    "oil_price_usd_bbl",
    "gas_price_usd_mmbtu",
    "gas_mmbtu_per_boe",
    "fx_pkr_usd",
    "first_production_delay_quarters",
    "discount_rate",
    "fully_diluted_shares",
)
OPTIONAL_FIELDS = (
    "hyperbolic_b",
    "max_life_quarters",
    "market_premium_pkr_per_share",
    "scenario",
)
ALLOWED_FIELDS = frozenset(REQUIRED_FIELDS + OPTIONAL_FIELDS)

ENVELOPE_KEYS = (
    "schema_version",
    "formula_id",
    "engine_version",
    "case_id",
    "symbol",
    "case_family",
    "status",
    "blocked_reasons",
    "missing_inputs",
    "financial_truth_status",
    "assumptions_approved",
    "run_receipt",
    "scenario",
    "inputs_used",
    "quarterly_schedule",
    "values",
    "per_share",
    "probabilities",
    "confidence_limitations",
    "policy",
)


def _is_bool(value: Any) -> bool:
    return type(value) is bool


def _finite(value: Any) -> float | None:
    if _is_bool(value) or type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > MAX_ABS_NUMBER:
        return None
    return number


def _safe(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) > MAX_ABS_NUMBER:
            raise ValueError("non-finite or out-of-range arithmetic result")
        return value
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _in_bounds(number: float, low: float, low_inclusive: bool, high: float, high_inclusive: bool) -> bool:
    lower_ok = number > low or (low_inclusive and number == low)
    upper_ok = number < high or (high_inclusive and number == high)
    return lower_ok and upper_ok


def _int_ge(value: Any, minimum: int, maximum: int) -> int | None:
    if _is_bool(value) or type(value) is not int:
        return None
    if value < minimum or value > maximum:
        return None
    return value


def drilling_quarters(duration_months: float) -> int:
    return int(math.ceil(duration_months / 3.0))


def discount_factor(annual_rate: float, quarter_index: int) -> float:
    return _safe((1.0 + annual_rate) ** (-(quarter_index + 1) * YEAR_FRACTION))


def production_rate(initial: float, model: str, decline_rate: float, b: float, years: float) -> float:
    if model == "exponential":
        return _safe(initial * math.exp(-decline_rate * years))
    inner = _safe(1.0 + b * decline_rate * years)
    if inner <= 0.0:
        raise ValueError("hyperbolic decline produced a non-positive rate base")
    return _safe(initial / inner ** (1.0 / b))


def validate_assumptions(inputs: Any) -> list[str]:
    if type(inputs) is not dict:
        return ["assumptions: must be an exact mapping"]
    violations: list[str] = []
    for field in sorted(set(inputs) - ALLOWED_FIELDS):
        violations.append(f"{field}: unknown valuation input")
    missing = [field for field in REQUIRED_FIELDS if field not in inputs]
    for field in missing:
        violations.append(f"{field}: missing required input")
    if missing:
        return violations

    wi = _finite(inputs["working_interest"])
    if wi is None or not _in_bounds(wi, 0.0, False, 1.0, True):
        violations.append("working_interest: must be a finite number in (0, 1]")
    if not _is_bool(inputs["operator_status"]):
        violations.append("operator_status: must be a boolean")

    well_cost = _finite(inputs["well_cost"])
    if well_cost is None or well_cost < 0.0:
        violations.append("well_cost: must be a finite number >= 0")
    duration = _finite(inputs["drilling_duration_months"])
    if duration is None or not _in_bounds(duration, 0.0, False, 120.0, True):
        violations.append("drilling_duration_months: must be a finite number in (0, 120]")

    pg = _finite(inputs["geological_success_probability"])
    pc = _finite(inputs["commercial_success_probability"])
    if pg is None or not _in_bounds(pg, 0.0, False, 1.0, True):
        violations.append("geological_success_probability: must be a finite number in (0, 1]")
    if pc is None or not _in_bounds(pc, 0.0, False, 1.0, True):
        violations.append("commercial_success_probability: must be a finite number in (0, 1]")

    reserves = inputs["recoverable_reserves"]
    if type(reserves) is not dict:
        violations.append("recoverable_reserves: must be a mapping with low/base/high")
    else:
        parsed: dict[str, float] = {}
        for key in SCENARIOS:
            amount = _finite(reserves.get(key))
            if amount is None or not _in_bounds(amount, 0.0, False, 1.0e6, True):
                violations.append(f"recoverable_reserves.{key}: must be a finite mmboe in (0, 1e6]")
            else:
                parsed[key] = amount
        if len(parsed) == 3 and not (parsed["low"] <= parsed["base"] <= parsed["high"]):
            violations.append("recoverable_reserves: must satisfy low <= base <= high")

    mix = inputs["oil_gas_mix"]
    if type(mix) is not dict:
        violations.append("oil_gas_mix: must be a mapping with gas and oil fractions")
    else:
        gas = _finite(mix.get("gas"))
        oil = _finite(mix.get("oil"))
        if (
            gas is None
            or oil is None
            or not _in_bounds(gas, 0.0, True, 1.0, True)
            or not _in_bounds(oil, 0.0, True, 1.0, True)
        ):
            violations.append("oil_gas_mix: gas and oil must be finite fractions in [0, 1]")
        elif abs((gas + oil) - 1.0) > 1e-12:
            violations.append("oil_gas_mix: gas + oil must equal 1")

    initial = _finite(inputs["initial_production"])
    if initial is None or not _in_bounds(initial, 0.0, False, 1.0e6, True):
        violations.append("initial_production: must be a finite boepd in (0, 1e6]")
    model = inputs["decline_model"]
    if type(model) is not str or model not in DECLINE_MODELS:
        violations.append("decline_model: must be exponential or hyperbolic")
    decline = _finite(inputs["decline_rate"])
    if decline is None or not _in_bounds(decline, 0.0, True, 5.0, True):
        violations.append("decline_rate: must be a finite annual rate in [0, 5]")
    if model == "hyperbolic":
        b_value = _finite(inputs.get("hyperbolic_b"))
        if b_value is None or not _in_bounds(b_value, 0.0, False, 2.0, True):
            violations.append("hyperbolic_b: required for hyperbolic decline and must be in (0, 2]")

    schedule = inputs["development_capex_schedule"]
    if type(schedule) is not list or len(schedule) > MAX_SCHEDULE_ROWS:
        violations.append("development_capex_schedule: must be a list of at most 256 rows")
    else:
        seen: set[int] = set()
        for index, row in enumerate(schedule):
            if type(row) is not dict:
                violations.append(f"development_capex_schedule[{index}]: must be a mapping")
                continue
            if set(row) - {"quarter_offset", "amount_usd"}:
                violations.append(f"development_capex_schedule[{index}]: unknown field")
            offset = _int_ge(row.get("quarter_offset"), 0, MAX_LIFE_QUARTERS - 1)
            amount = _finite(row.get("amount_usd"))
            if offset is None:
                violations.append(
                    f"development_capex_schedule[{index}].quarter_offset: must be an integer in [0, 79]"
                )
            elif offset in seen:
                violations.append(f"development_capex_schedule[{index}].quarter_offset: duplicate offset")
            else:
                seen.add(offset)
            if amount is None or amount < 0.0:
                violations.append(
                    f"development_capex_schedule[{index}].amount_usd: must be a finite number >= 0"
                )

    for field, low_inclusive, high in (
        ("operating_cost_per_boe", True, 1000.0),
        ("oil_price_usd_bbl", False, 500.0),
        ("gas_price_usd_mmbtu", False, 100.0),
        ("gas_mmbtu_per_boe", False, 20.0),
        ("fx_pkr_usd", False, 1000.0),
    ):
        number = _finite(inputs[field])
        if number is None or not _in_bounds(number, 0.0, low_inclusive, high, True):
            left = "[" if low_inclusive else "("
            violations.append(f"{field}: must be a finite number in {left}0, {high:g}]")

    royalty = _finite(inputs["royalty_rate"])
    tax = _finite(inputs["tax_rate"])
    if royalty is None or not _in_bounds(royalty, 0.0, True, 1.0, False):
        violations.append("royalty_rate: must be a finite number in [0, 1)")
    if tax is None or not _in_bounds(tax, 0.0, True, 1.0, False):
        violations.append("tax_rate: must be a finite number in [0, 1)")

    delay = _int_ge(inputs["first_production_delay_quarters"], 0, MAX_LIFE_QUARTERS - 1)
    if delay is None:
        violations.append("first_production_delay_quarters: must be an integer in [0, 79]")
    elif duration is not None and duration > 0.0 and delay < drilling_quarters(duration) - 1:
        violations.append("first_production_delay_quarters: must not start before drilling completes")

    wacc = _finite(inputs["discount_rate"])
    if wacc is None or not _in_bounds(wacc, 0.0, False, 1.0, False):
        violations.append("discount_rate: must be a finite WACC in (0, 1)")
    shares = _finite(inputs["fully_diluted_shares"])
    if shares is None or not _in_bounds(shares, 0.0, False, 5.0e11, True):
        violations.append("fully_diluted_shares: must be a finite number in (0, 5e11]")

    if "max_life_quarters" in inputs and _int_ge(inputs["max_life_quarters"], 1, MAX_LIFE_QUARTERS) is None:
        violations.append("max_life_quarters: must be an integer in [1, 80]")
    if "scenario" in inputs and inputs["scenario"] not in SCENARIOS:
        violations.append("scenario: must be one of low, base, high")
    if "market_premium_pkr_per_share" in inputs:
        premium = _finite(inputs["market_premium_pkr_per_share"])
        if premium is None or abs(premium) > 1.0e9:
            violations.append("market_premium_pkr_per_share: must be a finite number")
    return violations


def _exploration_amounts(well_cost: float, working_interest: float, duration_months: float) -> dict[int, float]:
    quarters = drilling_quarters(duration_months)
    share = _safe(well_cost * working_interest)
    amounts: dict[int, float] = {}
    remaining = share
    for index in range(quarters):
        if index == quarters - 1:
            amounts[index] = _safe(remaining)
        else:
            part = _safe(share / quarters)
            amounts[index] = part
            remaining = _safe(remaining - part)
    return amounts


def _roll_forward(inputs: Mapping[str, Any], scenario: str) -> dict[str, Any]:
    working_interest = float(inputs["working_interest"])
    tax_rate = float(inputs["tax_rate"])
    royalty_rate = float(inputs["royalty_rate"])
    opex = float(inputs["operating_cost_per_boe"])
    oil_price = float(inputs["oil_price_usd_bbl"])
    gas_price = float(inputs["gas_price_usd_mmbtu"])
    gas_mmbtu = float(inputs["gas_mmbtu_per_boe"])
    gas_fraction = float(inputs["oil_gas_mix"]["gas"])
    oil_fraction = float(inputs["oil_gas_mix"]["oil"])
    initial = float(inputs["initial_production"])
    model = str(inputs["decline_model"])
    decline_rate = float(inputs["decline_rate"])
    b_value = float(inputs["hyperbolic_b"]) if model == "hyperbolic" else 1.0
    delay = int(inputs["first_production_delay_quarters"])
    wacc = float(inputs["discount_rate"])
    life = int(inputs["max_life_quarters"]) if "max_life_quarters" in inputs else MAX_LIFE_QUARTERS
    remaining = _safe(float(inputs["recoverable_reserves"][scenario]) * 1_000_000.0)
    value_per_boe = _safe(oil_fraction * oil_price + gas_fraction * gas_price * gas_mmbtu)

    exploration = _exploration_amounts(
        float(inputs["well_cost"]), working_interest, float(inputs["drilling_duration_months"])
    )
    development = {
        int(row["quarter_offset"]): _safe(float(row["amount_usd"]) * working_interest)
        for row in inputs["development_capex_schedule"]
    }
    rows: list[dict[str, Any]] = []
    produced = 0.0

    for quarter in range(life):
        expl = exploration.get(quarter, 0.0)
        dev = development.get(quarter, 0.0)
        production_boe = 0.0
        gross_revenue = 0.0
        royalty = 0.0
        opex_usd = 0.0
        tax = 0.0
        operating_net = 0.0
        if quarter >= delay and remaining > 1e-12:
            years = (quarter - delay) * YEAR_FRACTION
            rate = production_rate(initial, model, decline_rate, b_value, years)
            gross = _safe(min(rate * DAYS_PER_QUARTER, remaining))
            remaining = _safe(remaining - gross)
            produced = _safe(produced + gross)
            production_boe = _safe(gross * working_interest)
            gross_revenue = _safe(production_boe * value_per_boe)
            royalty = _safe(gross_revenue * royalty_rate)
            opex_usd = _safe(production_boe * opex)
            operating_net = _safe(gross_revenue - royalty - opex_usd)
            tax = _safe(operating_net * tax_rate if operating_net > 0.0 else 0.0)
        if expl == 0.0 and dev == 0.0 and production_boe == 0.0:
            continue
        if production_boe > 0.0 and (expl > 0.0 or dev > 0.0):
            phase = "development_and_production"
        elif production_boe > 0.0:
            phase = "production"
        elif expl > 0.0:
            phase = "exploration"
        else:
            phase = "development"
        success_net = _safe(-expl - dev + operating_net - tax)
        dry_net = _safe(-expl * (1.0 - tax_rate)) if expl > 0.0 else 0.0
        factor = discount_factor(wacc, quarter)
        rows.append(
            _safe(
                {
                    "quarter_index": quarter,
                    "phase": phase,
                    "discount_factor": factor,
                    "exploration_capex_usd": expl,
                    "development_capex_usd": dev,
                    "production_boe": production_boe,
                    "gross_revenue_usd": gross_revenue,
                    "royalty_usd": royalty,
                    "opex_usd": opex_usd,
                    "tax_usd": tax,
                    "success_net_cash_flow_usd": success_net,
                    "dry_hole_net_cash_flow_usd": dry_net,
                    "discounted_success_usd": _safe(success_net * factor),
                    "discounted_dry_hole_usd": _safe(dry_net * factor),
                }
            )
        )

    return {
        "scenario": scenario,
        "rows": rows,
        "unrisked_npv_usd": _safe(math.fsum(row["discounted_success_usd"] for row in rows)),
        "dry_hole_cost_usd": _safe(-math.fsum(row["discounted_dry_hole_usd"] for row in rows)),
        "produced_gross_boe": produced,
        "value_per_boe_usd": value_per_boe,
    }


def _probabilities(unrisked: float, dry_cost: float, p_disc: float, premium_usd: float | None) -> dict[str, Any]:
    spread = _safe(unrisked + dry_cost)
    break_even = None
    break_even_note = None
    if abs(spread) < 1e-12:
        break_even_note = "degenerate spread between unrisked NPV and dry-hole cost"
    else:
        candidate = _safe(dry_cost / spread)
        if 0.0 < candidate <= 1.0:
            break_even = candidate
        else:
            break_even_note = "break-even discovery probability outside (0, 1]"

    implied = None
    implied_note = None
    implied_missing: list[str] = []
    if premium_usd is None:
        implied_missing = ["market_premium_pkr_per_share"]
    elif abs(spread) < 1e-12:
        implied_note = "degenerate spread between unrisked NPV and dry-hole cost"
    else:
        candidate = _safe((premium_usd + dry_cost) / spread)
        if 0.0 <= candidate <= 1.0:
            implied = candidate
        else:
            implied_note = "market-implied discovery probability outside [0, 1]"
    return {
        "p_disc": p_disc,
        "risked_npv_usd": _safe(p_disc * unrisked - (1.0 - p_disc) * dry_cost),
        "break_even_discovery_probability": break_even,
        "break_even_note": break_even_note,
        "market_implied_discovery_probability": implied,
        "market_implied_note": implied_note,
        "market_implied_missing": implied_missing,
    }


def compute_valuation(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Pure arithmetic for a contract-valid assumption set. Raises on hostile input."""
    violations = validate_assumptions(inputs)
    if violations:
        raise ValueError("; ".join(violations))
    scenario = inputs.get("scenario", "base")
    rolled = _roll_forward(inputs, scenario)
    p_disc = _safe(
        float(inputs["geological_success_probability"]) * float(inputs["commercial_success_probability"])
    )
    fx = float(inputs["fx_pkr_usd"])
    shares = float(inputs["fully_diluted_shares"])
    premium = None
    if "market_premium_pkr_per_share" in inputs:
        premium = _safe(float(inputs["market_premium_pkr_per_share"]) * shares / fx)
    stats = _probabilities(rolled["unrisked_npv_usd"], rolled["dry_hole_cost_usd"], p_disc, premium)
    unrisked_pkr = _safe(rolled["unrisked_npv_usd"] * fx)
    dry_pkr = _safe(rolled["dry_hole_cost_usd"] * fx)
    risked_pkr = _safe(stats["risked_npv_usd"] * fx)
    return _safe(
        {
            "scenario": scenario,
            "p_disc": p_disc,
            "quarterly_schedule": rolled["rows"],
            "values": {
                "dry_hole_cost_usd": rolled["dry_hole_cost_usd"],
                "unrisked_npv_usd": rolled["unrisked_npv_usd"],
                "risked_npv_usd": stats["risked_npv_usd"],
                "dry_hole_cost_pkr": dry_pkr,
                "unrisked_npv_pkr": unrisked_pkr,
                "risked_npv_pkr": risked_pkr,
                "p_disc": p_disc,
                "produced_gross_boe": rolled["produced_gross_boe"],
                "value_per_boe_usd": rolled["value_per_boe_usd"],
            },
            "per_share": {
                "risked_pkr": _safe(risked_pkr / shares),
                "unrisked_pkr": _safe(unrisked_pkr / shares),
            },
            "probabilities": {
                "break_even_discovery_probability": stats["break_even_discovery_probability"],
                "break_even_note": stats["break_even_note"],
                "market_implied_discovery_probability": stats["market_implied_discovery_probability"],
                "market_implied_note": stats["market_implied_note"],
                "market_implied_missing": stats["market_implied_missing"],
            },
        }
    )


def _limitations() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "single_point_estimate": True,
        "simplifications": [
            "equal 365.25/4-day quarters; production uses the start-of-quarter instantaneous rate",
            "exponential q(t)=qi*exp(-D*t) or hyperbolic q(t)=qi/(1+b*Di*t)^(1/b); t is years from first production",
            "recoverable mmboe is gross field; working interest scales production, opex and capex",
            "dry-hole cost is the discounted after-tax exploration writeoff; success case treats exploration as pre-tax capex with no DD&A shield",
            "royalty on working-interest revenue; cash tax on positive operating net only; no loss carryforward",
            "operator_status is descriptive provenance and does not change cash flows",
            "commodity prices, opex, royalty, tax and FX are flat over field life",
        ],
    }


def _policy() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "no_order": True,
        "fail_closed_without_qualified_financial_truth": True,
        "fail_closed_without_approved_assumptions": True,
        "synthetic_numbers_not_written_to_retained_state": True,
    }


def _blank_envelope(
    status: str,
    reasons: list[str],
    missing: list[str],
    truth_status: str,
    approved: bool,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = identity or {}
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "case_id": identity.get("case_id") or CASE_ID,
        "symbol": identity.get("symbol") or SYMBOL,
        "case_family": CASE_FAMILY,
        "status": status,
        "blocked_reasons": sorted(set(str(reason) for reason in reasons if type(reason) is str and reason)),
        "missing_inputs": sorted(set(missing)),
        "financial_truth_status": truth_status,
        "assumptions_approved": approved,
        "run_receipt": {"inputs_sha256": None, "contract_version": ENGINE_VERSION},
        "scenario": None,
        "inputs_used": None,
        "quarterly_schedule": [],
        "values": None,
        "per_share": None,
        "probabilities": None,
        "confidence_limitations": _limitations(),
        "policy": _policy(),
    }


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Gate then compute. Unqualified truth or unapproved assumptions never emit numbers."""
    if type(case) is not dict:
        return _blank_envelope(
            STATUS_MISSING,
            ["case: must be an exact mapping"],
            list(REQUIRED_FIELDS),
            "unknown",
            False,
        )
    truth_qualified = case.get("financial_truth_qualified") is True
    approved = case.get("assumptions_approved") is True
    assumptions = case.get("assumptions")
    identity = {
        "case_id": case.get("case_id") or CASE_ID,
        "symbol": case.get("symbol") or SYMBOL,
    }
    if not truth_qualified or not approved:
        missing = [
            field for field in REQUIRED_FIELDS if type(assumptions) is not dict or field not in assumptions
        ]
        reasons = []
        if not truth_qualified:
            reasons.append("financial_truth_not_qualified")
        if not approved:
            reasons.append("assumptions_unapproved")
        truth_status = "qualified" if truth_qualified else "not_qualified"
        return _blank_envelope(STATUS_TRUTH, reasons, missing, truth_status, approved, identity)

    if type(assumptions) is not dict:
        return _blank_envelope(
            STATUS_MISSING, ["assumptions_missing"], list(REQUIRED_FIELDS), "qualified", True, identity
        )
    violations = validate_assumptions(assumptions)
    if violations:
        missing = [field for field in REQUIRED_FIELDS if field not in assumptions]
        return _blank_envelope(STATUS_MISSING, violations, missing, "qualified", True, identity)

    computed = compute_valuation(assumptions)
    canonical = json.dumps(assumptions, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return _safe(
        {
            "schema_version": RESULT_SCHEMA,
            "formula_id": FORMULA_ID,
            "engine_version": ENGINE_VERSION,
            "case_id": identity["case_id"],
            "symbol": identity["symbol"],
            "case_family": CASE_FAMILY,
            "status": STATUS_COMPUTED,
            "blocked_reasons": [],
            "missing_inputs": [],
            "financial_truth_status": "qualified",
            "assumptions_approved": True,
            "run_receipt": {"inputs_sha256": digest, "contract_version": ENGINE_VERSION},
            "scenario": computed["scenario"],
            "inputs_used": json.loads(canonical),
            "quarterly_schedule": computed["quarterly_schedule"],
            "values": computed["values"],
            "per_share": computed["per_share"],
            "probabilities": computed["probabilities"],
            "confidence_limitations": _limitations(),
            "policy": _policy(),
        }
    )


def _mari_truth(root: Path | None = None) -> dict[str, Any]:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "financial_truth_qualification.json", {})
    row = ((payload.get("companies") or {}).get(SYMBOL) or {})
    return row if type(row) is dict else {}


def _enp_assumptions_approved(root: Path | None = None) -> bool:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "financial_engine_assumptions.json", {})
    records = payload.get("records") if type(payload) is dict else None
    if type(records) is not list:
        return False
    for record in records:
        if type(record) is not dict or record.get("symbol") != SYMBOL or record.get("approved") is not True:
            continue
        metric = str(record.get("metric") or record.get("assumption") or record.get("label") or "")
        if any(token in metric.lower() for token in ("enp", "peshawar", "working_interest", "risked_nav")):
            return True
    return False


def build_retained_valuation(root: Path | None = None, *, write: bool = False) -> dict[str, Any]:
    """Fail-closed retained MARI envelope. Never invents project economics."""
    root = root or ROOT
    truth = _mari_truth(root)
    qualified = truth.get("status") == "qualified"
    approved = _enp_assumptions_approved(root)
    cases = load_json(root / "state" / "company_intel" / "intelligence_cases.json", {})
    company = ((cases.get("companies") or {}).get(SYMBOL) or {})
    matches = [
        row for row in (company.get("cases") or [])
        if type(row) is dict and row.get("case_id") == CASE_ID
    ]
    extra = ["no_model_ready_E_and_P_operands"]
    if not matches:
        extra.append("observed_mari_case_seed_missing")
    if not qualified:
        tie = truth.get("financial_tie_out") or {}
        extra.append("financial_truth_not_qualified: " + str(tie.get("reason") or "financial truth is not qualified"))
    if not approved:
        extra.append("assumptions_unapproved")
    envelope = evaluate_case(
        {
            "symbol": SYMBOL,
            "case_id": CASE_ID,
            "financial_truth_qualified": qualified,
            "assumptions_approved": approved,
            "assumptions": {},
        }
    )
    envelope["blocked_reasons"] = sorted(set(list(envelope["blocked_reasons"]) + extra))
    envelope["missing_inputs"] = list(REQUIRED_FIELDS)
    if write:
        save_json(root / "state" / "company_intel" / "mari_enp_valuation_engine.json", envelope)
    return envelope


def build(*, write: bool = True) -> dict[str, Any]:
    return build_retained_valuation(ROOT, write=write)


def main() -> None:
    envelope = build(write=True)
    print(f"mari_enp_valuation_engine: {envelope['status']} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

