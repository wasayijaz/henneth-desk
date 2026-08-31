#!/usr/bin/env python3
"""Deterministic checks for OCR quarantine boundaries."""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from ocr_quarantine import OcrQuarantineError, OcrSource, append_quarantine_record, quarantine_pdf_pages


OFFICIAL = "https://dps.psx.com.pk/download/document/111.pdf"


class FakeOcrEngine:
    engine_name = "synthetic-fake-ocr"
    engine_version = "1.0"

    def __init__(self, pages: list[dict[str, Any]] | None = None, *, mutate: Path | None = None) -> None:
        self.pages = pages
        self.mutate = mutate

    def recognize(self, pdf_path: Path, pages: list[int]) -> dict[str, Any]:
        if self.mutate is not None:
            self.mutate.write_bytes(self.mutate.read_bytes() + b"\n% changed")
        return {
            "engine": self.engine_name,
            "engine_version": self.engine_version,
            "pages": self.pages if self.pages is not None else [
                {
                    "page": page,
                    "text": "Revenue 300 Profit after tax 45 EPS 3.0",
                    "confidence": 0.96,
                    "bbox": [72.0, 72.0, 260.0, 118.0],
                }
                for page in pages
            ],
        }


class MissingIdentityEngine(FakeOcrEngine):
    engine_name = ""
    engine_version = ""


def _write_pdf(path: Path, pages: int = 1) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    try:
        for _ in range(pages):
            page = doc.new_page(width=300, height=240)
            page.draw_rect((70, 70, 260, 120), color=(0, 0, 0), fill=(0.92, 0.92, 0.92))
        data = doc.tobytes()
    finally:
        doc.close()
    path.write_bytes(data)
    return data


def _source(pdf: Path, sha: str, *, pages: tuple[int, ...] = (1,), url: str = OFFICIAL,
            doc_id: str = "psx:111", official_source: str = "PSX DPS") -> OcrSource:
    return OcrSource(
        pdf_path=pdf,
        document_id=doc_id,
        source_url=url,
        content_sha256=sha,
        pages=pages,
        title="Synthetic Financial Results",
        published_at="2026-08-01T09:00:00+05:00",
        official_source=official_source,
    )


def _assert_rejects(name: str, source: OcrSource, engine: Any, reason: str) -> None:
    try:
        quarantine_pdf_pages(source, engine)
    except OcrQuarantineError as exc:
        if str(exc) != reason:
            raise AssertionError(f"{name}: expected {reason}, got {exc}") from exc
        return
    raise AssertionError(f"{name}: accepted unsafe OCR input")


