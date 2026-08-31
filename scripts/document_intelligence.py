#!/usr/bin/env python3
"""Run the local, deterministic company-document intelligence pass.

Input is the existing ``state/research_index.json`` document registry.  Terra's
ingestion layer may attach a transient ``download.local_path``/``download.path``
or inline ``text`` to verified rows.  This pass never fetches a URL.  It writes
bounded metadata/evidence, appends events, and prepares a training-mode queue.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from document_events import extract_events
from document_extract import extract_entry, extract_chunked_local, stable_doc_id
from document_ledger import OUT as LEDGER_OUT, append_events
from document_queue import OUT as QUEUE_OUT, build_queue
from financial_series import normalize_fact
from financial_statement_facts import _available_on, extract_facts
from build_financial_series import OUT as SERIES_OUT, merge_rows
from psx_data import ROOT, STATE, load_json, save_json
from share_capital import extract_share_capital_evidence

OUT = STATE / "company_documents.json"
SHARE_CAPITAL_CANDIDATES_OUT = STATE / "company_intel" / "official_share_capital_candidates.json"
MAX_EVIDENCE = 8
MAX_BRIEF_EVIDENCE = 32
MAX_VERSIONS = 5


def _doc_rows(payload: Any) -> dict[str, dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("documents"), dict):
        return payload["documents"]
    if isinstance(payload, list):
        return {str(i): row for i, row in enumerate(payload) if isinstance(row, dict)}
    return {}


def _path_for(entry: dict[str, Any]) -> str | None:
    download = entry.get("download") if isinstance(entry.get("download"), dict) else {}
    return (entry.get("local_path") or entry.get("path") or download.get("local_path")
            or download.get("path") or download.get("file"))


def _ticks(entry: dict[str, Any]) -> list[str]:
    values = entry.get("tickers") or entry.get("symbols") or entry.get("symbol") or []
    if isinstance(values, str):
        values = [values]
    return sorted({str(v).strip().upper() for v in values if str(v).strip()})


def _source(entry: dict[str, Any], key: str) -> str | None:
    return entry.get(key) or entry.get("source_url") or entry.get("url") or None


def _load_registry(path: Path) -> dict[str, Any]:
    return load_json(path, {"schema_version": 1, "documents": {}, "_meta": {}})


def _doc_id(entry: dict[str, Any], key: str, url: str | None, local_path: str | None) -> str:
    source_id = entry.get("official_document_id") or entry.get("id") or key
    return str(entry.get("doc_id") or ("psx:" + str(source_id)
               if str(source_id).isdigit() else stable_doc_id(url, str(source_id), local_path)))


def _safe_path(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path).resolve()
    raw_root = (ROOT / ".cache" / "company_intel" / "raw").resolve()
    if not candidate.is_relative_to(raw_root):
        raise ValueError("local document path is outside Terra's transient raw cache")
    return str(candidate)


def _fact_delta(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bounded deterministic fact diff for the append-only change ledger."""
    def key(f: dict[str, Any]) -> tuple[str, str]:
        return (str(f.get("fact_type") or "other"), str(f.get("raw_value") or f.get("normalized_value")))
    old = {key(f): f for f in previous}
    new = {key(f): f for f in current}
    added = [new[k] for k in sorted(set(new) - set(old))]
    removed = [old[k] for k in sorted(set(old) - set(new))]
    changed: list[dict[str, Any]] = []
    old_by_type: dict[str, list[dict[str, Any]]] = {}
    new_by_type: dict[str, list[dict[str, Any]]] = {}
    for fact in previous:
        old_by_type.setdefault(str(fact.get("fact_type")), []).append(fact)
    for fact in current:
        new_by_type.setdefault(str(fact.get("fact_type")), []).append(fact)
    for fact_type in sorted(set(old_by_type) & set(new_by_type)):
        # Multiple values (e.g. several reporting periods) cannot be paired
        # safely without period labels; leave those as add/remove evidence.
        if len(old_by_type[fact_type]) != 1 or len(new_by_type[fact_type]) != 1:
            continue
        before, after = old_by_type[fact_type][0], new_by_type[fact_type][0]
        if (before.get("raw_value"), before.get("normalized_value")) != (after.get("raw_value"), after.get("normalized_value")):
            changed.append({"fact_type": fact_type, "previous": before, "current": after})
    return {"added": added[:8], "removed": removed[:8], "changed": changed[:8]}


