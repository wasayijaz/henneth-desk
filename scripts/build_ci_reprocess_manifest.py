"""Build the owner-review CI document restage manifest from retained metadata.

The manifest is deliberately metadata-only. It reads retained coverage plus
explicit owner-approved official PSX full-report counterparts, never downloads or opens a PDF,
and never writes canonical state or restage receipts.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json


OUT = ROOT / "config" / "ci_reprocess_review_manifest.json"
COVERAGE_PATH = STATE / "company_intel" / "financial_coverage.json"
RESEARCH_INDEX_PATH = STATE / "research_index.json"
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
    # Exact retained MLCF FY24 interim results extend the first-case financial
    # history only.  Each source remains hash-pinned and must pass the same
    # PSX/title/period gates as the existing FY26 quarterly tranche.
    {
        "symbol": "MLCF",
        "period": "2023-09-30",
        "period_type": "interim",
        "classification": "financial_results",
        "title_pattern": r"MLCF Financial Results for the Quarter Ended 30\.09\.2023",
        "require_retained_hash": True,
        "source_document_id": "psx:219092",
        "source_content_sha256": "0d0f108957f32cd911be7bcdc5b01dcc46c1c4872dad81dc59e5e0a453977f05",
    },
    {
        "symbol": "MLCF",
        "period": "2023-12-31",
        "period_type": "interim",
        "classification": "financial_results",
        "title_pattern": r"MLCF-Financial Results 31\.12\.2023",
        "require_retained_hash": True,
        "source_document_id": "psx:225623",
        "source_content_sha256": "921c6bffa5fb9fe8c001bc76288a60d811ddfc9acb2357753008d57f129cbf42",
    },
    {
        "symbol": "MLCF",
        "period": "2024-03-31",
        "period_type": "interim",
        "classification": "financial_results",
        "title_pattern": r"MLCF-Financial Results 31\.03\.2024",
        "require_retained_hash": True,
        "source_document_id": "psx:229941",
        "source_content_sha256": "9de20cf7a12f2e049ca2cf437be2089f300e7fc8aed8adae4d0be97492374030",
    },
    {
        "symbol": "MLCF",
        "period": "2025-06-30",
        "classification": "financial_statement",
        "title_pattern": r"MLCF Transmission of Annual Financial Statements for the Year Ended 30\.06\.2025",
        "require_retained_hash": True,
        "source_document_id": "psx:260032",
        "source_content_sha256": "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1",
    },
    # Exact retained full quarterly reports for the selected MLCF case.  This
    # is a bounded three-period parser-proof tranche, not an assertion that the
    # results contain qualified standalone three-month financial facts.
    {
        "symbol": "MLCF",
        "period": "2025-09-30",
        "period_type": "interim",
        "classification": "financial_statement",
        "title_pattern": r"MLCF Transmission of Quarterly Financial Statements for the Period Ended 30\.09\.2025",
        "require_retained_hash": True,
        "source_document_id": "psx:263397",
        "source_content_sha256": "a05eeee23485edd71c6c096a606a3b6fd76d6687e13bdaf032f97b59b9cdcc7e",
    },
    {
        "symbol": "MLCF",
        "period": "2025-12-31",
        "period_type": "interim",
        "classification": "financial_statement",
        "title_pattern": r"MLCF-Transmission of Quarterly Financial Statements for the Period Ended 31\.12\.2025",
        "require_retained_hash": True,
        "source_document_id": "psx:271712",
        "source_content_sha256": "f4f9d671658d9c402d650fd3e45bc098bd410084bba7d8fdcf7f8729cf9e5f69",
    },
    {
        "symbol": "MLCF",
        "period": "2026-03-31",
        "period_type": "interim",
        "classification": "financial_statement",
        "title_pattern": r"Transmission of Quarterly Financial Statements for the Period Ended 31\.03\.2026",
        "require_retained_hash": True,
        "source_document_id": "psx:275425",
        "source_content_sha256": "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f",
    },
    {
        "symbol": "DGKC",
        "period": "2026-03-31",
        "classification": "financial_results",
        "title_pattern": r"TRANSMISSION OF QUARTERLY REPOR TFOR THE PERIOD ENDED MARCH 31, 2026",
        "require_retained_hash": True,
        "source_document_id": "psx:275962",
    },
    # Owner-approved MARI evidence-path pilot.  FY26 annual includes the FY25
    # comparative, so a separate FY25 annual would duplicate the first
    # financial-history increment.  The three exact FY26 quarter reports test
    # standalone three-month extraction without widening provider scope.
    {
        "symbol": "MARI",
        "period": "2026-06-30",
        "period_type": "annual",
        "classification": "financial_results",
        "title_pattern": r"Financial Results for the Year Ended 30-06-2026",
        "require_retained_hash": False,
        "source_document_id": "psx:280901",
        "owner_approved": True,
    },
    {
        "symbol": "MARI",
        "period": "2025-09-30",
        "period_type": "interim",
        "classification": "financial_statement",
        "title_pattern": r"Transmission of Quarterly Report for the period ended September 30\. 2025",
        "require_retained_hash": False,
        "source_document_id": "psx:264550",
        "owner_approved": True,
    },
    {
        "symbol": "MARI",
        "period": "2025-12-31",
        "period_type": "interim",
        "classification": "financial_statement",
        "title_pattern": r"Transmission of Quarterly Financial Statements for the Period Ended 2025-12-31",
        "require_retained_hash": False,
        "source_document_id": "psx:271327",
        "owner_approved": True,
    },
    {
        "symbol": "MARI",
        "period": "2026-03-31",
        "period_type": "interim",
        "classification": "financial_statement",
        "title_pattern": r"Transmission of Quarterly Report for the Period Ended 2026-03-31",
        "require_retained_hash": False,
        "source_document_id": "psx:275583",
        "owner_approved": True,
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


def _resolve_slot(coverage: dict[str, Any], slot: dict[str, Any], research_index: dict[str, Any]) -> dict[str, Any]:
    symbol = str(slot["symbol"])
    period = str(slot["period"])
    classification = str(slot["classification"])
    pattern = str(slot["title_pattern"])
    explicit_id = _document_id(slot.get("source_document_id"))
    if explicit_id:
        row = (research_index.get("documents") or {}).get(explicit_id) or {}
        doc_id = _document_id(row.get("id") or row.get("official_document_id"))
        title = _text(row.get("title"))
        source_url = _official_pdf_url(explicit_id, row.get("url"))
        content_sha256 = str(row.get("content_sha256") or slot.get("source_content_sha256") or "").lower() or None
        pinned_sha = slot.get("source_content_sha256")
        if pinned_sha and content_sha256 != str(pinned_sha).lower():
            raise ValueError(f"{symbol} {period}: exact source hash mismatch")
        if (doc_id != explicit_id or row.get("source") != "PSX DPS" or row.get("source_type") != "filing"
                or symbol not in (row.get("tickers") or []) or not source_url
                or not re.search(pattern, title, re.I)
                or (content_sha256 and not SHA256_RE.fullmatch(content_sha256))
                or (slot.get("require_retained_hash") and not content_sha256)):
            raise ValueError(f"{symbol} {period}: explicit approved counterpart metadata is invalid")
        return {
            "document_id": explicit_id, "symbol": symbol, "period": period,
            "classification": classification, "title": title,
            "expected_title_pattern": pattern, "published_at": row.get("published_at"),
            "source_url": source_url, "content_sha256": content_sha256,
            "content_identity": ("retained_hash" if content_sha256 else "transport_hash_required_before_receipt"),
            "safe_period": {"period_end": period, "period_type": (slot.get("period_type") or ("annual" if classification == "financial_statement" else "interim")), "source": ("owner_approved_exact_source" if slot.get("source_content_sha256") else "owner_approved_counterpart")},
            "approval_status": "owner_approved" if (slot.get("owner_approved") or slot.get("source_content_sha256")) else "owner_review_required",
            "reason": ("owner-approved official exact source; transport hash must bind before any receipt or fact"
                       if slot.get("owner_approved") else "owner-approved retained official exact source for bounded CI filing restage"),
        }
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


def build_manifest(coverage: dict[str, Any] | None = None, research_index: dict[str, Any] | None = None) -> dict[str, Any]:
    coverage = coverage or load_json(COVERAGE_PATH, {})
    research_index = research_index or load_json(RESEARCH_INDEX_PATH, {})
    _assert_metadata_only(coverage)
    pilot = list(coverage.get("pilot_symbols") or [])
    if len(pilot) != PILOT_COUNT or len(set(pilot)) != PILOT_COUNT:
        raise ValueError("financial coverage pilot scope must be exactly 20 unique symbols")
    docs = [_resolve_slot(coverage, slot, research_index) for slot in APPROVED_REVIEW_SLOTS]
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
            "research_index": "state/research_index.json",
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
