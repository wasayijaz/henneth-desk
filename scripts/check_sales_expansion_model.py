"""Focused deterministic checks for the sales-expansion kernel."""
from __future__ import annotations

from collections.abc import Mapping
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


class ListKeyInputs(Mapping):
    def __init__(self, base: Mapping, bad_key: list, bad_value):
        self._items = list(base.items()) + [(bad_key, bad_value)]

    def __iter__(self):
        for key, _ in self._items:
            yield key

    def __len__(self):
        return len(self._items)

    def __getitem__(self, key):
        for stored_key, value in self._items:
            if stored_key == key:
                return value
        raise KeyError(key)


def assert_violation(name: str, candidate: dict, expected: str) -> None:
    violations = contract.validate_case(candidate)
    check(name, any(expected in violation for violation in violations), repr(violations))


def assert_rejected_by_evaluate(name: str, candidate: dict, expected: str) -> None:
    try:
        engine.evaluate_case(candidate)
    except ValueError as error:
        check(name, expected in str(error), str(error))
    else:
        raise AssertionError(f"{name}: evaluate_case should reject invalid case")


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

    hostile_root = ListKeyInputs(case, ["bad", "root"], analyst(1.0))
    root_violations = contract.validate_case(hostile_root)
    check("root list-like key is controlled",
          any("case.['bad', 'root']: unknown field" in violation for violation in root_violations),
          repr(root_violations))
    assert_rejected_by_evaluate(
        "evaluate rejects root list-like key", hostile_root, "case.['bad', 'root']: unknown field"
    )

    hostile_record_case = golden_case()
    hostile_record_case["inputs"]["fx_pkr_usd"] = ListKeyInputs(
        hostile_record_case["inputs"]["fx_pkr_usd"], ["bad", "record"], 1.0
    )
    record_violations = contract.validate_case(hostile_record_case)
    check("record list-like key is controlled",
          any("fx_pkr_usd.['bad', 'record']: unknown field" in violation
              for violation in record_violations),
          repr(record_violations))
    assert_rejected_by_evaluate(
        "evaluate rejects record list-like key",
        hostile_record_case,
        "fx_pkr_usd.['bad', 'record']: unknown field",
    )

    hostile_ref_case = golden_case()
    source_record = source(280.0)
    source_record["source_ref"] = ListKeyInputs(
        source_record["source_ref"], ["bad", "source-ref"], "x"
    )
    hostile_ref_case["inputs"]["fx_pkr_usd"] = source_record
    ref_violations = contract.validate_case(hostile_ref_case)
    check("source-ref list-like key is controlled",
          any("fx_pkr_usd.source_ref.['bad', 'source-ref']: unknown field" in violation
              for violation in ref_violations),
          repr(ref_violations))
    assert_rejected_by_evaluate(
        "evaluate rejects source-ref list-like key",
        hostile_ref_case,
        "fx_pkr_usd.source_ref.['bad', 'source-ref']: unknown field",
    )

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
          all(set(row) == {"field", "label_type", "analyst_note_id"}
              and row["label_type"] == "analyst"
              and row["analyst_note_id"] == "note:sales-expansion:golden"
              for row in result["inputs_lineage"]))
    check("lineage omits raw assumptions",
          all("value" not in row and "available_on" not in row and "analyst_ref" not in row
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

    sourced = golden_case()
    sourced["inputs"]["fx_pkr_usd"] = source(280.0)
    sourced["inputs"]["fx_pkr_usd"]["source_ref"]["as_of"] = "2025-12-30"
    sourced_result = engine.evaluate_case(sourced)
    sourced_lineage = next(row for row in sourced_result["inputs_lineage"] if row["field"] == "fx_pkr_usd")
    check("source lineage identifiers only",
          sourced_lineage == {
              "field": "fx_pkr_usd",
              "label_type": "source",
              "source_ref_id": "source:sales-expansion:fixture",
          })
    sourced_text = json.dumps(sourced_result, sort_keys=True).lower()
    check("source lineage omits prose and source dates",
          "retained expansion evidence" not in sourced_text
          and "https://example.invalid/retained-expansion" not in sourced_text
          and "2025-12-30" not in sourced_text)

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
        ("top-level extra", lambda c: c.update(caller_prose="you should buy"), "case.caller_prose: unknown field"),
        ("root nan", lambda c: c.update(extra_nan=float("nan")), "case: must be JSON-serializable with finite numeric values"),
        ("missing field", lambda c: c["inputs"].pop("gross_margin_pct"), "gross_margin_pct: missing required input"),
        ("bool numeric", lambda c: c["inputs"]["fx_pkr_usd"].update(value=True), "fx_pkr_usd: must be a finite number"),
        ("nan numeric", lambda c: c["inputs"]["fx_pkr_usd"].update(value=float("nan")), "fx_pkr_usd: must be a finite number"),
        ("hire bool", lambda c: c["inputs"]["sales_hires_schedule"]["value"].__setitem__(0, True), "sales_hires_schedule[0]: must be an integer >= 0"),
        ("hire negative", lambda c: c["inputs"]["sales_hires_schedule"]["value"].__setitem__(0, -1), "sales_hires_schedule[0]: must be an integer >= 0"),
        ("hire huge", lambda c: c["inputs"]["sales_hires_schedule"]["value"].__setitem__(0, 10**400), "sales_hires_schedule[0]: must be <="),
        ("support huge", lambda c: c["inputs"]["support_hires_schedule"]["value"].__setitem__(0, 10**400), "support_hires_schedule[0]: must be <="),
        ("schedule wrong length", lambda c: c["inputs"]["quarter_ends"].update(value=["2026-03-31"]), "quarter_ends: must be a list of exactly 8 values"),
        ("non-quarter-end", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(0, "2026-03-15"), "quarter_ends[0]: must be a quarter-end"),
        ("quarter before valuation", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(0, "2025-09-30"), "quarter_ends[0]: must be on or after valuation_date"),
        ("quarter out of order", lambda c: c["inputs"]["quarter_ends"]["value"].__setitem__(1, "2026-03-31"), "quarter_ends[1]: quarter ends must be strictly increasing"),
        ("gross margin 101", lambda c: c["inputs"]["gross_margin_pct"].update(value=101.0), "gross_margin_pct: must be in [0, 100]"),
        ("working capital 100", lambda c: c["inputs"]["working_capital_pct_revenue"].update(value=100.0), "working_capital_pct_revenue: must be in [0, 100)"),
        ("tax 100", lambda c: c["inputs"]["effective_tax_pct"].update(value=100.0), "effective_tax_pct: must be in [0, 100)"),
        ("discount zero", lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=0.0), "discount_rate_pct_annual: must be in (0, 100)"),
        ("discount 100", lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=100.0), "discount_rate_pct_annual: must be in (0, 100)"),
        ("investment zero", lambda c: c["inputs"]["initial_investment_pkr"].update(value=0.0), "initial_investment_pkr: must be > 0"),
        ("shares zero", lambda c: c["inputs"]["shares_out"].update(value=0.0), "shares_out: must be > 0"),
        ("lookahead", lambda c: c["inputs"]["fx_pkr_usd"].update(available_on="2026-01-01"), "fx_pkr_usd: available_on must be on or before valuation_date"),
        ("bad label", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="bad"), "provenance record must carry"),
        ("bad analyst ref", lambda c: c["inputs"]["fx_pkr_usd"].update(analyst_ref={"note_id": "n"}), "provenance record must carry"),
        ("bad source ref", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="source", source_ref={"id": "i", "label": "l"}), "provenance record must carry"),
        ("input record extra", lambda c: c["inputs"]["fx_pkr_usd"].update(caller_prose="you should buy"), "fx_pkr_usd.caller_prose: unknown field"),
        ("source ref extra date", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="source", source_ref={
            "id": "i", "label": "l", "url": "https://example.invalid", "date": "2030-01-01",
        }), "fx_pkr_usd.source_ref.date: unknown field"),
        ("source ref future as-of", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="source", source_ref={
            "id": "i", "label": "l", "url": "https://example.invalid", "as_of": "2026-01-01",
        }), "fx_pkr_usd.source_ref.as_of: must be on or before valuation_date"),
        ("source ref malformed as-of", lambda c: c["inputs"]["fx_pkr_usd"].update(label_type="source", source_ref={
            "id": "i", "label": "l", "url": "https://example.invalid", "as_of": "not-a-date",
        }), "fx_pkr_usd.source_ref.as_of: must be an ISO date"),
        ("analyst ref extra", lambda c: c["inputs"]["fx_pkr_usd"]["analyst_ref"].update(memo="forecast"), "fx_pkr_usd.analyst_ref.memo: unknown field"),
        ("case label", lambda c: c.update(case_label="stress"), "case_label: must be one of bear, base, bull"),
        ("unknown nan field", lambda c: c["inputs"].update(extra_nan=analyst(float("nan"))), "extra_nan: unknown input field"),
        ("non-json", lambda c: c["inputs"].update(extra={"value": {1, 2}}), "unknown input field"),
        ("inputs non-mapping", lambda c: c.update(inputs=[]), "inputs: must be a mapping of field to provenance record"),
        ("record non-mapping", lambda c: c["inputs"].update(fx_pkr_usd=[]), "fx_pkr_usd: input must be a provenance record mapping"),
        ("integer input key", lambda c: c["inputs"].update({1: analyst(1.0)}), "1: input field must be a string"),
        ("tuple input key", lambda c: c["inputs"].update({("bad", "key"): analyst(1.0)}), "('bad', 'key'): input field must be a string"),
        ("list-like input key", lambda c: c.update(inputs=ListKeyInputs(c["inputs"], ["bad", "key"], analyst(1.0))), "['bad', 'key']: input field must be a string"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        assert_violation(f"boundary {name}", candidate, expected)

    advice_case = golden_case()
    advice_case["inputs"]["fx_pkr_usd"]["analyst_ref"]["note"] = "you should buy this forecast"
    advice_result = engine.evaluate_case(advice_case)
    advice_text = json.dumps(advice_result, sort_keys=True).lower()
    check("analyst note advice does not leak", "you should buy" not in advice_text and "forecast" not in advice_text)

    for name, mutate, expected in (
        ("evaluate rejects top-level extra", lambda c: c.update(caller_prose="you should buy"), "case.caller_prose"),
        ("evaluate rejects huge hires", lambda c: c["inputs"]["sales_hires_schedule"]["value"].__setitem__(0, 10**400), "sales_hires_schedule[0]: must be <="),
        ("evaluate rejects integer input key", lambda c: c["inputs"].update({1: analyst(1.0)}), "1: input field must be a string"),
        ("evaluate rejects tuple input key", lambda c: c["inputs"].update({("bad", "key"): analyst(1.0)}), "('bad', 'key'): input field must be a string"),
        ("evaluate rejects list-like input key", lambda c: c.update(inputs=ListKeyInputs(c["inputs"], ["bad", "key"], analyst(1.0))), "['bad', 'key']: input field must be a string"),
    ):
        candidate = golden_case()
        mutate(candidate)
        assert_rejected_by_evaluate(name, candidate, expected)

    for name, mutate, expected in (
        ("extreme discount rate bounded", lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=1e308), "discount_rate_pct_annual: must be in (0, 100)"),
        ("extreme marketing remains finite", lambda c: c["inputs"]["marketing_spend_pkr_schedule"]["value"].__setitem__(0, 1e308), None),
        ("extreme investment remains finite", lambda c: c["inputs"]["initial_investment_pkr"].update(value=1e308), None),
        ("extreme shares remains finite", lambda c: c["inputs"]["shares_out"].update(value=1e308), None),
    ):
        candidate = golden_case()
        mutate(candidate)
        try:
            output = engine.evaluate_case(candidate)
        except ValueError as error:
            check(f"{name} fails cleanly", expected is not None and expected in str(error), str(error))
        else:
            check(f"{name} accepted only finite output", expected is None)
            for key, value in walk(output):
                if isinstance(value, float):
                    check(f"{name} finite {key}", math.isfinite(value))

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
