"""Focused deterministic checks for the sales-expansion kernel."""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sales_expansion_contract as contract
import sales_expansion_engine as engine

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


def analyst(value, note="explicit expansion case assumption"):
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "note:sales-expansion:golden", "note": note},
        "available_on": "2025-12-31",
    }


def source(value):
    return {
        "value": value,
        "label_type": "source",
        "source_ref": {
            "id": "source:sales-expansion:fixture",
            "label": "Retained expansion evidence",
            "url": "https://example.invalid/retained-expansion",
        },
        "available_on": "2025-12-31",
    }


def golden_case() -> dict:
    return {
        "symbol": "EXPAND",
        "event_ref": "sales-expansion-fixture",
        "case_label": "base",
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
        "inputs": {
            "quarter_ends": analyst([
                "2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31",
                "2027-03-31", "2027-06-30", "2027-09-30", "2027-12-31",
            ]),
            "sales_hires_schedule": analyst([2, 3, 4, 5, 6, 7, 8, 9]),
            "support_hires_schedule": analyst([1, 1, 1, 1, 1, 1, 1, 1]),
            "starting_revenue_pkr": analyst(100_000_000.0),
            "sales_compensation_usd_annual": analyst(12_000.0),
            "support_compensation_usd_annual": analyst(8_000.0),
            "fx_pkr_usd": analyst(280.0),
            "marketing_spend_pkr_schedule": analyst([1_000_000.0] * 8),
            "productivity_revenue_pkr_per_sales_hire_schedule": analyst(
                [5_000_000.0, 6_000_000.0, 7_000_000.0, 8_000_000.0,
                 9_000_000.0, 10_000_000.0, 11_000_000.0, 12_000_000.0]
            ),
            "gross_margin_pct": analyst(50.0),
            "working_capital_pct_revenue": analyst(10.0),
            "initial_investment_pkr": analyst(20_000_000.0),
            "effective_tax_pct": analyst(30.0),
            "shares_out": analyst(100_000_000.0),
            "discount_rate_pct_annual": analyst(12.0),
        },
    }


