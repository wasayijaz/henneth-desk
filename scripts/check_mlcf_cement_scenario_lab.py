"""Focused deterministic checks for the MLCF cement scenario lab and market
expectations gap engine (Case B, Sections 12 & 14).

Covers: bear/base/bull scenario ordering, the two 3x3 sensitivity grids
(structure and monotonicity), the market-expectations-gap arithmetic
(independently recomputed against the expansion model's own backsolve),
fail-closed blocking when financial truth is not qualified, and input
validation.
"""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mlcf_cement_scenario_lab as lab
import mlcf_cement_expansion_model as expansion_model

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=tol)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def analyst(value, note="explicit mlcf cement scenario-lab fixture assumption"):
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "note:mlcf-cement-scenario-lab:golden", "note": note},
        "available_on": "2025-12-31",
    }


def source(value):
    return {
        "value": value,
        "label_type": "source",
        "source_ref": {
            "id": "source:mlcf-cement-scenario-lab:fixture",
            "label": "Retained MLCF cement scenario-lab fixture evidence",
            "url": "https://example.invalid/mlcf-cement-scenario-lab",
        },
        "available_on": "2025-12-31",
    }


CONSTRUCTION_ENDS = ["2025-12-31", "2026-03-31"]
OPERATING_ENDS = [
    "2026-06-30", "2026-09-30", "2026-12-31", "2027-03-31",
    "2027-06-30", "2027-09-30", "2027-12-31", "2028-03-31",
]
BASE_RAMP = [30.0, 45.0, 60.0, 70.0, 80.0, 85.0, 90.0, 90.0]
MARKET_PRICE = 55.0
PRE_EXPANSION_VALUE = 48.0
HENNETH_BASE_UTILIZATION = 67.0
HISTORICAL_MEDIAN_UTILIZATION = 62.0


def base_case_inputs() -> dict:
    return {
        "commissioning_date_quarter": analyst(OPERATING_ENDS[0]),
        "construction_quarter_ends": analyst(list(CONSTRUCTION_ENDS)),
        "operating_quarter_ends": analyst(list(OPERATING_ENDS)),
        "annual_capacity_tons": analyst(2_000_000.0),
        "capex_spending_schedule_pct": analyst([60.0, 40.0]),
        "expansion_capex_total_pkr": analyst(20_000_000_000.0),
        "debt_financing_pct": analyst(60.0),
        "annual_interest_rate_pct": analyst(14.0),
        "repayment_quarters": analyst([5, 6, 7, 8]),
        "depreciation_method": analyst("straight_line_useful_life"),
        "useful_life_years": analyst(20.0),
        "ramp_pct_schedule": analyst(list(BASE_RAMP)),
        "selling_price_pkr_per_ton_schedule": analyst([18_000.0] * 8),
        "fuel_cost_pkr_per_ton_schedule": analyst([6_000.0] * 8),
        "power_cost_pkr_per_ton_schedule": analyst([2_500.0] * 8),
        "raw_materials_cost_pkr_per_ton_schedule": analyst([1_500.0] * 8),
        "fixed_operating_cost_pkr_quarterly_schedule": analyst([500_000_000.0] * 8),
        "working_capital_pct_revenue": analyst(8.0),
        "tax_rate_pct": analyst(29.0),
        "shares_outstanding": analyst(1_047_562_608.0),
        "valuation_discount_rate_pct_annual": analyst(16.0),
        "exit_ev_ebitda_multiple": analyst(7.0),
        "current_market_price_pkr_per_share": analyst(MARKET_PRICE),
        "pre_expansion_fair_value_pkr_per_share": analyst(PRE_EXPANSION_VALUE),
    }


