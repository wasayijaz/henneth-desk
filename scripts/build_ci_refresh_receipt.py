#!/usr/bin/env python3
"""Build a secret-free, delta-aware receipt for the CI-only refresh runner.

This module is deliberately a receipt builder, not another source or financial
parser.  The existing official-source producers remain authoritative for
conditional requests, extraction, and last-good retention.  A clean no-change
run does not rewrite the durable receipt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from uuid import uuid4

from psx_data import ROOT, STATE, load_json, save_json

RECEIPT = STATE / "company_intel" / "refresh_receipt.json"
SCHEMA_VERSION = 1
KIND = "ci_refresh_receipt"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
RUN_ID = re.compile(r"^[0-9a-fA-F-]{36}$")
UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
POLL_CADENCES = {"daily", "weekly", "manual", "none"}
POLL_STATUSES = {"ok", "degraded", "skipped"}
NEXT_ACTIONS = {"retry-source-poll", "poll-on-next-cadence"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_commit() -> str:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except Exception:
        return "unknown"
    return value if re.fullmatch(r"[0-9a-fA-F]{40}", value) else "unknown"


def _source_row_hash(row: dict[str, Any]) -> str:
    """Hash only source identity/state, excluding run timestamps and errors."""
    kept = {
        key: row.get(key)
        for key in (
            "id", "url", "title", "label", "kind", "document_type", "source_page",
            "content_sha256", "previous_sha256", "status", "published_at", "effective_at",
        )
        if key in row
    }
    return canonical_hash(kept)


def source_inventory(root: Path = ROOT) -> dict[str, str]:
    """Return stable hashes for retained official-source discovery state.

    The inventory intentionally excludes generated CI products and temporary PDF
    bytes.  It watches the two existing source seams: PSX document metadata and
    issuer pages/document links.
    """
    result: dict[str, str] = {}
    index = load_json(root / "state" / "research_index.json", {})
    for doc_id, row in sorted((index.get("documents") or {}).items()):
        if isinstance(row, dict):
            result[f"psx-document:{doc_id}"] = _source_row_hash({"id": doc_id, **row})
    registry = load_json(root / "state" / "company_intel" / "source_registry.json", {})
    for ticker, company in sorted((registry.get("tickers") or {}).items()):
        if not isinstance(company, dict):
            continue
        for row in company.get("monitored_pages") or []:
            if isinstance(row, dict) and row.get("url"):
                result[f"issuer-page:{ticker}:{row['url']}"] = _source_row_hash(row)
        for row in company.get("document_links") or []:
            if isinstance(row, dict) and row.get("id"):
                result[f"issuer-document:{ticker}:{row['id']}"] = _source_row_hash(row)
        # A missing/degraded issuer root is itself a source health change.
        result[f"issuer-health:{ticker}"] = canonical_hash({
            "status": company.get("status"),
            "error": company.get("error"),
            "issuer_url": company.get("issuer_url"),
        })
    return result


def _sanitize(text: Any) -> str:
    value = str(text or "")
    # Producer output is retained only as a short diagnostic. Never persist a
    # token-like value if a future producer accidentally prints one.
    value = re.sub(
        r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]", value,
    )
    return value[-1200:]


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_hashes(outputs_attempted: list[str], root: Path = ROOT) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}
    for value in sorted(set(str(item) for item in outputs_attempted)):
        candidate = (root / value).resolve()
        if root.resolve() not in candidate.parents:
            raise ValueError("output path escapes repository root")
        hashes[value] = _sha256_file(candidate)
    return hashes


def _changed_hashes(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    keys = sorted(set(before) | set(after))
    return {
        "added": [key for key in keys if key not in before],
        "removed": [key for key in keys if key not in after],
        "changed": [key for key in keys if key in before and key in after and before[key] != after[key]],
        "unchanged": [key for key in keys if key in before and key in after and before[key] == after[key]],
    }


def _compact_source_hashes(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    """Keep exact inventory digests plus only hashes for keys that changed."""
    delta = _changed_hashes(before, after)
    delta_hashes = {
        "added": [
            {"key": key, "before": None, "after": after[key]}
            for key in delta["added"]
        ],
        "removed": [
            {"key": key, "before": before[key], "after": None}
            for key in delta["removed"]
        ],
        "changed": [
            {"key": key, "before": before[key], "after": after[key]}
            for key in delta["changed"]
        ],
    }
    return {
        "before_count": len(before),
        "after_count": len(after),
        "before_digest": canonical_hash(dict(sorted(before.items()))),
        "after_digest": canonical_hash(dict(sorted(after.items()))),
        "delta": {
            "added": delta["added"],
            "removed": delta["removed"],
            "changed": delta["changed"],
            "unchanged_count": len(delta["unchanged"]),
        },
        "delta_hashes": delta_hashes,
    }


def build_receipt(
    *,
    before: dict[str, str],
    after: dict[str, str],
    polls: list[dict[str, Any]],
    outputs_attempted: list[str],
    failures: list[dict[str, Any]],
    force_write: bool = False,
    prior: dict[str, Any] | None = None,
    run_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    source_commit_sha: str | None = None,
    root: Path = ROOT,
) -> tuple[dict[str, Any] | None, bool]:
    """Return ``(receipt, written-worthy)`` without writing the receipt itself."""
    changed = _changed_hashes(before, after)
    prior = prior if isinstance(prior, dict) else {}
    failure_state = [
        {"name": str(item.get("name") or "unknown"), "error": _sanitize(item.get("error"))}
        for item in failures
    ]
    previous_failures = prior.get("failures") if isinstance(prior.get("failures"), list) else []
    poll_changed = any(item.get("changed") is True for item in polls)
    degraded_poll = any(item.get("status") == "degraded" for item in polls)
    meaningful = bool(
        changed["added"] or changed["removed"] or changed["changed"]
        or failure_state != previous_failures
        or degraded_poll
        or poll_changed
        or not prior
        or force_write
    )
    if not meaningful:
        return None, False
    finished = finished_at or utc_now()
    output_hashes = _output_hashes(outputs_attempted, root)
    artifact_manifest = _sha256_file(root / "state" / "company_intel" / "artifact_integrity.json")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_id": run_id or str(uuid4()),
        "run_status": "degraded" if failures or degraded_poll else "ok",
        "started_at": started_at or finished,
        "finished_at": finished,
        "source_commit_sha": source_commit_sha or _safe_commit(),
        "lineage": {
            "parent_run_id": prior.get("run_id"),
            "previous_receipt_sha256": canonical_hash(prior) if prior else None,
        },
        "source_polls": [
            {
                "name": str(item.get("name") or "unknown"),
                "cadence": str(item.get("cadence") or "unspecified"),
                "status": str(item.get("status") or "ok"),
                "returncode": int(item.get("returncode", 0)),
                "started_at": item.get("started_at"),
                "finished_at": item.get("finished_at"),
                "changed": bool(item.get("changed")),
                "diagnostic": _sanitize(item.get("diagnostic")),
            }
            for item in polls
        ],
        "source_hashes": _compact_source_hashes(before, after),
        "outputs_attempted": sorted(set(str(value) for value in outputs_attempted)),
        "output_hashes": output_hashes,
        "artifact_integrity_manifest_sha256": artifact_manifest,
        "failures": failure_state,
        "retry_state": {
            "retryable": bool(failures or degraded_poll),
            "attempts": int(prior.get("retry_state", {}).get("attempts", 0) or 0) + (1 if failures or degraded_poll else 0),
            "next_action": "retry-source-poll" if failures or degraded_poll else "poll-on-next-cadence",
        },
        "review_required": bool(failures or poll_changed or changed["added"] or changed["removed"] or changed["changed"]),
        "policy": {
            "deterministic": True,
            "llm_calls": 0,
            "source_failure_preserves_last_good_projection": True,
            "temporary_pdf_bytes_not_receipted": True,
            "no_change_runs_do_not_rewrite_receipt": True,
        },
    }
    return receipt, True


def validate_receipt(receipt: dict[str, Any]) -> None:
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be a JSON object")
    expected = {
        "schema_version", "kind", "run_id", "run_status", "started_at", "finished_at",
        "source_commit_sha", "lineage", "source_polls", "source_hashes", "outputs_attempted",
        "output_hashes", "artifact_integrity_manifest_sha256", "failures", "retry_state",
        "review_required", "policy",
    }
    if set(receipt) != expected:
        raise ValueError("receipt fields drifted")
    if receipt.get("schema_version") != SCHEMA_VERSION or receipt.get("kind") != KIND:
        raise ValueError("invalid CI refresh receipt identity")
    if not isinstance(receipt.get("run_id"), str) or not RUN_ID.fullmatch(receipt["run_id"]):
        raise ValueError("run_id must be a UUID-shaped value")
    if receipt.get("run_status") not in {"ok", "degraded"}:
        raise ValueError("run_status is invalid")
    for field in ("started_at", "finished_at"):
        if not isinstance(receipt.get(field), str) or not UTC_Z.fullmatch(receipt[field]):
            raise ValueError(f"{field} must be an explicit UTC timestamp")
    if not isinstance(receipt.get("source_commit_sha"), str) or not COMMIT_SHA.fullmatch(receipt["source_commit_sha"]):
        raise ValueError("source_commit_sha must be a full commit SHA")
    lineage = receipt.get("lineage")
    if not isinstance(lineage, dict) or set(lineage) != {"parent_run_id", "previous_receipt_sha256"}:
        raise ValueError("receipt lineage fields drifted")
    if lineage["parent_run_id"] is not None and (not isinstance(lineage["parent_run_id"], str) or not RUN_ID.fullmatch(lineage["parent_run_id"])):
        raise ValueError("parent_run_id is invalid")
    if lineage["previous_receipt_sha256"] is not None and (not isinstance(lineage["previous_receipt_sha256"], str) or not SHA256.fullmatch(lineage["previous_receipt_sha256"])):
        raise ValueError("previous receipt hash is invalid")
    hashes = receipt.get("source_hashes")
    if not isinstance(hashes, dict):
        raise ValueError("source hash summary missing")
    for field in ("before_count", "after_count", "before_digest", "after_digest"):
        if field not in hashes:
            raise ValueError(f"source hash summary missing {field}")
    if not all(isinstance(hashes.get(field), int) and hashes[field] >= 0 for field in ("before_count", "after_count")):
        raise ValueError("source hash counts must be non-negative integers")
    if not all(isinstance(hashes.get(field), str) and SHA256.fullmatch(hashes[field]) for field in ("before_digest", "after_digest")):
        raise ValueError("source inventory digests must be SHA-256 values")
    delta = hashes.get("delta")
    if not isinstance(delta, dict) or not all(isinstance(delta.get(key), list) for key in ("added", "removed", "changed")):
        raise ValueError("source hash delta missing")
    if not isinstance(delta.get("unchanged_count"), int) or delta["unchanged_count"] < 0:
        raise ValueError("source hash unchanged count missing")
    delta_hashes = hashes.get("delta_hashes")
    if not isinstance(delta_hashes, dict) or not all(isinstance(delta_hashes.get(key), list) for key in ("added", "removed", "changed")):
        raise ValueError("per-delta source hashes missing")
    for category in ("added", "removed", "changed"):
        expected_keys = delta[category]
        records = delta_hashes[category]
        if [row.get("key") for row in records if isinstance(row, dict)] != expected_keys:
            raise ValueError(f"per-delta source hash keys mismatch for {category}")
        for row in records:
            if not isinstance(row, dict) or not isinstance(row.get("key"), str):
                raise ValueError("invalid per-delta source hash record")
            for side in ("before", "after"):
                value = row.get(side)
                if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                    raise ValueError("invalid per-delta source hash value")
    if hashes["before_count"] != delta["unchanged_count"] + len(delta["removed"]) + len(delta["changed"]):
        raise ValueError("source hash before count does not reconcile")
    if hashes["after_count"] != delta["unchanged_count"] + len(delta["added"]) + len(delta["changed"]):
        raise ValueError("source hash after count does not reconcile")
    polls = receipt.get("source_polls")
    if not isinstance(polls, list) or not polls:
        raise ValueError("source polls must be a non-empty list")
    for poll in polls:
        if not isinstance(poll, dict) or set(poll) != {"name", "cadence", "status", "returncode", "started_at", "finished_at", "changed", "diagnostic"}:
            raise ValueError("source poll fields drifted")
        if not isinstance(poll["name"], str) or not poll["name"].strip() or poll["cadence"] not in POLL_CADENCES:
            raise ValueError("source poll name/cadence is invalid")
        if poll["status"] not in POLL_STATUSES or type(poll["returncode"]) is not int or type(poll["changed"]) is not bool:
            raise ValueError("source poll status/result is invalid")
        for field in ("started_at", "finished_at"):
            if not isinstance(poll[field], str) or not UTC_Z.fullmatch(poll[field]):
                raise ValueError(f"source poll {field} must be an explicit UTC timestamp")
        if not isinstance(poll["diagnostic"], str):
            raise ValueError("source poll diagnostic must be text")
    outputs = receipt.get("outputs_attempted")
    output_hashes = receipt.get("output_hashes")
    if not isinstance(outputs, list) or outputs != sorted(set(outputs)) or not all(isinstance(item, str) and item for item in outputs):
        raise ValueError("outputs_attempted must be a sorted unique path list")
    if not isinstance(output_hashes, dict) or set(output_hashes) != set(outputs):
        raise ValueError("output hashes must cover every attempted output")
    if not all(isinstance(value, str) and SHA256.fullmatch(value) for value in output_hashes.values()):
        raise ValueError("every attempted output must have a SHA-256 hash")
    manifest_hash = receipt.get("artifact_integrity_manifest_sha256")
    if not isinstance(manifest_hash, str) or not SHA256.fullmatch(manifest_hash):
        raise ValueError("artifact integrity manifest hash is missing or invalid")
    failures = receipt.get("failures")
    if not isinstance(failures, list) or not all(isinstance(item, dict) and set(item) == {"name", "error"} and isinstance(item["name"], str) and isinstance(item["error"], str) for item in failures):
        raise ValueError("failure records are invalid")
    degraded = receipt["run_status"] == "degraded"
    if degraded != bool(failures or any(item["status"] == "degraded" for item in polls)):
        raise ValueError("run_status does not match poll/failure state")
    retry = receipt.get("retry_state")
    if not isinstance(retry, dict) or set(retry) != {"retryable", "attempts", "next_action"}:
        raise ValueError("retry state fields drifted")
    if type(retry["retryable"]) is not bool or type(retry["attempts"]) is not int or retry["attempts"] < 0 or retry["next_action"] not in NEXT_ACTIONS:
        raise ValueError("retry state is invalid")
    if retry["retryable"] != degraded or retry["next_action"] != ("retry-source-poll" if degraded else "poll-on-next-cadence"):
        raise ValueError("retry state does not match run status")
    review_required = receipt.get("review_required")
    if type(review_required) is not bool:
        raise ValueError("review_required must be boolean")
    delta_changed = any(delta[key] for key in ("added", "removed", "changed"))
    poll_changed = any(item["changed"] is True for item in polls)
    if review_required != (degraded or poll_changed or delta_changed):
        raise ValueError("review_required does not match source/failure delta")
    policy = receipt.get("policy")
    if not isinstance(policy, dict) or policy != {
        "deterministic": True,
        "llm_calls": 0,
        "source_failure_preserves_last_good_projection": True,
        "temporary_pdf_bytes_not_receipted": True,
        "no_change_runs_do_not_rewrite_receipt": True,
    }:
        raise ValueError("receipt policy drifted")
    if not isinstance(receipt.get("outputs_attempted"), list):
        raise ValueError("poll/output receipt fields missing")
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    if re.search(r"(?i)(bearer\s+ey|service[_-]?role|vercel_.*secret|supabase_.*key)", encoded):
        raise ValueError("possible secret material in receipt")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--poll-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=RECEIPT)
    parser.add_argument("--force-write", action="store_true")
    args = parser.parse_args(argv)
    before = load_json(args.before, {})
    after = load_json(args.after, {})
    results = load_json(args.poll_results, {})
    prior = load_json(args.output, {})
    receipt, should_write = build_receipt(
        before=before, after=after, polls=list(results.get("polls") or []),
        outputs_attempted=list(results.get("outputs_attempted") or []),
        failures=list(results.get("failures") or []), force_write=args.force_write,
        prior=prior,
    )
    if should_write and receipt:
        validate_receipt(receipt)
        save_json(args.output, receipt)
        print(f"ci_refresh_receipt: wrote {args.output}")
    else:
        print("ci_refresh_receipt: no meaningful change; durable receipt unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
