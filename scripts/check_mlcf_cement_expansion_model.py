"""Focused deterministic checks for the MLCF cement capacity-expansion model
and valuation engine (Case B: Industrial / Cement Expansion).

Covers: accounting integrity (income statement -> cash flow -> balance sheet
link), ramp mathematics, debt-schedule roll-forward, break-even utilization
backsolve, price-implied expectation backsolve, fail-closed blocking when
financial truth is not qualified, and input validation.
"""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mlcf_cement_expansion_model as model

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


def analyst(value, note="explicit mlcf cement expansion fixture assumption"):
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "note:mlcf-cement-expansion:golden", "note": note},
        "available_on": "2025-12-31",
    }


def source(value):
    return {
        "value": value,
        "label_type": "source",
        "source_ref": {
            "id": "source:mlcf-cement-expansion:fixture",
            "label": "Retained MLCF cement expansion fixture evidence",
            "url": "https://example.invalid/mlcf-cement-expansion",
        },
        "available_on": "2025-12-31",
    }


CONSTRUCTION_ENDS = ["2025-12-31", "2026-03-31"]
OPERATING_ENDS = [
    "2026-06-30", "2026-09-30", "2026-12-31", "2027-03-31",
    "2027-06-30", "2027-09-30", "2027-12-31", "2028-03-31",
]
ANNUAL_CAPACITY_TONS = 2_000_000.0
CAPEX_TOTAL = 20_000_000_000.0
CAPEX_PCT = [60.0, 40.0]
DEBT_PCT = 60.0
INTEREST_PCT = 14.0
REPAYMENT_QUARTERS = [5, 6, 7, 8]
USEFUL_LIFE_YEARS = 20.0
RAMP = [30.0, 45.0, 60.0, 70.0, 80.0, 85.0, 90.0, 90.0]
PRICE = [18_000.0] * 8
FUEL = [6_000.0] * 8
POWER = [2_500.0] * 8
RAW_MAT = [1_500.0] * 8
FIXED_COST = [500_000_000.0] * 8
WORKING_CAPITAL_PCT = 8.0
TAX_PCT = 29.0
SHARES = 1_047_562_608.0
WACC_PCT = 16.0
EXIT_MULTIPLE = 7.0
MARKET_PRICE = 55.0
PRE_EXPANSION_VALUE = 48.0


def golden_case() -> dict:
    return {
        "symbol": "CEMEXP",
        "project_name": "Fixture Line Expansion",
        "event_ref": "fixture:mlcf-cement-expansion:v1",
        "case_label": "base",
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
        "inputs": {
            "commissioning_date_quarter": analyst(OPERATING_ENDS[0]),
            "construction_quarter_ends": analyst(list(CONSTRUCTION_ENDS)),
            "operating_quarter_ends": analyst(list(OPERATING_ENDS)),
            "annual_capacity_tons": analyst(ANNUAL_CAPACITY_TONS),
            "capex_spending_schedule_pct": analyst(list(CAPEX_PCT)),
            "expansion_capex_total_pkr": analyst(CAPEX_TOTAL),
            "debt_financing_pct": analyst(DEBT_PCT),
            "annual_interest_rate_pct": analyst(INTEREST_PCT),
            "repayment_quarters": analyst(list(REPAYMENT_QUARTERS)),
            "depreciation_method": analyst("straight_line_useful_life"),
            "useful_life_years": analyst(USEFUL_LIFE_YEARS),
            "ramp_pct_schedule": analyst(list(RAMP)),
            "selling_price_pkr_per_ton_schedule": analyst(list(PRICE)),
            "fuel_cost_pkr_per_ton_schedule": analyst(list(FUEL)),
            "power_cost_pkr_per_ton_schedule": analyst(list(POWER)),
            "raw_materials_cost_pkr_per_ton_schedule": analyst(list(RAW_MAT)),
            "fixed_operating_cost_pkr_quarterly_schedule": analyst(list(FIXED_COST)),
            "working_capital_pct_revenue": analyst(WORKING_CAPITAL_PCT),
            "tax_rate_pct": analyst(TAX_PCT),
            "shares_outstanding": analyst(SHARES),
            "valuation_discount_rate_pct_annual": analyst(WACC_PCT),
            "exit_ev_ebitda_multiple": analyst(EXIT_MULTIPLE),
            "current_market_price_pkr_per_share": analyst(MARKET_PRICE),
            "pre_expansion_fair_value_pkr_per_share": analyst(PRE_EXPANSION_VALUE),
        },
    }