BEAR_MULTIPLIERS = {
    "ramp_scale_pct": analyst(85.0),
    "price_scale_pct": analyst(95.0),
    "fuel_cost_scale_pct": analyst(115.0),
    "power_cost_scale_pct": analyst(110.0),
    "raw_materials_cost_scale_pct": analyst(110.0),
    "wacc_delta_pct_points": analyst(2.0),
}
BULL_MULTIPLIERS = {
    "ramp_scale_pct": analyst(115.0),
    "price_scale_pct": analyst(105.0),
    "fuel_cost_scale_pct": analyst(90.0),
    "power_cost_scale_pct": analyst(92.0),
    "raw_materials_cost_scale_pct": analyst(92.0),
    "wacc_delta_pct_points": analyst(-1.5),
}
GRID_CONFIG = {
    "price_axis_step_pct": analyst(10.0),
    "coal_cost_axis_step_pct": analyst(15.0),
    "ramp_axis_step_pct": analyst(12.0),
    "wacc_axis_step_pct_points": analyst(2.0),
}
GAP_INPUTS = {
    "henneth_base_case_utilization_pct": analyst(HENNETH_BASE_UTILIZATION),
    "historical_comparable_median_utilization_pct": analyst(HISTORICAL_MEDIAN_UTILIZATION),
}


def golden_case() -> dict:
    return {
        "symbol": "CEMEXP",
        "project_name": "Fixture Line Expansion",
        "event_ref": "fixture:mlcf-cement-lab:v1",
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
        "base_case_inputs": base_case_inputs(),
        "scenario_multipliers": {
            "bear": copy.deepcopy(BEAR_MULTIPLIERS),
            "bull": copy.deepcopy(BULL_MULTIPLIERS),
        },
        "sensitivity_grid_config": copy.deepcopy(GRID_CONFIG),
        "expectations_gap_inputs": copy.deepcopy(GAP_INPUTS),
    }


def expect_reject(name, candidate, expected):
    violations = lab.validate_case(candidate)
    check(f"boundary {name}", any(expected in violation for violation in violations), repr(violations))


def qualified_truth_row() -> dict:
    schedule = {
        "required": 5, "present": 5,
        "direct_flow_statement_periods": [], "direct_balance_sheet_periods": [],
        "derived_ebitda_periods": [], "derived_free_cash_flow_periods": [],
    }
    quarter_schedule = dict(schedule, required=8, present=8)
    return {
        "status": "qualified",
        "financial_tie_out": {"status": "qualified"},
        "model_ready_financial_statement_coverage": {
            "annual": schedule, "reported_quarter": quarter_schedule,
        },
        "evidence_gaps": [],
    }


def not_qualified_truth_row() -> dict:
    return {"status": "not_qualified"}


def test_scenario_ordering() -> None:
    case = golden_case()
    result = lab.evaluate_case(case)
    summaries = result["scenario_lab"]["summaries"]
    bear, base, bull = (summaries[label]["fair_value_impact_per_share_pkr"] for label in ("bear", "base", "bull"))
    check("bear < base", bear < base)
    check("base < bull", base < bull)
    check("ordering check flags true", result["scenario_lab"]["ordering_check"] == {"bear_le_base": True, "base_le_bull": True})

    # base scenario must exactly match a direct expansion_model.evaluate_case
    # call on the unmodified base_case_inputs (no drift introduced by the lab).
    direct_base_case = {
        "symbol": case["symbol"], "project_name": case["project_name"],
        "event_ref": f"{case['event_ref']}:base", "case_label": "base",
        "effective_date": case["effective_date"], "valuation_date": case["valuation_date"],
        "inputs": case["base_case_inputs"],
    }
    direct_result = expansion_model.evaluate_case(direct_base_case)
    check("base scenario matches direct expansion-model call",
          close(summaries["base"]["fair_value_impact_per_share_pkr"],
                direct_result["valuation"]["fair_value_impact_per_share_pkr"]))

    # bear must have a lower average utilization and higher effective WACC
    # than bull (the multipliers we fixed above are directionally bearish).
    bear_avg_util = summaries["bear"]["average_operating_utilization_pct"]
    bull_avg_util = summaries["bull"]["average_operating_utilization_pct"]
    check("bear utilization below bull", bear_avg_util < bull_avg_util)
    for label in ("bear", "base", "bull"):
        check(f"{label} accounting integrity balanced", summaries[label]["accounting_integrity_balanced"])


