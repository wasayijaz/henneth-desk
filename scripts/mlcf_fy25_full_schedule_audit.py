"""Emit a fail-closed, audit-only receipt for the retained MLCF FY25 annual source.

The receipt reads only the exact owner-retained PDF bytes for ``psx:260032`` and
records the current geometry parser's bounded result. It never reads a different
worktree, downloads a source, invokes OCR, or writes canonical facts.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from financial_statement_facts import PARSER_REVISION, PARSER_VERSION, extract_facts
from mlcf_derived_dna import DerivedDnaError, build_receipt_block, read_note_page

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/ci_reprocess_review_manifest.json"
DOCUMENTS = ROOT / "state/company_documents.json"
LOCAL_SOURCE = ROOT / ".cache/company_intel/raw/manual/260032.pdf"
OUT = ROOT / "state/company_intel/mlcf_fy25_full_schedule_audit.json"
DOCUMENT_ID = "psx:260032"
SOURCE_URL = "https://dps.psx.com.pk/download/document/260032.pdf"
EXPECTED_HASH = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"

SCHEDULE_LINES = {
    "balance_sheet": [
        "cash_and_cash_equivalents", "trade_receivables", "inventories",
        "total_current_assets", "property_plant_equipment", "total_assets",
        "short_term_borrowings", "long_term_borrowings", "trade_payables",
        "total_equity",
    ],
    "income_statement": [
        "revenue", "gross_profit", "ebitda", "operating_profit", "finance_cost",
        "profit_before_tax", "profit_after_tax_attributable", "tax_expense", "basic_eps",
    ],
    "cash_flow_statement": [
        "operating_cash_flow", "capital_expenditure", "depreciation_amortization",
        "net_cash_from_investing_activities", "net_cash_from_financing_activities",
        "dividends_paid",
    ],
}


def _page_records(raw: bytes, page_scope: list[int]) -> tuple[list[str], list[list[tuple]], list[dict[str, object]], int]:
    """Read only the owner-approved statement pages from the retained PDF."""
    import pymupdf

    pdf = pymupdf.open(stream=raw, filetype="pdf")
    try:
        if any(page < 1 or page > len(pdf) for page in page_scope):
            raise ValueError("retained FY25 source page scope is outside the verified PDF")
        records = [pdf[page - 1] for page in page_scope]
        pages = [page.get_text("text") or "" for page in records]
        words = [page.get_text("words") or [] for page in records]
        page_records = [
            {"page": page_no, "text": text, "words": page_words}
            for page_no, text, page_words in zip(page_scope, pages, words)
        ]
        return pages, words, page_records, len(pdf)
    finally:
        pdf.close()


def _compact_fact(fact: dict[str, object]) -> dict[str, object]:
    """Keep audit evidence source-bound without copying parser geometry or IDs."""
    return {
        "statement_type": fact.get("statement_type"),
        "canonical_line": fact.get("line"),
        "period_end": fact.get("period_end"),
        "duration_months": fact.get("duration_months"),
        "column_role": fact.get("column_role"),
        "consolidation": fact.get("consolidation"),
        "currency": fact.get("currency"),
        "scale": fact.get("scale"),
        "unit": fact.get("unit"),
        "raw_value": fact.get("raw_value"),
        "normalized_value": fact.get("normalized_value"),
        "page": fact.get("page"),
        "parser_version": fact.get("parser_version"),
        "parser_revision": fact.get("parser_revision"),
        "quality_flags": list(fact.get("quality_flags") or []),
        "readiness": fact.get("readiness"),
    }


def build() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc = manifest["documents"][DOCUMENT_ID]
    documents = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
    retained_document = documents["documents"][DOCUMENT_ID]
    if doc.get("source_url") != SOURCE_URL or doc.get("content_sha256") != EXPECTED_HASH:
        raise ValueError("retained FY25 source metadata does not match the exact PSX document")
    if (retained_document.get("source_url") != SOURCE_URL
            or retained_document.get("content_sha256") != EXPECTED_HASH
            or not retained_document.get("available_on")):
        raise ValueError("retained FY25 document-state availability binding is incomplete")
    page_scope = [291, 292, 293, 295]
    raw = LOCAL_SOURCE.read_bytes() if LOCAL_SOURCE.is_file() else None
    local_status = "missing"
    facts: list[dict[str, object]] = []
    page_count = None
    parser = {
        "version": PARSER_VERSION,
        "revision": PARSER_REVISION,
        "page_scope": page_scope,
        "current_period_fact_count": 0,
        "all_period_fact_count": 0,
    }
    if raw is not None:
        local_hash = hashlib.sha256(raw).hexdigest()
        if local_hash != EXPECTED_HASH:
            raise ValueError("retained FY25 source bytes do not match the approved SHA-256")
        local_status = "retained_hash_verified"
        pages, words, page_records, page_count = _page_records(raw, page_scope)
        doc_for_parser = {
            "doc_id": DOCUMENT_ID,
            "title": doc.get("title") or "",
            "source_url": SOURCE_URL,
            "content_sha256": EXPECTED_HASH,
            "period_end": "2025-06-30",
            "published_at": doc.get("published_at"),
            "available_on": retained_document.get("available_on"),
        }
        parsed = extract_facts(doc_for_parser, pages, words=words, page_records=page_records)
        current = [
            fact for fact in parsed
            if fact.get("period_end") == "2025-06-30"
            and fact.get("column_role") == "current_period"
            and fact.get("consolidation") == "consolidated"
            and fact.get("parser_version") == PARSER_VERSION
            and fact.get("parser_revision") == PARSER_REVISION
        ]
        facts = sorted(
            (_compact_fact(fact) for fact in current),
            key=lambda row: (str(row.get("statement_type")), str(row.get("canonical_line")), int(row.get("page") or 0)),
        )
        parser["current_period_fact_count"] = len(facts)
        parser["all_period_fact_count"] = len(parsed)
    derived_block = None
    if raw is not None and facts:
        operating_profit = next(
            (row for row in facts if row.get("canonical_line") == "operating_profit"), None
        )
        if operating_profit is None:
            raise ValueError("current-period operating profit fact missing; derived EBITDA lineage cannot bind")
        note_text, note_words = read_note_page(raw)
        try:
            derived_block = build_receipt_block(
                DOCUMENT_ID,
                EXPECTED_HASH,
                note_words,
                note_text,
                "2025-06-30",
                float(operating_profit["normalized_value"]),
                int(operating_profit["page"]),
            )
        except DerivedDnaError as exc:
            raise ValueError(f"note 43.1 operand geometry failed strict validation: {exc}") from exc
    required = {
        (statement_type, line): page
        for statement_type, page in (("balance_sheet", 291), ("income_statement", 293), ("cash_flow_statement", 295))
        for line in SCHEDULE_LINES[statement_type]
    }
    present = {(str(row.get("statement_type")), str(row.get("canonical_line"))) for row in facts}
    omissions = [
        {
            "statement_type": statement_type,
            "canonical_line": line,
            "reason": "current_parser_did_not_emit_required_fact" if local_status != "missing" else "exact_local_source_bytes_absent",
            "original_page": page,
            "parser_revision": PARSER_REVISION,
        }
        for (statement_type, line), page in required.items()
        if (statement_type, line) not in present
    ]
    if local_status == "missing":
        # No source means no parser claim. Keep the fail-closed legacy omissions.
        omissions = [
            {
                "statement_type": statement_type,
                "canonical_line": line,
                "reason": "exact_local_source_bytes_absent",
                "original_page": page,
            }
            for (statement_type, line), page in required.items()
        ]
    qualified = local_status == "retained_hash_verified" and not omissions
    if qualified:
        qualification_reason = "all required current-period full-statement lines were emitted by the current parser"
    elif local_status == "missing":
        qualification_reason = "exact local FY25 source bytes are absent; no geometry-bound extraction is permitted"
    else:
        qualification_reason = (
            f"current parser emitted {len(facts)} of {len(required)} required current-period lines; "
            f"{len(omissions)} required lines remain absent"
        )
    blockers = []
    if local_status == "missing":
        blockers.extend([
            "exact local source bytes absent at source.raw_path",
            "original-page statement geometry unavailable without those bytes",
        ])
    else:
        blockers.extend([
            "current parser did not emit every required full-statement line",
            "formal financial-truth qualification remains blocked until the complete schedule is proven",
        ])
    blockers.append("consolidated identity, unit/scale, headers, rows and cells remain subject to independent tie-out")
    return {
        "schema_version": 1,
        "receipt_version": "mlcf_fy25_full_schedule_audit_v1",
        "symbol": "MLCF",
        "document_id": DOCUMENT_ID,
        "source": {
            "document_id": DOCUMENT_ID,
            "source_url": SOURCE_URL,
            "raw_path": str(LOCAL_SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "local_bytes_status": local_status,
            "content_sha256": EXPECTED_HASH,
            "local_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            "page_scope": page_scope,
            "page_count": page_count,
            "official_availability": {
                "published_at": doc.get("published_at"),
                "available_on": retained_document.get("available_on"),
                "status": "proven_from_retained_manifest_and_document_state",
                "no_date_inferred": True,
            },
        },
        "period": {"period_end": "2025-06-30", "duration_months": 12, "comparison_period_end": "2024-06-30"},
        "policy": {
            "official_hash_bound_original_only": True,
            "consolidated_statement_only": True,
            "local_scale_required": True,
            "current_column_header_required": True,
            "row_geometry_required": True,
            "no_network": True,
            "no_ocr": True,
            "audit_only": True,
            "canonical_financial_facts_written": False,
            "coverage_changed": False,
            "lifecycle_changed": False,
            "forecasts_changed": False,
            "valuation_changed": False,
            "expectations_changed": False,
        },
        "parser": parser,
        "candidates": facts,
        "derived": derived_block,
        "omissions": omissions,
        "counts": {"candidate_count": len(facts), "omission_count": len(omissions)},
        "qualification": {
            "status": "qualified" if qualified else "blocked",
            "full_schedule_qualified": qualified,
            "reason": qualification_reason,
        },
        "blockers": blockers,
        "required_before_promotion": [
            "exact local original PDF bytes with matching SHA-256",
            "original-page consolidated statement geometry for pages 291, 293 and 295",
            "independent full-statement extraction and annual tie-out",
            "existing canonical conflict check and financial-truth builder acceptance",
        ],
        "non_effects": "This audit-only receipt cannot alter canonical facts, coverage, lifecycle, forecasts, valuation, or expectations.",
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
