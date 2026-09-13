"""Focused deterministic checks for the PSO Case C OMC adapter."""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pso_sales_expansion_model as model

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-5)


def qualified_truth() -> dict:
    return {"status": "qualified", "financial_tie_out": {"status": "qualified"},
            "model_ready_financial_statement_coverage": {
                "annual": {"required": 5, "present": 5},
                "reported_quarter": {"required": 8, "present": 8}}, "evidence_gaps": []}


def main() -> None:
    case = model.default_case()
    check("archetype", model.MODEL_ARCHETYPE == "omc_distribution_network_expansion_v1")
    check("valid fixture", model.validate_case(case) == [],
          repr(model.validate_case(case)))

    result = model.evaluate_case(case)
    rows = result["quarterly_schedule"]
    check("eight quarters", len(rows) == 8)
    check("gross-net reconciliation", rows[0]["network"]["gross_outlets_opened"] == 107
          and rows[0]["network"]["closures_or_reclassifications"] == 38
          and rows[0]["network"]["net_active_change"] == 69
          and rows[0]["network"]["closing_active_outlets"] == 3649)
    check("identity", result["accounting_integrity"]["balanced"]
          and result["accounting_integrity"]["max_absolute_gap_pkr"] <= 1e-6)
    check("identity each quarter", all(abs(row["balance_sheet_delta_gap_pkr"]) <= 1e-6 for row in rows))
    check("distinct channels", {"fuel_channel", "nonfuel_channel", "lpg_channel"}.issubset(rows[0]))
    check("vibe not double counted", rows[0]["nonfuel_channel"]["vibe_subset_of_convenience"] is True
          and rows[0]["nonfuel_channel"]["incremental_nonfuel_revenue"] >= 0)
    check("income schedule", all(all(key in row for key in ("revenue_pkr", "gross_profit_pkr", "sga_pkr", "ebitda_pkr", "depreciation_pkr", "finance_cost_pkr", "pbt_pkr", "tax_pkr", "pat_pkr", "eps_pkr")) for row in rows))
    check("cash schedule", all(all(key in row for key in ("operating_cash_flow_pkr", "capex_pkr", "fcf_pkr")) for row in rows))
    check("valuation", result["valuation"]["project_dcf_npv_pkr"] == result["valuation"]["project_dcf_npv_pkr"]
          and result["valuation"]["fair_value_impact_per_share_pkr"] == result["valuation"]["fair_value_impact_pkr"] / model._value(case["inputs"], "shares_outstanding"))

    # Bear/base/bull scenarios are independent runs: changing one case does not mutate another.
    bear = copy.deepcopy(case); bear["case_label"] = "bear"; bear["inputs"]["gross_openings_schedule"]["value"][0] = 50
    bull = copy.deepcopy(case); bull["case_label"] = "bull"; bull["inputs"]["gross_openings_schedule"]["value"][0] = 150
    base_again = model.evaluate_case(case)
    bear_result = model.evaluate_case(bear)
    bull_result = model.evaluate_case(bull)
    check("scenario isolation labels", {base_again["scenario"], bear_result["scenario"], bull_result["scenario"]} == {"base", "bear", "bull"})
    check("scenario isolation values", bear_result["quarterly_schedule"][0]["network"]["gross_outlets_opened"] < base_again["quarterly_schedule"][0]["network"]["gross_outlets_opened"] < bull_result["quarterly_schedule"][0]["network"]["gross_outlets_opened"])
    check("scenario isolation mutation", case["inputs"]["gross_openings_schedule"]["value"][0] == 107)

    blocked = model.evaluate_with_financial_truth_gate(model._real_identity(), {"status": "not_qualified"})
    check("fail closed status", blocked["status"].startswith("blocked_financial_truth_not_qualified"))
    check("fail closed no numbers", blocked["quarterly_schedule"] == [] and blocked["valuation"] is None and blocked["market_expectations_backsolve"] is None)

    expectations = result["market_expectations_backsolve"]
    check("expectation backsolve", set(expectations) == {"implied_by_openings", "implied_by_throughput_productivity"}
          and all("implied_scale" in value and "reachable" in value for value in expectations.values()))
    check("break-even separation", set(result["break_even"]) == {"ebitda_break_even_quarter", "cash_payback_quarter"})
    check("determinism", json.dumps(result, sort_keys=True) == json.dumps(model.evaluate_case(copy.deepcopy(case)), sort_keys=True))
    print(f"pso sales expansion model: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
