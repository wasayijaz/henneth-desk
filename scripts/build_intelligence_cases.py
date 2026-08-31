"""Build the two fixed, observed IntelligenceCase seeds from retained evidence."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "intelligence_cases.json"
CASE_PRODUCT_VERSION = "observed_intelligence_case_seed_v3"
LIFECYCLE = ["Observed", "Corroborated", "Modelled", "Validated", "Published"]
PKT = timezone(timedelta(hours=5))

MLCF_CASE_ID = "case_mlcf_pioc_control_observed_v1"
PUBLIC_OFFER_EVENT_ID = "evt_cb44dc32c91b0c5712a5"
FOLLOW_THROUGH_EVENT_ID = "evt_25bfb52e721191c7b644"
PUBLIC_OFFER_DOC_ID = "psx:267429"
FOLLOW_THROUGH_DOC_ID = "psx:275425"

MARI_CASE_ID = "case_mari_working_interest_observed_v1"
MARI_EVENT_ID = "evt_eddfcc381018cb0dff43"
MARI_DOC_ID = "psx:260446"
MARI_DOC_HASH = "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42"


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text += "T00:00:00"
    elif len(text) == 16 and text[10] == " ":
        text = text.replace(" ", "T") + ":00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed.replace(tzinfo=PKT) if parsed.tzinfo is None else parsed).astimezone(PKT)


def _iso_time(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else None


def _event(ledger: dict[str, Any], symbol: str, event_id: str) -> dict[str, Any] | None:
    events = (((ledger.get("companies") or {}).get(symbol) or {}).get("events") or [])
    for event in events:
        if isinstance(event, dict) and event.get("event_id") == event_id and event.get("tickers") == [symbol]:
            return event
    return None


def _document(documents: dict[str, Any], doc_id: str) -> dict[str, Any] | None:
    document = (documents.get("documents") or {}).get(doc_id)
    return document if isinstance(document, dict) else None


def _evidence_ref(event: dict[str, Any], document: dict[str, Any], symbol: str, page: int, content_hash: str) -> dict[str, Any] | None:
    if event.get("doc_id") != document.get("doc_id") or document.get("status") != "ready":
        return None
    if content_hash and document.get("content_sha256") != content_hash:
        return None
    if document.get("tickers") != [symbol]:
        return None
    source_url = document.get("source_url")
    for evidence in event.get("evidence") or []:
        if not isinstance(evidence, dict) or evidence.get("page") != page or not evidence.get("text"):
            continue
        if evidence.get("source_url") != source_url:
            continue
        event_time = _iso_time(event.get("event_date"))
        published_at = _iso_time(document.get("published_at"))
        if not event_time or not published_at:
            return None
        return {
            "event_id": event.get("event_id"),
            "document_id": document.get("doc_id"),
            "document_title": document.get("title"),
            "document_published_at": published_at,
            "document_retrieved_at": _iso_time(document.get("retrieved_at")),
            "content_sha256": document.get("content_sha256"),
            "source": document.get("source") or "PSX DPS",
            "source_url": source_url,
            "page": page,
            "text": evidence.get("text"),
            "event_date": event_time,
        }
    return None


def _source_cutoff(refs: list[dict[str, Any]]) -> str | None:
    dates = [_parse_time(ref.get("event_date") or ref.get("document_published_at")) for ref in refs]
    dates = [value for value in dates if value]
    return max(dates).isoformat() if dates else None


def _policy() -> dict[str, bool]:
    return {
        "observed_only": True,
        "no_forecast": True,
        "no_valuation": True,
        "no_market_expectations": True,
        "no_recommendation": True,
        "reported_values_only": True,
    }


def _blocks(extra: str) -> dict[str, str]:
    return {
        "Corroborated": extra,
        "Modelled": "Blocked: no source-qualified financial model or owner-approved assumptions are attached.",
        "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
    }


def _mlcf_case(ledger: dict[str, Any], documents: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    offer_event = _event(ledger, "MLCF", PUBLIC_OFFER_EVENT_ID)
    follow_event = _event(ledger, "MLCF", FOLLOW_THROUGH_EVENT_ID)
    offer_doc = _document(documents, PUBLIC_OFFER_DOC_ID)
    follow_doc = _document(documents, FOLLOW_THROUGH_DOC_ID)
    offer_ref = _evidence_ref(offer_event, offer_doc, "MLCF", 3, "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54") if offer_event and offer_doc else None
    follow_ref = _evidence_ref(follow_event, follow_doc, "MLCF", 4, "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f") if follow_event and follow_doc else None
    if not offer_ref or not follow_ref:
        return None, ["mlcf_retained_source_mismatch"]
    refs = [offer_ref, follow_ref]
    return {
        "case_id": MLCF_CASE_ID,
        "symbol": "MLCF",
        "target_symbol": "PIOC",
        "case_family": "industrial_cement",
        "case_type": "acquisition_control",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": _source_cutoff(refs),
        "summary": "Observed official-source seed: MLCF reported a public offer/control transaction for Pioneer Cement, and a later MLCF filing reported Pioneer Cement dispatches included in local-market totals after the February 2026 acquisition.",
        "observed_facts": [
            {
                "fact_id": "mlcf_pioc_public_offer_control",
                "source_event_id": PUBLIC_OFFER_EVENT_ID,
                "document_id": PUBLIC_OFFER_DOC_ID,
                "event_date": offer_ref["event_date"],
                "statement": "MLCF reported a public offer to acquire PIOC shares and control of Pioneer Cement Limited.",
                "reported_values": [
                    {"label": "public_offer_shares", "value": "up to 26,623,096 PIOC shares"},
                    {"label": "public_offer_percent", "value": "11.72% shares"},
                    {"label": "spa_percent", "value": "58.03% through Share Purchase Agreement(s)"},
                    {"label": "offer_price", "value": "PKR 478.43 per share"},
                ],
                "evidence": [offer_ref],
            },
            {
                "fact_id": "mlcf_pioc_dispatch_inclusion",
                "source_event_id": FOLLOW_THROUGH_EVENT_ID,
                "document_id": FOLLOW_THROUGH_DOC_ID,
                "event_date": follow_ref["event_date"],
                "statement": "MLCF reported inclusion of Pioneer Cement Limited dispatches in local-market total due to its acquisition during February 2026.",
                "reported_values": [
                    {"label": "acquisition_timing", "value": "during February 2026"},
                    {"label": "operating_follow_through", "value": "Pioneer Cement Limited dispatches included in local-market total"},
                ],
                "evidence": [follow_ref],
            },
        ],
        "alternative_readings": [
            {"alternative_id": "public_offer_not_full_model", "reading": "The official offer/control disclosure is not a quantified earnings model.", "status": "retained_as_observed_only", "rejection_condition": "Reject modelling if source-qualified incremental financial operands are absent."},
            {"alternative_id": "dispatch_inclusion_not_financial_impact", "reading": "The later filing shows operating inclusion, not a standalone PIOC financial impact.", "status": "retained_as_observed_only", "rejection_condition": "Reject modelling if source-qualified revenue, margin, EPS, cash-flow, debt and share-count operands are absent."},
        ],
        "promotion_blocks": _blocks("Blocked: retained evidence is an official MLCF/PSX chain, not independent-originator corroboration."),
        "policy": _policy(),
        "source_lineage": refs,
    }, []


def _mari_case(ledger: dict[str, Any], documents: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    event = _event(ledger, "MARI", MARI_EVENT_ID)
    document = _document(documents, MARI_DOC_ID)
    ref = _evidence_ref(event, document, "MARI", 1, MARI_DOC_HASH) if event and document else None
    if not ref:
        return None, ["mari_retained_source_mismatch"]
    return {
        "case_id": MARI_CASE_ID,
        "symbol": "MARI",
        "case_family": "e_and_p",
        "case_type": "working_interest_acquisition",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": _source_cutoff([ref]),
        "summary": "Observed official-source seed: Mari Energies reported acquisition of working interest in Peshawar Block as an operator.",
        "observed_facts": [{
            "fact_id": "mari_peshawar_working_interest_acquisition",
            "source_event_id": MARI_EVENT_ID,
            "document_id": MARI_DOC_ID,
            "event_date": ref["event_date"],
            "statement": "Mari Energies reported acquisition of working interest in Peshawar Block as an operator.",
            "reported_values": [
                {"label": "block", "value": "Peshawar Block"},
                {"label": "operator_status", "value": "as an Operator"},
            ],
            "evidence": [ref],
        }],
        "alternative_readings": [
            {"alternative_id": "working_interest_not_reserves", "reading": "Working-interest acquisition does not establish reserves, a commercial discovery, or future production.", "status": "retained_as_observed_only", "rejection_condition": "Reject promotion if no official source identifies technical results, resource potential, or a development path."},
            {"alternative_id": "operator_status_not_economics", "reading": "The notice does not establish cost, timing, resource, production or project economics.", "status": "retained_as_observed_only", "rejection_condition": "Reject modelling if source-qualified project economics and qualified company financial inputs remain absent."},
        ],
        "promotion_blocks": _blocks("Blocked: retained evidence is a single official MARI/PSX source and no independent-originator corroboration is attached."),
        "policy": _policy(),
        "source_lineage": [ref],
    }, []


def build(write: bool = True) -> dict[str, Any]:
    profiles = load_json(STATE / "company_profiles.json", {})
    ledger = load_json(STATE / "company_event_ledger.json", {"companies": {}})
    documents = load_json(STATE / "company_documents.json", {"documents": {}})
    pilot = list((profiles.get("pilot") or {}).get("symbols") or [])
    companies = {symbol: {"symbol": symbol, "status": "no_observed_case", "case_count": 0, "cases": [], "rejection_reasons": ["no_selected_observed_case_seed"]} for symbol in pilot}
    mlcf, mlcf_reasons = _mlcf_case(ledger, documents)
    mari, mari_reasons = _mari_case(ledger, documents)
    for symbol, case, reasons in (("MLCF", mlcf, mlcf_reasons), ("MARI", mari, mari_reasons)):
        if symbol not in companies:
            companies[symbol] = {"symbol": symbol, "status": "no_observed_case", "case_count": 0, "cases": [], "rejection_reasons": ["symbol_not_in_pilot"]}
        if case:
            companies[symbol] = {"symbol": symbol, "status": "observed_seed_available", "case_count": 1, "cases": [case], "rejection_reasons": []}
        else:
            companies[symbol]["rejection_reasons"] = reasons
    refs = [ref for case in (mlcf, mari) if case for ref in case.get("source_lineage", [])]
    result = {
        "schema_version": 1,
        "case_product_version": CASE_PRODUCT_VERSION,
        "as_of": _source_cutoff(refs),
        "pilot_symbols": pilot,
        "selected_symbols": ["MARI", "MLCF"],
        "status_lifecycle": LIFECYCLE,
        "policy": {"dedicated_observed_seeds_only": True, "no_generic_case_engine": True, "reported_values_only": True, "formal_engines_unchanged": True},
        "summary": {"company_count": len(companies), "observed_case_count": sum(row["case_count"] for row in companies.values()), "published_case_count": 0},
        "companies": companies,
    }
    if write:
        save_json(OUT, result)
        print(f"intelligence_cases: {result['summary']['observed_case_count']} observed seeds")
    return result


if __name__ == "__main__":
    build()
