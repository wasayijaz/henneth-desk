#!/usr/bin/env python3
"""Fail-closed checker for the MLCF FY2022 table audit receipt."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "state/company_intel/mlcf_fy22_table_audit.json"
PDF = ROOT / ".cache/company_intel/mlcf_official_intake/194111.pdf"
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"

def main() -> int:
    r = json.loads(OUT.read_text(encoding="utf-8")); m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    row = next(d for d in m["documents"] if d["document_id"] == "psx:194111")
    assert r.get("receipt_version") == "mlcf_fy22_table_audit_v1"
    digest = hashlib.sha256(PDF.read_bytes()).hexdigest(); assert digest == row["content_sha256"] == r.get("content_sha256")
    availability = r["official_availability"]
    assert "published_at" not in row and "available_on" not in row
    assert availability == {
        "published_at": None, "available_on": None, "status": "missing",
        "reason": "source_manifest_has_no_official_published_at_or_available_on",
        "binding_required_before_promotion": True, "no_date_inferred": True,
    }
    p = r.get("policy", {})
    for k in ("local_original_only", "native_text_geometry_required", "hash_bound", "consolidated_only", "audit_only"): assert p.get(k) is True
    for k in ("facts_promoted", "coverage_changed", "case_changed"): assert p.get(k) is False
    assert p.get("promotion_status") == "blocked" and r["summary"]["facts"] == []
    assert r["summary"]["reason"] == availability["reason"]
    assert "official availability-date binding from source manifest published_at or available_on" in r["required_before_promotion"]
    assert set(r.get("pages", {})) == {"271", "273", "275"}
    for pg in r["pages"].values():
        assert pg["identity"] == "consolidated" and pg["duration_months"] == 12 and pg["period_end"] == "2022-06-30"
        h = pg.get("table_header_geometry"); assert h and all(h.get(x) is not None for x in ("x0", "y0", "x1", "y1"))
    allowed = {"sales_net", "profit_after_taxation", "eps_basic_diluted", "net_cash_generated_from_operating_activities"}
    for c in r.get("candidates", []):
        assert c["metric"] in allowed and c["statement_identity"] == "consolidated" and c["content_sha256"] == digest
        assert c["status"] == "audit_only" and c["promotion_status"] == "blocked" and c.get("cell_geometry")
        assert c["model_readiness"] == "not_ready" and c["model_readiness_reason"] == availability["reason"]
        assert c["page"] in (273, 275) and c.get("unit") in ("PKR_thousand", "PKR/share")
    assert r["summary"]["candidate_count"] == len(r["candidates"])
    print(f"mlcf_fy22_table_audit: PASS (candidates={len(r['candidates'])}; promotion blocked)")
    return 0

if __name__ == "__main__": raise SystemExit(main())
