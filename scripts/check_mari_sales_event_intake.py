#!/usr/bin/env python3
"""Fail-closed contract check for the approved MARI material-event pair."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import document_intelligence
import reprocess_company_documents as reprocess
from psx_data import ROOT, load_json


MANIFEST = ROOT / "config" / "ci_mari_sales_event_intake_allowlist.json"


def _fail(message: str) -> None:
    raise AssertionError(message)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def main() -> int:
    payload = load_json(MANIFEST, {})
    expected = reprocess.MARI_SALES_EVENT_INTAKE_IDS
    if payload.get("kind") != "ci_mari_sales_event_intake_allowlist":
        _fail("MARI event intake manifest kind drifted")
    policy = payload.get("policy") or {}
    for key in ("owner_approved_exact_ids_only", "official_psx_dps_pdfs_only",
                "material_event_evidence_only", "transport_hash_required_before_receipt",
                "no_bulk_discovery", "no_new_provider", "no_ocr",
                "no_financial_truth_activation"):
        if policy.get(key) is not True:
            _fail(f"MARI event intake policy missing {key}=true")
    if payload.get("document_ids") != ["psx:280337", "psx:280161"]:
        _fail("MARI event intake document order or scope drifted")
    approved = reprocess.load_allowlist(MANIFEST, expected)
    if set(approved) != set(expected):
        _fail("MARI event intake allowlist does not resolve the exact approved pair")
    resolved = reprocess.resolve_documents(list(payload["document_ids"]), ROOT / "state", approved)
    if [doc.doc_id for doc in resolved] != list(payload["document_ids"]):
        _fail("MARI event intake rows no longer resolve exactly from retained metadata")
    for doc in resolved:
        if doc.content_sha256 is not None:
            _fail(f"{doc.doc_id}: first-seen material-event content must bind at transport, not config")
        if (doc.manifest or {}).get("classification") != "material_information":
            _fail(f"{doc.doc_id}: material-event classification missing")
    if not reprocess.MARI_SALES_EVENT_INTAKE_IDS.isdisjoint(reprocess.APPROVED_WAVE3_ALLOWLIST):
        _fail("material-event pair leaked into the financial restage allowlist")
    with tempfile.TemporaryDirectory(prefix="henneth-mari-event-") as tmp:
        bad = copy.deepcopy(payload)
        bad["documents"]["psx:280337"]["expected_title"] = "Different title"
        bad_path = Path(tmp) / "bad.json"
        _write(bad_path, bad)
        try:
            reprocess.load_allowlist(bad_path, expected)
        except reprocess.UnsafeInput:
            pass
        else:
            _fail("event manifest with a changed title was accepted")
        bad = copy.deepcopy(payload)
        bad["documents"]["psx:280161"]["source_url"] = "https://dps.psx.com.pk/download/document/280337.pdf"
        _write(bad_path, bad)
        try:
            reprocess.load_allowlist(bad_path, expected)
        except reprocess.UnsafeInput:
            pass
        else:
            _fail("event manifest with a mismatched DPS URL was accepted")
        row = copy.deepcopy((load_json(ROOT / "state" / "research_index.json", {}).get("documents") or {})["psx:280337"])
        row["content_sha256"] = "a" * 64
        try:
            reprocess._validate_row("psx:280337", row, "psx:280337", {"MARI"}, approved)
        except reprocess.UnsafeInput:
            pass
        else:
            _fail("event intake accepted a mutable research-index content hash")
        _assert_material_event_intake_never_writes_financial_facts(Path(tmp))
    print("mari_sales_event_intake: PASS (2 exact source-bound event leads)")
    return 0


def _assert_material_event_intake_never_writes_financial_facts(root: Path) -> None:
    """Exercise the extraction seam with financial-looking event text."""
    import pymupdf

    raw = root / ".cache" / "company_intel" / "raw" / "event.pdf"
    raw.parent.mkdir(parents=True)
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Mari entered into an agreement. Revenue of Rs 999 million.")
    raw.write_bytes(pdf.tobytes())
    pdf.close()
    payload = {
        "documents": {
            "psx:280337": {
                "id": "psx:280337", "official_document_id": "280337",
                "source": "PSX DPS", "source_type": "filing", "doc_type": "company_announcement",
                "title": "Launch of Pakistan First and Largest Purpose-Built AI Ready Data Centre Campus",
                "published_at": "2026-07-24T16:26:00+05:00", "date": "2026-07-24",
                "tickers": ["MARI"], "url": "https://dps.psx.com.pk/download/document/280337.pdf",
                "content_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                "classification": "material_information", "local_path": str(raw),
            }
        }
    }
    state = root / "state"
    _write(state / "research_index.json", payload)
    _write(state / "company_intel" / "source_registry.json", {"tickers": {"MARI": {}}})
    previous_root = document_intelligence.ROOT
    try:
        document_intelligence.ROOT = root
        rc = document_intelligence.run(
            index_path=state / "research_index.json", output_path=state / "company_documents.json",
            extraction_queue_path=root / "queue-input.json", ledger_path=state / "company_event_ledger.json",
            queue_path=state / "document_synthesis_queue.json", series_path=state / "company_financial_series.json",
        )
    finally:
        document_intelligence.ROOT = previous_root
    if rc != 0:
        _fail("material-event fixture could not pass document intelligence")
    record = (load_json(state / "company_documents.json", {}).get("documents") or {}).get("psx:280337") or {}
    if record.get("facts") or record.get("classification") != "material_information":
        _fail("material-event fixture emitted financial facts or lost its classification")
    series = load_json(state / "company_financial_series.json", {}).get("tickers") or {}
    if any((row.get("document_id") == "psx:280337") for value in series.values() if isinstance(value, dict) for row in (value.get("facts") or [])):
        _fail("material-event fixture leaked a financial-series fact")


if __name__ == "__main__":
    raise SystemExit(main())
