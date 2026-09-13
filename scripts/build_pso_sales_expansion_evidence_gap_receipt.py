"""Build the PSO Case C evidence-gap receipt from retained local authorities.

This does not fetch, parse, restage, promote, or model anything.  It records
why the FY2025 PSO retail-network expansion is selected as the Case C candidate
but cannot be emitted as an Observed IntelligenceCase seed in this checkout.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from psx_data import STATE, load_json, save_json

SCHEMA_VERSION = "pso_sales_expansion_evidence_gap_receipt_v1"
RECEIPT_VERSION = "pso_sales_expansion_case_c_candidate_gap_v1"
OUTPUT_PATH = STATE / "company_intel" / "pso_sales_expansion_evidence_gap_receipt.json"

RESEARCH_INDEX_PATH = STATE / "research_index.json"
COMPANY_DOCUMENTS_PATH = STATE / "company_documents.json"
SOURCE_REGISTRY_PATH = STATE / "company_intel" / "source_registry.json"
OPERATING_EVENTS_PATH = STATE / "company_intel" / "operating_events.json"
AUDIT_PATH = "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md"

PSX_DOC_ID = "psx:260771"
EVENT_REF = "PSO_FY2025_RETAIL_NETWORK_AND_CHANNEL_EXPANSION"
CASE_ID = "case_pso_fy2025_distribution_network_expansion_gap_v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _documents_table(company_documents: Mapping[str, Any]) -> Mapping[str, Any]:
    documents = company_documents.get("documents")
    return documents if isinstance(documents, Mapping) else {}


def _research_documents(research_index: Mapping[str, Any]) -> Mapping[str, Any]:
    documents = research_index.get("documents")
    return documents if isinstance(documents, Mapping) else {}


def _pso_registry(source_registry: Mapping[str, Any]) -> Mapping[str, Any]:
    tickers = source_registry.get("tickers")
    if not isinstance(tickers, Mapping):
        return {}
    row = tickers.get("PSO")
    return row if isinstance(row, Mapping) else {}


def _pso_operating_events(operating_events: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    companies = operating_events.get("companies")
    if not isinstance(companies, Mapping):
        return []
    pso = companies.get("PSO")
    if not isinstance(pso, Mapping):
        return []
    events = pso.get("events")
    return [row for row in events if isinstance(row, Mapping)] if isinstance(events, list) else []


def _source_registry_links(registry_row: Mapping[str, Any]) -> list[dict[str, Any]]:
    links = registry_row.get("document_links")
    if not isinstance(links, list):
        return []
    retained = []
    for link in links:
        if not isinstance(link, Mapping):
            continue
        retained.append({
            "id": link.get("id"),
            "url": link.get("url"),
            "label": link.get("label"),
            "status": link.get("status"),
            "first_seen_at": link.get("first_seen_at"),
        })
    return retained


def _document_binding(company_documents: Mapping[str, Any], doc_id: str) -> dict[str, Any] | None:
    doc = _documents_table(company_documents).get(doc_id)
    if not isinstance(doc, Mapping):
        return None
    evidence = doc.get("evidence")
    rows = []
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, Mapping):
                rows.append({
                    "page": item.get("page"),
                    "text": item.get("text"),
                    "source_url": item.get("source_url"),
                })
    return {
        "document_id": doc_id,
        "title": doc.get("title"),
        "source": doc.get("source"),
        "source_url": doc.get("source_url"),
        "status": doc.get("status"),
        "published_at": doc.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "content_sha256": doc.get("content_sha256"),
        "local_sha256": doc.get("local_sha256"),
        "evidence": rows,
    }


def _retained_same_issuer_bindings(company_documents: Mapping[str, Any]) -> list[dict[str, Any]]:
    bindings = []
    for doc_id in (
        "issuer:61d85f4626413576b676aed8",
        "issuer:ca78a4beec7f30b38e790a5e",
        "issuer:bed83f3756e28ddc1a880ca9",
        "issuer:cbe4419e5053660b66196642",
    ):
        binding = _document_binding(company_documents, doc_id)
        if binding:
            binding["qualifies_observed_seed"] = False
            binding["no_go_reason"] = "same_issuer_corporate_card_material_not_dated_fy2025_network_expansion"
            bindings.append(binding)
    return bindings


def build(*, write: bool = True) -> dict[str, Any]:
    research_index = load_json(RESEARCH_INDEX_PATH, {})
    company_documents = load_json(COMPANY_DOCUMENTS_PATH, {})
    source_registry = load_json(SOURCE_REGISTRY_PATH, {})
    operating_events = load_json(OPERATING_EVENTS_PATH, {})

    psx_index_doc = _research_documents(research_index).get(PSX_DOC_ID)
    psx_index_doc = psx_index_doc if isinstance(psx_index_doc, Mapping) else None
    retained_decisive_doc = _documents_table(company_documents).get(PSX_DOC_ID)

    pso_events = _pso_operating_events(operating_events)
    pso_distribution_events = [
        event for event in pso_events
        if event.get("event_type") == "distribution_network_expansion"
        or "distribution" in str(event.get("event_subtype") or "").lower()
        or EVENT_REF in str(event.get("event_id") or "")
    ]

    gross_openings = 107
    prior_ending_network = 3580
    ending_network = 3649
    net_active_change = ending_network - prior_ending_network
    unknown_closures_or_reclassifications = gross_openings - net_active_change

    blocked_reasons = sorted([
        "PSO:fy2025_decisive_source_not_retained_hash_page_bound",
        "PSO:canonical_distribution_network_expansion_event_absent",
        "PSO:corporate_card_station_list_is_undated_current_footprint_not_expansion_event",
        "PSO:gross_openings_vs_net_network_change_unreconciled",
        "sales_lane:no_observed_case_seed_permitted",
    ])

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "receipt_version": RECEIPT_VERSION,
        "case_id": CASE_ID,
        "event_ref": EVENT_REF,
        "ticker": "PSO",
        "issuer": "Pakistan State Oil Company Limited",
        "case_family": "sales_led_expansion",
        "event_type": "distribution_network_expansion",
        "event_subtype": "fuel_retail_and_convenience_channel",
        "status": "evidence_gap_no_observed_seed",
        "selection_state": "selected_candidate_pending_evidence_ingestion",
        "observed_seed_permitted": False,
        "event_period_end": "2025-06-30",
        "available_on": None,
        "source_cutoff": None,
        "audit_authority": AUDIT_PATH,
        "required_decisive_evidence": {
            "accepted_sources": [
                "retained_hash_page_bound_official_pso_fy2025_results_release",
                "retained_hash_page_bound_official_pso_fy2025_summary_or_full_annual_report",
                "retained_hash_page_bound_psx_annual_report_filing_psx_260771",
            ],
            "required_fields": [
                "document_id",
                "source_url",
                "content_sha256",
                "one_based_page",
                "bounded_text",
                "published_at_or_conservative_available_on",
            ],
        },
        "retained_authority_state": {
            "research_index_psx_260771": {
                "present": psx_index_doc is not None,
                "document_id": PSX_DOC_ID,
                "title": psx_index_doc.get("title") if psx_index_doc else None,
                "source": psx_index_doc.get("source") if psx_index_doc else None,
                "url": psx_index_doc.get("url") if psx_index_doc else None,
                "published_at": psx_index_doc.get("published_at") if psx_index_doc else None,
                "download_status": (psx_index_doc.get("download") or {}).get("status") if psx_index_doc else None,
                "download_error": (psx_index_doc.get("download") or {}).get("error") if psx_index_doc else None,
                "content_sha256": psx_index_doc.get("content_sha256") if psx_index_doc else None,
                "qualifies_observed_seed": False,
                "no_go_reason": "metadata_only_or_download_failed_without_retained_hash_page_evidence",
            },
            "company_documents_psx_260771_present": isinstance(retained_decisive_doc, Mapping),
            "operating_events_pso_distribution_candidates": len(pso_distribution_events),
            "source_registry_pso_document_links": _source_registry_links(_pso_registry(source_registry)),
            "same_issuer_hash_bound_nonqualifying_documents": _retained_same_issuer_bindings(company_documents),
        },
        "reported_fact_candidates_unpromoted": {
            "basis": "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md; not promoted because decisive official FY2025 source is not retained/hash-page-bound in this checkout",
            "fy2024_ending_network_outlets": prior_ending_network,
            "fy2025_gross_new_outlets": gross_openings,
            "fy2025_ending_network_outlets": ending_network,
            "derived_net_active_change_outlets": net_active_change,
            "unknown_closures_or_reclassifications_outlets": unknown_closures_or_reclassifications,
            "promotion_status": "not_promoted_to_reported_facts",
        },
        "epistemic_boundaries": {
            "gross_openings_are_not_net_additions": True,
            "unknown_38_outlet_delta_may_be_closures_replacements_reclassifications_or_counting_basis_change": True,
            "channel_layers_are_nested_not_additive": True,
            "fuel_outlets_convenience_vibe_asaan_safar_and_digital_outlets_must_not_be_double_counted": True,
            "reported_market_share_or_pat_must_not_be_backsolved_as_causal_expansion_impact": True,
        },
        "downstream_status": {
            "intelligence_case_seed": "blocked",
            "operating_event": "blocked",
            "scenario_model": "blocked",
            "valuation": "blocked",
            "publication": "blocked",
        },
        "blocked_reasons": blocked_reasons,
        "run_receipt": {},
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_fetch": True,
            "no_promotion": True,
            "fail_closed": True,
        },
    }
    receipt["run_receipt"] = {
        "input_sha256": _sha256({
            "research_index_psx_260771": receipt["retained_authority_state"]["research_index_psx_260771"],
            "company_documents_psx_260771_present": receipt["retained_authority_state"]["company_documents_psx_260771_present"],
            "same_issuer_hash_bound_nonqualifying_documents": receipt["retained_authority_state"]["same_issuer_hash_bound_nonqualifying_documents"],
            "reported_fact_candidates_unpromoted": receipt["reported_fact_candidates_unpromoted"],
        }),
        "output_sha256": _sha256([]),
        "contract_version": SCHEMA_VERSION,
    }
    if write:
        save_json(OUTPUT_PATH, receipt)
    return receipt


if __name__ == "__main__":
    result = build()
    print(f"pso_sales_expansion_evidence_gap_receipt: status={result['status']}")
