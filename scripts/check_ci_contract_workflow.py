#!/usr/bin/env python3
"""Offline structural check for the committed GitHub Actions CI contract.

This intentionally parses only the small YAML subset used by the workflow.  It
does not execute Actions, contact GitHub, or rely on a third-party YAML parser.
The check verifies that the workflow invokes the repository's real local gates
under Python 3.12; a successful check is not evidence of a live Actions run.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from typing import Any


CI_FIXED_POINT_BUILDERS = (
    "build_event_to_value_product_readiness.py",
    "build_ci_slice.py",
    "build_ci_artifact_integrity.py",
    "build_event_to_value_product_readiness.py",
    "build_ci_slice.py",
    "build_ci_artifact_integrity.py",
)


class WorkflowSyntaxError(ValueError):
    """Raised when the workflow is outside the deliberately supported subset."""


def _indent(line: str, line_no: int) -> int:
    if "\t" in line[: len(line) - len(line.lstrip())]:
        raise WorkflowSyntaxError(f"line {line_no}: tabs are not supported for indentation")
    return len(line) - len(line.lstrip(" "))


def _scalar(raw: str, line_no: int) -> Any:
    raw = raw.strip()
    if raw in ("", "null", "~"):
        return None
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    if raw.startswith(("'", '"')):
        try:
            return ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise WorkflowSyntaxError(f"line {line_no}: invalid quoted scalar") from exc
    if raw.startswith("[") or raw.startswith("{"):
        try:
            return ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise WorkflowSyntaxError(f"line {line_no}: invalid inline scalar") from exc
    return raw


def _key_value(text: str, line_no: int) -> tuple[str, str]:
    if ":" not in text:
        raise WorkflowSyntaxError(f"line {line_no}: expected 'key: value'")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise WorkflowSyntaxError(f"line {line_no}: empty mapping key")
    return key, value.strip()


def parse_workflow(text: str) -> dict[str, Any]:
    """Parse the workflow's YAML subset into ordinary Python containers."""
    raw_lines = text.splitlines()
    lines: list[tuple[int, int, str]] = []
    for number, raw in enumerate(raw_lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise WorkflowSyntaxError(f"line {number}: tabs are not supported for indentation")
        lines.append((_indent(raw, number), number, raw.lstrip(" ")))
    if not lines:
        raise WorkflowSyntaxError("workflow is empty")

    def block(pos: int, wanted: int) -> tuple[Any, int]:
        if pos >= len(lines):
            raise WorkflowSyntaxError("expected an indented block")
        actual, number, content = lines[pos]
        if actual != wanted:
            raise WorkflowSyntaxError(f"line {number}: expected indentation {wanted}, found {actual}")
        is_list = content.startswith("-")
        result: Any = [] if is_list else {}
        while pos < len(lines):
            current, number, content = lines[pos]
            if current < wanted:
                break
            if current > wanted:
                raise WorkflowSyntaxError(f"line {number}: unexpected indentation {current} (expected {wanted})")
            if is_list:
                if not content.startswith("-"):
                    raise WorkflowSyntaxError(f"line {number}: mixed mapping and list entries")
                item = content[1:].strip()
                if not item:
                    if pos + 1 >= len(lines) or lines[pos + 1][0] <= wanted:
                        raise WorkflowSyntaxError(f"line {number}: empty list item")
                    value, pos = block(pos + 1, lines[pos + 1][0])
                    result.append(value)
                    continue
                if ":" not in item:
                    result.append(_scalar(item, number))
                    pos += 1
                    continue
                key, value_text = _key_value(item, number)
                item_map: dict[str, Any] = {}
                if value_text == "|":
                    value, pos = block_scalar(pos + 1, wanted)
                elif value_text:
                    value, pos = _scalar(value_text, number), pos + 1
                else:
                    if pos + 1 < len(lines) and lines[pos + 1][0] > wanted:
                        value, pos = block(pos + 1, lines[pos + 1][0])
                    else:
                        value, pos = None, pos + 1
                item_map[key] = value
                if pos < len(lines) and lines[pos][0] > wanted:
                    extra, pos = block(pos, lines[pos][0])
                    if not isinstance(extra, dict):
                        raise WorkflowSyntaxError(f"line {lines[pos - 1][1]}: list mapping continuation must be a mapping")
                    item_map.update(extra)
                result.append(item_map)
            else:
                if content.startswith("-"):
                    raise WorkflowSyntaxError(f"line {number}: list entry in mapping block")
                key, value_text = _key_value(content, number)
                if key in result:
                    raise WorkflowSyntaxError(f"line {number}: duplicate key '{key}'")
                if value_text == "|":
                    value, pos = block_scalar(pos + 1, wanted)
                elif value_text:
                    value, pos = _scalar(value_text, number), pos + 1
                elif pos + 1 < len(lines) and lines[pos + 1][0] > wanted:
                    value, pos = block(pos + 1, lines[pos + 1][0])
                else:
                    value, pos = None, pos + 1
                result[key] = value
        return result, pos

    def block_scalar(pos: int, parent_indent: int) -> tuple[str, int]:
        if pos >= len(lines) or lines[pos][0] <= parent_indent:
            return "", pos
        base = lines[pos][0]
        collected: list[str] = []
        while pos < len(lines) and lines[pos][0] > parent_indent:
            ind, number, content = lines[pos]
            if ind < base:
                raise WorkflowSyntaxError(f"line {number}: inconsistent block-scalar indentation")
            collected.append(" " * (ind - base) + content)
            pos += 1
        return "\n".join(collected) + "\n", pos

    root, end = block(0, lines[0][0])
    if end != len(lines) or not isinstance(root, dict):
        raise WorkflowSyntaxError("workflow root must be a mapping")
    return root


def _ordered_subsequence(names: list[str], required: tuple[str, ...]) -> bool:
    position = -1
    for required_name in required:
        try:
            position = names.index(required_name, position + 1)
        except ValueError:
            return False
    return True


def _fixed_point_order_errors(names: list[str], *, label: str) -> list[str]:
    errors: list[str] = []
    for required_name in set(CI_FIXED_POINT_BUILDERS):
        expected_count = CI_FIXED_POINT_BUILDERS.count(required_name)
        actual_count = names.count(required_name)
        if actual_count != expected_count:
            errors.append(f"{label}: {required_name} must run {expected_count} times in the readiness/slice/integrity fixed-point sequence")
    if not _ordered_subsequence(names, CI_FIXED_POINT_BUILDERS):
        errors.append(f"{label}: readiness, CI slice, and artifact integrity must run as a two-pass fixed-point sequence")
    if names and names[-1] != "build_ci_artifact_integrity.py":
        errors.append(f"{label}: the final CI artifact producer must be build_ci_artifact_integrity.py")
    return errors


def validate_run_cloud_steps(steps: list[str] | tuple[str, ...]) -> list[str]:
    names = [str(step).strip() for step in steps]
    errors: list[str] = []
    try:
        completion_index = len(names) - 1 - names[::-1].index("build_ci_completion_matrix.py")
        archive_index = names.index("supabase_ci_store.py", completion_index + 1)
        producer_tail = names[completion_index + 1 : archive_index]
        errors.extend(_fixed_point_order_errors(producer_tail, label="run_cloud.STEPS"))
        first_readiness_index = names.index("build_event_to_value_product_readiness.py")
        if first_readiness_index < completion_index:
            errors.append("run_cloud.STEPS: Event-to-Value product readiness must run after the completion matrix")
    except ValueError:
        errors.append("run_cloud.STEPS: missing completion matrix, fixed-point builders, or CI archive seam")
    return errors


def validate_workflow(workflow: dict[str, Any]) -> list[str]:
    """Return deterministic, human-readable contract violations."""
    errors: list[str] = []
    triggers = workflow.get("on")
    if not isinstance(triggers, dict) or "pull_request" not in triggers:
        errors.append("on: pull_request trigger is required")
    push = triggers.get("push") if isinstance(triggers, dict) else None
    branches = push.get("branches") if isinstance(push, dict) else None
    if not isinstance(branches, list) or "main" not in branches:
        errors.append("on.push.branches: main trigger is required")
    permissions = workflow.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        errors.append("permissions.contents: must be read")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return ["jobs: missing mapping"]
    validate = jobs.get("validate")
    if not isinstance(validate, dict):
        return ["jobs.validate: missing job mapping"]
    if validate.get("runs-on") != "ubuntu-latest":
        errors.append("jobs.validate.runs-on: must be ubuntu-latest")
    steps = validate.get("steps")
    if not isinstance(steps, list):
        return errors + ["jobs.validate.steps: missing list"]
    named = {step.get("name"): step for step in steps if isinstance(step, dict) and step.get("name")}
    if not any(isinstance(step, dict) and step.get("uses") == "actions/checkout@v4" for step in steps):
        errors.append("steps: missing actions/checkout@v4")
    setup = next((s for s in steps if isinstance(s, dict) and s.get("uses") == "actions/setup-python@v5"), None)
    if setup is None:
        errors.append("steps: missing actions/setup-python@v5")
    elif not isinstance(setup.get("with"), dict) or str(setup["with"].get("python-version")) != "3.12":
        errors.append("setup-python: with.python-version must be 3.12")
    install = named.get("Install Python requirements")
    if not install or "python -m pip install -r requirements.txt" not in str(install.get("run", "")):
        errors.append("steps: missing Python requirements install gate")
    syntax = named.get("Python syntax")
    if not syntax or "python -m compileall -q scripts" not in str(syntax.get("run", "")):
        errors.append("steps: missing Python compileall gate")
    cutoff = named.get("Set CI build cutoff")
    cutoff_run = str(cutoff.get("run", "")) if cutoff else ""
    if not cutoff or "HENNETH_CI_BUILD_CUTOFF_AT" not in cutoff_run or "date -u" not in cutoff_run:
        errors.append("steps: CI build must set one explicit UTC HENNETH_CI_BUILD_CUTOFF_AT")
    js = named.get("JavaScript syntax")
    js_run = str(js.get("run", "")) if js else ""
    if not js or "subprocess.run" not in js_run or '"node", "-c"' not in js_run:
        errors.append("steps: JavaScript syntax gate must invoke node -c through subprocess")
    preflight = named.get("Preflight gate")
    if not preflight or "python scripts/preflight.py" not in str(preflight.get("run", "")):
        errors.append("steps: missing preflight gate")
    ci_build = named.get("Build generated Company Intelligence artifacts")
    ci_build_run = str(ci_build.get("run", "")) if ci_build else ""
    if not ci_build:
        errors.append("steps: missing generated Company Intelligence artifact build")
    else:
        ci_build_names = [
            line.removeprefix("python scripts/")
            for line in (line.strip() for line in ci_build_run.splitlines())
            if line.startswith("python scripts/")
        ]
        required_ci_builders = (
            "python scripts/build_financial_evidence_reconciliation.py",
            "python scripts/build_financial_truth_qualification.py",
            "python scripts/build_formal_financial_engines.py",
            "python scripts/build_company_brains.py",
            "python scripts/build_ci_completion_matrix.py",
            "python scripts/build_ci_slice.py",
            "python scripts/build_ci_artifact_integrity.py",
        )
        for command in required_ci_builders:
            if command not in ci_build_run:
                errors.append(f"steps: CI artifact build missing {command}")
        order_pairs = (
            (
                "python scripts/build_financial_evidence_reconciliation.py",
                "python scripts/build_financial_truth_qualification.py",
                "steps: financial truth qualification must be rebuilt after financial evidence reconciliation",
            ),
            (
                "python scripts/build_financial_truth_qualification.py",
                "python scripts/build_formal_financial_engines.py",
                "steps: formal financial engines must be rebuilt after financial truth qualification",
            ),
            (
                "python scripts/build_formal_financial_engines.py",
                "python scripts/build_company_brains.py",
                "steps: Company Brain must be rebuilt after formal financial engines",
            ),
            (
                "python scripts/build_company_brains.py",
                "python scripts/build_ci_completion_matrix.py",
                "steps: completion matrix must be rebuilt after Company Brain",
            ),
        )
        for before, after, message in order_pairs:
            if before in ci_build_run and after in ci_build_run and ci_build_run.find(before) > ci_build_run.find(after):
                errors.append(message)
        if (
            "python scripts/build_ci_completion_matrix.py" in ci_build_run
            and "python scripts/build_ci_slice.py" in ci_build_run
            and ci_build_run.rfind("python scripts/build_ci_completion_matrix.py")
            > ci_build_run.rfind("python scripts/build_ci_slice.py")
        ):
            errors.append("steps: CI slice must be rebuilt after completion matrix")
        if (
            "python scripts/build_ci_slice.py" in ci_build_run
            and "python scripts/build_ci_artifact_integrity.py" in ci_build_run
            and ci_build_run.rfind("python scripts/build_ci_slice.py")
            > ci_build_run.rfind("python scripts/build_ci_artifact_integrity.py")
        ):
            errors.append("steps: CI artifact integrity must run after the final CI slice build")
        errors.extend(_fixed_point_order_errors(ci_build_names[-len(CI_FIXED_POINT_BUILDERS):], label="steps: CI artifact build"))
    aggregate = named.get("Company Intelligence product contract aggregate")
    if not aggregate or "python scripts/check_ci_product_contracts.py" not in str(aggregate.get("run", "")):
        errors.append("steps: missing Company Intelligence product contract aggregate")
    integrity_check = named.get("Verify finalized artifacts match this commit")
    integrity_check_run = str(integrity_check.get("run", "")) if integrity_check else ""
    if not integrity_check or "python scripts/check_ci_artifact_integrity.py" not in integrity_check_run:
        errors.append("steps: missing exact-commit artifact-integrity verification after finalization")
    if setup is not None:
        setup_index = steps.index(setup)
        for label in (
            "Install Python requirements",
            "Python syntax",
            "Set CI build cutoff",
            "JavaScript syntax",
            "Build generated Company Intelligence artifacts",
            "Verify finalized artifacts match this commit",
            "Company Intelligence product contract aggregate",
            "Preflight gate",
        ):
            step = named.get(label)
            if step is not None and steps.index(step) < setup_index:
                errors.append(f"steps: {label} runs before Python 3.12 setup")
    ci_build_index = steps.index(ci_build) if ci_build in steps else None
    integrity_check_index = steps.index(integrity_check) if integrity_check in steps else None
    aggregate_index = steps.index(aggregate) if aggregate in steps else None
    preflight_index = steps.index(preflight) if preflight in steps else None
    if ci_build_index is not None and integrity_check_index is not None and integrity_check_index < ci_build_index:
        errors.append("steps: artifact-integrity verification runs before CI artifact finalization")
    if integrity_check_index is not None and aggregate_index is not None and aggregate_index < integrity_check_index:
        errors.append("steps: product contract aggregate runs before exact-commit artifact verification")
    if ci_build_index is not None and aggregate_index is not None and aggregate_index < ci_build_index:
        errors.append("steps: product contract aggregate runs before CI artifact build")
    if aggregate_index is not None and preflight_index is not None and preflight_index < aggregate_index:
        errors.append("steps: preflight runs before Company Intelligence product contract aggregate")
    return errors


VALID_FIXTURE = """name: fixture
on:
  pull_request:
  push:
    branches:
      - main
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: \"3.12\"
      - name: Install Python requirements
        run: python -m pip install -r requirements.txt
      - name: Python syntax
        run: python -m compileall -q scripts
      - name: Set CI build cutoff
        run: echo "HENNETH_CI_BUILD_CUTOFF_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_ENV"
      - name: JavaScript syntax
        run: |
          subprocess.run([\"node\", \"-c\", str(path)], check=True)
      - name: Build generated Company Intelligence artifacts
        run: |
          python scripts/build_financial_evidence_reconciliation.py
          python scripts/build_financial_truth_qualification.py
          python scripts/build_formal_financial_engines.py
          python scripts/build_company_brains.py
          python scripts/build_ci_completion_matrix.py
          python scripts/build_ci_slice.py
          python scripts/build_ci_artifact_integrity.py
          python scripts/build_event_to_value_product_readiness.py
          python scripts/build_ci_slice.py
          python scripts/build_ci_artifact_integrity.py
      - name: Verify finalized artifacts match this commit
        run: python scripts/check_ci_artifact_integrity.py
      - name: Company Intelligence product contract aggregate
        run: python scripts/check_ci_product_contracts.py
      - name: Preflight gate
        run: python scripts/preflight.py
"""


def self_test() -> int:
    if validate_workflow(parse_workflow(VALID_FIXTURE)):
        print("self-test failed: valid fixture rejected")
        return 1
    valid_run_cloud_tail = [
        "build_ci_completion_matrix.py",
        *CI_FIXED_POINT_BUILDERS,
        "supabase_ci_store.py",
    ]
    if validate_run_cloud_steps(valid_run_cloud_tail):
        print("self-test failed: valid run_cloud fixed-point tail rejected")
        return 1
    one_pass_run_cloud_tail = [
        "build_ci_completion_matrix.py",
        "build_event_to_value_product_readiness.py",
        "build_ci_slice.py",
        "build_ci_artifact_integrity.py",
        "supabase_ci_store.py",
    ]
    errors = validate_run_cloud_steps(one_pass_run_cloud_tail)
    if not any("fixed-point" in error or "must run 2 times" in error for error in errors):
        print("self-test failed: one-pass run_cloud tail was accepted")
        return 1
    broken = VALID_FIXTURE.replace('python-version: "3.12"', 'python-version: "3.11"')
    errors = validate_workflow(parse_workflow(broken))
    if not any("python-version" in error for error in errors):
        print("self-test failed: invalid fixture was accepted")
        return 1
    missing_cutoff = VALID_FIXTURE.replace(
        '      - name: Set CI build cutoff\n        run: echo "HENNETH_CI_BUILD_CUTOFF_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_ENV"\n',
        "",
    )
    errors = validate_workflow(parse_workflow(missing_cutoff))
    if not any("explicit UTC" in error for error in errors):
        print("self-test failed: missing build cutoff was accepted")
        return 1
    stale_financial_order = VALID_FIXTURE.replace(
        "          python scripts/build_financial_truth_qualification.py\n"
        "          python scripts/build_formal_financial_engines.py\n",
        "          python scripts/build_formal_financial_engines.py\n"
        "          python scripts/build_financial_truth_qualification.py\n",
    )
    errors = validate_workflow(parse_workflow(stale_financial_order))
    if not any("formal financial engines" in error for error in errors):
        print("self-test failed: stale financial engine order was accepted")
        return 1
    stale_brain_order = VALID_FIXTURE.replace(
        "          python scripts/build_formal_financial_engines.py\n"
        "          python scripts/build_company_brains.py\n",
        "          python scripts/build_company_brains.py\n"
        "          python scripts/build_formal_financial_engines.py\n",
    )
    errors = validate_workflow(parse_workflow(stale_brain_order))
    if not any("Company Brain" in error for error in errors):
        print("self-test failed: stale Company Brain order was accepted")
        return 1
    print("self-test: ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run offline parser/validator fixtures")
    parser.add_argument("--workflow", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = args.workflow or os.path.join(root, ".github", "workflows", "ci-contract.yml")
    try:
        with open(path, encoding="utf-8") as handle:
            workflow = parse_workflow(handle.read())
        errors = validate_workflow(workflow)
        try:
            from run_cloud import STEPS as RUN_CLOUD_STEPS
        except Exception as exc:  # noqa: BLE001 - static checker should explain import failures
            errors.append(f"run_cloud.STEPS: could not import ordered list: {exc}")
        else:
            errors.extend(validate_run_cloud_steps(RUN_CLOUD_STEPS))
    except (OSError, WorkflowSyntaxError) as exc:
        print(f"CI contract workflow check: FAIL — {exc}")
        return 1
    if errors:
        print("CI contract workflow check: FAIL")
        for error in errors:
            print(f"  x {error}")
        return 1
    print("CI contract workflow check: OK (structural only; no live run performed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
