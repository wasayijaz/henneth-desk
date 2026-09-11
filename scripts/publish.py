#!/usr/bin/env python3
"""Publish local repository changes through the gated Git push path.

Every loop/task calls this instead of re-implementing git. It:
  1. acquires the shared cross-worktree repository push lane,
  2. runs the preflight gate (never publish a structurally broken cycle),
  3. stages Desk state/generated public data only (add --code for pre-staged code),
  4. commits + pushes ONLY if something actually changed,
  5. a push to `main` triggers eligible Git-linked Desk/marketing deploys.

Deterministic, zero tokens. Safe to call every run: a no-op when nothing changed.

Staging is scoped on purpose — the cloud cron and any number of interactive sessions
share one checkout, so a blanket stage publishes whoever else's half-finished edits are
lying around. Data refreshes stay automatic; shipping code stays deliberate.

Usage:
  python scripts/publish.py "Hourly desk refresh 11:20 PKT"          # state/ only
  git add dashboard/app.js docs/OPERATIONS.md                       # stage YOUR files by name
  python scripts/publish.py "Fix sizing bug" --code                  # ships only what you staged
  python scripts/publish.py                                          # timestamped default msg

--code ships ONLY hand-authored files already in the index when it runs — it never discovers
or `git add -A`s them itself. Stage your own files by name first (`git status --porcelain` to
confirm nothing else is dirty), then run with --code.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from publish_lock import PublishLock, PublishLockBusy, git_path

ROOT = Path(__file__).resolve().parent.parent

GENERATED = [
    "site/src/data/public/",
    "site/public/moon_ephem.bin",
]


def _is_auto(path: str) -> bool:
    """Return true only for ordinary generated Desk state/public extracts."""
    normalized = path.replace("\\", "/")
    return ((normalized.startswith("state/")
             and not normalized.startswith("state/company_intel/"))
            or any(normalized.startswith(generated) for generated in GENERATED))


def _run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def _git_running() -> bool:
    # `tasklist` exists only on Windows, but .github/workflows/desk-data.yml runs this same
    # script on ubuntu — there an unguarded call raises FileNotFoundError and takes the whole
    # cloud publish down whenever a stale .git/index.lock happens to exist. The cloud runner is
    # a fresh single-process checkout with no competing git, so "nothing is holding the lock"
    # is the correct answer there and the caller clears it.
    if not sys.platform.startswith("win"):
        return False
    r = _run(["tasklist", "/FI", "IMAGENAME eq git.exe"])
    # a real match adds a data row containing "git.exe"; no match prints "INFO: No tasks..."
    return "git.exe" in r.stdout


def _clear_stale_lock(retries=5, delay=2):
    """A leftover .git/index.lock (e.g. from a prior run interrupted mid-`git add`) makes
    every `git add` below fail silently, since nothing here checked their returncode — the
    index stays empty, `git diff --cached --quiet` sees nothing staged, and publish prints a
    false "no state change" even though state/ is genuinely dirty. Hit for real on 2026-08-27:
    a scheduled run reported NOTHING PUBLISHED while ~300 state/ files sat uncommitted.
    Fail loud instead: if a git process actually holds the lock, wait for it; if nothing does,
    the lock is stale — clear it and say so.
    """
    lock = git_path(ROOT, "index.lock")
    if not lock.exists():
        return
    for _ in range(retries):
        if not _git_running():
            break
        time.sleep(delay)
    else:
        print(f"publish: .git/index.lock present and a git process is still running after "
              f"{retries * delay}s — refusing to touch it. Wait for it to finish and re-run.")
        sys.exit(1)
    if lock.exists():
        try:
            lock.unlink()
        except OSError as e:
            print(f"publish: found stale .git/index.lock but could not remove it: {e}")
            sys.exit(1)
        print("publish: cleared a stale .git/index.lock (no git process was holding it) before staging.")


def _push_with_rebase() -> None:
    """Push, retrying only after a clean rebase and a fresh Desk preflight."""
    def _push():
        result = _run(["git", "push", "origin", "main"])
        return result.returncode == 0, (result.stderr or result.stdout or "").strip()

    def _preflight_after_rebase():
        result = _run([sys.executable, "scripts/preflight.py", "--desk"])
        print(result.stdout.strip()[-400:])
        if result.returncode != 0:
            print("publish: PREFLIGHT FAILED after rebase — not pushing.")
            raise SystemExit(1)

    ok, last_err = _push()
    if ok:
        return

    for attempt in range(3):
        fetch = _run(["git", "fetch", "origin", "main"])
        if fetch.returncode != 0:
            detail = (fetch.stderr or fetch.stdout or "").strip()
            print(f"publish: fetch failed — refusing to rebase or retry push: {detail[:400]}")
            raise SystemExit(1)
        rebase = _run(["git", "rebase", "origin/main"])
        if rebase.returncode != 0:
            conflicted = _run(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.splitlines()
            _run(["git", "rebase", "--abort"])
            print(f"publish: rebase conflict on {conflicted or ['unknown files']} — "
                  "refusing to choose either side. Manual merge needed: "
                  "git pull --rebase origin main, resolve by hand, re-run.")
            raise SystemExit(1)
        _preflight_after_rebase()
        ok, last_err = _push()
        if ok:
            return
        time.sleep(2 + attempt)

    print(f"publish: could not push after retries — last git error:\n{last_err[:400]}")
    raise SystemExit(1)


def _publish():
    # positional message only — otherwise `publish.py --code` would commit with the literal
    # message "--code"
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    msg = positional[0] if positional else f"Desk refresh {time.strftime('%Y-%m-%d %H:%M')}"

    _clear_stale_lock()

    # 1) Desk preflight gate.
    pf = _run([sys.executable, "scripts/preflight.py", "--desk"])
    print(pf.stdout.strip()[-400:])
    if pf.returncode != 0:
        print("publish: PREFLIGHT FAILED — not publishing (last-good site stays live).")
        sys.exit(1)

    # 2) stage — SCOPED. This used to be a blanket `git add -A`, which is the same mistake
    # the rebase logic below already refuses to make. Staging had no such care, so a
    # publish swept up whatever happened to be in the working tree.
    #
    # That is not just cosmetic. Multiple sessions and the cloud cron share this checkout.
    # On 2026-07-19 three commits carried work their message never mentioned — a Desk Room
    # commit shipped another session's in-progress dashboard/app.js and scripts/push_send.py.
    # Committing a file nobody has finished editing can publish broken code, and the message
    # gives no clue it happened.
    #
    # So: ordinary state/ (regenerated deterministic data) stages by default. The CI-private
    # subtree remains excluded even if a stale local routine recreates it.
    # Hand-authored files require --code — AND must already be staged by the caller (git add
    # <file> before running this). --code never calls `git add -A` itself: on 2026-07-26 it
    # still did, and a careful "stage only mine, confirm via git status --porcelain" run swept
    # up a concurrent session's unstaged, in-progress dashboard/app.js anyway. Pre-staging is
    # what makes the caller's own scoping the actual gate, not just a courtesy.
    code_mode = "--code" in sys.argv
    if code_mode:
        print("publish: --code — only files YOU already staged (git add <file>) ship as code. "
              "Dirty-but-unstaged hand-authored files are left alone (they may be someone else's).")
    add_state = _run([
        "git", "add", "-A", "--", "state/", ":(exclude)state/company_intel/**",
    ])
    if add_state.returncode != 0:
        print("publish: staging Desk state failed:\n" + (add_state.stderr or add_state.stdout)[:300])
        sys.exit(1)

    # GENERATED ARTEFACTS THAT LIVE OUTSIDE state/.
    # The marketing build is hermetic — it never reads state/ — so the pipeline hands it data by
    # writing these instead (scripts/build_astro_lite.py, scripts/build_public_slice.py). They are
    # regenerated deterministic output exactly like state/, not hand-authored code, so they belong
    # in the default publish rather than behind --code.
    #
    # Without this they were rewritten by every cycle and committed by none: the live astro page
    # would keep serving whatever sky was current the day it shipped, and both files would sit
    # permanently dirty, adding noise to the "hand-authored files" warning below until someone
    # swept them into an unrelated --code release.
    add_gen = _run(["git", "add", "-A", "--", *GENERATED])
    if add_gen.returncode != 0:
        print("publish: `git add -- GENERATED` failed:\n" + (add_gen.stderr or add_gen.stdout)[:300])
        sys.exit(1)

    # what else is dirty? split into files the CALLER already staged themselves (index status
    # is non-blank/non-'?') vs files that are merely dirty in the working tree. Only the former
    # are ever eligible to ship — see the 2026-07-26 incident note below.
    staged_hand, unstaged_hand = [], []
    for ln in _run(["git", "status", "--porcelain"]).stdout.splitlines():
        path = ln[3:].strip().strip('"')
        if not path or _is_auto(path):
            continue
        (staged_hand if ln[0] not in (" ", "?") else unstaged_hand).append(path)
    other = staged_hand + unstaged_hand

    if code_mode and unstaged_hand:
        print(f"publish: --code — leaving {len(unstaged_hand)} unstaged hand-authored file(s) OUT "
              f"(not staged by you, may belong to another session): {', '.join(unstaged_hand[:8])}"
              + (f" (+{len(unstaged_hand)-8} more)" if len(unstaged_hand) > 8 else ""))
        print("  If any of these are actually yours and ready, stage them yourself "
              "(git add <file>) and re-run.")

    if code_mode and staged_hand:
        # 2026-07-19 AND 2026-07-26: a blanket `git add -A` here re-discovered and staged
        # every dirty hand-authored file regardless of who owned it — including another
        # session's in-progress dashboard/app.js edit that its author had deliberately left
        # unstaged. `--code` now ships ONLY what the caller already staged themselves; it never
        # discovers files on its own. This is what lets "stage mine by name, run --code" actually
        # be a safety boundary instead of a false sense of one.
        print(f"publish: --code — committing {len(staged_hand)} pre-staged hand-authored file(s): "
              f"{', '.join(staged_hand[:8])}" + (f" (+{len(staged_hand)-8} more)" if len(staged_hand) > 8 else ""))
    elif not code_mode and other:
        # UNSTAGE them, don't just decline to add them. `git status --porcelain` reports files
        # that are already IN THE INDEX as well as merely modified ones, so a session that ran
        # `git add dashboard/app.js` mid-edit leaves it staged for whoever commits next — and
        # the commit below commits the whole index, not only what this run added. Without this
        # reset the warning prints "NOT committing ..." while committing exactly those files,
        # which is the 2026-07-19 incident this whole block exists to prevent.
        _run(["git", "reset", "--quiet", "--", *other])
        print(f"publish: NOT committing {len(other)} hand-authored file(s) — data-only publish.")
        for f in other[:12]:
            print(f"    · {f}")
        if len(other) > 12:
            print(f"    · (+{len(other)-12} more)")
        print("  These may belong to another session mid-edit. If they are YOURS and ready, "
              "re-run: python scripts/publish.py \"<msg>\" --code")

    # 3) commit only if there is something staged
    if _run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        if other:
            # loud, not silent: code changed but this was a data-only publish, so nothing shipped
            print("publish: no state change, and code changes were left unstaged — NOTHING PUBLISHED. "
                  "Re-run with --code if those edits are yours and ready to ship.")
            return
        print("publish: nothing changed — no deploy needed.")
        return

    c = _run(["git", "commit", "-m", msg])
    if c.returncode != 0:
        print("publish: commit failed:\n" + (c.stderr or c.stdout)[:300])
        sys.exit(1)

    # 4) push -> Vercel auto-deploys. RACE-SAFE: the cloud GitHub-Actions cron and the
    # app loops both push to main, so a push can be rejected (non-fast-forward) if the
    # other side pushed since our last pull. On rejection, rebase onto the latest origin.
    #
    # Never resolve a rebase conflict by choosing a side. State contains append-only and
    # hand-authored research records as well as generated data, so even an apparently harmless
    # state conflict can discard a real routine's work. A clean rebase changes the snapshot that
    # was checked before commit, therefore preflight must run again before the retry push.
    _push_with_rebase()
    print(f"publish: pushed '{msg}' -> eligible Desk/marketing Vercel projects may deploy.")


def main():
    task = (os.environ.get("HENNETH_AUTOMATION_ID")
            or os.environ.get("GITHUB_WORKFLOW")
            or "manual-publish")
    try:
        with PublishLock(ROOT, timeout_s=300, task=task) as lock:
            print(f"publish: acquired shared repository push lane in {lock.common_dir}")
            _publish()
    except PublishLockBusy as exc:
        print(f"publish: {exc}. Prepared work was left intact; retry after that publisher finishes.")
        sys.exit(1)


if __name__ == "__main__":
    main()
