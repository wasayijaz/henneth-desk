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
    MISSING_COUNTERPART,
    RAW_BYTES_MISSING,
    RETAINED_MLCF_DOCUMENT_IDS,
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
    states = _load_states()
    case = build_case(states)
    validate_case(case)
    checks.append("valid fixture")

    result = evaluate_case(case, retained_state=states)
    if result["status"] != "blocked" or result["contract_version"] != CONTRACT_VERSION:
        raise AssertionError("result is not a blocked contract result")
    if result["coverage_before"] != result["coverage_after"]:
        raise AssertionError("blocked case changed coverage")
    if result["blocked_reasons"] != [MISSING_COUNTERPART, BLOCKER, RAW_BYTES_MISSING, FACT_EVIDENCE_MISSING]:
        raise AssertionError("blocked reasons are not explicit and deterministic")
    if any(row["facts"] != [] for row in result["candidate_evidence"]):
        raise AssertionError("candidate evidence contains facts")
    if _contains_forbidden_fields(result):
        raise AssertionError("result contains forbidden financial/advice fields")
    checks.append("blocked result")
    try:
        evaluate_case(case)
    except ValueError:
        checks.append("authority required")
    else:
        raise AssertionError("evaluate_case emitted output without authoritative state")

    again = evaluate_case(copy.deepcopy(case), retained_state=states)
    if json.dumps(result, sort_keys=True, separators=(",", ":")) != json.dumps(again, sort_keys=True, separators=(",", ":")):
        raise AssertionError("result is not deterministic")
    case["baseline"]["annual_income_triplets"]["present"] = 0
    if result["coverage_before"]["annual_income_triplets"]["present"] != 3:
        raise AssertionError("result shares mutable baseline")
    checks.append("determinism and isolation")

    for label, mutate in (
        ("financial coverage drift", lambda s: s["financial_truth"]["companies"]["MLCF"]["annual_income_triplets"].__setitem__("present", 2)),
        ("annual period drift", lambda s: s["financial_truth"]["companies"]["MLCF"]["annual_income_triplets"]["qualified_periods"].__setitem__(2, "2023-06-30")),
        ("annual required-count drift", lambda s: s["financial_truth"]["companies"]["MLCF"]["annual_income_triplets"].__setitem__("required", 6)),
        ("required source hash drift", lambda s: s["review_manifest"]["documents"][RETAINED_MLCF_DOCUMENT_IDS[0]].__setitem__("content_sha256", "0" * 64)),
        ("manifest period drift", lambda s: (s["review_manifest"]["documents"][RETAINED_MLCF_DOCUMENT_IDS[0]].__setitem__("period", "2023-08-31"), s["review_manifest"]["documents"][RETAINED_MLCF_DOCUMENT_IDS[0]]["safe_period"].__setitem__("period_end", "2023-08-31"))),
        ("manifest source drift", lambda s: s["review_manifest"].__setitem__("source", "EVIL")),
        ("company document drift", lambda s: s["company_documents"]["documents"][RETAINED_MLCF_DOCUMENT_IDS[0]].__setitem__("evidence", [{"page": 1}])),
        ("unknown parser geometry field", lambda s: s["company_documents"]["documents"][RETAINED_MLCF_DOCUMENT_IDS[0]].__setitem__("parser_geometry", "evil")),
        ("research index drift", lambda s: s["research_index"]["documents"][RETAINED_MLCF_DOCUMENT_IDS[0]].__setitem__("url", "https://example.invalid")),
        ("reconciliation evidence drift", lambda s: s["reconciliation"]["companies"]["MLCF"]["facts"].append({"source": {"document_id": RETAINED_MLCF_DOCUMENT_IDS[0]}})),
    ):
        states = copy.deepcopy(_load_states())
        mutate(states)
        _assert_source_reject(states, checks, label)

    for label, mutate in (
        ("missing candidate", lambda c: c["candidates"].pop()),
        ("duplicate candidate", lambda c: c["candidates"].__setitem__(1, copy.deepcopy(c["candidates"][0]))),
        ("fabricated document", lambda c: c["candidates"][0].__setitem__("document_id", "psx:999999")),
        ("wrong symbol", lambda c: c["candidates"][0].__setitem__("symbol", "OTHER")),
        ("wrong title", lambda c: c["candidates"][0].__setitem__("title", "made up")),
        ("wrong source", lambda c: c["candidates"][0].__setitem__("source", "other")),
        ("wrong URL", lambda c: c["candidates"][0].__setitem__("source_url", "https://example.invalid")),
        ("wrong hash", lambda c: c["candidates"][0].__setitem__("content_sha256", "0" * 64)),
        ("wrong available date", lambda c: c["candidates"][0].__setitem__("available_on", "2023-10-28")),
        ("published after as_of", lambda c: c["candidates"][0].__setitem__("published_at", "2027-01-01T00:00:00+05:00")),
        ("lookahead", lambda c: c.__setitem__("as_of_date", "2023-10-26")),
        ("malformed date", lambda c: c["candidates"][0].__setitem__("period_end", "2023-02-30")),
        ("raw bytes promoted", lambda c: c["candidates"][0].__setitem__("raw_retained", True)),
        ("text promoted", lambda c: c["candidates"][0].__setitem__("text_extractable", True)),
        ("parser bypass", lambda c: c["candidates"][0].__setitem__("parser_status", "parsed")),
        ("evidence promoted", lambda c: c["candidates"][0].__setitem__("evidence_status", "qualified")),
        ("blocker removed", lambda c: c["candidates"][0].__setitem__("blocker_reason", "")),
        ("facts fabricated", lambda c: c["candidates"][0].__setitem__("facts", [{"revenue": 1}])),
        ("unknown candidate field", lambda c: c["candidates"][0].__setitem__("revenue", 1)),
        ("unknown root field", lambda c: c.__setitem__("forecast_value", 1)),
        ("unknown baseline field", lambda c: c["baseline"].__setitem__("revenue", 1)),
        ("period count mismatch", lambda c: c["baseline"]["annual_income_triplets"].__setitem__("present", 2)),
        ("period duplicate", lambda c: c["baseline"]["annual_income_triplets"].__setitem__("qualified_periods", ["2026-06-30", "2026-06-30", "2024-06-30"])),
        ("conflict introduced", lambda c: c["baseline"].__setitem__("source_conflict_count", 1)),
        ("share tieout fabricated", lambda c: c["baseline"]["share_count"].__setitem__("present", 1)),
    ):
        mutated = copy.deepcopy(build_case())
        mutate(mutated)
        _assert_reject(mutated, checks, label)

    if not re.search(r"open\s*\(|write_text|write_bytes|requests|load_json|save_json", Path(__file__).with_name("mlcf_financial_truth_gap_contract.py").read_text(encoding="utf-8"), re.I):
        checks.append("no state/network I/O")
    else:
        raise AssertionError("contract unexpectedly contains state/network I/O")
    if any(isinstance(value, float) and not math.isfinite(value) for _, value in _walk(result)):
        raise AssertionError("result contains non-finite numbers")
    checks.append("finite output")
    print(f"mlcf financial truth gap: PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
