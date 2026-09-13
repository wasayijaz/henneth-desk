"""Attempt PSO hash-bound financial-truth tranche reparse, fail-closed.

The current approved parser needs exact local PDF bytes (or transient page
geometry supplied by the ingestion queue).  This builder never fetches.  It
parses a document only when an existing retained local path is present and its
bytes match the saved content hash.  Otherwise it records a zero-delta blocked
attempt per document.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from document_extract import extract_local
from financial_series import normalize_fact
from financial_statement_facts import PARSER_REVISION, PARSER_VERSION, extract_facts
from psx_data import ROOT, STATE, load_json, save_json
from share_capital import extract_share_capital_evidence


OUT = STATE / "company_intel" / "pso_hashbound_tranche_reparse_attempt.json"
TICKER = "PSO"
TRANCHE_DOCUMENT_IDS = ("psx:257951", "psx:263690", "psx:270316", "psx:275672")
ATTEMPT_DATE = "2026-09-13"

INPUT_PATHS = {
    "company_documents": STATE / "company_documents.json",
    "company_financial_series": STATE / "company_financial_series.json",
    "financial_evidence_reconciliation": STATE / "company_intel" / "financial_evidence_reconciliation.json",
    "financial_truth_qualification": STATE / "company_intel" / "financial_truth_qualification.json",
    "official_share_capital_candidates": STATE / "company_intel" / "official_share_capital_candidates.json",
    "official_share_capital_approvals": STATE / "company_intel" / "official_share_capital_approvals.json",
    "source_registry": STATE / "company_intel" / "source_registry.json",
    "extraction_queue": ROOT / ".cache" / "company_intel" / "extraction_queue.json",
}

TARGET_FACT_LINES = (
    "revenue",
    "gross_profit",
    "operating_profit",
    "finance_cost",
    "profit_before_tax",
    "tax_expense",
    "profit_after_tax_attributable",
    "basic_eps",
    "operating_cash_flow",
    "capital_expenditure",
    "net_cash_from_investing_activities",
    "net_cash_from_financing_activities",
    "dividends_paid",
    "cash_and_cash_equivalents",
    "trade_receivables",
    "inventories",
    "total_current_assets",
    "property_plant_equipment",
    "total_assets",
    "short_term_borrowings",
    "long_term_borrowings",
    "trade_payables",
    "total_equity",
)


def _file_sha(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _documents(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("documents") if isinstance(payload.get("documents"), dict) else payload
    return {str(key): row for key, row in (rows or {}).items() if isinstance(row, dict)}


def _company(payload: dict[str, Any], symbol: str = TICKER) -> dict[str, Any]:
    return (payload.get("companies") or {}).get(symbol) or payload.get(symbol) or {}


def _periods(node: dict[str, Any]) -> list[str]:
    return list(node.get("qualified_periods") or node.get("periods") or [])


def _coverage_from_truth(row: dict[str, Any]) -> dict[str, Any]:
    model_ready = row.get("model_ready_financial_statement_coverage") or {}
    annual = model_ready.get("annual") or {}
    quarter = model_ready.get("reported_quarter") or {}
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
            "required": annual.get("required", 5),
            "present": annual.get("present", 0),
            "qualified_periods": _periods(annual),
        },
        "reported_quarter_full_statement_schedules": {
            "required": quarter.get("required", 8),
            "present": quarter.get("present", 0),
            "qualified_periods": _periods(quarter),
        },
        "official_share_count_capital_note_tie_out": {
            "required": 1,
            "present": 1 if share.get("status") in {
                "qualified",
                "official_share_count_capital_note_tied_out",
            } else 0,
            "status": share.get("status") or "missing_official_share_count_capital_note_tie_out",
            "available_on": share.get("available_on"),
            "source": share.get("source"),
        },
    }


def _facts_for_symbol(series: dict[str, Any], symbol: str = TICKER) -> list[dict[str, Any]]:
    ticker_row = (series.get("tickers") or {}).get(symbol) or {}
    return list(ticker_row.get("facts") or [])


def _existing_fact_ids(series: dict[str, Any], doc_id: str) -> set[str]:
    return {
        str(fact.get("fact_id"))
        for fact in _facts_for_symbol(series)
        if fact.get("document_id") == doc_id and fact.get("fact_id")
    }


def _doc_local_path(doc: dict[str, Any]) -> str | None:
    download = doc.get("download") if isinstance(doc.get("download"), dict) else {}
    value = doc.get("local_path") or doc.get("path") or download.get("local_path") or download.get("path") or download.get("file")
    return str(value) if value else None


def _transient_path(doc_id: str, extraction_queue: Any) -> str | None:
    rows = extraction_queue
    if isinstance(rows, dict):
        rows = rows.get("documents") or rows.get("queue") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("doc_id") == doc_id and row.get("path"):
            return str(row.get("path"))
    return None


def _candidate_path(doc_id: str, doc: dict[str, Any], extraction_queue: Any) -> str | None:
    return _doc_local_path(doc) or _transient_path(doc_id, extraction_queue)


def _safe_existing_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _fresh_fact_ok(row: dict[str, Any], doc: dict[str, Any]) -> bool:
    if row.get("parser_version") != PARSER_VERSION or row.get("parser_revision") != PARSER_REVISION:
        return False
    if row.get("document_id") != doc.get("doc_id"):
        return False
    if row.get("content_sha256") != doc.get("content_sha256"):
        return False
    if row.get("source_url") != doc.get("source_url"):
        return False
    if row.get("metric") not in TARGET_FACT_LINES:
        return False
    evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
    if not evidence or not all(item.get("page") and item.get("source_url") == doc.get("source_url") for item in evidence if isinstance(item, dict)):
        return False
    if not row.get("statement_type") or row.get("consolidation") != "consolidated" or not row.get("period_end"):
        return False
    if row.get("currency") != "PKR" and row.get("metric") != "basic_eps":
        return False
    if row.get("unit") not in {"PKR", "PKR/share"}:
        return False
    if row.get("available_on") is None:
        return False
    return row.get("readiness") == "model_loadable"


def _attempt_document(
    doc_id: str,
    doc: dict[str, Any],
    series: dict[str, Any],
    source_registry: dict[str, Any],
    extraction_queue: Any,
) -> dict[str, Any]:
    expected_hash = str(doc.get("content_sha256") or "").lower()
    local_sha = str(doc.get("local_sha256") or "").lower()
    source_url = str(doc.get("source_url") or "")
    existing_before = _existing_fact_ids(series, doc_id)
    base = {
        "document_id": doc_id,
        "title": doc.get("title"),
        "source_url": source_url,
        "published_at": doc.get("published_at"),
        "available_on": doc.get("available_on"),
        "status": doc.get("status"),
        "company_documents_present": bool(doc),
        "content_sha256": expected_hash or None,
        "local_sha256": local_sha or None,
        "hash_bound": bool(expected_hash and local_sha == expected_hash),
        "existing_series_fact_ids": sorted(existing_before),
        "existing_series_fact_count": len(existing_before),
        "fresh_parser_fact_count": 0,
        "fresh_model_loadable_fact_count": 0,
        "fresh_share_capital_candidate_count": 0,
        "fresh_fact_ids": [],
        "fresh_share_capital_fact_ids": [],
        "delta_series_fact_count": 0,
        "delta_financial_truth_coverage_count": 0,
        "parser_version": PARSER_VERSION,
        "parser_revision": PARSER_REVISION,
    }
    if not doc:
        return {**base, "attempt_status": "blocked_document_record_missing", "blocker": "company_documents_record_missing"}
    if doc.get("status") != "ready":
        return {**base, "attempt_status": "blocked_document_not_ready", "blocker": "company_documents_status_not_ready"}
    if not base["hash_bound"]:
        return {**base, "attempt_status": "blocked_hash_mismatch_or_missing", "blocker": "content_sha256_and_local_sha256_must_match"}
    path = _safe_existing_path(_candidate_path(doc_id, doc, extraction_queue))
    if path is None:
        return {
            **base,
            "attempt_status": "blocked_exact_retained_bytes_absent",
            "blocker": "no_retained_local_pdf_path_or_transient_extraction_queue_path",
            "parser_invoked": False,
        }
    extracted = extract_local(path)
    if extracted.get("content_sha256") != expected_hash:
        return {
            **base,
            "attempt_status": "blocked_local_bytes_hash_mismatch",
            "blocker": "local_bytes_sha256_does_not_match_company_documents_content_sha256",
            "observed_local_sha256": extracted.get("content_sha256"),
            "parser_invoked": False,
        }
    parser_doc = {
        "doc_id": doc_id,
        "title": doc.get("title"),
        "source_url": source_url,
        "content_sha256": expected_hash,
        "period_end": doc.get("period_end"),
        "published_at": doc.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "available_on": doc.get("available_on"),
        "symbol": TICKER,
        "page_count": len(extracted.get("pages") or []),
    }
    raw_facts = extract_facts(parser_doc, extracted.get("pages") or [], extracted.get("words"), extracted.get("page_records"))
    normalized = [
        row for fact in raw_facts
        if (row := normalize_fact({**doc, "doc_id": doc_id}, fact, pages=extracted.get("pages") or [], source_registry=source_registry))
    ]
    qualified = [row for row in normalized if _fresh_fact_ok(row, {**doc, "doc_id": doc_id})]
    share_candidates = extract_share_capital_evidence(parser_doc, extracted.get("pages") or [], extracted.get("page_records"))
    return {
        **base,
        "attempt_status": "parsed_exact_retained_bytes",
        "parser_invoked": True,
        "fresh_parser_fact_count": len(normalized),
        "fresh_model_loadable_fact_count": len(qualified),
        "fresh_share_capital_candidate_count": len(share_candidates),
        "fresh_fact_ids": [row.get("fact_id") for row in qualified if row.get("fact_id")],
        "fresh_share_capital_fact_ids": [row.get("fact_id") for row in share_candidates if row.get("fact_id")],
        "delta_series_fact_count": 0,
        "delta_financial_truth_coverage_count": 0,
        "qualified_fact_rows_not_persisted": qualified[:40],
        "share_capital_candidates_not_persisted": share_candidates[:20],
    }


def _review_candidate(
    attempts: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    """Summarise fresh receipt-only facts without creating canonical state.

    This is deliberately a review artifact, not a promotion decision.  The
    PSO reprocess path has no owner-approved allowlist/manifest, so even a
    complete direct-quarter set must remain outside financial_series and the
    financial-truth qualification state until that boundary is approved.
    """
    rows = [
        row
        for attempt in attempts
        for row in (attempt.get("qualified_fact_rows_not_persisted") or [])
        if isinstance(row, dict) and row.get("document_id") == "psx:275672"
    ]
    metrics = {"revenue", "profit_after_tax_attributable", "basic_eps"}

    def _metric_set(duration: int, period_end: str, role: str) -> list[str]:
        return sorted({
            str(row.get("metric"))
            for row in rows
            if row.get("duration_months") == duration
            and row.get("period_end") == period_end
            and row.get("column_role") == role
        })

    current_direct = _metric_set(3, "2026-03-31", "current_period")
    comparative_direct = _metric_set(3, "2025-03-31", "comparative_prior_period")
    current_cumulative = _metric_set(9, "2026-03-31", "current_period")
    comparative_cumulative = _metric_set(9, "2025-03-31", "comparative_prior_period")
    source_doc = next((attempt for attempt in attempts if attempt.get("document_id") == "psx:275672"), {})
    source_rows = rows or [{}]
    evidence_pages = sorted({
        item.get("page")
        for row in source_rows
        for item in (row.get("evidence") or [])
        if isinstance(item, dict) and item.get("page") is not None
    })
    reconciliation_company = _company(reconciliation)
    conflicts = reconciliation_company.get("conflicts") or []
    return {
        "status": "owner_approval_required",
        "review_scope": "receipt-only candidate facts; no canonical state write",
        "candidate_document_id": "psx:275672",
        "candidate_fact_ids": sorted({str(row.get("fact_id")) for row in rows if row.get("fact_id")}),
        "candidate_fact_count": len(rows),
        "source": {
            "name": "PSX DPS",
            "source_url": source_doc.get("source_url"),
            "content_sha256": source_doc.get("content_sha256"),
            "page": evidence_pages,
            "statement_type": sorted({str(row.get("statement_type")) for row in rows}),
            "consolidation": sorted({str(row.get("consolidation")) for row in rows}),
            "currency": sorted({str(row.get("currency")) for row in rows}),
            "unit_multiplier": sorted({row.get("unit_multiplier") for row in rows}),
            "unit_scale_by_unit": {
                str(unit): sorted({row.get("unit_multiplier") for row in rows if row.get("unit") == unit})
                for unit in sorted({str(row.get("unit")) for row in rows})
            },
        },
        "period_mapping": {
            "current_direct_quarter": {
                "period_end": "2026-03-31",
                "duration_months": 3,
                "column_role": "current_period",
                "metrics": current_direct,
                "required_metrics": sorted(metrics),
                "complete_direct_quarter_triplet": metrics.issubset(set(current_direct)),
            },
            "comparative_direct_quarter": {
                "period_end": "2025-03-31",
                "duration_months": 3,
                "column_role": "comparative_prior_period",
                "comparative_to_period_end": "2026-03-31",
                "metrics": comparative_direct,
                "required_metrics": sorted(metrics),
                "complete_direct_quarter_triplet": metrics.issubset(set(comparative_direct)),
            },
            "current_cumulative": {
                "period_end": "2026-03-31",
                "duration_months": 9,
                "column_role": "current_period",
                "metrics": current_cumulative,
                "required_metrics": sorted(metrics),
                "complete_cumulative_income_triplet": metrics.issubset(set(current_cumulative)),
            },
            "comparative_cumulative": {
                "period_end": "2025-03-31",
                "duration_months": 9,
                "column_role": "comparative_prior_period",
                "comparative_to_period_end": "2026-03-31",
                "metrics": comparative_cumulative,
                "required_metrics": sorted(metrics),
                "complete_cumulative_income_triplet": metrics.issubset(set(comparative_cumulative)),
            },
        },
        "duplicate_status": "no_duplicate_eligible_facts_written",
        "conflict_status": "no_canonical_conflicts_in_current_state" if not conflicts else "canonical_conflicts_present",
        "canonical_source_conflict_count": len(conflicts),
        "promotion_status": "not_promoted",
        "promotion_boundary": (
            "The existing canonical owner-approved reprocess path has no PSO allowlist or manifest; "
            "explicit owner approval is required before financial_series or financial_truth promotion."
        ),
        "authoritative_delta": {
            "series_fact_count": 0,
            "financial_truth_coverage_count": 0,
        },
    }


def build(write: bool = True) -> dict[str, Any]:
    docs_payload = load_json(INPUT_PATHS["company_documents"], {"documents": {}})
    documents = _documents(docs_payload)
    series = load_json(INPUT_PATHS["company_financial_series"], {"tickers": {}})
    reconciliation = load_json(INPUT_PATHS["financial_evidence_reconciliation"], {"companies": {}})
    truth = load_json(INPUT_PATHS["financial_truth_qualification"], {"companies": {}})
    source_registry = load_json(INPUT_PATHS["source_registry"], {"tickers": {}})
    extraction_queue = load_json(INPUT_PATHS["extraction_queue"], []) if INPUT_PATHS["extraction_queue"].exists() else []

    before = _coverage_from_truth(_company(truth))
    attempts = [
        _attempt_document(doc_id, documents.get(doc_id) or {}, series, source_registry, extraction_queue)
        for doc_id in TRANCHE_DOCUMENT_IDS
    ]
    fresh_model_loadable = sum(row["fresh_model_loadable_fact_count"] for row in attempts)
    fresh_share_candidates = sum(row["fresh_share_capital_candidate_count"] for row in attempts)
    parser_invoked_count = sum(1 for row in attempts if row.get("parser_invoked") is True)
    blocked_count = sum(1 for row in attempts if str(row.get("attempt_status") or "").startswith("blocked_"))
    fresh_parser_fact_count = sum(row["fresh_parser_fact_count"] for row in attempts)
    review_candidate = _review_candidate(attempts, reconciliation) if fresh_model_loadable else {
        "status": "no_fresh_model_loadable_candidates",
        "review_scope": "no receipt-only candidate facts",
        "candidate_fact_count": 0,
        "authoritative_delta": {"series_fact_count": 0, "financial_truth_coverage_count": 0},
    }
    if fresh_model_loadable or fresh_share_candidates:
        status = "fresh_fact_review_required"
        reason = (
            "The hash-bound PSO tranche produced fresh parser or share-capital candidates. They remain in the "
            "receipt only and require an explicit fact-level review before any financial-series promotion."
        )
    elif parser_invoked_count:
        status = "parsed_zero_delta"
        reason = (
            "Exact hash-bound PSO bytes were parsed, but the conservative geometry parser emitted no fresh "
            "model-loadable financial facts or share-capital candidates. Financial truth remains unchanged and "
            "formal outputs remain fail-closed."
        )
    else:
        status = "blocked_zero_delta"
        reason = (
            "No exact retained local PDF bytes or transient extraction-queue paths are available for the "
            "hash-bound PSO tranche, so the approved geometry parser cannot emit fresh source-bound facts."
        )

    receipt = {
        "schema_version": 1,
        "receipt_type": "pso_hashbound_tranche_reparse_attempt",
        "ticker": TICKER,
        "status": status,
        "attempt_date": ATTEMPT_DATE,
        "tranche_document_ids": list(TRANCHE_DOCUMENT_IDS),
        "parser": {
            "parser_version": PARSER_VERSION,
            "parser_revision": PARSER_REVISION,
            "requires_exact_local_bytes_or_transient_page_geometry": True,
            "no_fetch": True,
        },
        "decision": {
            "financial_truth_state_changed": False,
            "old_audit_rows_relabelled": False,
            "formal_outputs_remain_fail_closed": True,
            "reason": reason,
        },
        "coverage_before": before,
        "coverage_after": before,
        "attempt_summary": {
            "document_count": len(attempts),
            "blocked_document_count": blocked_count,
            "parser_invoked_document_count": parser_invoked_count,
            "fresh_parser_fact_count": fresh_parser_fact_count,
            "fresh_model_loadable_fact_count": fresh_model_loadable,
            "fresh_share_capital_candidate_count": fresh_share_candidates,
            "delta_series_fact_count": sum(row["delta_series_fact_count"] for row in attempts),
            "delta_financial_truth_coverage_count": sum(row["delta_financial_truth_coverage_count"] for row in attempts),
            "existing_audit_only_reconciliation_fact_count": (_company(reconciliation).get("audit_only_fact_count") or 0),
            "eligible_reconciliation_fact_count": (_company(reconciliation).get("eligible_fact_count") or 0),
        },
        "documents": attempts,
        "review_candidate": review_candidate,
        "target_slots": {
            "annual_and_quarter_income": ["revenue", "profit_after_tax_attributable", "basic_eps"],
            "full_income_balance_cash_flow_schedules": list(TARGET_FACT_LINES),
            "share_capital_note": "official_share_count_capital_note_tie_out",
        },
        "policy": {
            "fail_closed": True,
            "no_fetch": True,
            "no_provider_change": True,
            "no_financial_series_write": True,
            "no_financial_truth_write": True,
            "no_relabel_legacy_audit_rows": True,
            "audit_only_values_not_promoted": True,
            "no_forecast": True,
            "no_valuation": True,
            "no_market_expectations": True,
        },
        "_meta": {
            "generator_version": "pso_hashbound_tranche_reparse_attempt_v1",
            "inputs_sha256": {name: _file_sha(path) for name, path in sorted(INPUT_PATHS.items()) if path.exists()},
            "artifact_path": "state/company_intel/pso_hashbound_tranche_reparse_attempt.json",
            "timestamp_semantics": {
                "attempt_date": "local audit date only; not a source-effective or source-published date"
            },
        },
    }
    if write:
        save_json(OUT, receipt)
    return receipt


if __name__ == "__main__":
    result = build(write=True)
    summary = result["attempt_summary"]
    print(
        "pso_hashbound_tranche_reparse_attempt: "
        f"{result['status']} docs={summary['document_count']} "
        f"blocked={summary['blocked_document_count']} "
        f"parser_invoked={summary['parser_invoked_document_count']} "
        f"fresh_model_loadable={summary['fresh_model_loadable_fact_count']} "
        f"share_candidates={summary['fresh_share_capital_candidate_count']}"
    )
