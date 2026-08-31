"""Emit a fail-closed, audit-only receipt for the retained MLCF FY25 annual source.

This integration checkout does not retain the original PDF bytes for ``psx:260032``.
The receipt therefore records metadata and explicit omissions only.  It never reads a
different worktree, downloads a source, invokes OCR, parses text, or writes facts.
"""
from __future__ import annotations

import json
from pathlib import Path

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
    # A present file is deliberately not consumed by this blocked implementation: parsing
    # requires a separately reviewed geometry path and must not silently change this receipt.
    local_status = "present_but_unprocessed" if LOCAL_SOURCE.is_file() else "missing"
    omissions = [
        {
            "statement_type": statement_type,
            "canonical_line": line,
            "reason": "exact_local_source_bytes_absent",
            "original_page": page,
        }
        for statement_type, page in (("balance_sheet", 291), ("income_statement", 293), ("cash_flow_statement", 295))
        for line in SCHEDULE_LINES[statement_type]
    ]
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
            "page_scope": [291, 293, 295],
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
        "candidates": [],
        "omissions": omissions,
        "counts": {"candidate_count": 0, "omission_count": len(omissions)},
        "qualification": {
            "status": "blocked",
            "full_schedule_qualified": False,
            "reason": "exact local FY25 source bytes are absent; no geometry-bound extraction is permitted",
        },
        "blockers": [
            "exact local source bytes absent at source.raw_path",
            "original-page statement geometry unavailable without those bytes",
            "consolidated identity, unit/scale, headers, rows and cells cannot be proven",
        ],
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
