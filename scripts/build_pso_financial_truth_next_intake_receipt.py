"""Build PSO's fail-closed financial-truth next-intake receipt.

This is intentionally not a parser correction. Current retained PSO financial facts are
audit-only legacy snippets, not canonical, source-bound full-statement facts.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from psx_data import STATE, load_json, save_json


ROOT = Path(__file__).resolve().parent.parent
OUT = STATE / "company_intel" / "pso_financial_truth_next_intake_receipt.json"
TICKER = "PSO"
AUDIT_DATE = "2026-09-13"

INPUT_PATHS = {
    "financial_truth_qualification": STATE / "company_intel" / "financial_truth_qualification.json",
    "financial_coverage": STATE / "company_intel" / "financial_coverage.json",
    "financial_evidence_reconciliation": STATE / "company_intel" / "financial_evidence_reconciliation.json",
    "financial_statement_v2_candidate_queue": STATE / "company_intel" / "financial_statement_v2_candidate_queue.json",
    "company_financial_series": STATE / "company_financial_series.json",
    "company_documents": STATE / "company_documents.json",
    "research_index": STATE / "research_index.json",
    "official_share_capital_candidates": STATE / "company_intel" / "official_share_capital_candidates.json",
    "official_share_capital_approvals": STATE / "company_intel" / "official_share_capital_approvals.json",
}

PRIMARY_HASH_BOUND_TARGETS = ("psx:257951", "psx:263690", "psx:270316", "psx:275672")
METADATA_ONLY_RESTAGE_TARGETS = ("psx:260771", "psx:264179", "psx:276065")
ALL_TARGETS = PRIMARY_HASH_BOUND_TARGETS + METADATA_ONLY_RESTAGE_TARGETS


def _company(payload: dict[str, Any], symbol: str = TICKER) -> dict[str, Any]:
    companies = payload.get("companies") or {}
    return companies.get(symbol) or payload.get(symbol) or {}


def _facts_for_symbol(payload: dict[str, Any], symbol: str = TICKER) -> list[dict[str, Any]]:
    company = _company(payload, symbol)
    if isinstance(company.get("facts"), list):
        return list(company.get("facts") or [])
    tickers = payload.get("tickers") or {}
    if isinstance(tickers, dict) and isinstance((tickers.get(symbol) or {}).get("facts"), list):
        return list((tickers.get(symbol) or {}).get("facts") or [])
    if payload.get("ticker") == symbol and isinstance(payload.get("facts"), list):
        return list(payload.get("facts") or [])
    if payload.get("symbol") == symbol and isinstance(payload.get("facts"), list):
        return list(payload.get("facts") or [])
    return []


def _file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256(path.read_bytes()).hexdigest()


def _periods(node: dict[str, Any]) -> list[str]:
    return list(node.get("qualified_periods") or node.get("periods") or [])


def _coverage_from_truth(row: dict[str, Any]) -> dict[str, Any]:
    model_ready = row.get("model_ready_financial_statement_coverage") or {}
    annual_schedule = model_ready.get("annual") or {}
    quarter_schedule = model_ready.get("reported_quarter") or {}
    share = row.get("share_count") or {}
    return {
        "annual_income_triplets": {
            "required": (row.get("annual_income_triplets") or {}).get("required", 5),
            "present": (row.get("annual_income_triplets") or {}).get("present", 0),
            "qualified_periods": _periods(row.get("annual_income_triplets") or {}),
        },
        "reported_quarter_fact_sets": {
            "required": (row.get("qualified_reported_quarter_fact_sets") or {}).get("required", 8),
            "present": (row.get("qualified_reported_quarter_fact_sets") or {}).get("present", 0),
            "qualified_periods": _periods(row.get("qualified_reported_quarter_fact_sets") or {}),
        },
        "annual_operating_cash_flow": {
            "required": (row.get("annual_operating_cash_flow") or {}).get("required", 5),
            "present": (row.get("annual_operating_cash_flow") or {}).get("present", 0),
            "qualified_periods": _periods(row.get("annual_operating_cash_flow") or {}),
        },
        "annual_full_statement_schedules": {
            "required": annual_schedule.get("required", 5),
            "present": annual_schedule.get("present", 0),
            "qualified_periods": _periods(annual_schedule),
        },
        "reported_quarter_full_statement_schedules": {
            "required": quarter_schedule.get("required", 8),
            "present": quarter_schedule.get("present", 0),
            "qualified_periods": _periods(quarter_schedule),
        },
        "official_share_count_capital_note_tie_out": {
            "required": 1,
            "present": 1 if share.get("status") == "qualified" else 0,
            "status": share.get("status") or "missing_official_share_count_capital_note_tie_out",
            "source": share.get("source"),
            "available_on": share.get("available_on"),
        },
    }


def _doc_record(doc_id: str, docs: dict[str, Any], research_index: dict[str, Any]) -> dict[str, Any]:
    doc = docs.get(doc_id) or {}
    research = research_index.get(doc_id) or {}
    source = doc.get("source") or {}
    url = doc.get("source_url") or source.get("url") or research.get("url")
    label = doc.get("title") or doc.get("label") or research.get("title") or research.get("label")
    content_sha = doc.get("content_sha256") or doc.get("content_sha") or source.get("content_sha256")
    return {
        "document_id": doc_id,
        "label": label,
        "url": url,
        "published_at": doc.get("published_at") or research.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "status": doc.get("status"),
        "content_sha256": content_sha,
        "company_documents_present": bool(doc),
        "hash_bound": bool(content_sha),
        "evidence_count": len(doc.get("evidence") or []),
        "source_registry_or_research_index_present": bool(research),
    }


def _share_capital_summary(candidates: dict[str, Any], approvals: dict[str, Any]) -> dict[str, Any]:
    candidate_records = [
        item for item in candidates.get("candidates", [])
        if item.get("symbol") == TICKER
    ]
    approved_records = [
        item for item in approvals.get("records", [])
        if item.get("symbol") == TICKER
        and item.get("record_type") == "official_share_count_capital_note_tie_out"
        and item.get("approved") is True
    ]
    return {
        "candidate_count": len(candidate_records),
        "approved_tie_out_count": len(approved_records),
        "candidate_fact_ids": [item.get("fact_id") for item in candidate_records if item.get("fact_id")],
        "approved_fact_ids": [item.get("fact_id") for item in approved_records if item.get("fact_id")],
        "status": "missing_for_pso" if not approved_records else "approved_tie_out_present",
    }


def build(write: bool = True) -> dict[str, Any]:
    truth = load_json(INPUT_PATHS["financial_truth_qualification"], {"companies": {}})
    coverage = load_json(INPUT_PATHS["financial_coverage"], {"companies": {}})
    reconciliation = load_json(INPUT_PATHS["financial_evidence_reconciliation"], {"companies": {}})
    v2_queue = load_json(INPUT_PATHS["financial_statement_v2_candidate_queue"], {"companies": {}})
    series = load_json(INPUT_PATHS["company_financial_series"], {})
    docs_payload = load_json(INPUT_PATHS["company_documents"], {})
    docs = docs_payload.get("documents") or docs_payload
    research_payload = load_json(INPUT_PATHS["research_index"], {})
    research_index = research_payload.get("documents") or research_payload
    candidates = load_json(INPUT_PATHS["official_share_capital_candidates"], {"candidates": []})
    approvals = load_json(INPUT_PATHS["official_share_capital_approvals"], {"records": []})

    truth_row = _company(truth)
    coverage_row = _company(coverage)
    reconciliation_row = _company(reconciliation)
    series_facts = _facts_for_symbol(series)
    reconciliation_facts = _facts_for_symbol(reconciliation)
    before = _coverage_from_truth(truth_row)
    share_summary = _share_capital_summary(candidates, approvals)

    audit_only_facts = [fact for fact in series_facts if fact.get("readiness") == "audit_only"]
    eligible_facts = [fact for fact in reconciliation_facts if fact.get("status") == "eligible"]
    v2_row = _company(v2_queue) if v2_queue.get("companies") else (v2_queue if v2_queue.get("ticker") == TICKER else {})

    receipt = {
        "schema_version": 1,
        "receipt_type": "pso_financial_truth_next_intake_receipt",
        "ticker": TICKER,
        "status": "next_intake_required_no_parser_correction",
        "audit_date": AUDIT_DATE,
        "decision": {
            "parser_correction_eligible": False,
            "reason": (
                "Retained PSO facts are audit-only legacy snippets with zero eligible reconciliation facts, "
                "zero v2 candidates, incomplete canonical slots, and no PSO official share-capital tie-out."
            ),
            "financial_truth_state_changed": False,
            "downstream_status": truth_row.get("downstream", {}),
        },
        "coverage_before": before,
        "coverage_after": before,
        "fact_inventory": {
            "series_fact_count": len(series_facts),
            "series_audit_only_fact_count": len(audit_only_facts),
            "reconciliation_eligible_fact_count": len(eligible_facts),
            "reconciliation_audit_only_fact_count": reconciliation_row.get("audit_only_fact_count", 0),
            "reconciliation_missing_slot_count": reconciliation_row.get("missing_slot_count", 0),
            "financial_statement_v2_candidate_count": v2_row.get("candidate_count", 0),
            "share_capital": share_summary,
            "audit_only_fact_ids_not_promoted": [
                fact.get("fact_id") for fact in audit_only_facts if fact.get("fact_id")
            ],
        },
        "retained_official_candidate_documents": {
            "primary_hash_bound_fact_qualification_wave": [
                _doc_record(doc_id, docs, research_index) for doc_id in PRIMARY_HASH_BOUND_TARGETS
            ],
            "metadata_only_restage_wave": [
                _doc_record(doc_id, docs, research_index) for doc_id in METADATA_ONLY_RESTAGE_TARGETS
            ],
            "financial_coverage_indexed_document_count": coverage_row.get("indexed_official_financial_doc_count"),
            "financial_coverage_queue_id": (coverage_row.get("qualification_queue") or {}).get("queue_id"),
        },
        "missing_slots": [
            {
                "slot": "annual_income_triplets",
                "required": 5,
                "present": before["annual_income_triplets"]["present"],
                "smallest_retained_candidate_ids": ["psx:257951"],
                "remaining_need": "four more annual periods need exact retained official annual result/report IDs before qualification.",
            },
            {
                "slot": "reported_direct_quarter_fact_sets",
                "required": 8,
                "present": before["reported_quarter_fact_sets"]["present"],
                "smallest_retained_candidate_ids": ["psx:263690", "psx:270316", "psx:275672"],
                "restage_candidates_for_statement_report_pages": ["psx:264179", "psx:276065"],
                "remaining_need": "five more direct quarters need exact retained official report/result IDs before qualification.",
            },
            {
                "slot": "annual_operating_cash_flow",
                "required": 5,
                "present": before["annual_operating_cash_flow"]["present"],
                "smallest_retained_candidate_ids": ["psx:260771"],
                "remaining_need": "all five annual OCF periods require source-bound cash-flow statement facts.",
            },
            {
                "slot": "full_income_balance_cash_flow_schedules",
                "required": {"annual": 5, "reported_quarter": 8},
                "present": {
                    "annual": before["annual_full_statement_schedules"]["present"],
                    "reported_quarter": before["reported_quarter_full_statement_schedules"]["present"],
                },
                "smallest_retained_candidate_ids": list(ALL_TARGETS),
                "remaining_need": "canonical direct metrics must be extracted with statement type, period type, page, hash, and availability binding.",
            },
            {
                "slot": "official_share_count_capital_note_tie_out",
                "required": 1,
                "present": before["official_share_count_capital_note_tie_out"]["present"],
                "smallest_retained_candidate_ids": ["psx:260771"],
                "remaining_need": "PSO has no retained approved share-capital candidate or tie-out record.",
            },
        ],
        "next_action": {
            "type": "owner_approved_bounded_restage_and_fact_qualification_wave",
            "does_not_fetch": True,
            "does_not_promote_audit_only_facts": True,
            "ordered_targets": [
                {
                    "rank": 1,
                    "document_ids": list(PRIMARY_HASH_BOUND_TARGETS),
                    "purpose": "Attempt source-bound qualification from already retained/hash-bound official PSX result documents only where canonical direct facts are present.",
                    "promotion_condition": "Every emitted fact must include canonical metric, statement type, period type/duration, consolidation, page, source URL, content hash, published_at/available_on, and eligibility scope.",
                },
                {
                    "rank": 2,
                    "document_ids": list(METADATA_ONLY_RESTAGE_TARGETS),
                    "purpose": "Restage official annual/quarterly statement filings already known by ID before seeking full schedules, OCF, and share-capital tie-out.",
                    "promotion_condition": "No fact may be emitted until the document is retained with exact URL/hash/page/availability binding.",
                },
            ],
        },
        "policy": {
            "fail_closed": True,
            "no_fetch": True,
            "no_forecast": True,
            "no_valuation": True,
            "no_market_expectations": True,
            "audit_only_values_not_promoted": True,
            "research_only_no_advice_language": True,
            "do_not_touch_sales_expansion_receipt": True,
        },
        "_meta": {
            "generator_version": "pso_financial_truth_next_intake_receipt_v1",
            "inputs_sha256": {name: _file_sha(path) for name, path in sorted(INPUT_PATHS.items())},
            "artifact_path": "state/company_intel/pso_financial_truth_next_intake_receipt.json",
            "timestamp_semantics": {
                "audit_date": "local audit date only; not a source-effective or source-published date"
            },
        },
    }
    if write:
        save_json(OUT, receipt)
    return receipt


if __name__ == "__main__":
    result = build(write=True)
    before = result["coverage_before"]
    print(
        "pso_financial_truth_next_intake_receipt: "
        f"{result['status']} "
        f"annual={before['annual_income_triplets']['present']}/5 "
        f"quarters={before['reported_quarter_fact_sets']['present']}/8 "
        f"ocf={before['annual_operating_cash_flow']['present']}/5 "
        f"share={before['official_share_count_capital_note_tie_out']['present']}/1"
    )
