#!/usr/bin/env python3
"""Build a bounded, evidence-linked company financial series.

This is a pure state transform: no URL fetches, models or external services.
Rows with no source/page are rejected rather than silently becoming facts.  A
live extraction may provide transient ``pages`` in ``document_pages``; normal
rebuilds use only the evidence retained by ``company_documents.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from financial_series import _parse_structured_raw, normalize_fact
from financial_statement_facts import PARSER_REVISION
from manual_financial_claims import MANUAL_SOURCE_METHOD, qualified_manual_rows
from psx_data import STATE, load_json, save_json

OUT = STATE / "company_financial_series.json"


def _issuer_binding_ok(row: dict[str, Any]) -> bool:
    binding = row.get("issuer_registry_binding")
    if not isinstance(binding, dict) or binding.get("status") != "qualified":
        return False
    source_url = str(row.get("source_url") or "")
    source_page = str(binding.get("source_page") or "")
    root = str(binding.get("root_domain") or "").lower().rstrip(".")
    if root.startswith("www."):
        root = root[4:]
    def _host(value: str) -> str:
        host = (urlparse(value).hostname or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host
    host, page_host = _host(source_url), _host(source_page)
    evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
    first_evidence = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
    return (
        str(binding.get("document_id") or "") == str(row.get("document_id") or "")
        and str(binding.get("link_id") or "") == str(row.get("document_id") or "")
        and str(binding.get("source_url") or "") == source_url
        and str(binding.get("content_sha256") or "") == str(row.get("content_sha256") or "")
        and binding.get("evidence_page") == first_evidence.get("page")
        and source_url.startswith("https://") and source_url.lower().endswith(".pdf")
        and bool(root and (host == root or host.endswith("." + root))
                 and (page_host == root or page_host.endswith("." + root)))
    )


def _repair_row(row: dict[str, Any]) -> dict[str, Any]:
    """Repair invariant-breaking retained rows before conflict grouping."""
    repaired = dict(row)
    unit = str(repaired.get("unit") or "").lower()
    if unit.endswith("/share") and repaired.get("unit_multiplier") != 1:
        repaired["unit_multiplier"] = 1
        raw = repaired.get("raw_value")
        number = _parse_structured_raw(raw)
        if number is not None:
            repaired["normalized_value"] = int(number) if number.is_integer() else number
            repaired["quality_flags"] = [
                flag for flag in (repaired.get("quality_flags") or [])
                if flag != "unparseable_raw_value"
            ]
        else:
            repaired.setdefault("quality_flags", [])
            repaired["quality_flags"] = sorted(set(repaired["quality_flags"] + ["unparseable_raw_value"]))
    return repaired


def _sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Repair impossible legacy scaling before quality-based deduplication."""
    clean = dict(row)
    manual_fact = clean.get("source_method") == MANUAL_SOURCE_METHOD
    # `operating_cash_flow` is a valid geometry-backed cash-flow fact.  Older
    # rows were tagged before the normalizer admitted cash-flow statements;
    # clear only those two obsolete classifier flags when every structural
    # identity field proves this is the same qualified fact type.
    if (
        clean.get("parser_version") == "financial_statement_v2"
        and clean.get("parser_revision") == PARSER_REVISION
        and clean.get("metric") == "operating_cash_flow"
        and clean.get("line") == "operating_cash_flow"
        and clean.get("statement_type") == "cash_flow_statement"
    ):
        clean["quality_flags"] = [
            flag for flag in (clean.get("quality_flags") or [])
            if flag not in {"invalid_structured_statement_type", "unsupported_structured_line"}
        ]
    if clean.get("parser_version") != "financial_statement_v2" and not manual_fact:
        flags = list(clean.get("quality_flags") or [])
        clean["quality_flags"] = sorted(set(flags + ["legacy_extractor_not_model_eligible"]))
    if (clean.get("parser_version") == "financial_statement_v2"
            and clean.get("parser_revision") != PARSER_REVISION):
        flags = list(clean.get("quality_flags") or [])
        clean["quality_flags"] = sorted(set(flags + ["legacy_parser_revision_quarantine"]))
    unit = str(clean.get("unit") or "").lower()
    if unit.endswith("/share") or unit == "percent":
        clean["unit_multiplier"] = 1
        raw = str(clean.get("raw_value") or "").replace("%", "").strip()
        value = _parse_structured_raw(raw)
        if value is not None:
            clean["normalized_value"] = int(value) if value.is_integer() else value
            clean["quality_flags"] = [
                flag for flag in (clean.get("quality_flags") or [])
                if flag != "unparseable_raw_value"
            ]
        else:
            flags = list(clean.get("quality_flags") or [])
            clean["quality_flags"] = sorted(set(flags + ["unparseable_raw_value"]))
    if unit == "percent" or clean.get("metric") == "change_pct":
        clean["currency"] = None
    if (clean.get("parser_version") == "financial_statement_v2"
            and str(clean.get("document_id") or "").startswith("issuer:")):
        binding = clean.get("issuer_registry_binding")
        if not _issuer_binding_ok(clean):
            flags = list(clean.get("quality_flags") or [])
            clean["quality_flags"] = sorted(set(flags + ["issuer_registry_binding_required"]))
    blocking = {"missing_period_end", "missing_currency", "missing_unit_scale",
                "missing_consolidation_basis", "conflicting_consolidation_labels",
                "unparseable_raw_value", "conflict", "issuer_registry_binding_required",
                "legacy_extractor_not_model_eligible", "legacy_parser_revision_quarantine"}
    clean["readiness"] = ("model_loadable" if (clean.get("parser_version") == "financial_statement_v2" or manual_fact) and clean.get("metric") != "change_pct"
                           and not blocking.intersection(clean.get("quality_flags") or []) else "audit_only")
    return clean