def main() -> None:
    case = golden_case()
    check("contract version", contract.CONTRACT_VERSION == "sales_expansion_contract_v1")
    check("engine ids",
          engine.ENGINE_VERSION == "sales_expansion_engine_v1"
          and engine.FORMULA_ID == "sales_expansion.operating_economics.v1"
          and engine.RESULT_SCHEMA == "sales_expansion_model_result_v1")
    check("golden validates", contract.validate_case(case) == [])
    check("source provenance accepted", contract.provenance_ok(source(1.0)))
    check("analyst provenance accepted", contract.provenance_ok(analyst(1.0)))
    check("unknown provenance rejected", not contract.provenance_ok({"label_type": "guess"}))
    check("source locator required",
          not contract.provenance_ok({"label_type": "source",
                                      "source_ref": {"id": "x", "label": "y"}}))
    check("analyst note required",
          not contract.provenance_ok({"label_type": "analyst",
                                      "analyst_ref": {"note_id": "n"}}))

    result = engine.evaluate_case(case)
    expected_keys = {
        "schema_version", "formula_id", "engine_version", "run_receipt",
        "status", "blocked_reasons", "scenario", "inputs_lineage",
        "quarterly_schedule", "values", "per_share", "break_even",
        "confidence_limitations",
    }
    check("envelope shape", set(result) == expected_keys)
    check("envelope ids",
          result["schema_version"] == engine.RESULT_SCHEMA
          and result["formula_id"] == engine.FORMULA_ID
          and result["engine_version"] == engine.ENGINE_VERSION)
    check("computed status", result["status"] == "computed" and result["blocked_reasons"] == [])
    check("lineage sorted and complete",
          [row["field"] for row in result["inputs_lineage"]] == sorted(case["inputs"]))
    check("lineage provenance",
          all(row["label_type"] == "analyst" and row["available_on"] == "2025-12-31"
              for row in result["inputs_lineage"]))
    check("schedule has eight rows",
          len(result["quarterly_schedule"]) == 8
          and [row["quarter_index"] for row in result["quarterly_schedule"]] == list(range(1, 9)))
    check("schedule dates preserved",
          [row["quarter_end"] for row in result["quarterly_schedule"]]
          == case["inputs"]["quarter_ends"]["value"])
    q1 = result["quarterly_schedule"][0]
    check("q1 revenue", close(q1["revenue_pkr"], 110_000_000.0))
    check("q1 sga", close(q1["sga_pkr"], 3_240_000.0))
    check("q1 gross profit", close(q1["gross_profit_pkr"], 55_000_000.0))
    check("q1 ebitda", close(q1["ebitda_pkr"], 51_760_000.0))
    check("q1 tax", close(q1["tax_pkr"], 15_528_000.0))
    check("q1 eps operating proxy", close(q1["eps_pkr"], 0.36232))
    check("q1 working capital", close(q1["working_capital_pkr"], 11_000_000.0))
    check("q1 delta working capital", close(q1["delta_working_capital_pkr"], 1_000_000.0))
    check("q1 fcf", close(q1["fcf_pkr"], 15_232_000.0))
    check("q1 roic", close(q1["roic_pct"], 181.16))
    check("q1 discounts after valuation quarter", q1["discount_factor"] < 1.0)
    check("q1 discounted fcf", close(q1["discounted_fcf_pkr"], q1["fcf_pkr"] * q1["discount_factor"]))
    check("values aggregate",
          close(result["values"]["total_revenue_pkr"],
                sum(row["revenue_pkr"] for row in result["quarterly_schedule"]))
          and close(result["values"]["total_fcf_pkr"],
                    sum(row["fcf_pkr"] for row in result["quarterly_schedule"])))
    check("npv positive", result["values"]["npv_pkr"] > 0.0)
    check("per-share value", close(result["per_share"]["npv_pkr"],
                                   result["values"]["npv_pkr"] / 100_000_000.0))
    check("break-even reached",
          result["break_even"]["ebitda_break_even_quarter"] == 1
          and result["break_even"]["cash_break_even_quarter"] == 1
          and result["break_even"]["note"] is None)
    check("CAC/retention not input fields",
          all("cac" not in row["field"].lower() and "retention" not in row["field"].lower()
              for row in result["inputs_lineage"])
          and "CAC and customer retention are not modeled in v1"
          in result["confidence_limitations"]["simplifications"])

    repeat = engine.evaluate_case(case)
    copied = engine.evaluate_case(copy.deepcopy(case))
    dump = json.dumps(result, sort_keys=True)
    check("same object deterministic", json.dumps(repeat, sort_keys=True) == dump)
    check("deepcopy deterministic", json.dumps(copied, sort_keys=True) == dump)
    frozen = json.dumps(result, sort_keys=True)
    case["inputs"]["fx_pkr_usd"]["value"] = 281.0
    check("result detached from input mutation", json.dumps(result, sort_keys=True) == frozen)
    changed = engine.evaluate_case(case)
    check("input mutation changes hash", changed["run_receipt"]["inputs_sha256"] != result["run_receipt"]["inputs_sha256"])

    for field in ("fx_pkr_usd", "starting_revenue_pkr"):
        extreme = golden_case()
        extreme["inputs"][field]["value"] = 1e308
        try:
            engine.evaluate_case(extreme)
        except ValueError as error:
            check(f"extreme {field} fails closed", "non-finite output" in str(error))
        else:
            raise AssertionError(f"extreme {field} should fail closed")

    mutations = [
        ("missing field", lambda c: c["inputs"].pop("gross_margin_pct"), "gross_margin_pct: missing required input"),
        ("bool numeric", lambda c: c["inputs"]["fx_pkr_usd"].update(value=True), "fx_pkr_usd: must be a finite number"),
        ("nan numeric", lambda c: c["inputs"]["fx_pkr_usd"].update(value=float("nan")), "fx_pkr_usd: must be a finite number"),
        ("hire bool", lambda c: c["inputs"]["sales_hires_schedule"]["value"].__setitem__(0, True), "sales_hires_schedule[0]: must be an integer >= 0"),
        ("hire negative", lambda c: c["inputs"]["sales_hires_schedule"]["value"].__setitem__(0, -1), "sales_hires_schedule[0]: must be an integer >= 0"),
        ("schedule wrong length", lambda c: c["inputs"]["quarter_ends"].update(value=["2026-03-31"]), "quarter_ends: must be a list of exactly 8 values"),
        ("non-quarter-end", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(0, "2026-03-15"), "quarter_ends[0]: must be a quarter-end"),
        ("quarter before valuation", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(0, "2025-09-30"), "quarter_ends[0]: must be on or after valuation_date"),
        ("quarter out of order", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(1, "2026-03-31"), "quarter_ends[1]: quarter ends must be strictly increasing"),
        ("gross margin 101", lambda c: c["inputs"]["gross_margin_pct"].update(value=101.0), "gross_margin_pct: must be in [0, 100]"),
        ("working capital 100", lambda c: c["inputs"]["working_capital_pct_revenue"].update(value=100.0), "working_capital_pct_revenue: must be in [0, 100)"),
        ("tax 100", lambda c: c["inputs"]["effective_tax_pct"].update(value=100.0), "effective_tax_pct: must be in [0, 100)"),
        ("discount zero", lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=0.0), "discount_rate_pct_annual: must be > 0"),
        ("investment zero", lambda c: c["inputs"]["initial_investment_pkr"].update(value=0.0), "initial_investment_pkr: must be > 0"),
        ("shares zero", lambda c: c["inputs"]["shares_out"].update(value=0.0), "shares_out: must be > 0"),
        ("lookahead", lambda c: c["inputs"]["fx_pkr_usd"].update(available_on="2026-01-01"), "fx_pkr_usd: available_on must be on or before valuation_date"),
        ("bad label", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="bad"), "provenance record must carry"),
        ("bad analyst ref", lambda c: c["inputs"]["fx_pkr_usd"].update(analyst_ref={"note_id": "n"}), "provenance record must carry"),
        ("bad source ref", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="source", source_ref={"id": "i", "label": "l"}), "provenance record must carry"),
        ("case label", lambda c: c.update(case_label="stress"), "case_label: must be one of bear, base, bull"),
        ("unknown nan field", lambda c: c["inputs"].update(extra_nan=analyst(float("nan"))), "extra_nan: unknown input field"),
        ("non-json", lambda c: c["inputs"].update(extra={"value": {1, 2}}), "unknown input field"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        violations = contract.validate_case(candidate)
        check(f"boundary {name}", any(expected in violation for violation in violations),
              repr(violations))

    try:
        engine.evaluate_case({"symbol": "EXPAND"})
    except ValueError as error:
        check("evaluate raises named violations", "; " in str(error) and "case_label" in str(error))
    else:
        raise AssertionError("evaluate should reject invalid case")

    blocked = engine.blocked_result(golden_case(), ["zeta", "alpha", "alpha"])
    check("blocked envelope", blocked["status"] == "blocked"
          and blocked["values"] is None
          and blocked["per_share"] is None
          and blocked["quarterly_schedule"] == []
          and blocked["break_even"] is None
          and blocked["blocked_reasons"] == ["alpha", "zeta"])

    for label, payload in (("computed", result), ("blocked", blocked)):
        text = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", phrase not in text)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))

    for module in (contract, engine):
        for symbol in ("open", "save_json", "load_json", "write"):
            check(f"no file io symbol {module.__name__}.{symbol}", not hasattr(module, symbol))
    print(f"sales expansion model: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
