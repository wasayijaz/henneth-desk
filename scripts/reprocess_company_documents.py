#!/usr/bin/env python3
"""Exact-ID offline-safe restage transport for selected PSX company documents.

This module is deliberately a transport boundary, not a second document ledger.
It accepts only exact operator-approved PSX DPS document IDs, verifies that each
ID is still present in the retained research index and in the Wave 3 allowlist,
downloads/verifies the PDF through an injectable transport, stages a run-scoped
registry/queue for a caller-supplied consumer, and appends a metadata-only
receipt. It never rewrites ``state/company_documents.json`` directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

from financial_statement_facts import diagnose_page_records, PARSER_VERSION, PARSER_REVISION
from psx_data import ROOT, STATE, load_json, save_json
from pdf_chunking import SourceIdentity, split_pdf, ChunkRecord

MAX_DOCUMENT_IDS = 5
MAX_REDIRECTS = 4
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_RUN_BYTES = 30 * 1024 * 1024
MAX_FILE_PAGES = 120
MAX_RUN_PAGES = 300
MIN_NORMALIZED_TEXT_CHARS = 32
LEGACY_PARSER_REVISION = "legacy_geometry_v1"
BASE_DPS_HOST = "dps.psx.com.pk"

# The only retained-original escape hatch is this exact, owner-reviewed source.
# Keep this mapping explicit: do not scan caches or infer alternate paths.
RETAINED_ORIGINALS: dict[str, dict[str, Any]] = {
    "psx:260947": {
        "relative_path": Path(".cache") / "company_intel" / "raw" / "manual" / "260947.pdf",
        "source_url": "https://dps.psx.com.pk/download/document/260947.pdf",
        "content_sha256": "1a10091295cf7a815f1910eb418215d501d42b52e39dcbd0b54a53fd1aceaa7d",
        "page_count": 333,
    },
}
APPROVED_WAVE3_ALLOWLIST: frozenset[str] = frozenset({
    "psx:260947",
    "psx:264230",
    "psx:275962",
})

DOCUMENT_ID_RE = re.compile(r"^psx:(\d+)$")
DOCUMENT_PATH_RE = re.compile(r"^/download/document/(\d+)\.pdf$", re.I)
SPACE_RE = re.compile(r"\s+")
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}
ALLOWED_DOC_TYPES = {"financial_results", "financial_statement"}
ALLOWED_TITLE_RE = re.compile(
    r"\b(financial results?|financial statements?|annual report|annual accounts|"
    r"quarterly accounts?|half.?yearly accounts?|transmission of .*financial)\b",
    re.I,
)
EXCLUDED_TITLE_RE = re.compile(
    r"\b(revoked|notice|non.?statement|board meeting|other than financial results|"
    r"agm|egm|eogm|book closure|corporate briefing|disclosure of interest|"
    r"material information|credit rating|addendum|corrigendum)\b",
    re.I,
)

# Fail-closed by default. The orchestrator should supply an exact Wave 3 manifest
# with {"document_ids": ["psx:..."]}. Keeping this empty prevents accidental
# broad restages when the manifest is not wired yet.
BUILTIN_ALLOWLIST: frozenset[str] = frozenset()
PROCESSED_RECEIPT_STATUSES = {"success", "processed_unsupported"}
CANONICAL_RELATIVE_PATHS = (
    Path("company_documents.json"),
    Path("company_event_ledger.json"),
    Path("document_synthesis_queue.json"),
    Path("company_financial_series.json"),
    Path("company_intel") / "financial_model_inputs.json",
    Path("company_intel") / "financial_evidence_reconciliation.json",
    Path("company_intel") / "financial_truth_qualification.json",
    Path("company_intel") / "financial_forecasts.json",
    Path("company_intel") / "formal_valuations.json",
    Path("company_intel") / "market_expectations.json",
    Path("company_intel") / "evidence_watchlist.json",
    Path("company_intel") / "cement_operating_series.json",
)
CI_SLICE_PATH = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
CI_ARTIFACT_INTEGRITY_EXCLUDED_STATE_NAMES = {
    "artifact_integrity.json",
    "backfill_cursor.json",
    "cursors.json",
    "reprocess_receipts.json",
    "supabase_archive_receipt.json",
    "private_thesis_storage_receipt.json",
    "release_integrity_receipt.json",
}


class UnsafeInput(ValueError):
    """Operator input or retained metadata failed the pre-network safety contract."""


class DegradedDocument(RuntimeError):
    """One document could not be safely transported; the run should continue and exit 0."""


class ReprocessTransactionError(RuntimeError):
    """A canonical consume transaction failed without writing a success receipt."""

    def __init__(self, stage: str, reason: str, *, rolled_back: bool,
                 canonical_state_committed: bool = False,
                 documents: list[dict[str, Any]] | None = None) -> None:
        self.stage = stage
        self.reason = _clean_text(reason)[:500]
        self.rolled_back = bool(rolled_back)
        self.canonical_state_committed = bool(canonical_state_committed)
        self.documents = documents or []
        super().__init__(f"{stage}: {self.reason}")

    def to_result(self, run_id: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": 1,
            "status": "transaction_failed",
            "failure_stage": self.stage,
            "reason": self.reason,
            "rolled_back": self.rolled_back,
            "canonical_state_committed": self.canonical_state_committed,
            "receipt_written": False,
            "parser_version": PARSER_VERSION,
            "parser_revision": PARSER_REVISION,
        }
        if run_id:
            result["run_id"] = run_id
        if self.documents:
            result["documents"] = self.documents
        return result


def chunk_verified_oversized_pdf(doc: "VerifiedDocument", fetched: "FetchResult",
                                 output_dir: Path, *, expected_page_count: int | None = None,
                                 period_end: str | None = None) -> list[ChunkRecord]:
    """Chunk one verified oversized source for canonical extraction.

    This is intentionally separate from the normal 120-page transport gate:
    the source has already passed byte/hash/type checks, and only the temporary
    parser units are opened.  The global cap is unchanged; all facts retain the
    original source identity and page numbers.
    """
    page_count = int(expected_page_count or fetched.page_count)
    identity = SourceIdentity(
        document_id=doc.doc_id,
        title=str(doc.row.get("title") or doc.row.get("digest") or ""),
        source_url=doc.url,
        content_sha256=fetched.content_sha256,
        published_at=doc.row.get("published_at") or doc.row.get("date"),
        available_on=doc.row.get("available_on"),
        page_count=page_count,
    )
    source_path = output_dir / f"{doc.doc_id.replace(':', '_')}_{fetched.content_sha256[:16]}_source.pdf"
    source_path.write_bytes(fetched.body)
    chunks_dir = output_dir / "chunks"
    records = split_pdf(source_path, chunks_dir, identity)
    # The canonical extraction seam consumes the records and maps parser pages
    # back to source pages.  The enclosing reprocess transaction removes the
    # source/chunk directory after the consumer and receipt have completed.
    return records


@dataclass(frozen=True)
class VerifiedDocument:
    doc_id: str
    numeric_id: str
    row: dict[str, Any]
    url: str
    tickers: list[str]
    content_sha256: str | None = None
    manifest: dict[str, Any] | None = None


@dataclass
class FetchResult:
    body: bytes
    content_sha256: str
    content_length: int
    final_url: str
    content_type: str
    page_count: int
    normalized_chars: int


class RunBudget:
    def __init__(self) -> None:
        self.bytes = 0
        self.pages = 0

    def add_bytes(self, count: int) -> None:
        if self.bytes + count > MAX_RUN_BYTES:
            raise DegradedDocument("run_byte_cap_exceeded")
        self.bytes += count

    def add_pages(self, count: int) -> None:
        if self.pages + count > MAX_RUN_PAGES:
            raise DegradedDocument("run_page_cap_exceeded")
        self.pages += count


class RequestsTransport:
    """Lazy requests-backed transport. Tests pass an injectable fake instead."""

    def __init__(self) -> None:
        import requests

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 HennethDesk/2.CI.0 exact-id-restage"
        })

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._session.get(url, **kwargs)


def _utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4)


def _clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def _doc_rows(payload: Any) -> dict[str, dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("documents"), dict):
        return {str(k): v for k, v in payload["documents"].items() if isinstance(v, dict)}
    if isinstance(payload, list):
        return {str(i): row for i, row in enumerate(payload) if isinstance(row, dict)}
    return {}


def validate_operator_ids(document_ids: Iterable[str]) -> list[str]:
    ids = list(document_ids or [])
    if not 1 <= len(ids) <= MAX_DOCUMENT_IDS:
        raise UnsafeInput("provide 1-5 repeated --document-id values")
    if len(ids) != len(set(ids)):
        raise UnsafeInput("duplicate document IDs are not allowed")
    for value in ids:
        raw = str(value or "").strip()
        if raw != value or not DOCUMENT_ID_RE.fullmatch(raw):
            raise UnsafeInput(
                "document IDs must be exact psx:<digits>; wildcards, ranges, tickers, URLs, files and stdin are rejected"
            )
    return ids


def load_allowlist(manifest_path: Path | None = None,
                   expected_ids: frozenset[str] = APPROVED_WAVE3_ALLOWLIST) -> dict[str, dict[str, Any]]:
    allowed = {doc_id: {"doc_id": doc_id} for doc_id in BUILTIN_ALLOWLIST}
    if manifest_path:
        payload = load_json(manifest_path, {})
        values = payload.get("document_ids") if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise UnsafeInput("allowlist manifest must contain document_ids list")
        if len(values) != len(set(values)):
            raise UnsafeInput("allowlist manifest contains duplicate document IDs")
        for value in values:
            if not isinstance(value, str) or not DOCUMENT_ID_RE.fullmatch(value):
                raise UnsafeInput("allowlist manifest contains a non-exact document ID")
        manifest_ids = set(values)
        if manifest_ids != set(expected_ids):
            raise UnsafeInput("allowlist manifest must exactly match the approved Wave 3 document IDs")
        documents = payload.get("documents") if isinstance(payload, dict) else None
        if not isinstance(documents, dict) or set(documents) != manifest_ids:
            raise UnsafeInput("allowlist manifest must contain exact per-document metadata")
        for doc_id, meta in documents.items():
            if not isinstance(meta, dict):
                raise UnsafeInput(f"{doc_id}: allowlist metadata must be an object")
            symbol = meta.get("symbol")
            company = meta.get("company_name")
            pattern = meta.get("expected_title_pattern")
            period = meta.get("period")
            if not all(isinstance(v, str) and v.strip() for v in (symbol, company, pattern, period)):
                raise UnsafeInput(f"{doc_id}: allowlist metadata requires symbol, company_name, expected_title_pattern and period")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise UnsafeInput(f"{doc_id}: invalid expected_title_pattern") from exc
            allowed[doc_id] = {
                "doc_id": doc_id,
                "symbol": symbol.strip().upper(),
                "company_name": _clean_text(company),
                "expected_title_pattern": pattern,
                "period": period.strip(),
            }
    return allowed


def _pilot_symbols(state_root: Path) -> set[str]:
    payload = load_json(state_root / "company_profiles.json", {})
    values = (payload.get("pilot") or {}).get("symbols") if isinstance(payload, dict) else []
    return {str(v).strip().upper() for v in values or [] if str(v).strip()}


def _row_doc_id(key: str, row: dict[str, Any]) -> str:
    for field in ("doc_id", "id", "hash"):
        value = row.get(field)
        if isinstance(value, str) and DOCUMENT_ID_RE.fullmatch(value):
            return value
    value = row.get("official_document_id")
    if str(value or "").isdigit():
        return f"psx:{value}"
    if DOCUMENT_ID_RE.fullmatch(str(key)):
        return str(key)
    return ""


def _row_tickers(row: dict[str, Any]) -> list[str]:
    values = row.get("tickers") or row.get("symbols") or row.get("symbol") or []
    if isinstance(values, str):
        values = [values]
    return sorted({str(v).strip().upper() for v in values if str(v).strip()})


def _validated_dps_url(doc_id: str, url: Any) -> str:
    numeric = DOCUMENT_ID_RE.fullmatch(doc_id)
    if not numeric:
        raise UnsafeInput(f"{doc_id}: invalid document ID")
    parsed = urlparse(str(url or ""))
    match = DOCUMENT_PATH_RE.fullmatch(parsed.path or "")
    if parsed.scheme != "https" or parsed.hostname != BASE_DPS_HOST or not match:
        raise UnsafeInput(f"{doc_id}: URL must be https://{BASE_DPS_HOST}/download/document/<same-id>.pdf")
    if match.group(1) != numeric.group(1):
        raise UnsafeInput(f"{doc_id}: URL document number mismatch")
    if parsed.params or parsed.query or parsed.fragment:
        raise UnsafeInput(f"{doc_id}: URL must not contain params, query or fragment")
    return f"https://{BASE_DPS_HOST}{parsed.path}"


def _manifest_matches(row: dict[str, Any], tickers: list[str], title: str, meta: dict[str, Any]) -> bool:
    symbol = str(meta.get("symbol") or "").upper()
    company = _clean_text(meta.get("company_name"))
    pattern = str(meta.get("expected_title_pattern") or "")
    return (
        symbol in tickers
        and _clean_text(row.get("company_name")) == company
        and bool(re.search(pattern, title, re.I))
    )


def _validate_row(doc_id: str, row: dict[str, Any], key: str, pilot: set[str],
                  allowlist: dict[str, dict[str, Any]]) -> VerifiedDocument:
    if doc_id not in allowlist:
        raise UnsafeInput(f"{doc_id}: not in Wave 3 exact allowlist")
    manifest_meta = allowlist[doc_id]
    row_doc_id = _row_doc_id(key, row)
    if row_doc_id != doc_id:
        raise UnsafeInput(f"{doc_id}: retained research_index ID mismatch")
    if row.get("source") != "PSX DPS" or row.get("source_type") != "filing":
        raise UnsafeInput(f"{doc_id}: source must be retained PSX DPS filing metadata")
    tickers = _row_tickers(row)
    if not tickers or not set(tickers).issubset(pilot):
        raise UnsafeInput(f"{doc_id}: tickers must be exact current pilot symbols")
    doc_type = str(row.get("doc_type") or "")
    title = _clean_text(row.get("title") or row.get("digest"))
    manifest_report = _manifest_matches(row, tickers, title, manifest_meta)
    if doc_type not in ALLOWED_DOC_TYPES and not (doc_type == "company_announcement" and manifest_report):
        raise UnsafeInput(f"{doc_id}: document must be a financial statement/results filing or exact manifest-pinned report")
    if not ALLOWED_TITLE_RE.search(title) and not manifest_report:
        raise UnsafeInput(f"{doc_id}: document title must match a statement/report predicate")
    if EXCLUDED_TITLE_RE.search(title):
        raise UnsafeInput(f"{doc_id}: notices/revoked/nonstatement filings are excluded")
    url = _validated_dps_url(doc_id, row.get("url") or row.get("source_url"))
    numeric_id = DOCUMENT_ID_RE.fullmatch(doc_id).group(1)  # type: ignore[union-attr]
    known = row.get("content_sha256")
    known_sha = str(known).lower() if isinstance(known, str) and re.fullmatch(r"[0-9a-fA-F]{64}", known) else None
    return VerifiedDocument(doc_id=doc_id, numeric_id=numeric_id, row=row, url=url, tickers=tickers,
                            content_sha256=known_sha, manifest=manifest_meta)


def resolve_documents(document_ids: list[str], state_root: Path,
                      allowlist: dict[str, dict[str, Any]]) -> list[VerifiedDocument]:
    index = load_json(state_root / "research_index.json", {})
    rows = _doc_rows(index)
    pilot = _pilot_symbols(state_root)
    if not pilot:
        raise UnsafeInput("company_profiles.pilot.symbols is unavailable")
    resolved: list[VerifiedDocument] = []
    for doc_id in document_ids:
        matches = [(key, row) for key, row in rows.items() if _row_doc_id(key, row) == doc_id]
        if len(matches) != 1:
            raise UnsafeInput(f"{doc_id}: must resolve to exactly one retained research_index row")
        resolved.append(_validate_row(doc_id, matches[0][1], matches[0][0], pilot, allowlist))
    return resolved


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", {}) or {}
    if hasattr(headers, "get"):
        return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
    return None


def _status(response: Any) -> int:
    return int(getattr(response, "status_code", 0) or 0)


def _chunks(response: Any) -> Iterable[bytes]:
    if hasattr(response, "iter_content"):
        yield from response.iter_content(chunk_size=64 * 1024)
        return
    content = getattr(response, "content", None)
    if content is None:
        content = getattr(response, "body", b"")
    yield bytes(content)


def _redirect_location(response: Any) -> str | None:
    if _status(response) not in {301, 302, 303, 307, 308}:
        return None
    return _header(response, "Location")


def _validate_redirect_url(doc: VerifiedDocument, base_url: str, location: str) -> str:
    next_url = urljoin(base_url, location)
    parsed = urlparse(next_url)
    match = DOCUMENT_PATH_RE.fullmatch(parsed.path or "")
    if parsed.scheme != "https" or parsed.hostname != BASE_DPS_HOST or not match or match.group(1) != doc.numeric_id:
        raise DegradedDocument("redirect_target_mismatch")
    return f"https://{BASE_DPS_HOST}{parsed.path}"


def _validate_pdf(body: bytes, budget: RunBudget, *, allow_image_only: bool = False,
                  allow_oversized_chunk: bool = False) -> tuple[int, int]:
    if not body.startswith(b"%PDF-"):
        raise DegradedDocument("pdf_magic_mismatch")
    try:
        import pymupdf

        with pymupdf.open(stream=body, filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise DegradedDocument("encrypted_pdf")
            page_count = len(pdf)
            if page_count < 1:
                raise DegradedDocument("empty_pdf")
            if page_count > MAX_FILE_PAGES and not allow_oversized_chunk:
                raise DegradedDocument("file_page_cap_exceeded")
            normalized = ""
            for page in pdf:
                normalized += " " + _clean_text(page.get_text("text"))
    except DegradedDocument:
        raise
    except Exception as exc:
        raise DegradedDocument(f"pdf_open_failed:{type(exc).__name__}") from exc
    if not (allow_oversized_chunk and page_count > MAX_FILE_PAGES):
        budget.add_pages(page_count)
    normalized_chars = len(_clean_text(normalized))
    if normalized_chars < MIN_NORMALIZED_TEXT_CHARS and not allow_image_only:
        raise DegradedDocument("unsupported_image_only")
    return page_count, normalized_chars


def fetch_verified_pdf(doc: VerifiedDocument, transport: Any, budget: RunBudget,
                       *, allow_image_only: bool = False,
                       allow_oversized_chunk: bool = False) -> FetchResult:
    url = doc.url
    response = None
    for hop in range(MAX_REDIRECTS + 1):
        try:
            response = transport.get(url, stream=True, allow_redirects=False, timeout=(10, 35))
        except Exception as exc:
            raise DegradedDocument(f"transport_error:{type(exc).__name__}") from exc
        location = _redirect_location(response)
        if location:
            if hop >= MAX_REDIRECTS:
                raise DegradedDocument("redirect_cap_exceeded")
            url = _validate_redirect_url(doc, url, location)
            continue
        break
    if response is None or _status(response) != 200:
        raise DegradedDocument(f"http_status_{_status(response) if response is not None else 0}")
    final_url = getattr(response, "url", None) or url
    try:
        _validated_dps_url(doc.doc_id, final_url)
    except UnsafeInput as exc:
        raise DegradedDocument("final_url_mismatch") from exc
    content_type = (_header(response, "Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise DegradedDocument("content_type_not_allowed")
    declared = _header(response, "Content-Length")
    if declared is not None:
        try:
            declared_length = int(declared)
        except ValueError as exc:
            raise DegradedDocument("invalid_content_length") from exc
        if declared_length > MAX_FILE_BYTES:
            raise DegradedDocument("declared_file_cap_exceeded")
        if budget.bytes + declared_length > MAX_RUN_BYTES:
            raise DegradedDocument("declared_run_cap_exceeded")
    body = bytearray()
    for chunk in _chunks(response):
        if not chunk:
            continue
        if len(body) + len(chunk) > MAX_FILE_BYTES:
            raise DegradedDocument("stream_file_cap_exceeded")
        budget.add_bytes(len(chunk))
        body.extend(chunk)
    raw = bytes(body)
    if not raw:
        raise DegradedDocument("empty_body")
    content_sha = hashlib.sha256(raw).hexdigest()
    if doc.content_sha256 and content_sha != doc.content_sha256:
        raise DegradedDocument("known_receipt_hash_mismatch")
    page_count, normalized_chars = _validate_pdf(
        raw, budget, allow_image_only=allow_image_only,
        allow_oversized_chunk=allow_oversized_chunk)
    return FetchResult(body=raw, content_sha256=content_sha, content_length=len(raw), final_url=final_url,
                       content_type=content_type, page_count=page_count, normalized_chars=normalized_chars)


def fetch_retained_original(doc: VerifiedDocument, root: Path, budget: RunBudget,
                            *, allow_image_only: bool = False,
                            allow_oversized_chunk: bool = False) -> FetchResult:
    """Load and re-verify the one explicitly retained original, if approved.

    This is intentionally an exact-ID lookup.  It does not search the cache,
    accept caller-provided paths, or permit a source without the pinned hash.
    """
    spec = RETAINED_ORIGINALS.get(doc.doc_id)
    if spec is None:
        raise DegradedDocument("retained_original_not_approved")
    if doc.url != spec["source_url"] or doc.content_sha256 != spec["content_sha256"]:
        raise DegradedDocument("retained_source_identity_mismatch")
    path = root / spec["relative_path"]
    try:
        stat = path.stat()
    except OSError as exc:
        raise DegradedDocument("retained_original_unavailable") from exc
    if not path.is_file():
        raise DegradedDocument("retained_original_unavailable")
    if stat.st_size > MAX_FILE_BYTES:
        raise DegradedDocument("retained_file_cap_exceeded")
    if budget.bytes + stat.st_size > MAX_RUN_BYTES:
        raise DegradedDocument("retained_run_cap_exceeded")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DegradedDocument("retained_original_unavailable") from exc
    if len(raw) != stat.st_size:
        raise DegradedDocument("retained_original_changed")
    content_sha = hashlib.sha256(raw).hexdigest()
    if content_sha != spec["content_sha256"]:
        raise DegradedDocument("retained_hash_mismatch")
    if not raw:
        raise DegradedDocument("empty_body")
    budget.add_bytes(len(raw))
    page_count, normalized_chars = _validate_pdf(
        raw, budget, allow_image_only=allow_image_only,
        allow_oversized_chunk=allow_oversized_chunk)
    if page_count != int(spec["page_count"]):
        raise DegradedDocument("retained_page_count_mismatch")
    return FetchResult(body=raw, content_sha256=content_sha, content_length=len(raw),
                       final_url=str(spec["source_url"]), content_type="application/pdf",
                       page_count=page_count, normalized_chars=normalized_chars)


def fetch_with_retained_fallback(doc: VerifiedDocument, transport: Any, budget: RunBudget,
                                 root: Path, *, allow_image_only: bool = False,
                                 allow_oversized_chunk: bool = False) -> FetchResult:
    """Fetch from PSX, falling back only when no network response exists."""
    try:
        return fetch_verified_pdf(doc, transport, budget,
                                  allow_image_only=allow_image_only,
                                  allow_oversized_chunk=allow_oversized_chunk)
    except DegradedDocument as exc:
        reason = str(exc)
        if not (reason.startswith("transport_error:") or reason == "http_status_0"):
            raise
        return fetch_retained_original(doc, root, budget,
                                       allow_image_only=allow_image_only,
                                       allow_oversized_chunk=allow_oversized_chunk)


def _load_receipts(path: Path) -> dict[str, Any]:
    payload = load_json(path, {"schema_version": 1, "receipts": []})
    receipts = payload.get("receipts") if isinstance(payload, dict) else []
    if not isinstance(receipts, list):
        receipts = []
    return {"schema_version": 1, "receipts": receipts}


def _receipt_revision(receipt: dict[str, Any]) -> str:
    revision = receipt.get("parser_revision")
    return str(revision or LEGACY_PARSER_REVISION)


def _receipt_key(receipt: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(receipt.get("doc_id") or ""),
        str(receipt.get("content_sha256") or ""),
        str(receipt.get("parser_version") or ""),
        _receipt_revision(receipt),
    )


def successful_receipt_exists(receipts: dict[str, Any], doc_id: str, content_sha256: str | None,
                              parser_version: str, parser_revision: str) -> bool:
    if not content_sha256:
        return False
    wanted = (doc_id, content_sha256, parser_version, parser_revision)
    return any(_receipt_key(row) == wanted and row.get("status") in PROCESSED_RECEIPT_STATUSES
               for row in receipts.get("receipts") or [] if isinstance(row, dict))


def latest_receipt_hash(receipts: dict[str, Any], doc_id: str, parser_version: str,
                        parser_revision: str) -> str | None:
    for row in reversed(receipts.get("receipts") or []):
        if not isinstance(row, dict):
            continue
        if (row.get("doc_id") == doc_id and row.get("parser_version") == parser_version
                and _receipt_revision(row) == parser_revision
                and row.get("status") in PROCESSED_RECEIPT_STATUSES):
            content_sha = row.get("content_sha256")
            if isinstance(content_sha, str) and re.fullmatch(r"[0-9a-f]{64}", content_sha):
                return content_sha
    return None


def append_receipt(path: Path, receipt: dict[str, Any]) -> None:
    payload = _load_receipts(path)
    receipts = list(payload["receipts"])
    key = _receipt_key(receipt)
    if any(_receipt_key(row) == key and row.get("status") == receipt.get("status")
           for row in receipts if isinstance(row, dict)):
        return
    receipts.append(receipt)
    save_json(path, {"schema_version": 1, "receipts": receipts, "updated": _utc_stamp()})


def _copy_if_exists(src: Path, dest: Path) -> None:
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _atomic_replace_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + f".reprocess.{secrets.token_hex(4)}.tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dest)


def _read_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _restore_snapshot(snapshot: dict[Path, bytes | None]) -> None:
    for path, data in snapshot.items():
        if data is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + f".restore.{secrets.token_hex(4)}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)


def _snapshot_paths(state_root: Path, ci_slice_path: Path = CI_SLICE_PATH) -> list[Path]:
    paths = [state_root / rel for rel in CANONICAL_RELATIVE_PATHS]
    ci_dir = state_root / "company_intel"
    if ci_dir.exists():
        paths.extend(
            path for path in sorted(ci_dir.glob("*.json"))
            if path.name not in CI_ARTIFACT_INTEGRITY_EXCLUDED_STATE_NAMES
        )
    paths.append(ci_slice_path)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        key = path.resolve()
        if key not in seen:
            deduped.append(path)
            seen.add(key)
    return deduped


def _copy_canonical_to_work(state_root: Path, work_state: Path) -> None:
    for rel in CANONICAL_RELATIVE_PATHS:
        _copy_if_exists(state_root / rel, work_state / rel)


def _verified_commits(state_root: Path, fetched_docs: list[tuple[VerifiedDocument, FetchResult]]) -> list[dict[str, str]]:
    docs = load_json(state_root / "company_documents.json", {"documents": {}}).get("documents") or {}
    series = load_json(state_root / "company_financial_series.json", {"tickers": {}}).get("tickers") or {}
    committed: list[dict[str, str]] = []
    for doc, fetched in fetched_docs:
        row = docs.get(doc.doc_id) if isinstance(docs, dict) else None
        if not isinstance(row, dict) or row.get("content_sha256") != fetched.content_sha256 or row.get("status") != "ready":
            continue
        has_v2 = False
        for ticker in doc.tickers:
            for fact in ((series.get(ticker) or {}).get("facts") or []):
                if (fact.get("document_id") == doc.doc_id
                        and fact.get("content_sha256") == fetched.content_sha256
                        and fact.get("parser_version") == PARSER_VERSION
                        and fact.get("parser_revision") == PARSER_REVISION):
                    has_v2 = True
                    break
            if has_v2:
                break
        committed.append({
            "doc_id": doc.doc_id,
            "content_sha256": fetched.content_sha256,
            "status": "success" if has_v2 else "processed_unsupported",
        })
    return committed


def _run_checker(script_name: str) -> None:
    env = None
    if script_name in {"check_ci_completion_matrix.py", "preflight.py"}:
        env = dict(os.environ)
        if script_name == "check_ci_completion_matrix.py":
            env["HENNETH_CI_PRODUCT_CONTRACTS_VERIFIED_BY_PREFLIGHT"] = "1"
        if script_name == "preflight.py":
            env["HENNETH_REPROCESS_TRANSACTION"] = "1"
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script_name)],
                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=120, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed: {result.stdout[-1000:]}")


def _validate_canonical_boundaries(state_root: Path, before_counts: dict[str, int],
                                   ci_slice_path: Path = CI_SLICE_PATH) -> None:
    profiles = load_json(state_root / "company_profiles.json", {})
    pilot = sorted((profiles.get("pilot") or {}).get("symbols") or [])
    if len(pilot) != 20:
        raise RuntimeError(f"company_profiles pilot count is {len(pilot)}, expected 20")
    model_inputs = load_json(state_root / "company_intel" / "financial_model_inputs.json", {})
    model_companies = model_inputs.get("companies") if isinstance(model_inputs, dict) else None
    if not isinstance(model_companies, dict) or sorted(model_companies) != pilot:
        raise RuntimeError("financial_model_inputs boundary does not match exact 20-company pilot")
    truth = load_json(state_root / "company_intel" / "financial_truth_qualification.json", {})
    truth_companies = truth.get("companies") if isinstance(truth, dict) else None
    if not isinstance(truth_companies, dict) or sorted(truth_companies) != pilot:
        raise RuntimeError("financial_truth_qualification boundary does not match exact 20-company pilot")
    for name in ("financial_forecasts", "formal_valuations", "market_expectations"):
        payload = load_json(state_root / "company_intel" / f"{name}.json", {})
        companies = payload.get("companies") if isinstance(payload, dict) else None
        if not isinstance(companies, dict) or sorted(companies) != pilot:
            raise RuntimeError(f"{name} boundary does not match exact 20-company pilot")
    series = load_json(state_root / "company_financial_series.json", {})
    series_tickers = series.get("tickers") if isinstance(series, dict) else None
    if not isinstance(series_tickers, dict) or len(series_tickers) < before_counts.get("series_tickers", 0):
        raise RuntimeError("company_financial_series ticker count regressed")
    docs = load_json(state_root / "company_documents.json", {})
    documents = docs.get("documents") if isinstance(docs, dict) else None
    if not isinstance(documents, dict) or len(documents) < before_counts.get("documents", 0):
        raise RuntimeError("company_documents count regressed")
    ci = load_json(ci_slice_path, {})
    rows = ci.get("tickers") if isinstance(ci, dict) else None
    ci_symbols = sorted(row.get("symbol") for row in rows if isinstance(row, dict)) if isinstance(rows, list) else []
    if ci_symbols != pilot:
        raise RuntimeError("company_intelligence slice boundary does not match exact 20-company pilot")


def _canonical_counts(state_root: Path) -> dict[str, int]:
    docs = load_json(state_root / "company_documents.json", {"documents": {}})
    series = load_json(state_root / "company_financial_series.json", {"tickers": {}})
    return {
        "documents": len((docs.get("documents") or {}) if isinstance(docs, dict) else {}),
        "series_tickers": len((series.get("tickers") or {}) if isinstance(series, dict) else {}),
    }


def _pending_document_diagnostics(
    pending_docs: list[tuple[VerifiedDocument, FetchResult]],
    chunk_records: dict[str, list[ChunkRecord]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc, fetched in pending_docs:
        chunks = (chunk_records or {}).get(doc.doc_id) or []
        row: dict[str, Any] = {
            "doc_id": doc.doc_id,
            "content_sha256": fetched.content_sha256,
            "page_count": fetched.page_count,
            "source_url": doc.url,
            "receipt": "not_written_transaction_failed",
        }
        if chunks:
            row["chunked_source"] = True
            row["chunk_ranges"] = [
                {
                    "source_page_start": chunk.source_page_start,
                    "source_page_end": chunk.source_page_end,
                    "page_count": chunk.page_count,
                    "chunk_sha256": chunk.chunk_sha256,
                }
                for chunk in chunks
            ]
        rows.append(row)
    return rows


def consume_canonical(registry_path: Path, queue_path: Path, output_root: Path,
                      fetched_docs: list[tuple[VerifiedDocument, FetchResult]],
                      *, state_root: Path = STATE,
                      ci_slice_path: Path = CI_SLICE_PATH,
                      model_builder: Callable[[], Any] | None = None,
                      reconciliation_builder: Callable[[], Any] | None = None,
                      truth_builder: Callable[[], Any] | None = None,
                      formal_builder: Callable[[], Any] | None = None,
                      evidence_watchlist_builder: Callable[[], Any] | None = None,
                      completion_matrix_builder: Callable[[], Any] | None = None,
                      ci_builder: Callable[[], Any] | None = None,
                      checker: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Consume scoped inputs through existing owners under one restoreable transaction."""

    from document_intelligence import run as run_document_intelligence
    from build_financial_model_inputs import build as build_model_inputs
    from build_financial_evidence_reconciliation import build as build_reconciliation
    from build_financial_truth_qualification import build as build_financial_truth
    from build_formal_financial_engines import build as build_formal_engines
    from build_evidence_watchlist import build as build_evidence_watchlist
    from build_company_brains import build as build_company_brains
    from build_thesis_monitoring import build as build_thesis_monitoring
    from build_intelligence_confidence import build as build_intelligence_confidence
    from build_guidance_contradictions import build as build_guidance_contradictions
    from build_management_delivery import build as build_management_delivery
    from build_signal_clusters import build as build_signal_clusters
    from build_ci_monitoring import build as build_ci_monitoring
    from build_ci_work_routing_policy import build as build_ci_work_routing_policy
    from build_ci_completion_matrix import build as build_ci_completion_matrix
    from build_ci_artifact_integrity import build as build_ci_artifact_integrity

    work_state = output_root / "canonical_state"
    if work_state.exists():
        safe_cleanup(work_state, output_root)
    work_state.mkdir(parents=True, exist_ok=True)
    _copy_canonical_to_work(state_root, work_state)
    stage = "document_intelligence"
    try:
        rc = run_document_intelligence(
            index_path=registry_path,
            output_path=work_state / "company_documents.json",
            extraction_queue_path=queue_path,
            ledger_path=work_state / "company_event_ledger.json",
            queue_path=work_state / "document_synthesis_queue.json",
            series_path=work_state / "company_financial_series.json",
        )
    except Exception as exc:
        raise ReprocessTransactionError(stage, str(exc), rolled_back=False) from exc
    if rc != 0:
        raise ReprocessTransactionError(stage, f"document_intelligence returned {rc}", rolled_back=False)
    stage = "verify_committed_documents"
    committed = _verified_commits(work_state, fetched_docs)
    expected = {doc.doc_id for doc, _ in fetched_docs}
    observed = {row["doc_id"] for row in committed}
    if observed != expected:
        missing = ",".join(sorted(expected - observed))
        raise ReprocessTransactionError(
            stage,
            f"canonical consume did not durably verify every requested document; missing={missing}",
            rolled_back=False,
        )
    snapshot = {path: _read_bytes(path) for path in _snapshot_paths(state_root, ci_slice_path)}
    before_counts = _canonical_counts(state_root)
    ci_builder_injected = ci_builder is not None
    model_builder = model_builder or build_model_inputs
    reconciliation_builder = reconciliation_builder or build_reconciliation
    truth_builder = truth_builder or build_financial_truth
    formal_builder = formal_builder or build_formal_engines
    evidence_watchlist_builder = evidence_watchlist_builder or (
        (lambda: None) if ci_builder_injected else build_evidence_watchlist
    )
    completion_matrix_builder = completion_matrix_builder or (
        (lambda: None) if ci_builder_injected else build_ci_completion_matrix
    )
    if ci_builder is None:
        from build_ci_slice import build as build_ci_slice
        ci_builder = build_ci_slice
    dependent_ci_builders = (
        () if ci_builder_injected else (
            build_signal_clusters,
            build_thesis_monitoring,
            build_intelligence_confidence,
            build_guidance_contradictions,
            build_management_delivery,
            build_company_brains,
        )
    )
    post_watchlist_builders = (
        () if ci_builder_injected else (
            build_ci_monitoring,
            build_ci_work_routing_policy,
        )
    )
    checker = checker or _run_checker
    try:
        for rel in (Path("company_documents.json"), Path("company_event_ledger.json"),
                    Path("document_synthesis_queue.json"), Path("company_financial_series.json")):
            stage = f"publish:{rel.as_posix()}"
            if (work_state / rel).exists():
                _atomic_replace_file(work_state / rel, state_root / rel)
        stage = "build_financial_model_inputs"
        model_builder()
        stage = "build_financial_evidence_reconciliation"
        reconciliation_builder()
        stage = "build_financial_truth_qualification"
        truth_builder()
        stage = "build_formal_financial_engines"
        formal_builder()
        for builder in dependent_ci_builders:
            stage = f"build:{getattr(builder, '__module__', 'unknown')}"
            builder()
        stage = "build_evidence_watchlist"
        evidence_watchlist_builder()
        for builder in post_watchlist_builders:
            stage = f"build:{getattr(builder, '__module__', 'unknown')}"
            builder()
        stage = "build_ci_completion_matrix"
        completion_matrix_builder()
        stage = "build_ci_slice"
        ci_builder()
        if not ci_builder_injected:
            stage = "build_ci_artifact_integrity"
            build_ci_artifact_integrity()
        stage = "validate_canonical_boundaries"
        _validate_canonical_boundaries(state_root, before_counts, ci_slice_path)
        for checker_name in (
            "check_financial_model_inputs.py",
            "check_financial_evidence_reconciliation.py",
            "check_financial_truth_qualification.py",
            "check_formal_financial_engines.py",
            "check_ci_completion_matrix.py",
            "check_event_studies.py",
            "check_operating_intelligence.py",
        ):
            stage = f"checker:{checker_name}"
            checker(checker_name)
        # Several legacy contract checks rebuild their authoritative inputs as
        # part of their idempotency proof.  Rebuild the dependent CI surface
        # once more after those checks, then run the aggregate gate against a
        # coherent final artifact set rather than a stale watchlist/slice.
        for builder in dependent_ci_builders:
            stage = f"rebuild:{getattr(builder, '__module__', 'unknown')}"
            builder()
        stage = "rebuild_evidence_watchlist"
        evidence_watchlist_builder()
        for builder in post_watchlist_builders:
            stage = f"rebuild:{getattr(builder, '__module__', 'unknown')}"
            builder()
        stage = "rebuild_ci_completion_matrix"
        completion_matrix_builder()
        stage = "rebuild_ci_slice"
        ci_builder()
        if not ci_builder_injected:
            stage = "rebuild_ci_artifact_integrity"
            build_ci_artifact_integrity()
        stage = "checker:preflight.py"
        checker("preflight.py")
    except Exception:
        exc = sys.exc_info()[1]
        _restore_snapshot(snapshot)
        if isinstance(exc, ReprocessTransactionError):
            raise
        raise ReprocessTransactionError(
            stage,
            str(exc),
            rolled_back=True,
            canonical_state_committed=False,
        ) from exc
    return {"status": "committed", "committed": [
        {"doc_id": row["doc_id"], "content_sha256": row["content_sha256"]}
        for row in committed if row["status"] == "success"
    ], "processed": committed}