def _rows(payload: Any) -> dict[str, dict[str, Any]]:
    values = payload.get("documents") if isinstance(payload, dict) else payload
    if isinstance(values, dict):
        return {str(k): v for k, v in values.items() if isinstance(v, dict)}
    return {}


def _evidence_pages(doc: dict[str, Any]) -> list[str]:
    # Durable documents only retain bounded excerpts.  ``document_pages`` is a
    # transient hook supplied by the current extraction pass and is never saved.
    pages = doc.get("document_pages")
    if isinstance(pages, list):
        return [str(p or "") for p in pages]
    return [str(e.get("text") or "") for e in (doc.get("evidence") or []) if isinstance(e, dict)]


def _assemble(rows_by_ticker: dict[str, list[dict[str, Any]]], *, source_documents: int,
              rejected: int) -> dict[str, Any]:
    tickers: dict[str, dict[str, Any]] = {}
    for ticker, candidates in sorted(rows_by_ticker.items()):
        bucket = {"ticker": ticker, "facts": [], "conflicts": [], "coverage": {}}
        candidates = [_sanitize_row(row) for row in candidates]
        production = [_repair_row(row) for row in candidates if row.get("series_id")]
        def quality(row: dict[str, Any]) -> tuple[int, int, int, str]:
            explicit = sum(bool(row.get(key)) and row.get(key) != "unknown" for key in
                           ("period_end", "currency", "unit_multiplier"))
            explicit += int(row.get("consolidation") not in (None, "unknown"))
            explicit += int(row.get("period_type") not in (None, "unknown"))
            evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
            linked_evidence = sum(
                1 for item in evidence
                if isinstance(item, dict) and item.get("source_url") == row.get("source_url")
            )
            availability = str(row.get("available_on") or "")
            # A subsequent normalization may correct a stale parser-level
            # availability copy from the document receipt.  For the same fact,
            # retain the earliest valid source date; a later date can only
            # weaken the daily no-lookahead guarantee.
            try:
                availability_rank = -date.fromisoformat(availability[:10]).toordinal()
            except ValueError:
                availability_rank = -10**9
            return (explicit + int(bool(row.get("source_url"))) + int(bool(evidence)) + linked_evidence,
                    int(availability_rank != -10**9), availability_rank,
                    -len(row.get("quality_flags") or []),
                    sum(len(str(item.get("text") or "")) for item in evidence if isinstance(item, dict)),
                    json.dumps(row, sort_keys=True, separators=(",", ":")))
        unique: dict[str, dict[str, Any]] = {}
        for row in production:
            key = str(row["series_id"])
            if key not in unique or quality(row) > quality(unique[key]):
                unique[key] = row
        if not unique:
            continue
        facts = list(unique.values())
        facts.sort(key=lambda row: (row.get("period_end") or "", row.get("metric") or "", row["series_id"]))
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in facts:
            group_key = (str(row.get("metric")), str(row.get("period_end")), str(row.get("period_type")), str(row.get("consolidation")))
            groups.setdefault(group_key, []).append(row)
        conflicts = []
        for group_key, members in sorted(groups.items()):
            # A quarantined legacy extraction is retained for auditability but
            # cannot contradict a geometry-verified statement fact.  Only
            # compare like-for-like, model-eligible parser outputs here; a
            # disagreement within that tier remains a real blocking conflict.
            comparable = [m for m in members if (
                m.get("parser_version") == "financial_statement_v2"
                and not (m.get("quality_flags") or [])
            )]
            values = {str((m.get("normalized_value"), m.get("raw_value"))) for m in comparable}
            # Unknown periods/bases are not comparable and must remain visible
            # without being labelled as a conflict.
            if len(values) <= 1 or group_key[1] in {"None", "unknown"} or group_key[3] in {"None", "unknown"}:
                continue
            conflict_id = "conf_" + hashlib.sha256("|".join(group_key).encode()).hexdigest()[:20]
            for member in comparable:
                member.setdefault("quality_flags", [])
                member["quality_flags"] = sorted(set(member["quality_flags"] + ["conflict"]))
                member["readiness"] = "audit_only"
            conflicts.append({"conflict_id": conflict_id, "metric": group_key[0],
                              "period_end": None if group_key[1] == "None" else group_key[1],
                              "period_type": group_key[2], "consolidation": group_key[3],
                              "series_ids": [m["series_id"] for m in members],
                              "reason": "multiple evidenced values share the same period and basis"})
        metrics: dict[str, list[str]] = {}
        for row in facts:
            metrics.setdefault(str(row.get("metric") or "other"), []).append(row["series_id"])
        bucket["facts"] = facts
        bucket["metrics"] = metrics
        bucket["conflicts"] = conflicts
        bucket["coverage"] = {"source_documents": len({f["document_id"] for f in facts}),
                               "fact_count": len(facts),
                               "period_count": len({f.get("period_end") for f in facts if f.get("period_end")}),
                               "missing_required_source": any(not f.get("source_url") or not f.get("evidence") for f in facts),
                               "missing_period_count": sum(1 for f in facts if not f.get("period_end")),
                               "conflict_count": len(conflicts),
                               "model_loadable_count": sum(1 for f in facts if f.get("readiness") == "model_loadable"),
                               "audit_only_count": sum(1 for f in facts if f.get("readiness") != "model_loadable")}
        tickers[ticker] = bucket
    return {"schema_version": 1, "tickers": tickers,
            "_meta": {"updated": time.strftime("%Y-%m-%d %H:%M"),
                      "source": "state/company_documents.json + current verified extraction",
                      "source_documents": source_documents, "rejected_facts": rejected,
                      "append_only_values": True,
                      "note": "Unknown period, unit, currency and consolidation remain explicit; facts retain source/page evidence."}}


