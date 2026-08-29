#!/usr/bin/env python3
"""Focused deterministic checks for temporary oversized-filing chunking."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pymupdf

from pdf_chunking import (
    ChunkingError,
    SourceIdentity,
    build_page_ranges,
    map_evidence,
    split_pdf,
    temporary_chunks,
    verify_source_pdf,
)


def _fixture(path: Path, pages: int = 333) -> str:
    with pymupdf.open() as pdf:
        for number in range(1, pages + 1):
            page = pdf.new_page()
            page.insert_text((36, 48), f"DGKC fixture source page {number}")
        pdf.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="henneth-pdf-chunk-") as root:
        root_path = Path(root)
        source = root_path / "annual.pdf"
        source_hash = _fixture(source)
        identity = SourceIdentity(
            document_id="psx:260947",
            title="TRANSMISSION OF ANNUAL REPORT FOR THE YEAR ENDED JUNE 30, 2025",
            source_url="https://dps.psx.com.pk/download/document/260947.pdf",
            content_sha256=source_hash,
            published_at="2025-10-03T11:05:00+05:00",
            available_on="2025-10-03",
            page_count=333,
        )
        assert verify_source_pdf(source, identity) == identity
        ranges = build_page_ranges(333, preferred_ends=(111, 222, 333))
        assert ranges == [(1, 111), (112, 222), (223, 333)]
        assert all(end - start + 1 <= 120 for start, end in ranges)
        try:
            build_page_ranges(333, preferred_ends=(111, 222, 334))
        except ChunkingError:
            pass
        else:
            raise AssertionError("overlapping/gapped preferred ranges accepted")
        try:
            verify_source_pdf(source, SourceIdentity(**{**identity.__dict__, "page_count": 332}))
        except ChunkingError as exc:
            assert "page_count_mismatch" in str(exc)
        else:
            raise AssertionError("stale 332-page assertion accepted")
        output = root_path / "chunks"
        records = split_pdf(source, output, identity, ranges=ranges)
        assert [(r.source_page_start, r.source_page_end, r.page_count) for r in records] == [
            (1, 111, 111), (112, 222, 111), (223, 333, 111)
        ]
        assert all(Path(r.chunk_path).exists() and len(r.chunk_sha256) == 64 for r in records)
        mapped = map_evidence({"page": 2, "text": "fixture"}, records[1])
        assert mapped["page"] == 113
        assert mapped["document_id"] == identity.document_id
        assert mapped["content_sha256"] == identity.content_sha256
        # Temporary processing units are removed after verified consumption.
        temp_output = root_path / "temporary"
        with temporary_chunks(source, temp_output, identity, ranges=ranges) as temp_records:
            assert len(temp_records) == 3 and temp_output.exists()
        assert not temp_output.exists()

        # MLCF FY2025 is the sole four-unit 401-page transport exception.
        mlcf_source = root_path / "mlcf-annual.pdf"
        mlcf_hash = _fixture(mlcf_source, pages=401)
        mlcf_identity = SourceIdentity(
            document_id="psx:260032",
            title="MLCF Transmission of Annual Financial Statements for the Year Ended 30.06.2025",
            source_url="https://dps.psx.com.pk/download/document/260032.pdf",
            content_sha256=mlcf_hash,
            published_at="2025-09-25T12:43:00+05:00",
            available_on="2025-09-25",
            page_count=401,
        )
        mlcf_ranges = build_page_ranges(401, preferred_ends=(120, 240, 360, 401))
        assert mlcf_ranges == [(1, 120), (121, 240), (241, 360), (361, 401)]
        mlcf_chunks = split_pdf(mlcf_source, root_path / "mlcf-chunks", mlcf_identity,
                                ranges=mlcf_ranges)
        assert [(r.source_page_start, r.source_page_end, r.page_count) for r in mlcf_chunks] == [
            (1, 120, 120), (121, 240, 120), (241, 360, 120), (361, 401, 41)
        ]
        mapped_mlcf = map_evidence({"page": 41, "text": "fixture"}, mlcf_chunks[-1])
        assert mapped_mlcf["page"] == 401
        assert mapped_mlcf["document_id"] == "psx:260032"
        assert mapped_mlcf["source_url"] == mlcf_identity.source_url
        assert mapped_mlcf["content_sha256"] == mlcf_hash
    print("pdf_chunking self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
