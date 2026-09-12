#!/usr/bin/env python3
"""Focused contract checks for finalize_routine.py.

Mocked cases cover safety ordering and idempotency.  The final case uses a real
temporary bare Git repository and real fetch/push commands, but never touches
this checkout or a production remote.
"""
from __future__ import annotations

import json
import multiprocessing
import subprocess
import tempfile
from pathlib import Path

from finalize_routine import CommandResult, finalize


SHA = "0123456789abcdef0123456789abcdef01234567"
PM = "pm"
DAILY = "daily"
STARTED = "2026-09-12T17:20:00+05:00"
ENDED = "2026-09-12T18:00:00+05:00"


class FakeEnvironment:
    def __init__(self, root: Path, *, research_ok: bool = True,
                 preflight_ok: bool = True, publisher_ok: bool = True) -> None:
        self.root = root
        self.research_ok = research_ok
        self.preflight_ok = preflight_ok
        self.publisher_ok = publisher_ok
        self.remote_files: dict[str, bytes] = {}
        self.remote_commit = "remote-base"
        self.local_commit = self.remote_commit
        self.dirty = False
        self.publisher_calls = 0
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str] | tuple[str, ...], cwd: Path) -> CommandResult:
        command = list(command)
        self.commands.append(command)
        if command[0] == "git":
            args = command[1:]
            if args[:3] == ["fetch", "origin", "main"]:
                return CommandResult(0)
            if args[:2] == ["status", "--porcelain"]:
                return CommandResult(0, b"dirty\n" if self.dirty else b"")
            if args[:2] == ["rev-parse", "--verify"]:
                target = args[2]
                if target == "HEAD":
                    return CommandResult(0, (self.local_commit + "\n").encode())
                if target == "origin/main":
                    return CommandResult(0, (self.remote_commit + "\n").encode())
                if target == f"{SHA}^{{commit}}":
                    return CommandResult(0 if self.research_ok else 1,
                                         (SHA + "\n").encode() if self.research_ok else b"",
                                         b"unknown research\n")
                raise AssertionError(f"unexpected rev-parse target: {target}")
            if args[:3] == ["merge-base", "--is-ancestor", SHA]:
                return CommandResult(0 if self.research_ok else 1)
            if args[:2] == ["rev-list", "--count"]:
                range_name = args[2]
                if range_name in ("origin/main..HEAD", "HEAD..origin/main"):
                    return CommandResult(0, b"1\n" if self.local_commit != self.remote_commit else b"0\n")
                raise AssertionError(f"unexpected rev-list range: {range_name}")
            if args[:1] == ["show"]:
                key = args[1].split(":", 1)[1]
                if key not in self.remote_files:
                    return CommandResult(1, b"", b"path does not exist\n")
                return CommandResult(0, self.remote_files[key])
            raise AssertionError(f"unexpected git command: {command}")

        if "scripts/preflight.py" in command:
            return CommandResult(0 if self.preflight_ok else 1, b"preflight\n",
                                 b"failed\n" if not self.preflight_ok else b"")
        if "scripts/publish.py" in command:
            self.publisher_calls += 1
            if not self.publisher_ok:
                self.local_commit = "receipt-local"
                return CommandResult(1, b"", b"push rejected\n")
            for relative in ("state/routine_finalization.json", "state/runlog.json", "state/checkpoint_ack.json"):
                path = self.root / relative
                if path.exists():
                    self.remote_files[relative] = path.read_bytes()
            self.remote_commit = "receipt-commit"
            self.local_commit = self.remote_commit
            return CommandResult(0, b"published\n")
        raise AssertionError(f"unexpected command: {command}")


def _state(root: Path, path: str, default: object) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(default, indent=1), encoding="utf-8")


def _assert_no_ack_or_receipt(root: Path) -> None:
    assert not (root / "state/routine_finalization.json").exists()
    assert not (root / "state/checkpoint_ack.json").exists()
    assert json.loads((root / "state/runlog.json").read_text(encoding="utf-8")) == []


