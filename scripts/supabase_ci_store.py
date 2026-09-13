#!/usr/bin/env python3
"""Append source-grounded Company Intelligence state to Supabase.

The local ``state/`` tree remains the desk's source of truth. This adapter is a
server-only archive writer for the deployed CI tables and is inert until both
``HENNETH_CI_SUPABASE_URL`` and ``HENNETH_CI_SUPABASE_SERVICE_KEY`` are set.
It never fetches binaries, never prints secrets, and never updates existing
archive rows; duplicates are ignored by each table's deployed unique key. If a
current-run verified PDF is still present in the ignored local cache, it is
also copied into the private Henneth CI Storage bucket.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psx_data import ROOT, load_json, save_json


ENV_URL = "HENNETH_CI_SUPABASE_URL"
ENV_KEY = "HENNETH_CI_SUPABASE_SERVICE_KEY"
PRODUCER = "henneth-ci-state-archive"
SCHEMA_VERSION = 2

TABLES = {
    "source_documents": ("ci_source_documents", "document_key"),
    "document_blobs": ("ci_document_blobs", "document_key"),
    "document_facts": ("ci_document_facts", "fact_key"),
    "state_snapshots": ("ci_state_snapshots", "snapshot_key"),
    "sync_runs": ("ci_sync_runs", "run_key"),
}

DOCUMENT_BUCKET = "ci-documents"
PDF_CONTENT_TYPE = "application/pdf"
PDF_MAX_BYTES = 50 * 1024 * 1024
ARCHIVE_RECEIPT_RELATIVE_PATH = Path("state") / "company_intel" / "supabase_archive_receipt.json"

SELECTED_INTEL_PRODUCTS = (
    # Explicitly archive every generated per-company CI product.  Cursor, receipt,
    # and transient-review files are intentionally excluded: they are not research
    # state and must not masquerade as a source-grounded company snapshot.
    "causal_foundations.json",
    "cement_operating_series.json",
    "cement_historical_reconciliation.json",
    "change_intelligence.json",
    "company_brains.json",
    "company_graph.json",
    "conditional_benchmarks.json",
    "driver_graphs.json",
    "earnings_bridges.json",
    "guidance_contradictions.json",
    "evidence_watchlist.json",
    "financial_coverage.json",
    "financial_evidence_reconciliation.json",
    "financial_forecasts.json",
    "financial_model_inputs.json",
    "forecast_readiness.json",
    "formal_valuations.json",
    "historical_state_map.json",
    "impact_scenarios.json",
    "intelligence_confidence.json",
    "management_delivery.json",
    "market_expectations.json",
    "monitoring.json",
    "operating_events.json",
    "peer_registry.json",
    "scenario_lab.json",
    "signal_clusters.json",
    "thesis_monitoring.json",
)

DATE_FIELDS = (
    "available_at",
    "available_on",
    "published_at",
    "published_on",
    "retrieved_at",
    "detected_at",
    "as_of",
    "generated_at",
    "updated_at",
)


@dataclass(frozen=True)
class Config:
    url: str
    service_key: str


@dataclass
class BuildStats:
    source_documents: int = 0
    document_blobs: int = 0
    document_facts: int = 0
    state_snapshots: int = 0
    sync_runs: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    sources: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def source(self, path: str) -> None:
        self.sources[path] = self.sources.get(path, 0) + 1

    @property
    def rows(self) -> int:
        return self.source_documents + self.document_facts + self.state_snapshots + self.sync_runs


@dataclass
class ArchiveRows:
    source_documents: list[dict[str, Any]] = field(default_factory=list)
    document_blobs: list[dict[str, Any]] = field(default_factory=list)
    document_blob_candidates: list["BlobCandidate"] = field(default_factory=list)
    document_facts: list[dict[str, Any]] = field(default_factory=list)
    state_snapshots: list[dict[str, Any]] = field(default_factory=list)
    sync_runs: list[dict[str, Any]] = field(default_factory=list)

    def as_table_map(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "source_documents": self.source_documents,
            "document_blobs": self.document_blobs,
            "document_facts": self.document_facts,
            "state_snapshots": self.state_snapshots,
            "sync_runs": self.sync_runs,
        }


@dataclass(frozen=True)
class BlobCandidate:
    document_key: str
    local_path: str
    content_type: str = PDF_CONTENT_TYPE


class SupabaseTransport:
    """Small injectable PostgREST transport; checks replace it with a fake."""

    def post_json(self, url: str, headers: dict[str, str], rows: list[dict[str, Any]]) -> int:
        data = json.dumps(rows, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return int(getattr(response, "status", response.getcode()))

    def upload_storage(self, url: str, headers: dict[str, str], body: bytes) -> int:
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return int(getattr(response, "status", response.getcode()))

    def get_json(self, url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
        """Read a bounded server-only PostgREST result for archive verification."""
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("archive verification returned a non-list response")
        return [row for row in payload if isinstance(row, dict)]


def config_from_env(env: dict[str, str] | None = None) -> tuple[Config | None, list[str]]:
    env = env or os.environ
    missing = [name for name in (ENV_URL, ENV_KEY) if not str(env.get(name) or "").strip()]
    if missing:
        return None, missing
    return Config(url=str(env[ENV_URL]).rstrip("/"), service_key=str(env[ENV_KEY])), []


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_sha(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in value)


def _as_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


def _symbols_from(value: Any) -> list[str]:
    raw = None
    if isinstance(value, dict):
        raw = value.get("symbol") or value.get("ticker") or value.get("company_id") or value.get("tickers")
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        return sorted({symbol for item in raw if (symbol := _as_symbol(item))})
    symbol = _as_symbol(raw)
    return [symbol] if symbol else []


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _availability(*records: dict[str, Any]) -> Any:
    for record in records:
        for field_name in DATE_FIELDS:
            value = record.get(field_name)
            if value not in (None, ""):
                return value
    return None


def _date_candidates(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in DATE_FIELDS and item not in (None, ""):
                out.append(str(item))
            elif isinstance(item, (dict, list)):
                out.extend(_date_candidates(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_date_candidates(item))
    return out


def _best_available_at(payload: Any) -> str | None:
    candidates = _date_candidates(payload)
    return sorted(candidates)[-1] if candidates else None


def _evidence_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _nested_evidence(record: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for field_name in ("evidence", "evidence_refs", "provenance", "provenance_refs", "operand_provenance"):
        evidence.extend(_evidence_items(record.get(field_name)))
    if isinstance(record.get("source"), dict):
        evidence.extend(_evidence_items(record.get("source")))
    for field_name in ("events", "facts", "objects", "contradictions", "alerts", "clusters", "intelligence_objects"):
        for child in _evidence_items(record.get(field_name)):
            evidence.extend(_nested_evidence(child))
    if _first_value(record.get("source_url"), record.get("content_sha256"), record.get("document_id"), record.get("doc_id")):
        evidence.append({})
    return evidence


def _record_id(record: dict[str, Any], fallback: str) -> str:
    for field_name in (
        "id",
        "fact_id",
        "doc_id",
        "document_id",
        "series_id",
        "event_id",
        "guidance_id",
        "reconciliation_id",
        "evidence_id",
        "cluster_id",
        "alert_id",
        "object_id",
    ):
        value = record.get(field_name)
        if value not in (None, ""):
            return str(value)
    return fallback


def _page_value(value: Any) -> int | str | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _clean_payload(record: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "evidence",
        "evidence_refs",
        "provenance",
        "provenance_refs",
        "operand_provenance",
        "source",
        "text",
    }
    return {str(key): value for key, value in record.items() if key not in blocked}


def _doc_fields(record: dict[str, Any], evidence: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    source_url = _first_value(evidence.get("source_url"), record.get("source_url"))
    source_sha = _first_value(evidence.get("content_sha256"), record.get("content_sha256"), record.get("source_sha256"))
    available_at = _availability(evidence, record)
    if not isinstance(source_url, str) or not source_url.strip():
        return None, "missing_source_url"
    if not _is_sha(source_sha):
        return None, "missing_source_sha256"
    if not available_at:
        return None, "missing_available_at"
    return {
        "source_url": source_url.strip(),
        "source_sha256": str(source_sha).lower(),
        "available_at": available_at,
        "source_system": str(_first_value(evidence.get("source"), record.get("source"), record.get("source_system"), "PSX DPS")),
        "document_id": _first_value(evidence.get("document_id"), record.get("document_id"), record.get("doc_id")),
        "document_type": _first_value(record.get("document_type"), record.get("doc_type"), record.get("type")),
        "title": record.get("title"),
        "published_at": _first_value(evidence.get("published_at"), record.get("published_at"), record.get("published_on")),
    }, None


def _document_key(symbol: str, fields: dict[str, Any]) -> str:
    return "doc_" + digest({
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "source_url": fields["source_url"],
        "source_sha256": fields["source_sha256"],
    })


def _source_document_row(symbol: str, record: dict[str, Any], evidence: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    fields, reason = _doc_fields(record, evidence)
    if fields is None:
        return None, reason
    document_key = _document_key(symbol, fields)
    metadata = _clean_payload(record)
    metadata["schema_version"] = SCHEMA_VERSION
    if fields.get("document_id") not in (None, ""):
        metadata["document_id"] = str(fields["document_id"])
    return {
        "document_key": document_key,
        "symbol": symbol,
        "source_url": fields["source_url"],
        "source_system": fields["source_system"],
        "document_type": fields["document_type"],
        "title": fields["title"],
        "published_at": fields["published_at"],
        "available_at": fields["available_at"],
        "source_sha256": fields["source_sha256"],
        "metadata": metadata,
    }, None


def _fact_row(
    *,
    source_path: str,
    record_kind: str,
    symbol: str,
    record: dict[str, Any],
    record_id: str,
    document_key: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    fact_payload = _clean_payload(record)
    fact_payload["source_path"] = source_path
    fact_payload["record_id"] = record_id
    fact_payload["provenance"] = {
        "document_id": _first_value(evidence.get("document_id"), record.get("document_id"), record.get("doc_id")),
        "source_url": _first_value(evidence.get("source_url"), record.get("source_url")),
        "source_sha256": _first_value(evidence.get("content_sha256"), record.get("content_sha256"), record.get("source_sha256")),
        "evidence_sha256": evidence.get("evidence_sha256"),
        "page": _page_value(_first_value(evidence.get("page"), record.get("page"))),
    }
    payload_sha = digest(fact_payload)
    fact_type = str(_first_value(record.get("fact_type"), record.get("metric"), record.get("event_type"), record_kind))
    return {
        "fact_key": "fact_" + digest({
            "schema_version": SCHEMA_VERSION,
            "document_key": document_key,
            "symbol": symbol,
            "fact_type": fact_type,
            "payload_sha256": payload_sha,
        }),
        "document_key": document_key,
        "symbol": symbol,
        "fact_type": fact_type,
        "fact_payload": fact_payload,
        "available_at": _availability(evidence, record),
        "payload_sha256": payload_sha,
    }


def _fact_rows_from_record(
    *,
    source_path: str,
    record_kind: str,
    record: dict[str, Any],
    fallback_id: str,
    source_documents: dict[str, dict[str, Any]],
    stats: BuildStats,
    default_symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    symbols = _symbols_from(record) or list(default_symbols or [])
    if not symbols:
        stats.reject("missing_symbol")
        return []
    record_id = _record_id(record, fallback_id)
    out: list[dict[str, Any]] = []
    seen = set()
    reasons: list[str] = []
    for evidence in _nested_evidence(record):
        page = _page_value(_first_value(evidence.get("page"), record.get("page")))
        if page is None:
            reasons.append("missing_page")
            continue
        for symbol in symbols:
            doc_row, reason = _source_document_row(symbol, record, evidence)
            if doc_row is None:
                if reason:
                    reasons.append(reason)
                continue
            source_documents.setdefault(doc_row["document_key"], doc_row)
            row = _fact_row(
                source_path=source_path,
                record_kind=record_kind,
                symbol=symbol,
                record=record,
                record_id=record_id,
                document_key=doc_row["document_key"],
                evidence=evidence,
            )
            if row["fact_key"] not in seen:
                seen.add(row["fact_key"])
                out.append(row)
    if not out:
        stats.reject(sorted(reasons)[0] if reasons else "missing_provenance")
    return out


def _document_rows(payload: dict[str, Any], source_documents: dict[str, dict[str, Any]], stats: BuildStats) -> None:
    documents = payload.get("documents") if isinstance(payload.get("documents"), dict) else {}
    for key, doc in sorted(documents.items(), key=lambda item: str(item[0])):
        if not isinstance(doc, dict) or doc.get("status") not in (None, "ready"):
            stats.reject("document_not_ready")
            continue
        symbols = _symbols_from(doc)
        if not symbols:
            stats.reject("missing_symbol")
            continue
        for symbol in symbols:
            row, reason = _source_document_row(symbol, doc, {})
            if row is None:
                if reason:
                    stats.reject(reason)
                continue
            source_documents.setdefault(row["document_key"], row)
            stats.source("state/company_documents.json")


def _path_for(record: dict[str, Any]) -> str | None:
    download = record.get("download") if isinstance(record.get("download"), dict) else {}
    value = (
        record.get("local_path")
        or record.get("path")
        or download.get("local_path")
        or download.get("path")
        or download.get("file")
    )
    return str(value) if value not in (None, "") else None


def _safe_blob_path(root: Path, value: str | None) -> str | None:
    if not value:
        return None
    try:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        raw_root = (root / ".cache" / "company_intel" / "raw").resolve()
        if raw_root not in candidate.parents:
            return None
        return str(candidate)
    except (OSError, RuntimeError, ValueError):
        return None


def _load_extraction_queue(root: Path) -> dict[str, dict[str, Any]]:
    path = root / ".cache" / "company_intel" / "extraction_queue.json"
    if not path.exists():
        return {}
    payload = load_json(path, {})
    rows = payload.get("documents") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}
    return {str(row.get("doc_id")): row for row in rows if isinstance(row, dict) and row.get("doc_id")}


def _blob_candidate_path(root: Path, doc: dict[str, Any], transient: dict[str, dict[str, Any]]) -> str | None:
    local_path = _path_for(doc)
    doc_id = str(doc.get("doc_id") or "")
    if not local_path and doc_id in transient:
        local_path = _path_for(transient[doc_id])
    return _safe_blob_path(root, local_path)


def _document_blob_candidates(
    *,
    root: Path,
    payload: dict[str, Any],
    source_documents: dict[str, dict[str, Any]],
    transient: dict[str, dict[str, Any]],
    stats: BuildStats,
) -> list[BlobCandidate]:
    documents = payload.get("documents") if isinstance(payload.get("documents"), dict) else {}
    candidates: dict[str, BlobCandidate] = {}
    for _key, doc in sorted(documents.items(), key=lambda item: str(item[0])):
        if not isinstance(doc, dict) or doc.get("status") != "ready":
            continue
        local_path = _blob_candidate_path(root, doc, transient)
        if not local_path:
            continue
        for symbol in _symbols_from(doc):
            row, _reason = _source_document_row(symbol, doc, {})
            if row is None or row["document_key"] not in source_documents:
                continue
            content_type = str(_first_value(doc.get("media_type"), doc.get("mime_type"), PDF_CONTENT_TYPE))
            candidates[row["document_key"]] = BlobCandidate(
                document_key=row["document_key"],
                local_path=local_path,
                content_type=content_type,
            )
    stats.document_blobs = len(candidates)
    return [candidates[key] for key in sorted(candidates)]


def _document_index(documents_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    documents = documents_payload.get("documents") if isinstance(documents_payload.get("documents"), dict) else {}
    return {str(doc.get("doc_id") or key): doc for key, doc in documents.items() if isinstance(doc, dict)}


def _financial_rows(
    payload: dict[str, Any],
    docs_by_id: dict[str, dict[str, Any]],
    source_documents: dict[str, dict[str, Any]],
    stats: BuildStats,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tickers = payload.get("tickers") if isinstance(payload.get("tickers"), dict) else {}
    for ticker, bucket in sorted(tickers.items(), key=lambda item: str(item[0])):
        facts = bucket.get("facts") if isinstance(bucket, dict) else []
        for index, fact in enumerate(facts or []):
            if not isinstance(fact, dict):
                stats.reject("invalid_financial_fact")
                continue
            record = dict(fact)
            record.setdefault("ticker", str(ticker).upper())
            doc = docs_by_id.get(str(record.get("document_id") or ""))
            if doc:
                for field_name in ("title", "doc_type", "source", "available_on", "published_at", "retrieved_at"):
                    if field_name in doc and field_name not in record:
                        record[field_name] = doc[field_name]
            for row in _fact_rows_from_record(
                source_path="state/company_financial_series.json",
                record_kind="financial_fact",
                record=record,
                fallback_id=f"{ticker}:{index}",
                source_documents=source_documents,
                stats=stats,
                default_symbols=[str(ticker).upper()],
            ):
                stats.source("state/company_financial_series.json")
                rows.append(row)
    return rows


def _company_records(product_payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    companies = product_payload.get("companies") if isinstance(product_payload.get("companies"), dict) else {}
    records: list[tuple[str, dict[str, Any]]] = []
    for symbol, bucket in sorted(companies.items(), key=lambda item: str(item[0])):
        if not isinstance(bucket, dict):
            continue
        for field_name in (
            "events",
            "facts",
            "objects",
            "contradictions",
            "alerts",
            "clusters",
            "intelligence_objects",
        ):
            values = bucket.get(field_name)
            if isinstance(values, list):
                records.extend((str(symbol).upper(), item) for item in values if isinstance(item, dict))
        if any(name in bucket for name in ("evidence", "evidence_refs", "provenance", "source")):
            records.append((str(symbol).upper(), bucket))
    return records


def _intel_rows(ci_dir: Path, source_documents: dict[str, dict[str, Any]], stats: BuildStats) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in SELECTED_INTEL_PRODUCTS:
        path = ci_dir / filename
        if not path.exists():
            continue
        source_path = "state/company_intel/" + filename
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            stats.reject("invalid_intel_product")
            continue
        for index, (symbol, record) in enumerate(_company_records(payload)):
            record = dict(record)
            record.setdefault("symbol", symbol)
            for row in _fact_rows_from_record(
                source_path=source_path,
                record_kind="ci_product_record",
                record=record,
                fallback_id=f"{symbol}:{index}",
                source_documents=source_documents,
                stats=stats,
                default_symbols=[symbol],
            ):
                stats.source(source_path)
                rows.append(row)
    return rows


def _snapshot_key(state_name: str, symbol: str | None, available_at: str, payload_sha: str) -> str:
    return "snap_" + digest({
        "schema_version": SCHEMA_VERSION,
        "state_name": state_name,
        "symbol": symbol,
        "available_at": available_at,
        "payload_sha256": payload_sha,
    })


def _snapshot_row(state_name: str, symbol: str | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    available_at = _best_available_at(payload)
    if not available_at:
        return None
    payload_sha = digest(payload)
    return {
        "snapshot_key": _snapshot_key(state_name, symbol, available_at, payload_sha),
        "state_name": state_name,
        "symbol": symbol,
        "available_at": available_at,
        "payload": payload,
        "payload_sha256": payload_sha,
    }


def _document_snapshots(payload: dict[str, Any], stats: BuildStats) -> list[dict[str, Any]]:
    documents = payload.get("documents") if isinstance(payload.get("documents"), dict) else {}
    grouped: dict[str, dict[str, Any]] = {}
    for key, doc in documents.items():
        if not isinstance(doc, dict):
            continue
        for symbol in _symbols_from(doc):
            grouped.setdefault(symbol, {})[str(key)] = doc
    rows: list[dict[str, Any]] = []
    for symbol, docs in sorted(grouped.items()):
        row = _snapshot_row("company_documents", symbol, {
            "schema_version": payload.get("schema_version"),
            "documents": docs,
        })
        if row:
            rows.append(row)
            stats.source("state/company_documents.json")
        else:
            stats.reject("snapshot_missing_available_at")
    return rows


def _financial_snapshots(payload: dict[str, Any], stats: BuildStats) -> list[dict[str, Any]]:
    tickers = payload.get("tickers") if isinstance(payload.get("tickers"), dict) else {}
    rows: list[dict[str, Any]] = []
    for ticker, bucket in sorted(tickers.items(), key=lambda item: str(item[0])):
        if not isinstance(bucket, dict):
            continue
        row = _snapshot_row("company_financial_series", str(ticker).upper(), {
            "schema_version": payload.get("schema_version"),
            "ticker": str(ticker).upper(),
            "facts": bucket.get("facts") if isinstance(bucket.get("facts"), list) else [],
        })
        if row:
            rows.append(row)
            stats.source("state/company_financial_series.json")
        else:
            stats.reject("snapshot_missing_available_at")
    return rows


def _intel_snapshots(ci_dir: Path, stats: BuildStats) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in SELECTED_INTEL_PRODUCTS:
        path = ci_dir / filename
        if not path.exists():
            continue
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            stats.reject("invalid_intel_product")
            continue
        companies = payload.get("companies") if isinstance(payload.get("companies"), dict) else {}
        state_name = "company_intel/" + filename.removesuffix(".json")
        for symbol, bucket in sorted(companies.items(), key=lambda item: str(item[0])):
            if not isinstance(bucket, dict):
                continue
            row = _snapshot_row(state_name, str(symbol).upper(), {
                "schema_version": payload.get("schema_version"),
                "registry_version": payload.get("registry_version"),
                "as_of": payload.get("as_of"),
                "symbol": str(symbol).upper(),
                "company": bucket,
            })
            if row:
                rows.append(row)
                stats.source("state/company_intel/" + filename)
            else:
                stats.reject("snapshot_missing_available_at")
    return rows


def _dedupe(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_key = {str(row[key]): row for row in rows}
    return [by_key[name] for name in sorted(by_key)]


def _archive_payload_sha(rows: ArchiveRows) -> str:
    return digest({
        "source_documents": rows.source_documents,
        "document_blobs": rows.document_blobs,
        "document_facts": rows.document_facts,
        "state_snapshots": rows.state_snapshots,
    })


def _sync_run(payload_sha: str, counts: dict[str, int], clock: Any | None = None) -> dict[str, Any]:
    now = clock() if clock else utc_now()
    return {
        "run_key": "run_" + digest({
            "schema_version": SCHEMA_VERSION,
            "producer": PRODUCER,
            "payload_sha256": payload_sha,
        }),
        "producer": PRODUCER,
        "started_at": now,
        "completed_at": now,
        "status": "completed",
        "payload_sha256": payload_sha,
        "counts": counts,
    }


def build_rows(root: Path = ROOT, clock: Any | None = None) -> tuple[ArchiveRows, BuildStats]:
    state_dir = root / "state"
    documents_payload = load_json(state_dir / "company_documents.json", {})
    series_payload = load_json(state_dir / "company_financial_series.json", {})
    if not isinstance(documents_payload, dict):
        documents_payload = {}
    if not isinstance(series_payload, dict):
        series_payload = {}

    stats = BuildStats()
    source_documents: dict[str, dict[str, Any]] = {}
    rows = ArchiveRows()
    transient = _load_extraction_queue(root)

    _document_rows(documents_payload, source_documents, stats)
    rows.document_facts.extend(_financial_rows(series_payload, _document_index(documents_payload), source_documents, stats))
    rows.document_facts.extend(_intel_rows(state_dir / "company_intel", source_documents, stats))
    rows.state_snapshots.extend(_document_snapshots(documents_payload, stats))
    rows.state_snapshots.extend(_financial_snapshots(series_payload, stats))
    rows.state_snapshots.extend(_intel_snapshots(state_dir / "company_intel", stats))

    rows.source_documents = _dedupe(list(source_documents.values()), "document_key")
    rows.document_blob_candidates = _document_blob_candidates(
        root=root,
        payload=documents_payload,
        source_documents={row["document_key"]: row for row in rows.source_documents},
        transient=transient,
        stats=stats,
    )
    rows.document_facts = _dedupe(rows.document_facts, "fact_key")
    rows.state_snapshots = _dedupe(rows.state_snapshots, "snapshot_key")
    counts = {
        "source_documents": len(rows.source_documents),
        "document_blobs": len(rows.document_blob_candidates),
        "document_facts": len(rows.document_facts),
        "state_snapshots": len(rows.state_snapshots),
        "rejected": dict(sorted(stats.rejected.items())),
    }
    rows.sync_runs = [_sync_run(_archive_payload_sha(rows), counts, clock=clock)]

    stats.source_documents = len(rows.source_documents)
    stats.document_blobs = len(rows.document_blob_candidates)
    stats.document_facts = len(rows.document_facts)
    stats.state_snapshots = len(rows.state_snapshots)
    stats.sync_runs = len(rows.sync_runs)
    return rows, stats


def _headers(config: Config) -> dict[str, str]:
    return {
        "apikey": config.service_key,
        "Authorization": "Bearer " + config.service_key,
        "Content-Type": "application/json",
        "Prefer": "return=minimal,resolution=ignore-duplicates",
    }


def _endpoint(config: Config, table_key: str) -> str:
    table, conflict = TABLES[table_key]
    params = urllib.parse.urlencode({"on_conflict": conflict})
    return f"{config.url}/rest/v1/{table}?{params}"


def _storage_headers(config: Config, content_type: str) -> dict[str, str]:
    return {
        "apikey": config.service_key,
        "Authorization": "Bearer " + config.service_key,
        "Content-Type": content_type,
        "cache-control": "31536000",
        "x-upsert": "true",
    }


def _storage_path(document_key: str, content_sha256: str) -> str:
    return f"source-documents/{document_key}/{content_sha256}.pdf"


def _storage_endpoint(config: Config, storage_path: str) -> str:
    quoted = urllib.parse.quote(storage_path, safe="/")
    return f"{config.url}/storage/v1/object/{DOCUMENT_BUCKET}/{quoted}"


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def _blob_row(candidate: BlobCandidate) -> dict[str, Any] | None:
    try:
        path = Path(candidate.local_path)
        if not path.exists() or not path.is_file():
            return None
        body = path.read_bytes()
    except OSError:
        return None
    if not body or len(body) > PDF_MAX_BYTES or not body.startswith(b"%PDF-"):
        return None
    content_sha = hashlib.sha256(body).hexdigest()
    return {
        "document_key": candidate.document_key,
        "storage_path": _storage_path(candidate.document_key, content_sha),
        "content_sha256": content_sha,
        "content_type": PDF_CONTENT_TYPE,
        "byte_size": len(body),
        "_body": body,
    }


def push_rows(
    config: Config,
    rows: ArchiveRows,
    transport: SupabaseTransport | None = None,
    batch_size: int = 250,
) -> dict[str, Any]:
    transport = transport or SupabaseTransport()
    statuses: dict[str, list[int]] = {}
    table_map = rows.as_table_map()
    ordered_keys = ("source_documents", "document_blobs", "document_facts", "state_snapshots", "sync_runs")
    for table_key in ordered_keys:
        table_rows = table_map[table_key]
        statuses[table_key] = []
        if table_key == "document_blobs":
            blob_rows: list[dict[str, Any]] = []
            for candidate in rows.document_blob_candidates:
                row = _blob_row(candidate)
                if row is None:
                    continue
                body = row.pop("_body")
                statuses[table_key].append(
                    transport.upload_storage(
                        _storage_endpoint(config, row["storage_path"]),
                        _storage_headers(config, row["content_type"]),
                        body,
                    )
                )
                blob_rows.append(row)
            rows.document_blobs = _dedupe(blob_rows, "document_key")
            table_rows = rows.document_blobs
        for chunk in _chunks(table_rows, batch_size):
            statuses[table_key].append(transport.post_json(_endpoint(config, table_key), _headers(config), chunk))
    return {"batches": sum(len(value) for value in statuses.values()), "statuses": statuses}


def _project_ref(config: Config) -> str | None:
    """Return the public project reference without retaining the server URL."""
    host = (urllib.parse.urlparse(config.url).hostname or "").lower()
    suffix = ".supabase.co"
    if not host.endswith(suffix):
        return None
    reference = host[: -len(suffix)]
    return reference or None


def _sync_run_verify_endpoint(config: Config, run_key: str) -> str:
    """Return the least-privilege query for one known append-only sync run."""
    params = urllib.parse.urlencode({
        "select": "run_key,completed_at,status,payload_sha256,counts",
        "run_key": "eq." + run_key,
        "limit": "2",
    })
    return f"{config.url}/rest/v1/{TABLES['sync_runs'][0]}?{params}"


def verify_latest_sync_receipt(
    root: Path,
    config: Config,
    transport: SupabaseTransport | None = None,
) -> dict[str, Any]:
    """Read back and match the current local success receipt against Supabase.

    This is intentionally opt-in and read-only.  It provides stronger evidence
    than a successful POST response without letting a transient verifier failure
    change archive state, public research state, or the release gate.
    """
    receipt = load_json(root / ARCHIVE_RECEIPT_RELATIVE_PATH, {})
    if not isinstance(receipt, dict) or receipt.get("status") != "synced":
        raise RuntimeError("archive verification requires a successful local sync receipt")
    expected = receipt.get("latest_sync")
    if not isinstance(expected, dict):
        raise RuntimeError("archive verification requires a latest local sync receipt")
    run_key = expected.get("run_key")
    if not isinstance(run_key, str) or not run_key.startswith("run_"):
        raise RuntimeError("archive verification receipt has an invalid run key")

    transport = transport or SupabaseTransport()
    remote_rows = transport.get_json(_sync_run_verify_endpoint(config, run_key), _headers(config))
    if len(remote_rows) != 1:
        raise RuntimeError("archive verification did not find exactly one remote sync run")
    remote = remote_rows[0]
    required = ("run_key", "completed_at", "status", "payload_sha256", "counts")
    if any(key not in remote for key in required):
        raise RuntimeError("archive verification remote sync run is incomplete")
    if remote.get("status") != "completed":
        raise RuntimeError("archive verification remote sync run is not completed")
    for key in ("run_key", "completed_at", "payload_sha256", "counts"):
        if remote.get(key) != expected.get(key):
            raise RuntimeError(f"archive verification remote {key} does not match local receipt")
    return {
        "run_key": run_key,
        "completed_at": expected["completed_at"],
        "payload_sha256": expected["payload_sha256"],
        "counts": expected["counts"],
    }


def _successful_statuses(result: dict[str, Any]) -> dict[str, list[int]]:
    statuses = result.get("statuses")
    if not isinstance(statuses, dict):
        raise RuntimeError("archive transport returned no status receipt")
    normalized: dict[str, list[int]] = {}
    for table_key, values in statuses.items():
        if not isinstance(table_key, str) or not isinstance(values, list):
            raise RuntimeError("archive transport returned malformed status receipt")
        normalized_values: list[int] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int) or not 200 <= value < 300:
                raise RuntimeError("archive transport returned a non-success status")
            normalized_values.append(value)
        normalized[table_key] = normalized_values
    return normalized


def write_sync_receipt(
    root: Path,
    config: Config,
    rows: ArchiveRows,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Append an evidence-only receipt after every fully successful archive payload.

    ``ci_sync_runs`` remains the durable remote record.  This local receipt never
    contains a URL, credential, source payload, or local path; it simply proves
    that the bounded payload received successful HTTP responses in a cloud cycle.
    Failed or partial runs deliberately write no receipt.
    """
    statuses = _successful_statuses(result)
    run = rows.sync_runs[0] if len(rows.sync_runs) == 1 else None
    if not isinstance(run, dict):
        raise RuntimeError("archive payload did not create exactly one sync run")

    path = root / ARCHIVE_RECEIPT_RELATIVE_PATH
    prior = load_json(path, {})
    prior = prior if isinstance(prior, dict) else {}
    receipts = [item for item in (prior.get("sync_receipts") or []) if isinstance(item, dict)]
    run_key = run.get("run_key")
    if not isinstance(run_key, str) or not run_key:
        raise RuntimeError("archive sync run is missing its stable key")
    if not any(item.get("run_key") == run_key for item in receipts):
        receipts.append({
            "run_key": run_key,
            "completed_at": run.get("completed_at"),
            "payload_sha256": run.get("payload_sha256"),
            "counts": run.get("counts"),
            "http_statuses": statuses,
        })

    receipt = dict(prior)
    receipt["schema_version"] = max(2, int(prior.get("schema_version") or 1))
    project_ref = _project_ref(config)
    if project_ref:
        receipt["project_ref"] = project_ref
    receipt["status"] = "synced"
    receipt["sync_receipts"] = receipts
    receipt["latest_sync"] = receipts[-1]
    receipt["last_attempt"] = {
        "run_key": run_key,
        "completed_at": run.get("completed_at"),
        "status": "synced",
        "payload_sha256": run.get("payload_sha256"),
        "counts": run.get("counts"),
    }
    save_json(path, receipt)
    return receipt


