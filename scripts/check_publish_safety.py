#!/usr/bin/env python3
"""Offline regression checks for the publisher's race and staging boundaries."""
from __future__ import annotations

import subprocess

import publish


PUBLISH_PUSH_COMMAND = ["git", "push", "origin", "HEAD:main"]


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def run_push_targets_current_head_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return completed(command)

    original_run = publish._run
    publish._run = fake_run
    try:
        publish._push_with_rebase()
    finally:
        publish._run = original_run

    assert calls == [PUBLISH_PUSH_COMMAND], "publisher must push the verified HEAD to main"


def run_local_ahead_no_change_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:2] == [publish.sys.executable, "scripts/preflight.py"]:
            return completed(command, stdout="preflight ok")
        if command == ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"]:
            return completed(command, stdout="0 1\n")
        return completed(command)

    original_run, original_argv, original_exit = publish._run, publish.sys.argv, publish.sys.exit
    publish._run = fake_run
    publish.sys.argv = ["publish.py"]
    publish.sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))
    try:
        try:
            publish._publish()
        except SystemExit as exc:
            assert exc.code == 1, "local-ahead no-change retry must fail closed"
        else:
            raise AssertionError("local-ahead no-change retry must not report success")
    finally:
        publish._run, publish.sys.argv, publish.sys.exit = original_run, original_argv, original_exit

    assert not any(command[:3] == ["git", "commit", "-m"] for command in calls)
    assert not any(command == PUBLISH_PUSH_COMMAND for command in calls)


def run_cached_diff_error_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:2] == [publish.sys.executable, "scripts/preflight.py"]:
            return completed(command, stdout="preflight ok")
        if command == ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"]:
            return completed(command, stdout="0 0\n")
        if command == ["git", "diff", "--cached", "--quiet"]:
            return completed(command, 2, stderr="index unavailable")
        if command[:3] == ["git", "commit", "-m"]:
            raise AssertionError("cached diff errors must stop before commit")
        return completed(command)

    original_run, original_argv, original_exit = publish._run, publish.sys.argv, publish.sys.exit
    publish._run = fake_run
    publish.sys.argv = ["publish.py"]
    publish.sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))
    try:
        try:
            publish._publish()
        except SystemExit as exc:
            assert exc.code == 1, "cached diff errors must fail closed"
        else:
            raise AssertionError("cached diff errors must not continue to commit")
    finally:
        publish._run, publish.sys.argv, publish.sys.exit = original_run, original_argv, original_exit

    assert not any(command[:3] == ["git", "commit", "-m"] for command in calls)


def run_unstage_failure_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command == ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"]:
            return completed(command, stdout="0 0\n")
        if command == ["git", "status", "--porcelain"]:
            return completed(command, stdout="M  dashboard/app.js\n")
        if command[:3] == ["git", "reset", "--quiet"]:
            return completed(command, 1, stderr="index unavailable")
        if command == ["git", "diff", "--cached", "--quiet"]:
            return completed(command, 1)
        return completed(command)

    original_run, original_argv = publish._run, publish.sys.argv
    publish._run = fake_run
    publish.sys.argv = ["publish.py"]
    try:
        try:
            publish._publish()
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("failed unstage must stop a data-only publish")
    finally:
        publish._run, publish.sys.argv = original_run, original_argv
    assert any(command[:3] == ["git", "reset", "--quiet"] for command in calls)
    assert not any(command[:2] in (["git", "commit"], ["git", "push"]) for command in calls)


def run_clean_rebase_case() -> None:
    calls = []
    push_results = iter([completed([], 1, stderr="non-fast-forward"), completed([], 0)])

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command == PUBLISH_PUSH_COMMAND:
            return next(push_results)
        if command[:3] == ["git", "rebase", "origin/main"]:
            return completed(command)
        if command[:2] == [publish.sys.executable, "scripts/preflight.py"]:
            return completed(command, stdout="preflight ok")
        return completed(command)

    original_run, original_sleep = publish._run, publish.time.sleep
    publish._run = fake_run
    publish.time.sleep = lambda _seconds: None
    try:
        publish._push_with_rebase()
    finally:
        publish._run, publish.time.sleep = original_run, original_sleep

    rebase_index = calls.index(["git", "rebase", "origin/main"])
    preflight_index = next(i for i, command in enumerate(calls) if command[:2] == [publish.sys.executable, "scripts/preflight.py"])
    push_indices = [i for i, command in enumerate(calls) if command == PUBLISH_PUSH_COMMAND]
    assert rebase_index < preflight_index < push_indices[-1], "clean rebase must re-preflight before retry push"
    assert not any(command[:3] == ["git", "checkout", "--theirs"] for command in calls), "publisher must not choose a rebase side"


def run_conflict_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command == PUBLISH_PUSH_COMMAND:
            return completed(command, 1, stderr="non-fast-forward")
        if command[:3] == ["git", "rebase", "origin/main"]:
            return completed(command, 1, stderr="conflict")
        if command[:4] == ["git", "diff", "--name-only", "--diff-filter=U"]:
            return completed(command, stdout="state/newslog.json\n")
        return completed(command)

    original_run = publish._run
    publish._run = fake_run
    try:
        try:
            publish._push_with_rebase()
        except SystemExit as exc:
            assert exc.code == 1, "conflict must fail the publisher"
        else:
            raise AssertionError("conflict must not be resolved automatically")
    finally:
        publish._run = original_run

    assert ["git", "rebase", "--abort"] in calls, "conflict must abort the rebase"
    assert not any(command[:3] == ["git", "checkout", "--theirs"] for command in calls), "conflict must not choose a side"
    assert not any(command[:2] == [publish.sys.executable, "scripts/preflight.py"] for command in calls), "failed rebase must not continue toward push"