def _new_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix="henneth-finalization-")
    root = Path(temporary.name)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", str(root / "origin.git")],
        check=True,
        capture_output=True,
    )
    _state(root, "state/runlog.json", [])
    return temporary, root


def _finalize(env: FakeEnvironment, root: Path, *, routine: str = PM,
              outcome: str = "completed"):
    return finalize(routine=routine, started=STARTED, research_sha=SHA,
                    mode="light" if routine == PM else "full", outcome=outcome,
                    root=root, runner=env, clock=lambda: ENDED)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _real_runner(command: list[str] | tuple[str, ...], cwd: Path) -> CommandResult:
    result = subprocess.run(list(command), cwd=cwd, capture_output=True)
    return CommandResult(result.returncode, result.stdout or b"", result.stderr or b"")


def _seed_remote(base: Path, name: str) -> Path:
    remote = base / f"{name}.git"
    seed = base / f"{name}-seed"
    _git(base, "init", "-q", "--bare", str(remote))
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _state(seed, "state/runlog.json", [])
    scripts = seed / "scripts"
    scripts.mkdir()
    (scripts / "preflight.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (scripts / "publish.py").write_text(
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "root = Path(__file__).resolve().parent.parent\n"
        "subprocess.run(['git', 'add', 'state'], cwd=root, check=True)\n"
        "subprocess.run(['git', '-c', 'user.name=fixture', '-c',\n"
        "                'user.email=fixture@example.invalid', 'commit', '-m', sys.argv[1]],\n"
        "               cwd=root, check=True, capture_output=True)\n"
        "subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=root, check=True, capture_output=True)\n",
        encoding="utf-8",
    )
    _git(seed, "add", "state", "scripts")
    _git(seed, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-qm", "fixture base")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "-u", "origin", "main")
    _git(base, "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main")
    return remote


def _clone(base: Path, remote: Path, name: str) -> Path:
    clone = base / name
    _git(base, "clone", "-q", "-b", "main", str(remote), str(clone))
    return clone


def _hold_finalization_lane(root: str, ready, release) -> None:
    from finalize_routine import PublishLock

    with PublishLock(Path(root), timeout_s=2, poll_s=0.05,
                     task="finalization-check-holder", lane="finalization"):
        ready.set()
        release.wait(10)


def _contend_finalization_lane(root: str, result_queue) -> None:
    from finalize_routine import PublishLock, PublishLockBusy

    try:
        with PublishLock(Path(root), timeout_s=0.2, poll_s=0.05,
                         task="finalization-check-contender", lane="finalization"):
            result_queue.put("entered")
    except PublishLockBusy as exc:
        result_queue.put(str(exc))


def _same_checkout_finalize_worker(root: str, research_sha: str, started: str,
                                   ended: str, outcome: str, ready, release,
                                   invoked, result_queue, pause_publisher: bool) -> None:
    invoked.set()

    def runner(command: list[str] | tuple[str, ...], cwd: Path) -> CommandResult:
        if pause_publisher and "scripts/publish.py" in command:
            ready.set()
            if not release.wait(10):
                raise RuntimeError("same-checkout race release was not signaled")
        return _real_runner(command, cwd)

    result = finalize(
        routine=DAILY,
        started=started,
        research_sha=research_sha,
        mode="full",
        outcome=outcome,
        root=Path(root),
        runner=runner,
        clock=lambda: ended,
    )
    result_queue.put((outcome, result.success, result.status, result.message))


def _same_checkout_finalize_race_check() -> None:
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="henneth-finalization-same-checkout-") as name:
        base = Path(name)
        origin = _seed_remote(base, "same-checkout-origin")
        checkout = _clone(base, origin, "shared-checkout")
        research_sha = _git(checkout, "rev-parse", "HEAD")
        first_started = "2026-09-12T17:20:00+05:00"
        second_started = "2026-09-12T19:00:00+05:00"
        first_ready = context.Event()
        first_release = context.Event()
        second_invoked = context.Event()
        result_queue = context.Queue()
        first = context.Process(
            target=_same_checkout_finalize_worker,
            args=(str(checkout), research_sha, first_started, "2026-09-12T18:00:00+05:00",
                  "first same-checkout session", first_ready, first_release,
                  context.Event(), result_queue, True),
        )
        second = context.Process(
            target=_same_checkout_finalize_worker,
            args=(str(checkout), research_sha, second_started, "2026-09-12T19:01:00+05:00",
                  "second same-checkout session", context.Event(), context.Event(),
                  second_invoked, result_queue, False),
        )
        first.start()
        try:
            if not first_ready.wait(10):
                raise AssertionError("first same-checkout finalizer did not reach publisher")
            second.start()
            if not second_invoked.wait(10):
                raise AssertionError("second same-checkout finalizer did not enter finalize")
            first_release.set()
            first.join(20)
            second.join(20)
        finally:
            first_release.set()
            for process in (first, second):
                if process.is_alive():
                    process.terminate()
                    process.join(5)
        if first.exitcode != 0 or second.exitcode != 0:
            raise AssertionError(
                f"same-checkout finalizers exited with {first.exitcode} and {second.exitcode}"
            )
        results = [result_queue.get(timeout=2), result_queue.get(timeout=2)]
        if any(not result[1] or result[2] != "verified" for result in results):
            raise AssertionError(f"same-checkout finalization failed: {results}")
        receipts = json.loads(_git(checkout, "show", "origin/main:state/routine_finalization.json"))
        starts = {entry["started"] for entry in receipts}
        if {first_started, second_started} - starts:
            raise AssertionError("same-checkout race did not preserve both remote receipts")


