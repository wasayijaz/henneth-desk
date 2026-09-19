"""Fail-closed checker for the MLCF FY25 full-schedule audit receipt."""
from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from financial_statement_facts import PARSER_REVISION, PARSER_VERSION

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/ci_reprocess_review_manifest.json"
DOCUMENTS = ROOT / "state/company_documents.json"
LOCAL_SOURCE = ROOT / ".cache/company_intel/raw/manual/260032.pdf"
RECEIPT = ROOT / "state/company_intel/mlcf_fy25_full_schedule_audit.json"
DOC = "psx:260032"
SHA = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"
EXPECTED_CANDIDATES = 23
EXPECTED_OMISSIONS = 2


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
    assert source["local_bytes_status"] == "retained_hash_verified" and LOCAL_SOURCE.exists()
    assert source["local_sha256"] == SHA
    assert source["page_scope"] == [291, 292, 293, 295]
    assert source["page_count"] == 401
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
    parser = receipt["parser"]
    assert parser == {
        "version": PARSER_VERSION,
        "revision": PARSER_REVISION,
        "page_scope": [291, 292, 293, 295],
        "current_period_fact_count": EXPECTED_CANDIDATES,
        "all_period_fact_count": 46,
    }
    assert len(receipt["candidates"]) == EXPECTED_CANDIDATES
    assert all(
        candidate["period_end"] == "2025-06-30"
        and candidate["column_role"] == "current_period"
        and candidate["consolidation"] == "consolidated"
        and candidate["parser_version"] == PARSER_VERSION
        and candidate["parser_revision"] == PARSER_REVISION
        and candidate["readiness"] == "model_loadable"
        for candidate in receipt["candidates"]
    )
    by_line = {candidate["canonical_line"]: candidate for candidate in receipt["candidates"]}
    assert by_line["profit_before_tax"]["page"] == 293
    assert by_line["profit_before_tax"]["raw_value"] == "16,329,735"
    assert by_line["profit_before_tax"]["normalized_value"] == 16329735000.0
    assert by_line["tax_expense"]["page"] == 293
    assert by_line["tax_expense"]["raw_value"] == "(4,826,457)"
    assert by_line["tax_expense"]["normalized_value"] == -4826457000.0
    assert by_line["capital_expenditure"]["page"] == 295
    assert by_line["capital_expenditure"]["raw_value"] == "(3,611,410)"
    assert by_line["capital_expenditure"]["normalized_value"] == -3611410000.0
    assert len(receipt["omissions"]) == EXPECTED_OMISSIONS
    assert receipt["counts"] == {"candidate_count": EXPECTED_CANDIDATES, "omission_count": EXPECTED_OMISSIONS}
    assert all(
        o["reason"] == "current_parser_did_not_emit_required_fact"
        and o["parser_revision"] == PARSER_REVISION
        for o in receipt["omissions"]
    )
    assert receipt["qualification"] == {
        "status": "blocked",
        "full_schedule_qualified": False,
        "reason": "current parser emitted 23 of 25 required current-period lines; 2 required lines remain absent",
    }
    assert "exact local source bytes absent" not in json.dumps(receipt["blockers"], sort_keys=True)
    assert "cannot alter canonical facts, coverage, lifecycle, forecasts, valuation, or expectations" in receipt["non_effects"]
    print(f"mlcf_fy25_full_schedule_audit: PASS ({EXPECTED_CANDIDATES} parser candidates; {EXPECTED_OMISSIONS} explicit omissions; blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
