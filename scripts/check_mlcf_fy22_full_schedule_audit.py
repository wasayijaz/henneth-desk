"""Fail-closed checker for the FY22 MLCF schedule audit receipt."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / ".cache/company_intel/mlcf_official_intake/194111.pdf"
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
RECEIPT = ROOT / "state/company_intel/mlcf_fy22_full_schedule_audit.json"
SHA = "5103d0a5eaaa8ce2c8c435ae50de6ee5000248ad05094e3f0ac086212e687aae"
PAGES = {271, 272, 273, 275}
MISSING_OFFICIAL_AVAILABILITY_REASON = "source_manifest_has_no_official_published_at_or_available_on"
OFFICIAL_AVAILABILITY_REQUIREMENT = "official availability-date binding from source manifest published_at or available_on"

def main() -> int:
    r = json.loads(RECEIPT.read_text(encoding="utf-8")); m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert r["receipt_version"] == "mlcf_fy22_full_schedule_audit_v1"
    assert r["source"]["document_id"] == "psx:194111" and r["source"]["content_sha256"] == SHA
    assert set(r["source"]["page_scope"]) == PAGES and hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA
    manifest_doc = next(d for d in m["documents"] if d["document_id"] == "psx:194111")
    assert manifest_doc["content_sha256"] == SHA
    assert "published_at" not in manifest_doc and "available_on" not in manifest_doc
    availability = r["source"]["official_availability"]
    assert availability["published_at"] is None and availability["available_on"] is None
    assert availability["status"] == "missing" and availability["reason"] == MISSING_OFFICIAL_AVAILABILITY_REASON
    assert availability["binding_required_before_promotion"] is True and availability["no_date_inferred"] is True
    policy = r["policy"]
    for k in ("official_hash_bound_original_only", "consolidated_statement_only", "local_scale_required", "current_column_header_required", "row_geometry_required", "no_network", "no_ocr", "audit_only"):
        assert policy[k] is True
    for k in ("canonical_financial_facts_written", "qualification_changed", "formal_outputs_activated"):
        assert policy[k] is False
    assert r["qualification"]["status"] == "blocked" and r["qualification"]["full_schedule_qualified"] is False
    assert MISSING_OFFICIAL_AVAILABILITY_REASON in r["qualification"]["reason"] or "official availability-date binding" in r["qualification"]["reason"]
    assert OFFICIAL_AVAILABILITY_REQUIREMENT in r["required_before_promotion"]
    assert r["candidates"] and r["omissions"]
    for c in r["candidates"]:
        assert c["document_id"] == "psx:194111" and c["source_url"].startswith("https://") and c["content_sha256"] == SHA
        assert c["statement_identity"] == "consolidated" and c["status"] == "audit_only" and c["promotion_status"] == "blocked"
        assert c["model_readiness"] == "not_ready" and c["model_readiness_reason"] == MISSING_OFFICIAL_AVAILABILITY_REASON
        assert c["original_page"] in PAGES and c["period_end"] == "2022-06-30" and c["column_role"] == "current"
        assert c["current_period_header_geometry"]["text"] == "2022" and c["comparison_period_header_geometry"]["text"] == "2021"
        assert c["row_geometry"]["x1"] > c["row_geometry"]["x0"] and c["cell_geometry"]["current"]["x1"] > c["cell_geometry"]["current"]["x0"]
        assert c["scale"] == 1000 and c["currency"] == "PKR"
        assert c["unit"] in {"PKR thousands", "PKR per share"}
        assert c["scale_evidence"]["text"] == "Rupees in thousand" and c["scale_evidence"]["geometry"]["x1"] > c["scale_evidence"]["geometry"]["x0"]
        assert c["basis_evidence"]["text"] == "CONSOLIDATED" and c["basis_evidence"]["geometry"]["x1"] > c["basis_evidence"]["geometry"]["x0"]
        assert c["basis_evidence"]["original_page"] == c["original_page"]
        assert "facts" not in c and "metrics" not in c and "values" not in c
    for o in r["omissions"]:
        assert o["reason"] == "missing_or_ambiguous_geometry_on_scoped_pages"
    print(f"mlcf_fy22_full_schedule_audit: PASS ({len(r['candidates'])} candidates; {len(r['omissions'])} explicit omissions; blocked)")
    return 0

if __name__ == "__main__": raise SystemExit(main())
