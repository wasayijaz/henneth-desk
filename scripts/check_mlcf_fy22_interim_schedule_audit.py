"""Fail-closed checker for the MLCF interim direct-quarter audit receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
RECEIPT = ROOT / "state/company_intel/mlcf_fy22_interim_schedule_audit.json"
INTAKE = ROOT / ".cache/company_intel/mlcf_official_intake"
DOCS = {
    "issuer:mlcf:1q-2021-09": ("q1_2021.pdf", 32, "42c675f3cfa973684d5e04be00f9ef330c6554484f09714193556d2110b42f01"),
    "issuer:mlcf:hy-2021-12": ("hy_2021.pdf", 40, "f363e99782080db7c405f4afc418cd77915317a0fa47a3dff2f3525e6c5f1b10"),
    "issuer:mlcf:q3-2022-03": ("q3_2022.pdf", 34, "1d01533de7d12b8c8d480dd58b137f38888abe88c9557a2ca7e09170dc9aecd5"),
}
METRICS = {"revenue", "profit_after_tax", "basic_eps"}


def _positive(box: dict[str, float]) -> bool:
    return box["x1"] > box["x0"] and box["y1"] > box["y0"]


def main() -> int:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert receipt["receipt_version"] == "mlcf_fy22_interim_schedule_audit_v1"
    assert receipt["symbol"] == "MLCF" and receipt["candidates"] == []
    assert receipt["policy"] == {
        "official_hash_bound_original_only": True,
        "consolidated_statement_only": True,
        "direct_three_month_column_required": True,
        "no_quarter_from_cumulative_subtraction": True,
        "local_scale_currency_required": True,
        "statement_period_identity_geometry_required": True,
        "no_network": True,
        "no_ocr": True,
        "audit_only": True,
        "canonical_financial_facts_written": False,
        "financial_truth_changed": False,
        "formal_outputs_activated": False,
    }
    assert receipt["official_availability"]["status"] == "missing"
    assert receipt["official_availability"]["promotion_blocker"] is True
    assert receipt["official_availability"]["no_date_inferred"] is True
    assert receipt["official_availability"]["reason"] == "source_manifest_has_no_official_published_at_or_available_on"
    expected = {(doc, metric) for doc in DOCS for metric in METRICS}
    omissions = {(o["document_id"], o["metric"]) for o in receipt["omissions"] if "metric" in o}
    assert omissions == expected and len(receipt["omissions"]) == 9
    manifest_rows = {d["document_id"]: d for d in manifest["documents"]}
    for document_id, metric in sorted(expected):
        o = next(x for x in receipt["omissions"] if x.get("document_id") == document_id and x.get("metric") == metric)
        assert o["why_no_direct_current_3m_set"]
        assert o["selected_original_page"] == DOCS[document_id][1]
        if "geometry_evidence" in o:
            assert o["selected_page_text"] and "CONSOLIDATED" in o["selected_page_text"] and "ENDED" in o["selected_page_text"]
            ev = o["geometry_evidence"]
            assert ev["statement_identity"]["text"] == "CONSOLIDATED"
            assert ev["period"]["duration_months"] == 3 and _positive(ev["period"]["geometry"])
            assert ev["scale_currency"]["text"] == "Rupees in thousand" and _positive(ev["scale_currency"]["geometry"])
            assert ev["current_period_header"]["text"] in {"2021", "2022"} and _positive(ev["current_period_header"]["geometry"])
            assert _positive(ev["cell"]["geometry"])
    for document_id, (filename, _page, sha) in DOCS.items():
        raw = (INTAKE / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sha
        assert manifest_rows[document_id]["content_sha256"] == sha
        assert manifest_rows[document_id].get("published_at") is None
        assert manifest_rows[document_id].get("available_on") is None
    assert receipt["qualification"] == {
        "status": "blocked",
        "direct_three_month_set_qualified": False,
        "reason": "audit candidates only; official availability dates and independent reconciliation remain missing",
    }
    print("mlcf_fy22_interim_schedule_audit: PASS (zero promotion candidates; 9 explicit metric omissions; availability blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
