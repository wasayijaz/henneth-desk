"""Fail-closed checker for the MLCF FY25 full-schedule audit receipt."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/ci_reprocess_review_manifest.json"
DOCUMENTS = ROOT / "state/company_documents.json"
LOCAL_SOURCE = ROOT / ".cache/company_intel/raw/manual/260032.pdf"
RECEIPT = ROOT / "state/company_intel/mlcf_fy25_full_schedule_audit.json"
DOC = "psx:260032"
SHA = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"
EXPECTED_OMISSIONS = 25


def main() -> int:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    documents = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
    doc = manifest["documents"][DOC]
    retained_document = documents["documents"][DOC]
    assert receipt["receipt_version"] == "mlcf_fy25_full_schedule_audit_v1"
    assert receipt["document_id"] == DOC and receipt["symbol"] == "MLCF"
    source = receipt["source"]
    assert source["source_url"] == doc["source_url"] == "https://dps.psx.com.pk/download/document/260032.pdf"
    assert source["content_sha256"] == doc["content_sha256"] == SHA
    assert source["raw_path"] == ".cache/company_intel/raw/manual/260032.pdf"
    assert source["local_bytes_status"] == "missing" and not LOCAL_SOURCE.exists()
    assert source["page_scope"] == [291, 293, 295]
    availability = source["official_availability"]
    assert availability["status"] == "proven_from_retained_manifest_and_document_state"
    assert availability["published_at"] == doc["published_at"]
    assert availability["available_on"] == retained_document["available_on"] == "2025-09-25"
    assert availability["no_date_inferred"] is True
    policy = receipt["policy"]
    for key in ("official_hash_bound_original_only", "consolidated_statement_only", "local_scale_required", "current_column_header_required", "row_geometry_required", "no_network", "no_ocr", "audit_only"):
        assert policy[key] is True
    for key in ("canonical_financial_facts_written", "coverage_changed", "lifecycle_changed", "forecasts_changed", "valuation_changed", "expectations_changed"):
        assert policy[key] is False
    assert receipt["candidates"] == []
    assert len(receipt["omissions"]) == EXPECTED_OMISSIONS
    assert receipt["counts"] == {"candidate_count": 0, "omission_count": EXPECTED_OMISSIONS}
    assert all(o["reason"] == "exact_local_source_bytes_absent" for o in receipt["omissions"])
    assert receipt["qualification"] == {"status": "blocked", "full_schedule_qualified": False, "reason": "exact local FY25 source bytes are absent; no geometry-bound extraction is permitted"}
    assert "cannot alter canonical facts, coverage, lifecycle, forecasts, valuation, or expectations" in receipt["non_effects"]
    print(f"mlcf_fy25_full_schedule_audit: PASS (0 candidates; {EXPECTED_OMISSIONS} explicit omissions; blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
