"""Build MARI's hash-bound financial-statement parser rerun receipt.

This receipt is deliberately not a canonical fact promotion path.  It attempts
to use only exact retained local PDF bytes for the first approved MARI tranche;
when those bytes or their page geometry are unavailable, it records a per-doc
zero delta and leaves existing audit-only facts untouched.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from financial_statement_facts import PARSER_REVISION, PARSER_VERSION, extract_facts
from psx_data import ROOT, STATE, load_json, save_json


TICKER = "MARI"
AUDIT_DATE = "2026-09-13"
RECEIPT_VERSION = "mari_financial_truth_hash_bound_rerun_v1"
OUT = STATE / "company_intel" / "mari_financial_truth_hash_bound_rerun_receipt.json"
SOURCE_RECEIPT = STATE / "company_intel" / "mari_financial_truth_next_intake_receipt.json"

TARGET_DOCUMENTS = {
    "psx:275583": "b2d9a7ce564306b3fccfb301801f774c90accb69ceffa8e3c0c1c9e69137c02b",
    "psx:271327": "e53fccd6eca58c685dbf9225140056303be704b1f389b876ba33d87aa4b687b3",
    "psx:264550": "7f4cf3461439d968407a7cb06d446dc02876f13e923893c165d36a9e0e7f88f5",
}

INPUT_PATHS = {
    "company_documents": STATE / "company_documents.json",
    "company_financial_series": STATE / "company_financial_series.json",
    "financial_truth_qualification": STATE / "company_intel" / "financial_truth_qualification.json",
    "next_intake_receipt": SOURCE_RECEIPT,
}

PATH_FIELDS = (
    "path",
    "local_path",
    "file_path",
    "pdf_path",
    "raw_path",
    "raw_pdf_path",
)
GEOMETRY_FIELDS = (
    "document_pages",
    "page_records",
    "pages",
    "page_words",
    "words",
    "word_pages",
)
FOCUS_LINES = {
    "revenue",
    "profit_after_tax_attributable",
    "basic_eps",
    "operating_cash_flow",
    "gross_profit",
    "ebitda",
    "operating_profit",
    "finance_cost",
    "profit_before_tax",
    "tax_expense",
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
    "capital_expenditure",
    "depreciation_amortization",
    "net_cash_from_investing_activities",
    "net_cash_from_financing_activities",
    "dividends_paid",
}


def _file_sha(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _load_company(payload: dict[str, Any], symbol: str = TICKER) -> dict[str, Any]:
    companies = payload.get("companies") or {}
    return companies.get(symbol) or payload.get(symbol) or {}


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


def _resolve_candidate_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    return path if path.is_absolute() else ROOT / path


def _hash_match(path: Path, expected_sha: str, expected_length: int | None) -> dict[str, Any]:
    exists = path.exists() and path.is_file()
    size = path.stat().st_size if exists else None
    actual = _file_sha(path) if exists else None
    return {
        "path": str(path),
        "exists": exists,
        "size": size,
        "size_matches": bool(expected_length is not None and size == expected_length),
        "sha256": actual,
        "sha256_matches": actual == expected_sha,
    }


def _explicit_byte_candidates(doc: dict[str, Any], expected_sha: str) -> list[dict[str, Any]]:
    expected_length = doc.get("content_length") if isinstance(doc.get("content_length"), int) else None
    candidates = []
    for field in PATH_FIELDS:
        path = _resolve_candidate_path(doc.get(field))
        if path is not None:
            candidates.append({"field": field, **_hash_match(path, expected_sha, expected_length)})
    return candidates


def _cache_byte_matches(doc_id: str, doc: dict[str, Any], expected_sha: str) -> list[dict[str, Any]]:
    cache = ROOT / ".cache"
    if not cache.exists():
        return []
    expected_length = doc.get("content_length") if isinstance(doc.get("content_length"), int) else None
    numeric_id = doc_id.split(":", 1)[-1]
    matches = []
    for path in sorted(cache.rglob("*.pdf")):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        name = path.name.lower()
        should_hash = (
            numeric_id in name
            or expected_sha[:12] in name
            or (expected_length is not None and size == expected_length)
        )
        if not should_hash:
            continue
        row = _hash_match(path, expected_sha, expected_length)
        if row["sha256_matches"]:
            matches.append(row)
    return matches


def _retained_geometry_summary(doc: dict[str, Any]) -> dict[str, Any]:
    present = {field: isinstance(doc.get(field), list) and bool(doc.get(field)) for field in GEOMETRY_FIELDS}
    return {
        "has_any_persisted_geometry_or_full_pages": any(present.values()),
        "fields_present": {field: value for field, value in present.items() if value},
        "bounded_evidence_excerpt_count": len(doc.get("evidence") or []),
        "bounded_facts_count": len(doc.get("facts") or []),
    }


def _period_start(period_end: Any, duration_months: Any) -> str | None:
    try:
        end = date.fromisoformat(str(period_end)[:10])
        months = int(duration_months)
    except (TypeError, ValueError):
        return None
    start_month_index = end.year * 12 + end.month - months
    year = start_month_index // 12
    month = start_month_index % 12 + 1
    try:
        return date(year, month, 1).isoformat()
    except ValueError:
        return None


def _fact_level(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_id": row.get("fact_id"),
        "parser_version": row.get("parser_version"),
        "parser_revision": row.get("parser_revision"),
        "document_id": row.get("document_id"),
        "source_url": row.get("source_url"),
        "source_hash": row.get("content_sha256"),
        "page": row.get("page"),
        "statement_identity": {
            "statement_type": row.get("statement_type"),
            "statement_heading": row.get("statement_heading"),
            "reported_label": row.get("reported_label"),
            "line": row.get("line") or row.get("fact_type"),
        },
        "basis": {
            "consolidated_or_company": row.get("consolidation"),
        },
        "unit": {
            "currency": row.get("currency"),
            "unit": row.get("unit"),
            "unit_multiplier": row.get("unit_multiplier"),
        },
        "period": {
            "start": _period_start(row.get("period_end"), row.get("duration_months")),
            "end": row.get("period_end"),
            "duration_months": row.get("duration_months"),
            "period_type": row.get("period_type"),
            "column_role": row.get("column_role"),
            "comparative_to_period_end": row.get("comparative_to_period_end"),
        },
        "values": {
            "raw_value": row.get("raw_value"),
            "normalized_value": row.get("normalized_value") if "normalized_value" in row else row.get("value"),
        },
        "availability": {
            "available_on": row.get("available_on"),
            "published_at": row.get("published_at"),
            "retrieved_at": row.get("retrieved_at"),
        },
        "readiness": row.get("readiness"),
        "quality_flags": list(row.get("quality_flags") or []),
        "evidence": row.get("evidence") or [],
    }


def _extract_from_pdf(doc: dict[str, Any], pdf_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        import pymupdf
    except Exception as exc:  # pragma: no cover - depends on runtime packaging
        return [], f"pymupdf_unavailable:{type(exc).__name__}"
    try:
        handle = pymupdf.open(str(pdf_path))
    except Exception as exc:
        return [], f"pdf_open_failed:{type(exc).__name__}"
    try:
        page_records = [
            {"page": index + 1, "text": page.get_text("text") or "", "words": page.get_text("words") or []}
            for index, page in enumerate(handle)
        ]
    finally:
        handle.close()
    if not page_records:
        return [], "pdf_has_no_pages"
    if not any(record.get("words") for record in page_records):
        return [], "text_geometry_unavailable"
    parser_doc = {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "source_url": doc.get("source_url"),
        "content_sha256": doc.get("content_sha256"),
        "period_end": doc.get("period_end"),
        "published_at": doc.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
    }
    pages = [str(record.get("text") or "") for record in page_records]
    facts = extract_facts(parser_doc, pages, page_records=page_records)
    focused = [
        _fact_level(row)
        for row in facts
        if (row.get("line") or row.get("fact_type")) in FOCUS_LINES
    ]
    return focused, None


def _series_inventory(series: dict[str, Any]) -> dict[str, Any]:
    facts = [
        fact for fact in (series.get("tickers", {}).get(TICKER, {}).get("facts") or [])
        if fact.get("document_id") in TARGET_DOCUMENTS
    ]
    by_doc = {}
    for doc_id in TARGET_DOCUMENTS:
        doc_facts = [fact for fact in facts if fact.get("document_id") == doc_id]
        by_doc[doc_id] = {
            "fact_count": len(doc_facts),
            "model_loadable_count": sum(1 for fact in doc_facts if fact.get("readiness") == "model_loadable"),
            "audit_only_count": sum(1 for fact in doc_facts if fact.get("readiness") != "model_loadable"),
            "parser_revisions": dict(Counter(str(fact.get("parser_revision") or "none") for fact in doc_facts)),
            "quality_flags": sorted({flag for fact in doc_facts for flag in (fact.get("quality_flags") or [])}),
        }
    return {
        "fact_count": len(facts),
        "model_loadable_count": sum(1 for fact in facts if fact.get("readiness") == "model_loadable"),
        "audit_only_count": sum(1 for fact in facts if fact.get("readiness") != "model_loadable"),
        "by_document": by_doc,
    }


def _source_receipt_tranche(source_receipt: dict[str, Any]) -> dict[str, str | None]:
    docs = ((source_receipt.get("retained_official_candidate_documents") or {})
            .get("hash_bound_statement_restage_wave") or [])
    return {
        str(row.get("document_id")): row.get("content_sha256")
        for row in docs
        if isinstance(row, dict) and row.get("document_id")
    }


def _document_attempt(doc_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    expected_sha = TARGET_DOCUMENTS[doc_id]
    explicit = _explicit_byte_candidates(doc, expected_sha)
    cache_matches = _cache_byte_matches(doc_id, doc, expected_sha)
    exact_paths = [Path(row["path"]) for row in explicit + cache_matches if row.get("sha256_matches")]
    geometry = _retained_geometry_summary(doc)
    emitted_facts: list[dict[str, Any]] = []
    parser_blocker = None
    parser_run_attempted = False
    if exact_paths:
        parser_run_attempted = True
        emitted_facts, parser_blocker = _extract_from_pdf(doc, exact_paths[0])
    elif geometry["has_any_persisted_geometry_or_full_pages"]:
        parser_blocker = "persisted_geometry_not_in_current_parser_page_records_shape"
    else:
        parser_blocker = "exact_retained_pdf_bytes_missing_and_no_persisted_text_geometry"

    status = "zero_delta" if not emitted_facts else "fact_level_output_only_not_promoted"
    return {
        "document_id": doc_id,
        "status": status,
        "parser_version": PARSER_VERSION,
        "parser_revision": PARSER_REVISION,
        "document_status": doc.get("status"),
        "title": doc.get("title"),
        "source_url": doc.get("source_url"),
        "published_at": doc.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "available_on": doc.get("available_on") or (str(doc.get("published_at") or "")[:10] or None),
        "content_sha256": doc.get("content_sha256"),
        "expected_content_sha256": expected_sha,
        "local_sha256": doc.get("local_sha256"),
        "hash_bound": doc.get("content_sha256") == expected_sha,
        "content_length": doc.get("content_length"),
        "page_count": doc.get("page_count"),
        "retained_byte_check": {
            "explicit_path_candidates": explicit,
            "cache_exact_hash_matches": cache_matches,
            "exact_local_pdf_bytes_present": bool(exact_paths),
            "selected_path": str(exact_paths[0]) if exact_paths else None,
        },
        "retained_geometry_check": geometry,
        "parser_run_attempted": parser_run_attempted,
        "parser_blocker": parser_blocker,
        "facts_emitted": len(emitted_facts),
        "fact_level_output": emitted_facts,
        "canonical_facts_written": 0,
        "audit_only_relabels": 0,
    }


def build(write: bool = True) -> dict[str, Any]:
    docs_payload = load_json(INPUT_PATHS["company_documents"], {})
    series = load_json(INPUT_PATHS["company_financial_series"], {})
    truth = load_json(INPUT_PATHS["financial_truth_qualification"], {"companies": {}})
    source_receipt = load_json(SOURCE_RECEIPT, {})

    docs = docs_payload.get("documents") or docs_payload
    truth_row = _load_company(truth)
    coverage = _coverage_from_truth(truth_row)
    source_tranche = _source_receipt_tranche(source_receipt)
    attempts = [_document_attempt(doc_id, docs.get(doc_id) or {}) for doc_id in TARGET_DOCUMENTS]
    total_facts = sum(row["facts_emitted"] for row in attempts)
    all_zero_delta = total_facts == 0
    receipt = {
        "schema_version": 1,
        "receipt_type": "mari_financial_truth_hash_bound_rerun_receipt",
        "receipt_version": RECEIPT_VERSION,
        "ticker": TICKER,
        "audit_date": AUDIT_DATE,
        "status": (
            "zero_delta_parser_rerun_blocked_missing_retained_bytes_or_geometry"
            if all_zero_delta else "fact_level_output_only_not_promoted"
        ),
        "source_receipt": {
            "path": "state/company_intel/mari_financial_truth_next_intake_receipt.json",
            "receipt_type": source_receipt.get("receipt_type"),
            "status": source_receipt.get("status"),
            "hash_bound_statement_restage_wave": source_tranche,
        },
        "parser": {
            "version": PARSER_VERSION,
            "revision": PARSER_REVISION,
            "source": "scripts/financial_statement_facts.py",
            "mode": "exact_retained_bytes_only",
        },
        "policy": {
            "fail_closed": True,
            "no_fetch": True,
            "no_audit_only_relabel": True,
            "no_canonical_fact_write": True,
            "fact_level_output_only": True,
        },
        "coverage_before": coverage,
        "coverage_after": coverage,
        "state_delta": {
            "financial_truth_state_changed": False,
            "company_financial_series_changed": False,
            "canonical_facts_written": 0,
            "audit_only_relabels": 0,
            "fact_level_outputs_emitted_to_receipt": total_facts,
        },
        "retained_series_inventory_before": _series_inventory(series),
        "documents": attempts,
        "blockers": [
            {
                "document_id": row["document_id"],
                "reason": row["parser_blocker"],
                "zero_delta": row["facts_emitted"] == 0,
            }
            for row in attempts
            if row["facts_emitted"] == 0
        ],
        "_meta": {
            "generator_version": RECEIPT_VERSION,
            "artifact_path": "state/company_intel/mari_financial_truth_hash_bound_rerun_receipt.json",
            "inputs_sha256": {name: _file_sha(path) for name, path in sorted(INPUT_PATHS.items())},
            "target_content_sha256": TARGET_DOCUMENTS,
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
    delta = result["state_delta"]
    print(
        "mari_financial_truth_hash_bound_rerun_receipt: "
        f"{result['status']} "
        f"facts={delta['fact_level_outputs_emitted_to_receipt']} "
        f"canonical_writes={delta['canonical_facts_written']} "
        f"relabels={delta['audit_only_relabels']}"
    )
