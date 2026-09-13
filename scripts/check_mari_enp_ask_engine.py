"""Deterministic checks for the MARI E&P Ask Henneth engine."""
from __future__ import annotations

import copy
import json
import math

import mari_enp_ask_engine as ask
import mari_enp_scenario_lab as lab
import mari_enp_valuation_engine as nav

PASSED = 0
BANNED = ("buy", "sell", "accumulate", "target price", "price target", "you should")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(name + (": " + detail if detail else ""))
    PASSED += 1


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)


def q(value: float) -> str:
    return ask._q(value)


def golden_assumptions() -> dict:
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


def golden_case() -> dict:
    return {
        "symbol": "MARI",
        "case_id": ask.CASE_ID,
        "financial_truth_qualified": True,
        "assumptions_approved": True,
        "assumptions": golden_assumptions(),
        "scenarios": {
            "bear": {
                "recoverable_scenario": "low",
                "commodity_price_factor": 0.85,
                "discount_rate": 0.12,
                "geological_success_probability": 0.25,
                "commercial_success_probability": 0.40,
            },
            "base": {
                "recoverable_scenario": "base",
                "commodity_price_factor": 1.0,
                "discount_rate": 0.10,
                "geological_success_probability": 0.40,
                "commercial_success_probability": 0.50,
            },
            "bull": {
                "recoverable_scenario": "high",
                "commodity_price_factor": 1.15,
                "discount_rate": 0.08,
                "geological_success_probability": 0.55,
                "commercial_success_probability": 0.60,
            },
        },
        "grids": {
            "commodity_vs_reserves": {
                "commodity_price_factors": [0.85, 1.0, 1.15],
                "reserve_scenarios": ["low", "base", "high"],
            },
            "discount_vs_success": {
                "discount_rates": [0.08, 0.10, 0.12],
                "success_probabilities": [0.10, 0.20, 0.33],
            },
        },
    }


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def by_id(envelope: dict) -> dict:
    return {row["question_id"]: row for row in envelope["questions"]}


def assert_sections(row: dict, name: str) -> None:
    check(name + " section order", tuple(row["sections"]) == ask.SECTION_KEYS)
    for key, title in ask.SECTION_SPECS:
        section = row["sections"][key]
        check(name + " " + key + " title", section["title"] == title and section["key"] == key)
        check(name + " " + key + " text", isinstance(section["text"], str) and section["text"])
        if section["numbers"] is not None:
            for field, value in section["numbers"].items():
                check(name + " " + key + " " + field + " in text", q(value) in section["text"] or key in {"confidence"})