def expect_reject(name, candidate, expected):
    violations = model.validate_case(candidate)
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


def test_ramp_mathematics() -> None:
    case = golden_case()
    construction_rows = model.construction_schedule(case)
    operating_rows = model.operating_schedule(case, construction_rows)
    capacity_per_quarter = ANNUAL_CAPACITY_TONS / 4.0
    for index, row in enumerate(operating_rows):
        expected_volume = capacity_per_quarter * RAMP[index] / 100.0
        check(f"ramp volume q{index+1}", close(row["volume_tons"], expected_volume))
        check(f"ramp utilization q{index+1}", close(row["utilization_pct"], RAMP[index]))
    scaled = model.operating_schedule(case, construction_rows, utilization_scale=2.0)
    for index, row in enumerate(scaled):
        expected_pct = min(RAMP[index] * 2.0, 100.0)
        check(f"ramp scale caps at 100 q{index+1}", close(row["utilization_pct"], expected_pct))
        check(f"ramp scale volume q{index+1}",
              close(row["volume_tons"], capacity_per_quarter * expected_pct / 100.0))
    zero = model.operating_schedule(case, construction_rows, utilization_scale=0.0)
    check("zero utilization gives zero volume", all(close(row["volume_tons"], 0.0) for row in zero))
    check("zero utilization gives zero revenue", all(close(row["revenue_pkr"], 0.0) for row in zero))


def test_debt_schedule_roll_forward() -> None:
    case = golden_case()
    construction_rows = model.construction_schedule(case)
    operating_rows = model.operating_schedule(case, construction_rows)

    debt_open = 0.0
    quarterly_interest = INTEREST_PCT / 100.0 / 4.0
    for index, row in enumerate(construction_rows):
        capex = CAPEX_TOTAL * CAPEX_PCT[index] / 100.0
        expected_draw = capex * DEBT_PCT / 100.0
        expected_capitalized_interest = debt_open * quarterly_interest
        expected_close = debt_open + expected_draw + expected_capitalized_interest
        check(f"construction debt open c{index+1}", close(row["debt_open_pkr"], debt_open))
        check(f"construction debt draw c{index+1}", close(row["debt_draw_pkr"], expected_draw))
        check(f"construction capitalized interest c{index+1}",
              close(row["capitalized_interest_pkr"], expected_capitalized_interest))
        check(f"construction debt close c{index+1}", close(row["debt_close_pkr"], expected_close))
        debt_open = expected_close

    installment = debt_open / len(REPAYMENT_QUARTERS)
    for index, row in enumerate(operating_rows):
        quarter_number = index + 1
        check(f"operating debt open o{quarter_number}", close(row["debt_open_pkr"], debt_open))
        expected_repay = installment if quarter_number in REPAYMENT_QUARTERS else 0.0
        check(f"operating debt repayment o{quarter_number}", close(row["debt_repayment_pkr"], expected_repay))
        expected_close = debt_open - expected_repay
        check(f"operating debt close o{quarter_number}", close(row["debt_close_pkr"], expected_close))
        expected_interest = debt_open * quarterly_interest
        check(f"operating finance cost o{quarter_number}", close(row["finance_cost_pkr"], expected_interest))
        debt_open = expected_close
    check("debt fully amortized at horizon end", close(debt_open, 0.0, tol=1e-3))


