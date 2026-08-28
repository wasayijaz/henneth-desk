#!/usr/bin/env python3
"""Local document extraction primitives used by the deterministic intelligence pass.

The caller supplies a local path or inline text.  PDFs are read with PyMuPDF (the
only PDF dependency in this desk); no network or model call happens here.  Full
text is returned to the caller for one-pass parsing and is deliberately not a
state output.  Page numbers are one-based, and text documents use form-feed
boundaries when they have no native pages.
"""
from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from typing import Any


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def canonical_source(value: str | None) -> str:
    """Return a stable source key (URL/source id/path), without retrieval time."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    return _WS_RE.sub(" ", raw).rstrip("/")


def stable_doc_id(source_url: str | None = None, source_id: str | None = None,
                  path: str | None = None) -> str:
    source = canonical_source(source_id or source_url or path)
    if not source:
        raise ValueError("document needs source_id, source_url, or path")
    return "doc_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]


def _normalise(text: str) -> str:
    text = html.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def extract_local(path: str | Path) -> dict[str, Any]:
    """Extract a local PDF/text file.  Returns full text only for transient parsing."""
    p = Path(path)
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        import pymupdf  # already pinned by requirements.txt
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            pages = [_normalise(page.get_text("text")) for page in pdf]
            # Transient layout only: callers may use words to align table rows/columns;
            # this is never persisted in state.
            words = [[tuple(w[:8]) for w in page.get_text("words")] for page in pdf]
            page_records = [{"page": i + 1, "text": pages[i], "words": words[i], "width": float(page.rect.width), "height": float(page.rect.height)} for i, page in enumerate(pdf)]
        media = "application/pdf"
    else:
        words = []
        text = raw.decode("utf-8", errors="replace")
        pages = [_normalise(part) for part in text.split("\f")]
        media = {
            ".html": "text/html", ".htm": "text/html", ".md": "text/markdown",
            ".csv": "text/csv", ".json": "application/json",
        }.get(suffix, "text/plain")
    return {"text": "\n".join(pages), "pages": pages, "page_records": (page_records if suffix == ".pdf" else [{"page": i+1, "text": p, "words": []} for i,p in enumerate(pages)]), "words": words if suffix == ".pdf" else [], "content_sha256": sha,
            "media_type": media, "path": str(p)}


def extract_chunked_local(paths: list[str | Path], page_offsets: list[int] | None = None,
                          chunk_hashes: list[str] | None = None) -> dict[str, Any]:
    """Extract parser-sized PDFs as one transient source with original pages.

    ``page_offsets`` is zero-based and maps each chunk's local page one-to-one
    to the original source page.  The chunks must already have been verified by
    the bounded chunk transport; this helper does not create durable artifacts.
    """
    if not paths:
        raise ValueError("chunked document needs at least one path")
    offsets = list(page_offsets or [0] * len(paths))
    if len(offsets) != len(paths) or any(int(v) < 0 for v in offsets):
        raise ValueError("chunk page offsets must align with paths")
    hashes = list(chunk_hashes or [])
    if hashes and len(hashes) != len(paths):
        raise ValueError("chunk hashes must align with paths")
    pages: list[str] = []
    words: list[list[tuple]] = []
    page_records: list[dict[str, Any]] = []
    for chunk_index, (path, offset) in enumerate(zip(paths, offsets)):
        extracted = extract_local(path)
        if extracted.get("media_type") != "application/pdf":
            raise ValueError("chunked extraction accepts PDF paths only")
        if hashes:
            if extracted["content_sha256"] != str(hashes[chunk_index]).lower():
                raise ValueError("chunk content hash mismatch")
        for local, (text, page_words) in enumerate(zip(extracted["pages"], extracted["words"]), 1):
            original = int(offset) + local
            pages.append(text)
            words.append(page_words)
            page_records.append({
                "page": original,
                "text": text,
                "words": page_words,
                "width": 0.0,
                "height": 0.0,
            })
    raw_hash = hashlib.sha256("|".join(str(Path(p).resolve()) for p in paths).encode("utf-8")).hexdigest()
    return {"text": "\n".join(pages), "pages": pages, "page_records": page_records,
            "words": words, "content_sha256": raw_hash, "media_type": "application/pdf",
            "path": None}


def extract_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract an inbox entry from ``path``/``local_path`` or inline ``text``."""
    path = entry.get("local_path") or entry.get("path")
    if path:
        return extract_local(path)
    text = entry.get("text")
    if text is None:
        raise ValueError("document needs local_path/path or text")
    text = str(text)
    raw = text.encode("utf-8")
    pages = [_normalise(part) for part in text.split("\f")]
    return {"text": "\n".join(pages), "pages": pages, "page_records": [{"page": i+1, "text": p, "words": []} for i,p in enumerate(pages)],
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "media_type": entry.get("media_type") or "text/plain", "path": None}


def evidence_for(term: str, pages: list[str], limit: int = 240) -> dict[str, Any] | None:
    """Return one exact, bounded evidence excerpt for a regex term."""
    pattern = re.compile(term, re.I)
    for number, page in enumerate(pages, 1):
        match = pattern.search(page)
        if not match:
            continue
        start = max(0, match.start() - 90)
        end = min(len(page), match.end() + 150)
        excerpt = page[start:end].strip()
        if len(excerpt) > limit:
            excerpt = excerpt[: limit - 1].rstrip() + "…"
        return {"page": number, "text": excerpt}
    return None