def test_sensitivity_grids() -> None:
    case = golden_case()
    result = lab.evaluate_case(case)
    grid1 = result["sensitivity_grids"]["selling_price_vs_variable_cost"]
    grid2 = result["sensitivity_grids"]["utilization_ramp_vs_wacc"]

    check("grid1 id", grid1["grid_id"] == "selling_price_vs_variable_cost")
    check("grid1 shape", len(grid1["fair_value_impact_per_share_pkr"]) == 3
          and all(len(row) == 3 for row in grid1["fair_value_impact_per_share_pkr"]))
    check("grid1 row axis values", grid1["row_axis"]["values"] == [90.0, 100.0, 110.0])
    check("grid1 column axis values", grid1["column_axis"]["values"] == [85.0, 100.0, 115.0])
    cells1 = grid1["fair_value_impact_per_share_pkr"]
    check("grid1 monotonic increasing by price (rows)",
          all(cells1[0][c] < cells1[1][c] < cells1[2][c] for c in range(3)))
    check("grid1 monotonic decreasing by variable cost (columns)",
          all(cells1[r][0] > cells1[r][1] > cells1[r][2] for r in range(3)))
    check("grid1 centre cell equals base fair value",
          close(cells1[1][1], result["scenario_lab"]["summaries"]["base"]["fair_value_impact_per_share_pkr"]))

    check("grid2 id", grid2["grid_id"] == "utilization_ramp_vs_wacc")
    check("grid2 row axis values", grid2["row_axis"]["values"] == [88.0, 100.0, 112.0])
    check("grid2 column axis values", grid2["column_axis"]["values"] == [-2.0, 0.0, 2.0])
    cells2 = grid2["fair_value_impact_per_share_pkr"]
    check("grid2 monotonic increasing by ramp (rows)",
          all(cells2[0][c] < cells2[1][c] < cells2[2][c] for c in range(3)))
    check("grid2 monotonic decreasing by wacc (columns)",
          all(cells2[r][0] > cells2[r][1] > cells2[r][2] for r in range(3)))
    check("grid2 centre cell equals base fair value",
          close(cells2[1][1], result["scenario_lab"]["summaries"]["base"]["fair_value_impact_per_share_pkr"]))

    # Independently recompute one off-centre grid1 cell via a direct
    # expansion_model call, duplicating none of the lab's own transform code.
    scaled_inputs = copy.deepcopy(case["base_case_inputs"])
    scaled_inputs["selling_price_pkr_per_ton_schedule"]["value"] = [
        v * 0.9 for v in scaled_inputs["selling_price_pkr_per_ton_schedule"]["value"]
    ]
    scaled_inputs["fuel_cost_pkr_per_ton_schedule"]["value"] = [
        v * 0.85 for v in scaled_inputs["fuel_cost_pkr_per_ton_schedule"]["value"]
    ]
    scaled_inputs["power_cost_pkr_per_ton_schedule"]["value"] = [
        v * 0.85 for v in scaled_inputs["power_cost_pkr_per_ton_schedule"]["value"]
    ]
    scaled_inputs["raw_materials_cost_pkr_per_ton_schedule"]["value"] = [
        v * 0.85 for v in scaled_inputs["raw_materials_cost_pkr_per_ton_schedule"]["value"]
    ]
    direct_case = {
        "symbol": case["symbol"], "project_name": case["project_name"],
        "event_ref": "recompute", "case_label": "base",
        "effective_date": case["effective_date"], "valuation_date": case["valuation_date"],
        "inputs": scaled_inputs,
    }
    direct_result = expansion_model.evaluate_case(direct_case)
    check("grid1 top-left cell matches independent recomputation",
          close(cells1[0][0], direct_result["valuation"]["fair_value_impact_per_share_pkr"]))


