"""Focused checks for the sales-led case-run envelope."""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sales_expansion_case_run_adapter as adapter
import sales_expansion_case_run_contract as contract

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def must_fail(name: str, func, expected: str = "") -> None:
    try:
        func()
    except Exception as error:
        check(name, (not expected) or expected in str(error), str(error))
    else:
        raise AssertionError(f"{name}: expected failure")


def walk(value):
    if type(value) is dict:
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif type(value) is list:
        for item in value:
            yield from walk(item)


def load_authorities() -> dict:
    return adapter._load_fixed_authorities()


def retained_event(authorities: dict, symbol: str, event_id: str) -> dict:
    return next(
        row for row in authorities["company_event_ledger"]["companies"][symbol]["events"]
        if row.get("event_id") == event_id
    )


class SneakyDict(dict):
    pass


def main() -> None:
    real = adapter.build_real_case_run()
    check("real validates", contract.validate_case_run(real) == [])
    check("real blocked", real["status"] == "blocked" and real["fixture_only"] is False)
    check("real no scenarios", real["scenario_runs"] == [])
    check("real no numeric leakage", contract.numeric_output_keys(real) == [])
    check("real boundary reasons", real["blocked_reasons"] == contract.expected_real_blocked_reasons())
    check("real formal readiness blocked", real["formal_output_readiness"]["status"] == "blocked")
    check("real analogue not ready", real["analogue_readiness"]["status"] == "not_ready")
    check("real exact lineage", real["input_lineage"] == contract.expected_real_source_refs())
    check("real retained projection exact lineage", real["retained_projection"]["input_lineage"] == real["input_lineage"])
    check("real receipt bound", real["run_receipt"]["input_sha256"] == contract.sha256_json(contract.real_receipt_payload(real)))
    check("real projection receipt bound", real["run_receipt"]["retained_projection_sha256"] == contract.sha256_json(real["retained_projection"]))
    check("real output receipt empty", real["run_receipt"]["output_sha256"] == contract.sha256_json([]))
    check("real cutoff retained", real["run_receipt"]["cutoff_at"] == "2026-03-05T12:29:00+05:00")
    source_ids = {row["source_ref"]["id"] for row in real["input_lineage"]}
    check("real source ids",
          source_ids == {
              "psx:272102",
              "issuer:61d85f4626413576b676aed8",
              "issuer:ca78a4beec7f30b38e790a5e",
              "issuer_home:9fed93ec98418218bc7449c51856fa3e79c8c9edccb0443189778495bc0200e7",
          })
    for row in real["input_lineage"]:
        ref = row["source_ref"]
        check("real closed lineage row", set(row) == {"kind", "symbol", "role", "qualifies_sales_event", "no_go_reason", "source_ref"})
        check("real closed source ref", set(ref) == {
            "id", "event_id", "document_id", "url", "title", "source", "source_origin",
            "event_type", "event_date", "published_at", "retrieved_at", "page",
            "content_sha256", "evidence_sha256", "text",
        })
        check("real source hash bound", re.fullmatch(r"[0-9a-f]{64}", ref["content_sha256"] or "") is not None)
        check("real evidence hash bound", re.fullmatch(r"[0-9a-f]{64}", ref["evidence_sha256"] or "") is not None)
        check("real no promotion", row["qualifies_sales_event"] is False)
    check("BOP exact no-go",
          next(row for row in real["input_lineage"] if row["symbol"] == "BOP")["source_ref"]["page"] == 25
          and next(row for row in real["input_lineage"] if row["symbol"] == "BOP")["source_ref"]["event_date"] == "2026-03-05T12:29:00+05:00")
    check("PSO dates null",
          all(row["source_ref"]["event_date"] is None and row["source_ref"]["published_at"] is None
              for row in real["input_lineage"] if row["symbol"] == "PSO"))
    check("GAL no event", next(row for row in real["input_lineage"] if row["symbol"] == "GAL")["source_ref"]["event_id"] is None)

    with patch("pathlib.Path.open", side_effect=AssertionError("state read attempted")):
        must_fail("real reads retained state", adapter.build_real_case_run, "state read attempted")

    authorities = load_authorities()
    forged = copy.deepcopy(authorities)
    forged["source_registry"]["updated"] = "2099-01-01T00:00:00+05:00"
    forged["source_registry"]["_meta"]["build_cutoff_at"] = "2099-01-01T00:00:00Z"
    forged["source_registry"]["_meta"]["generated_at"] = "2099-01-01T00:00:00Z"
    forged["company_documents"]["_meta"]["updated"] = "2099-01-01T00:00:00+05:00"
    forged["company_event_ledger"]["_meta"]["updated"] = "2099-01-01T00:00:00+05:00"
    forged["research_index"]["_meta"]["built"] = "2099-01-01T00:00:00+05:00"
    metadata_mutated = adapter._build_real_case_run_for_test(forged)
    check("generated metadata cannot move cutoff", metadata_mutated["run_receipt"]["cutoff_at"] == real["run_receipt"]["cutoff_at"])

    for name, mutate in (
        ("BOP event id", lambda a: retained_event(a, "BOP", "evt_a51de635bed77b8329cc").__setitem__("event_id", "evt_forged")),
        ("BOP page", lambda a: retained_event(a, "BOP", "evt_a51de635bed77b8329cc")["evidence"][0].__setitem__("page", 26)),
        ("BOP content hash", lambda a: a["company_documents"]["documents"]["psx:272102"].__setitem__("content_sha256", "0" * 64)),
        ("BOP index title", lambda a: a["research_index"]["documents"]["psx:272102"].__setitem__("title", "forged")),
        ("PSO source url", lambda a: a["company_documents"]["documents"]["issuer:61d85f4626413576b676aed8"].__setitem__("source_url", "https://evil.invalid/x.pdf")),
        ("PSO event date", lambda a: retained_event(a, "PSO", "evt_2f3bfdf4a586999e66b6").__setitem__("event_date", "2026-01-01T00:00:00+05:00")),
        ("GAL hash", lambda a: a["source_registry"]["tickers"]["GAL"]["monitored_pages"][0].__setitem__("content_sha256", "0" * 64)),
        ("top unknown", lambda a: a["source_registry"].__setitem__("extra", True)),
    ):
        forged = copy.deepcopy(authorities)
        mutate(forged)
        must_fail(f"retained mutation rejected {name}", lambda forged=forged: adapter._build_real_case_run_for_test(forged), "retained sales")

    fixture = adapter.build_fixture_case_run()
    check("fixture validates", contract.validate_case_run(fixture) == [])
    check("fixture status", fixture["status"] == "computed_fixture" and fixture["fixture_only"] is True)
    check("fixture three scenarios", [r["scenario"] for r in fixture["scenario_runs"]] == ["bear", "base", "bull"])
    check("fixture computed", all(r["status"] == "computed" and r["result"]["status"] == "computed" for r in fixture["scenario_runs"]))
    check("fixture nonauthoritative", fixture["policy"]["fixture_non_authoritative"] is True and fixture["formal_output_readiness"]["status"] == "not_ready")
    check("fixture cutoff", fixture["run_receipt"]["cutoff_at"] == "2025-12-31T00:00:00+05:00")
    check("fixture input receipt", fixture["run_receipt"]["input_sha256"] == contract.sha256_json([r["case"] for r in fixture["scenario_runs"]]))
    check("fixture output receipt", fixture["run_receipt"]["output_sha256"] == contract.sha256_json([r["result"] for r in fixture["scenario_runs"]]))
    check("fixture retained receipt null", fixture["run_receipt"]["retained_projection_sha256"] == contract.sha256_json(None))
    repeat = adapter.build_fixture_case_run()
    check("fixture deterministic", json.dumps(fixture, sort_keys=True) == json.dumps(repeat, sort_keys=True))
    check("fixture isolated", fixture is not repeat and fixture["scenario_runs"] is not repeat["scenario_runs"])

    for label, payload in (("real", real), ("fixture", fixture)):
        text = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text) is None)
        for key, value in walk(payload):
            if type(value) is float:
                check(f"{label} finite {key}", math.isfinite(value))

    forged = copy.deepcopy(real)
    forged["blocked_reasons"].append("forged")
    check("forged real reasons rejected", bool(contract.validate_case_run(forged)))
    forged = copy.deepcopy(real)
    forged["retained_projection"]["cutoff_at"] = "2099-01-01T00:00:00+05:00"
    forged["run_receipt"]["cutoff_at"] = forged["retained_projection"]["cutoff_at"]
    forged["run_receipt"]["input_sha256"] = contract.sha256_json(contract.real_receipt_payload(forged))
    forged["run_receipt"]["retained_projection_sha256"] = contract.sha256_json(forged["retained_projection"])
    check("forged retained cutoff rejected despite recomputed receipt", bool(contract.validate_case_run(forged)))
    for field, value in (
        ("unexpected", {"note": "forged"}),
        ("values", {"npv_pkr": 1.0}),
        ("lifecycle", {"stage": "selected"}),
        ("output", {"status": "computed"}),
    ):
        forged = copy.deepcopy(real)
        forged["retained_projection"]["derivation"][field] = value
        forged["run_receipt"]["input_sha256"] = contract.sha256_json(contract.real_receipt_payload(forged))
        forged["run_receipt"]["retained_projection_sha256"] = contract.sha256_json(forged["retained_projection"])
        check(f"forged retained nested {field} rejected despite recomputed receipt", bool(contract.validate_case_run(forged)))
    forged = copy.deepcopy(real)
    forged["input_lineage"][0]["source_ref"]["id"] = "psx:999999"
    forged["retained_projection"]["input_lineage"][0]["source_ref"]["id"] = "psx:999999"
    forged["run_receipt"]["input_sha256"] = contract.sha256_json(contract.real_receipt_payload(forged))
    forged["run_receipt"]["retained_projection_sha256"] = contract.sha256_json(forged["retained_projection"])
    check("forged real source rejected despite recomputed receipt", bool(contract.validate_case_run(forged)))
    for field, value in (
        ("url", "https://evil.invalid/doc.pdf"),
        ("page", 99),
        ("content_sha256", "0" * 64),
        ("evidence_sha256", "1" * 64),
        ("text", "forged retained text"),
        ("event_date", "2024-01-01T00:00:00+05:00"),
        ("published_at", "2024-01-01T00:00:00+05:00"),
    ):
        forged = copy.deepcopy(real)
        forged["input_lineage"][0]["source_ref"][field] = value
        forged["retained_projection"]["input_lineage"][0]["source_ref"][field] = value
        forged["run_receipt"]["input_sha256"] = contract.sha256_json(contract.real_receipt_payload(forged))
        forged["run_receipt"]["retained_projection_sha256"] = contract.sha256_json(forged["retained_projection"])
        check(f"forged real {field} rejected", bool(contract.validate_case_run(forged)))
    forged = copy.deepcopy(fixture)
    forged["scenario_runs"][0]["result"]["values"]["npv_pkr"] = 0.0
    check("forged fixture arithmetic rejected", bool(contract.validate_case_run(forged)))
    forged = copy.deepcopy(fixture)
    forged["run_receipt"]["output_sha256"] = "0" * 64
    check("forged fixture receipt rejected", bool(contract.validate_case_run(forged)))
    forged = copy.deepcopy(fixture)
    forged["scenario_runs"][0]["case"]["valuation_date"] = "2030-01-01"
    check("fixture lookahead rejected", bool(contract.validate_case_run(forged)))
    forged = copy.deepcopy(fixture)
    forged["fixture_only"] = False
    forged["status"] = "blocked"
    forged["fixture_identity"] = None
    check("fixture relabel rejected", bool(contract.validate_case_run(forged)))

    original_case_id = contract.CASE_ID
    original_symbol = contract.FIXTURE_SYMBOL
    try:
        contract.CASE_ID = "case_forged_sales_selected"
        contract.FIXTURE_SYMBOL = "FORGED"
        mutated_real = adapter.build_real_case_run()
        check("global case id injection ignored by adapter", mutated_real["case_id"] == "case_sales_expansion_unselected_v1")
        check("global case id injection rejected by validator", contract.validate_case_run(mutated_real) == [])
        mutated_fixture = adapter.build_fixture_case_run()
        check("global fixture symbol injection ignored", mutated_fixture["scenario_runs"][0]["case"]["symbol"] == "SALES-FIXTURE")
        check("global fixture symbol injection validates literal", contract.validate_case_run(mutated_fixture) == [])
    finally:
        contract.CASE_ID = original_case_id
        contract.FIXTURE_SYMBOL = original_symbol

    original_expected_sources = contract.expected_real_source_refs
    original_expected_reasons = contract.expected_real_blocked_reasons
    original_receipt_payload = contract.real_receipt_payload
    original_adapter_fixture_identity = adapter._fixture_identity
    try:
        forged_lineage = copy.deepcopy(real["input_lineage"])
        forged_lineage[0]["source_ref"]["id"] = "psx:forged"
        contract.expected_real_source_refs = lambda: forged_lineage
        contract.expected_real_blocked_reasons = lambda: ["forged:selected"]
        contract.real_receipt_payload = lambda envelope: {"caller_state": "forged"}
        forged = copy.deepcopy(real)
        forged["input_lineage"] = forged_lineage
        forged["retained_projection"]["input_lineage"] = forged_lineage
        forged["blocked_reasons"] = ["forged:selected"]
        forged["retained_projection"]["blocked_reasons"] = ["forged:selected"]
        forged["run_receipt"]["input_sha256"] = contract.sha256_json({"caller_state": "forged"})
        forged["run_receipt"]["retained_projection_sha256"] = contract.sha256_json(forged["retained_projection"])
        check("contract helper relabel rejected", bool(contract.validate_case_run(forged)))
        adapter._fixture_identity = lambda: {
            "symbol": "FORGED",
            "event_ref": "fixture:sales-expansion-v1",
            "effective_date": "2025-12-31",
            "valuation_date": "2025-12-31",
            "cutoff_at": "2025-12-31T00:00:00+05:00",
        }
        must_fail("adapter fixture helper relabel rejected", adapter.build_fixture_case_run, "contract violation")
    finally:
        contract.expected_real_source_refs = original_expected_sources
        contract.expected_real_blocked_reasons = original_expected_reasons
        contract.real_receipt_payload = original_receipt_payload
        adapter._fixture_identity = original_adapter_fixture_identity

    cycle = copy.deepcopy(real)
    cycle["input_lineage"].append(cycle)
    check("cycle deterministic violation", "cyclic JSON object is forbidden" in "; ".join(contract.validate_case_run(cycle)))
    deep = {}
    cursor = deep
    for _ in range(60):
        cursor["x"] = {}
        cursor = cursor["x"]
    check("deep deterministic violation", bool(contract.validate_case_run(deep)))
    wide = {"items": [None] * 20_100}
    check("volume deterministic violation", bool(contract.validate_case_run(wide)))
    sneaky = SneakyDict(real)
    check("dict subclass rejected", "not SneakyDict" in "; ".join(contract.validate_case_run(sneaky)))
    bad = copy.deepcopy(fixture)
    bad["scenario_runs"][0]["case"]["inputs"]["starting_revenue_pkr"]["value"] = float("nan")
    check("NaN rejected", bool(contract.validate_case_run(bad)))
    bad = copy.deepcopy(fixture)
    bad["scenario_runs"][0]["case"]["inputs"]["starting_revenue_pkr"]["value"] = float("inf")
    check("Inf rejected", bool(contract.validate_case_run(bad)))
    bad = copy.deepcopy(fixture)
    bad["scenario_runs"][0]["case"]["inputs"]["starting_revenue_pkr"]["value"] = True
    check("bool numeric rejected", bool(contract.validate_case_run(bad)))
    # Integer magnitude is bounded before any canonical JSON or receipt hash;
    # both nested containers and the exact boundary are covered here.
    projected, projection_errors = contract.safe_json_projection(
        {"nested": [contract.MAX_ABS_INTEGER, {"ok": -contract.MAX_ABS_INTEGER}]}
    )
    check("integer boundary remains valid", not projection_errors and projected["nested"][0] == contract.MAX_ABS_INTEGER)
    giant = copy.deepcopy(real)
    giant["retained_projection"]["derivation"]["huge"] = 10**100000
    try:
        giant_errors = contract.validate_case_run(giant)
    except Exception as error:
        raise AssertionError(f"giant integer raised: {error}")
    check("giant integer rejected without raising", bool(giant_errors) and any("integer exceeds magnitude limit" in item for item in giant_errors))
    class SneakyList(list):
        pass
    list_alias = copy.deepcopy(real)
    list_alias["input_lineage"] = SneakyList(list_alias["input_lineage"])
    check("list subclass rejected", bool(contract.validate_case_run(list_alias)))

    source = Path(adapter.__file__).read_text(encoding="utf-8").lower()
    check("adapter no writer/network symbols", not any(token in source for token in ("save_json", "requests", "urllib", "httpx")))
    print(f"sales expansion case-run adapter: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