def _finalization_lock_checks() -> None:
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="henneth-finalization-lock-") as name:
        base = Path(name)
        origin = _seed_remote(base, "finalization-origin")
        first = _clone(base, origin, "clone-a")
        second = _clone(base, origin, "clone-b")

        ready = context.Event()
        release = context.Event()
        holder = context.Process(target=_hold_finalization_lane,
                                 args=(str(first), ready, release))
        holder.start()
        try:
            if not ready.wait(5):
                raise AssertionError("finalization holder did not acquire its lane")
            result_queue = context.Queue()
            contender = context.Process(target=_contend_finalization_lane,
                                        args=(str(second), result_queue))
            contender.start()
            contender.join(5)
            if contender.exitcode != 0:
                raise AssertionError(f"finalization contender exited with {contender.exitcode}")
            result = result_queue.get(timeout=2)
            if "busy" not in result or "finalization-check-holder" not in result:
                raise AssertionError(f"unexpected finalization contention result: {result}")

            # A finalization holder must not prevent the nested standard
            # publisher lane: distinct lane files are the deadlock contract.
            from publish_lock import PublishLock
            with PublishLock(second, timeout_s=0.2, poll_s=0.05,
                             task="finalization-check-publisher"):
                pass
        finally:
            release.set()
            holder.join(5)
            if holder.is_alive():
                holder.terminate()
                holder.join(5)
        if holder.exitcode != 0:
            raise AssertionError(f"finalization holder exited with {holder.exitcode}")


