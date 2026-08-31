#!/usr/bin/env python3
"""Bounded temporary PDF chunking for oversized retained PSX filings.

The source document remains the only evidence identity.  Chunks are parser
transport units and are never written to durable state or published.  Every
chunk carries the source document id/hash/url and an explicit one-based source
page range so facts can be mapped back to the original filing.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator, Sequence

import pymupdf


MAX_PARSER_PAGES = 120

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ChunkingError(ValueError):
    """The source or chunk set failed a fail-closed integrity invariant."""


@dataclass(frozen=True)
class SourceIdentity:
    document_id: str
    title: str
    source_url: str
    content_sha256: str
    published_at: str | None
    available_on: str | None
    page_count: int
    media_type: str = "application/pdf"


@dataclass(frozen=True)
class ChunkRecord:
    document_id: str
    source_title: str
    source_url: str
    source_content_sha256: str
    published_at: str | None
    available_on: str | None
    source_page_start: int
    source_page_end: int
    page_count: int
    chunk_path: str
    chunk_sha256: str
    media_type: str = "application/pdf"

    @property
    def source_page_offset(self) -> int:
        """Zero-based offset used to translate parser-local pages."""
        return self.source_page_start - 1


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise_hash(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise ChunkingError("source content_sha256 must be a 64-character hexadecimal hash")
    return text


def inspect_pdf(path: str | Path) -> tuple[int, str, str]:
    """Return (page_count, media_type, header) without changing the file."""
    source = Path(path)
    raw_head = source.read_bytes()[:8]
    if not raw_head.startswith(b"%PDF-"):
        raise ChunkingError("pdf_magic_mismatch")
    try:
        with pymupdf.open(source) as pdf:
            page_count = len(pdf)
            if page_count < 1:
                raise ChunkingError("empty_pdf")
    except ChunkingError:
        raise
    except Exception as exc:  # pragma: no cover - dependency-specific detail
        raise ChunkingError(f"pdf_open_failed:{type(exc).__name__}") from exc
    return page_count, "application/pdf", raw_head.decode("ascii", errors="replace")


def verify_source_pdf(path: str | Path, identity: SourceIdentity) -> SourceIdentity:
    """Verify exact retained source identity before any pages are split."""
    source = Path(path)
    if identity.media_type != "application/pdf":
        raise ChunkingError("source_media_type_not_pdf")
    expected_hash = _normalise_hash(identity.content_sha256)
    actual_hash = sha256_file(source)
    if actual_hash != expected_hash:
        raise ChunkingError("original_hash_mismatch")
    page_count, media_type, _ = inspect_pdf(source)
    if page_count != identity.page_count:
        raise ChunkingError(
            f"original_page_count_mismatch:expected={identity.page_count}:actual={page_count}"
        )
    if media_type != identity.media_type:
        raise ChunkingError("source_media_type_mismatch")
    if not identity.document_id.startswith("psx:"):
        raise ChunkingError("source_document_id_not_official_psx")
    if not identity.source_url.startswith("https://dps.psx.com.pk/download/document/"):
        raise ChunkingError("source_url_not_official_psx")
    return identity


def build_page_ranges(page_count: int, *, max_pages: int = MAX_PARSER_PAGES,
                      preferred_ends: Sequence[int] | None = None) -> list[tuple[int, int]]:
    """Build and validate contiguous one-based ranges under the parser cap."""
    if page_count < 1 or max_pages < 1:
        raise ChunkingError("invalid_page_range_parameters")
    ends = [int(v) for v in (preferred_ends or ())]
    if ends:
        if ends[-1] != page_count:
            raise ChunkingError("preferred_ranges_total_page_mismatch")
        starts: list[int] = []
        previous = 0
        for end in ends:
            if end <= previous or end - previous > max_pages:
                raise ChunkingError("preferred_ranges_overlap_gap_or_cap")
            starts.append(previous + 1)
            previous = end
        ranges = list(zip(starts, ends))
    else:
        ranges = []
        start = 1
        while start <= page_count:
            end = min(page_count, start + max_pages - 1)
            ranges.append((start, end))
            start = end + 1
    _assert_exact_ranges(ranges, page_count, max_pages=max_pages)
    return ranges


def _assert_exact_ranges(ranges: Sequence[tuple[int, int]], page_count: int,
                         *, max_pages: int = MAX_PARSER_PAGES) -> None:
    if not ranges or ranges[0][0] != 1 or ranges[-1][1] != page_count:
        raise ChunkingError("chunk_ranges_total_page_mismatch")
    previous_end = 0
    for start, end in ranges:
        if start != previous_end + 1:
            raise ChunkingError("chunk_ranges_overlap_or_gap")
        if end < start or end - start + 1 > max_pages:
            raise ChunkingError("chunk_range_exceeds_parser_cap")
        previous_end = end


def _chunk_filename(source: SourceIdentity, index: int, start: int, end: int) -> str:
    safe_id = source.document_id.replace(":", "_")
    return f"{safe_id}_chunk{index:02d}_pages{start:03d}-{end:03d}.pdf"


def split_pdf(path: str | Path, output_dir: str | Path, identity: SourceIdentity,
              *, ranges: Sequence[tuple[int, int]] | None = None) -> list[ChunkRecord]:
    """Verify and split a source PDF into temporary parser-sized PDFs."""
    source = Path(path)
    verify_source_pdf(source, identity)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    selected = list(ranges or build_page_ranges(
        identity.page_count, preferred_ends=(111, 222, identity.page_count)
        if identity.page_count == 333 else None,
    ))
    _assert_exact_ranges(selected, identity.page_count)
    records: list[ChunkRecord] = []
    try:
        with pymupdf.open(source) as original:
            if len(original) != identity.page_count:
                raise ChunkingError("original_page_count_changed_before_split")
            for index, (start, end) in enumerate(selected, 1):
                target = destination / _chunk_filename(identity, index, start, end)
                with pymupdf.open() as chunk:
                    chunk.insert_pdf(original, from_page=start - 1, to_page=end - 1)
                    chunk.save(target)
                observed_pages, media_type, _ = inspect_pdf(target)
                if observed_pages != end - start + 1:
                    raise ChunkingError("chunk_page_count_mismatch")
                records.append(ChunkRecord(
                    document_id=identity.document_id,
                    source_title=identity.title,
                    source_url=identity.source_url,
                    source_content_sha256=identity.content_sha256,
                    published_at=identity.published_at,
                    available_on=identity.available_on,
                    source_page_start=start,
                    source_page_end=end,
                    page_count=observed_pages,
                    chunk_path=str(target.resolve()),
                    chunk_sha256=sha256_file(target),
                    media_type=media_type,
                ))
        _assert_exact_ranges([(r.source_page_start, r.source_page_end) for r in records], identity.page_count)
        if sum(r.page_count for r in records) != identity.page_count:
            raise ChunkingError("chunk_page_total_mismatch")
        return records
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def map_parser_page(page: int, chunk: ChunkRecord) -> int:
    """Map a one-based parser-local page to its one-based source page."""
    local = int(page)
    if local < 1 or local > chunk.page_count:
        raise ChunkingError("parser_page_out_of_chunk_bounds")
    return chunk.source_page_offset + local


def map_evidence(evidence: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
    """Copy evidence and replace parser-local page with original page."""
    mapped = dict(evidence)
    if "page" in mapped:
        mapped["page"] = map_parser_page(int(mapped["page"]), chunk)
    mapped.update({
        "document_id": chunk.document_id,
        "source_url": chunk.source_url,
        "content_sha256": chunk.source_content_sha256,
        "source_page_start": chunk.source_page_start,
        "source_page_end": chunk.source_page_end,
    })
    return mapped


def receipt(identity: SourceIdentity, records: Sequence[ChunkRecord], *, status: str,
            cleanup_status: str = "pending") -> dict[str, Any]:
    """Build a bounded processing receipt; no PDF bytes or full text are retained."""
    _assert_exact_ranges([(r.source_page_start, r.source_page_end) for r in records], identity.page_count)
    return {
        "schema_version": 1,
        "status": status,
        "document_id": identity.document_id,
        "title": identity.title,
        "source_url": identity.source_url,
        "content_sha256": identity.content_sha256,
        "published_at": identity.published_at,
        "available_on": identity.available_on,
        "page_count": identity.page_count,
        "media_type": identity.media_type,
        "transport_units": [asdict(record) for record in records],
        "chunk_ranges_cover_source_once": True,
        "cleanup_status": cleanup_status,
        "raw_retained": False,
    }


@contextmanager
def temporary_chunks(path: str | Path, output_dir: str | Path, identity: SourceIdentity,
                     *, ranges: Sequence[tuple[int, int]] | None = None) -> Iterator[list[ChunkRecord]]:
    """Yield verified chunks and remove the temporary directory on exit."""
    records = split_pdf(path, output_dir, identity, ranges=ranges)
    try:
        yield records
    finally:
        root = Path(output_dir).resolve()
        if root.exists() and root.parent != root:
            shutil.rmtree(root)
