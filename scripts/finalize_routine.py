#!/usr/bin/env python3
"""Finalize one already-published Henneth research routine.

The routine itself publishes research.  This script is the small, deterministic
receipt step that follows it: it proves the research commit is on a fresh
origin/main, proves the current checkout passes preflight, appends the receipt
and run log, acknowledges only the PM checkpoint, and sends those state changes
through the existing publisher.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from publish_lock import PublishLock, PublishLockBusy


ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
RECEIPT_PATH = Path("state/routine_finalization.json")
RUNLOG_PATH = Path("state/runlog.json")
ACK_PATH = Path("state/checkpoint_ack.json")
PKT = timezone(timedelta(hours=5))

ROUTINE_MODES = {
    "pm": {"light", "light-escalated", "light-skipped"},
    "daily": {"full"},
    "room": {"room"},
    "harvest": {"harvest"},
}
SUCCESS_STATUS = "success"
# Status-like prefixes are rejected, while ordinary research prose such as
# "company failed target review" remains a valid outcome.
FORBIDDEN_STATUS_PREFIX = re.compile(
    r"^(?:holiday|weekend|failure|failed|fail|blocked|training)\b", re.IGNORECASE
)
TRANSPORT_WORDS = re.compile(
    r"\b(?:push|pushed|publish|published|publication|remote|receipt|commit|deployed)\b",
    re.IGNORECASE,
)
SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


@dataclass(frozen=True)
class FinalizationResult:
    success: bool
    status: str
    message: str
    remote_commit: str | None = None
    idempotent: bool = False


Runner = Callable[[Sequence[str], Path], CommandResult]


class FinalizationError(RuntimeError):
    """A safe, user-actionable finalization failure."""


@dataclass(frozen=True)
class LegacyAck:
    """The pre-finalizer PM ack shape; it is a clock, not receipt proof."""

    acked_at: str


def _run_command(command: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=False)
    return CommandResult(completed.returncode, completed.stdout or b"", completed.stderr or b"")


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def _call(runner: Runner, command: Sequence[str], root: Path) -> CommandResult:
    try:
        return runner(command, root)
    except OSError as exc:
        raise FinalizationError(f"could not run {' '.join(command[:3])}: {exc}") from exc


def _git(runner: Runner, root: Path, args: Sequence[str]) -> CommandResult:
    return _call(runner, ["git", *args], root)


def _require(result: CommandResult, description: str) -> None:
    if result.returncode:
        detail = _text(result.stderr) or _text(result.stdout)
        if len(detail) > 240:
            detail = detail[:240] + "..."
        raise FinalizationError(f"{description} failed" + (f": {detail}" if detail else ""))


def _now() -> str:
    return datetime.now(PKT).isoformat(timespec="seconds")


def _validate_started(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FinalizationError("started must be an ISO-8601 timestamp with the PKT offset +05:00") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=5):
        raise FinalizationError("started must be an ISO-8601 timestamp with the PKT offset +05:00")
    return parsed.isoformat(timespec="seconds")


def _require_ended_after(started: str, ended: str, label: str) -> None:
    if datetime.fromisoformat(_validate_started(ended)) < datetime.fromisoformat(_validate_started(started)):
        raise FinalizationError(f"{label} ended before it started")


def _validate_inputs(
    routine: str,
    started: str,
    research_sha: str,
    mode: str,
    outcome: str,
    status: str,
) -> tuple[str, str, str]:
    routine = routine.strip().lower()
    if routine not in ROUTINE_MODES:
        raise FinalizationError("routine must be one of: " + ", ".join(sorted(ROUTINE_MODES)))
    started = _validate_started(started.strip())
    research_sha = research_sha.strip().lower()
    if not SHA_RE.fullmatch(research_sha):
        raise FinalizationError("research-sha must be a full hexadecimal git object id (40-64 characters)")
    mode = mode.strip().lower()
    if mode not in ROUTINE_MODES[routine]:
        allowed = ", ".join(sorted(ROUTINE_MODES[routine]))
        raise FinalizationError(f"mode {mode!r} is not valid for {routine}; allowed: {allowed}")
    outcome = " ".join(outcome.split())
    if not outcome:
        raise FinalizationError("outcome must not be empty")
    if status.strip().lower() != SUCCESS_STATUS:
        raise FinalizationError("only a successful routine may be finalized; use the routine recovery path")
    if FORBIDDEN_STATUS_PREFIX.search(outcome):
        raise FinalizationError("holiday, failure, blocked, and training status outcomes cannot be finalized")
    if TRANSPORT_WORDS.search(outcome):
        raise FinalizationError("outcome must describe research only; transport is reported after remote verification")
    return routine, started, research_sha


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _load_bytes(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"cannot read {path.as_posix()}: {exc}") from exc


def _load_array(path: Path) -> list[dict]:
    value = _load_bytes(path, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise FinalizationError(f"{path.as_posix()} must be a JSON array of objects")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_json_bytes(value))
    temporary.replace(path)


def _key_matches(item: dict, routine: str, started: str) -> bool:
    return item.get("routine") == routine and item.get("started") == started


def _find_one(items: list[dict], routine: str, started: str, label: str) -> dict | None:
    matches = [item for item in items if _key_matches(item, routine, started)]
    if len(matches) > 1:
        raise FinalizationError(f"{label} contains duplicate entries for {routine}/{started}")
    return matches[0] if matches else None


def _payload_matches(item: dict, expected: dict) -> bool:
    return all(item.get(field) == expected.get(field) for field in ("routine", "started", "research_sha", "mode", "outcome"))


def _remote_bytes(runner: Runner, root: Path, path: Path) -> bytes | None:
    result = _git(runner, root, ["show", f"origin/main:{path.as_posix()}"])
    if result.returncode:
        return None
    return result.stdout


def _remote_array(runner: Runner, root: Path, path: Path) -> list[dict]:
    raw = _remote_bytes(runner, root, path)
    if raw is None:
        return []
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"origin/main:{path.as_posix()} is not valid JSON: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise FinalizationError(f"origin/main:{path.as_posix()} must be a JSON array of objects")
    return value


ACK_FIELDS = ("acked_at", "by", "routine", "started", "research_sha")


def _validate_ack(value: object, label: str) -> dict:
    if not isinstance(value, dict) or any(field not in value for field in ACK_FIELDS):
        raise FinalizationError(f"{label} is missing PM acknowledgment fields")
    if value["by"] != "checkpoint-pm" or value["routine"] != "pm":
        raise FinalizationError(f"{label} is not a PM checkpoint acknowledgment")
    if not isinstance(value["research_sha"], str) or not SHA_RE.fullmatch(value["research_sha"]):
        raise FinalizationError(f"{label} has an invalid research SHA")
    started = _validate_started(str(value["started"]))
    acked_at = _validate_started(str(value["acked_at"]))
    _require_ended_after(started, acked_at, label)
    return value


def _remote_ack(runner: Runner, root: Path) -> dict | LegacyAck | None:
    raw = _remote_bytes(runner, root, ACK_PATH)
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"origin/main PM acknowledgment is not valid JSON: {exc}") from exc
    if (isinstance(value, dict)
            and set(value) == {"acked_at", "by"}
            and value.get("by") == "checkpoint-pm"):
        acked_at = _validate_started(str(value["acked_at"]))
        return LegacyAck(acked_at)
    return _validate_ack(value, "origin/main PM acknowledgment")


def _verify_pm_ack_state(
    runner: Runner,
    root: Path,
    remote_receipts: list[dict],
    remote_log: list[dict],
    receipt: dict,
) -> None:
    proof = receipt.get("ack_proof")
    if not isinstance(proof, dict):
        raise FinalizationError("PM receipt has no immutable acknowledgment proof")
    _validate_ack(proof, "PM receipt acknowledgment proof")
    if (proof != {"acked_at": receipt.get("ended"), "by": "checkpoint-pm",
                  "routine": "pm", "started": receipt.get("started"),
                  "research_sha": receipt.get("research_sha")}):
        raise FinalizationError("PM receipt acknowledgment proof does not match its receipt")

    current = _remote_ack(runner, root)
    if current is None:
        raise FinalizationError("PM receipt exists but its remote acknowledgment is missing")
    if isinstance(current, LegacyAck):
        raise FinalizationError("legacy PM acknowledgment cannot authenticate this receipt")
    if current == proof:
        return

    target_start = datetime.fromisoformat(_validate_started(str(receipt["started"])))
    current_start = datetime.fromisoformat(_validate_started(str(current["started"])))
    if current_start <= target_start:
        raise FinalizationError("remote PM acknowledgment is missing, corrupt, or different for this receipt")

    later_receipt = _find_one(remote_receipts, "pm", current["started"], "later PM receipt")
    later_log = _find_one(remote_log, "pm", current["started"], "later PM runlog")
    if (later_receipt is None or later_log is None
            or not _payload_matches(later_log, later_receipt)
            or later_receipt.get("research_sha") != current["research_sha"]
            or later_receipt.get("ack_proof") != current
            or not isinstance(later_receipt.get("ended"), str)):
        raise FinalizationError("later PM acknowledgment is not backed by a verified later receipt")
    _require_ended_after(later_receipt["started"], later_receipt["ended"], "later PM receipt")


def _fetch_and_verify_research(runner: Runner, root: Path, research_sha: str) -> None:
    _require(_git(runner, root, ["fetch", "origin", "main", "--quiet"]), "fresh origin/main fetch")
    _require(_git(runner, root, ["rev-parse", "--verify", f"{research_sha}^{{commit}}"]), "research SHA lookup")
    ancestor = _git(runner, root, ["merge-base", "--is-ancestor", research_sha, "origin/main"])
    if ancestor.returncode:
        raise FinalizationError("research SHA is not reachable from freshly fetched origin/main")


def _require_clean_synced_baseline(runner: Runner, root: Path) -> None:
    status = _git(runner, root, ["status", "--porcelain", "--untracked-files=all"])
    _require(status, "clean baseline check")
    if _text(status.stdout):
        raise FinalizationError("baseline is dirty; synchronize and clean the checkout before finalization")

    head = _git(runner, root, ["rev-parse", "--verify", "HEAD"])
    _require(head, "local HEAD lookup")
    origin = _git(runner, root, ["rev-parse", "--verify", "origin/main"])
    _require(origin, "origin/main lookup")
    if _text(head.stdout) != _text(origin.stdout):
        raise FinalizationError("baseline is not synchronized with origin/main; no local-ahead or stale checkout is allowed")

    ahead = _git(runner, root, ["rev-list", "--count", "origin/main..HEAD"])
    _require(ahead, "local-ahead baseline check")
    behind = _git(runner, root, ["rev-list", "--count", "HEAD..origin/main"])
    _require(behind, "local-behind baseline check")
    if _text(ahead.stdout) != "0" or _text(behind.stdout) != "0":
        raise FinalizationError("baseline is not cleanly synchronized with origin/main")


def _remote_commit(runner: Runner, root: Path) -> str | None:
    result = _git(runner, root, ["rev-parse", "--verify", "origin/main"])
    return _text(result.stdout) if result.returncode == 0 else None


def _local_is_ahead(runner: Runner, root: Path) -> bool:
    result = _git(runner, root, ["rev-list", "--count", "origin/main..HEAD"])
    _require(result, "local versus origin/main check")
    try:
        return int(_text(result.stdout) or "0") > 0
    except ValueError as exc:
        raise FinalizationError("local versus origin/main check returned a non-numeric count") from exc


def _merge_append_only(remote: list[dict], local: list[dict]) -> list[dict]:
    """Use the fetched remote history as the base and retain local-only entries."""
    merged = list(remote)
    for item in local:
        if item not in merged:
            merged.append(item)
    return merged


def _exact_entry_matches(item: dict, expected: dict, fields: Sequence[str]) -> bool:
    return all(item.get(field) == expected.get(field) for field in fields)


def _verify_remote(
    runner: Runner,
    root: Path,
    expected_receipt: dict,
    expected_log: dict,
    pm: bool,
) -> str:
    remote_receipts = _remote_array(runner, root, RECEIPT_PATH)
    remote_receipt = _find_one(remote_receipts, expected_receipt["routine"], expected_receipt["started"], "remote receipt")
    receipt_fields = ("routine", "started", "research_sha", "mode", "outcome", "ended")
    if pm:
        receipt_fields += ("ack_proof",)
    if remote_receipt is None or not _exact_entry_matches(remote_receipt, expected_receipt, receipt_fields):
        raise FinalizationError("origin/main receipt does not contain the requested finalization entry")
    _require_ended_after(remote_receipt["started"], remote_receipt["ended"], "remote receipt")

    remote_log = _remote_array(runner, root, RUNLOG_PATH)
    remote_log_entry = _find_one(remote_log, expected_log["routine"], expected_log["started"], "remote runlog")
    if remote_log_entry is None or not _exact_entry_matches(remote_log_entry, expected_log, ("started", "mode", "ended", "outcome", "routine", "research_sha")):
        raise FinalizationError("origin/main runlog does not contain the requested finalization entry")

    if pm:
        _verify_pm_ack_state(runner, root, remote_receipts, remote_log, remote_receipt)

    commit = _remote_commit(runner, root)
    if not commit:
        raise FinalizationError("could not resolve the containing origin/main commit")
    return commit


def _finalize_locked(
    *,
    routine: str,
    started: str,
    research_sha: str,
    mode: str,
    outcome: str,
    status: str = SUCCESS_STATUS,
    root: Path = ROOT,
    runner: Runner = _run_command,
    clock: Callable[[], str] = _now,
) -> FinalizationResult:
    """Run one finalization while the per-origin finalization lane is held."""
    try:
        routine, started, research_sha = _validate_inputs(routine, started, research_sha, mode, outcome, status)
        mode = mode.strip().lower()
        outcome = " ".join(outcome.split())
        receipt_path = root / RECEIPT_PATH
        runlog_path = root / RUNLOG_PATH
        ack_path = root / ACK_PATH

        _fetch_and_verify_research(runner, root, research_sha)
        _require_clean_synced_baseline(runner, root)

        expected_stub = {
            "routine": routine,
            "started": started,
            "research_sha": research_sha,
            "mode": mode,
            "outcome": outcome,
        }
        local_receipts = _load_array(receipt_path)
        local_log = _load_array(runlog_path)
        remote_receipts = _remote_array(runner, root, RECEIPT_PATH)
        remote_log = _remote_array(runner, root, RUNLOG_PATH)
        remote_receipt = _find_one(remote_receipts, routine, started, "remote receipt")
        local_receipt = _find_one(local_receipts, routine, started, "local receipt")
        remote_log_entry = _find_one(remote_log, routine, started, "remote runlog")
        local_log_entry = _find_one(local_log, routine, started, "local runlog")

        remote_ack = _remote_ack(runner, root) if routine == "pm" else None

        if remote_receipt is not None:
            if not _payload_matches(remote_receipt, expected_stub):
                raise FinalizationError("same routine/start already exists remotely with different inputs")
            if remote_log_entry is None or not _payload_matches(remote_log_entry, expected_stub):
                raise FinalizationError("remote receipt exists but its runlog entry is missing or different")
            _require_ended_after(remote_receipt.get("started", ""), remote_receipt.get("ended", ""), "remote receipt")
            if routine == "pm":
                _verify_pm_ack_state(runner, root, remote_receipts, remote_log, remote_receipt)
            commit = _remote_commit(runner, root)
            if not commit:
                raise FinalizationError("could not resolve the containing origin/main commit")
            return FinalizationResult(True, "already-finalized", "same routine/start already verified on origin/main", commit, True)

        if remote_log_entry is not None:
            raise FinalizationError("origin/main has a runlog entry for this routine/start but no receipt")
        if local_receipt is not None or local_log_entry is not None:
            raise FinalizationError("local finalization history exists without a remote matching entry; reconcile it before retrying")

        if isinstance(remote_ack, LegacyAck):
            if datetime.fromisoformat(started) <= datetime.fromisoformat(remote_ack.acked_at):
                raise FinalizationError("this PM run is older than the legacy PM acknowledgment and cannot overwrite it")
        elif remote_ack is not None:
            ack_start = datetime.fromisoformat(_validate_started(str(remote_ack["started"])))
            target_start = datetime.fromisoformat(started)
            if ack_start > target_start:
                raise FinalizationError("this PM run would overwrite a newer remote PM acknowledgment")
            if ack_start == target_start and remote_ack["research_sha"] != research_sha:
                raise FinalizationError("remote PM acknowledgment for this start has a different research SHA")

        preflight = _call(runner, [sys.executable, "scripts/preflight.py", "--desk"], root)
        if preflight.returncode:
            raise FinalizationError("current preflight failed; no acknowledgment or finalization was written")

        ended = clock()
        _validate_started(ended)
        ack = None
        if (routine == "pm" and isinstance(remote_ack, dict)
                and remote_ack["started"] == started):
            ack = remote_ack
            ended = ack["acked_at"]
        else:
            _require_ended_after(started, ended, "finalization")
            if routine == "pm":
                ack = {"acked_at": ended, "by": "checkpoint-pm", "routine": routine,
                       "started": started, "research_sha": research_sha}
        receipt = {**expected_stub, "ended": ended}
        if routine == "pm":
            if ack is None:
                raise FinalizationError("PM acknowledgment could not be prepared")
            receipt["ack_proof"] = ack
        log_entry = {"started": started, "mode": mode, "ended": ended, "outcome": outcome,
                     "routine": routine, "research_sha": research_sha}

        local_receipts = _merge_append_only(remote_receipts, local_receipts)
        local_log = _merge_append_only(remote_log, local_log)
        local_receipts.append(receipt)
        _write_json(receipt_path, local_receipts)
        local_log.append(log_entry)
        _write_json(runlog_path, local_log)

        if routine == "pm":
            if not isinstance(remote_ack, dict) or remote_ack["started"] != started:
                _write_json(ack_path, ack)

        publisher_message = f"Finalize {routine} {started} research {research_sha[:12]}"
        published = _call(runner, [sys.executable, "scripts/publish.py", publisher_message], root)
        if published.returncode:
            fetch = _git(runner, root, ["fetch", "origin", "main", "--quiet"])
            if fetch.returncode == 0 and _local_is_ahead(runner, root):
                raise FinalizationError("publisher failed and a local receipt commit is ahead of origin/main; reconcile that existing commit before retrying")
            raise FinalizationError("publisher failed; finalization is not successful and remote verification did not pass")

        _require(_git(runner, root, ["fetch", "origin", "main", "--quiet"]), "post-publish origin/main fetch")
        if _remote_bytes(runner, root, RECEIPT_PATH) is None and _local_is_ahead(runner, root):
            raise FinalizationError("publisher returned without a remote receipt; a local commit is ahead of origin/main")
        commit = _verify_remote(runner, root, receipt, log_entry, routine == "pm")
        return FinalizationResult(True, "verified", f"receipt, runlog, and required acknowledgment verified on origin/main commit {commit}", commit)
    except FinalizationError as exc:
        return FinalizationResult(False, "blocked", str(exc))
    except (OSError, ValueError, TypeError) as exc:
        return FinalizationResult(False, "blocked", f"finalization stopped safely: {exc}")


def finalize(
    *,
    routine: str,
    started: str,
    research_sha: str,
    mode: str,
    outcome: str,
    status: str = SUCCESS_STATUS,
    root: Path = ROOT,
    runner: Runner = _run_command,
    clock: Callable[[], str] = _now,
) -> FinalizationResult:
    """Serialize finalizer preparation through verified publication."""
    try:
        with PublishLock(root, timeout_s=300, poll_s=0.2,
                         task="routine-finalizer", lane="finalization"):
            return _finalize_locked(
                routine=routine,
                started=started,
                research_sha=research_sha,
                mode=mode,
                outcome=outcome,
                status=status,
                root=root,
                runner=runner,
                clock=clock,
            )
    except (FinalizationError, PublishLockBusy) as exc:
        return FinalizationResult(False, "blocked", str(exc))
    except (OSError, ValueError, TypeError) as exc:
        return FinalizationResult(False, "blocked", f"finalization stopped safely: {exc}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize one already-published Henneth research routine")
    parser.add_argument("--routine", required=True, choices=sorted(ROUTINE_MODES))
    parser.add_argument("--started", required=True, help="ISO-8601 PKT timestamp, for example 2026-09-12T17:20:00+05:00")
    parser.add_argument("--research-sha", required=True, help="full research commit SHA already reachable from origin/main")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--status", default=SUCCESS_STATUS, choices=[SUCCESS_STATUS],
                        help="structural completion status; only success may be finalized")
    args = parser.parse_args(argv)
    result = finalize(**vars(args))
    prefix = "OK" if result.success else "BLOCKED"
    print(f"{prefix}: {result.message}")
    return 0 if result.success else 2


if __name__ == "__main__":
    sys.exit(main())
