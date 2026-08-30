"""Focused checks for the MLCF/PIOC case-run adapter lane."""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mlcf_pioc_case_run_adapter as adapter
from mlcf_pioc_case_run_contract import CASE_ID, SCENARIOS, numeric_output_keys, validate_case_run

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def _real_inputs() -> tuple[dict, dict]:
    intelligence = json.loads((ROOT / "state/company_intel/intelligence_cases.json").read_text(encoding="utf-8"))
    readiness = json.loads((ROOT / "state/company_intel/mlcf_pioc_readiness_manifest.json").read_text(encoding="utf-8"))
    case = next(row for row in intelligence["companies"]["MLCF"]["cases"] if row.get("case_id") == CASE_ID)
    manifest = readiness["companies"]["MLCF"]["manifest"]
    return case, manifest


def main() -> None:
    check("case id", CASE_ID == "case_mlcf_pioc_control_observed_v1")
    check("three scenarios", SCENARIOS == ("bear", "base", "bull"))

    case, manifest = _real_inputs()
    real = adapter.build_real_case_run(case, manifest)
    check("real validates", validate_case_run(real) == [])
    check("real blocked", real["status"] == "blocked")
    check("real case id", real["case_id"] == CASE_ID)
    check("real no scenario objects", real["scenario_runs"] == [])
    check("real has exact current blockers", "pioc_retained_official_financial_documents:missing" in real["blocked_reasons"]
          and "mlcf_full_financial_truth_gate:missing" in real["blocked_reasons"])
    check("real has evidence lineage", all(row.get("kind") == "evidence" for row in real["input_lineage"]))
    check("real no numeric payload", not numeric_output_keys(real))
    check("real formal hard block", real["formal_output_readiness"]["status"] == "blocked"
          and real["formal_output_readiness"]["hard_block"])
    check("real analogue exact not ready", real["analogue_readiness"]["status"] == "not_ready"
          and real["analogue_readiness"]["hard_block"])
    check("real formal reasons authoritative", real["formal_output_readiness"]["blocked_reasons"] == real["blocked_reasons"]
          and real["formal_output_readiness"]["reason"] == real["blocked_reasons"][0])
    for row in real["input_lineage"]:
        ref = row.get("source_ref") or {}
        check("real lineage closed full evidence ref",
              set(row) == {"kind", "document_id", "source_ref"}
              and set(ref) == {"event_id", "document_id", "document_title", "document_published_at",
                               "document_retrieved_at", "content_sha256", "source", "source_url",
                               "page", "text"}
              and row.get("document_id") == ref.get("document_id")
              and re.fullmatch(r"[0-9a-f]{64}", str(ref.get("content_sha256") or ""), re.I) is not None
              and isinstance(ref.get("page"), int) and ref.get("page") > 0
              and bool(ref.get("text")))
    try:
        no_lineage_case = copy.deepcopy(case)
        no_lineage_case.pop("source_lineage", None)
        adapter.build_real_case_run(no_lineage_case, {"status": "blocked_missing_inputs"})
    except ValueError as error:
        check("missing lineage fails closed", "without exact source lineage" in str(error))
    else:
        raise AssertionError("missing lineage should fail closed")

    fixture = adapter.build_fixture_case_run()
    check("fixture validates", validate_case_run(fixture) == [])
    check("fixture computed", fixture["status"] == "computed")
    check("fixture three computed runs", [r["scenario"] for r in fixture["scenario_runs"]] == list(SCENARIOS)
          and all(r["status"] == "computed" and r["result"]["status"] == "computed" for r in fixture["scenario_runs"]))
    check("fixture eight-quarter schedules", all(len(r["result"]["quarterly_schedule"]) == 8 for r in fixture["scenario_runs"]))
    check("fixture is unmistakably synthetic", fixture["formal_output_readiness"]["status"] == "not_ready"
          and "synthetic_fixture_not_formal_output" in fixture["formal_output_readiness"]["blocked_reasons"]
          and all(r["result"]["scenario"]["symbol"] == "MLCF-FIXTURE" for r in fixture["scenario_runs"]))
    check("fixture analogue exact not ready", fixture["analogue_readiness"]["status"] == "not_ready"
          and fixture["analogue_readiness"]["hard_block"])

    one_row = copy.deepcopy(fixture)
    one_row["scenario_runs"][0]["result"]["quarterly_schedule"] = one_row["scenario_runs"][0]["result"]["quarterly_schedule"][:1]
    check("nested one-row schedule rejected", any("exactly 8 rows" in x for x in validate_case_run(one_row)))
    mismatched = copy.deepcopy(fixture)
    mismatched["scenario_runs"][0]["result"]["scenario"]["case_label"] = "bull"
    check("nested scenario mismatch rejected", any("fixture identity" in x for x in validate_case_run(mismatched)))
    for path in (("values", "invented"), ("per_share", "invented"), ("quarterly_schedule", 0, "invented")):
        mutated = copy.deepcopy(fixture)
        if path[0] == "quarterly_schedule":
            mutated["scenario_runs"][0]["result"][path[0]][path[1]][path[2]] = 1
        else:
            mutated["scenario_runs"][0]["result"][path[0]][path[1]] = 1
        check(f"adversarial invented {path[0]}", bool(validate_case_run(mutated)))
    empty = copy.deepcopy(fixture); empty["scenario_runs"][0]["result"]["values"] = {}
    check("adversarial empty values", bool(validate_case_run(empty)))
    empty = copy.deepcopy(fixture); empty["scenario_runs"][0]["result"]["per_share"] = {}
    check("adversarial empty per-share", bool(validate_case_run(empty)))
    no_reasons = copy.deepcopy(fixture); no_reasons["scenario_runs"][0]["blocked_reasons"] = ["oops"]
    check("computed run blocked reasons rejected", bool(validate_case_run(no_reasons)))
    mutations = [
        ("computed formula_id mutation", lambda x: x["scenario_runs"][0]["result"].__setitem__("formula_id", "forged")),
        ("computed engine_version mutation", lambda x: x["scenario_runs"][0]["result"].__setitem__("engine_version", "forged")),
        ("computed receipt hash mutation", lambda x: x["scenario_runs"][0]["result"]["run_receipt"].__setitem__("inputs_sha256", "0" * 64)),
        ("computed scenario symbol mutation", lambda x: x["scenario_runs"][0]["result"]["scenario"].__setitem__("symbol", "EVIL")),
        ("computed scenario event mutation", lambda x: x["scenario_runs"][0]["result"]["scenario"].__setitem__("event_ref", "evil:event")),
        ("computed effective date mutation", lambda x: x["scenario_runs"][0]["result"]["scenario"].__setitem__("effective_date", "2030-12-31")),
        ("computed valuation date mutation", lambda x: x["scenario_runs"][0]["result"]["scenario"].__setitem__("valuation_date", "2020-12-31")),
        ("computed quarter non-quarter-end", lambda x: x["scenario_runs"][0]["result"]["quarterly_schedule"][0].__setitem__("quarter_end", "2026-01-01")),
        ("computed quarter out of order", lambda x: x["scenario_runs"][0]["result"]["quarterly_schedule"][1].__setitem__("quarter_end", "2025-12-31")),
        ("computed source ref incomplete", lambda x: (
            x["scenario_runs"][0]["result"]["inputs_lineage"][0].__setitem__("label_type", "source"),
            x["scenario_runs"][0]["result"]["inputs_lineage"][0].__setitem__("source_ref", {"id": "x"}),
            x["scenario_runs"][0]["result"]["inputs_lineage"][0].pop("analyst_ref", None),
        )),
        ("computed analyst ref incomplete", lambda x: x["scenario_runs"][0]["result"]["inputs_lineage"][0].__setitem__("analyst_ref", {"note_id": "x"})),
        ("computed lineage wrong value type", lambda x: x["scenario_runs"][0]["result"]["inputs_lineage"][0].__setitem__("value", {"forged": "object"})),
        ("computed wrong aggregate", lambda x: x["scenario_runs"][0]["result"]["values"].__setitem__("npv_pkr", 123.0)),
        ("computed wrong per share", lambda x: x["scenario_runs"][0]["result"]["per_share"].__setitem__("npv_pkr", 123.0)),
        ("computed wrong row arithmetic", lambda x: x["scenario_runs"][0]["result"]["quarterly_schedule"][0].__setitem__("revenue_pkr", 123.0)),
        ("fixture formal readiness ready", lambda x: x["formal_output_readiness"].__setitem__("status", "ready")),
        ("fixture analogue readiness ready", lambda x: x["analogue_readiness"].__setitem__("status", "ready")),
    ]
    for name, mutate in mutations:
        mutated = copy.deepcopy(fixture)
        mutate(mutated)
        check(f"adversarial {name}", bool(validate_case_run(mutated)))
    real_mutations = [
        ("real formal readiness ready", lambda x: x["formal_output_readiness"].__setitem__("status", "ready")),
        ("real formal readiness not_ready", lambda x: x["formal_output_readiness"].__setitem__("status", "not_ready")),
        ("real formal reasons diverge", lambda x: x["formal_output_readiness"].__setitem__("blocked_reasons", ["synthetic"])),
        ("real analogue readiness ready", lambda x: x["analogue_readiness"].__setitem__("status", "ready")),
        ("real input lineage document id only", lambda x: x.__setitem__("input_lineage", [{"kind": "evidence", "document_id": "psx:267429"}])),
        ("real input lineage unknown source ref", lambda x: x["input_lineage"][0].__setitem__("source_ref", {"id": "x"})),
        ("real input lineage source ref removed", lambda x: x["input_lineage"][0].pop("source_ref", None)),
        ("real input lineage hash removed", lambda x: x["input_lineage"][0]["source_ref"].pop("content_sha256", None)),
        ("real input lineage text removed", lambda x: x["input_lineage"][0]["source_ref"].pop("text", None)),
        ("real input lineage page bool", lambda x: x["input_lineage"][0]["source_ref"].__setitem__("page", True)),
    ]
    for name, mutate in real_mutations:
        mutated = copy.deepcopy(real)
        mutate(mutated)
        check(f"adversarial {name}", bool(validate_case_run(mutated)))

    repeat = adapter.build_fixture_case_run()
    check("fixture deterministic", json.dumps(fixture, sort_keys=True) == json.dumps(repeat, sort_keys=True))
    for label, payload in (("real", real), ("fixture", fixture)):
        text = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text) is None)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))

    # Contract boundaries: unknown economic fields, future availability and
    # non-finite values are rejected by the underlying cement contract.
    bad = copy.deepcopy(adapter._fixture_case("base"))
    bad["inputs"]["unknown_economic_field"] = bad["inputs"]["debt_financing_pkr"]
    check("unknown economic field rejected", any("unknown input field" in x for x in __import__("cement_expansion_contract").validate_case(bad)))
    bad = copy.deepcopy(adapter._fixture_case("base"))
    bad["inputs"]["debt_financing_pkr"]["value"] = float("nan")
    check("nonfinite rejected", any("finite number" in x for x in __import__("cement_expansion_contract").validate_case(bad)))
    print(f"mlcf pioc case-run adapter: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
