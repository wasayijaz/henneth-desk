"""Strict contract for the MLCF/PIOC acquisition-control case-run envelope.

This module deliberately owns no state I/O.  It validates the narrow envelope
emitted by :mod:`mlcf_pioc_case_run_adapter` and delegates economic scenario
validation to the existing cement expansion contract.  A blocked run carries
identity and provenance only; no partial economic values are accepted.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Mapping

import cement_expansion_contract as cement

CASE_ID = "case_mlcf_pioc_control_observed_v1"
SCENARIOS = ("bear", "base", "bull")
ENVELOPE_KEYS = {
    "status",
    "case_id",
    "scenario_runs",
    "blocked_reasons",
    "input_lineage",
    "analogue_readiness",
    "formal_output_readiness",
}
RUN_KEYS = {"scenario", "status", "blocked_reasons", "result"}
READINESS_KEYS = {"status", "blocked_reasons", "hard_block", "reason"}

_ADVICE_RE = re.compile(
    r"\b(?:buy|sell|accumulate|recommend(?:ation)?|you\s+should)\b|"
    r"\btarget\s+price\b|\bprice\s+target\b",
    flags=re.IGNORECASE,
)
_LEAK_KEYS = {"target_price", "price_target", "targetPrice", "priceTarget"}


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _scan_leaks(value: Any, path: str = "$") -> list[str]:
    """Return advice/target-price/non-finite violations in arbitrary JSON."""
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in _LEAK_KEYS or _ADVICE_RE.search(key_text):
                violations.append(f"{path}.{key_text}: advice or target-price field is forbidden")
            violations.extend(_scan_leaks(item, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(_scan_leaks(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _ADVICE_RE.search(value):
        violations.append(f"{path}: advice or target-price language is forbidden")
    elif isinstance(value, float) and not math.isfinite(value):
        violations.append(f"{path}: value must be finite")
    return violations


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_scenario_case(case: Mapping[str, Any]) -> list[str]:
    """Validate one economic scenario, including exact case identity."""
    if not isinstance(case, Mapping):
        return ["scenario case: must be a mapping"]
    violations: list[str] = []
    if case.get("case_id") != CASE_ID:
        violations.append(f"case_id: must equal {CASE_ID}")
    if case.get("case_label") not in SCENARIOS:
        violations.append("case_label: must be one of bear, base, bull")
    violations.extend(cement.validate_case(case))
    violations.extend(_scan_leaks(case))
    return sorted(set(violations))


def _lineage_valid(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, Mapping):
            return False
        # Every lineage item must identify a retained source or an explicit
        # analyst note.  Numeric economic values are intentionally optional.
        label = item.get("label_type")
        if label == "source":
            ref = item.get("source_ref")
            if not isinstance(ref, Mapping) or not str(ref.get("id", "")).strip():
                return False
        elif label == "analyst":
            ref = item.get("analyst_ref")
            if not isinstance(ref, Mapping) or not str(ref.get("note_id", "")).strip():
                return False
        elif item.get("kind") == "evidence":
            if not str(item.get("document_id", "")).strip():
                return False
        else:
            return False
    return True


def validate_case_run(envelope: Mapping[str, Any]) -> list[str]:
    """Return deterministic named violations; an empty list means valid."""
    if not isinstance(envelope, Mapping):
        return ["envelope: must be a mapping"]
    violations: list[str] = []
    unknown = set(envelope) - ENVELOPE_KEYS
    violations.extend(f"{key}: unknown envelope field" for key in sorted(unknown, key=str))
    if envelope.get("case_id") != CASE_ID:
        violations.append(f"case_id: must equal {CASE_ID}")
    status = envelope.get("status")
    if status not in {"blocked", "computed"}:
        violations.append("status: must be blocked or computed")
    reasons = envelope.get("blocked_reasons")
    if not isinstance(reasons, list) or any(not isinstance(row, str) or not row.strip() for row in reasons):
        violations.append("blocked_reasons: must be a list of non-empty strings")
    elif reasons != sorted(set(reasons)):
        violations.append("blocked_reasons: must be sorted and deduplicated")
    if not _lineage_valid(envelope.get("input_lineage")):
        violations.append("input_lineage: must contain source/analyst/evidence lineage")

    runs = envelope.get("scenario_runs")
    if not isinstance(runs, list):
        violations.append("scenario_runs: must be a list")
        runs = []
    elif status == "computed" and len(runs) != 3:
        violations.append("scenario_runs: computed envelope must contain exactly bear, base and bull")
    elif status == "blocked" and runs:
        violations.append("scenario_runs: blocked envelope must contain no scenario objects")
    labels: list[str] = []
    for index, run in enumerate(runs):
        path = f"scenario_runs[{index}]"
        if not isinstance(run, Mapping):
            violations.append(f"{path}: must be a mapping")
            continue
        labels.append(str(run.get("scenario")))
        violations.extend(f"{path}.{key}: unknown field" for key in sorted(set(run) - RUN_KEYS, key=str))
        if run.get("scenario") not in SCENARIOS:
            violations.append(f"{path}.scenario: must be one of bear, base, bull")
        run_status = run.get("status")
        if run_status not in {"blocked", "computed"}:
            violations.append(f"{path}.status: must be blocked or computed")
        run_reasons = run.get("blocked_reasons")
        if not isinstance(run_reasons, list) or any(not isinstance(row, str) or not row.strip() for row in run_reasons):
            violations.append(f"{path}.blocked_reasons: must be a list of non-empty strings")
        elif run_reasons != sorted(set(run_reasons)):
            violations.append(f"{path}.blocked_reasons: must be sorted and deduplicated")
        if run_status == "blocked":
            if "result" in run:
                violations.append(f"{path}: blocked run cannot carry result values")
            if not run_reasons:
                violations.append(f"{path}: blocked run requires a reason")
        elif not isinstance(run.get("result"), Mapping):
            violations.append(f"{path}.result: computed run requires an engine result")
        elif run_reasons:
            violations.append(f"{path}: computed run cannot carry blocked reasons")
        elif run["result"].get("status") != "computed":
            violations.append(f"{path}.result.status: must be computed")

    if status == "computed" and labels != list(SCENARIOS):
        violations.append("scenario_runs: labels must be exactly bear, base, bull")
    if status == "blocked" and any(isinstance(run, Mapping) and run.get("status") == "computed" for run in runs):
        violations.append("status: blocked envelope cannot contain computed scenarios")
    if status == "computed" and any(isinstance(run, Mapping) and run.get("status") != "computed" for run in runs):
        violations.append("status: computed envelope requires three computed scenarios")
    for field in ("analogue_readiness", "formal_output_readiness"):
        value = envelope.get(field)
        if not isinstance(value, Mapping):
            violations.append(f"{field}: must be a mapping")
        else:
            violations.extend(f"{field}.{key}: unknown field" for key in sorted(set(value) - READINESS_KEYS, key=str))
            if value.get("status") not in {"blocked", "ready", "not_ready"}:
                violations.append(f"{field}.status: invalid readiness status")
            if "blocked_reasons" in value and (not isinstance(value["blocked_reasons"], list) or any(not isinstance(x, str) for x in value["blocked_reasons"])):
                violations.append(f"{field}.blocked_reasons: must be a list of strings")
    violations.extend(_scan_leaks(envelope))
    return sorted(set(violations))


def numeric_output_keys(value: Any, path: str = "$") -> list[str]:
    """Find numeric economic payloads; blocked runs use this as a safety check."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"values", "per_share", "quarterly_schedule", "break_even"} and item not in (None, [], {}):
                found.append(f"{path}.{key}")
            found.extend(numeric_output_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(numeric_output_keys(item, f"{path}[{index}]"))
    return found