def test_market_expectations_gap() -> None:
    case = golden_case()
    gap = lab.compute_market_expectations_gap(case)
    check("gap target value", close(gap["market_implied_incremental_value_per_share_pkr"], MARKET_PRICE - PRE_EXPANSION_VALUE))
    check("gap reachable", gap["utilization_backsolve_reachable"])
    check("gap henneth reference", close(gap["henneth_base_case_utilization_pct"], HENNETH_BASE_UTILIZATION))
    check("gap historical reference", close(gap["historical_comparable_median_utilization_pct"], HISTORICAL_MEDIAN_UTILIZATION))

    # Independently recompute the implied average utilization from the
    # engine's own backsolve + operating_schedule, duplicating none of the
    # lab's arithmetic other than the averaging itself.
    base_case = {
        "symbol": case["symbol"], "project_name": case["project_name"],
        "event_ref": "recompute-gap", "case_label": "base",
        "effective_date": case["effective_date"], "valuation_date": case["valuation_date"],
        "inputs": case["base_case_inputs"],
    }
    construction_rows = expansion_model.construction_schedule(base_case)
    backsolve = expansion_model.backsolve_utilization_scale(base_case)
    scale = backsolve["implied_utilization_scale_pct"] / 100.0
    operating_rows = expansion_model.operating_schedule(base_case, construction_rows, utilization_scale=scale)
    expected_avg = sum(row["utilization_pct"] for row in operating_rows) / len(operating_rows)
    check("gap market-implied utilization matches independent recomputation",
          close(gap["market_implied_utilization_pct"], expected_avg))

    check("gap vs henneth arithmetic", close(gap["gap_vs_henneth_base_case_pct_points"], expected_avg - HENNETH_BASE_UTILIZATION))
    check("gap vs historical arithmetic", close(gap["gap_vs_historical_comparable_median_pct_points"], expected_avg - HISTORICAL_MEDIAN_UTILIZATION))
    expected_interpretation = "market_implied_less_optimistic" if expected_avg < HENNETH_BASE_UTILIZATION - 0.5 else (
        "market_implied_more_optimistic" if expected_avg > HENNETH_BASE_UTILIZATION + 0.5 else "market_implied_in_line"
    )
    check("gap interpretation vs henneth", gap["interpretation"]["vs_henneth_base_case"] == expected_interpretation)

    delay = expansion_model.backsolve_commissioning_delay_quarters(base_case)
    check("gap delay matches independent backsolve", gap["market_implied_commissioning_delay_quarters"] == delay["implied_commissioning_delay_quarters"])
    check("gap delay absolute gap matches", close(gap["commissioning_delay_absolute_gap_pkr"], delay["absolute_gap_pkr"]))

    # Boundary: exactly at the tolerance must be in_line, not optimistic/pessimistic.
    check("interpretation boundary exact zero", lab._interpretation(0.0) == "market_implied_in_line")
    check("interpretation boundary at tolerance", lab._interpretation(0.5) == "market_implied_in_line")
    check("interpretation boundary just above tolerance", lab._interpretation(0.500001) == "market_implied_more_optimistic")
    check("interpretation boundary just below negative tolerance", lab._interpretation(-0.500001) == "market_implied_less_optimistic")

    # Non-monotonic (unreachable) backsolve must propagate as None, not a
    # spurious number.
    broken = golden_case()
    for index in range(8):
        broken["base_case_inputs"]["fuel_cost_pkr_per_ton_schedule"]["value"][index] = 1_000_000.0
    broken_gap = lab.compute_market_expectations_gap(broken)
    check("unreachable gap withholds utilization", broken_gap["market_implied_utilization_pct"] is None)
    check("unreachable gap withholds deltas", broken_gap["gap_vs_henneth_base_case_pct_points"] is None
          and broken_gap["gap_vs_historical_comparable_median_pct_points"] is None)
    check("unreachable gap interpretation", broken_gap["interpretation"]["vs_henneth_base_case"] == "not_reachable"
          and broken_gap["interpretation"]["vs_historical_comparable_median"] == "not_reachable")


def test_fail_closed_financial_truth_gate() -> None:
    case = golden_case()

    blocked = lab.evaluate_with_financial_truth_gate(case, not_qualified_truth_row())
    check("not-qualified blocks", blocked["status"] == "blocked_financial_truth_not_qualified")
    check("not-qualified reason recorded", blocked["blocked_reasons"] == ["financial_truth_status:not_qualified"])
    check("not-qualified withholds scenario lab", blocked["scenario_lab"] is None)
    check("not-qualified withholds sensitivity grids", blocked["sensitivity_grids"] is None)
    check("not-qualified withholds expectations gap", blocked["market_expectations_gap"] is None)

    missing = lab.evaluate_with_financial_truth_gate(case, {})
    check("missing truth row blocks", missing["status"] == "blocked_financial_truth_not_qualified"
          and missing["blocked_reasons"] == ["financial_truth_status:missing"])

    computed = lab.evaluate_with_financial_truth_gate(case, qualified_truth_row())
    check("qualified computes", computed["status"] == "computed")
    check("qualified matches pure kernel",
          json.dumps(computed, sort_keys=True) == json.dumps(lab.evaluate_case(case), sort_keys=True))

    invalid_case = golden_case()
    invalid_case["base_case_inputs"].pop("useful_life_years")
    invalid_blocked = lab.evaluate_with_financial_truth_gate(invalid_case, qualified_truth_row())
    check("qualified but invalid case blocks on inputs", invalid_blocked["status"] == "blocked_invalid_inputs")
    check("invalid input reason present",
          any("useful_life_years" in reason for reason in invalid_blocked["blocked_reasons"]))


