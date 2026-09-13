"""Build MARI's fail-closed financial-truth next-intake receipt.

This is not a parser correction. Current retained MARI facts are audit-only or
metadata leads, not canonical source-bound full-statement facts.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "mari_financial_truth_next_intake_receipt.json"
TICKER = "MARI"
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
    "mari_enp_evidence_readiness": STATE / "company_intel" / "mari_enp_evidence_readiness.json",
}

HASH_BOUND_STATEMENT_TARGETS = ("psx:275583", "psx:271327", "psx:264550")
METADATA_ONLY_FINANCIAL_TARGETS = (
    "psx:280901",
    "psx:274864",
    "psx:269182",
    "psx:bd312748aa6ef5cd050cfc1a",
    "psx:258895",
    "psx:257577",
)
ENP_SECTOR_KPI_EVENT_TARGETS = ("psx:260446", "psx:265594")


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
    return []


def _file_sha(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


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
            "present": 1 if share.get("status") == "official_share_count_capital_note_tied_out" else 0,
            "status": share.get("status") or "missing_official_share_count_capital_note_tie_out",
            "source": share.get("source"),
            "available_on": share.get("available_on"),
        },
    }


def _doc_lookup(doc_id: str, docs: dict[str, Any], research_index: dict[str, Any], coverage_docs: dict[str, Any]) -> dict[str, Any]:
    doc = docs.get(doc_id) or {}
    research = research_index.get(doc_id) or {}
    coverage = coverage_docs.get(doc_id) or {}
    source = doc.get("source") or {}
    content_sha = (
        doc.get("content_sha256")
        or doc.get("content_sha")
        or source.get("content_sha256")
        or coverage.get("content_sha256")
    )
    return {
        "document_id": doc_id,
        "label": doc.get("title") or doc.get("label") or coverage.get("title") or research.get("title"),
        "url": doc.get("source_url") or source.get("url") or coverage.get("source_url") or research.get("url"),
        "published_at": doc.get("published_at") or coverage.get("published_at") or research.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "safe_period": coverage.get("safe_period"),
        "content_sha256": content_sha,
        "company_documents_present": bool(doc),
        "hash_bound": bool(content_sha),
        "evidence_count": len(doc.get("evidence") or []),
    }


def _share_summary(candidates: dict[str, Any], approvals: dict[str, Any]) -> dict[str, Any]:
    candidate_records = [item for item in candidates.get("candidates", []) if item.get("symbol") == TICKER]
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
        "status": "missing_for_mari" if not approved_records else "approved_tie_out_present",
    }


def build(write: bool = True) -> dict[str, Any]:
    truth = load_json(INPUT_PATHS["financial_truth_qualification"], {"companies": {}})
    coverage = load_json(INPUT_PATHS["financial_coverage"], {"companies": {}})
    reconciliation = load_json(INPUT_PATHS["financial_evidence_reconciliation"], {"companies": {}})
    v2_queue = load_json(INPUT_PATHS["financial_statement_v2_candidate_queue"], {"companies": {}})
    series = load_json(INPUT_PATHS["company_financial_series"], {})
    docs_payload = load_json(INPUT_PATHS["company_documents"], {})
    research_payload = load_json(INPUT_PATHS["research_index"], {})
    candidates = load_json(INPUT_PATHS["official_share_capital_candidates"], {"candidates": []})
    approvals = load_json(INPUT_PATHS["official_share_capital_approvals"], {"records": []})
    enp = load_json(INPUT_PATHS["mari_enp_evidence_readiness"], {})

    truth_row = _company(truth)
    coverage_row = _company(coverage)
    reconciliation_row = _company(reconciliation)
    series_facts = _facts_for_symbol(series)
    reconciliation_facts = _facts_for_symbol(reconciliation)
    before = _coverage_from_truth(truth_row)
    docs = docs_payload.get("documents") or docs_payload
    research_index = research_payload.get("documents") or research_payload
    coverage_docs = {
        doc.get("document_id"): doc
        for doc in coverage_row.get("indexed_official_financial_docs") or []
        if isinstance(doc, dict) and doc.get("document_id")
    }
    v2_row = _company(v2_queue) if v2_queue.get("companies") else {}
    audit_only_facts = [fact for fact in series_facts if fact.get("readiness") == "audit_only"]
    eligible_facts = [fact for fact in reconciliation_facts if fact.get("status") == "eligible"]
    metric_counts = Counter(fact.get("metric") for fact in series_facts)

    receipt = {
        "schema_version": 1,
        "receipt_type": "mari_financial_truth_next_intake_receipt",
        "ticker": TICKER,
        "status": "next_intake_required_no_parser_correction",
        "audit_date": AUDIT_DATE,
        "decision": {
            "parser_correction_eligible": False,
            "reason": (
                "Retained MARI financial facts remain audit-only with zero eligible reconciliation facts, "
                "zero statement-v2 candidates, no official share-capital tie-out, and no complete annual "
                "or reported-quarter full-statement schedules."
            ),
            "financial_truth_state_changed": False,
            "downstream_status": truth_row.get("downstream", {}),
        },
        "coverage_before": before,
        "coverage_after": before,
        "fact_inventory": {
            "series_fact_count": len(series_facts),
            "series_audit_only_fact_count": len(audit_only_facts),
            "series_metric_counts": dict(sorted(metric_counts.items())),
            "reconciliation_eligible_fact_count": len(eligible_facts),
            "reconciliation_audit_only_fact_count": reconciliation_row.get("audit_only_fact_count", 0),
            "reconciliation_missing_slot_count": reconciliation_row.get("missing_slot_count", 0),
            "reconciliation_source_conflict_count": reconciliation_row.get("source_conflict_count", 0),
            "financial_statement_v2_candidate_count": v2_row.get("candidate_count", 0),
            "share_capital": _share_summary(candidates, approvals),
            "audit_only_fact_ids_not_promoted": [
                fact.get("fact_id") for fact in audit_only_facts if fact.get("fact_id")
            ],
        },
        "retained_official_candidate_documents": {
            "hash_bound_statement_restage_wave": [
                _doc_lookup(doc_id, docs, research_index, coverage_docs)
                for doc_id in HASH_BOUND_STATEMENT_TARGETS
            ],
            "metadata_only_financial_restage_wave": [
                _doc_lookup(doc_id, docs, research_index, coverage_docs)
                for doc_id in METADATA_ONLY_FINANCIAL_TARGETS
            ],
            "financial_coverage_indexed_document_count": coverage_row.get("indexed_official_financial_doc_count"),
            "financial_coverage_queue_id": (coverage_row.get("qualification_queue") or {}).get("queue_id"),
        },
        "missing_slots": [
            {
                "slot": "annual_income_triplets",
                "required": 5,
                "present": before["annual_income_triplets"]["present"],
                "smallest_retained_candidate_ids": ["psx:280901", "psx:258895", "psx:257577"],
                "remaining_need": "five annual revenue/PAT/EPS triplets must be parsed from source-bound annual result/report filings before qualification.",
            },
            {
                "slot": "reported_direct_quarter_fact_sets",
                "required": 8,
                "present": before["reported_quarter_fact_sets"]["present"],
                "smallest_retained_candidate_ids": [
                    "psx:275583",
                    "psx:274864",
                    "psx:271327",
                    "psx:269182",
                    "psx:264550",
                    "psx:bd312748aa6ef5cd050cfc1a",
                ],
                "remaining_need": "eight reported-quarter revenue/PAT/EPS fact sets need exact period, duration, page, hash, and eligibility-scope binding.",
            },
            {
                "slot": "annual_operating_cash_flow",
                "required": 5,
                "present": before["annual_operating_cash_flow"]["present"],
                "smallest_retained_candidate_ids": ["psx:258895"],
                "remaining_need": "all five annual OCF periods require source-bound cash-flow statement facts.",
            },
            {
                "slot": "full_income_balance_cash_flow_schedules",
                "required": {"annual": 5, "reported_quarter": 8},
                "present": {
                    "annual": before["annual_full_statement_schedules"]["present"],
                    "reported_quarter": before["reported_quarter_full_statement_schedules"]["present"],
                },
                "smallest_retained_candidate_ids": list(HASH_BOUND_STATEMENT_TARGETS + METADATA_ONLY_FINANCIAL_TARGETS),
                "remaining_need": "canonical direct metrics plus EBITDA/FCF operand lineage must be extracted with statement type, period type, page, hash, and availability binding.",
            },
            {
                "slot": "official_share_count_capital_note_tie_out",
                "required": 1,
                "present": before["official_share_count_capital_note_tie_out"]["present"],
                "smallest_retained_candidate_ids": ["psx:258895"],
                "remaining_need": "MARI has no retained approved share-count capital-note candidate or tie-out record.",
            },
            {
                "slot": "sector_kpi_schedule",
                "required": "e_and_p_numeric_driver_schedule",
                "present": 0,
                "smallest_retained_candidate_ids": list(ENP_SECTOR_KPI_EVENT_TARGETS),
                "status": (enp.get("event") or {}).get("status") or "blocked",
                "remaining_need": "Observed E&P event filings are hash/page-backed, but numeric driver operands remain unavailable and cannot activate a sector KPI schedule.",
            },
        ],
        "next_action": {
            "type": "owner_approved_bounded_restage_and_fact_qualification_wave",
            "does_not_fetch": True,
            "does_not_promote_audit_only_facts": True,
            "ordered_targets": [
                {
                    "rank": 1,
                    "document_ids": list(HASH_BOUND_STATEMENT_TARGETS),
                    "purpose": "Restage already retained/hash-bound quarterly statement filings and qualify only exact canonical facts that already have page/hash/period binding.",
                    "promotion_condition": "Every fact must include canonical metric, statement type, period type/duration, consolidation, page, source URL, content hash, published_at/available_on, and financial-truth eligibility scope.",
                },
                {
                    "rank": 2,
                    "document_ids": list(METADATA_ONLY_FINANCIAL_TARGETS),
                    "purpose": "Retain/hash annual and results metadata leads before attempting annual coverage, OCF, share-count, and reported-quarter qualification.",
                    "promotion_condition": "No fact may be emitted until the document has exact URL/hash/page/availability binding.",
                },
                {
                    "rank": 3,
                    "document_ids": list(ENP_SECTOR_KPI_EVENT_TARGETS),
                    "purpose": "Keep E&P event documents observed-only unless official numeric driver operands become source-bound.",
                    "promotion_condition": "Sector KPI schedule remains blocked without working-interest economics, production/reserve/timing operands, and qualified financial truth.",
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
        },
        "_meta": {
            "generator_version": "mari_financial_truth_next_intake_receipt_v1",
            "inputs_sha256": {name: _file_sha(path) for name, path in sorted(INPUT_PATHS.items())},
            "artifact_path": "state/company_intel/mari_financial_truth_next_intake_receipt.json",
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
        "mari_financial_truth_next_intake_receipt: "
        f"{result['status']} "
        f"annual={before['annual_income_triplets']['present']}/5 "
        f"quarters={before['reported_quarter_fact_sets']['present']}/8 "
        f"ocf={before['annual_operating_cash_flow']['present']}/5 "
        f"share={before['official_share_count_capital_note_tie_out']['present']}/1"
    )
