"""Build compact observed IntelligenceCase seeds from retained official evidence.

This is intentionally not a generic case engine.  The current product need is a
single MLCF observed seed over the Pioneer Cement acquisition/control record.
Later statuses or sector models must earn their own builders/checks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "intelligence_cases.json"
CASE_PRODUCT_VERSION = "observed_intelligence_case_seed_v1"
PKT = timezone(timedelta(hours=5))

MLCF_CASE_ID = "case_mlcf_pioc_control_observed_v1"
PUBLIC_OFFER_EVENT_ID = "evt_cb44dc32c91b0c5712a5"
FOLLOW_THROUGH_EVENT_ID = "evt_25bfb52e721191c7b644"
PUBLIC_OFFER_DOC_ID = "psx:267429"
FOLLOW_THROUGH_DOC_ID = "psx:275425"


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00"
    elif len(text) == 16 and text[10] == " ":
        text = text.replace(" ", "T") + ":00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PKT)
    return parsed.astimezone(PKT)


def _iso_time(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else None


def _date(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.date().isoformat() if parsed else None


def _event(ledger: dict[str, Any], symbol: str, event_id: str) -> dict[str, Any] | None:
    for event in (((ledger.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None


def _document(documents: dict[str, Any], doc_id: str) -> dict[str, Any] | None:
    doc = (documents.get("documents") or {}).get(doc_id)
    return doc if isinstance(doc, dict) else None


def _evidence_ref(event: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    evidence = (event.get("evidence") or [{}])[0]
    return {
        "event_id": event.get("event_id"),
        "document_id": event.get("doc_id"),
        "document_title": doc.get("title"),
        "document_published_at": _iso_time(doc.get("published_at") or event.get("event_date")),
        "document_retrieved_at": _iso_time(doc.get("retrieved_at")),
        "content_sha256": doc.get("content_sha256"),
        "source": doc.get("source") or "PSX DPS",
        "source_url": evidence.get("source_url") or doc.get("source_url"),
        "page": evidence.get("page"),
        "text": evidence.get("text"),
    }


def _source_cutoff(refs: list[dict[str, Any]]) -> str:
    parsed = [
        _parse_time(ref.get("document_retrieved_at") or ref.get("document_published_at"))
        for ref in refs
    ]
    parsed = [value for value in parsed if value is not None]
    return (max(parsed) if parsed else datetime.now(PKT).replace(microsecond=0)).isoformat()


def _empty_company(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "no_observed_case",
        "case_count": 0,
        "cases": [],
        "rejection_reasons": ["no_selected_observed_case_seed"],
    }


def _mlcf_case(ledger: dict[str, Any], documents: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    public_offer = _event(ledger, "MLCF", PUBLIC_OFFER_EVENT_ID)
    follow_through = _event(ledger, "MLCF", FOLLOW_THROUGH_EVENT_ID)
    public_offer_doc = _document(documents, PUBLIC_OFFER_DOC_ID)
    follow_through_doc = _document(documents, FOLLOW_THROUGH_DOC_ID)
    missing = []
    for label, value in (
        ("missing_public_offer_event", public_offer),
        ("missing_follow_through_event", follow_through),
        ("missing_public_offer_document", public_offer_doc),
        ("missing_follow_through_document", follow_through_doc),
    ):
        if value is None:
            missing.append(label)
    if missing:
        return None, missing, []
    assert public_offer is not None and follow_through is not None
    assert public_offer_doc is not None and follow_through_doc is not None
    refs = [_evidence_ref(public_offer, public_offer_doc), _evidence_ref(follow_through, follow_through_doc)]
    cutoff = _source_cutoff(refs)
    case = {
        "case_id": MLCF_CASE_ID,
        "symbol": "MLCF",
        "target_symbol": "PIOC",
        "case_family": "industrial_cement",
        "case_type": "acquisition_control",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": cutoff,
        "summary": (
            "Observed official-source seed: MLCF reported a public offer/control transaction for "
            "Pioneer Cement, and a later MLCF quarterly filing reported Pioneer Cement dispatches "
            "included in local-market totals after the February 2026 acquisition."
        ),
        "observed_facts": [
            {
                "fact_id": "mlcf_pioc_public_offer_control",
                "source_event_id": PUBLIC_OFFER_EVENT_ID,
                "document_id": PUBLIC_OFFER_DOC_ID,
                "event_date": _iso_time(public_offer.get("event_date")),
                "statement": "MLCF reported a public offer to acquire PIOC shares and control of Pioneer Cement Limited.",
                "reported_values": [
                    {"label": "public_offer_shares", "value": "up to 26,623,096 PIOC shares"},
                    {"label": "public_offer_percent", "value": "11.72% shares"},
                    {"label": "spa_percent", "value": "58.03% through Share Purchase Agreement(s)"},
                    {"label": "offer_price", "value": "PKR 478.43 per share"},
                ],
                "evidence": [refs[0]],
            },
            {
                "fact_id": "mlcf_pioc_dispatch_inclusion",
                "source_event_id": FOLLOW_THROUGH_EVENT_ID,
                "document_id": FOLLOW_THROUGH_DOC_ID,
                "event_date": _iso_time(follow_through.get("event_date")),
                "statement": (
                    "MLCF reported inclusion of Pioneer Cement Limited dispatches in local-market "
                    "total due to its acquisition during February 2026."
                ),
                "reported_values": [
                    {"label": "acquisition_timing", "value": "during February 2026"},
                    {"label": "operating_follow_through", "value": "Pioneer Cement Limited dispatches included in local-market total"},
                ],
                "evidence": [refs[1]],
            },
        ],
        "alternative_readings": [
            {
                "alternative_id": "public_offer_not_full_model",
                "reading": "The December 2025 document is an official offer/control disclosure, not a quantified earnings model.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject promotion if no later official source preserves acquisition/control or operating inclusion.",
            },
            {
                "alternative_id": "dispatch_inclusion_not_financial_impact",
                "reading": "The April 2026 filing shows operating inclusion after acquisition, but not a standalone PIOC financial impact.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject modelling if source-qualified incremental revenue, margin, EPS, cash-flow, debt and share-count operands are absent.",
            },
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: retained evidence is an official MLCF/PSX chain, not independent-originator corroboration.",
            "Modelled": "Blocked: no source-qualified financial impact model or owner-approved assumptions are attached.",
            "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        "policy": {
            "observed_only": True,
            "no_forecast": True,
            "no_valuation": True,
            "no_market_expectations": True,
            "no_recommendation": True,
            "reported_values_only": True,
        },
        "source_lineage": refs,
    }
    return case, [], refs


def build(write: bool = True) -> dict[str, Any]:
    profiles = load_json(STATE / "company_profiles.json", {})
    ledger = load_json(STATE / "company_event_ledger.json", {"companies": {}})
    documents = load_json(STATE / "company_documents.json", {"documents": {}})
    pilot = sorted((profiles.get("pilot") or {}).get("symbols") or [])
    companies = {symbol: _empty_company(symbol) for symbol in pilot}
    case, rejections, refs = _mlcf_case(ledger, documents)
    as_of = _source_cutoff(refs) if refs else datetime.now(PKT).replace(microsecond=0).isoformat()
    if "MLCF" not in companies:
        companies["MLCF"] = _empty_company("MLCF")
    if case:
        companies["MLCF"] = {
            "symbol": "MLCF",
            "status": "observed_seed_available",
            "case_count": 1,
            "cases": [case],
            "rejection_reasons": [],
        }
    else:
        companies["MLCF"]["rejection_reasons"] = rejections
    result = {
        "schema_version": 1,
        "case_product_version": CASE_PRODUCT_VERSION,
        "as_of": as_of,
        "pilot_symbols": pilot,
        "selected_symbols": ["MLCF"],
        "status_lifecycle": ["Observed", "Corroborated", "Modelled", "Validated", "Published"],
        "policy": {
            "dedicated_observed_seed_only": True,
            "no_generic_case_engine": True,
            "reported_values_only": True,
            "formal_engines_unchanged": True,
        },
        "summary": {
            "company_count": len(companies),
            "observed_case_count": sum(row.get("case_count", 0) for row in companies.values()),
            "published_case_count": 0,
        },
        "companies": companies,
    }
    if write:
        save_json(OUT, result)
        print(f"intelligence_cases: {result['summary']['observed_case_count']} observed seed")
    return result


if __name__ == "__main__":
    build()
