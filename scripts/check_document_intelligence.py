#!/usr/bin/env python3
"""Small offline self-check for document intelligence contracts."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from document_events import event_is_supported, extract_events
from document_extract import extract_entry, stable_doc_id
from document_ledger import append_events
from document_queue import build_queue
from document_intelligence import run as run_intelligence
from psx_data import STATE, load_json


def _validate_state() -> None:
    docs_path = STATE / "company_documents.json"
    if docs_path.exists():
        docs = load_json(docs_path, {}).get("documents") or {}
        for doc_id, doc in docs.items():
            if doc.get("status") != "ready":
                continue
            assert doc.get("source_url") and doc.get("content_sha256"), f"ready doc provenance: {doc_id}"
            for item in (doc.get("events") or []) + (doc.get("facts") or []):
                assert item.get("evidence"), f"missing evidence: {item.get('event_id') or item.get('fact_id')}"
                for evidence in item["evidence"]:
                    assert isinstance(evidence.get("page"), int) and evidence["page"] >= 1
                    assert evidence.get("text") and len(evidence["text"]) <= 240
                    assert evidence.get("source_url") == doc.get("source_url")
    ledger_path = STATE / "company_event_ledger.json"
    if ledger_path.exists():
        ledger = load_json(ledger_path, {}).get("companies") or {}
        for row in ledger.values():
            event_ids = [e.get("event_id") for e in (row.get("events") or [])]
            change_ids = [c.get("change_id") for c in (row.get("changes") or [])]
            assert len(event_ids) == len(set(event_ids))
            assert len(change_ids) == len(set(change_ids))
    queue_path = STATE / "document_synthesis_queue.json"
    if queue_path.exists():
        queue = load_json(queue_path, {})
        rows = queue.get("queue") or []
        assert queue.get("_meta", {}).get("training_mode") is True
        assert len({(r.get("doc_id"), r.get("content_sha256")) for r in rows}) == len(rows)
        assert all(r.get("approval_status") == "pending" for r in rows)


def main() -> int:
    live_series_path = STATE / "company_financial_series.json"
    live_series_before = live_series_path.read_bytes() if live_series_path.exists() else None
    with tempfile.TemporaryDirectory(prefix="henneth-doc-") as tmp:
        root = Path(tmp)
        text = "FFC quarterly results. EPS Rs 12.5; final dividend Rs 3. Revenue Rs 12 bn."
        extracted = extract_entry({"text": text, "media_type": "text/plain"})
        noisy = extract_entry({"text": "UBL results. Revenue Rs .; profit Rs ,.", "media_type": "text/plain"})
        noisy_kind, noisy_events, noisy_facts = extract_events(
            "doc_noisy", "UBL results", noisy["text"], noisy["pages"], ["UBL"])
        assert noisy_kind == "results" and isinstance(noisy_facts, list)
        routine = extract_entry({"text": (
            "Board of Directors Mr A, Chief Executive Mr B. Unclaimed dividend 26,721. "
            "Contract liabilities 788,499. The filing was submitted to SECP."
        ), "media_type": "text/plain"})
        _, routine_events, _ = extract_events(
            "doc_routine", "Company information", routine["text"], routine["pages"], ["ABC"])
        assert not routine_events, "routine filing language became a material event"
        assert not event_is_supported({"event_type": "dividend", "evidence": [{"text": "Unclaimed dividend 26,721"}]})
        assert not event_is_supported({"event_type": "management_change", "evidence": [{"text": "Chief Executive Mr B"}]})
        assert event_is_supported({"event_type": "management_change", "evidence": [{"text": "Mr B appointed as Chief Executive"}]})
        import pymupdf
        pdf = pymupdf.open()
        pdf.new_page()  # blank page keeps page-number provenance honest
        page = pdf.new_page()
        page.insert_text((72, 72), text)
        pdf_path = root / "fixture.pdf"
        pdf_path.write_bytes(pdf.tobytes())
        pdf.close()
        pdf_extracted = extract_entry({"path": str(pdf_path)})
        assert pdf_extracted["media_type"] == "application/pdf" and len(pdf_extracted["pages"]) == 2
        doc_id = stable_doc_id(source_url="https://example.test/ffc/1")
        kind, events, facts = extract_events(doc_id, "FFC results", extracted["text"], extracted["pages"],
                                             ["FFC"], "https://example.test/ffc/1", "2026-08-18",
                                             extracted["content_sha256"])
        assert kind == "results" and events and facts
        assert all((e["evidence"][0]["page"] or 0) >= 1 for e in events + facts)
        rev = next(f for f in facts if f["fact_type"] == "revenue")
        assert rev["raw_value"].endswith("bn") and rev["scale_multiplier"] == 1_000_000_000
        ledger = root / "ledger.json"
        append_events(events, ledger)
        first = ledger.read_text(encoding="utf-8")
        append_events(events, ledger)
        assert ledger.read_text(encoding="utf-8") == first, "ledger churned on a no-op"
        append_events([], ledger, changes=[{"change_id": "chg_fixture", "doc_id": doc_id,
                                           "tickers": ["FFC"], "fact_delta": {"added": facts[:1]}}])
        ledger_payload = json.loads(ledger.read_text(encoding="utf-8"))
        assert ledger_payload["companies"]["FFC"]["changes"][0]["fact_delta"]["added"]
        docs = {doc_id: {"status": "ready", "content_sha256": extracted["content_sha256"],
                         "tickers": ["FFC"], "doc_type": kind,
                         "events": events,
                         "brief_evidence": [{"page": 9, "text": "retained citation",
                                             "content_sha256": extracted["content_sha256"]}]}}
        queue = root / "queue.json"
        build_queue(docs, queue)
        first_queue = queue.read_text(encoding="utf-8")
        build_queue(docs, queue)
        assert queue.read_text(encoding="utf-8") == first_queue, "queue churned on a no-op"
        payload = json.loads(first_queue)
        assert payload["_meta"]["training_mode"] is True and payload["queue"][0]["approval_status"] == "pending"
        receipts = root / "brief_receipts.json"
        receipts.write_text(json.dumps({"receipts": [{"based_on": [
            {"doc_id": doc_id, "content_sha256": extracted["content_sha256"]}
        ]}]}), encoding="utf-8")
        build_queue(docs, queue, receipts)
        assert not json.loads(queue.read_text(encoding="utf-8"))["queue"], "approved receipt stayed active"

        # Simulate a crash after the durable document receipt but before ledger/queue writes.
        # The next metadata-only run must replay both outputs without needing raw bytes again.
        index = root / "research_index.json"
        output = root / "company_documents.json"
        recovered_ledger = root / "recovered_ledger.json"
        recovered_queue = root / "recovered_queue.json"
        recovered_series = root / "recovered_series.json"
        extraction_queue = root / "missing_extraction_queue.json"
        base_row = {"doc_id": doc_id, "official_document_id": "fixture",
                    "tickers": ["FFC"], "title": "FFC quarterly results",
                    "published_at": "2026-08-18", "url": "https://example.test/ffc/fixture.pdf",
                    "text": text, "media_type": "text/plain"}
        output.write_text(json.dumps({"schema_version": 1, "documents": docs}), encoding="utf-8")
        index.write_text(json.dumps({"documents": {doc_id: base_row}}), encoding="utf-8")
        run_intelligence(index, output, extraction_queue, recovered_ledger, recovered_queue, recovered_series)
        retained_doc = json.loads(output.read_text(encoding="utf-8"))["documents"][doc_id]
        assert retained_doc["brief_evidence"][0]["page"] == 9, "approved citation evidence was compacted away"
        recovered_ledger.unlink()
        recovered_queue.unlink()
        base_row.pop("text")
        index.write_text(json.dumps({"documents": {doc_id: base_row}}), encoding="utf-8")
        run_intelligence(index, output, extraction_queue, recovered_ledger, recovered_queue, recovered_series)
        recovered = json.loads(recovered_ledger.read_text(encoding="utf-8"))
        assert recovered["companies"]["FFC"]["events"], "ledger was not recovered from durable document"
        recovered_q = json.loads(recovered_queue.read_text(encoding="utf-8"))
        assert recovered_q["queue"], "queue was not recovered from durable document"

        # A verified-capital-note extraction is durable review evidence only.
        # It must retain the source binding and tie-out, but never become an
        # approved assumption or activate a financial engine as a side effect.
        capital_index = root / "capital_research_index.json"
        capital_output = root / "capital_company_documents.json"
        capital_candidates = root / "company_intel" / "official_share_capital_candidates.json"
        capital_text = (
            "2025 2024 Note (Rupees in thousand) Issued, subscribed and paid-up share capital "
            "1,047,562,608 ordinary shares of Rs 10 each 5 10,475,626 10,475,626"
        )
        capital_index.write_text(json.dumps({"documents": {"psx:999999": {
            "doc_id": "psx:999999", "official_document_id": "999999", "tickers": ["MLCF"],
            "title": "MLCF Annual Report", "period_end": "2025-06-30",
            "published_at": "2025-09-25", "url": "https://dps.psx.com.pk/download/document/999999.pdf",
            "text": capital_text, "media_type": "text/plain",
        }}}), encoding="utf-8")
        run_intelligence(
            capital_index, capital_output, extraction_queue, root / "capital_ledger.json",
            root / "capital_queue.json", root / "capital_series.json", capital_candidates,
        )
        capital_state = json.loads(capital_candidates.read_text(encoding="utf-8"))
        assert capital_state["policy"]["candidate_only"] is True
        assert capital_state["policy"]["does_not_activate_financial_truth"] is True
        candidate = capital_state["candidates"]
        assert len(candidate) == 1 and candidate[0]["symbol"] == "MLCF"
        assert candidate[0]["approved"] is False and candidate[0]["readiness"] == "candidate_only"
        assert candidate[0]["source"]["id"] == "psx:999999" and candidate[0]["source"]["page"] == 1
    live_series_after = live_series_path.read_bytes() if live_series_path.exists() else None
    assert live_series_after == live_series_before, "offline self-check touched live financial series"
    _validate_state()
    print("document intelligence self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