def _safe_child(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    root = parent.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise UnsafeInput("path escape rejected")
    return resolved


def safe_cleanup(path: Path, allowed_parent: Path) -> None:
    resolved = _safe_child(path, allowed_parent)
    if resolved.exists():
        shutil.rmtree(resolved)


def _write_scoped_inputs(stage_dir: Path, raw_dir: Path, docs: list[tuple[VerifiedDocument, FetchResult]],
                         chunk_records: dict[str, list[ChunkRecord]] | None = None) -> tuple[Path, Path]:
    registry: dict[str, Any] = {"schema_version": 1, "documents": {}, "_meta": {
        "source": "reprocess_company_documents scoped exact-ID restage",
        "full_text_retained": False,
        "raw_bytes_retained": False,
    }}
    queue: list[dict[str, Any]] = []
    for doc, fetched in docs:
        filename = f"{doc.doc_id.replace(':', '_')}_{fetched.content_sha256[:16]}.pdf"
        raw_path = _safe_child(raw_dir / filename, raw_dir)
        raw_path.write_bytes(fetched.body)
        row = dict(doc.row)
        row.update({
            "doc_id": doc.doc_id,
            "id": doc.doc_id,
            "hash": doc.doc_id,
            "official_document_id": doc.numeric_id,
            "url": doc.url,
            "source_url": doc.url,
            "source": "PSX DPS",
            "source_type": "filing",
            "source_page": doc.row.get("source_page") or "https://dps.psx.com.pk/announcements/companies",
            "source_identity": {
                "provider": "PSX DPS",
                "official_document_id": doc.numeric_id,
                "url": doc.url,
            },
            "parser_version": PARSER_VERSION,
            "parser_revision": PARSER_REVISION,
            "tickers": doc.tickers,
            "expected_symbol": (doc.manifest or {}).get("symbol"),
            "expected_company_name": (doc.manifest or {}).get("company_name"),
            "expected_title_pattern": (doc.manifest or {}).get("expected_title_pattern"),
            "period": (doc.manifest or {}).get("period"),
            "period_end": (doc.manifest or {}).get("period"),
            "published_at": doc.row.get("published_at") or doc.row.get("date"),
            "retrieved_at": _utc_stamp(),
            "content_sha256": fetched.content_sha256,
            "content_length": fetched.content_length,
            "page_count": fetched.page_count,
            "mime_type": "application/pdf",
            "download": {"status": "verified", "checked_at": _utc_stamp(), "error": None},
        })
        chunks = (chunk_records or {}).get(doc.doc_id) or []
        if chunks:
            row["chunked_source"] = True
            row["source_page_count"] = sum(item.page_count for item in chunks)
            row["chunk_ranges"] = [
                {"source_page_start": item.source_page_start,
                 "source_page_end": item.source_page_end,
                 "page_count": item.page_count,
                 "chunk_sha256": item.chunk_sha256}
                for item in chunks
            ]
        registry["documents"][doc.doc_id] = row
        queue_row = {"doc_id": doc.doc_id, "path": str(raw_path), "content_sha256": fetched.content_sha256,
                     "parser_version": PARSER_VERSION, "parser_revision": PARSER_REVISION}
        if chunks:
            queue_row.update({
                "chunk_paths": [r.chunk_path for r in chunks],
                "chunk_page_offsets": [r.source_page_offset for r in chunks],
                "chunk_hashes": [r.chunk_sha256 for r in chunks],
                "source_page_count": sum(r.page_count for r in chunks),
                "source_document_id": doc.doc_id,
            })
        queue.append(queue_row)
    registry_path = stage_dir / "registry.json"
    queue_path = stage_dir / "queue.json"
    save_json(registry_path, registry)
    save_json(queue_path, {"schema_version": 1, "documents": queue})
    return registry_path, queue_path


def _diagnostic_page_records(fetched: FetchResult, *, max_pages: int = 25) -> list[dict[str, Any]]:
    import pymupdf

    doc = pymupdf.open(stream=fetched.body, filetype="pdf")
    try:
        records = []
        for index in range(min(len(doc), max_pages)):
            page = doc[index]
            records.append({
                "page": index + 1,
                "text": page.get_text("text") or "",
                "words": page.get_text("words") or [],
            })
        return records
    finally:
        doc.close()


def _diagnose_document(doc: VerifiedDocument, fetched: FetchResult) -> dict[str, Any]:
    parser_doc = {
        "doc_id": doc.doc_id,
        "title": doc.row.get("title") or doc.row.get("digest") or "",
        "source_url": doc.url,
        "content_sha256": fetched.content_sha256,
        "period_end": (doc.manifest or {}).get("period") or doc.row.get("period_end"),
        "published_at": doc.row.get("published_at") or doc.row.get("date"),
        "retrieved_at": doc.row.get("retrieved_at"),
    }
    summary = diagnose_page_records(parser_doc, _diagnostic_page_records(fetched))
    return {
        "doc_id": doc.doc_id,
        "status": "diagnosed",
        "content_sha256": fetched.content_sha256,
        "content_length": fetched.content_length,
        "page_count": fetched.page_count,
        "diagnostic": summary,
    }


def run_reprocess(
    document_ids: Iterable[str],
    *,
    root: Path = ROOT,
    state_root: Path = STATE,
    allowlist_manifest: Path | None = None,
    transport: Any | None = None,
    consume: bool = False,
    diagnose: bool = False,
    _consumer: Callable[[Path, Path, Path, list[tuple[VerifiedDocument, FetchResult]]], dict[str, Any]] | None = None,
    receipts_path: Path | None = None,
    expected_allowlist: frozenset[str] = APPROVED_WAVE3_ALLOWLIST,
    ci_slice_path: Path = CI_SLICE_PATH,
    _model_builder: Callable[[], Any] | None = None,
    _reconciliation_builder: Callable[[], Any] | None = None,
    _truth_builder: Callable[[], Any] | None = None,
    _formal_builder: Callable[[], Any] | None = None,
    _evidence_watchlist_builder: Callable[[], Any] | None = None,
    _completion_matrix_builder: Callable[[], Any] | None = None,
    _ci_builder: Callable[[], Any] | None = None,
    _checker: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if diagnose and (consume or _consumer is not None):
        raise UnsafeInput("diagnose mode cannot consume canonical state")
    ids = validate_operator_ids(document_ids)
    allowlist = load_allowlist(allowlist_manifest, expected_allowlist)
    docs = resolve_documents(ids, state_root, allowlist)
    receipts_file = receipts_path or (state_root / "company_intel" / "reprocess_receipts.json")
    receipts = _load_receipts(receipts_file)
    run_id = _run_id()
    raw_root = root / ".cache" / "company_intel" / "raw" / "reprocess"
    stage_root = root / ".cache" / "company_intel" / "reprocess"
    raw_dir = _safe_child(raw_root / run_id, raw_root)
    stage_dir = _safe_child(stage_root / run_id, stage_root)
    raw_dir.mkdir(parents=True, exist_ok=False)
    stage_dir.mkdir(parents=True, exist_ok=False)
    budget = RunBudget()
    transport = transport or RequestsTransport()
    results: list[dict[str, Any]] = []
    fetched_docs: list[tuple[VerifiedDocument, FetchResult]] = []
    pending_docs: list[tuple[VerifiedDocument, FetchResult]] = []
    chunk_records_by_doc: dict[str, list[ChunkRecord]] = {}
    try:
        for doc in docs:
            if diagnose:
                try:
                    fetched = fetch_with_retained_fallback(
                        doc, transport, budget, root,
                        allow_oversized_chunk=(doc.doc_id == "psx:260947"))
                    results.append(_diagnose_document(doc, fetched))
                except DegradedDocument as exc:
                    results.append({"doc_id": doc.doc_id, "status": "degraded", "reason": str(exc)})
                continue
            known_hash = doc.content_sha256 or latest_receipt_hash(receipts, doc.doc_id, PARSER_VERSION, PARSER_REVISION)
            if successful_receipt_exists(receipts, doc.doc_id, known_hash, PARSER_VERSION, PARSER_REVISION):
                results.append({"doc_id": doc.doc_id, "status": "skipped_idempotent"})
                continue
            try:
                oversized = doc.doc_id == "psx:260947"
                fetched = fetch_with_retained_fallback(
                    doc, transport, budget, root,
                    allow_oversized_chunk=oversized)
                fetched_docs.append((doc, fetched))
                if successful_receipt_exists(receipts, doc.doc_id, fetched.content_sha256, PARSER_VERSION, PARSER_REVISION):
                    results.append({"doc_id": doc.doc_id, "status": "skipped_idempotent_after_fetch",
                                    "content_sha256": fetched.content_sha256})
                else:
                    pending_docs.append((doc, fetched))
                    results.append({"doc_id": doc.doc_id, "status": "validated",
                                    "content_sha256": fetched.content_sha256})
                    if oversized and fetched.page_count > MAX_FILE_PAGES:
                        chunk_records_by_doc[doc.doc_id] = chunk_verified_oversized_pdf(
                            doc, fetched, raw_dir, expected_page_count=fetched.page_count)
                        results[-1].update({
                            "chunk_count": len(chunk_records_by_doc[doc.doc_id]),
                            "chunk_ranges": [[r.source_page_start, r.source_page_end]
                                             for r in chunk_records_by_doc[doc.doc_id]],
                        })
            except DegradedDocument as exc:
                results.append({"doc_id": doc.doc_id, "status": "degraded", "reason": str(exc)})
        if diagnose:
            return {
                "schema_version": 1,
                "run_id": run_id,
                "mode": "diagnose",
                "status": "degraded" if any(r["status"] == "degraded" for r in results) else "ok",
                "results": results,
                "bytes": budget.bytes,
                "pages": budget.pages,
                "parser_version": PARSER_VERSION,
                "parser_revision": PARSER_REVISION,
                "canonical_state_committed": False,
                "receipt_written": False,
            }
        if pending_docs:
            registry_path, queue_path = _write_scoped_inputs(
                stage_dir, raw_dir, pending_docs, chunk_records_by_doc)
            if _consumer is not None:
                consumer = _consumer
            elif consume:
                consumer = lambda a, b, c, d: consume_canonical(
                    a, b, c, d, state_root=state_root, ci_slice_path=ci_slice_path,
                    model_builder=_model_builder, reconciliation_builder=_reconciliation_builder,
                    truth_builder=_truth_builder, formal_builder=_formal_builder,
                    evidence_watchlist_builder=_evidence_watchlist_builder,
                    completion_matrix_builder=_completion_matrix_builder,
                    ci_builder=_ci_builder, checker=_checker)
            else:
                consumer = None
            if consumer is None:
                for row in results:
                    if row.get("status") == "validated":
                        row["status"] = "staged_validated"
                        row["receipt"] = "not_written_without_consumer_commit"
                return {
                    "schema_version": 1,
                    "run_id": run_id,
                    "status": "degraded" if any(r["status"] == "degraded" for r in results) else "staged",
                    "results": results,
                    "bytes": budget.bytes,
                    "pages": budget.pages,
                    "parser_version": PARSER_VERSION,
                    "parser_revision": PARSER_REVISION,
                    "limitation": "without a known retained source hash or prior receipt, content identity is only known after fetch; post-fetch duplicates skip extraction/state/receipt churn",
                }
            try:
                consumer_result = consumer(registry_path, queue_path, stage_dir, pending_docs)
            except ReprocessTransactionError as exc:
                raise ReprocessTransactionError(
                    exc.stage,
                    exc.reason,
                    rolled_back=exc.rolled_back,
                    canonical_state_committed=exc.canonical_state_committed,
                    documents=_pending_document_diagnostics(pending_docs, chunk_records_by_doc),
                ) from exc
            except Exception as exc:
                raise ReprocessTransactionError(
                    "consumer",
                    str(exc),
                    rolled_back=False,
                    canonical_state_committed=False,
                    documents=_pending_document_diagnostics(pending_docs, chunk_records_by_doc),
                ) from exc
            processed = (consumer_result.get("processed") if isinstance(consumer_result, dict) else []) or []
            processed_by_doc = {
                str(item.get("doc_id")): item for item in processed
                if isinstance(item, dict) and item.get("doc_id")
            }
            if not isinstance(consumer_result, dict) or consumer_result.get("status") != "committed":
                raise RuntimeError("restage consumer did not return a verifiable durable commit")
            for doc, fetched in pending_docs:
                processed_status = str((processed_by_doc.get(doc.doc_id) or {}).get("status") or "")
                receipt_status = "success" if processed_status == "success" else "processed_unsupported"
                append_receipt(receipts_file, {
                    "doc_id": doc.doc_id,
                    "content_sha256": fetched.content_sha256,
                    "parser_version": PARSER_VERSION,
                    "parser_revision": PARSER_REVISION,
                    "status": receipt_status,
                    "observed_at": _utc_stamp(),
                    "source": "PSX DPS",
                    "source_url": doc.url,
                    "official_document_id": doc.numeric_id,
                    "tickers": doc.tickers,
                    "content_length": fetched.content_length,
                    "page_count": fetched.page_count,
                    "content_type": fetched.content_type,
                    "transport": "exact_id_reprocess",
                    "chunked_source": bool(chunk_records_by_doc.get(doc.doc_id)),
                    "chunk_ranges": [
                        {"source_page_start": r.source_page_start,
                         "source_page_end": r.source_page_end,
                         "page_count": r.page_count,
                         "chunk_sha256": r.chunk_sha256}
                        for r in chunk_records_by_doc.get(doc.doc_id, [])
                    ],
                    "raw_retained": False,
                    "canonical_state_committed": True,
                })
            for row in results:
                if row.get("status") == "validated":
                    processed_status = str((processed_by_doc.get(str(row.get("doc_id"))) or {}).get("status") or "")
                    row["status"] = "committed" if processed_status == "success" else "processed_unsupported"
                    row["receipt"] = "success" if processed_status == "success" else "processed_unsupported"
        return {
            "schema_version": 1,
            "run_id": run_id,
            "status": "degraded" if any(r["status"] == "degraded" for r in results) else "ok",
            "results": results,
            "bytes": budget.bytes,
            "pages": budget.pages,
            "parser_version": PARSER_VERSION,
            "parser_revision": PARSER_REVISION,
        }
    finally:
        safe_cleanup(raw_dir, raw_root)
        safe_cleanup(stage_dir, stage_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-ID Wave 3 PSX company-document restage transport")
    parser.add_argument("--document-id", action="append", required=True,
                        help="Exact PSX DPS document id, repeated 1-5 times, e.g. psx:280589")
    parser.add_argument("--allowlist-manifest", type=Path,
                        help="Exact Wave 3 manifest containing document_ids; fail-closed if omitted and no built-in IDs exist")
    parser.add_argument("--consume", action="store_true",
                        help="After offline transport validation, consume through existing canonical owners and receipt only verified durable results")
    parser.add_argument("--diagnose", action="store_true",
                        help="Fetch through exact-ID gates and emit bounded parser diagnostics only; writes no receipts or canonical state")
    args = parser.parse_args(argv)
    try:
        result = run_reprocess(args.document_id, allowlist_manifest=args.allowlist_manifest,
                               consume=args.consume, diagnose=args.diagnose)
    except UnsafeInput as exc:
        print(f"reprocess_company_documents: unsafe input: {exc}", file=sys.stderr)
        return 2
    except ReprocessTransactionError as exc:
        print(json.dumps(exc.to_result(), indent=1, sort_keys=True))
        return 1
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