def _assert_no_fact_like_payload(value: Any) -> None:
    forbidden_keys = {
        "fact_id",
        "metric",
        "line",
        "raw_value",
        "normalized_value",
        "value",
    }
    forbidden_values = {"model_loadable", "input_ready", "qualified_financial_truth", "success"}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in forbidden_keys:
                raise AssertionError(f"OCR quarantine emitted fact-like key {key}")
            _assert_no_fact_like_payload(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_fact_like_payload(item)
    elif isinstance(value, str) and value in forbidden_values:
        raise AssertionError(f"OCR quarantine emitted promoting value {value}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-ocr-quarantine-") as td:
        root = Path(td)
        pdf = root / "source.pdf"
        raw = _write_pdf(pdf, pages=2)
        sha = hashlib.sha256(raw).hexdigest()
        source = _source(pdf, sha, pages=(1, 2))
        record = quarantine_pdf_pages(source, FakeOcrEngine(), generated_at="2026-08-31T00:00:00Z")
        assert record["status"] == "quarantined"
        assert record["audit_only"] is True
        assert record["source"]["document_id"] == "psx:111"
        assert record["source"]["source_url"] == OFFICIAL
        assert record["source"]["content_sha256"] == sha
        assert record["source"]["requested_pages"] == [1, 2]
        assert record["ocr_engine"] == {"name": "synthetic-fake-ocr", "version": "1.0"}
        assert {row["page"] for row in record["page_receipts"]} == {1, 2}
        assert {row["page"] for row in record["candidates"]} == {1, 2}
        assert all(row["status"] == "quarantined" and row["readiness_status"] == "audit_only" for row in record["candidates"])
        for key in (
            "does_not_emit_canonical_financial_facts",
            "does_not_create_parser_receipts",
            "does_not_promote_financial_truth",
            "does_not_activate_forecasts",
            "does_not_activate_valuations",
            "does_not_activate_market_expectations",
        ):
            assert record["policy"][key] is True
        _assert_no_fact_like_payload(record)

        ledger = root / "state" / "company_intel" / "ocr_quarantine.json"
        append_quarantine_record(ledger, record)
        append_quarantine_record(ledger, record)
        ledger_payload = json.loads(ledger.read_text(encoding="utf-8"))
        assert ledger_payload["append_only"] is True
        assert len(ledger_payload["records"]) == 1
        assert not (root / "state" / "company_financial_series.json").exists()
        for name in ("financial_truth_qualification", "financial_forecasts", "formal_valuations", "market_expectations"):
            assert not (root / "state" / "company_intel" / f"{name}.json").exists()

        txt = root / "source.txt"
        txt.write_text("not a pdf", encoding="utf-8")
        _assert_rejects("non-pdf", _source(txt, hashlib.sha256(txt.read_bytes()).hexdigest()), FakeOcrEngine(), "non_pdf_rejected")
        _assert_rejects("missing hash", _source(pdf, ""), FakeOcrEngine(), "content_hash_missing_or_invalid")
        _assert_rejects("source URL", _source(pdf, sha, url="https://example.test/document/111.pdf"), FakeOcrEngine(), "official_source_mismatch")
        _assert_rejects("document URL mismatch", _source(pdf, sha, doc_id="psx:222"), FakeOcrEngine(), "official_source_mismatch")
        _assert_rejects("official source", _source(pdf, sha, official_source="Issuer site"), FakeOcrEngine(), "official_source_missing")
        _assert_rejects("pages missing", _source(pdf, sha, pages=()), FakeOcrEngine(), "pages_missing")
        _assert_rejects("page out of range", _source(pdf, sha, pages=(3,)), FakeOcrEngine(), "page_mismatch")
        _assert_rejects("hash drift", _source(pdf, "0" * 64), FakeOcrEngine(), "original_bytes_hash_mismatch")
        _assert_rejects("engine page mismatch", _source(pdf, sha, pages=(1, 2)), FakeOcrEngine([
            {"page": 1, "text": "Only one page", "confidence": 0.96, "bbox": [72, 72, 120, 90]},
        ]), "ocr_page_set_mismatch")
        _assert_rejects("low confidence", _source(pdf, sha), FakeOcrEngine([
            {"page": 1, "text": "Revenue 300", "confidence": 0.50, "bbox": [72, 72, 120, 90]},
        ]), "ocr_confidence_out_of_range")
        _assert_rejects("unknown confidence", _source(pdf, sha), FakeOcrEngine([
            {"page": 1, "text": "Revenue 300", "confidence": math.nan, "bbox": [72, 72, 120, 90]},
        ]), "ocr_confidence_missing_or_unknown")
        _assert_rejects("missing geometry", _source(pdf, sha), FakeOcrEngine([
            {"page": 1, "text": "Revenue 300", "confidence": 0.90},
        ]), "ocr_geometry_missing_or_invalid")
        _assert_rejects("geometry bounds", _source(pdf, sha), FakeOcrEngine([
            {"page": 1, "text": "Revenue 300", "confidence": 0.90, "bbox": [72, 72, 400, 90]},
        ]), "ocr_geometry_out_of_bounds")
        _assert_rejects("fact-like OCR", _source(pdf, sha), FakeOcrEngine([
            {"page": 1, "text": "Revenue 300", "confidence": 0.90, "bbox": [72, 72, 120, 90], "value": 300},
        ]), "ocr_candidate_fact_like_keys_rejected")

        forged = dict(record)
        forged["status"] = "success"
        try:
            append_quarantine_record(root / "forged.json", forged)
        except OcrQuarantineError as exc:
            assert str(exc) == "only_quarantined_audit_records_can_be_appended"
        else:
            raise AssertionError("append accepted promoting status")

        mutating = root / "mutating.pdf"
        mutating.write_bytes(raw)
        _assert_rejects("changed during OCR", _source(mutating, sha), FakeOcrEngine(mutate=mutating), "original_bytes_changed_during_ocr")
        _assert_rejects("engine identity", _source(pdf, sha), MissingIdentityEngine(), "ocr_engine_identity_missing")

    print("ocr_quarantine: PASS (hash-bound OCR retained as audit-only quarantine)")


if __name__ == "__main__":
    main()
