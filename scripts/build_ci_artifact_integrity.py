#!/usr/bin/env python3
"""Stamp Company Intelligence artifacts with one reproducible UTC build envelope.

This is a finalizer, not a source or calculation producer.  It runs only after
the CI product builders and the private slice have completed.  It gives every
generated CI artifact the same build cutoff, generator identity and source
commit, then writes a separate, hash-backed manifest.  Source timestamps stay
inside their source records; this envelope must never be treated as economic
event timing by a consumer or no-lookahead check.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json


CI_DIR = STATE / "company_intel"
SLICE = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
MANIFEST = CI_DIR / "artifact_integrity.json"
READINESS = CI_DIR / "event_to_value_product_readiness.json"
GENERATOR_VERSION = "ci_artifact_integrity_v1"
COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
EXCLUDED_STATE_NAMES = {
    "artifact_integrity.json",
    "backfill_cursor.json",
    "cursors.json",
    "reprocess_receipts.json",
    # Operational CI refresh lineage is append/update state, not a generated
    # investor artifact. Excluding it prevents a no-change/poll receipt update
    # from invalidating the sealed product envelope.
    "refresh_receipt.json",
    "supabase_archive_receipt.json",
    "private_thesis_storage_receipt.json",
    # Owner-approved, append-only page geometry for image-only documents. It
    # is a provenance ledger, not a generated investor-facing artifact; its
    # closed schema must not receive a generated metadata envelope.
    "manual_document_authority.json",
    # A manual, append-only deployment-verification record. It is release
    # evidence rather than a generated investor-facing CI product artifact.
    "release_integrity_receipt.json",
}


def utc_z(value: str | None = None) -> str:
    """Validate a UTC build timestamp, defaulting to the current instant."""
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value).strip()
    if not text.endswith("Z"):
        raise ValueError("build cutoff must be ISO 8601 UTC with a Z suffix")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("build cutoff must be UTC")
    return parsed.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit_sha() -> str:
    configured = str(os.environ.get("HENNETH_CI_SOURCE_COMMIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=5
        ).strip()
    except Exception:
        return "unknown"


def artifact_paths() -> list[Path]:
    paths = [path for path in sorted(CI_DIR.glob("*.json")) if path.name not in EXCLUDED_STATE_NAMES]
    if not SLICE.exists():
        raise FileNotFoundError(f"private CI slice is missing: {SLICE}")
    paths.append(SLICE)
    return paths


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def canonical_hash(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stamp(data: dict[str, Any], *, cutoff: str, sha: str, source_path: str) -> dict[str, Any]:
    existing = data.get("_meta")
    meta = dict(existing) if isinstance(existing, dict) else {}
    meta.update({
        "generator_version": GENERATOR_VERSION,
        "source_commit_sha": sha,
        "build_cutoff_at": cutoff,
        "generated_at": cutoff,
        "artifact_path": source_path,
        "timestamp_semantics": {
            "build_cutoff_at": "generation boundary only; not a source-effective or source-published time",
            "generated_at": "artifact generation time only; not a source-effective or source-published time",
        },
    })
    return {**data, "_meta": meta}


def build(*, cutoff: str | None = None, source_sha: str | None = None) -> dict[str, Any]:
    build_cutoff = utc_z(cutoff or os.environ.get("HENNETH_CI_BUILD_CUTOFF_AT"))
    sha = str(source_sha or commit_sha()).strip().lower()
    if not COMMIT_SHA.fullmatch(sha):
        raise ValueError("source commit must be a full 40-character SHA")
    artifacts: list[dict[str, Any]] = []
    for path in artifact_paths():
        raw = load_json(path, None)
        if not isinstance(raw, dict):
            raise ValueError(f"{rel(path)} must be a JSON object to receive integrity metadata")
        # The readiness artifact consumes this manifest.  Stamp every other
        # artifact, but hash readiness as-is to avoid a self-referential
        # manifest/readiness update loop.
        stamped = raw if path == READINESS else stamp(raw, cutoff=build_cutoff, sha=sha, source_path=rel(path))
        if path != READINESS:
            save_json(path, stamped)
        artifacts.append({
            "path": rel(path),
            "sha256": canonical_hash(stamped),
            "bytes": len(json.dumps(stamped, ensure_ascii=False, allow_nan=False).encode("utf-8")),
        })
    payload = {
        "schema_version": 1,
        "kind": "ci_artifact_integrity_manifest",
        "generator_version": GENERATOR_VERSION,
        "source_commit_sha": sha,
        "build_cutoff_at": build_cutoff,
        "generated_at": build_cutoff,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "policy": {
            "single_utc_build_cutoff": True,
            "all_generated_ci_artifacts_stamped": True,
            "generated_metadata_is_not_source_timing": True,
            "deployed_commit_must_match_source_commit_sha": True,
        },
    }
    save_json(MANIFEST, payload)
    print(f"ci_artifact_integrity: {len(artifacts)} artifacts at {build_cutoff}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-cutoff-at", help="one ISO 8601 UTC Z timestamp for the complete CI build")
    parser.add_argument("--source-commit-sha", help="commit supplied by CI/deployment instead of resolving HEAD")
    args = parser.parse_args(argv)
    build(cutoff=args.build_cutoff_at, source_sha=args.source_commit_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
