#!/usr/bin/env python3
"""Check the CI document restage review manifest and execution allowlist."""
from __future__ import annotations

import json
import re

import reprocess_company_documents as reprocess
from build_ci_reprocess_manifest import OUT, build_manifest
from psx_data import ROOT, load_json


EXECUTION_ALLOWLIST = ROOT / "config" / "ci_reprocess_allowlist.json"
DOC_ID_RE = re.compile(r"^psx:\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS = {"normalized_value", "raw_value", "value", "amount", "eps", "revenue", "pat"}
ALLOWED_KEY_PATHS = {"content_sha256", "document_count", "retained_hash_count", "transport_hash_required_count"}
MLCF_FY24_INTERIM_SOURCES = {
    "psx:219092": ("2023-09-30", "0d0f108957f32cd911be7bcdc5b01dcc46c1c4872dad81dc59e5e0a453977f05"),
    "psx:225623": ("2023-12-31", "921c6bffa5fb9fe8c001bc76288a60d811ddfc9acb2357753008d57f129cbf42"),
    "psx:229941": ("2024-03-31", "9de20cf7a12f2e049ca2cf437be2089f300e7fc8aed8adae4d0be97492374030"),
}
RETIRED_DGKC_DUPLICATE_OR_METADATA_LEADS = {"psx:260947", "psx:264230"}


def _fail(message: str) -> None:
    raise AssertionError(message)


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = path + (str(key),)
            yield next_path, item
            yield from _walk(item, next_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _walk(item, path + (str(idx),))


def _assert_no_numeric_facts(manifest: dict) -> None:
    for path, value in _walk(manifest):
        key = path[-1] if path else ""
        if key in FORBIDDEN_KEYS and key not in ALLOWED_KEY_PATHS:
            _fail(f"forbidden numeric fact-like key present at {'.'.join(path)}")
        if isinstance(value, str) and any(fragment in value.lower() for fragment in ("forecast", "valuation")):
            if value not in {"config/ci_reprocess_allowlist.json"}:
                _fail(f"forecast/valuation language is not allowed in restage manifest at {'.'.join(path)}")


def _assert_manifest_shape(manifest: dict) -> None:
    policy = manifest.get("policy") or {}
    for flag in ("owner_review_only", "metadata_only", "official_psx_dps_pdfs_only",
                 "no_pdf_fetch", "no_pdf_parsing", "no_reprocess_side_effects", "no_numeric_facts"):
        if policy.get(flag) is not True:
            _fail(f"manifest policy missing {flag}=true")
    pilot = manifest.get("pilot_symbols") or []
    if len(pilot) != 20 or len(set(pilot)) != 20:
        _fail("manifest pilot scope must be exactly 20 unique symbols")
    ids = manifest.get("document_ids") or []
    if not ids or len(ids) != len(set(ids)):
        _fail("manifest document_ids must be non-empty and unique")
    retired = RETIRED_DGKC_DUPLICATE_OR_METADATA_LEADS.intersection(ids)
    if retired:
        _fail(f"retired DGKC duplicate/metadata leads remain executable: {sorted(retired)}")
    documents = manifest.get("documents") or {}
    if set(documents) != set(ids):
        _fail("manifest documents map must exactly match document_ids")
    for doc_id in ids:
        if not DOC_ID_RE.fullmatch(str(doc_id)):
            _fail(f"{doc_id}: invalid document ID")
        doc = documents.get(doc_id) or {}
        if doc.get("document_id") != doc_id:
            _fail(f"{doc_id}: document_id mismatch")
        if doc.get("symbol") not in pilot:
            _fail(f"{doc_id}: symbol outside exact pilot")
        if doc.get("classification") not in {"financial_results", "financial_statement"}:
            _fail(f"{doc_id}: unsafe classification")
        if not str(doc.get("source_url") or "").startswith("https://dps.psx.com.pk/download/document/"):
            _fail(f"{doc_id}: source_url is not official DPS PDF")
        if f"/{str(doc_id).split(':', 1)[1]}.pdf" not in str(doc.get("source_url")):
            _fail(f"{doc_id}: URL/ID mismatch")
        if not str(doc.get("expected_title_pattern") or ""):
            _fail(f"{doc_id}: expected title pattern missing")
        try:
            if not re.search(str(doc["expected_title_pattern"]), str(doc.get("title") or ""), re.I):
                _fail(f"{doc_id}: expected title pattern does not match retained title")
        except re.error as exc:
            _fail(f"{doc_id}: invalid title regex {exc}")
        content_sha = doc.get("content_sha256")
        if content_sha is not None and not SHA256_RE.fullmatch(str(content_sha)):
            _fail(f"{doc_id}: invalid content_sha256")
        if doc.get("content_identity") == "retained_hash" and not content_sha:
            _fail(f"{doc_id}: retained_hash identity without hash")
        if doc.get("content_identity") == "transport_hash_required_before_receipt" and content_sha:
            _fail(f"{doc_id}: transport-hash identity should not carry retained hash")


def _assert_execution_allowlist_payload(expected: dict, payload: dict) -> None:
    expected_ids = list(expected.get("document_ids") or [])
    actual_ids = payload.get("document_ids") if isinstance(payload, dict) else None
    if actual_ids != expected_ids:
        _fail("config/ci_reprocess_allowlist.json document_ids drifted from metadata-derived review manifest")
    actual_docs = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(actual_docs, dict) or set(actual_docs) != set(expected_ids):
        _fail("config/ci_reprocess_allowlist.json documents map does not match metadata-derived IDs")
    for doc_id in expected_ids:
        expected_doc = expected["documents"][doc_id]
        actual_doc = actual_docs.get(doc_id) or {}
        if actual_doc.get("symbol") != expected_doc.get("symbol"):
            _fail(f"{doc_id}: execution allowlist symbol drift")
        if actual_doc.get("period") != expected_doc.get("period"):
            _fail(f"{doc_id}: execution allowlist period drift")
        pattern = actual_doc.get("expected_title_pattern")
        if not isinstance(pattern, str) or not pattern:
            _fail(f"{doc_id}: execution allowlist missing expected_title_pattern")
        try:
            if not re.search(pattern, expected_doc.get("title") or "", re.I):
                _fail(f"{doc_id}: execution allowlist title pattern no longer matches coverage title")
        except re.error as exc:
            _fail(f"{doc_id}: invalid execution allowlist title pattern {exc}")


def _assert_execution_allowlist(expected: dict) -> None:
    expected_ids = list(expected.get("document_ids") or [])
    payload = load_json(EXECUTION_ALLOWLIST, {})
    _assert_execution_allowlist_payload(expected, payload)
    approved = reprocess.load_allowlist(EXECUTION_ALLOWLIST, frozenset(expected_ids))
    if set(approved) != set(expected_ids):
        _fail("reprocess load_allowlist did not enforce the metadata-derived approved set")
    if set(reprocess.APPROVED_WAVE3_ALLOWLIST) != set(expected_ids):
        _fail("reprocess APPROVED_WAVE3_ALLOWLIST drifted from metadata-derived review manifest")


def _assert_exact_oversized_policy(expected: dict) -> None:
    doc = (expected.get("documents") or {}).get("psx:260032") or {}
    policy = reprocess.OVERSIZED_CHUNK_POLICIES.get("psx:260032") or {}
    if doc.get("source_url") != policy.get("source_url"):
        _fail("MLCF exact source URL drifted from the chunk policy")
    if doc.get("content_sha256") != policy.get("content_sha256"):
        _fail("MLCF exact source hash drifted from the chunk policy")
    if tuple(policy.get("ranges") or ()) != ((1, 120), (121, 240), (241, 360), (361, 401)):
        _fail("MLCF chunk ranges are not the approved four transport units")


def _assert_mlcf_fy24_interim_sources(expected: dict) -> None:
    documents = expected.get("documents") or {}
    for doc_id, (period, content_sha256) in MLCF_FY24_INTERIM_SOURCES.items():
        doc = documents.get(doc_id) or {}
        if doc.get("symbol") != "MLCF" or doc.get("classification") != "financial_results":
            _fail(f"{doc_id}: MLCF FY24 interim source identity drift")
        if doc.get("period") != period or (doc.get("safe_period") or {}).get("period_type") != "interim":
            _fail(f"{doc_id}: MLCF FY24 interim period identity drift")
        if doc.get("content_sha256") != content_sha256 or doc.get("content_identity") != "retained_hash":
            _fail(f"{doc_id}: MLCF FY24 source hash binding drift")
        if doc.get("approval_status") != "owner_approved":
            _fail(f"{doc_id}: MLCF FY24 source is not owner-approved")


def _assert_stale_execution_payloads_fail(expected: dict) -> None:
    good_docs = {}
    for doc_id, doc in (expected.get("documents") or {}).items():
        good_docs[doc_id] = {
            "symbol": doc["symbol"],
            "company_name": "fixture",
            "expected_title_pattern": doc["expected_title_pattern"],
            "period": doc["period"],
        }
    good = {"schema_version": 1, "document_ids": list(expected["document_ids"]), "documents": good_docs}
    bad_cases = []
    bad_cases.append({**good, "document_ids": good["document_ids"] + ["psx:999999"]})
    bad_cases.append({**good, "document_ids": good["document_ids"][:-1]})
    first = good["document_ids"][0]
    bad_period_docs = {key: dict(value) for key, value in good_docs.items()}
    bad_period_docs[first]["period"] = "1999-12-31"
    bad_cases.append({**good, "documents": bad_period_docs})
    bad_title_docs = {key: dict(value) for key, value in good_docs.items()}
    bad_title_docs[first]["expected_title_pattern"] = "does not match retained title"
    bad_cases.append({**good, "documents": bad_title_docs})
    for payload in bad_cases:
        try:
            _assert_execution_allowlist_payload(expected, payload)
        except AssertionError:
            continue
        _fail("stale/manual execution allowlist fixture was accepted")


def main() -> int:
    expected = build_manifest()
    expected_again = build_manifest()
    if _dump(expected) != _dump(expected_again):
        _fail("ci restage manifest builder is not deterministic")
    _assert_manifest_shape(expected)
    _assert_exact_oversized_policy(expected)
    _assert_mlcf_fy24_interim_sources(expected)
    _assert_no_numeric_facts(expected)
    committed = load_json(OUT, {})
    if _dump(committed) != _dump(expected):
        _fail("config/ci_reprocess_review_manifest.json is stale; run scripts/build_ci_reprocess_manifest.py")
    _assert_stale_execution_payloads_fail(expected)
    _assert_execution_allowlist(expected)
    print(f"ci_reprocess_manifest: PASS ({len(expected['document_ids'])} documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
