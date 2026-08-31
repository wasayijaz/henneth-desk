#!/usr/bin/env python3
"""Hash-bound OCR quarantine for image-only official PDFs.

This module is deliberately an evidence quarantine seam.  It may retain
machine-read text candidates for later deterministic review, but it never emits
canonical financial facts, parser receipts, financial-truth qualification,
forecasts, valuations, or market expectations.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from psx_data import save_json


OFFICIAL_URL_RE = re.compile(r"^https://dps\.psx\.com\.pk/download/document/(\d+)\.pdf$")
PSX_DOC_RE = re.compile(r"^psx:(\d+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MIN_OCR_CONFIDENCE = 0.80
QUARANTINE_SCHEMA_VERSION = 1
QUARANTINE_POLICY = {
    "audit_only": True,
    "quarantined": True,
    "does_not_emit_canonical_financial_facts": True,
    "does_not_create_parser_receipts": True,
    "does_not_promote_financial_truth": True,
    "does_not_activate_forecasts": True,
    "does_not_activate_valuations": True,
    "does_not_activate_market_expectations": True,
    "promotion_path": "separate deterministic statement/tie-out gate required",
}
FORBIDDEN_CANDIDATE_KEYS = {
    "fact_id",
    "metric",
    "line",
    "raw_value",
    "normalized_value",
    "value",
    "readiness",
    "eligibility_scope",
}
FORBIDDEN_STATUS_VALUES = {
    "ready",
    "success",
    "qualified",
    "model_loadable",
    "input_ready",
    "qualified_financial_truth",
}


class OcrQuarantineError(ValueError):
    """Source, engine, or candidate data failed the quarantine contract."""


class OcrEngine(Protocol):
    engine_name: str
    engine_version: str

    def recognize(self, pdf_path: Path, pages: list[int]) -> dict[str, Any]:
        """Return OCR results for one-based original pages."""


@dataclass(frozen=True)
class OcrSource:
    pdf_path: Path
    document_id: str
    source_url: str
    content_sha256: str
    pages: tuple[int, ...]
    title: str | None = None
    published_at: str | None = None
    official_source: str = "PSX DPS"


def _utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise OcrQuarantineError("ocr_confidence_missing_or_unknown")
    confidence = float(value)
    if confidence < MIN_OCR_CONFIDENCE or confidence > 1.0:
        raise OcrQuarantineError("ocr_confidence_out_of_range")
    return confidence


def _validate_official_source(source: OcrSource) -> None:
    doc_match = PSX_DOC_RE.fullmatch(str(source.document_id or ""))
    url_match = OFFICIAL_URL_RE.fullmatch(str(source.source_url or ""))
    if not doc_match or not url_match or doc_match.group(1) != url_match.group(1):
        raise OcrQuarantineError("official_source_mismatch")
    if source.official_source != "PSX DPS":
        raise OcrQuarantineError("official_source_missing")
    if not SHA256_RE.fullmatch(str(source.content_sha256 or "")):
        raise OcrQuarantineError("content_hash_missing_or_invalid")
    if source.pdf_path.suffix.lower() != ".pdf":
        raise OcrQuarantineError("non_pdf_rejected")
    if not source.pdf_path.is_file():
        raise OcrQuarantineError("pdf_unavailable")
    if not source.pages:
        raise OcrQuarantineError("pages_missing")
    if len(source.pages) != len(set(source.pages)) or any(not isinstance(page, int) or isinstance(page, bool) or page < 1 for page in source.pages):
        raise OcrQuarantineError("pages_invalid")


def _pdf_page_records(source: OcrSource) -> tuple[list[dict[str, Any]], int]:
    raw = source.pdf_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source.content_sha256:
        raise OcrQuarantineError("original_bytes_hash_mismatch")
    if not raw.startswith(b"%PDF-"):
        raise OcrQuarantineError("non_pdf_rejected")
    try:
        import pymupdf

        with pymupdf.open(source.pdf_path) as pdf:
            if pdf.is_encrypted:
                raise OcrQuarantineError("encrypted_pdf")
            page_count = len(pdf)
            if page_count < 1:
                raise OcrQuarantineError("empty_pdf")
            if any(page > page_count for page in source.pages):
                raise OcrQuarantineError("page_mismatch")
            records = []
            for page_number in source.pages:
                page = pdf[page_number - 1]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)
                records.append({
                    "page": page_number,
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                    "render_sha256": hashlib.sha256(pix.tobytes("png")).hexdigest(),
                    "render_width": int(pix.width),
                    "render_height": int(pix.height),
                })
            return records, page_count
    except OcrQuarantineError:
        raise
    except Exception as exc:
        raise OcrQuarantineError(f"pdf_open_failed:{type(exc).__name__}") from exc


def _bbox_ok(bbox: Any, width: float, height: float) -> list[float]:
    if (not isinstance(bbox, list) or len(bbox) != 4
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in bbox)):
        raise OcrQuarantineError("ocr_geometry_missing_or_invalid")
    x0, y0, x1, y1 = [float(value) for value in bbox]
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0 or x1 > width or y1 > height:
        raise OcrQuarantineError("ocr_geometry_out_of_bounds")
    return [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]


def _candidate_policy_ok(candidate: dict[str, Any]) -> None:
    if FORBIDDEN_CANDIDATE_KEYS.intersection(candidate):
        raise OcrQuarantineError("ocr_candidate_fact_like_keys_rejected")
    if str(candidate.get("status") or "").lower() in FORBIDDEN_STATUS_VALUES:
        raise OcrQuarantineError("ocr_candidate_promoting_status_rejected")


def _normalize_result_page(row: dict[str, Any], page_receipts: dict[int, dict[str, Any]]) -> dict[str, Any]:
    _candidate_policy_ok(row)
    page_number = row.get("page")
    if page_number not in page_receipts:
        raise OcrQuarantineError("ocr_page_mismatch")
    receipt = page_receipts[page_number]
    text = _clean(row.get("text"))
    if not text:
        raise OcrQuarantineError("ocr_text_missing")
    confidence = _valid_confidence(row.get("confidence"))
    bbox = _bbox_ok(row.get("bbox"), float(receipt["width"]), float(receipt["height"]))
    candidate = {
        "candidate_id": "ocr_" + hashlib.sha256(
            f"{page_number}\x1f{text}\x1f{bbox}".encode("utf-8")
        ).hexdigest()[:20],
        "page": page_number,
        "text": text,
        "confidence": confidence,
        "bbox": bbox,
        "status": "quarantined",
        "readiness_status": "audit_only",
        "promotion_status": "blocked_pending_deterministic_statement_tie_out",
    }
    _candidate_policy_ok(candidate)
    return candidate


def quarantine_pdf_pages(source: OcrSource, engine: OcrEngine, *, generated_at: str | None = None) -> dict[str, Any]:
    """Run OCR through an injected local engine and return an audit-only record."""
    _validate_official_source(source)
    page_receipts_list, page_count = _pdf_page_records(source)
    requested_pages = list(source.pages)
    result = engine.recognize(source.pdf_path, requested_pages)
    if not isinstance(result, dict):
        raise OcrQuarantineError("ocr_engine_result_invalid")
    engine_name = _clean(result.get("engine") or getattr(engine, "engine_name", ""))
    engine_version = _clean(result.get("engine_version") or getattr(engine, "engine_version", ""))
    if not engine_name or not engine_version:
        raise OcrQuarantineError("ocr_engine_identity_missing")
    result_pages = result.get("pages")
    if not isinstance(result_pages, list) or not result_pages:
        raise OcrQuarantineError("ocr_pages_missing")
    page_receipts = {row["page"]: row for row in page_receipts_list}
    candidates = [_normalize_result_page(row, page_receipts) for row in result_pages if isinstance(row, dict)]
    if len(candidates) != len(result_pages):
        raise OcrQuarantineError("ocr_page_shape_invalid")
    observed_pages = {row["page"] for row in candidates}
    if observed_pages != set(requested_pages):
        raise OcrQuarantineError("ocr_page_set_mismatch")
    if _sha256(source.pdf_path) != source.content_sha256:
        raise OcrQuarantineError("original_bytes_changed_during_ocr")
    return {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        "quarantine_revision": "ocr_quarantine_v1",
        "status": "quarantined",
        "audit_only": True,
        "generated_at": generated_at or _utc_stamp(),
        "source": {
            "document_id": source.document_id,
            "source": source.official_source,
            "source_url": source.source_url,
            "content_sha256": source.content_sha256,
            "title": source.title,
            "published_at": source.published_at,
            "page_count": page_count,
            "requested_pages": requested_pages,
        },
        "ocr_engine": {
            "name": engine_name,
            "version": engine_version,
        },
        "page_receipts": page_receipts_list,
        "candidates": candidates,
        "policy": dict(QUARANTINE_POLICY),
    }


def _record_key(record: dict[str, Any]) -> tuple[str, str, tuple[int, ...], str, str]:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    engine = record.get("ocr_engine") if isinstance(record.get("ocr_engine"), dict) else {}
    return (
        str(source.get("document_id") or ""),
        str(source.get("content_sha256") or ""),
        tuple(int(page) for page in (source.get("requested_pages") or [])),
        str(engine.get("name") or ""),
        str(engine.get("version") or ""),
    )


def append_quarantine_record(path: Path, record: dict[str, Any]) -> None:
    """Append one machine-read OCR record without touching canonical state."""
    if record.get("status") != "quarantined" or record.get("audit_only") is not True:
        raise OcrQuarantineError("only_quarantined_audit_records_can_be_appended")
    policy = record.get("policy") if isinstance(record.get("policy"), dict) else {}
    for key, expected in QUARANTINE_POLICY.items():
        if policy.get(key) != expected:
            raise OcrQuarantineError("quarantine_policy_invalid")
    candidates = record.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise OcrQuarantineError("quarantine_candidates_missing")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise OcrQuarantineError("quarantine_candidate_invalid")
        _candidate_policy_ok(candidate)
        if candidate.get("status") != "quarantined" or candidate.get("readiness_status") != "audit_only":
            raise OcrQuarantineError("quarantine_candidate_not_audit_only")
    payload: dict[str, Any] = {"schema_version": QUARANTINE_SCHEMA_VERSION, "records": []}
    if path.exists():
        import json

        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or not isinstance(loaded.get("records"), list):
            raise OcrQuarantineError("quarantine_ledger_invalid")
        payload = loaded
    records = [row for row in payload.get("records") or [] if isinstance(row, dict)]
    key = _record_key(record)
    if any(_record_key(row) == key for row in records):
        return
    records.append(record)
    save_json(path, {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        "append_only": True,
        "records": records,
        "updated": _utc_stamp(),
        "policy": dict(QUARANTINE_POLICY),
    })
