"""Deterministic checks for the MARI E&P risked-NAV valuation engine."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import mari_enp_valuation_engine as engine

PASSED = 0
DAYS = engine.DAYS_PER_QUARTER
BANNED = ("buy", "sell", "accumulate", "target price", "price target", "you should")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(name + (": " + detail if detail else ""))
    PASSED += 1


def close(left: float, right: float, tol: float = 1e-9) -> bool:
    return math.isclose(left, right, rel_tol=tol, abs_tol=1e-6)


def df(rate: float, quarter: int) -> float:
    return (1.0 + rate) ** (-(quarter + 1) * 0.25)


def golden_inputs() -> dict:
    return {
        "working_interest": 1.0,
        "operator_status": True,
        "well_cost": 2_000_000.0,
        "drilling_duration_months": 3.0,
        "geological_success_probability": 0.4,
        "commercial_success_probability": 0.5,
        "recoverable_reserves": {"low": 0.182625, "base": 0.36525, "high": 0.547875},
        "oil_gas_mix": {"gas": 0.8, "oil": 0.2},
        "initial_production": 1000.0,
        "decline_model": "exponential",
        "decline_rate": 0.0,
        "development_capex_schedule": [{"quarter_offset": 1, "amount_usd": 3_000_000.0}],
        "operating_cost_per_boe": 8.0,
        "royalty_rate": 0.125,
        "tax_rate": 0.29,
        "oil_price_usd_bbl": 80.0,
        "gas_price_usd_mmbtu": 4.0,
        "gas_mmbtu_per_boe": 6.0,
        "fx_pkr_usd": 280.0,
        "first_production_delay_quarters": 1,
        "discount_rate": 0.10,
        "fully_diluted_shares": 1_000_000_000.0,
        "max_life_quarters": 20,
    }


def independent_roll(inputs: dict, scenario: str = "base") -> dict:
    wi = float(inputs["working_interest"])
    tax = float(inputs["tax_rate"])
    royalty = float(inputs["royalty_rate"])
    opex = float(inputs["operating_cost_per_boe"])
    mix = inputs["oil_gas_mix"]
    value = mix["oil"] * inputs["oil_price_usd_bbl"] + mix["gas"] * inputs["gas_price_usd_mmbtu"] * inputs["gas_mmbtu_per_boe"]
    remaining = inputs["recoverable_reserves"][scenario] * 1_000_000.0
    delay = int(inputs["first_production_delay_quarters"])
    wacc = float(inputs["discount_rate"])
    model = inputs["decline_model"]
    decline = float(inputs["decline_rate"])
    b_value = float(inputs.get("hyperbolic_b") or 1.0)
    qi = float(inputs["initial_production"])
    drill = engine.drilling_quarters(float(inputs["drilling_duration_months"]))
    expl_share = float(inputs["well_cost"]) * wi
    expl = {i: expl_share / drill for i in range(drill)}
    expl[drill - 1] = expl_share - expl_share / drill * (drill - 1)
    dev = {int(row["quarter_offset"]): float(row["amount_usd"]) * wi for row in inputs["development_capex_schedule"]}
    success = 0.0
    dry = 0.0
    rows = []
    produced = 0.0
    for quarter in range(int(inputs.get("max_life_quarters", 80))):
        production = 0.0
        ncf = 0.0
        if quarter >= delay and remaining > 1e-12:
            years = (quarter - delay) * 0.25
            if model == "exponential":
                rate = qi * math.exp(-decline * years)
            else:
                rate = qi / (1.0 + b_value * decline * years) ** (1.0 / b_value)
            gross = min(rate * DAYS, remaining)
            remaining -= gross
            produced += gross
            production = gross * wi
            revenue = production * value
            roy = revenue * royalty
            opex_usd = production * opex
            operating = revenue - roy - opex_usd
            tax_usd = operating * tax if operating > 0.0 else 0.0
            ncf = operating - tax_usd
        e_cost = expl.get(quarter, 0.0)
        d_cost = dev.get(quarter, 0.0)
        if e_cost == 0.0 and d_cost == 0.0 and production == 0.0:
            continue
        factor = df(wacc, quarter)
        success += (-e_cost - d_cost + ncf) * factor
        dry += e_cost * (1.0 - tax) * factor
        rows.append(quarter)
    p_disc = inputs["geological_success_probability"] * inputs["commercial_success_probability"]
    return {
        "unrisked": success,
        "dry": dry,
        "risked": p_disc * success - (1.0 - p_disc) * dry,
        "p_disc": p_disc,
        "produced": produced,
        "value": value,
        "rows": rows,
    }


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def main() -> None:
    check("engine ids", engine.FORMULA_ID == "enp_exploration.risked_nav.v1" and engine.ENGINE_VERSION == "mari_enp_valuation_engine_v1")
    inputs = golden_inputs()
    check("golden assumptions validate", engine.validate_assumptions(inputs) == [])
    computed = engine.compute_valuation(inputs)
    expected = independent_roll(inputs)
    values = computed["values"]
    check("dry-hole after-tax identity", close(values["dry_hole_cost_usd"], expected["dry"]))
    check("dry-hole is well * (1-tax) * df0", close(values["dry_hole_cost_usd"], 2_000_000.0 * 0.71 * df(0.10, 0)))
    check("unrisked DCF matches independent roll-forward", close(values["unrisked_npv_usd"], expected["unrisked"]))
    check("reserves fully produced on zero-decline golden", close(values["produced_gross_boe"], 365_250.0))
    check("value per boe is oil/gas blend", close(values["value_per_boe_usd"], 35.2))
    check("p_disc is Pg * Pc", close(values["p_disc"], 0.2))
    check("risked identity", close(values["risked_npv_usd"], expected["risked"]))
    check(
        "risked formula components",
        close(values["risked_npv_usd"], 0.2 * values["unrisked_npv_usd"] - 0.8 * values["dry_hole_cost_usd"]),
    )
    check("PKR conversion", close(values["risked_npv_pkr"], values["risked_npv_usd"] * 280.0))
    check("per-share is risked / shares", close(computed["per_share"]["risked_pkr"], values["risked_npv_pkr"] / 1_000_000_000.0))
    check("no NaN in golden", all(not isinstance(item, float) or math.isfinite(item) for _, item in walk(computed)))

    production = [row for row in computed["quarterly_schedule"] if row["production_boe"] > 0.0]
    check("four production quarters", len(production) == 4)
    check("first production quarter index", production[0]["quarter_index"] == 1)
    check("quarter 0 is exploration writeoff row", computed["quarterly_schedule"][0]["phase"] == "exploration")
    check("quarter 0 success capex is pre-tax well", close(computed["quarterly_schedule"][0]["exploration_capex_usd"], 2_000_000.0))
    check(
        "quarter 0 dry cash is after-tax",
        close(computed["quarterly_schedule"][0]["dry_hole_net_cash_flow_usd"], -2_000_000.0 * 0.71),
    )

    p_be = computed["probabilities"]["break_even_discovery_probability"]
    check("break-even exists", p_be is not None)
    check(
        "break-even backsolve is zero EMV",
        close(p_be * values["unrisked_npv_usd"] - (1.0 - p_be) * values["dry_hole_cost_usd"], 0.0),
    )
    check("break-even formula Dry/(Unrisked+Dry)", close(p_be, values["dry_hole_cost_usd"] / (values["unrisked_npv_usd"] + values["dry_hole_cost_usd"])))
    check("market implied missing without premium", computed["probabilities"]["market_implied_missing"] == ["market_premium_pkr_per_share"])

    target_p = 0.35
    premium_usd = target_p * (values["unrisked_npv_usd"] + values["dry_hole_cost_usd"]) - values["dry_hole_cost_usd"]
    priced = copy.deepcopy(inputs)
    priced["market_premium_pkr_per_share"] = premium_usd * 280.0 / 1_000_000_000.0
    implied = engine.compute_valuation(priced)
    check("market-implied backsolve", close(implied["probabilities"]["market_implied_discovery_probability"], target_p, 1e-10))

    hyper = copy.deepcopy(inputs)
    hyper["decline_model"] = "hyperbolic"
    hyper["decline_rate"] = 0.25
    hyper["hyperbolic_b"] = 0.5
    hyper_result = engine.compute_valuation(hyper)
    hyper_expected = independent_roll(hyper)
    check("hyperbolic DCF matches independent roll-forward", close(hyper_result["values"]["unrisked_npv_usd"], hyper_expected["unrisked"]))
    check("hyperbolic produces less than zero-decline", hyper_result["values"]["produced_gross_boe"] <= 365_250.0 + 1e-6)

    wi_case = copy.deepcopy(inputs)
    wi_case["working_interest"] = 0.65
    wi_result = engine.compute_valuation(wi_case)
    check("working interest scales dry-hole cost", close(wi_result["values"]["dry_hole_cost_usd"], expected["dry"] * 0.65))

    operator = engine.compute_valuation(inputs)
    non_op = copy.deepcopy(inputs)
    non_op["operator_status"] = False
    non_op_result = engine.compute_valuation(non_op)
    check("operator_status does not change arithmetic", operator["values"] == non_op_result["values"])

    low = copy.deepcopy(inputs)
    low["scenario"] = "low"
    high = copy.deepcopy(inputs)
    high["scenario"] = "high"
    low_v = engine.compute_valuation(low)
    high_v = engine.compute_valuation(high)
    check("low scenario produces less oil than base", low_v["values"]["produced_gross_boe"] < values["produced_gross_boe"])
    check("high scenario produces more oil than base", high_v["values"]["produced_gross_boe"] > values["produced_gross_boe"])

    hostile = [
        ("NaN working interest", {"working_interest": float("nan")}, "working_interest"),
        ("infinite well cost", {"well_cost": float("inf")}, "well_cost"),
        ("boolean well cost", {"well_cost": True}, "well_cost"),
        ("zero working interest", {"working_interest": 0.0}, "working_interest"),
        ("Pg above 1", {"geological_success_probability": 1.01}, "geological_success_probability"),
        ("tax 100 percent", {"tax_rate": 1.0}, "tax_rate"),
        ("negative opex", {"operating_cost_per_boe": -1.0}, "operating_cost_per_boe"),
        ("mix not unit", {"oil_gas_mix": {"gas": 0.7, "oil": 0.2}}, "oil_gas_mix"),
        ("hyperbolic without b", {"decline_model": "hyperbolic"}, "hyperbolic_b"),
        ("production before drilling", {"first_production_delay_quarters": 0, "drilling_duration_months": 6.0}, "first_production_delay_quarters"),
        ("unknown field", {"mystery": 1}, "unknown valuation input"),
        ("reserves inverted", {"recoverable_reserves": {"low": 3.0, "base": 2.0, "high": 1.0}}, "low <= base <= high"),
        ("bool delay", {"first_production_delay_quarters": True}, "first_production_delay_quarters"),
        ("zero shares", {"fully_diluted_shares": 0.0}, "fully_diluted_shares"),
        ("WACC zero", {"discount_rate": 0.0}, "discount_rate"),
    ]
    for name, mutation, fragment in hostile:
        bad = copy.deepcopy(inputs)
        bad.update(mutation)
        violations = engine.validate_assumptions(bad)
        check(f"hostile reject: {name}", any(fragment in item for item in violations), str(violations))
        raised = False
        try:
            engine.compute_valuation(bad)
        except ValueError as error:
            raised = fragment in str(error)
        check(f"compute raises: {name}", raised)

    qualified_case = {
        "symbol": "MARI",
        "case_id": engine.CASE_ID,
        "financial_truth_qualified": True,
        "assumptions_approved": True,
        "assumptions": inputs,
    }
    computed_case = engine.evaluate_case(qualified_case)
    check("evaluate computed status", computed_case["status"] == "computed")
    check("evaluate envelope keys", tuple(computed_case) == engine.ENVELOPE_KEYS)
    check("evaluate values present", computed_case["values"] is not None and computed_case["per_share"] is not None)
    check("repeat evaluate is identical", json.dumps(engine.evaluate_case(qualified_case), sort_keys=True) == json.dumps(computed_case, sort_keys=True))

    blocked_truth = engine.evaluate_case(
        {
            "symbol": "MARI",
            "financial_truth_qualified": False,
            "assumptions_approved": True,
            "assumptions": inputs,
        }
    )
    check("unqualified truth fail-closed status", blocked_truth["status"] == engine.STATUS_TRUTH)
    check("unqualified truth has no numbers", blocked_truth["values"] is None and blocked_truth["per_share"] is None and blocked_truth["probabilities"] is None)
    check("unqualified truth empty schedule", blocked_truth["quarterly_schedule"] == [])
    check("unqualified truth reason", "financial_truth_not_qualified" in blocked_truth["blocked_reasons"])
    check("complete assumptions still blocked without truth", blocked_truth["status"] != "computed")

    blocked_unapproved = engine.evaluate_case(
        {
            "symbol": "MARI",
            "financial_truth_qualified": True,
            "assumptions_approved": False,
            "assumptions": inputs,
        }
    )
    check("unapproved assumptions fail-closed", blocked_unapproved["status"] == engine.STATUS_TRUTH)
    check("unapproved assumptions have no numbers", blocked_unapproved["values"] is None)
    check("unapproved reason", "assumptions_unapproved" in blocked_unapproved["blocked_reasons"])

    blocked_missing = engine.evaluate_case(
        {
            "symbol": "MARI",
            "financial_truth_qualified": True,
            "assumptions_approved": True,
            "assumptions": {},
        }
    )
    check("missing inputs status", blocked_missing["status"] == engine.STATUS_MISSING)
    check("missing inputs list required fields", blocked_missing["missing_inputs"] == sorted(engine.REQUIRED_FIELDS) or set(blocked_missing["missing_inputs"]) == set(engine.REQUIRED_FIELDS))
    check("missing inputs have no numbers", blocked_missing["values"] is None)

    retained = engine.build(write=True)
    artifact = json.loads(engine.OUT.read_text(encoding="utf-8"))
    check("retained status is fail-closed truth gate", retained["status"] == engine.STATUS_TRUTH)
    check("retained artifact matches builder", artifact["status"] == retained["status"] and artifact["values"] is None)
    check("retained missing every operand", set(retained["missing_inputs"]) == set(engine.REQUIRED_FIELDS))
    check("retained does not invent numbers", retained["values"] is None and retained["per_share"] is None and retained["probabilities"] is None)
    check("retained identity", retained["symbol"] == "MARI" and retained["case_id"] == engine.CASE_ID)
    check("retained reasons include operand gap", "no_model_ready_E_and_P_operands" in retained["blocked_reasons"])
    check("repeat retained is identical", json.dumps(engine.build(write=False), sort_keys=True) == json.dumps(retained, sort_keys=True))
    for _, item in walk(retained):
        if isinstance(item, str):
            lowered = item.lower()
            check("no advice language", not any(phrase in lowered for phrase in BANNED))

    print(f"{PASSED} checks passed")


if __name__ == "__main__":
    main()
