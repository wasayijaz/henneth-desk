#!/usr/bin/env python3
"""Read-only contract checks for the two deterministic observed case payloads."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ci_slice import _intelligence_case_row, build as build_slice
import build_intelligence_cases as case_builder
from build_intelligence_cases import (
    FOLLOW_THROUGH_DOC_ID,
    FOLLOW_THROUGH_EVENT_ID,
    MARI_CASE_ID,
    MARI_SALES_CASE_ID,
    MARI_DOC_HASH,
    MARI_DOC_ID,
    MARI_EVENT_ID,
    MLCF_CASE_ID,
    PSO_CANONICAL_EVENT_ID,
    PSO_CASE_ID,
    PSO_CONTENT_SHA256,
    PSO_DOC_ID,
    PSO_EFFECTIVE_DATE,
    PSO_KERNEL_FIELDS,
    PSO_PUBLISHED_AT,
    PSO_SOURCE_URL,
    PUBLIC_OFFER_DOC_ID,
    PUBLIC_OFFER_EVENT_ID,
    build as build_cases,
)
from psx_data import ROOT, STATE, load_json


OUT = STATE / "company_intel" / "intelligence_cases.json"
SLICE_OUT = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
CONFIDENCE_OUT = STATE / "company_intel" / "intelligence_confidence.json"
WATCHLIST_OUT = STATE / "company_intel" / "evidence_watchlist.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
FORBIDDEN_KEYS = {"forecast", "valuation", "market_expectations", "price_target", "target_price", "recommendation", "probability", "expected_return"}
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        raise AssertionError(message)


def walk(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def snapshot(paths: list[Path]) -> dict[str, tuple[bool, str | None]]:
    result = {}
    for path in paths:
        if not path.exists():
            result[str(path)] = (False, None)
            continue
        result[str(path)] = (True, hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def without_root_meta(value: dict) -> dict:
    """Compare deterministic case content independently of the final build envelope."""
    return {key: item for key, item in value.items() if key != "_meta"}


def assert_evidence(ref: dict, event_id: str, document_id: str, page: int, content_hash: str) -> None:
    check(ref.get("event_id") == event_id, f"event mismatch: {ref.get('event_id')}")
    check(ref.get("document_id") == document_id, f"document mismatch: {ref.get('document_id')}")
    check(ref.get("page") == page, f"page mismatch for {document_id}")
    check(ref.get("content_sha256") == content_hash and HEX64.fullmatch(str(ref.get("content_sha256") or "")), f"hash mismatch for {document_id}")
    check(str(ref.get("source_url") or "").startswith("https://dps.psx.com.pk/download/document/"), f"non-PSX URL for {document_id}")
    check(bool(ref.get("text")) and ref.get("event_date") and ref.get("document_published_at"), f"incomplete evidence for {document_id}")


def hostile_case_result(symbol: str, case_fn, ledger: dict, documents: dict, operating_events: dict):
    try:
        result = case_fn(ledger, documents, operating_events) if symbol == "MLCF" else case_fn(ledger, documents)
    except ValueError:
        return None
    return result[0]


def main() -> None:
    watched = [OUT, SLICE_OUT]
    before = snapshot(watched)
    first = build_cases(write=False)
    second = build_cases(write=False)
    check(json.dumps(first, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(second, sort_keys=True, ensure_ascii=False, allow_nan=False), "case builder is not deterministic")
    check(first["summary"] == {"company_count": 20, "observed_case_count": 4, "published_case_count": 0}, "case summary mismatch")
    check(set(first["companies"]) == set(first["pilot_symbols"]) and len(first["pilot_symbols"]) == 20, "pilot boundary mismatch")
    check(first["selected_symbols"] == ["MARI", "MLCF", "PSO"], "selected symbol boundary mismatch")
    check(first["status_lifecycle"] == ["Observed", "Corroborated", "Modelled", "Validated", "Published", "Monitoring", "Closed"], "lifecycle vocabulary mismatch")

    mlcf = first["companies"]["MLCF"]["cases"][0]
    check(first["companies"]["MLCF"]["symbol"] == "MLCF" and mlcf["case_id"] == MLCF_CASE_ID, "MLCF identity mismatch")
    check(mlcf["status"] == "Observed" and mlcf["epistemic_type"] == "reported_fact", "MLCF lifecycle/epistemic mismatch")
    facts = {item["fact_id"]: item for item in mlcf["observed_facts"]}
    check(set(facts) == {"mlcf_pioc_public_offer_control", "mlcf_pioc_dispatch_inclusion"}, "MLCF fact set mismatch")
    values = {item["label"]: item["value"] for item in facts["mlcf_pioc_public_offer_control"]["reported_values"]}
    check(values == {"public_offer_shares": "up to 26,623,096 PIOC shares", "public_offer_percent": "11.72% shares", "spa_percent": "58.03% through Share Purchase Agreement(s)", "offer_price": "PKR 478.43 per share"}, "MLCF reported values mismatch")
    assert_evidence(facts["mlcf_pioc_public_offer_control"]["evidence"][0], PUBLIC_OFFER_EVENT_ID, PUBLIC_OFFER_DOC_ID, 3, "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54")
    assert_evidence(facts["mlcf_pioc_dispatch_inclusion"]["evidence"][0], FOLLOW_THROUGH_EVENT_ID, FOLLOW_THROUGH_DOC_ID, 4, "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f")

    mari = first["companies"]["MARI"]["cases"][0]
    check(first["companies"]["MARI"]["symbol"] == "MARI" and mari["case_id"] == MARI_CASE_ID, "MARI identity mismatch")
    check(mari["status"] == "Observed" and mari["epistemic_type"] == "reported_fact", "MARI lifecycle/epistemic mismatch")
    mari_fact = mari["observed_facts"][0]
    check(mari_fact["fact_id"] == "mari_peshawar_working_interest_acquisition", "MARI fact mismatch")
    assert_evidence(mari_fact["evidence"][0], MARI_EVENT_ID, MARI_DOC_ID, 1, MARI_DOC_HASH)
    check(MARI_DOC_ID != "psx:265594" and MARI_DOC_HASH == "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42", "MARI strategy document substituted")

    pso = first["companies"]["PSO"]["cases"][0]
    check(first["companies"]["PSO"]["symbol"] == "PSO" and pso["case_id"] == PSO_CASE_ID, "PSO identity mismatch")
    check(pso["status"] == "Observed" and pso["epistemic_type"] == "reported_fact", "PSO lifecycle/epistemic mismatch")
    pso_fact = pso["observed_facts"][0]
    check(pso_fact["fact_id"] == "pso_fy2025_reported_network_expansion", "PSO fact mismatch")
    pso_values = {item["label"]: item["value"] for item in pso_fact.get("reported_values") or []}
    check(
        pso_values.get("fy2025_gross_new_outlets") == "107"
        and pso_values.get("fy2025_ending_network_outlets") == "3,649"
        and pso_values.get("fy2024_ending_network_outlets") == "3,580",
        "PSO reported values mismatch",
    )
    pso_refs = pso_fact.get("evidence") or []
    check({ref.get("page") for ref in pso_refs} == {15, 310}, "PSO evidence page mismatch")
    for ref in pso_refs:
        check(
            ref.get("canonical_event_id") == PSO_CANONICAL_EVENT_ID
            and ref.get("document_id") == PSO_DOC_ID
            and ref.get("source_url") == PSO_SOURCE_URL
            and ref.get("content_sha256") == PSO_CONTENT_SHA256
            and ref.get("document_published_at") == PSO_PUBLISHED_AT
            and ref.get("event_date") == PSO_EFFECTIVE_DATE
            and ref.get("text"),
            "PSO evidence source binding mismatch",
        )
    pso_derived = {item.get("fact_id"): item for item in pso.get("derived_facts") or {}}
    pso_recon = pso_derived.get("pso_fy2025_net_active_change_reconciliation") or {}
    pso_derived_values = {item.get("label"): item for item in pso_recon.get("derived_values") or []}
    check(
        pso_derived_values.get("derived_net_active_change_outlets", {}).get("value") == 69
        and pso_derived_values.get("unresolved_difference_outlets", {}).get("value") == 38
        and pso_derived_values.get("unresolved_difference_outlets", {}).get("status") == "unknown_not_asserted_as_closures",
        "PSO derived reconciliation mismatch",
    )
    pso_readiness = pso.get("sales_input_readiness") or {}
    pso_gate = pso_readiness.get("financial_truth_gate") or {}
    check(
        pso_gate.get("status") == "not_qualified"
        and all(value == "blocked_financial_truth_not_qualified" for value in (pso_gate.get("formal_output_statuses") or {}).values()),
        "PSO formal outputs must remain blocked",
    )
    pso_requirements = pso_readiness.get("event_specific_kernel_requirements") or {}
    check(set(pso_requirements) == set(PSO_KERNEL_FIELDS) and all(row.get("value") is None for row in pso_requirements.values()), "PSO model operands must remain null")
    check(len(pso.get("competing_hypotheses") or []) == 3 and all(row.get("distinguishing_evidence") for row in pso.get("competing_hypotheses") or []), "PSO competing hypotheses mismatch")

    ledger = load_json(STATE / "company_event_ledger.json", {"companies": {}})
    documents = load_json(STATE / "company_documents.json", {"documents": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    for symbol, event_id, doc_id, case_fn in (
        ("MLCF", PUBLIC_OFFER_EVENT_ID, PUBLIC_OFFER_DOC_ID, case_builder._mlcf_case),
        ("MARI", MARI_EVENT_ID, MARI_DOC_ID, case_builder._mari_case),
    ):
        for hostile_tickers in (["OTHER"], [], [symbol, "OTHER"], [1], None, symbol):
            hostile_ledger = deepcopy(ledger)
            event = next(item for item in hostile_ledger["companies"][symbol]["events"] if item.get("event_id") == event_id)
            event["tickers"] = hostile_tickers
            case = hostile_case_result(symbol, case_fn, hostile_ledger, documents, operating_events)
            check(case is None, f"{symbol} malformed event ticker binding was not rejected")
        for hostile_tickers in (["OTHER"], [], [symbol, "OTHER"], [1], None, symbol):
            hostile_documents = deepcopy(documents)
            hostile_documents["documents"][doc_id]["tickers"] = hostile_tickers
            case = hostile_case_result(symbol, case_fn, ledger, hostile_documents, operating_events)
            check(case is None, f"{symbol} malformed document ticker binding was not rejected")

    for case in (mlcf, mari, pso):
        check(case["promotion_blocks"].keys() >= {"Corroborated", "Modelled", "Published"}, f"promotion blocks missing for {case['case_id']}")
        check(all(case["policy"].get(key) is True for key in ("observed_only", "no_forecast", "no_valuation", "no_market_expectations", "no_recommendation")), f"policy missing for {case['case_id']}")
        cutoff = case["as_of"]
        for ref in case["source_lineage"]:
            check(ref["event_date"] <= cutoff and ref["document_published_at"] <= cutoff, f"evidence after case cutoff for {case['case_id']}")
        for key, _value in walk(case):
            check(str(key).lower() not in FORBIDDEN_KEYS, f"formal output key emitted: {key}")
    check(mlcf["policy"].get("reported_values_only") is False and mlcf["policy"].get("deterministic_derived_context_only") is True, "MLCF derived-market-context policy mismatch")
    check(mari["policy"].get("reported_values_only") is False and mari["policy"].get("deterministic_derived_context_only") is True, "MARI derived-market-context policy mismatch")

    sliced = build_slice(write=False)
    rows = {row["symbol"]: row for row in sliced["tickers"]}
    raw_mlcf = load_json(OUT, {})["companies"]["MLCF"]
    check(raw_mlcf == first["companies"]["MLCF"], "raw MLCF case state changed during UI projection")
    projected_mlcf = rows["MLCF"]["intelligence_cases"]
    check(projected_mlcf["symbol"] == "MLCF" and projected_mlcf["cases"][0]["case_id"] == MLCF_CASE_ID, "MLCF projected case identity mismatch")
    sections = projected_mlcf["cases"][0].get("sections") or {}
    mechanism = sections.get("mechanism") or {}
    check(mechanism.get("status") == "available" and mechanism.get("epistemic_type") == "reported_fact", "MLCF reported mechanism was not projected")
    mechanism_item = (mechanism.get("items") or [{}])[0]
    mechanism_refs = mechanism_item.get("evidence") or []
    check(len(mechanism_refs) == 2 and [ref.get("document_id") for ref in mechanism_refs] == ["psx:267429", "psx:275425"], "MLCF mechanism source order mismatch")
    check("not a quantified transaction outcome" in str(mechanism_item.get("text") or "") and "forecast" in str(mechanism_item.get("reason") or ""), "MLCF mechanism boundary missing")
    check(sections.get("confidence", {}).get("status") == "available", "MLCF source-bound confidence was not projected")
    check(sections.get("watch_next", {}).get("status") == "available", "MLCF source-bound watch list was not projected")
    dimensions = sections["confidence"].get("dimensions") or []
    check(dimensions and dimensions[0].get("status") == "low (42.0/100)", "MLCF projected confidence did not preserve financial-truth-gated score")
    watch_items = sections["watch_next"].get("items") or []
    check(len(watch_items) == 4 and all(item.get("reason") for item in watch_items), "MLCF projected watch items missing source requirements")
    check(rows["MARI"]["intelligence_cases"] == first["companies"]["MARI"], "MARI case row not attached exactly")
    check(rows["PSO"]["intelligence_cases"] == first["companies"]["PSO"], "PSO case row not attached exactly")
    projected_mari_case = next(case for case in rows["MARI"]["intelligence_cases"]["cases"] if case.get("case_id") == MARI_CASE_ID)
    mari_mechanism = (projected_mari_case.get("sections") or {}).get("mechanism") or {}
    check(mari_mechanism.get("status") == "blocked" and mari_mechanism.get("reason"), "MARI mechanism was not blocked")
    check(
        "financial truth is not_qualified" in str(mari_mechanism.get("reason") or "")
        and "project-economics inputs" in str(mari_mechanism.get("reason") or ""),
        "MARI mechanism block reason missing concrete evidence gaps",
    )
    projected_mari_sales_case = next(
        case for case in rows["MARI"]["intelligence_cases"]["cases"]
        if case.get("case_id") == MARI_SALES_CASE_ID
    )
    mari_sales_mechanism = (projected_mari_sales_case.get("sections") or {}).get("mechanism") or {}
    check(
        mari_sales_mechanism.get("status") == "blocked"
        and "financial truth is not_qualified" in str(mari_sales_mechanism.get("reason") or "")
        and "contracted-capacity" in str(mari_sales_mechanism.get("reason") or ""),
        "MARI sales-led mechanism block reason missing concrete evidence gaps",
    )
    for symbol, row in rows.items():
        payload = row.get("intelligence_cases")
        if payload:
            check(payload.get("symbol") == symbol, f"case payload crossed ticker boundary: {symbol}")
        if symbol not in {"MLCF", "MARI", "PSO"}:
            check(payload is None or (payload.get("case_count") == 0 and payload.get("cases") == []), f"unexpected case on {symbol}")
    check(_intelligence_case_row({}, "MLCF") is None, "missing case state produced a synthetic row")
    check(_intelligence_case_row({"companies": {"MLCF": {"symbol": "MARI", "case_count": 1}}}, "MLCF") is None, "mismatched case state crossed ticker boundary")
    confidence_state = load_json(CONFIDENCE_OUT, {})
    watchlist_state = load_json(WATCHLIST_OUT, {})
    hostile_confidence = deepcopy(confidence_state["companies"]["MLCF"])
    hostile_confidence["assessments"][0]["provenance_refs"][0]["content_sha256"] = "0" * 64
    rejected_projection = _intelligence_case_row(
        first,
        "MLCF",
        confidence_row=hostile_confidence,
        watchlist_row=watchlist_state["companies"]["MLCF"],
    )
    rejected_sections = rejected_projection["cases"][0].get("sections") or {}
    check(set(rejected_sections) == {"mechanism", "analogues"}, "mismatched evidence hash was projected into MLCF case")
    hostile_watch = deepcopy(watchlist_state["companies"]["MLCF"])
    hostile_watch["items"][0]["ids"]["assertion_key"] = "different_assertion"
    rejected_watch = _intelligence_case_row(
        first,
        "MLCF",
        confidence_row=confidence_state["companies"]["MLCF"],
        watchlist_row=hostile_watch,
    )
    rejected_watch_sections = rejected_watch["cases"][0].get("sections") or {}
    check(set(rejected_watch_sections) == {"mechanism", "analogues"}, "mismatched assertion was projected into MLCF case")

    after = snapshot(watched)
    check(before == after, "payload checker wrote an artifact")
    if OUT.exists():
        check(
            without_root_meta(load_json(OUT, {})) == without_root_meta(first),
            "generated case state differs from deterministic builder output",
        )
    print(f"intelligence_case_payloads: PASS ({checks} assertions)")


try:
    main()
except Exception as error:
    print(f"intelligence_case_payloads: FAIL — {error}")
    raise SystemExit(1)
