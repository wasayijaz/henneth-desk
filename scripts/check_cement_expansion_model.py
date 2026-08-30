"""Focused deterministic checks for the cement-expansion kernel."""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cement_expansion_contract as contract
import cement_expansion_engine as engine

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def analyst(value, note="explicit cement expansion case assumption"):
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "note:cement-expansion:golden", "note": note},
        "available_on": "2025-12-31",
    }


def source(value):
    return {
        "value": value,
        "label_type": "source",
        "source_ref": {
            "id": "source:cement-expansion:fixture",
            "label": "Retained cement expansion evidence",
            "url": "https://example.invalid/cement-expansion",
        },
        "available_on": "2025-12-31",
    }


def golden_case() -> dict:
    return {
        "symbol": "CEMEXP",
        "event_ref": "cement-expansion-fixture",
        "case_label": "base",
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
        "inputs": {
            "quarter_ends": analyst([
                "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30",
                "2026-12-31", "2027-03-31", "2027-06-30", "2027-09-30",
            ]),
            "commissioning_quarter_index": analyst(2),
            "incremental_capacity_units": analyst(100_000.0),
            "starting_utilization_pct": analyst(20.0),
            "utilization_ramp_pct_schedule": analyst([20.0, 40.0, 55.0, 70.0, 80.0, 85.0, 90.0, 90.0]),
            "starting_revenue_pkr": analyst(100_000_000.0),
            "selling_price_pkr_per_unit_schedule": analyst([2_000.0] * 8),
            "fuel_cost_pkr_per_unit_schedule": analyst([300.0] * 8),
            "power_cost_pkr_per_unit_schedule": analyst([100.0] * 8),
            "freight_cost_pkr_per_unit_schedule": analyst([50.0] * 8),
            "fixed_cost_pkr_schedule": analyst([10_000_000.0] * 8),
            "capex_schedule_pkr": analyst([50_000_000.0, 100_000_000.0, 50_000_000.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            "depreciation_pkr_schedule": analyst([0.0, 5_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0]),
            "gross_margin_pct": analyst(50.0),
            "working_capital_pct_revenue": analyst(10.0),
            "debt_financing_pkr": analyst(50_000_000.0),
            "equity_financing_pkr": analyst(150_000_000.0),
            "annual_interest_rate_pct": analyst(12.0),
            "effective_tax_pct": analyst(30.0),
            "shares_out": analyst(100_000_000.0),
            "discount_rate_pct_annual": analyst(12.0),
        },
    }


def expect_reject(name, candidate, expected):
    violations = contract.validate_case(candidate)
    check(f"boundary {name}", any(expected in violation for violation in violations), repr(violations))


def main() -> None:
    case = golden_case()
    check("contract version", contract.CONTRACT_VERSION == "cement_expansion_contract_v1")
    check("engine ids", engine.ENGINE_VERSION == "cement_expansion_engine_v1"
          and engine.FORMULA_ID == "cement_expansion.operating_economics.v1"
          and engine.RESULT_SCHEMA == "cement_expansion_model_result_v1")
    check("golden validates", contract.validate_case(case) == [])
    check("source provenance accepted", contract.provenance_ok(source(1.0)))
    check("analyst provenance accepted", contract.provenance_ok(analyst(1.0)))
    check("unknown provenance rejected", not contract.provenance_ok({"label_type": "guess"}))
    check("source locator required", not contract.provenance_ok({"label_type": "source", "source_ref": {"id": "x", "label": "y"}}))
    check("analyst note required", not contract.provenance_ok({"label_type": "analyst", "analyst_ref": {"note_id": "n"}}))

    result = engine.evaluate_case(case)
    expected_keys = {"schema_version", "formula_id", "engine_version", "run_receipt", "status",
                     "blocked_reasons", "scenario", "inputs_lineage", "quarterly_schedule",
                     "values", "per_share", "break_even", "confidence_limitations"}
    check("envelope shape", set(result) == expected_keys)
    check("computed status", result["status"] == "computed" and result["blocked_reasons"] == [])
    check("lineage sorted and complete", [row["field"] for row in result["inputs_lineage"]] == sorted(case["inputs"]))
    check("lineage provenance", all(row["label_type"] == "analyst" for row in result["inputs_lineage"]))
    rows = result["quarterly_schedule"]
    check("schedule has eight rows", len(rows) == 8 and [row["quarter_index"] for row in rows] == list(range(1, 9)))
    check("schedule dates preserved", [row["quarter_end"] for row in rows] == case["inputs"]["quarter_ends"]["value"])
    q1, q2 = rows[:2]
    check("commissioning gate", q1["commissioned"] is False and close(q1["volume_units"], 0.0)
          and q2["commissioned"] is True and close(q2["volume_units"], 40_000.0))
    check("q1 revenue", close(q1["revenue_pkr"], 100_000_000.0))
    check("q1 gross profit", close(q1["gross_profit_pkr"], 50_000_000.0))
    check("q1 ebitda", close(q1["ebitda_pkr"], 40_000_000.0))
    check("q1 tax", close(q1["tax_pkr"], 11_550_000.0))
    check("q1 eps", close(q1["eps_pkr"], 0.2695))
    check("q1 fcf", close(q1["fcf_pkr"], -23_050_000.0))
    check("q1 roic", close(q1["roic_pct"], 14.0))
    check("q1 discount at valuation", close(q1["discount_factor"], 1.0))
    check("q2 incremental economics", close(q2["revenue_pkr"], 180_000_000.0)
          and close(q2["variable_cost_pkr"], 18_000_000.0)
          and close(q2["gross_profit_pkr"], 112_000_000.0)
          and close(q2["ebitda_pkr"], 102_000_000.0)
          and close(q2["eps_pkr"], 0.6685))
    check("q2 discount after valuation", q2["discount_factor"] < 1.0)
    check("discounted fcf identity", close(q2["discounted_fcf_pkr"], q2["fcf_pkr"] * q2["discount_factor"]))
    check("values aggregate", close(result["values"]["total_revenue_pkr"], sum(row["revenue_pkr"] for row in rows))
          and close(result["values"]["total_fcf_pkr"], sum(row["fcf_pkr"] for row in rows)))
    check("per-share value", close(result["per_share"]["npv_pkr"], result["values"]["npv_pkr"] / 100_000_000.0))
    check("break-even fields", result["break_even"]["ebitda_break_even_quarter"] == 1
          and result["break_even"]["cash_break_even_quarter"] == 4)
    check("limitations explicit", result["confidence_limitations"]["research_only"]
          and result["confidence_limitations"]["no_advice"]
          and "depreciation, capex, fixed costs and financing schedules are explicit; debt principal amortization is not modeled"
          in result["confidence_limitations"]["simplifications"])

    repeat = engine.evaluate_case(case)
    copied = engine.evaluate_case(copy.deepcopy(case))
    dump = json.dumps(result, sort_keys=True)
    check("same object deterministic", json.dumps(repeat, sort_keys=True) == dump)
    check("deepcopy deterministic", json.dumps(copied, sort_keys=True) == dump)
    frozen = json.dumps(result, sort_keys=True)
    case["inputs"]["gross_margin_pct"]["value"] = 51.0
    check("result detached from input mutation", json.dumps(result, sort_keys=True) == frozen)
    changed = engine.evaluate_case(case)
    check("input mutation changes hash", changed["run_receipt"]["inputs_sha256"] != result["run_receipt"]["inputs_sha256"])

    extreme = golden_case()
    extreme["inputs"]["starting_revenue_pkr"]["value"] = 1e308
    try:
        engine.evaluate_case(extreme)
    except ValueError as error:
        check("extreme revenue fails closed", "non-finite output" in str(error))
    else:
        raise AssertionError("extreme revenue should fail closed")

    mutations = [
        ("missing field", lambda c: c["inputs"].pop("gross_margin_pct"), "gross_margin_pct: missing required input"),
        ("bool numeric", lambda c: c["inputs"]["debt_financing_pkr"].update(value=True), "debt_financing_pkr: must be a finite number"),
        ("nan numeric", lambda c: c["inputs"]["debt_financing_pkr"].update(value=float("nan")), "debt_financing_pkr: must be a finite number"),
        ("commissioning bool", lambda c: c["inputs"]["commissioning_quarter_index"].update(value=True), "commissioning_quarter_index: must be an integer"),
        ("commissioning zero", lambda c: c["inputs"]["commissioning_quarter_index"].update(value=0), "commissioning_quarter_index: must be an integer"),
        ("schedule wrong length", lambda c: c["inputs"]["quarter_ends"].update(value=["2025-12-31"]), "quarter_ends: must be a list of exactly 8 values"),
        ("non-quarter-end", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(0, "2026-01-01"), "quarter_ends[0]: must be a quarter-end"),
        ("quarter before valuation", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(0, "2025-09-30"), "quarter_ends[0]: must be on or after valuation_date"),
        ("quarter out of order", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(1, "2025-12-31"), "quarter_ends[1]: quarter ends must be strictly increasing"),
        ("gross margin 101", lambda c: c["inputs"]["gross_margin_pct"].update(value=101.0), "gross_margin_pct: must be in [0, 100]"),
        ("working capital 100", lambda c: c["inputs"]["working_capital_pct_revenue"].update(value=100.0), "working_capital_pct_revenue: must be in [0, 100)"),
        ("tax 100", lambda c: c["inputs"]["effective_tax_pct"].update(value=100.0), "effective_tax_pct: must be in [0, 100)"),
        ("interest 100", lambda c: c["inputs"]["annual_interest_rate_pct"].update(value=100.0), "annual_interest_rate_pct: must be in [0, 100)"),
        ("discount zero", lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=0.0), "discount_rate_pct_annual: must be > 0"),
        ("capacity zero", lambda c: c["inputs"]["incremental_capacity_units"].update(value=0.0), "incremental_capacity_units: must be > 0"),
        ("utilization 101", lambda c: c["inputs"]["utilization_ramp_pct_schedule"]["value"].__setitem__(0, 101.0), "utilization_ramp_pct_schedule[0]: must be in [0, 100]"),
        ("price zero", lambda c: c["inputs"]["selling_price_pkr_per_unit_schedule"]["value"].__setitem__(0, 0.0), "selling_price_pkr_per_unit_schedule[0]: must be > 0"),
        ("shares zero", lambda c: c["inputs"]["shares_out"].update(value=0.0), "shares_out: must be > 0"),
        ("lookahead", lambda c: c["inputs"]["debt_financing_pkr"].update(available_on="2026-01-01"), "debt_financing_pkr: available_on must be on or before valuation_date"),
        ("bad label", lambda c: c["inputs"]["debt_financing_pkr"].update(label_type="bad"), "provenance record must carry"),
        ("bad analyst ref", lambda c: c["inputs"]["debt_financing_pkr"].update(analyst_ref={"note_id": "n"}), "provenance record must carry"),
        ("case label", lambda c: c.update(case_label="stress"), "case_label: must be one of bear, base, bull"),
        ("unknown field", lambda c: c["inputs"].update(extra=analyst(1.0)), "extra: unknown input field"),
        ("non-json", lambda c: c["inputs"].update(extra={"value": {1, 2}}), "extra: unknown input field"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        expect_reject(name, candidate, expected)

    try:
        engine.evaluate_case({"symbol": "CEMEXP"})
    except ValueError as error:
        check("evaluate raises named violations", "; " in str(error) and "case_label" in str(error))
    else:
        raise AssertionError("evaluate should reject invalid case")

    blocked = engine.blocked_result(golden_case(), ["zeta", "alpha", "alpha"])
    check("blocked envelope", blocked["status"] == "blocked" and blocked["values"] is None
          and blocked["per_share"] is None and blocked["quarterly_schedule"] == []
          and blocked["break_even"] is None and blocked["blocked_reasons"] == ["alpha", "zeta"])

    for label, payload in (("computed", result), ("blocked", blocked)):
        text = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text) is None)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))

    for module in (contract, engine):
        for symbol in ("open", "save_json", "load_json", "write"):
            check(f"no file io symbol {module.__name__}.{symbol}", not hasattr(module, symbol))
    print(f"cement expansion model: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
