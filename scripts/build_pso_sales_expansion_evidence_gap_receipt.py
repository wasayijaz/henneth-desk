"""Build the PSO Case C evidence-gap receipt from retained local authorities.

This does not fetch, parse, restage, promote, or model anything.  It records
why the FY2025 PSO retail-network expansion is selected as the Case C candidate
but cannot be emitted as an Observed IntelligenceCase seed in this checkout.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

import pymupdf

from psx_data import STATE, load_json, save_json

SCHEMA_VERSION = "pso_sales_expansion_evidence_gap_receipt_v1"
RECEIPT_VERSION = "pso_sales_expansion_case_c_candidate_gap_v1"
INTAKE_REVISION = "psx_260771_hash_page_bound_v1"
OUTPUT_PATH = STATE / "company_intel" / "pso_sales_expansion_evidence_gap_receipt.json"

RESEARCH_INDEX_PATH = STATE / "research_index.json"
COMPANY_DOCUMENTS_PATH = STATE / "company_documents.json"
SOURCE_REGISTRY_PATH = STATE / "company_intel" / "source_registry.json"
OPERATING_EVENTS_PATH = STATE / "company_intel" / "operating_events.json"
INTELLIGENCE_CASES_PATH = STATE / "company_intel" / "intelligence_cases.json"
AUDIT_PATH = "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md"
LOCAL_PDF_PATH = STATE.parent / ".cache" / "company_intel" / "pso_sales_expansion_intake" / "260771.pdf"

PSX_DOC_ID = "psx:260771"
EVENT_REF = "PSO_FY2025_RETAIL_NETWORK_AND_CHANNEL_EXPANSION"
CASE_ID = "case_pso_fy2025_distribution_network_expansion_gap_v1"
OFFICIAL_URL = "https://dps.psx.com.pk/download/document/260771.pdf"
OFFICIAL_TITLE = "Transmission of Annual Report for the year ended June 30, 2025"
OFFICIAL_PUBLISHED_AT = "2025-10-02T08:48:00+05:00"
EXPECTED_CONTENT_SHA256 = "c336ba824d4010dff3878779c31bbc76fd85ab6704b4ecb4837de821f9bd0a2d"
MAX_DOCUMENT_SPECIFIC_BYTES = 14 * 1024 * 1024
EXPECTED_PAGE_COUNT = 420

EVIDENCE_SELECTORS = (
    {
        "evidence_id": "pso_fy2025_retail_network_channel_expansion",
        "page": 15,
        "required_terms": (
            "adding 107 new outlets in FY25",
            "network of 3,649 across Pakistan",
            "over 310 convenience stores",
            "launched VIBE",
            "Karachi, Lahore, and Islamabad",
            "introduced the first phase of Asaan Safar",
        ),
        "anchor": "expanded its retail presence",
    },
    {
        "evidence_id": "pso_fy2025_network_count_reconciliation",
        "page": 310,
        "required_terms": (
            "total 3,649",
            "2024: 3,580",
            "retail filling station",
        ),
        "anchor": "total 3,649",
    },
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise_pdf_text(text: str) -> str:
    return (
        str(text or "")
        .replace("\ufb01", "fi")
        .replace("\ufb02", "fl")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )


def _bounded_text(text: str, anchor: str, *, before: int = 260, after: int = 760) -> str:
    compact = " ".join(_normalise_pdf_text(text).split())
    index = compact.lower().find(anchor.lower())
    if index < 0:
        raise ValueError(f"missing evidence anchor: {anchor}")
    start = max(0, index - before)
    end = min(len(compact), index + after)
    return compact[start:end]


def _extract_decisive_source(psx_index_doc: Mapping[str, Any] | None) -> dict[str, Any]:
    if not psx_index_doc:
        return {"status": "missing_research_index_metadata", "qualifies_observed_seed": False}
    if psx_index_doc.get("title") != OFFICIAL_TITLE:
        return {"status": "research_index_title_mismatch", "qualifies_observed_seed": False}
    if psx_index_doc.get("url") != OFFICIAL_URL:
        return {"status": "research_index_url_mismatch", "qualifies_observed_seed": False}
    if psx_index_doc.get("published_at") != OFFICIAL_PUBLISHED_AT:
        return {"status": "research_index_published_at_mismatch", "qualifies_observed_seed": False}
    if not LOCAL_PDF_PATH.exists():
        return {
            "status": "missing_local_pdf_bytes",
            "document_id": PSX_DOC_ID,
            "raw_path": str(LOCAL_PDF_PATH.relative_to(STATE.parent)).replace("\\", "/"),
            "qualifies_observed_seed": False,
        }
    size = LOCAL_PDF_PATH.stat().st_size
    if size > MAX_DOCUMENT_SPECIFIC_BYTES:
        return {
            "status": "document_specific_size_cap_exceeded",
            "content_length": size,
            "document_specific_max_bytes": MAX_DOCUMENT_SPECIFIC_BYTES,
            "global_default_cap_preserved_bytes": 12 * 1024 * 1024,
            "qualifies_observed_seed": False,
        }
    digest = _file_sha256(LOCAL_PDF_PATH)
    if digest != EXPECTED_CONTENT_SHA256:
        return {
            "status": "content_hash_mismatch",
            "content_sha256": digest,
            "expected_content_sha256": EXPECTED_CONTENT_SHA256,
            "qualifies_observed_seed": False,
        }
    evidence_rows: list[dict[str, Any]] = []
    with pymupdf.open(LOCAL_PDF_PATH) as pdf:
        page_count = len(pdf)
        if page_count != EXPECTED_PAGE_COUNT:
            return {
                "status": "page_count_mismatch",
                "content_sha256": digest,
                "page_count": page_count,
                "expected_page_count": EXPECTED_PAGE_COUNT,
                "qualifies_observed_seed": False,
            }
        for selector in EVIDENCE_SELECTORS:
            page_no = int(selector["page"])
            text = pdf[page_no - 1].get_text()
            bounded = _bounded_text(text, str(selector["anchor"]))
            missing_terms = [
                term for term in selector["required_terms"]
                if term.lower() not in bounded.lower()
            ]
            if missing_terms:
                return {
                    "status": "required_evidence_term_missing",
                    "content_sha256": digest,
                    "page_count": page_count,
                    "evidence_id": selector["evidence_id"],
                    "missing_terms": missing_terms,
                    "qualifies_observed_seed": False,
                }
            evidence_rows.append({
                "evidence_id": selector["evidence_id"],
                "page": page_no,
                "text": bounded,
                "source_url": OFFICIAL_URL,
                "content_sha256": digest,
            })
    gross_openings = 107
    prior_ending_network = 3580
    ending_network = 3649
    net_active_change = ending_network - prior_ending_network
    unknown_closures_or_reclassifications = gross_openings - net_active_change
    if unknown_closures_or_reclassifications != 38:
        return {
            "status": "network_reconciliation_arithmetic_mismatch",
            "qualifies_observed_seed": False,
        }
    return {
        "status": "hash_page_bound_observed_seed_defensible",
        "document_id": PSX_DOC_ID,
        "title": OFFICIAL_TITLE,
        "source": "PSX DPS",
        "source_url": OFFICIAL_URL,
        "raw_path": str(LOCAL_PDF_PATH.relative_to(STATE.parent)).replace("\\", "/"),
        "published_at": OFFICIAL_PUBLISHED_AT,
        "available_on": OFFICIAL_PUBLISHED_AT[:10],
        "content_sha256": digest,
        "content_length": size,
        "page_count": EXPECTED_PAGE_COUNT,
        "media_type": "application/pdf",
        "document_specific_oversized_handling": {
            "status": "accepted_for_this_document_only",
            "global_default_cap_preserved_bytes": 12 * 1024 * 1024,
            "document_specific_max_bytes": MAX_DOCUMENT_SPECIFIC_BYTES,
            "reason": "psx:260771 exceeds the default 12 MiB transport cap but remains below the exact PSO FY2025 annual-report cap",
        },
        "event_date": "2025-06-30",
        "event_date_basis": "FY2025 completed retail-network/channel expansion disclosed in the annual report; not a per-outlet opening date",
        "event_type": "distribution_network_expansion",
        "event_subtype": "fuel_retail_and_convenience_channel",
        "evidence": evidence_rows,
        "network_reconciliation": {
            "fy2024_ending_network_outlets": prior_ending_network,
            "fy2025_gross_new_outlets": gross_openings,
            "fy2025_ending_network_outlets": ending_network,
            "derived_net_active_change_outlets": net_active_change,
            "unknown_closures_or_reclassifications_outlets": unknown_closures_or_reclassifications,
            "inference_policy": "do_not_infer_the_38_outlet_difference",
        },
        "qualifies_observed_seed": True,
        "case_seed_promoted": False,
        "financial_facts_promoted": False,
    }


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


def _pso_intelligence_cases(intelligence_cases: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    companies = intelligence_cases.get("companies")
    if not isinstance(companies, Mapping):
        return []
    pso = companies.get("PSO")
    if not isinstance(pso, Mapping):
        return []
    cases = pso.get("cases")
    return [row for row in cases if isinstance(row, Mapping)] if isinstance(cases, list) else []


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
    intelligence_cases = load_json(INTELLIGENCE_CASES_PATH, {})

    psx_index_doc = _research_documents(research_index).get(PSX_DOC_ID)
    psx_index_doc = psx_index_doc if isinstance(psx_index_doc, Mapping) else None
    retained_decisive_doc = _documents_table(company_documents).get(PSX_DOC_ID)
    decisive_source = _extract_decisive_source(psx_index_doc)
    observed_seed_defensible = decisive_source.get("qualifies_observed_seed") is True

    pso_events = _pso_operating_events(operating_events)
    pso_distribution_events = [
        event for event in pso_events
        if event.get("event_type") == "distribution_network_expansion"
        or "distribution" in str(event.get("event_subtype") or "").lower()
        or EVENT_REF in str(event.get("event_id") or "")
    ]
    pso_case_count = sum(
        1 for case in _pso_intelligence_cases(intelligence_cases)
        if case.get("case_id") == "case_pso_fy2025_distribution_network_expansion_observed_v1"
        and case.get("status") == "Observed"
    )
    observed_seed_promoted = observed_seed_defensible and len(pso_distribution_events) == 1 and pso_case_count == 1
    if observed_seed_promoted:
        decisive_source["case_seed_promoted"] = True
        decisive_source["financial_facts_promoted"] = False

    gross_openings = 107
    prior_ending_network = 3580
    ending_network = 3649
    net_active_change = ending_network - prior_ending_network
    unknown_closures_or_reclassifications = gross_openings - net_active_change

    if observed_seed_promoted:
        blocked_reasons = [
            "PSO:corroboration_not_independent_originator",
            "PSO:financial_truth_still_not_qualified",
            "PSO:source_bound_operating_observation_only",
        ]
    elif observed_seed_defensible:
        blocked_reasons = [
            "PSO:canonical_operating_event_not_written_by_this_bounded_intake",
            "PSO:case_seed_not_promoted_by_this_bounded_intake",
            "PSO:corporate_card_station_list_is_undated_current_footprint_not_expansion_event",
            "sales_lane:financial_truth_still_not_qualified",
        ]
    else:
        blocked_reasons = [
            "PSO:fy2025_decisive_source_not_retained_hash_page_bound",
            "PSO:canonical_distribution_network_expansion_event_absent",
            "PSO:corporate_card_station_list_is_undated_current_footprint_not_expansion_event",
            "PSO:gross_openings_vs_net_network_change_unreconciled",
            "sales_lane:no_observed_case_seed_permitted",
        ]
    blocked_reasons = sorted(blocked_reasons)

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
        "status": (
            "observed_seed_promoted"
            if observed_seed_promoted
            else "observed_seed_defensible_not_promoted"
            if observed_seed_defensible
            else "evidence_gap_no_observed_seed"
        ),
        "selection_state": (
            "canonical_observed_layer_promoted"
            if observed_seed_promoted
            else "selected_candidate_source_bound_pending_case_promotion"
            if observed_seed_defensible
            else "selected_candidate_pending_evidence_ingestion"
        ),
        "observed_seed_permitted": observed_seed_defensible,
        "event_period_end": "2025-06-30",
        "available_on": decisive_source.get("available_on") if observed_seed_defensible else None,
        "source_cutoff": decisive_source.get("published_at") if observed_seed_defensible else None,
        "audit_authority": AUDIT_PATH,
        "intake_revision": INTAKE_REVISION,
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
                "content_sha256": psx_index_doc.get("content_sha256") if psx_index_doc else decisive_source.get("content_sha256"),
                "qualifies_observed_seed": observed_seed_defensible,
                "no_go_reason": None if observed_seed_defensible else "metadata_only_or_download_failed_without_retained_hash_page_evidence",
            },
            "decisive_psx_260771": decisive_source,
            "company_documents_psx_260771_present": isinstance(retained_decisive_doc, Mapping),
            "operating_events_pso_distribution_candidates": len(pso_distribution_events),
            "intelligence_cases_pso_observed_candidates": pso_case_count,
            "source_registry_pso_document_links": _source_registry_links(_pso_registry(source_registry)),
            "same_issuer_hash_bound_nonqualifying_documents": _retained_same_issuer_bindings(company_documents),
        },
        "reported_fact_candidates_unpromoted": {
            "basis": (
                "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md plus hash/page-bound psx:260771"
                if observed_seed_defensible
                else "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md; not promoted because decisive official FY2025 source is not retained/hash-page-bound in this checkout"
            ),
            "fy2024_ending_network_outlets": prior_ending_network,
            "fy2025_gross_new_outlets": gross_openings,
            "fy2025_ending_network_outlets": ending_network,
            "derived_net_active_change_outlets": net_active_change,
            "unknown_closures_or_reclassifications_outlets": unknown_closures_or_reclassifications,
            "promotion_status": (
                "promoted_to_canonical_observed_layer_reported_facts"
                if observed_seed_promoted
                else "source_bound_not_promoted_to_reported_facts"
                if observed_seed_defensible
                else "not_promoted_to_reported_facts"
            ),
        },
        "epistemic_boundaries": {
            "gross_openings_are_not_net_additions": True,
            "unknown_38_outlet_delta_may_be_closures_replacements_reclassifications_or_counting_basis_change": True,
            "channel_layers_are_nested_not_additive": True,
            "fuel_outlets_convenience_vibe_asaan_safar_and_digital_outlets_must_not_be_double_counted": True,
            "reported_market_share_or_pat_must_not_be_backsolved_as_causal_expansion_impact": True,
        },
        "downstream_status": {
            "intelligence_case_seed": (
                "observed" if observed_seed_promoted else "defensible_not_promoted" if observed_seed_defensible else "blocked"
            ),
            "operating_event": (
                "observed" if observed_seed_promoted else "defensible_not_written" if observed_seed_defensible else "blocked"
            ),
            "financial_forecast": "blocked",
            "scenario_model": "blocked",
            "valuation": "blocked",
            "market_expectations": "blocked",
            "publication": "blocked",
        },
        "blocked_reasons": blocked_reasons,
        "run_receipt": {},
        "policy": {
            "research_only": True,
            "no_advice": True,
            "builder_no_network": True,
            "single_official_pdf_fetched_for_this_bounded_intake": observed_seed_defensible,
            "canonical_observed_layer_promotion_only": observed_seed_promoted,
            "no_promotion": not observed_seed_promoted,
            "no_financial_promotion": True,
            "fail_closed": True,
        },
    }
    receipt["run_receipt"] = {
        "input_sha256": _sha256({
            "research_index_psx_260771": receipt["retained_authority_state"]["research_index_psx_260771"],
            "decisive_psx_260771": receipt["retained_authority_state"]["decisive_psx_260771"],
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