def _cross_clone_stale_retry_check() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-finalization-retry-") as name:
        base = Path(name)
        origin = _seed_remote(base, "retry-origin")
        updater = _clone(base, origin, "clone-updater")
        second = _clone(base, origin, "clone-stale")

        # Advance origin outside the stale clone, then prove the stale clone
        # fails before any receipt/ack bytes are created.
        _git(updater, "fetch", "-q", "origin", "main")
        _git(updater, "merge", "--ff-only", "origin/main")
        _state(updater, "state/remote_marker.json", {"advanced": True})
        _git(updater, "add", "state/remote_marker.json")
        _git(updater, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
             "commit", "-qm", "advance origin")
        _git(updater, "push", "-q", "origin", "HEAD:main")
        research_sha = _git(updater, "rev-parse", "HEAD")
        stale_result = finalize(
            routine=DAILY, started=STARTED, research_sha=research_sha,
            mode="full", outcome="stale clone", root=second,
            runner=_real_runner, clock=lambda: ENDED,
        )
        if stale_result.success or not ("synchronized" in stale_result.message or "dirty" in stale_result.message):
            raise AssertionError(f"stale clone was not blocked: {stale_result}")
        if (second / "state/routine_finalization.json").exists():
            raise AssertionError("stale clone wrote a receipt before baseline verification")

        # Synchronize and retry with two distinct finalization sessions; the
        # remote history must retain both append-only entries.
        _git(second, "merge", "--ff-only", "origin/main")
        retry = finalize(
            routine=DAILY, started=STARTED, research_sha=research_sha,
            mode="full", outcome="synced retry", root=second,
            runner=_real_runner, clock=lambda: ENDED,
        )
        if not retry.success:
            raise AssertionError(f"synchronized retry failed: {retry}")

        other_started = "2026-09-12T19:00:00+05:00"
        _git(second, "fetch", "-q", "origin", "main")
        second_result = finalize(
            routine=PM, started=other_started, research_sha=research_sha,
            mode="light", outcome="second session", root=second,
            runner=_real_runner, clock=lambda: "2026-09-12T19:01:00+05:00",
        )
        if not second_result.success:
            raise AssertionError(f"second synced finalization failed: {second_result}")
        receipts = json.loads(_git(second, "show", "origin/main:state/routine_finalization.json"))
        starts = {(entry["routine"], entry["started"]) for entry in receipts}
        if {(DAILY, STARTED), (PM, other_started)} - starts:
            raise AssertionError("cross-clone synced retry did not preserve both receipts")


def _bare_git_end_to_end() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-finalization-bare-") as name:
        root = Path(name)
        bare = root / "origin.git"
        work = root / "work"
        subprocess.run(["git", "init", "--bare", str(bare)], check=True,
                       capture_output=True)
        work.mkdir()
        _git(work, "init")
        _git(work, "config", "user.email", "fixture@example.invalid")
        _git(work, "config", "user.name", "fixture")
        _state(work, "state/runlog.json", [])
        preflight = work / "scripts/preflight.py"
        publisher = work / "scripts/publish.py"
        preflight.parent.mkdir(parents=True, exist_ok=True)
        preflight.write_text("raise SystemExit(0)\n", encoding="utf-8")
        publisher.write_text(
            "import subprocess, sys\n"
            "from pathlib import Path\n"
            "root = Path(__file__).resolve().parent.parent\n"
            "subprocess.run(['git', 'add', 'state/routine_finalization.json', 'state/runlog.json', 'state/checkpoint_ack.json'], cwd=root, check=True)\n"
            "subprocess.run(['git', 'commit', '-m', sys.argv[1]], cwd=root, check=True, capture_output=True)\n"
            "subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=root, check=True, capture_output=True)\n",
            encoding="utf-8",
        )
        _git(work, "add", "state", "scripts")
        _git(work, "commit", "-m", "fixture base")
        _git(work, "remote", "add", "origin", str(bare))
        _git(work, "push", "origin", "HEAD:main")
        _git(work, "fetch", "origin", "main")

        _state(work, "state/research_marker.json", {"fixture": True})
        _git(work, "add", "state/research_marker.json")
        _git(work, "commit", "-m", "fixture research")
        _git(work, "push", "origin", "HEAD:main")
        _git(work, "fetch", "origin", "main")
        research_sha = _git(work, "rev-parse", "HEAD")

        result = finalize(
            routine=PM,
            started=STARTED,
            research_sha=research_sha,
            mode="light",
            outcome="company failed target review",
            root=work,
            runner=_real_runner,
            clock=lambda: ENDED,
        )
        assert result.success and result.status == "verified", result
        remote_receipts = json.loads(_git(bare, "show", "main:state/routine_finalization.json"))
        remote_log = json.loads(_git(bare, "show", "main:state/runlog.json"))
        remote_ack = json.loads(_git(bare, "show", "main:state/checkpoint_ack.json"))
        assert any(entry["routine"] == PM and entry["started"] == STARTED for entry in remote_receipts)
        assert any(entry["routine"] == PM and entry["started"] == STARTED for entry in remote_log)
        assert remote_ack["routine"] == PM and remote_ack["started"] == STARTED


