#!/usr/bin/env python3
"""Cross-clone lock for the local shared-repository push lane.

Sibling Git worktrees have separate indexes, and independent clones have separate
Git common directories.  A user-local OS-level advisory lock keyed by the
credential-free canonical push remote serializes the short preflight/commit/push
transaction without preventing routines from preparing research in parallel.  The
operating system releases the lock automatically if a publisher exits or crashes.

This serializes Git mutation, not product refresh lifecycles.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import posixpath
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


LOCK_NAME = "henneth-repo-publish.lock"
METADATA_NAME = "henneth-repo-publish.lock.json"
_SCP_REMOTE_RE = re.compile(r"^[^/@\s]+@([^:\s]+):(.+)$")
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


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


def _repository_path(path_text: str) -> str:
    """Normalize a local repository path without retaining a trailing ``.git``."""
    path = Path(path_text).expanduser().resolve(strict=False)
    if path.name.lower().endswith(".git"):
        path = path.with_name(path.name[:-4])
    return os.path.normcase(str(path))


def _remote_path(path_text: str) -> str:
    path = posixpath.normpath("/" + unquote(path_text).lstrip("/"))
    if path == "/.":
        path = "/"
    path = path.rstrip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    return path.strip("/")


def _canonical_remote_url(remote_url: str) -> str:
    """Return a credential-free identity for a Git remote URL.

    Transport and authentication details are deliberately excluded so HTTPS and
    SSH URLs for the same host/path share a publication lane.  Local repository
    URLs retain their normalized absolute path so unrelated repositories stay
    independent.
    """
    raw = remote_url.strip()
    if not raw:
        raise ValueError("empty remote URL")

    scp_match = _SCP_REMOTE_RE.match(raw)
    if scp_match:
        host, path = scp_match.groups()
        normalized_path = _remote_path(path)
        if not normalized_path:
            raise ValueError("remote URL has no repository path")
        return f"remote:{host.lower()}/{normalized_path}"

    if _WINDOWS_PATH_RE.match(raw):
        return f"local:{_repository_path(raw)}"

    parsed = urlsplit(raw)
    if not parsed.scheme:
        return f"local:{_repository_path(raw)}"

    if parsed.scheme.lower() == "file":
        local_path = url2pathname(unquote(parsed.path))
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            local_path = f"//{parsed.netloc}{local_path}"
        return f"local:{_repository_path(local_path)}"

    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("remote URL has an invalid host or port") from exc
    if not host:
        raise ValueError("remote URL has no host")
    host = host.encode("idna").decode("ascii").lower()
    default_ports = {"http": 80, "https": 443, "git": 9418, "ssh": 22}
    authority = host
    if port is not None and port != default_ports.get(parsed.scheme.lower()):
        authority = f"{host}:{port}"
    normalized_path = _remote_path(parsed.path)
    if not normalized_path:
        raise ValueError("remote URL has no repository path")
    return f"remote:{authority}/{normalized_path}"


def git_remote_identity(root: Path) -> str:
    """Return the credential-free identity of the repository's push remote.

    A repository without an ``origin`` cannot have a cross-clone identity.  It
    falls back to its Git common directory so the old local locking guarantee is
    retained without ever placing a raw remote URL in an error or lock path.
    """
    result = subprocess.run(
        ["git", "remote", "get-url", "--push", "origin"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        remote_url = next(
            (line.strip() for line in result.stdout.splitlines() if line.strip()), ""
        )
        if remote_url:
            try:
                return _canonical_remote_url(remote_url)
            except ValueError:
                pass
    return f"git-common:{git_common_dir(root)}"


def _publish_lock_root() -> Path:
    """Return a user-local directory for OS publication locks."""
    configured = os.environ.get("XDG_RUNTIME_DIR") if os.name != "nt" else None
    user_scope = hashlib.sha256(
        f"{getpass.getuser()}:{getattr(os, 'getuid', lambda: 0)()}".encode("utf-8")
    ).hexdigest()[:16]
    base = (
        Path(configured)
        if configured and Path(configured).is_absolute()
        else Path(tempfile.gettempdir()) / f"henneth-publish-{user_scope}"
    )
    root = base / "henneth-publish-locks"
    root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            root.chmod(0o700)
        except OSError:
            pass
    return root


def publish_lock_directory(root: Path) -> Path:
    """Return the per-remote user-local directory used by ``PublishLock``."""
    identity = git_remote_identity(root)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    path = _publish_lock_root() / digest
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


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
    """Bounded context manager for a named per-remote repository lane."""

    def __init__(
        self,
        root: Path,
        *,
        timeout_s: float = 60,
        poll_s: float = 2,
        task: str | None = None,
        lane: str = "publish",
    ) -> None:
        self.root = root.resolve()
        self.timeout_s = max(0.0, timeout_s)
        self.poll_s = max(0.05, poll_s)
        self.task = task or "manual-publish"
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", lane):
            raise ValueError("lock lane must be lowercase alphanumeric words separated by hyphens")
        self.lane = lane
        self.common_dir = git_common_dir(self.root)
        self.lock_dir = publish_lock_directory(self.root)
        self.lock_path = self.lock_dir / (
            LOCK_NAME if lane == "publish" else f"henneth-repo-{lane}.lock"
        )
        self.metadata_path = self.lock_dir / (
            METADATA_NAME if lane == "publish" else f"henneth-repo-{lane}.lock.json"
        )
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
                raise PublishLockBusy(f"{self.lane} lane is busy: " + self._holder())
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