def merge_rows(rows: list[dict[str, Any]], output_path: Path = OUT) -> dict[str, Any]:
    """Merge rows from the current transient extraction into durable series."""
    prior = load_json(output_path, {}) if output_path.exists() else {}
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for ticker, bucket in (prior.get("tickers") or {}).items():
        by_ticker[str(ticker).upper()] = list((bucket or {}).get("facts") or [])
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)
    out = _assemble(by_ticker, source_documents=int((prior.get("_meta") or {}).get("source_documents") or 0), rejected=0)
    prior_meta = dict(prior.get("_meta") or {})
    out_meta = dict(out.get("_meta") or {})
    prior_meta.pop("updated", None)
    out_meta.pop("updated", None)
    if out.get("tickers") != prior.get("tickers") or out_meta != prior_meta:
        save_json(output_path, out)
    elif prior:
        out = prior
    return out


def build(input_path: Path = STATE / "company_documents.json", output_path: Path = OUT,
          source_registry_path: Path | None = None) -> dict[str, Any]:
    payload = load_json(input_path, {})
    registry_path = source_registry_path or (STATE / "company_intel" / "source_registry.json")
    source_registry = load_json(registry_path, {"tickers": {}})
    rows = _rows(payload)
    previous = load_json(output_path, {}) if output_path.exists() else {}
    # Durable rows are append-only.  The bounded document surface can be
    # compacted or temporarily degraded; a rebuild must not erase a verified
    # transient full-page normalization from a prior run.
    rows_by_ticker: dict[str, list[dict[str, Any]]] = {
        str(ticker).upper(): [
            fact for fact in (bucket or {}).get("facts") or []
            if not (isinstance(fact, dict) and fact.get("source_method") == MANUAL_SOURCE_METHOD)
        ]
        for ticker, bucket in (previous.get("tickers") or {}).items()
    }
    rejected = 0
    source_docs = 0
    for key, doc in sorted(rows.items()):
        if doc.get("status") != "ready":
            continue
        source_docs += 1
        for fact in doc.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            row = normalize_fact(doc, fact, pages=_evidence_pages(doc), source_registry=source_registry)
            if row is None:
                rejected += 1
                continue
            rows_by_ticker.setdefault(row["ticker"], []).append(row)
    existing_facts = [fact for facts in rows_by_ticker.values() for fact in facts if isinstance(fact, dict)]
    manual_rows, manual_meta = qualified_manual_rows(existing_facts=existing_facts)
    for row in manual_rows:
        rows_by_ticker.setdefault(row["ticker"], []).append(row)
    prior_source_documents = int((previous.get("_meta") or {}).get("source_documents") or 0)
    out = _assemble(rows_by_ticker, source_documents=max(source_docs, prior_source_documents), rejected=rejected)
    out["_meta"]["manual_claims"] = manual_meta
    previous_meta = dict(previous.get("_meta") or {})
    output_meta = dict(out.get("_meta") or {})
    previous_meta.pop("updated", None)
    output_meta.pop("updated", None)
    if out.get("tickers") != previous.get("tickers") or output_meta != previous_meta:
        save_json(output_path, out)
    elif previous:
        out = previous
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=STATE / "company_documents.json")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(argv)
    result = build(args.input, args.output)
    print(f"financial_series: tickers={len(result['tickers'])} facts={sum(len(v.get('facts', [])) for v in result['tickers'].values())} rejected={result['_meta']['rejected_facts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