def _merge_share_capital_candidates(
    prior: dict[str, Any],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist only unapproved source-bound capital-note candidates.

    A candidate is evidence for review, not a financial-engine operand.  A
    reprocessed source replaces only its own prior candidate so a later
    verified version cannot leave an obsolete same-document value active.
    """
    current_keys = {
        (str((row.get("source") or {}).get("id") or ""), str(row.get("symbol") or ""))
        for row in current if isinstance(row, dict)
    }
    retained = [
        row for row in prior.get("candidates") or []
        if isinstance(row, dict)
        and (str((row.get("source") or {}).get("id") or ""), str(row.get("symbol") or "")) not in current_keys
    ]
    candidates = retained + current
    candidates.sort(key=lambda row: (str(row.get("symbol") or ""), str((row.get("source") or {}).get("id") or "")))
    return {
        "schema_version": 1,
        "source": {"company_documents": "state/company_documents.json"},
        "policy": {
            "candidate_only": True,
            "approved": False,
            "does_not_activate_financial_truth": True,
            "owner_approval_required_before_financial_engine_import": True,
            "no_raw_pdf_or_full_page_text": True,
        },
        "summary": {
            "candidate_count": len(candidates),
            "candidate_company_count": len({row.get("symbol") for row in candidates if row.get("symbol")}),
        },
        "candidates": candidates,
    }


def run(index_path: Path = STATE / "research_index.json", output_path: Path = OUT,
        extraction_queue_path: Path | None = None, ledger_path: Path = LEDGER_OUT,
        queue_path: Path = QUEUE_OUT, series_path: Path = SERIES_OUT,
        share_capital_candidates_path: Path | None = None) -> int:
    registry = load_json(index_path, {})
    rows = _doc_rows(registry)
    # Terra's raw bytes are intentionally transient and ignored by git.  Join
    # them here by stable doc_id; this pass never downloads a URL.
    extraction_queue_path = extraction_queue_path or (ROOT / ".cache" / "company_intel" / "extraction_queue.json")
    extraction_rows = load_json(extraction_queue_path, []) if extraction_queue_path.exists() else []
    if isinstance(extraction_rows, dict):
        extraction_rows = extraction_rows.get("documents") or extraction_rows.get("queue") or []
    transient = {str(r.get("doc_id")): r for r in extraction_rows if isinstance(r, dict) and r.get("doc_id")}
    source_registry = load_json(STATE / "company_intel" / "source_registry.json", {"tickers": {}})
    prior = _load_registry(output_path)
    documents = dict(prior.get("documents") or {})
    processed = failed = staged = 0
    transient_series: list[dict[str, Any]] = []
    transient_share_capital_candidates: list[dict[str, Any]] = []
    if share_capital_candidates_path is None:
        share_capital_candidates_path = (
            SHARE_CAPITAL_CANDIDATES_OUT if output_path == OUT
            else output_path.parent / "company_intel" / "official_share_capital_candidates.json"
        )
    prior_share_capital_candidates = load_json(share_capital_candidates_path, {"candidates": []})

    for key, entry in sorted(rows.items(), key=lambda item: str(item[0])):
        source_id = entry.get("official_document_id") or entry.get("id") or key
        url = _source(entry, "url")
        local_path = _path_for(entry)
        doc_hint = str(entry.get("doc_id") or ("psx:" + str(entry.get("official_document_id") or entry.get("id") or key)
                                               if str(entry.get("official_document_id") or entry.get("id") or key).isdigit()
                                               else ""))
        if not local_path and doc_hint in transient:
            local_path = transient[doc_hint].get("path")
        doc_id = _doc_id(entry, str(key), url, local_path)
        inline = entry.get("text")
        # Only verified content enters extraction. Metadata-only legacy research
        # rows remain outside this state file rather than being guessed as events.
        download = entry.get("download") if isinstance(entry.get("download"), dict) else {}
        if download and download.get("status") not in (None, "verified", "ok"):
            continue
        if not local_path and inline is None:
            staged += 1
            continue
        try:
            local_path = _safe_path(local_path)
            transient_row = transient.get(doc_hint) if doc_hint else None
            chunk_paths = transient_row.get("chunk_paths") if isinstance(transient_row, dict) else None
            if isinstance(chunk_paths, list) and chunk_paths:
                safe_chunks = [_safe_path(str(path)) for path in chunk_paths]
                offsets = [int(v) for v in (transient_row.get("chunk_page_offsets") or [])]
                hashes = [str(v) for v in (transient_row.get("chunk_hashes") or [])]
                extracted = extract_chunked_local(safe_chunks, offsets, hashes)
                # The chunks are transport units; canonical source identity is
                # the retained original hash, never the synthetic path hash.
                extracted["content_sha256"] = str(entry.get("content_sha256") or transient_row.get("content_sha256") or "")
            else:
                extracted = extract_entry({"path": local_path, "text": inline,
                                           "media_type": entry.get("mime_type") or entry.get("media_type")})
            # Terra's hash is the ingestion hash.  Use it when present, but keep
            # our local hash for integrity diagnostics if bytes differ.
            content_sha = str(entry.get("content_sha256") or extracted["content_sha256"])
            if entry.get("content_sha256") and content_sha != extracted["content_sha256"]:
                raise ValueError("content_sha256 does not match extracted local bytes")
            title = entry.get("title") or entry.get("digest") or ""
            doc_type, doc_events, facts = extract_events(
                doc_id, title, extracted["text"], extracted["pages"], _ticks(entry),
                source_url=url, published_at=entry.get("published_at") or entry.get("date"),
                content_sha256=content_sha)
            material_event_only = entry.get("classification") == "material_information"
            if material_event_only:
                # Exact material-information intake may yield source-bound
                # operating evidence, never financial, capital, or model
                # inputs.  The transport manifest is the sole authority for
                # this narrow classification; unclassified announcements do
                # not reach this path.
                facts = []
            v2_doc = {"doc_id": doc_id, "title": title, "source_url": url, "content_sha256": content_sha, "period_end": entry.get("period_end"), "published_at": entry.get("published_at") or entry.get("date"), "retrieved_at": entry.get("retrieved_at"), "available_on": entry.get("available_on")}
            v2_doc["symbol"] = (_ticks(entry) or [None])[0]
            v2_doc["page_count"] = len(extracted["pages"])
            v2_facts = [] if material_event_only else extract_facts(
                v2_doc, extracted["pages"], extracted.get("words"), extracted.get("page_records"))
            if not material_event_only:
                transient_share_capital_candidates.extend(
                    extract_share_capital_evidence(v2_doc, extracted["pages"], extracted.get("page_records"))
                )
            # Retain geometry-backed facts first.  Legacy extractor claims can
            # be numerous, and a shared evidence cap must never evict the
            # stricter page/table facts that downstream financial models need.
            facts = facts + v2_facts
            retained_facts = v2_facts + facts[:-len(v2_facts)] if v2_facts else facts
            evidence: list[dict[str, Any]] = []
            for item in doc_events + facts:
                evidence.extend(item.get("evidence") or [])
            # Stable de-duplication and bounded exact excerpts.
            seen = set()
            evidence = [e for e in evidence if not (str(e) in seen or seen.add(str(e)))]
            old = documents.get(doc_id) or {}
            versions = list(old.get("versions") or [])
            ledger_changes = list(old.get("ledger_changes") or [])
            if old.get("content_sha256") and old.get("content_sha256") != content_sha:
                versions.append({"content_sha256": old.get("content_sha256"),
                                 "observed_at": old.get("retrieved_at"),
                                 "doc_type": old.get("doc_type")})
            versions = versions[-MAX_VERSIONS:]
            record = {
                "schema_version": 1, "doc_id": doc_id, "tickers": _ticks(entry),
                "title": title, "doc_type": doc_type,
                "classification": entry.get("classification"),
                "published_at": entry.get("published_at") or entry.get("date"),
                "retrieved_at": entry.get("retrieved_at") or (old.get("retrieved_at") if old.get("content_sha256") == content_sha else time.strftime("%Y-%m-%d %H:%M")),
                "available_on": _available_on(v2_doc),
                "source_url": url, "source": entry.get("source"),
                "content_sha256": content_sha, "local_sha256": extracted["content_sha256"],
                "content_length": entry.get("content_length"),
                "page_count": len(extracted["pages"]),
                "media_type": entry.get("mime_type") or entry.get("media_type") or extracted["media_type"],
                "status": "ready", "stale": False, "error": None,
                "evidence": evidence[:MAX_EVIDENCE], "events": doc_events,
                "facts": retained_facts[:MAX_EVIDENCE], "versions": versions,
                "brief_evidence": list(old.get("brief_evidence") or [])[-MAX_BRIEF_EVIDENCE:],
                "ledger_changes": ledger_changes,
            }
            # Normalize while the verified full pages are still transient.  Only
            # bounded values/evidence are retained by the series writer; raw PDF
            # bytes and full page text never enter durable state.
            for fact in facts:
                series_row = normalize_fact(record, fact, pages=extracted["pages"],
                                            source_registry=source_registry)
                if series_row:
                    transient_series.append(series_row)
            if record != old:
                if old.get("content_sha256") and old.get("content_sha256") != content_sha:
                    change = {"change_id": "chg_" + doc_id + "_" + content_sha[:16],
                              "doc_id": doc_id, "tickers": _ticks(entry),
                              "previous_sha256": old.get("content_sha256"),
                              "content_sha256": content_sha,
                              "changed_at": record["retrieved_at"],
                              "event_ids": [e.get("event_id") for e in doc_events],
                              "fact_delta": _fact_delta(old.get("facts") or [], facts)}
                    if change["change_id"] not in {c.get("change_id") for c in ledger_changes}:
                        ledger_changes.append(change)
                    record["ledger_changes"] = ledger_changes
                documents[doc_id] = record
                processed += 1
        except Exception as exc:  # one bad local file must not kill the cycle
            failed += 1
            old = documents.get(doc_id)
            if old:
                documents[doc_id] = {**old, "status": "stale", "stale": True,
                                     "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
            else:
                documents[doc_id] = {"schema_version": 1, "doc_id": doc_id,
                                     "tickers": _ticks(entry), "title": entry.get("title") or entry.get("digest"),
                                     "source_url": url, "status": "error", "stale": True,
                                     "error": f"{type(exc).__name__}: {str(exc)[:120]}",
                                     "evidence": [], "events": [], "facts": [], "versions": []}

    prior_docs = prior.get("documents") or {}
    out = {"schema_version": 1, "documents": documents,
           "_meta": {"updated": time.strftime("%Y-%m-%d %H:%M"),
                     "processed": processed, "staged": staged, "failed": failed,
                     "evidence_max_per_document": MAX_EVIDENCE,
                     "full_text_retained": False,
                     "source": "state/research_index.json; local verified content only"}}
    # Do not destroy last-good state if the registry is unavailable or malformed.
    if documents != prior_docs or not output_path.exists():
        save_json(output_path, out)
    share_capital_state = _merge_share_capital_candidates(
        prior_share_capital_candidates, transient_share_capital_candidates,
    )
    if share_capital_state != prior_share_capital_candidates or not share_capital_candidates_path.exists():
        save_json(share_capital_candidates_path, share_capital_state)
    # Replay every durable receipt on each run. append_events/build_queue deduplicate, so this
    # repairs a crash after company_documents.json was saved but before either downstream write.
    replay_events = [event for doc in documents.values() for event in (doc.get("events") or [])]
    replay_changes = [change for doc in documents.values() for change in (doc.get("ledger_changes") or [])]
    append_events(replay_events, path=ledger_path, changes=replay_changes)
    build_queue(documents, path=queue_path)
    if transient_series or not series_path.exists():
        merge_rows(transient_series, output_path=series_path)
    print(
        "document_intelligence: "
        f"processed={processed} staged={staged} failed={failed} events={len(replay_events)} "
        f"share_capital_candidates={len(share_capital_state['candidates'])}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=STATE / "research_index.json")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--extraction-queue", type=Path,
                        default=ROOT / ".cache" / "company_intel" / "extraction_queue.json")
    parser.add_argument("--series", type=Path, default=SERIES_OUT)
    args = parser.parse_args(argv)
    return run(args.input, args.output, args.extraction_queue, series_path=args.series)


if __name__ == "__main__":
    sys.exit(main())
