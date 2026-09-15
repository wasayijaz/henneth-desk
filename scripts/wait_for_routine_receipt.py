"""Wait for a verified PM or Daily completion receipt on origin/main.

This is a read-only coordination gate for the scheduled PM -> Daily -> Room chain.
It fetches the canonical remote, validates the matching receipt and run-log pair,
and exits non-zero instead of allowing a downstream routine to guess that its
predecessor completed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable


class ReceiptError(RuntimeError):
    """Raised when remote completion evidence is absent or inconsistent."""


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ReceiptError(detail)
    return result


def _remote_json(root: Path, relative_path: str) -> object:
    result = _git(root, "show", f"origin/main:{relative_path}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"origin/main:{relative_path} is not valid JSON: {exc}") from exc


def _same_entry(left: dict, right: dict) -> bool:
    fields = ("routine", "started", "research_sha", "mode", "outcome", "ended")
    return all(left.get(field) == right.get(field) for field in fields)


def validate_evidence(
    receipts: object,
    runlog: object,
    acknowledgment: object,
    routine: str,
    session_date: date,
    is_ancestor: Callable[[str], bool],
) -> dict:
    if not isinstance(receipts, list) or not isinstance(runlog, list):
        raise ReceiptError("remote receipt or run-log file is not a JSON array")

    matches: list[dict] = []
    for entry in receipts:
        if not isinstance(entry, dict) or entry.get("routine") != routine:
            continue
        try:
            started_date = datetime.fromisoformat(str(entry.get("started"))).date()
        except ValueError:
            continue
        if started_date == session_date:
            matches.append(entry)
    if not matches:
        raise ReceiptError(f"no {routine} receipt for {session_date.isoformat()} on origin/main")

    receipt = max(matches, key=lambda item: str(item.get("started", "")))
    log = next(
        (
            item
            for item in runlog
            if isinstance(item, dict)
            and item.get("routine") == routine
            and item.get("started") == receipt.get("started")
        ),
        None,
    )
    if log is None or not _same_entry(log, receipt):
        raise ReceiptError("matching remote run-log evidence is missing or differs from the receipt")

    research_sha = str(receipt.get("research_sha", ""))
    if len(research_sha) != 40 or not is_ancestor(research_sha):
        raise ReceiptError("receipt research SHA is not reachable from origin/main")

    if routine == "pm":
        proof = receipt.get("ack_proof")
        expected = {
            "acked_at": receipt.get("ended"),
            "by": "checkpoint-pm",
            "routine": "pm",
            "started": receipt.get("started"),
            "research_sha": research_sha,
        }
        if proof != expected or acknowledgment != proof:
            raise ReceiptError("PM receipt acknowledgment proof is missing or not current on origin/main")

    return receipt


def check_remote(root: Path, routine: str, session_date: date) -> dict:
    _git(root, "fetch", "origin", "main")
    receipts = _remote_json(root, "state/routine_finalization.json")
    runlog = _remote_json(root, "state/runlog.json")
    acknowledgment = _remote_json(root, "state/checkpoint_ack.json") if routine == "pm" else None

    def is_ancestor(sha: str) -> bool:
        return _git(root, "merge-base", "--is-ancestor", sha, "origin/main", check=False).returncode == 0

    return validate_evidence(receipts, runlog, acknowledgment, routine, session_date, is_ancestor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routine", choices=("pm", "daily"), required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=180)
    args = parser.parse_args()
    if args.timeout_seconds < 0 or not 1 <= args.poll_seconds <= 300:
        parser.error("timeout must be non-negative and poll interval must be 1-300 seconds")

    root = Path(__file__).resolve().parents[1]
    deadline = time.monotonic() + args.timeout_seconds
    last_error = "completion evidence unavailable"
    while True:
        try:
            receipt = check_remote(root, args.routine, args.date)
            print(json.dumps({
                "status": "verified",
                "routine": args.routine,
                "date": args.date.isoformat(),
                "started": receipt["started"],
                "research_sha": receipt["research_sha"],
            }, sort_keys=True))
            return 0
        except ReceiptError as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            print(f"BLOCKED: {last_error}")
            return 1
        time.sleep(min(args.poll_seconds, max(0.0, deadline - time.monotonic())))


if __name__ == "__main__":
    raise SystemExit(main())
