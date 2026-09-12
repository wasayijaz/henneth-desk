#!/usr/bin/env python3
"""Deterministic regression check for the shared repository push lane."""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from publish_lock import (
    PublishLock,
    PublishLockBusy,
    _canonical_remote_url,
    git_common_dir,
    git_path,
)


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")


def _seed_remote(base: Path, name: str) -> Path:
    remote = base / f"{name}.git"
    seed = base / f"{name}-seed"
    _git(base, "init", "-q", "--bare", str(remote))
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _git(
        seed,
        "-c",
        "user.name=Henneth Lock Check",
        "-c",
        "user.email=lock-check@invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "initial",
    )
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "-u", "origin", "main")
    return remote


def _clone(base: Path, remote: Path, name: str) -> Path:
    clone = base / name
    _git(base, "clone", "-q", str(remote), str(clone))
    return clone


def _hold(root: str, ready, release) -> None:
    with PublishLock(Path(root), timeout_s=2, poll_s=0.05, task="lock-check-holder"):
        ready.set()
        release.wait(10)


def _acquire_then_exit(root: str, ready) -> None:
    lock = PublishLock(Path(root), timeout_s=2, poll_s=0.05, task="lock-check-crash")
    lock.acquire()
    ready.set()
    os._exit(0)


def main() -> None:
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="henneth-publish-lock-") as temporary:
        base = Path(temporary)
        origin = _seed_remote(base, "shared-origin")
        separate_origin = _seed_remote(base, "separate-origin")
        primary = _clone(base, origin, "clone-a")
        independent = _clone(base, origin, "clone-b")
        separate = _clone(base, separate_origin, "separate-clone")
        peer = base / "worktree"
        _git(primary, "worktree", "add", "-qb", "peer", str(peer))

        if git_common_dir(primary) != git_common_dir(peer):
            raise AssertionError("sibling worktrees did not resolve one Git common directory")
        if git_common_dir(primary) == git_common_dir(independent):
            raise AssertionError("independent clones unexpectedly share a Git common directory")
        if git_path(peer, "index.lock").parent == peer / ".git":
            raise AssertionError("linked-worktree index lock resolved under the .git pointer file")

        credentialed = _canonical_remote_url(
            "https://user:secret@example.com/org/henneth.git?token=ignored"
        )
        ssh = _canonical_remote_url("git@EXAMPLE.com:org/henneth.git")
        if credentialed != ssh or "secret" in credentialed:
            raise AssertionError("remote identity did not normalize credentials and transport")

        primary_lock = PublishLock(primary, timeout_s=1, poll_s=0.05)
        independent_lock = PublishLock(independent, timeout_s=1, poll_s=0.05)
        peer_lock = PublishLock(peer, timeout_s=1, poll_s=0.05)
        separate_lock = PublishLock(separate, timeout_s=1, poll_s=0.05)
        if primary_lock.lock_path != independent_lock.lock_path:
            raise AssertionError("independent clones of one origin did not share a lock path")
        if primary_lock.lock_path != peer_lock.lock_path:
            raise AssertionError("worktree and clone did not share a lock path")
        if primary_lock.lock_path == separate_lock.lock_path:
            raise AssertionError("separate repositories unexpectedly share a lock path")

        ready = context.Event()
        release = context.Event()
        holder = context.Process(target=_hold, args=(str(primary), ready, release))
        holder.start()
        try:
            if not ready.wait(5):
                raise AssertionError("holder did not acquire the publication lane")
            with PublishLock(
                separate, timeout_s=0.2, poll_s=0.05, task="lock-check-separate-repo"
            ):
                pass
            try:
                with PublishLock(
                    independent, timeout_s=0.2, poll_s=0.05, task="lock-check-contender"
                ):
                    raise AssertionError("contender entered an occupied publication lane")
            except PublishLockBusy as exc:
                if "lock-check-holder" not in str(exc):
                    raise AssertionError("cross-clone busy result omitted holder metadata") from exc
        finally:
            release.set()
            holder.join(5)
            if holder.is_alive():
                holder.terminate()
                holder.join(5)
        if holder.exitcode != 0:
            raise AssertionError(f"holder exited with {holder.exitcode}")

        with PublishLock(independent, timeout_s=1, poll_s=0.05, task="lock-check-release"):
            pass

        cleanup = PublishLock(
            independent, timeout_s=1, poll_s=0.05, task="lock-check-metadata-cleanup"
        ).acquire()
        with patch.object(Path, "unlink", side_effect=PermissionError("simulated busy file")):
            cleanup.release()
        with PublishLock(independent, timeout_s=1, poll_s=0.05, task="lock-check-after-warning"):
            pass

        crashed_ready = context.Event()
        crashed = context.Process(
            target=_acquire_then_exit, args=(str(independent), crashed_ready)
        )
        crashed.start()
        if not crashed_ready.wait(5):
            raise AssertionError("crash worker did not acquire the publication lane")
        crashed.join(5)
        if crashed.exitcode != 0:
            raise AssertionError(f"crash worker exited with {crashed.exitcode}")

        with PublishLock(peer, timeout_s=1, poll_s=0.05, task="lock-check-recovery"):
            pass

        metadata_path = PublishLock(independent, timeout_s=1, poll_s=0.05).metadata_path
        if metadata_path.exists():
            raise AssertionError("holder metadata remained after publication lane release")

    print(
        "check_publish_lock: PASS - same-origin clones contended; separate repository did not; "
        "crash released the lane"
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
