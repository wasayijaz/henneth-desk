"""Deterministic checks for the MARI E&P scenario lab and expectations gap."""
from __future__ import annotations

import copy
import json
import math

import mari_enp_scenario_lab as lab
import mari_enp_valuation_engine as nav

PASSED = 0
BANNED = ("buy", "sell", "accumulate", "target price", "price target", "you should")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(name + (": " + detail if detail else ""))
    PASSED += 1


def close(left: float, right: float, tol: float = 1e-9) -> bool:
    return math.isclose(left, right, rel_tol=tol, abs_tol=1e-6)


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
    assumptions = golden_assumptions()
    return {
        "symbol": "MARI",
        "case_id": lab.CASE_ID,
        "financial_truth_qualified": True,
        "assumptions_approved": True,
        "assumptions": assumptions,
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


def implied_p(unrisked_pkr: float, dry_pkr: float, premium_ps: float, shares: float, fx: float) -> float:
    unrisked_usd = unrisked_pkr / fx
    dry_usd = dry_pkr / fx
    premium_usd = premium_ps * shares / fx
    return (premium_usd + dry_usd) / (unrisked_usd + dry_usd)


def main() -> None:
    check("ids", lab.FORMULA_ID == "enp_exploration.scenario_lab.v1" and lab.GAP_FORMULA_ID == "enp_exploration.expectations_gap.v1")
    case = golden_case()
    base_seed = nav.compute_valuation({**copy.deepcopy(case["assumptions"]), "scenario": "base"})
    unrisked_usd = base_seed["values"]["unrisked_npv_usd"]
    dry_usd = base_seed["values"]["dry_hole_cost_usd"]
    target_p_market = 0.35
    premium_usd = target_p_market * (unrisked_usd + dry_usd) - dry_usd
    premium_ps = premium_usd * 280.0 / 1_000_000_000.0
    case["market"] = {"latest_price_pkr": 700.0 + premium_ps, "undisturbed_price_pkr": 700.0}
    check("golden lab case validates", lab.validate_lab_case(case) == [])
    result = lab.evaluate_lab(case)
    check("computed status", result["status"] == lab.STATUS_COMPUTED)
    check("envelope keys exact", tuple(result) == lab.ENVELOPE_KEYS)
    check("uses valuation engine version", result["valuation_engine_version"] == nav.ENGINE_VERSION)

    for label in ("bear", "base", "bull"):
        row = result["scenarios"][label]
        check(f"{label} computed", row["status"] == "computed" and row["values"] is not None)
        params = case["scenarios"][label]
        mutated = lab.apply_scenario_params(case["assumptions"], params)
        independent = nav.compute_valuation(mutated)
        check(f"{label} matches valuation engine", close(row["values"]["risked_npv_pkr"], independent["values"]["risked_npv_pkr"]))
        check(f"{label} p_disc is Pg*Pc", close(row["p_disc"], params["geological_success_probability"] * params["commercial_success_probability"]))
        check(f"{label} explicit parameters retained", row["parameters"] == params)

    check("bear below base below bull on risked NPV", result["scenarios"]["bear"]["values"]["risked_npv_pkr"] < result["scenarios"]["base"]["values"]["risked_npv_pkr"] < result["scenarios"]["bull"]["values"]["risked_npv_pkr"])

    commodity = result["grids"]["commodity_vs_reserves"]
    check("commodity grid is 3x3", len(commodity["cells"]) == 3 and all(len(row) == 3 for row in commodity["cells"]))
    check("commodity axes", commodity["row_axis"]["values"] == ["low", "base", "high"] and commodity["col_axis"]["values"] == [0.85, 1.0, 1.15])
    center = commodity["cells"][1][1]
    base_nav = nav.compute_valuation({**copy.deepcopy(case["assumptions"]), "scenario": "base"})
    check("center cell is base commodity/reserves", close(center["values"]["risked_npv_pkr"], base_nav["values"]["risked_npv_pkr"]))
    check("higher commodity lifts NPV", commodity["cells"][1][2]["values"]["risked_npv_pkr"] > center["values"]["risked_npv_pkr"])
    check("higher reserves lift NPV", commodity["cells"][2][1]["values"]["risked_npv_pkr"] > center["values"]["risked_npv_pkr"])
    low_high = lab.apply_price_factor(case["assumptions"], 1.15)
    low_high["scenario"] = "low"
    check("corner cell matches engine", close(commodity["cells"][0][2]["values"]["risked_npv_pkr"], nav.compute_valuation(low_high)["values"]["risked_npv_pkr"]))

    success = result["grids"]["discount_vs_success"]
    check("success grid is 3x3", len(success["cells"]) == 3 and all(len(row) == 3 for row in success["cells"]))
    mid = success["cells"][1][1]
    check("mid success cell p_disc", close(mid["values"]["p_disc"], 0.20))
    check("higher success probability lifts NPV", success["cells"][2][1]["values"]["risked_npv_pkr"] > mid["values"]["risked_npv_pkr"])
    check("higher discount rate lowers NPV", success["cells"][1][2]["values"]["risked_npv_pkr"] < mid["values"]["risked_npv_pkr"])
    disc_case = copy.deepcopy(case["assumptions"])
    disc_case["discount_rate"] = 0.10
    disc_case["geological_success_probability"] = 0.20
    disc_case["commercial_success_probability"] = 1.0
    check("success grid uses joint P_disc", close(mid["values"]["risked_npv_pkr"], nav.compute_valuation(disc_case)["values"]["risked_npv_pkr"]))

    gap = result["expectations_gap"]
    base_values = result["scenarios"]["base"]["values"]
    expected_p_market = implied_p(base_values["unrisked_npv_pkr"], base_values["dry_hole_cost_pkr"], premium_ps, 1_000_000_000.0, 280.0)
    check("gap computed", gap["status"] == "computed")
    check("p_base is Henneth base Pg*Pc", close(gap["p_base"], 0.20))
    check("p_market reverse-solved", close(gap["p_market"], expected_p_market))
    check("delta is p_market minus p_base", close(gap["delta"], expected_p_market - 0.20))
    check("premium from latest minus undisturbed", close(gap["market_premium_pkr_per_share"], premium_ps))

    priced = copy.deepcopy(case)
    priced.pop("market")
    priced["market"] = {"market_premium_pkr_per_share": premium_ps}
    alt = lab.evaluate_lab(priced)
    check("direct premium matches price pair", close(alt["expectations_gap"]["p_market"], gap["p_market"]))

    no_market = copy.deepcopy(case)
    no_market.pop("market")
    no_market_result = lab.evaluate_lab(no_market)
    check("scenarios still computed without market", no_market_result["status"] == "computed")
    check("gap fail-closed without market", no_market_result["expectations_gap"]["status"] == lab.STATUS_MISSING and no_market_result["expectations_gap"]["p_market"] is None and no_market_result["expectations_gap"]["delta"] is None)

    blocked_truth = lab.evaluate_lab(
        {
            "financial_truth_qualified": False,
            "assumptions_approved": True,
            "assumptions": case["assumptions"],
            "scenarios": case["scenarios"],
            "grids": case["grids"],
            "market": case["market"],
        }
    )
    check("unqualified truth blocks lab", blocked_truth["status"] == lab.STATUS_TRUTH)
    check("unqualified truth has no scenarios", blocked_truth["scenarios"] is None and blocked_truth["grids"] is None and blocked_truth["expectations_gap"] is None)
    check("unqualified truth reason", "financial_truth_not_qualified" in blocked_truth["blocked_reasons"])

    blocked_unapproved = lab.evaluate_lab({**case, "assumptions_approved": False})
    check("unapproved assumptions block lab", blocked_unapproved["status"] == lab.STATUS_TRUTH and blocked_unapproved["grids"] is None)

    blocked_missing = lab.evaluate_lab(
        {
            "financial_truth_qualified": True,
            "assumptions_approved": True,
            "assumptions": {},
        }
    )
    check("missing inputs status", blocked_missing["status"] == lab.STATUS_MISSING)
    check("missing inputs have no numbers", blocked_missing["scenarios"] is None and blocked_missing["expectations_gap"] is None)

    hostile = copy.deepcopy(case)
    hostile["grids"]["commodity_vs_reserves"]["commodity_price_factors"] = [0.85, 1.0]
    check("rejects non-3x3 commodity grid", any("three factors" in item for item in lab.validate_lab_case(hostile)))
    hostile2 = copy.deepcopy(case)
    hostile2["scenarios"]["bear"]["commodity_price_factor"] = float("nan")
    check("rejects NaN scenario factor", any("commodity_price_factor" in item for item in lab.validate_lab_case(hostile2)))
    hostile3 = copy.deepcopy(case)
    hostile3["grids"]["discount_vs_success"]["success_probabilities"] = [0.1, 0.2, 1.5]
    check("rejects success probability above 1", any("success_probabilities" in item for item in lab.validate_lab_case(hostile3)))
    hostile4 = copy.deepcopy(case)
    hostile4["assumptions"]["working_interest"] = float("inf")
    check("evaluate_lab fail-closes hostile valuation input", lab.evaluate_lab(hostile4)["status"] == lab.STATUS_MISSING and lab.evaluate_lab(hostile4)["scenarios"] is None)

    out_of_range = copy.deepcopy(case)
    out_of_range["grids"]["commodity_vs_reserves"]["commodity_price_factors"] = [1.0, 1.0, 8.0]
    check("factor 8 rejected at contract", any("commodity_price_factors" in item for item in lab.validate_lab_case(out_of_range)))

    repeat = lab.evaluate_lab(case)
    check("deterministic evaluate", json.dumps(repeat, sort_keys=True) == json.dumps(result, sort_keys=True))
    check("no NaN in computed lab", all(not isinstance(item, float) or math.isfinite(item) for _, item in walk(result)))

    retained = lab.build(write=True)
    artifact = json.loads(lab.OUT.read_text(encoding="utf-8"))
    check("retained fail-closed", retained["status"] == lab.STATUS_TRUTH)
    check("retained artifact matches", artifact["status"] == retained["status"] and artifact["scenarios"] is None and artifact["grids"] is None and artifact["expectations_gap"] is None)
    check("retained identity", retained["symbol"] == "MARI" and retained["case_id"] == lab.CASE_ID)
    check("repeat retained identical", json.dumps(lab.build(write=False), sort_keys=True) == json.dumps(retained, sort_keys=True))
    for _, item in walk(retained):
        if isinstance(item, str):
            lowered = item.lower()
            check("no advice language", not any(phrase in lowered for phrase in BANNED))

    print(f"{PASSED} checks passed")


if __name__ == "__main__":
    main()
