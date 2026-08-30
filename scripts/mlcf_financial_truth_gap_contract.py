"""Deterministic, source-grounded contract for the blocked MLCF truth gap.

This module intentionally does not read or write desk state, fetch documents, parse
PDFs, run OCR, or emit financial values.  It records exactly why the retained
official FY24 tranche cannot be promoted under the current v2 geometry policy.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime
from typing import Any


CONTRACT_VERSION = "mlcf_financial_truth_gap_contract_v1"
CASE_SCHEMA = "mlcf_financial_truth_gap_case_v1"
SOURCE = "PSX DPS"
BLOCKER = "image_only_under_financial_statement_v2_geometry_gate"
MISSING_COUNTERPART = "no_text_readable_exact_official_counterpart_retained"
RAW_BYTES_MISSING = "raw_document_bytes_not_retained_for_reprocess"
FACT_EVIDENCE_MISSING = "fact_level_source_evidence_missing"

RETAINED_MLCF_DOCUMENTS: tuple[dict[str, str], ...] = (
    {
        "document_id": "psx:219092",
        "symbol": "MLCF",
        "period_end": "2023-09-30",
        "period_type": "interim",
        "title": "MLCF Financial Results for the Quarter Ended 30.09.2023",
        "published_at": "2023-10-27T08:50:00+05:00",
        "available_on": "2023-10-27",
        "source": SOURCE,
        "source_url": "https://dps.psx.com.pk/download/document/219092.pdf",
        "content_sha256": "0d0f108957f32cd911be7bcdc5b01dcc46c1c4872dad81dc59e5e0a453977f05",
    },
    {
        "document_id": "psx:225623",
        "symbol": "MLCF",
        "period_end": "2023-12-31",
        "period_type": "interim",
        "title": "MLCF-Financial Results 31.12.2023",
        "published_at": "2024-02-21T08:50:00+05:00",
        "available_on": "2024-02-21",
        "source": SOURCE,
        "source_url": "https://dps.psx.com.pk/download/document/225623.pdf",
        "content_sha256": "921c6bffa5fb9fe8c001bc76288a60d811ddfc9acb2357753008d57f129cbf42",
    },
    {
        "document_id": "psx:229941",
        "symbol": "MLCF",
        "period_end": "2024-03-31",
        "period_type": "interim",
        "title": "MLCF-Financial Results 31.03.2024",
        "published_at": "2024-04-25T12:56:00+05:00",
        "available_on": "2024-04-25",
        "source": SOURCE,
        "source_url": "https://dps.psx.com.pk/download/document/229941.pdf",
        "content_sha256": "9de20cf7a12f2e049ca2cf437be2089f300e7fc8aed8adae4d0be97492374030",
    },
)

_BASELINE_KEYS = {
    "annual_income_triplets",
    "qualified_reported_quarter_fact_sets",
    "annual_operating_cash_flow",
    "share_count",
    "source_conflict_count",
}
_COVERAGE_KEYS = {"required", "present", "qualified_periods"}
_CANDIDATE_KEYS = {
    "document_id",
    "symbol",
    "period_end",
    "period_type",
    "title",
    "published_at",
    "available_on",
    "source",
    "source_url",
    "content_sha256",
    "raw_retained",
    "text_extractable",
    "parser_status",
    "evidence_status",
    "blocker_reason",
    "facts",
}
_FORBIDDEN_FIELD_TERMS = {
    "revenue",
    "pat",
    "eps",
    "operating_cash_flow",
    "cash_flow",
    "forecast",
    "valuation",
    "price_target",
}
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")

EXPECTED_BASELINE: dict[str, Any] = {
    "annual_income_triplets": {
        "required": 5,
        "present": 3,
        "qualified_periods": ["2026-06-30", "2025-06-30", "2024-06-30"],
    },
    "qualified_reported_quarter_fact_sets": {
        "required": 8,
        "present": 3,
        "qualified_periods": ["2026-03-31", "2025-12-31", "2025-09-30"],
    },
    "annual_operating_cash_flow": {
        "required": 5,
        "present": 2,
        "qualified_periods": ["2025-06-30", "2024-06-30"],
    },
    "share_count": {
        "required": 1,
        "present": 0,
        "status": "missing_official_share_count_capital_note_tie_out",
    },
    "source_conflict_count": 0,
}


def _fail(path: str, message: str) -> None:
    raise ValueError(f"{path}: {message}")


def _closed_keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _fail(path, f"unknown fields {unknown}")


def _iso_date(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        _fail(path, "must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError:
        _fail(path, "must be a real calendar date")
    return value


def _iso_datetime(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail(path, "must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(path, "must be an ISO datetime")
    if parsed.tzinfo is None:
        _fail(path, "must include a timezone")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(path, "must be a non-negative integer")
    return value


def _validate_coverage(value: Any, path: str, *, require_periods: bool = True) -> None:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    _closed_keys(value, _COVERAGE_KEYS, path)
    for key in ("required", "present"):
        _nonnegative_int(value.get(key), f"{path}.{key}")
    periods = value.get("qualified_periods")
    if require_periods:
        if not isinstance(periods, list) or any(not isinstance(item, str) for item in periods):
            _fail(f"{path}.qualified_periods", "must be a list of ISO dates")
        for index, item in enumerate(periods):
            _iso_date(item, f"{path}.qualified_periods[{index}]")
        if len(periods) != value["present"] or len(set(periods)) != len(periods):
            _fail(path, "present must equal unique qualified_periods length")
    if value["present"] > value["required"]:
        _fail(path, "present cannot exceed required")


def _validate_baseline(value: Any, path: str = "baseline") -> None:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    _closed_keys(value, _BASELINE_KEYS, path)
    for key in ("annual_income_triplets", "qualified_reported_quarter_fact_sets", "annual_operating_cash_flow"):
        _validate_coverage(value.get(key), f"{path}.{key}")
    share = value.get("share_count")
    if not isinstance(share, dict) or set(share) != {"required", "present", "status"}:
        _fail(f"{path}.share_count", "must contain required, present and status only")
    _nonnegative_int(share["required"], f"{path}.share_count.required")
    _nonnegative_int(share["present"], f"{path}.share_count.present")
    if share["present"] > share["required"] or not isinstance(share["status"], str):
        _fail(f"{path}.share_count", "invalid count or status")
    if value.get("source_conflict_count") != 0:
        _fail(f"{path}.source_conflict_count", "must be zero")
    if value != EXPECTED_BASELINE:
        _fail(path, "does not match the committed MLCF qualification baseline")


def _expected_documents() -> dict[str, dict[str, str]]:
    return {item["document_id"]: item for item in RETAINED_MLCF_DOCUMENTS}


def _validate_candidate(value: Any, index: int, as_of_date: str) -> dict[str, Any]:
    path = f"candidates[{index}]"
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    _closed_keys(value, _CANDIDATE_KEYS, path)
    document_id = value.get("document_id")
    expected = _expected_documents().get(document_id)
    if expected is None:
        _fail(f"{path}.document_id", "is not an approved retained MLCF document")
    for key in expected:
        if value.get(key) != expected[key]:
            _fail(f"{path}.{key}", "does not match the retained official receipt")
    _iso_datetime(value.get("published_at"), f"{path}.published_at")
    available_on = _iso_date(value.get("available_on"), f"{path}.available_on")
    if available_on > as_of_date:
        _fail(path, "candidate is not available by as_of_date")
    if not _HASH_RE.fullmatch(value.get("content_sha256", "")):
        _fail(f"{path}.content_sha256", "must be a lowercase SHA-256")
    if value.get("raw_retained") is not False or value.get("text_extractable") is not False:
        _fail(path, "raw/text availability must remain false")
    if value.get("parser_status") != "image_only_under_financial_statement_v2_policy":
        _fail(f"{path}.parser_status", "must remain blocked by the current parser policy")
    if value.get("evidence_status") != "metadata_only_blocked" or value.get("blocker_reason") != BLOCKER:
        _fail(path, "evidence status/blocker is not the approved gap")
    if value.get("facts") != []:
        _fail(f"{path}.facts", "must be empty; no fact-level source evidence exists")
    return value


def validate_case(case: Any) -> dict[str, Any]:
    if not isinstance(case, dict):
        _fail("case", "must be an object")
    allowed = {"schema_version", "symbol", "as_of_date", "baseline", "candidates"}
    _closed_keys(case, allowed, "case")
    if case.get("schema_version") != CASE_SCHEMA or case.get("symbol") != "MLCF":
        _fail("case", "schema_version or symbol is invalid")
    as_of_date = _iso_date(case.get("as_of_date"), "as_of_date")
    _validate_baseline(case.get("baseline"))
    candidates = case.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != len(RETAINED_MLCF_DOCUMENTS):
        _fail("candidates", "must contain exactly the three retained MLCF documents")
    validated = [_validate_candidate(item, index, as_of_date) for index, item in enumerate(candidates)]
    expected_ids = [item["document_id"] for item in RETAINED_MLCF_DOCUMENTS]
    if [item["document_id"] for item in validated] != expected_ids:
        _fail("candidates", "must use deterministic retained-document order")
    return case


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _missing_requirements(baseline: dict[str, Any]) -> list[str]:
    requirements: list[str] = []
    labels = (
        ("annual_income_triplets", "annual_revenue_pat_eps"),
        ("qualified_reported_quarter_fact_sets", "direct_consolidated_reported_quarters"),
        ("annual_operating_cash_flow", "annual_operating_cash_flow"),
    )
    for key, label in labels:
        row = baseline[key]
        if row["present"] < row["required"]:
            requirements.append(f"{label}:{row['required'] - row['present']} missing")
    share = baseline["share_count"]
    if share["present"] < share["required"]:
        requirements.append("official_share_count_capital_note_tie_out:missing")
    return requirements


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    validate_case(case)
    baseline = copy.deepcopy(case["baseline"])
    reasons = [MISSING_COUNTERPART, BLOCKER, RAW_BYTES_MISSING, FACT_EVIDENCE_MISSING]
    candidate_evidence = []
    for candidate in case["candidates"]:
        candidate_evidence.append(
            {
                "document_id": candidate["document_id"],
                "period_end": candidate["period_end"],
                "available_on": candidate["available_on"],
                "source": candidate["source"],
                "source_url": candidate["source_url"],
                "content_sha256": candidate["content_sha256"],
                "evidence_status": candidate["evidence_status"],
                "blocker_reason": candidate["blocker_reason"],
                "facts": [],
            }
        )
    result = {
        "schema_version": CASE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "status": "blocked",
        "run_receipt": {"inputs_sha256": _canonical_sha256(case), "contract_version": CONTRACT_VERSION},
        "symbol": "MLCF",
        "as_of_date": case["as_of_date"],
        "coverage_before": baseline,
        "coverage_after": copy.deepcopy(baseline),
        "candidate_evidence": candidate_evidence,
        "blocked_reasons": reasons,
        "missing_requirements": _missing_requirements(baseline),
        "policy": {
            "retained_official_only": True,
            "no_pdf_fetch": True,
            "no_pdf_parse": True,
            "no_ocr": True,
            "no_numeric_facts": True,
            "no_forecast_or_valuation": True,
            "no_state_write": True,
        },
    }
    return result


__all__ = [
    "CASE_SCHEMA",
    "CONTRACT_VERSION",
    "RETAINED_MLCF_DOCUMENTS",
    "evaluate_case",
    "validate_case",
]