def test_accounting_integrity_link() -> None:
    case = golden_case()
    result = model.evaluate_case(case)
    check("accounting integrity balanced", result["accounting_integrity"]["balanced"])
    check("accounting integrity zero gap", close(result["accounting_integrity"]["max_absolute_gap_pkr"], 0.0, tol=1e-4))

    # Independently recompute assets == liabilities + equity for every quarter,
    # duplicating none of the engine's own arithmetic (only the identity).
    all_rows = result["construction_schedule"] + result["operating_schedule"]
    for row in all_rows:
        assets = row["cash_close_pkr"] + row["net_working_capital_pkr"] + row["ppe_close_pkr"]
        claims = row["debt_close_pkr"] + row["equity_close_pkr"]
        check(f"balance sheet ties at {row['phase']} q{row['quarter_index']}", close(assets, claims, tol=1e-3))

    # Cash flow -> balance sheet: cash roll-forward must equal operating income
    # statement outputs feeding into the cash-flow lines.
    for row in result["operating_schedule"]:
        recomputed_operating_cf = row["profit_after_tax_pkr"] + row["depreciation_pkr"] - row["delta_net_working_capital_pkr"]
        check(f"operating CF derives from IS q{row['quarter_index']}",
              close(row["operating_cash_flow_pkr"], recomputed_operating_cf))
        recomputed_net_cf = row["operating_cash_flow_pkr"] + row["investing_cash_flow_pkr"] + row["financing_cash_flow_pkr"]
        check(f"net CF sums components q{row['quarter_index']}", close(row["net_cash_flow_pkr"], recomputed_net_cf))
        check(f"cash rolls forward q{row['quarter_index']}",
              close(row["cash_close_pkr"], row["cash_open_pkr"] + recomputed_net_cf))


def test_break_even_utilization_backsolve() -> None:
    case = golden_case()
    for quarter_index in range(1, 9):
        be = model.break_even_utilization_pct(case, quarter_index)
        check(f"break-even reachable q{quarter_index}", be["reachable"])
        # Plug the break-even utilization back into the EBITDA formula: must
        # give ~0 EBITDA for that quarter in isolation.
        capacity_per_quarter = ANNUAL_CAPACITY_TONS / 4.0
        volume = capacity_per_quarter * be["break_even_utilization_pct"] / 100.0
        contribution_margin = PRICE[quarter_index - 1] - FUEL[quarter_index - 1] - POWER[quarter_index - 1] - RAW_MAT[quarter_index - 1]
        ebitda_at_break_even = volume * contribution_margin - FIXED_COST[quarter_index - 1]
        check(f"break-even zeroes EBITDA q{quarter_index}", close(ebitda_at_break_even, 0.0, tol=1e-3))

    unreachable_case = golden_case()
    unreachable_case["inputs"]["fuel_cost_pkr_per_ton_schedule"]["value"][0] = 100_000.0
    be = model.break_even_utilization_pct(unreachable_case, 1)
    check("break-even unreachable on negative margin", not be["reachable"] and be["break_even_utilization_pct"] is None)


def test_price_implied_backsolve() -> None:
    case = golden_case()
    utilization = model.backsolve_utilization_scale(case)
    check("utilization backsolve reachable", utilization["reachable"])
    check("utilization backsolve target", close(utilization["target_value_per_share_pkr"], MARKET_PRICE - PRE_EXPANSION_VALUE))
    construction_rows = model.construction_schedule(case)
    recomputed_value = model._fair_value_impact_for_scale(
        case, construction_rows, utilization["implied_utilization_scale_pct"] / 100.0
    )
    check("utilization backsolve converges", close(recomputed_value, utilization["target_value_per_share_pkr"], tol=1e-2))

    delay = model.backsolve_commissioning_delay_quarters(case)
    check("delay backsolve returns integer in range", isinstance(delay["implied_commissioning_delay_quarters"], int)
          and 0 <= delay["implied_commissioning_delay_quarters"] <= 8)
    recomputed_delay_value = model._fair_value_impact_for_scale(
        case, construction_rows, 1.0, delay_quarters=delay["implied_commissioning_delay_quarters"]
    )
    check("delay backsolve value matches grid search", close(recomputed_delay_value, delay["implied_value_per_share_pkr"]))

    # A non-monotonic bracket (negative contribution margin) must fail closed
    # with reachable == False rather than returning a spurious scale.
    broken = golden_case()
    for index in range(8):
        broken["inputs"]["fuel_cost_pkr_per_ton_schedule"]["value"][index] = 1_000_000.0
    broken_result = model.backsolve_utilization_scale(broken)
    check("non-monotonic backsolve fails closed", not broken_result["reachable"])