def test_real_build_blocks_against_current_state() -> None:
    # The real MLCF financial_truth_qualification.json row is not_qualified
    # today; the real build must fail closed and never leak numbers, and must
    # not fabricate scenario or sensitivity inputs.
    result = lab.build(write=False)
    check("real build blocks", result["status"] == "blocked_financial_truth_not_qualified")
    check("real build no numbers", result["scenario_lab"] is None and result["sensitivity_grids"] is None)
    check("real build identity", result["project"]["symbol"] == lab.REAL_SYMBOL
          and result["project"]["project_name"] == lab.REAL_PROJECT_NAME)

    written = lab.build(write=True)
    on_disk = json.loads(lab.OUTPUT_PATH.read_text(encoding="utf-8"))
    check("generated state file matches build output", on_disk == written)
    check("generated state file path", lab.OUTPUT_PATH.name == "mlcf_cement_scenario_lab.json"
          and lab.OUTPUT_PATH.parent.name == "company_intel")


def test_input_validation() -> None:
    case = golden_case()
    check("module version", lab.MODULE_VERSION == "mlcf_cement_scenario_lab_v1")
    check("formula id", lab.FORMULA_ID == "mlcf_cement_scenario_lab.scenario_sensitivity_and_expectations_gap.v1")
    check("result schema", lab.RESULT_SCHEMA == "mlcf_cement_scenario_lab_result_v1")
    check("golden validates", lab.validate_case(case) == [])

    mutations = [
        ("missing base_case_inputs field",
         lambda c: c["base_case_inputs"].pop("useful_life_years"),
         "base_case_inputs.useful_life_years: missing required input"),
        ("base_case_inputs invalid schedule length",
         lambda c: c["base_case_inputs"]["ramp_pct_schedule"].update(value=[10.0] * 7),
         "base_case_inputs.ramp_pct_schedule: must be a list of exactly 8 values"),
        ("missing scenario_multipliers block",
         lambda c: c["scenario_multipliers"].pop("bear"),
         "scenario_multipliers.bear: must be a mapping"),
        ("missing scenario multiplier field",
         lambda c: c["scenario_multipliers"]["bear"].pop("ramp_scale_pct"),
         "scenario_multipliers.bear.ramp_scale_pct: missing required multiplier"),
        ("unknown scenario multiplier field",
         lambda c: c["scenario_multipliers"]["bull"].update(extra=analyst(1.0)),
         "scenario_multipliers.bull.extra: unknown multiplier field"),
        ("scenario multiplier zero rejected",
         lambda c: c["scenario_multipliers"]["bear"]["ramp_scale_pct"].update(value=0.0),
         "scenario_multipliers.bear.ramp_scale_pct: must be in (0, 300]"),
        ("scenario multiplier out of bounds",
         lambda c: c["scenario_multipliers"]["bull"]["price_scale_pct"].update(value=301.0),
         "scenario_multipliers.bull.price_scale_pct: must be in (0, 300]"),
        ("wacc delta out of bounds",
         lambda c: c["scenario_multipliers"]["bear"]["wacc_delta_pct_points"].update(value=25.0),
         "scenario_multipliers.bear.wacc_delta_pct_points: must be in [-20, 20]"),
        ("scenario multiplier nan",
         lambda c: c["scenario_multipliers"]["bear"]["ramp_scale_pct"].update(value=float("nan")),
         "scenario_multipliers.bear.ramp_scale_pct: must be a finite number"),
        ("scenario multiplier bool",
         lambda c: c["scenario_multipliers"]["bear"]["ramp_scale_pct"].update(value=True),
         "scenario_multipliers.bear.ramp_scale_pct: must be a finite number"),
        ("missing grid config field",
         lambda c: c["sensitivity_grid_config"].pop("price_axis_step_pct"),
         "sensitivity_grid_config.price_axis_step_pct: missing required grid-config input"),
        ("unknown grid config field",
         lambda c: c["sensitivity_grid_config"].update(extra=analyst(1.0)),
         "sensitivity_grid_config.extra: unknown grid-config field"),
        ("grid step zero rejected",
         lambda c: c["sensitivity_grid_config"]["ramp_axis_step_pct"].update(value=0.0),
         "sensitivity_grid_config.ramp_axis_step_pct: must be in (0, 100]"),
        ("wacc axis step out of bounds",
         lambda c: c["sensitivity_grid_config"]["wacc_axis_step_pct_points"].update(value=21.0),
         "sensitivity_grid_config.wacc_axis_step_pct_points: must be in (0, 20]"),
        ("missing gap input field",
         lambda c: c["expectations_gap_inputs"].pop("henneth_base_case_utilization_pct"),
         "expectations_gap_inputs.henneth_base_case_utilization_pct: missing required expectations-gap input"),
        ("gap input out of bounds",
         lambda c: c["expectations_gap_inputs"]["historical_comparable_median_utilization_pct"].update(value=101.0),
         "expectations_gap_inputs.historical_comparable_median_utilization_pct: must be in [0, 100]"),
        ("unknown gap field",
         lambda c: c["expectations_gap_inputs"].update(extra=analyst(1.0)),
         "expectations_gap_inputs.extra: unknown expectations-gap field"),
        ("lookahead on multiplier",
         lambda c: c["scenario_multipliers"]["bear"]["ramp_scale_pct"].update(available_on="2026-01-01"),
         "scenario_multipliers.bear.ramp_scale_pct: available_on must be on or before valuation_date"),
        ("bad label on grid config",
         lambda c: c["sensitivity_grid_config"]["price_axis_step_pct"].update(label_type="bad"),
         "sensitivity_grid_config.price_axis_step_pct: provenance record must carry"),
        ("missing project name", lambda c: c.update(project_name=""), "project_name: must be a non-empty string"),
        ("effective after valuation",
         lambda c: c.update(effective_date="2026-01-01"),
         "effective_date: must be on or before valuation_date"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        expect_reject(name, candidate, expected)

    try:
        lab.evaluate_case({"symbol": "CEMEXP"})
    except ValueError as error:
        check("evaluate raises named violations", "; " in str(error) and "project_name" in str(error))
    else:
        raise AssertionError("evaluate should reject invalid case")

    with_source = golden_case()
    with_source["sensitivity_grid_config"]["price_axis_step_pct"] = source(10.0)
    check("source-labelled grid config accepted", lab.validate_case(with_source) == [])


def test_envelope_shape_and_no_advice() -> None:
    case = golden_case()
    result = lab.evaluate_case(case)
    expected_keys = {
        "schema_version", "formula_id", "module_version", "run_receipt", "status",
        "blocked_reasons", "project", "scenario_lab", "sensitivity_grids",
        "market_expectations_gap", "confidence_limitations",
    }
    check("envelope shape", set(result) == expected_keys)
    check("computed status", result["status"] == "computed" and result["blocked_reasons"] == [])

    repeat = lab.evaluate_case(case)
    copied = lab.evaluate_case(copy.deepcopy(case))
    dump = json.dumps(result, sort_keys=True)
    check("same object deterministic", json.dumps(repeat, sort_keys=True) == dump)
    check("deepcopy deterministic", json.dumps(copied, sort_keys=True) == dump)

    blocked = lab.blocked_result(golden_case(), ["zeta", "alpha", "alpha"])
    check("blocked envelope reasons sorted and deduped", blocked["blocked_reasons"] == ["alpha", "zeta"])

    for label, payload in (("computed", result), ("blocked", blocked)):
        text_payload = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text_payload) is None)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))


def main() -> None:
    test_scenario_ordering()
    test_sensitivity_grids()
    test_market_expectations_gap()
    test_fail_closed_financial_truth_gate()
    test_real_build_blocks_against_current_state()
    test_input_validation()
    test_envelope_shape_and_no_advice()
    print(f"mlcf cement scenario lab: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
