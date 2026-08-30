"""Focused checks for the blocked MLCF financial-truth gap contract."""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from mlcf_financial_truth_gap_contract import (
    BLOCKER,
    CASE_SCHEMA,
    CONTRACT_VERSION,
    FACT_EVIDENCE_MISSING,
    IMMUTABLE_PUBLICATION_AUTHORITY_UNAVAILABLE,
    MISSING_COUNTERPART,
    RAW_BYTES_MISSING,
    RETAINED_MLCF_DOCUMENT_IDS,
    RETAINED_MLCF_PUBLICATION_AUTHORITY,
    build_case_from_retained_state,
    evaluate_case,
    validate_case,
)


def build_case(states: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
    states = states or _load_states()
    return build_case_from_retained_state(
        states["financial_truth"],
        states["company_documents"],
        states["review_manifest"],
        states["research_index"],
        states["reconciliation"],
        as_of_date="2026-08-31",
    )


def _assert_reject(case: dict[str, object], checks: list[str], label: str) -> None:
    try:
        evaluate_case(case, retained_state=_load_states())
    except ValueError:
        checks.append(label)
        return
    raise AssertionError(f"adversarial case was accepted: {label}")


def _assert_source_reject(states: dict[str, dict[str, object]], checks: list[str], label: str) -> None:
    try:
        build_case_from_retained_state(
            states["financial_truth"],
            states["company_documents"],
            states["review_manifest"],
            states["research_index"],
            states["reconciliation"],
            as_of_date="2026-08-31",
        )
    except ValueError:
        checks.append(label)
        return
    raise AssertionError(f"source drift was accepted: {label}")


def _assert_source_accept(states: dict[str, dict[str, object]], checks: list[str], label: str) -> None:
    case = build_case(states)
    evaluate_case(case, retained_state=states)
    checks.append(label)


def _load_states() -> dict[str, dict[str, object]]:
    root = Path(__file__).resolve().parents[1]
    paths = {
        "financial_truth": "state/company_intel/financial_truth_qualification.json",
        "company_documents": "state/company_documents.json",
        "review_manifest": "config/ci_reprocess_review_manifest.json",
        "research_index": "state/research_index.json",
        "reconciliation": "state/company_intel/financial_evidence_reconciliation.json",
    }
    return {key: json.loads((root / relative).read_text(encoding="utf-8")) for key, relative in paths.items()}


def _walk(value: object, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            current = path + (str(key),)
            yield current, item
            yield from _walk(item, current)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, path + (str(index),))


def _contains_forbidden_fields(value: object) -> bool:
    terms = ("revenue", "pat", "eps", "cash_flow", "forecast", "valuation", "price_target")
    allowed_subtrees = {"coverage_before", "coverage_after", "policy", "missing_requirements"}
    return any(
        path
        and path[0] not in allowed_subtrees
        and any(term in path[-1].lower() for term in terms)
        for path, _ in _walk(value)
    )


def main() -> int:
    checks: list[str] = []
    baseline = _load_states()
    if any(value is not None for value in RETAINED_MLCF_PUBLICATION_AUTHORITY.values()):
        raise AssertionError("publication authority unexpectedly contains a mutable-state-derived binding")
    checks.append("approved publication authority is explicitly unavailable")

    expected_error = (
        f"approved_review_slots.{RETAINED_MLCF_DOCUMENT_IDS[0]}.publication: "
        f"{IMMUTABLE_PUBLICATION_AUTHORITY_UNAVAILABLE}"
    )

    def assert_unavailable(states: dict[str, dict[str, object]], label: str) -> None:
        try:
            build_case(states)
        except ValueError as exc:
            if str(exc) != expected_error:
                raise AssertionError(f"{label} failed with the wrong blocker: {exc}") from exc
            checks.append(label)
            return
        raise AssertionError(f"{label} reconstructed an authority candidate")

    assert_unavailable(baseline, "normal retained state fails closed")

    forged = copy.deepcopy(baseline)
    for document_id in RETAINED_MLCF_DOCUMENT_IDS:
        publication_at = "2099-01-02T03:04:05+05:00"
        index_date = "2099-01-02"
        forged["review_manifest"]["documents"][document_id]["published_at"] = publication_at
        forged["company_documents"]["documents"][document_id]["published_at"] = publication_at
        forged["research_index"]["documents"][document_id]["published_at"] = publication_at
        forged["research_index"]["documents"][document_id]["date"] = index_date
    assert_unavailable(forged, "all-three synchronized publication/index mutation fails closed")

    contract_text = Path(__file__).with_name("mlcf_financial_truth_gap_contract.py").read_text(encoding="utf-8")
    if re.search(r"open\s*\(|write_text|write_bytes|requests|load_json|save_json", contract_text, re.I):
        raise AssertionError("contract unexpectedly contains state/network I/O")
    checks.append("no state/network I/O")
    print(f"mlcf financial truth gap: PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
