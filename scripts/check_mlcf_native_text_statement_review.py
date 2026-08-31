#!/usr/bin/env python3
"""Focused fail-closed checker for the MLCF native-text review receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "mlcf_official_intake_manifest.json"
RECEIPT = ROOT / "state" / "company_intel" / "mlcf_native_text_statement_review_receipt.json"
BASE = ROOT / ".cache" / "company_intel" / "mlcf_official_intake"


def fail(msg: str) -> None:
    raise AssertionError(msg)


def main() -> int:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    r = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if r.get("receipt_version") != "mlcf_native_text_statement_review_v1":
        fail("receipt version drifted")
    policy = r.get("policy") or {}
    for key in ("local_originals_only", "manifest_hash_required", "native_text_geometry_only", "no_network", "no_ocr", "audit_only", "promotion_allowed"):
        expected = False if key == "promotion_allowed" else True
        if policy.get(key) is not expected:
            fail(f"policy {key} mismatch")
    if policy.get("financial_facts_emitted") is not False or policy.get("coverage_changed") is not False or policy.get("case_changed") is not False:
        fail("review must not emit facts or change coverage/cases")
    manifest_rows = {x["document_id"]: x for x in m["documents"] if x["document_id"] in {"psx:194111", "issuer:mlcf:1q-2021-09", "issuer:mlcf:hy-2021-12", "issuer:mlcf:q3-2022-03"}}
    docs = r.get("documents") or []
    if len(docs) != 4 or {d.get("document_id") for d in docs} != set(manifest_rows):
        fail("exact four-document scope required")
    for d in docs:
        mid = d["document_id"]
        row = manifest_rows[mid]
        path = ROOT / d["raw_path"]
        if d.get("content_sha256") != row.get("content_sha256"):
            fail(f"{mid}: receipt hash differs from manifest")
        if hashlib.sha256(path.read_bytes()).hexdigest() != d.get("content_sha256"):
            fail(f"{mid}: local bytes hash mismatch")
        if d.get("original_page") != 1 or not d.get("selected_statement_pages"):
            fail(f"{mid}: page binding missing")
        if d.get("facts") != [] or d.get("promotion_status") != "audit_only":
            fail(f"{mid}: fact-like payload or promotion status present")
        for p in d["selected_statement_pages"]:
            if not p.get("text_geometry_sufficient") or not p.get("statement_headers") or not p.get("period_header_visible") or not p.get("units_header_visible"):
                fail(f"{mid}: selected page lacks visible header/period/unit geometry")
            if any(k in p for k in ("values", "facts", "metrics")):
                fail(f"{mid}: fact-like page payload present")
    if (r.get("summary") or {}).get("facts") != []:
        fail("summary facts must be empty")
    print("mlcf_native_text_statement_review: PASS (4 hash-bound documents; audit-only; no facts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
