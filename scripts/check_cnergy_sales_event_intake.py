#!/usr/bin/env python3
"""Fail-closed checker for the isolated CNERGY sales-event intake lane."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "ci_cnergy_sales_event_intake_manifest.json"
RECEIPT = ROOT / "state" / "company_intel" / "cnergy_sales_event_intake_receipt.json"
SOURCE_REGISTRY = ROOT / "state" / "company_intel" / "source_registry.json"


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    registry = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8"))
    if manifest.get("kind") != "ci_cnergy_sales_event_intake_manifest":
        fail("manifest kind drifted")
    policy = manifest.get("policy") or {}
    for key in ("official_issuer_sources_only", "exact_source_registry_ids_only",
                "original_bytes_hash_bound_before_receipt", "no_ocr",
                "no_case_seed", "no_fact_promotion"):
        if policy.get(key) is not True:
            fail(f"policy {key}=true required")
    issuer = manifest.get("issuer") or {}
    if issuer.get("ticker") != "CNERGY":
        fail("ticker drifted")
    rows = manifest.get("sources") or []
    if [r.get("source_registry_id") for r in rows] != [
        "issuer:d9fcb2cee8c47f0960533b9f", "issuer:439f94b15635143d5d16b663"
    ]:
        fail("source scope/order drifted")
    primary, alternative = rows
    if primary.get("availability") != "unavailable_http_404" or primary.get("date_year_defensible") is not False:
        fail("primary source must remain explicitly date-blocked")
    if primary.get("content_sha256") is not None or primary.get("citation_page") is not None:
        fail("blocked primary cannot claim bytes/page evidence")
    if alternative.get("availability") != "retrieved" or alternative.get("citation_page") != 1:
        fail("verified alternative retrieval/page evidence missing")
    digest = alternative.get("content_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        fail("alternative content hash invalid")
    if alternative.get("original_document_date") != "2018-12-04" or alternative.get("date_year_defensible") is not True:
        fail("alternative original date/year is not bound")
    raw_path = ROOT / str(alternative.get("raw_path") or "")
    if not raw_path.is_file():
        fail("verified alternative original PDF is not retained locally")
    if raw_path.stat().st_size != alternative.get("content_length"):
        fail("verified alternative byte length mismatch")
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != digest:
        fail("verified alternative original hash mismatch")
    if urlparse(primary["url"]).netloc != "www.cnergyico.com" or urlparse(alternative["url"]).netloc != "www.cnergyico.com":
        fail("non-issuer URL accepted")
    registry_rows = [
        row for row in (registry.get("tickers", {}).get("CNERGY", {}).get("document_links", []) or [])
        if isinstance(row, dict) and row.get("id") in {primary["source_registry_id"], alternative["source_registry_id"]}
    ]
    if {row.get("id") for row in registry_rows} != {primary["source_registry_id"], alternative["source_registry_id"]}:
        fail("source registry bindings missing")
    if {row.get("url") for row in registry_rows} != {primary["url"], alternative["url"]}:
        fail("source registry URL bindings drifted")
    if receipt.get("ticker") != "CNERGY" or receipt.get("manifest") != "config/ci_cnergy_sales_event_intake_manifest.json":
        fail("receipt identity drifted")
    if receipt.get("primary_event", {}).get("event_status") != "observed_event_blocked":
        fail("receipt must expose primary observed-event-blocked status")
    if receipt.get("verified_alternative", {}).get("content_sha256") != digest:
        fail("receipt hash does not match manifest")
    if receipt.get("promotion", {}).get("case_seeds") != [] or receipt.get("promotion", {}).get("facts") != []:
        fail("case/fact promotion must remain zero")
    if receipt.get("promotion", {}).get("financial_truth_changed") is not False:
        fail("financial truth must remain unchanged")
    print("cnergy_sales_event_intake: PASS (primary blocked; dated alternative observed-only; zero promotion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
