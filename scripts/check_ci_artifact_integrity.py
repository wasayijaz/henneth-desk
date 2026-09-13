#!/usr/bin/env python3
"""Verify the Company Intelligence build envelope and artifact hashes offline."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_ci_artifact_integrity import (
    CI_DIR,
    GENERATOR_VERSION,
    MANIFEST,
    artifact_paths,
    canonical_hash,
    rel,
)
from psx_data import ROOT, load_json


UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def fail(message: str) -> None:
    raise AssertionError(message)


def configured_expected_source_commit_sha(env: dict[str, str] | None = None) -> str | None:
    """Return the explicit release/check source commit, if the environment supplies one."""
    env = env or os.environ
    configured = str(
        env.get("HENNETH_CI_SOURCE_COMMIT_SHA")
        or env.get("GITHUB_SHA")
        or ""
    ).strip()
    if configured and not COMMIT_SHA.fullmatch(configured):
        fail("configured CI source commit is not a full 40-character SHA")
    return configured.lower() if configured else None


def current_checkout_sha() -> str | None:
    """Resolve current HEAD when available; static artifact checks do not require it."""
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        return None
    if head and not COMMIT_SHA.fullmatch(head):
        fail("current checkout commit is not a full 40-character SHA")
    return head.lower() if head else None


def expected_source_commit_sha() -> str | None:
    """Resolve the exact commit required by a CI/release run, if configured.

    A committed generated artifact cannot contain the hash of the commit that
    contains it.  Therefore ordinary static checks verify the envelope and
    hashes without requiring HEAD equality.  CI and release jobs always expose
    GITHUB_SHA (or HENNETH_CI_SOURCE_COMMIT_SHA), so those runs remain strict
    and fail closed on any mismatch after finalization.
    """
    configured = configured_expected_source_commit_sha()
    head = current_checkout_sha()
    if configured and head and configured.lower() != head.lower():
        fail("configured CI source commit does not match current checkout HEAD")
    return configured


def assert_envelope(data: dict[str, Any], path: str, cutoff: str, sha: str) -> None:
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        fail(f"{path}: missing _meta build envelope")
    if meta.get("generator_version") != GENERATOR_VERSION:
        fail(f"{path}: generator version mismatch")
    if meta.get("source_commit_sha") != sha:
        fail(f"{path}: source commit mismatch")
    if meta.get("build_cutoff_at") != cutoff or meta.get("generated_at") != cutoff:
        fail(f"{path}: build cutoff/generated timestamp mismatch")
    if meta.get("artifact_path") != path:
        fail(f"{path}: artifact path mismatch")
    semantics = meta.get("timestamp_semantics") or {}
    if not isinstance(semantics, dict) or "not a source-effective" not in str(semantics.get("generated_at") or ""):
        fail(f"{path}: generated timestamp semantics missing")


def main() -> int:
    manifest = load_json(MANIFEST, {})
    if not isinstance(manifest, dict) or manifest.get("kind") != "ci_artifact_integrity_manifest":
        fail("integrity manifest missing or invalid")
    cutoff = manifest.get("build_cutoff_at")
    sha = manifest.get("source_commit_sha")
    if manifest.get("generator_version") != GENERATOR_VERSION or not isinstance(sha, str) or not sha:
        fail("manifest generator or source commit missing")
    if not COMMIT_SHA.fullmatch(sha):
        fail("manifest source commit must be a full 40-character SHA")
    expected_sha = expected_source_commit_sha()
    if expected_sha and sha.lower() != expected_sha:
        fail(f"manifest source commit {sha} does not match current checkout {expected_sha}")
    if not isinstance(cutoff, str) or not UTC_Z.fullmatch(cutoff) or manifest.get("generated_at") != cutoff:
        fail("manifest must use one UTC Z build cutoff")
    paths = artifact_paths()
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or manifest.get("artifact_count") != len(paths) or len(entries) != len(paths):
        fail("manifest artifact count mismatch")
    by_path = {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}
    if set(by_path) != {rel(path) for path in paths}:
        fail("manifest artifact paths drifted")
    for path in paths:
        path_text = rel(path)
        data = load_json(path, None)
        if not isinstance(data, dict):
            fail(f"{path_text}: not a JSON object")
        # Readiness consumes this manifest; it is intentionally not stamped
        # with the manifest envelope to avoid a self-referential loop.
        if path_text != "state/company_intel/event_to_value_product_readiness.json":
            assert_envelope(data, path_text, cutoff, sha)
        entry = by_path[path_text]
        if entry.get("sha256") != canonical_hash(data):
            fail(f"{path_text}: hash mismatch")
    policy = manifest.get("policy") or {}
    for key in ("single_utc_build_cutoff", "all_generated_ci_artifacts_stamped", "generated_metadata_is_not_source_timing", "deployed_commit_must_match_source_commit_sha"):
        if policy.get(key) is not True:
            fail(f"manifest policy missing {key}")
    print(f"ci_artifact_integrity: PASS ({len(paths)} artifacts, cutoff {cutoff})")
    return 0


def self_test() -> int:
    good = "1234567890abcdef1234567890abcdef12345678"
    other = "abcdef1234567890abcdef1234567890abcdef12"
    if configured_expected_source_commit_sha({"GITHUB_SHA": good}) != good:
        print("self-test failed: GITHUB_SHA was not accepted")
        return 1
    if configured_expected_source_commit_sha({"HENNETH_CI_SOURCE_COMMIT_SHA": other, "GITHUB_SHA": good}) != other:
        print("self-test failed: explicit Henneth source SHA did not win")
        return 1
    if configured_expected_source_commit_sha({}) is not None:
        print("self-test failed: static mode unexpectedly required a checkout commit")
        return 1
    try:
        configured_expected_source_commit_sha({"GITHUB_SHA": "not-a-sha"})
    except AssertionError:
        pass
    else:
        print("self-test failed: malformed source SHA was accepted")
        return 1
    print("ci_artifact_integrity self-test: ok")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(self_test())
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ci_artifact_integrity: FAIL ({exc})", file=sys.stderr)
        raise SystemExit(1)