def write_failed_attempt_receipt(root: Path, config: Config, rows: ArchiveRows, exc: Exception) -> dict[str, Any]:
    """Record a secret-free failed latest attempt without fabricating archive success."""
    run = rows.sync_runs[0] if len(rows.sync_runs) == 1 else {}
    path = root / ARCHIVE_RECEIPT_RELATIVE_PATH
    prior = load_json(path, {})
    prior = prior if isinstance(prior, dict) else {}
    receipt = dict(prior)
    receipt["schema_version"] = max(2, int(prior.get("schema_version") or 1))
    project_ref = _project_ref(config)
    if project_ref:
        receipt["project_ref"] = project_ref
    receipt["status"] = "sync_failed"
    receipt["last_attempt"] = {
        "run_key": run.get("run_key"),
        "completed_at": run.get("completed_at"),
        "status": "failed",
        "payload_sha256": run.get("payload_sha256"),
        "counts": run.get("counts"),
        "error_type": type(exc).__name__,
    }
    save_json(path, receipt)
    return receipt


def _public_stats(stats: BuildStats) -> str:
    rejected = ",".join(f"{key}={stats.rejected[key]}" for key in sorted(stats.rejected)) or "none"
    sources = ",".join(f"{key}={stats.sources[key]}" for key in sorted(stats.sources)) or "none"
    return (
        f"source_documents={stats.source_documents} document_blobs={stats.document_blobs} "
        f"document_facts={stats.document_facts} "
        f"state_snapshots={stats.state_snapshots} sync_runs={stats.sync_runs} "
        f"rejected={rejected} sources={sources}"
    )


