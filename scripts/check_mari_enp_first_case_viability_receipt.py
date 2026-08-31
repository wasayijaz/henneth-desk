"""Check the read-only MARI E&P first-case viability receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from operating_events import stable_id


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "state/company_intel/mari_enp_first_case_viability_receipt.json"
OPERATING_EVENTS_PATH = ROOT / "state/company_intel/operating_events.json"
LEDGER_PATH = ROOT / "state/company_event_ledger.json"
DOCUMENTS_PATH = ROOT / "state/company_documents.json"
SOURCE_REGISTRY_PATH = ROOT / "state/company_intel/source_registry.json"
FINANCIAL_TRUTH_PATH = ROOT / "state/company_intel/financial_truth_qualification.json"
READINESS_PATH = ROOT / "state/company_intel/mari_enp_evidence_readiness.json"

SYMBOL = "MARI"
CANONICAL_EVENT_ID = "evt_3d1dae7553f73da60ba3"
ORIGINAL_EVENT_ID = "evt_ddf99590afb6dacddbde"
DOCUMENT_ID = "psx:265594"
SOURCE_URL = "https://dps.psx.com.pk/download/document/265594.pdf"
PUBLISHED_AT = "2025-11-13T10:10:00+05:00"
EVENT_DATE = "2025-11-13"
CONTENT_SHA256 = "cdc3f69157f5e5803238ba347ecb4e96f7297479df87d345739896913de8aae4"
EVIDENCE_SHA256 = "56c298f041bd756cd184e75d122f5a95cc6879f4b5fa037786007948b76d3d83"


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    raise AssertionError(message)


def check(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def find_event(events_state: dict[str, Any], event_id: str) -> dict[str, Any]:
    for event in ((events_state.get("companies") or {}).get(SYMBOL) or {}).get("events") or []:
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    fail(f"missing retained operating event: {event_id}")


def find_ledger_event(ledger: dict[str, Any], event_id: str) -> dict[str, Any]:
    for event in ((ledger.get("companies") or {}).get(SYMBOL) or {}).get("events") or []:
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    fail(f"missing retained ledger event: {event_id}")


def assert_no_formal_values(value: Any, path: str = "receipt") -> None:
    forbidden_keys = {
        "forecast",
        "valuation",
        "market_expectations",
        "target_price",
        "price_target",
        "recommendation",
        "expected_return",
    }
    advice_phrases = ("buy", "sell", "accumulate", "you should")
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in forbidden_keys and not str(item).startswith("blocked_"):
                fail(f"unblocked formal output at {path}.{key}")
            assert_no_formal_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_formal_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for phrase in advice_phrases:
            if phrase in lowered:
                fail(f"advice phrase in receipt at {path}: {phrase}")


def main() -> None:
    receipt = load(RECEIPT_PATH)
    operating_events = load(OPERATING_EVENTS_PATH)
    ledger = load(LEDGER_PATH)
    documents = load(DOCUMENTS_PATH)
    source_registry = load(SOURCE_REGISTRY_PATH)
    financial_truth = load(FINANCIAL_TRUTH_PATH)
    readiness = load(READINESS_PATH)

    check(receipt.get("schema_version") == "mari_enp_first_case_viability_receipt_v1", "schema version mismatch")
    check(receipt.get("symbol") == SYMBOL, "symbol mismatch")
    check(receipt.get("receipt_status") == "observed_seed_ready", "receipt status mismatch")
    check(receipt.get("policy") == {
        "read_only_retained_state_only": True,
        "no_network_or_new_provider": True,
        "no_case_model_change": True,
        "no_formal_engine_activation": True,
        "no_invented_inputs": True,
        "no_advice_language": True,
    }, "policy mismatch")

    candidate = receipt.get("candidate") or {}
    event = find_event(operating_events, CANONICAL_EVENT_ID)
    ledger_event = find_ledger_event(ledger, ORIGINAL_EVENT_ID)
    doc = (documents.get("documents") or {}).get(DOCUMENT_ID)
    check(isinstance(doc, dict), "document missing")
    source_row = (source_registry.get("tickers") or {}).get(SYMBOL)
    check(isinstance(source_row, dict) and source_row.get("dps_company_url") == "https://dps.psx.com.pk/company/MARI", "source registry mismatch")

    check(stable_id(SYMBOL, ORIGINAL_EVENT_ID, "acquisition_divestment") == CANONICAL_EVENT_ID, "original stable-id binding mismatch")
    check(candidate.get("candidate_event_id") == event.get("event_id") == CANONICAL_EVENT_ID, "canonical event id mismatch")
    check(candidate.get("original_event_id") == ledger_event.get("event_id") == ORIGINAL_EVENT_ID, "original event id mismatch")
    check(candidate.get("document_id") == doc.get("doc_id") == ledger_event.get("doc_id") == DOCUMENT_ID, "document id mismatch")
    check(candidate.get("source_url") == event.get("source_url") == doc.get("source_url") == SOURCE_URL, "source url mismatch")
    check(candidate.get("published_at") == doc.get("published_at") == PUBLISHED_AT, "published timestamp mismatch")
    check(candidate.get("event_date") == event.get("effective_date") == EVENT_DATE, "event date mismatch")
    check(candidate.get("availability_date") == EVENT_DATE, "availability date mismatch")
    check(candidate.get("availability_date_basis") == "retained document has no available_on field; derived from published_at date", "availability basis mismatch")
    check(doc.get("available_on") is None, "fixture changed: document now has available_on")
    check(candidate.get("company_identity") == {"company_id": "MARI", "symbol": "MARI", "tickers": ["MARI"]}, "company identity mismatch")
    check(ledger_event.get("tickers") == ["MARI"], "ledger ticker mismatch")
    check(candidate.get("event_classification") == {
        "event_type": "acquisition_divestment",
        "event_subtype": "acquisition",
        "intelligence_type": "reported_fact",
        "priority_weight": 4,
    }, "event classification mismatch")
    check(event.get("event_type") == "acquisition_divestment" and event.get("event_subtype") == "acquisition", "retained event classification mismatch")

    evidence = (event.get("evidence") or [{}])[0]
    doc_evidence = (doc.get("evidence") or [{}])[0]
    check(evidence.get("document_id") == DOCUMENT_ID and evidence.get("source") == "PSX DPS", "event evidence document/source mismatch")
    check(evidence.get("page") == doc_evidence.get("page") == 3, "evidence page mismatch")
    check(evidence.get("content_sha256") == doc.get("content_sha256") == doc.get("local_sha256") == CONTENT_SHA256, "content hash mismatch")
    check(evidence.get("evidence_sha256") == EVIDENCE_SHA256, "evidence hash mismatch")
    expected_evidence_hash = hashlib.sha256(
        f"{DOCUMENT_ID}|{SOURCE_URL}|{evidence.get('page')}|{evidence.get('text')}".encode("utf-8")
    ).hexdigest()
    check(expected_evidence_hash == EVIDENCE_SHA256, "evidence hash no longer binds document/url/page/text")
    mechanism = candidate.get("initial_business_mechanism") or {}
    text = str(mechanism.get("evidence_text") or "")
    check("offshore exploration blocks" in text and "hydrocarbon resources" in text, "business mechanism text mismatch")
    check("operator status for this target event" in (mechanism.get("not_evidenced") or []), "operator-status limitation missing")

    binding = candidate.get("evidence_binding") or {}
    check(binding.get("page") == 3 and binding.get("content_sha256") == CONTENT_SHA256, "receipt evidence binding mismatch")
    check(binding.get("evidence_sha256") == EVIDENCE_SHA256 and binding.get("evidence_class") == "exact_hash_page_backed", "receipt evidence hash/class mismatch")

    truth = (financial_truth.get("companies") or {}).get(SYMBOL) or {}
    slice_row = receipt.get("bounded_first_vertical_slice") or {}
    check(slice_row.get("status") == "blocked_for_formal_outputs", "vertical slice status mismatch")
    check(slice_row.get("observed_event_path") == "ready", "observed event path mismatch")
    check(slice_row.get("financial_truth_status") == truth.get("status") == "not_qualified", "financial truth status mismatch")
    check(truth.get("annual_income_triplets", {}).get("present") == 0, "annual income present count mismatch")
    check(truth.get("qualified_reported_quarter_fact_sets", {}).get("present") == 0, "quarter fact present count mismatch")
    check(truth.get("annual_operating_cash_flow", {}).get("present") == 0, "operating cash flow present count mismatch")
    check(truth.get("share_count", {}).get("status") == "missing_official_share_count_capital_note_tie_out", "share tie-out mismatch")
    check(slice_row.get("formal_output_policy") == truth.get("downstream"), "formal output policy mismatch")

    readiness_row = slice_row.get("retained_evidence_readiness") or {}
    check(readiness.get("event", {}).get("status") == readiness_row.get("event_status") == "observed_only", "readiness event status mismatch")
    check(readiness.get("event", {}).get("exact_hash_page_backed_evidence_count") >= readiness_row.get("exact_hash_page_backed_evidence_count_min"), "readiness evidence count mismatch")
    check(readiness.get("ep_operands", {}).get("status") == readiness_row.get("ep_operands_status") == "blocked_missing_numeric_operands", "E&P operand readiness mismatch")
    activation = readiness.get("activation") or {}
    check(
        readiness_row == {
            "event_status": "observed_only",
            "exact_hash_page_backed_evidence_count_min": 1,
            "ep_operands_status": "blocked_missing_numeric_operands",
            "activation_status": "blocked",
            "kernel_activated": False,
            "forecast_activated": False,
            "valuation_activated": False,
            "market_expectations_activated": False,
        },
        "retained evidence readiness receipt mismatch",
    )
    check(activation.get("status") == "blocked" and activation.get("kernel_activated") is False, "activation gate mismatch")
    check(activation.get("forecast_activated") is False and activation.get("valuation_activated") is False, "formal engines activated")
    check(activation.get("market_expectations_activated") is False, "market expectations activated")

    cited_paths = {row.get("path") for row in receipt.get("citations") or []}
    check(cited_paths == {
        "state/company_intel/operating_events.json",
        "state/company_event_ledger.json",
        "state/company_documents.json",
        "state/company_intel/source_registry.json",
        "state/company_intel/financial_truth_qualification.json",
        "state/company_intel/mari_enp_evidence_readiness.json",
    }, "citation set mismatch")
    assert_no_formal_values(receipt)
    print("mari_enp_first_case_viability_receipt: PASS (retained-state observed seed ready; formal slice blocked)")


if __name__ == "__main__":
    main()
