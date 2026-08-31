"""Focused integrity checker for the MLCF official-source intake tranche."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
RECEIPTS = ROOT / "state/company_intel/mlcf_official_intake_receipts.json"
SHA = re.compile(r"^[0-9a-f]{64}$")

def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    receipts = json.loads(RECEIPTS.read_text(encoding="utf-8"))
    assert manifest["symbol"] == receipts["symbol"] == "MLCF"
    docs = {d["document_id"]: d for d in manifest["documents"]}
    rows = {r["document_id"]: r for r in receipts["receipts"]}
    assert set(docs) == set(rows)
    assert receipts["policy"]["canonical_financial_state_modified"] is False
    for doc_id, doc in docs.items():
        row = rows[doc_id]
        assert row["source_url"] == doc["source_url"]
        assert row["content_sha256"] == doc["content_sha256"] and SHA.fullmatch(row["content_sha256"])
        assert row["content_length"] == doc["content_length"] and row["page_count"] == doc["page_count"]
        assert row["facts"] == [] and row["promotion_status"] == "quarantined"
        assert row["original_page"] == 1
        raw_path = ROOT / row["raw_path"]
        assert raw_path.is_file(), f"{doc_id}: original PDF not retained"
        assert raw_path.stat().st_size == doc["content_length"], f"{doc_id}: byte length mismatch"
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == doc["content_sha256"], f"{doc_id}: original hash mismatch"
        if doc["text_extractable"] is False:
            assert row["ocr"]["status"] != "success"
            assert row["ocr"]["engine_version"] is None
    assert receipts["coverage_before"] == receipts["coverage_after"]
    print(f"mlcf official intake: PASS ({len(rows)} documents, hashes bound, facts quarantined)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