def main() -> None:
    check("ids", ask.FORMULA_ID == "enp_exploration.ask_henneth.v1")
    check("seven questions", len(ask.QUESTIONS) == 7)
    case = golden_case()
    seed = nav.compute_valuation({**copy.deepcopy(case["assumptions"]), "scenario": "base"})
    premium_usd = 0.35 * (seed["values"]["unrisked_npv_usd"] + seed["values"]["dry_hole_cost_usd"]) - seed["values"]["dry_hole_cost_usd"]
    premium_ps = premium_usd * 280.0 / 1_000_000_000.0
    case["market"] = {"latest_price_pkr": 700.0 + premium_ps, "undisturbed_price_pkr": 700.0}

    envelope = ask.evaluate_ask(case)
    check("computed status", envelope["status"] == ask.STATUS_COMPUTED)
    check("envelope keys", tuple(envelope) == ask.ENVELOPE_KEYS)
    check("question count", len(envelope["questions"]) == 7)
    check("question ids exact", [row["question_id"] for row in envelope["questions"]] == [item[0] for item in ask.QUESTIONS])
    check("question text exact", [row["question"] for row in envelope["questions"]] == [item[1] for item in ask.QUESTIONS])

    lab_result = lab.evaluate_lab(case)
    nav_result = nav.compute_valuation(lab.apply_scenario_params(case["assumptions"], case["scenarios"]["base"]))
    rows = by_id(envelope)
    for row in envelope["questions"]:
        assert_sections(row, row["question_id"])

    well = rows["well_cost_next_four_quarters"]["sections"]["financial_impact"]["numbers"]
    expected_well = sum(
        float(item["exploration_capex_usd"])
        for item in nav_result["quarterly_schedule"]
        if int(item["quarter_index"]) < 4
    )
    check("well cost ties to schedule", close(well["exploration_capex_next_four_quarters_usd"], expected_well))
    check("well cost PKR ties to FX", close(well["exploration_capex_next_four_quarters_pkr"], expected_well * 280.0))
    check("well cost uses gross * WI", close(well["exploration_capex_next_four_quarters_usd"], 2_000_000.0 * 1.0))

    timing = rows["first_production_timing"]["sections"]["financial_impact"]["numbers"]
    check("production delay ties to assumptions", close(timing["first_production_delay_quarters"], 1.0))
    check("drilling duration ties to assumptions", close(timing["drilling_duration_months"], 3.0))
    check("timing in conclusion", "quarter index 1" in rows["first_production_timing"]["sections"]["conclusion"]["text"])

    vs = rows["unrisked_vs_dry_hole"]["sections"]["valuation_impact"]["numbers"]
    check("unrisked ties to valuation engine", close(vs["unrisked_npv_pkr"], nav_result["values"]["unrisked_npv_pkr"]))
    check("dry hole ties to valuation engine", close(vs["dry_hole_cost_pkr"], nav_result["values"]["dry_hole_cost_pkr"]))
    check("risked identity in ask numbers", close(vs["risked_npv_pkr"], nav_result["values"]["risked_npv_pkr"]))

    per_share = rows["per_share_scenarios"]["sections"]["scenario_range"]["numbers"]
    check("bear per share ties to lab", close(per_share["bear_per_share_risked_pkr"], lab_result["scenarios"]["bear"]["values"]["per_share_risked_pkr"]))
    check("base per share ties to lab", close(per_share["base_per_share_risked_pkr"], lab_result["scenarios"]["base"]["values"]["per_share_risked_pkr"]))
    check("bull per share ties to lab", close(per_share["bull_per_share_risked_pkr"], lab_result["scenarios"]["bull"]["values"]["per_share_risked_pkr"]))
    check("bear below base below bull", per_share["bear_per_share_risked_pkr"] < per_share["base_per_share_risked_pkr"] < per_share["bull_per_share_risked_pkr"])

    implied = rows["implied_discovery_probability"]["sections"]["current_price_expectations"]["numbers"]
    check("p_base ties to lab", close(implied["p_base"], lab_result["expectations_gap"]["p_base"]))
    check("p_market ties to lab", close(implied["p_market"], lab_result["expectations_gap"]["p_market"]))
    check("delta ties to lab", close(implied["delta"], lab_result["expectations_gap"]["delta"]))
    check("delta is p_market minus p_base", close(implied["delta"], implied["p_market"] - implied["p_base"]))

    why = rows["why_acquire"]
    check("why acquire uses observed filing language", "Peshawar Block" in why["sections"]["observed_evidence"]["text"] or "working interest" in why["sections"]["observed_evidence"]["text"].lower())
    check("why acquire does not invent a buy motive", "you should" not in why["sections"]["conclusion"]["text"].lower())

    invalid = rows["invalidating_evidence"]
    watch = invalid["sections"]["what_to_watch"]["text"]
    check("invalidators present", all(item in watch for item in ask.INVALIDATORS))
    check("invalidators mention dry hole and working interest", "dry" in watch.lower() and "working interest" in watch.lower())

    no_market = copy.deepcopy(case)
    no_market.pop("market")
    no_market_env = ask.evaluate_ask(no_market)
    no_implied = by_id(no_market_env)["implied_discovery_probability"]["sections"]["current_price_expectations"]
    check("missing market still answers other questions", no_market_env["status"] == ask.STATUS_COMPUTED)
    check("implied probability fail-closed without market", no_implied["numbers"] is None and no_implied["status"] != ask.STATUS_COMPUTED)

    blocked = ask.evaluate_ask(
        {
            "financial_truth_qualified": False,
            "assumptions_approved": True,
            "assumptions": case["assumptions"],
            "scenarios": case["scenarios"],
            "grids": case["grids"],
            "market": case["market"],
        }
    )
    check("unqualified truth blocks ask", blocked["status"] == ask.STATUS_TRUTH)
    for row in blocked["questions"]:
        for key in ("financial_impact", "scenario_range", "valuation_impact", "current_price_expectations"):
            check("blocked " + row["question_id"] + " " + key, row["sections"][key]["numbers"] is None and row["sections"][key]["status"] == ask.STATUS_TRUTH)
        check("blocked still has observed evidence", row["sections"]["observed_evidence"]["status"] == ask.STATUS_OBSERVED)

    unapproved = ask.evaluate_ask({**case, "assumptions_approved": False})
    check("unapproved assumptions block ask", unapproved["status"] == ask.STATUS_TRUTH)

    hostile = copy.deepcopy(case)
    hostile["assumptions"]["working_interest"] = float("nan")
    hostile_env = ask.evaluate_ask(hostile)
    check("hostile inputs do not emit numbers", hostile_env["status"] != ask.STATUS_COMPUTED)
    check("hostile numeric sections empty", all(row["sections"]["valuation_impact"]["numbers"] is None for row in hostile_env["questions"]))

    repeat = ask.evaluate_ask(case)
    check("deterministic evaluate", json.dumps(repeat, sort_keys=True) == json.dumps(envelope, sort_keys=True))
    check("no NaN", all(not isinstance(item, float) or math.isfinite(item) for _, item in walk(envelope)))

    retained = ask.build(write=True)
    artifact = json.loads(ask.OUT.read_text(encoding="utf-8"))
    check("retained fail-closed", retained["status"] == ask.STATUS_TRUTH)
    check("retained has seven questions", len(retained["questions"]) == 7)
    check("retained artifact matches", artifact["status"] == retained["status"] and len(artifact["questions"]) == 7)
    check("retained identity", retained["symbol"] == "MARI" and retained["case_id"] == ask.CASE_ID)
    for row in retained["questions"]:
        assert_sections(row, "retained " + row["question_id"])
        check("retained no modelled numbers", row["sections"]["valuation_impact"]["numbers"] is None)
        check("retained observed evidence kept", "Peshawar" in row["sections"]["observed_evidence"]["text"] or "working interest" in row["sections"]["observed_evidence"]["text"].lower())
    check("repeat retained identical", json.dumps(ask.build(write=False), sort_keys=True) == json.dumps(retained, sort_keys=True))
    for _, item in walk(retained):
        if isinstance(item, str):
            lowered = item.lower()
            check("no advice language", not any(phrase in lowered for phrase in BANNED))

    print(f"{PASSED} checks passed")


if __name__ == "__main__":
    main()