def test_fail_closed_financial_truth_gate() -> None:
    case = golden_case()

    blocked = model.evaluate_with_financial_truth_gate(case, not_qualified_truth_row())
    check("not-qualified blocks", blocked["status"] == "blocked_financial_truth_not_qualified")
    check("not-qualified reason recorded", blocked["blocked_reasons"] == ["financial_truth_status:not_qualified"])
    check("not-qualified withholds valuation", blocked["valuation"] is None)
    check("not-qualified withholds schedules", blocked["operating_schedule"] == [] and blocked["construction_schedule"] == [])
    check("not-qualified withholds backsolve", blocked["price_implied_expectation_backsolve"] is None)

    missing = model.evaluate_with_financial_truth_gate(case, {})
    check("missing truth row blocks", missing["status"] == "blocked_financial_truth_not_qualified"
          and missing["blocked_reasons"] == ["financial_truth_status:missing"])

    computed = model.evaluate_with_financial_truth_gate(case, qualified_truth_row())
    check("qualified computes", computed["status"] == "computed")
    check("qualified matches pure kernel",
          json.dumps(computed, sort_keys=True) == json.dumps(model.evaluate_case(case), sort_keys=True))

    invalid_case = golden_case()
    invalid_case["inputs"].pop("useful_life_years")
    invalid_blocked = model.evaluate_with_financial_truth_gate(invalid_case, qualified_truth_row())
    check("qualified but invalid case blocks on inputs", invalid_blocked["status"] == "blocked_invalid_inputs")
    check("invalid input reason present",
          any("useful_life_years" in reason for reason in invalid_blocked["blocked_reasons"]))


def test_real_build_blocks_against_current_state() -> None:
    # The real MLCF financial_truth_qualification.json row is not_qualified
    # today; the real build must fail closed and never leak numbers, and must
    # not fabricate project economics inputs.
    result = model.build(write=False)
    check("real build blocks", result["status"] == "blocked_financial_truth_not_qualified")
    check("real build no numbers", result["valuation"] is None and result["operating_schedule"] == [])
    check("real build identity", result["project"]["symbol"] == model.REAL_SYMBOL
          and result["project"]["project_name"] == model.REAL_PROJECT_NAME)

    written = model.build(write=True)
    on_disk = json.loads(model.OUTPUT_PATH.read_text(encoding="utf-8"))
    check("generated state file matches build output", on_disk == written)
    check("generated state file path", model.OUTPUT_PATH.name == "mlcf_cement_expansion_model.json"
          and model.OUTPUT_PATH.parent.name == "company_intel")


