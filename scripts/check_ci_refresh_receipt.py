#!/usr/bin/env python3
"""Offline checker for the CI refresh receipt contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ci_artifact_integrity import artifact_paths
from build_ci_refresh_receipt import RECEIPT, build_receipt, validate_receipt


def assert_excluded_from_artifact_manifest() -> None:
    if any(path.name == RECEIPT.name for path in artifact_paths()):
        raise ValueError("refresh_receipt.json must remain outside the generated artifact manifest")


def self_check() -> int:
    receipt, written = build_receipt(
        before={"psx-document:1": "a" * 64},
        after={"psx-document:1": "b" * 64, "issuer-page:X:https://x": "c" * 64},
        polls=[{
            "name": "psx-index", "cadence": "daily", "status": "ok", "returncode": 0,
            "started_at": "2026-09-20T00:00:00Z", "finished_at": "2026-09-20T00:00:01Z",
        }],
        outputs_attempted=["state/research_index.json"],
        failures=[],
        prior={},
    )
    if not written or not isinstance(receipt, dict):
        print("ci_refresh_receipt self-check: FAIL (receipt not produced)")
        return 1
    if receipt.get("source_commit_sha") == "unknown":
        print("ci_refresh_receipt self-check: FAIL (lineage commit missing)")
        return 1
    validate_receipt(receipt)
    assert_excluded_from_artifact_manifest()
    hashes = receipt["source_hashes"]
    if "before" in hashes or "after" in hashes:
        print("ci_refresh_receipt self-check: FAIL (full inventory was embedded)")
        return 1
    if not hashes["delta_hashes"]["changed"][0]["before"] or not hashes["delta_hashes"]["changed"][0]["after"]:
        print("ci_refresh_receipt self-check: FAIL (changed hashes not retained)")
        return 1
    unchanged, should_write = build_receipt(
        before={"x": "a"}, after={"x": "a"}, polls=[], outputs_attempted=[], failures=[], prior=receipt,
    )
    if unchanged is not None or should_write:
        print("ci_refresh_receipt self-check: FAIL (no-change run rewrote receipt)")
        return 1
    changed_poll, changed_poll_write = build_receipt(
        before={"known-document": "a" * 64}, after={"known-document": "a" * 64},
        polls=[{
            "name": "psx-index", "cadence": "daily", "status": "ok", "returncode": 0,
            "started_at": "2026-09-20T00:00:00Z", "finished_at": "2026-09-20T00:00:01Z",
            "changed": True,
        }],
        outputs_attempted=["state/research_index.json"], failures=[], prior=receipt,
    )
    if not changed_poll_write or not isinstance(changed_poll, dict) or not changed_poll["review_required"]:
        print("ci_refresh_receipt self-check: FAIL (changed poll was skipped or not review-required)")
        return 1
    validate_receipt(changed_poll)
    try:
        validate_receipt({"kind": "wrong"})
    except ValueError:
        pass
    else:
        print("ci_refresh_receipt self-check: FAIL (invalid receipt accepted)")
        return 1
    malformed = list(receipt)
    try:
        validate_receipt(malformed)
    except ValueError:
        pass
    else:
        print("ci_refresh_receipt self-check: FAIL (non-object receipt was accepted)")
        return 1
    bad_review = dict(receipt)
    bad_review["review_required"] = False
    try:
        validate_receipt(bad_review)
    except ValueError:
        pass
    else:
        print("ci_refresh_receipt self-check: FAIL (false review state was accepted)")
        return 1
    print("ci_refresh_receipt self-check: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    try:
        assert_excluded_from_artifact_manifest()
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        validate_receipt(receipt)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"ci_refresh_receipt: FAIL ({exc})", file=sys.stderr)
        return 1
    print(f"ci_refresh_receipt: PASS ({receipt['run_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