def main() -> int:
    # 1. Research SHA is not remotely verified: no receipt, log, or PM ack.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root, research_ok=False)
        result = _finalize(env, root)
        assert not result.success and "research SHA" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 2. Current preflight fails: no PM acknowledgment is written.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root, preflight_ok=False)
        result = _finalize(env, root)
        assert not result.success and "preflight" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 3. A stale/behind baseline is blocked before any receipt or acknowledgment write.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        env.remote_commit = "remote-newer"
        result = _finalize(env, root)
        assert not result.success and "synchronized" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 4. A preexisting local-ahead baseline is blocked before any write.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        env.local_commit = "local-ahead"
        result = _finalize(env, root)
        assert not result.success and "synchronized" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 5. Publisher/push fails: pending local bytes do not become success.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root, publisher_ok=False)
        result = _finalize(env, root)
        assert not result.success and "publisher" in result.message
        assert (root / "state/routine_finalization.json").exists()
        assert (root / "state/checkpoint_ack.json").exists()
        assert env.remote_files == {}
    finally:
        temporary.cleanup()

    # 6. Successful publisher verifies matching entries and permits research prose
    # containing "failed" when it is not a status prefix.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        result = _finalize(env, root, outcome="company failed target review")
        assert result.success and result.status == "verified"
        assert result.remote_commit == "receipt-commit"
    finally:
        temporary.cleanup()

    # 7. Remote append-only history is retained even when the local fixture starts
    # without those newer rows.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        old_receipt = {"routine": DAILY, "started": "2026-09-11T17:20:00+05:00",
                       "research_sha": SHA, "mode": "full", "outcome": "old", "ended": ENDED}
        old_log = {"routine": DAILY, "started": old_receipt["started"], "research_sha": SHA,
                   "mode": "full", "outcome": "old", "ended": ENDED}
        env.remote_files["state/routine_finalization.json"] = json.dumps([old_receipt]).encode()
        env.remote_files["state/runlog.json"] = json.dumps([old_log]).encode()
        result = _finalize(env, root)
        assert result.success
        receipts = json.loads(env.remote_files["state/routine_finalization.json"])
        assert old_receipt in receipts and len(receipts) == 2
    finally:
        temporary.cleanup()

    # 8. Same-start retry validates matching remote entries only. A newer
    # unrelated receipt/log and a superseding PM ack must not un-finalize history.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        first = _finalize(env, root)
        assert first.success
        receipts = json.loads(env.remote_files["state/routine_finalization.json"])
        logs = json.loads(env.remote_files["state/runlog.json"])
        later_started = "2026-09-12T19:00:00+05:00"
        later_ended = "2026-09-12T19:01:00+05:00"
        later_ack = {"acked_at": later_ended, "by": "checkpoint-pm", "routine": PM,
                     "started": later_started, "research_sha": SHA}
        receipts.append({"routine": PM, "started": later_started, "research_sha": SHA,
                         "mode": "light", "outcome": "later", "ended": later_ended,
                         "ack_proof": later_ack})
        logs.append({"routine": PM, "started": later_started, "research_sha": SHA,
                     "mode": "light", "outcome": "later", "ended": later_ended})
        env.remote_files["state/routine_finalization.json"] = json.dumps(receipts).encode()
        env.remote_files["state/runlog.json"] = json.dumps(logs).encode()
        env.remote_files["state/checkpoint_ack.json"] = json.dumps(later_ack).encode()
        env.remote_commit = "newer-remote"
        env.local_commit = env.remote_commit
        second = _finalize(env, root)
        assert second.success and second.idempotent
        assert env.publisher_calls == 1
    finally:
        temporary.cleanup()

    # 9. A partial PM push with a missing or corrupt same-session ack is blocked.
    for corrupt in (False, True):
        temporary, root = _new_fixture()
        try:
            env = FakeEnvironment(root)
            first = _finalize(env, root)
            assert first.success
            if corrupt:
                env.remote_files["state/checkpoint_ack.json"] = json.dumps({
                    "acked_at": ENDED, "by": "checkpoint-pm", "routine": PM,
                    "started": STARTED, "research_sha": "f" * 40,
                }).encode()
            else:
                env.remote_files.pop("state/checkpoint_ack.json")
            retry = _finalize(env, root)
            assert not retry.success and "acknowledgment" in retry.message
            assert env.publisher_calls == 1
        finally:
            temporary.cleanup()

    # 10. An older PM run cannot overwrite a newer current acknowledgment.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        later_started = "2026-09-12T19:00:00+05:00"
        later_ended = "2026-09-12T19:01:00+05:00"
        later_ack = {"acked_at": later_ended, "by": "checkpoint-pm", "routine": PM,
                     "started": later_started, "research_sha": SHA}
        env.remote_files["state/routine_finalization.json"] = json.dumps([{
            "routine": PM, "started": later_started, "research_sha": SHA,
            "mode": "light", "outcome": "later", "ended": later_ended,
            "ack_proof": later_ack,
        }]).encode()
        env.remote_files["state/runlog.json"] = json.dumps([{
            "routine": PM, "started": later_started, "research_sha": SHA,
            "mode": "light", "outcome": "later", "ended": later_ended,
        }]).encode()
        env.remote_files["state/checkpoint_ack.json"] = json.dumps(later_ack).encode()
        result = _finalize(env, root)
        assert not result.success and "overwrite" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 11. A clock result before the caller's start cannot create a receipt.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        result = finalize(routine=PM, started=STARTED, research_sha=SHA, mode="light",
                          outcome="completed", root=root, runner=env,
                          clock=lambda: "2026-09-12T17:00:00+05:00")
        assert not result.success and "ended before it started" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 12. The production-shaped legacy ack is accepted as a historical clock:
    # a later first PM finalization replaces it with a fully identified ack.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        env.remote_files["state/checkpoint_ack.json"] = json.dumps({
            "acked_at": "2026-09-11T18:00:19+05:00", "by": "checkpoint-pm",
        }).encode()
        result = _finalize(env, root)
        assert result.success and env.publisher_calls == 1
        ack = json.loads(env.remote_files["state/checkpoint_ack.json"])
        assert ack["routine"] == PM and ack["started"] == STARTED and ack["research_sha"] == SHA
        receipt = json.loads(env.remote_files["state/routine_finalization.json"])[0]
        assert receipt["ack_proof"] == ack
    finally:
        temporary.cleanup()

    # 13. An older PM run cannot overwrite that legacy checkpoint clock.
    temporary, root = _new_fixture()
    try:
        env = FakeEnvironment(root)
        env.remote_files["state/checkpoint_ack.json"] = json.dumps({
            "acked_at": "2026-09-11T18:00:19+05:00", "by": "checkpoint-pm",
        }).encode()
        result = finalize(
            routine=PM,
            started="2026-09-11T17:00:00+05:00",
            research_sha=SHA,
            mode="light",
            outcome="completed",
            root=root,
            runner=env,
            clock=lambda: "2026-09-11T18:00:00+05:00",
        )
        assert not result.success and "legacy PM acknowledgment" in result.message
        _assert_no_ack_or_receipt(root)
        assert env.publisher_calls == 0
    finally:
        temporary.cleanup()

    # 14. Real temporary bare-Git transport and remote receipt proof.
    _bare_git_end_to_end()
    # 15. Cross-clone processes contend on the finalization lane; the standard
    # publisher lane remains independently acquirable (no nested deadlock).
    _finalization_lock_checks()
    # 16. Two real finalizers overlap in one checkout and both append safely.
    _same_checkout_finalize_race_check()
    # 17. A stale same-origin clone is blocked before writes, then a safe
    # fast-forward retry preserves append-only history.
    _cross_clone_stale_retry_check()

    print("routine finalization checks: OK (13 mocked scenarios + 1 bare-git end-to-end)")
    print("finalization lane concurrency: PASS - cross-clone contention, independent publisher lane, and same-checkout overlap verified")
    print("same-checkout finalizers: PASS - two real processes completed verified with both remote receipts")
    print("cross-clone stale retry: PASS - stale write blocked, fast-forward retry preserved both receipts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