def test_input_validation() -> None:
    case = golden_case()
    check("contract module version", model.MODULE_VERSION == "mlcf_cement_expansion_model_v1")
    check("formula id", model.FORMULA_ID == "mlcf_cement_expansion.operating_economics_and_valuation.v1")
    check("result schema", model.RESULT_SCHEMA == "mlcf_cement_expansion_model_result_v1")
    check("golden validates", model.validate_case(case) == [])

    mutations = [
        ("missing field", lambda c: c["inputs"].pop("exit_ev_ebitda_multiple"),
         "exit_ev_ebitda_multiple: missing required input"),
        ("unknown field", lambda c: c["inputs"].update(extra=analyst(1.0)), "extra: unknown input field"),
        ("bool numeric", lambda c: c["inputs"]["expansion_capex_total_pkr"].update(value=True),
         "expansion_capex_total_pkr: must be a finite number"),
        ("nan numeric", lambda c: c["inputs"]["expansion_capex_total_pkr"].update(value=float("nan")),
         "expansion_capex_total_pkr: must be a finite number"),
        ("capex zero", lambda c: c["inputs"]["expansion_capex_total_pkr"].update(value=0.0),
         "expansion_capex_total_pkr: must be > 0"),
        ("capex schedule not 100", lambda c: c["inputs"]["capex_spending_schedule_pct"].update(value=[60.0, 30.0]),
         "capex_spending_schedule_pct: must sum to 100"),
        ("capex schedule negative", lambda c: c["inputs"]["capex_spending_schedule_pct"].update(value=[110.0, -10.0]),
         "capex_spending_schedule_pct[1]: must be >= 0"),
        ("construction ends wrong length",
         lambda c: c["inputs"]["construction_quarter_ends"].update(value=["2025-12-31"]),
         "construction_quarter_ends: must be a list of exactly 2 values"),
        ("construction ends not quarter-end",
         lambda c: c["inputs"]["construction_quarter_ends"]["value"].__setitem__(0, "2026-01-05"),
         "construction_quarter_ends[0]: must be a quarter-end"),
        ("operating ends wrong length",
         lambda c: c["inputs"]["operating_quarter_ends"].update(value=["2026-06-30"]),
         "operating_quarter_ends: must be a list of exactly 8 values"),
        ("operating ends out of order",
         lambda c: c["inputs"]["operating_quarter_ends"]["value"].__setitem__(1, "2026-06-30"),
         "operating_quarter_ends[1]: quarter ends must be strictly increasing"),
        ("commissioning mismatch",
         lambda c: c["inputs"]["commissioning_date_quarter"].update(value="2026-09-30"),
         "commissioning_date_quarter: must equal operating_quarter_ends[0]"),
        ("commissioning not quarter-end",
         lambda c: c["inputs"]["commissioning_date_quarter"].update(value="2026-06-15"),
         "commissioning_date_quarter: must be a quarter-end"),
        ("depreciation method bad",
         lambda c: c["inputs"]["depreciation_method"].update(value="declining_balance"),
         "depreciation_method: must be one of"),
        ("repayment quarters out of range",
         lambda c: c["inputs"]["repayment_quarters"].update(value=[0, 5, 6, 7]),
         "repayment_quarters[0]: must be an integer from 1 to 8"),
        ("repayment quarters duplicate",
         lambda c: c["inputs"]["repayment_quarters"].update(value=[5, 5, 6, 7]),
         "repayment_quarters: must not contain duplicates"),
        ("repayment quarters empty",
         lambda c: c["inputs"]["repayment_quarters"].update(value=[]),
         "repayment_quarters: must be a non-empty list"),
        ("ramp schedule wrong length",
         lambda c: c["inputs"]["ramp_pct_schedule"].update(value=[10.0] * 7),
         "ramp_pct_schedule: must be a list of exactly 8 values"),
        ("ramp schedule out of bounds",
         lambda c: c["inputs"]["ramp_pct_schedule"]["value"].__setitem__(0, 101.0),
         "ramp_pct_schedule[0]: must be in [0, 100]"),
        ("selling price non-positive",
         lambda c: c["inputs"]["selling_price_pkr_per_ton_schedule"]["value"].__setitem__(0, 0.0),
         "selling_price_pkr_per_ton_schedule[0]: must be > 0"),
        ("fixed cost negative",
         lambda c: c["inputs"]["fixed_operating_cost_pkr_quarterly_schedule"]["value"].__setitem__(0, -1.0),
         "fixed_operating_cost_pkr_quarterly_schedule[0]: must be >= 0"),
        ("debt financing pct out of bounds",
         lambda c: c["inputs"]["debt_financing_pct"].update(value=101.0),
         "debt_financing_pct: must be in [0, 100]"),
        ("interest rate 100", lambda c: c["inputs"]["annual_interest_rate_pct"].update(value=100.0),
         "annual_interest_rate_pct: must be in [0, 100)"),
        ("tax rate 100", lambda c: c["inputs"]["tax_rate_pct"].update(value=100.0),
         "tax_rate_pct: must be in [0, 100)"),
        ("working capital 100", lambda c: c["inputs"]["working_capital_pct_revenue"].update(value=100.0),
         "working_capital_pct_revenue: must be in [0, 100)"),
        ("discount rate zero", lambda c: c["inputs"]["valuation_discount_rate_pct_annual"].update(value=0.0),
         "valuation_discount_rate_pct_annual: must be in (0, 100)"),
        ("discount rate 101", lambda c: c["inputs"]["valuation_discount_rate_pct_annual"].update(value=101.0),
         "valuation_discount_rate_pct_annual: must be in (0, 100)"),
        ("shares zero", lambda c: c["inputs"]["shares_outstanding"].update(value=0.0),
         "shares_outstanding: must be > 0"),
        ("exit multiple zero", lambda c: c["inputs"]["exit_ev_ebitda_multiple"].update(value=0.0),
         "exit_ev_ebitda_multiple: must be > 0"),
        ("useful life zero", lambda c: c["inputs"]["useful_life_years"].update(value=0.0),
         "useful_life_years: must be > 0"),
        ("pre-expansion value negative",
         lambda c: c["inputs"]["pre_expansion_fair_value_pkr_per_share"].update(value=-1.0),
         "pre_expansion_fair_value_pkr_per_share: must be >= 0"),
        ("lookahead", lambda c: c["inputs"]["expansion_capex_total_pkr"].update(available_on="2026-01-01"),
         "expansion_capex_total_pkr: available_on must be on or before valuation_date"),
        ("bad label", lambda c: c["inputs"]["expansion_capex_total_pkr"].update(label_type="bad"),
         "provenance record must carry"),
        ("case label", lambda c: c.update(case_label="stress"), "case_label: must be one of bear, base, bull"),
        ("missing project name", lambda c: c.update(project_name=""), "project_name: must be a non-empty string"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        expect_reject(name, candidate, expected)

    try:
        model.evaluate_case({"symbol": "CEMEXP"})
    except ValueError as error:
        check("evaluate raises named violations", "; " in str(error) and "case_label" in str(error))
    else:
        raise AssertionError("evaluate should reject invalid case")

    check("source provenance accepted", model.validate_case(golden_case()) == [])
    with_source = golden_case()
    with_source["inputs"]["expansion_capex_total_pkr"] = source(CAPEX_TOTAL)
    check("source-labelled input accepted", model.validate_case(with_source) == [])


def test_envelope_shape_and_no_advice() -> None:
    case = golden_case()
    result = model.evaluate_case(case)
    expected_keys = {
        "schema_version", "formula_id", "module_version", "run_receipt", "status",
        "blocked_reasons", "project", "inputs_lineage", "construction_schedule",
        "operating_schedule", "accounting_integrity", "valuation",
        "break_even_utilization", "price_implied_expectation_backsolve",
        "confidence_limitations",
    }
    check("envelope shape", set(result) == expected_keys)
    check("computed status", result["status"] == "computed" and result["blocked_reasons"] == [])
    check("lineage sorted and complete", [row["field"] for row in result["inputs_lineage"]] == sorted(case["inputs"]))

    repeat = model.evaluate_case(case)
    copied = model.evaluate_case(copy.deepcopy(case))
    dump = json.dumps(result, sort_keys=True)
    check("same object deterministic", json.dumps(repeat, sort_keys=True) == dump)
    check("deepcopy deterministic", json.dumps(copied, sort_keys=True) == dump)

    blocked = model.blocked_result(golden_case(), ["zeta", "alpha", "alpha"])
    check("blocked envelope reasons sorted and deduped", blocked["blocked_reasons"] == ["alpha", "zeta"])

    for label, payload in (("computed", result), ("blocked", blocked)):
        text_payload = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text_payload) is None)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))

    for symbol in ("open", "write", "requests"):
        check(f"kernel has no forbidden symbol: {symbol}", not hasattr(model, symbol) or symbol in ("save_json", "load_json"))


def main() -> None:
    test_ramp_mathematics()
    test_debt_schedule_roll_forward()
    test_accounting_integrity_link()
    test_break_even_utilization_backsolve()
    test_price_implied_backsolve()
    test_fail_closed_financial_truth_gate()
    test_real_build_blocks_against_current_state()
    test_input_validation()
    test_envelope_shape_and_no_advice()
    print(f"mlcf cement expansion model: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
