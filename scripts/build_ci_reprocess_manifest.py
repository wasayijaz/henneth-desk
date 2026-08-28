"""Build the owner-review CI document restage manifest from coverage metadata.

The manifest is deliberately metadata-only. It reads only
state/company_intel/financial_coverage.json, never downloads or opens a PDF,
and never writes canonical state or restage receipts.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json


OUT = ROOT / "config" / "ci_reprocess_review_manifest.json"
COVERAGE_PATH = STATE / "company_intel" / "financial_coverage.json"
MANIFEST_VERSION = "ci_reprocess_review_manifest_v1"
PILOT_COUNT = 20
PSX_DPS_PDF_RE = re.compile(r"^https://dps\.psx\.com\.pk/download/document/(\d+)\.pdf$")
DOC_ID_RE = re.compile(r"^psx:(\d+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_CLASSIFICATIONS = {"financial_results", "financial_statement"}
FORBIDDEN_VALUE_KEYS = {"normalized_value", "raw_value", "value", "amount", "eps", "revenue", "pat"}

# The owner-approved review batch is expressed as slots, not document IDs.
# Document IDs are derived from the current retained coverage metadata.
APPROVED_REVIEW_SLOTS: tuple[dict[str, Any], ...] = (
    {
        "symbol": "DGKC",
        "period": "2025-06-30",
        "classification": "financial_results",
        "title_pattern": r"TRANSMISSION OF ANNUAL REPORT FOR THE YEAR ENDED JUNE 30, 2025",
        "require_retained_hash": True,
    },
    {
        "symbol": "DGKC",
        "period": "2025-09-30",
        "classification": "financial_results",
        "title_pattern": r"FINANCIAL RESULTS FOR THE 1ST QUARTER ENDED SEPTEMBER 30, 2025",
        "require_retained_hash": True,
    },
    {
        "symbol": "DGKC",
        "period": "2026-03-31",
        "classification": "financial_results",
        "title_pattern": r"Financial Results for the 3rd Quarter ended March 31, 2026",
        "require_retained_hash": True,
    },
)


def _stable_id(prefix: str, *parts: Any) -> str:
    text = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]}"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _document_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if DOC_ID_RE.fullmatch(text) else None


def _official_pdf_url(doc_id: str, value: Any) -> str | None:
    match = PSX_DPS_PDF_RE.fullmatch(str(value or "").strip())
    doc_match = DOC_ID_RE.fullmatch(doc_id)
    if not match or not doc_match or match.group(1) != doc_match.group(1):
        return None
    return f"https://dps.psx.com.pk/download/document/{match.group(1)}.pdf"


def _period_matches(doc: dict[str, Any], period: str, *, allow_title_only_period: bool = False) -> bool:
    safe_period = doc.get("safe_period") if isinstance(doc.get("safe_period"), dict) else {}
    if safe_period.get("period_end") == period:
        return True
    if allow_title_only_period and not safe_period:
        return True
    return period in _text(doc.get("title"))


def _assert_metadata_only(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = path + (str(key),)
            if key in FORBIDDEN_VALUE_KEYS:
                raise ValueError(f"numeric fact-like key is not allowed in restage manifest input: {'.'.join(next_path)}")
            _assert_metadata_only(item, next_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _assert_metadata_only(item, path + (str(idx),))


def _candidate_docs(coverage: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    row = (coverage.get("companies") or {}).get(symbol) or {}
    docs = row.get("indexed_official_financial_docs") or []
    return [doc for doc in docs if isinstance(doc, dict)]


def _resolve_slot(coverage: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
    symbol = str(slot["symbol"])
    period = str(slot["period"])
    classification = str(slot["classification"])
    pattern = str(slot["title_pattern"])
    matches = []
    for doc in _candidate_docs(coverage, symbol):
        doc_id = _document_id(doc.get("document_id"))
        title = _text(doc.get("title"))
        if not doc_id:
            continue
        if doc.get("classification") != classification or classification not in ALLOWED_CLASSIFICATIONS:
            continue
        source_url = _official_pdf_url(doc_id, doc.get("source_url"))
        if not source_url:
            continue
        if not _period_matches(doc, period, allow_title_only_period=bool(slot.get("allow_title_only_period"))):
            continue
        if not re.search(pattern, title, re.I):
            continue
        content_sha256 = str(doc.get("content_sha256") or "").lower() or None
        if content_sha256 and not SHA256_RE.fullmatch(content_sha256):
            continue
        if slot.get("require_retained_hash") and not content_sha256:
            continue
        matches.append((doc_id, doc, source_url, content_sha256))
    if len(matches) != 1:
        raise ValueError(f"{symbol} {period}: expected exactly one metadata-derived restage document, found {len(matches)}")
    doc_id, doc, source_url, content_sha256 = matches[0]
    safe_period = doc.get("safe_period") if isinstance(doc.get("safe_period"), dict) else None
    return {
        "document_id": doc_id,
        "symbol": symbol,
        "period": period,
        "classification": classification,
        "title": _text(doc.get("title")),
        "expected_title_pattern": pattern,
        "published_at": doc.get("published_at"),
        "source_url": source_url,
        "content_sha256": content_sha256,
        "content_identity": "retained_hash" if content_sha256 else "transport_hash_required_before_receipt",
        "safe_period": safe_period,
        "approval_status": "owner_review_required",
        "reason": "metadata-derived approved review candidate for bounded CI filing restage",
    }


def build_manifest(coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    coverage = coverage or load_json(COVERAGE_PATH, {})
    _assert_metadata_only(coverage)
    pilot = list(coverage.get("pilot_symbols") or [])
    if len(pilot) != PILOT_COUNT or len(set(pilot)) != PILOT_COUNT:
        raise ValueError("financial coverage pilot scope must be exactly 20 unique symbols")
    docs = [_resolve_slot(coverage, slot) for slot in APPROVED_REVIEW_SLOTS]
    ids = [doc["document_id"] for doc in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("metadata-derived restage manifest contains duplicate document IDs")
    documents = {doc["document_id"]: doc for doc in docs}
    return {
        "schema_version": 1,
        "manifest_version": MANIFEST_VERSION,
        "manifest_id": _stable_id("cirestage", MANIFEST_VERSION, *ids),
        "source": {
            "financial_coverage": "state/company_intel/financial_coverage.json",
        },
        "policy": {
            "owner_review_only": True,
            "metadata_only": True,
            "official_psx_dps_pdfs_only": True,
            "no_pdf_fetch": True,
            "no_pdf_parsing": True,
            "no_reprocess_side_effects": True,
            "no_numeric_facts": True,
            "execution_allowlist_must_match_this_manifest": "config/ci_reprocess_allowlist.json",
        },
        "pilot_symbols": pilot,
        "approved_review_slots": [
            {
                "symbol": slot["symbol"],
                "period": slot["period"],
                "classification": slot["classification"],
                "require_retained_hash": bool(slot.get("require_retained_hash")),
            }
            for slot in APPROVED_REVIEW_SLOTS
        ],
        "document_ids": ids,
        "documents": documents,
        "summary": {
            "document_count": len(ids),
            "symbols": sorted({doc["symbol"] for doc in docs}),
            "retained_hash_count": sum(1 for doc in docs if doc.get("content_sha256")),
            "transport_hash_required_count": sum(1 for doc in docs if not doc.get("content_sha256")),
        },
    }


def build() -> dict[str, Any]:
    manifest = build_manifest()
    save_json(OUT, manifest)
    print(f"ci_reprocess_review_manifest: {len(manifest['document_ids'])} documents")
    return manifest


if __name__ == "__main__":
    build()
