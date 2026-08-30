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
from mlcf_pioc_case_run_contract import (
    CASE_ID,
    SCENARIOS,
    numeric_output_keys,
    retained_real_source_lineage,
    validate_cement_input_readiness,
    validate_case_run,
)

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


def must_fail(name: str, func, expected: str = "") -> None:
    try:
        func()
    except ValueError as error:
        check(name, (not expected) or expected in str(error), str(error))
    else:
        raise AssertionError(f"{name}: expected ValueError")


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
    bound_lineage, lineage_violations = retained_real_source_lineage(case, manifest)
    check("retained source lineage binds", not lineage_violations and len(bound_lineage) == 2)
    check("retained source lineage exact order", [row["document_id"] for row in bound_lineage] == ["psx:267429", "psx:275425"])
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
    # Every readiness seam is hostile-tested: the adapter must bind to the
    # current producer build, while the contract independently rejects drift.
    readiness_mutations = [
        ("top unknown", lambda r: r.__setitem__("unknown", True)),
        ("top missing", lambda r: r.pop("status")),
        ("status", lambda r: r.__setitem__("status", "ready")),
        ("kernel activation", lambda r: r.__setitem__("kernel_activation", "ready")),
        ("attribution value", lambda r: r["attribution"].__setitem__("target", "EVIL")),
        ("attribution unknown", lambda r: r["attribution"].__setitem__("extra", True)),
        ("attribution missing", lambda r: r["attribution"].pop("target")),
        ("source join order", lambda r: r.__setitem__("source_join", list(reversed(r["source_join"]))),),
        ("source join count", lambda r: r["source_join"].pop()),
        ("source join nonmapping", lambda r: r["source_join"].__setitem__(0, "bad")),
        ("source join role", lambda r: r["source_join"][0].__setitem__("role", "bad")),
        ("source join canonical", lambda r: r["source_join"][0].__setitem__("canonical_event_id", "bad")),
        ("source join binding", lambda r: r["source_join"][0].__setitem__("canonical_event_id_binding", "bad")),
        ("source join legacy", lambda r: r["source_join"][0].__setitem__("legacy_event_id", "bad")),
        ("source join document", lambda r: r["source_join"][0].__setitem__("document_id", "bad")),
        ("source join page", lambda r: r["source_join"][0].__setitem__("page", True)),
        ("source join content hash", lambda r: r["source_join"][0].__setitem__("content_sha256", "0" * 64)),
        ("source join evidence hash", lambda r: r["source_join"][0].__setitem__("evidence_sha256", "0" * 64)),
        ("source join published", lambda r: r["source_join"][0].__setitem__("published_at", "bad")),
        ("source join effective", lambda r: r["source_join"][0].__setitem__("effective_date", "bad")),
        ("source join available", lambda r: r["source_join"][0].__setitem__("available_on", "bad")),
        ("counter unknown", lambda r: r["financial_truth_counters"].__setitem__("extra", {})),
        ("counter missing", lambda r: r["financial_truth_counters"].pop("annual_income_triplets")),
        ("counter nonmapping", lambda r: r["financial_truth_counters"].__setitem__("annual_income_triplets", [])),
        ("counter required", lambda r: r["financial_truth_counters"]["annual_income_triplets"].__setitem__("required", "5")),
        ("counter present", lambda r: r["financial_truth_counters"]["annual_income_triplets"].__setitem__("present", 9)),
        ("counter periods", lambda r: r["financial_truth_counters"]["annual_income_triplets"].__setitem__("qualified_periods", ["bad"])),
        ("share status", lambda r: r["financial_truth_counters"]["share_count"].__setitem__("status", "ready")),
        ("share available", lambda r: r["financial_truth_counters"]["share_count"].__setitem__("available_on", "2026-01-01")),
        ("share source", lambda r: r["financial_truth_counters"]["share_count"].__setitem__("source", "manual")),
        ("requirement unknown", lambda r: r["event_specific_kernel_requirements"].__setitem__("extra", {})),
        ("requirement missing", lambda r: r["event_specific_kernel_requirements"].pop("incremental_revenue_pkr")),
        ("requirement nonmapping", lambda r: r["event_specific_kernel_requirements"].__setitem__("incremental_revenue_pkr", [])),
        ("requirement value", lambda r: r["event_specific_kernel_requirements"]["incremental_revenue_pkr"].__setitem__("value", 1)),
        ("requirement source label", lambda r: r["event_specific_kernel_requirements"]["incremental_revenue_pkr"].__setitem__("source_label", "manual")),
        ("requirement status", lambda r: r["event_specific_kernel_requirements"]["incremental_revenue_pkr"].__setitem__("status", "ready")),
        ("guardrails unknown", lambda r: r["guardrails"].__setitem__("extra", True)),
        ("guardrails missing", lambda r: r["guardrails"].pop("no_numeric_model_output")),
        ("guardrail value", lambda r: r["guardrails"].__setitem__("no_numeric_model_output", False)),
    ]
    for name, mutate in readiness_mutations:
        forged = copy.deepcopy(case)
        mutate(forged["cement_input_readiness"])
        check(f"readiness contract {name}", bool(validate_cement_input_readiness(forged["cement_input_readiness"])))
        must_fail(f"readiness adapter {name}", lambda forged=forged: adapter.build_real_case_run(forged, manifest), "without exact retained source lineage")
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
    check("real lineage equals retained binding", real["input_lineage"] == bound_lineage)
    try:
        no_lineage_case = copy.deepcopy(case)
        no_lineage_case.pop("source_lineage", None)
        adapter.build_real_case_run(no_lineage_case, {"status": "blocked_missing_inputs"})
    except ValueError as error:
        check("missing lineage fails closed", "without exact retained source lineage" in str(error))
    else:
        raise AssertionError("missing lineage should fail closed")
    for field, value in (
        ("document_id", "psx:999999"),
        ("event_id", "evt_forged"),
        ("document_title", "Forged retained-looking title"),
        ("document_published_at", "2024-01-01T00:00:00+05:00"),
        ("document_retrieved_at", "2024-01-02T00:00:00+05:00"),
        ("content_sha256", "0" * 64),
        ("source", "Forged Source"),
        ("source_url", "https://dps.psx.com.pk/download/document/999999.pdf"),
        ("page", 99),
        ("text", "forged retained-evidence-looking text"),
    ):
        forged = copy.deepcopy(case)
        forged["source_lineage"][0][field] = value
        if field == "document_id":
            forged["source_lineage"][0]["document_id"] = value
        must_fail(f"forged source_lineage {field} rejected",
                  lambda forged=forged: adapter.build_real_case_run(forged, manifest),
                  "exact retained source lineage")
    for field, value in (
        ("event_id", "evt_forged"),
        ("document_id", "psx:999999"),
        ("document_title", "Forged retained-looking title"),
        ("document_published_at", "2024-01-01T00:00:00+05:00"),
        ("document_retrieved_at", "2024-01-02T00:00:00+05:00"),
        ("content_sha256", "0" * 64),
        ("source", "Forged Source"),
        ("source_url", "https://dps.psx.com.pk/download/document/999999.pdf"),
        ("page", 99),
        ("text", "forged retained-evidence-looking text"),
    ):
        forged = copy.deepcopy(case)
        forged["observed_facts"][0]["evidence"][0][field] = value
        if field == "event_id":
            forged["observed_facts"][0]["source_event_id"] = value
        if field == "document_id":
            forged["observed_facts"][0]["document_id"] = value
        if field == "document_published_at":
            forged["observed_facts"][0]["event_date"] = value
        must_fail(f"forged observed_facts evidence {field} rejected",
                  lambda forged=forged: adapter.build_real_case_run(forged, manifest),
                  "exact retained source lineage")
    for field, value in (
        ("event_id", "evt_forged"),
        ("document_id", "psx:999999"),
        ("document_title", "Forged retained-looking title"),
        ("document_published_at", "2024-01-01T00:00:00+05:00"),
        ("document_retrieved_at", "2024-01-02T00:00:00+05:00"),
        ("content_sha256", "0" * 64),
        ("source", "Forged Source"),
        ("source_url", "https://dps.psx.com.pk/download/document/999999.pdf"),
        ("page", 99),
    ):
        forged_manifest = copy.deepcopy(manifest)
        forged_manifest["evidence_refs"][0][field] = value
        must_fail(f"forged manifest evidence_refs {field} rejected",
                  lambda forged_manifest=forged_manifest: adapter.build_real_case_run(case, forged_manifest),
                  "exact retained source lineage")
    for path_name, mutate in (
        ("case target symbol", lambda x: x.__setitem__("target_symbol", "EVIL")),
        ("case status", lambda x: x.__setitem__("status", "Modelled")),
        ("case family", lambda x: x.__setitem__("case_family", "evil")),
        ("manifest target symbol", lambda x: x.__setitem__("target_symbol", "EVIL")),
        ("manifest status", lambda x: x.__setitem__("status", "ready")),
        ("manifest pilot status", lambda x: x["pilot_status"].__setitem__("in_current_ci_pilot", True)),
        ("manifest known field", lambda x: x["known_fields"].__setitem__("offer_price", "PKR 1.00 per share")),
        ("manifest missing input status", lambda x: x["missing_inputs"][0].__setitem__("status", "ready")),
        ("manifest output policy", lambda x: x["formal_output_policy"].__setitem__("accepted_outputs", ["valuation"])),
    ):
        forged_case = copy.deepcopy(case)
        forged_manifest = copy.deepcopy(manifest)
        target = forged_manifest if path_name.startswith("manifest") else forged_case
        mutate(target)
        must_fail(f"forged real {path_name} rejected",
                  lambda forged_case=forged_case, forged_manifest=forged_manifest: adapter.build_real_case_run(forged_case, forged_manifest),
                  "exact retained source lineage")
    closed_case = copy.deepcopy(case)
    closed_case["unexpected"] = True
    must_fail("real case unknown top-level field rejected",
              lambda: adapter.build_real_case_run(closed_case, manifest),
              "exact retained source lineage")
    closed_manifest = copy.deepcopy(manifest)
    closed_manifest["evidence_refs"][0]["unexpected"] = True
    must_fail("real manifest nested unknown field rejected",
              lambda: adapter.build_real_case_run(case, closed_manifest),
              "exact retained source lineage")
    path_case = copy.deepcopy(case)
    path_case["source_lineage"][0].pop("source_url", None)
    path_case["source_lineage"][0]["path"] = "forged/local.pdf"
    must_fail("real source_lineage path substitution rejected",
              lambda: adapter.build_real_case_run(path_case, manifest),
              "exact retained source lineage")
    dated_case = copy.deepcopy(case)
    dated_case["source_lineage"][0]["available_on"] = "2024-01-01"
    dated_case["source_lineage"][0]["effective_date"] = "2024-01-01"
    must_fail("real source_lineage extra date fields rejected",
              lambda: adapter.build_real_case_run(dated_case, manifest),
              "exact retained source lineage")
    consistent_fake_case = copy.deepcopy(case)
    consistent_fake_manifest = copy.deepcopy(manifest)
    consistent_fake_case["observed_facts"][0]["evidence"][0]["content_sha256"] = "0" * 64
    consistent_fake_case["source_lineage"][0]["content_sha256"] = "0" * 64
    consistent_fake_manifest["evidence_refs"][0]["content_sha256"] = "0" * 64
    must_fail("consistent fake retained chain rejected",
              lambda: adapter.build_real_case_run(consistent_fake_case, consistent_fake_manifest),
              "exact retained source lineage")
    forged_envelope = copy.deepcopy(real)
    forged_envelope["input_lineage"][0]["source_ref"]["document_id"] = "psx:999999"
    forged_envelope["input_lineage"][0]["document_id"] = "psx:999999"
    check("direct forged real envelope rejected", any("retained MLCF/PIOC" in x or "source chain hash" in x for x in validate_case_run(forged_envelope)))

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