def run(
    *,
    root: Path = ROOT,
    env: dict[str, str] | None = None,
    transport: SupabaseTransport | None = None,
    dry_run: bool = False,
    clock: Any | None = None,
) -> dict[str, Any]:
    rows, stats = build_rows(root, clock=clock)
    config, missing = config_from_env(env)
    if missing or dry_run:
        reason = "missing_config:" + ",".join(missing) if missing else "forced"
        print(f"supabase_ci_store: dry-run {reason} {_public_stats(stats)}")
        return {"mode": "dry-run", "missing": missing, "rows": rows, "stats": stats}
    assert config is not None
    try:
        result = push_rows(config, rows, transport=transport)
        write_sync_receipt(root, config, rows, result)
    except Exception as exc:
        write_failed_attempt_receipt(root, config, rows, exc)
        raise
    print(f"supabase_ci_store: posted batches={result['batches']} {_public_stats(stats)}")
    return {"mode": "posted", "push": result, "rows": rows, "stats": stats}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--verify-receipt",
        action="store_true",
        help="read back the latest successful remote sync run without writing archive state",
    )
    args = parser.parse_args(argv)
    try:
        if args.verify_receipt:
            config, missing = config_from_env()
            if missing:
                print(f"supabase_ci_store: verify-receipt missing_config={','.join(missing)}")
                return 0
            assert config is not None
            verified = verify_latest_sync_receipt(args.root, config)
            print(f"supabase_ci_store: verify-receipt PASS run_key={verified['run_key']}")
            return 0
        run(root=args.root, dry_run=args.dry_run)
    except Exception as exc:
        print(f"supabase_ci_store: failed {type(exc).__name__}: {str(exc)[:160]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