def run_fetch_failure_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command == PUBLISH_PUSH_COMMAND:
            return completed(command, 1, stderr="non-fast-forward")
        if command[:4] == ["git", "fetch", "origin", "main"]:
            return completed(command, 1, stderr="network unavailable")
        return completed(command)

    original_run = publish._run
    publish._run = fake_run
    try:
        try:
            publish._push_with_rebase()
        except SystemExit as exc:
            assert exc.code == 1, "fetch failure must fail the publisher"
        else:
            raise AssertionError("fetch failure must not continue")
    finally:
        publish._run = original_run

    assert calls.count(PUBLISH_PUSH_COMMAND) == 1, "fetch failure must not retry push"
    assert not any(command[:3] == ["git", "rebase", "origin/main"] for command in calls), "fetch failure must not rebase"


def run_post_rebase_preflight_failure_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command == PUBLISH_PUSH_COMMAND:
            return completed(command, 1, stderr="non-fast-forward")
        if command[:2] == [publish.sys.executable, "scripts/preflight.py"]:
            return completed(command, 1, stdout="preflight failed")
        return completed(command)

    original_run = publish._run
    publish._run = fake_run
    try:
        try:
            publish._push_with_rebase()
        except SystemExit as exc:
            assert exc.code == 1, "post-rebase preflight failure must fail the publisher"
        else:
            raise AssertionError("post-rebase preflight failure must not continue")
    finally:
        publish._run = original_run

    assert calls.count(PUBLISH_PUSH_COMMAND) == 1, "failed post-rebase preflight must not retry push"
    assert ["git", "rebase", "origin/main"] in calls, "clean rebase must precede the post-rebase gate"


def run_staging_classification_case() -> None:
    assert publish._is_auto("state/quant.json")
    assert publish._is_auto("site/src/data/public/dashboard.json")
    ci_private = (
        "company_brief_receipts.json",
        "company_briefs.json",
        "company_documents.json",
        "company_event_ledger.json",
        "company_financial_series.json",
        "company_source_qa.json",
        "document_synthesis_queue.json",
    )
    for name in ci_private:
        assert not publish._is_auto(f"state/{name}"), f"recreated {name} must not auto-stage"
    assert not publish._is_auto("state/company_intel/source_registry.json")


def run_state_add_pathspec_case() -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return completed(command)

    original_run = publish._run
    publish._run = fake_run
    try:
        result = publish._run(publish._state_add_command())
    finally:
        publish._run = original_run

    assert result.returncode == 0
    assert calls == [publish._state_add_command()]
    assert calls[0][5:] == [
        ":(exclude)state/company_documents.json",
        ":(exclude)state/company_briefs.json",
        ":(exclude)state/company_brief_receipts.json",
        ":(exclude)state/company_event_ledger.json",
        ":(exclude)state/company_financial_series.json",
        ":(exclude)state/company_source_qa.json",
        ":(exclude)state/document_synthesis_queue.json",
        ":(exclude)state/company_intel/**",
    ]


def run_staged_private_path_case(path: str, code_mode: bool) -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:5] == ["git", "diff", "--cached", "--name-only", "-z"]:
            return completed(command, stdout=f"{path}\0")
        if command == ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"]:
            return completed(command, stdout="0 0\n")
        if command[:2] == [publish.sys.executable, "scripts/preflight.py"]:
            return completed(command, stdout="preflight ok")
        if command[:3] == ["git", "commit", "-m"]:
            raise AssertionError("CI-private staged state must be rejected before commit")
        return completed(command)

    original_run, original_argv, original_exit = publish._run, publish.sys.argv, publish.sys.exit
    publish._run = fake_run
    publish.sys.argv = ["publish.py"] + (["--code"] if code_mode else [])
    publish.sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))
    try:
        try:
            publish._publish()
        except SystemExit as exc:
            assert exc.code == 1, "CI-private staged state must fail closed"
        else:
            raise AssertionError("CI-private staged state must stop publication")
    finally:
        publish._run, publish.sys.argv, publish.sys.exit = original_run, original_argv, original_exit

    assert any(command[:5] == ["git", "diff", "--cached", "--name-only", "-z"] for command in calls)
    staged_check_index = next(
        i for i, command in enumerate(calls)
        if command[:5] == ["git", "diff", "--cached", "--name-only", "-z"]
    )
    status_indices = [i for i, command in enumerate(calls) if command[:2] == ["git", "status"]]
    assert not status_indices or staged_check_index < status_indices[0]
    assert not any(command[:3] == ["git", "commit", "-m"] for command in calls)


def run_staged_private_path_cases() -> None:
    for code_mode in (False, True):
        run_staged_private_path_case("state/company_documents.json", code_mode)
        run_staged_private_path_case("state/company_intel/source_registry.json", code_mode)


def main() -> None:
    run_push_targets_current_head_case()
    run_local_ahead_no_change_case()
    run_cached_diff_error_case()
    run_unstage_failure_case()
    run_clean_rebase_case()
    run_conflict_case()
    run_fetch_failure_case()
    run_post_rebase_preflight_failure_case()
    run_staging_classification_case()
    run_state_add_pathspec_case()
    run_staged_private_path_cases()
    print("publish safety self-test: OK")


if __name__ == "__main__":
    main()
