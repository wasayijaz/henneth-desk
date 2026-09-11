#!/usr/bin/env python3
"""Cross-worktree lock for the local shared-repository push lane.

Sibling Git worktrees have separate indexes but share one Git common directory.  An
OS-level advisory lock in that directory serializes the short preflight/commit/push
transaction without preventing routines from preparing research in parallel.  The
operating system releases the lock automatically if a publisher exits or crashes.

This serializes Git mutation, not product refresh lifecycles.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO


LOCK_NAME = "henneth-repo-publish.lock"
METADATA_NAME = "henneth-repo-publish.lock.json"


class PublishLockBusy(RuntimeError):
    """Raised when another local worktree owns the repository push lane."""


def git_common_dir(root: Path) -> Path:
    """Return the shared Git directory used by ``root`` and all sibling worktrees."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"cannot resolve Git common directory: {detail}")
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = root / common
    return common.resolve()


def git_path(root: Path, name: str) -> Path:
    """Resolve a Git-managed path for the specific worktree at ``root``."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", name],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"cannot resolve Git path {name}: {detail}")
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _lock_file(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class PublishLock:
    """Bounded context manager for Henneth's local repository push lane."""

    def __init__(
        self,
        root: Path,
        *,
        timeout_s: float = 60,
        poll_s: float = 2,
        task: str | None = None,
    ) -> None:
        self.root = root.resolve()
        self.timeout_s = max(0.0, timeout_s)
        self.poll_s = max(0.05, poll_s)
        self.task = task or "manual-publish"
        self.common_dir = git_common_dir(self.root)
        self.lock_path = self.common_dir / LOCK_NAME
        self.metadata_path = self.common_dir / METADATA_NAME
        self.token = uuid.uuid4().hex
        self.handle: BinaryIO | None = None

    def _metadata(self) -> dict[str, object]:
        return {
            "token": self.token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "task": self.task,
            "worktree": str(self.root),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    def _write_metadata(self) -> None:
        temporary = self.metadata_path.with_name(
            f"{self.metadata_path.name}.{self.token}.tmp"
        )
        temporary.write_text(
            json.dumps(self._metadata(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.metadata_path)

    def _holder(self) -> str:
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "another local publisher (holder metadata unavailable)"
        task = data.get("task") or "unknown task"
        host = data.get("host") or "unknown host"
        pid = data.get("pid") or "unknown PID"
        worktree = data.get("worktree") or "unknown worktree"
        started = data.get("started_at") or "unknown time"
        return f"{task} on {host} (PID {pid}, {worktree}, since {started})"

    def acquire(self) -> "PublishLock":
        deadline = time.monotonic() + self.timeout_s
        while True:
            handle = self.lock_path.open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            if _lock_file(handle):
                self.handle = handle
                try:
                    self._write_metadata()
                except Exception:
                    _unlock_file(handle)
                    handle.close()
                    self.handle = None
                    raise
                return self
            handle.close()

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PublishLockBusy(
                    "publication lane is busy: " + self._holder()
                )
            time.sleep(min(self.poll_s, remaining))

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            try:
                data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            if data.get("token") == self.token:
                try:
                    self.metadata_path.unlink(missing_ok=True)
                except OSError as exc:
                    # Diagnostic metadata must not turn a completed push into a
                    # reported failure. The next owner replaces it atomically.
                    print(
                        f"publish: warning: could not remove lock metadata: {exc}",
                        file=sys.stderr,
                    )
        finally:
            _unlock_file(self.handle)
            self.handle.close()
            self.handle = None

    def __enter__(self) -> "PublishLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()
