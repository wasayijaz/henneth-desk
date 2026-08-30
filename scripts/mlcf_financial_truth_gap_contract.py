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


CONTRACT_VERSION = "mlcf_financial_truth_gap_contract_v2"
CASE_SCHEMA = "mlcf_financial_truth_gap_case_v1"
SOURCE = "PSX DPS"
BLOCKER = "image_only_under_financial_statement_v2_geometry_gate"
MISSING_COUNTERPART = "no_text_readable_exact_official_counterpart_retained"
RAW_BYTES_MISSING = "raw_document_bytes_not_retained_for_reprocess"
FACT_EVIDENCE_MISSING = "fact_level_source_evidence_missing"

RETAINED_MLCF_DOCUMENT_IDS: tuple[str, ...] = ("psx:219092", "psx:225623", "psx:229941")

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


def _validate_candidate(value: Any, index: int, as_of_date: str) -> dict[str, Any]:
    path = f"candidates[{index}]"
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    _closed_keys(value, _CANDIDATE_KEYS, path)
    document_id = value.get("document_id")
    if document_id not in RETAINED_MLCF_DOCUMENT_IDS:
        _fail(f"{path}.document_id", "is not an approved retained MLCF document")
    if value.get("symbol") != "MLCF" or value.get("period_type") != "interim" or value.get("source") != SOURCE:
        _fail(path, "issuer, period type or source is not the retained MLCF scope")
    if value.get("source_url") != f"https://dps.psx.com.pk/download/document/{document_id.split(':', 1)[1]}.pdf":
        _fail(f"{path}.source_url", "must be the canonical PSX document URL")
    if not isinstance(value.get("title"), str) or not value["title"]:
        _fail(f"{path}.title", "must be present")
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
    if not isinstance(candidates, list) or len(candidates) != len(RETAINED_MLCF_DOCUMENT_IDS):
        _fail("candidates", "must contain exactly the three retained MLCF documents")
    validated = [_validate_candidate(item, index, as_of_date) for index, item in enumerate(candidates)]
    expected_ids = list(RETAINED_MLCF_DOCUMENT_IDS)
    if [item["document_id"] for item in validated] != expected_ids:
        _fail("candidates", "must use deterministic retained-document order")
    return case


def _state_row(state: Any, path: str) -> dict[str, Any]:
    if not isinstance(state, dict):
        _fail(path, "must be an object")
    return state


def _require_equal(actual: Any, expected: Any, path: str) -> None:
    if actual != expected:
        _fail(path, "does not match retained authoritative state")


def _build_candidate_from_state(
    document_id: str,
    company_documents: dict[str, Any],
    review_manifest: dict[str, Any],
    research_index: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    manifest = _state_row((review_manifest.get("documents") or {}).get(document_id), f"review_manifest.documents.{document_id}")
    document = _state_row((company_documents.get("documents") or {}).get(document_id), f"company_documents.documents.{document_id}")
    index = _state_row((research_index.get("documents") or {}).get(document_id), f"research_index.documents.{document_id}")
    if manifest.get("approval_status") != "owner_approved" or manifest.get("classification") != "financial_results":
        _fail(f"review_manifest.documents.{document_id}", "source is not an approved financial-results tranche")
    safe_period = _state_row(manifest.get("safe_period"), f"review_manifest.documents.{document_id}.safe_period")
    if safe_period.get("period_type") != "interim" or safe_period.get("source") != "owner_approved_exact_source":
        _fail(f"review_manifest.documents.{document_id}.safe_period", "period provenance is not exact")
    for key in ("document_id", "symbol", "period", "title", "published_at", "source_url", "content_sha256"):
        if not manifest.get(key):
            _fail(f"review_manifest.documents.{document_id}.{key}", "required retained-source metadata is missing")
    _require_equal(manifest.get("document_id"), document_id, f"review_manifest.documents.{document_id}.document_id")
    _require_equal(manifest.get("symbol"), "MLCF", f"review_manifest.documents.{document_id}.symbol")
    _require_equal(safe_period.get("period_end"), manifest.get("period"), f"review_manifest.documents.{document_id}.safe_period.period_end")
    _require_equal(document.get("doc_id"), document_id, f"company_documents.documents.{document_id}.doc_id")
    _require_equal(document.get("tickers"), ["MLCF"], f"company_documents.documents.{document_id}.tickers")
    for key in ("title", "published_at", "source_url", "content_sha256"):
        _require_equal(document.get(key), manifest.get(key), f"company_documents.documents.{document_id}.{key}")
    _require_equal(document.get("source"), SOURCE, f"company_documents.documents.{document_id}.source")
    _require_equal(document.get("local_sha256"), manifest.get("content_sha256"), f"company_documents.documents.{document_id}.local_sha256")
    for key, expected in (("status", "ready"), ("stale", False), ("error", None), ("media_type", "application/pdf"), ("content_length", None)):
        _require_equal(document.get(key), expected, f"company_documents.documents.{document_id}.{key}")
    for key in ("evidence", "events", "facts", "versions"):
        _require_equal(document.get(key), [], f"company_documents.documents.{document_id}.{key}")
    for key in ("brief_evidence", "ledger_changes"):
        if key in document:
            _require_equal(document.get(key), [], f"company_documents.documents.{document_id}.{key}")
    forbidden_document_fields = {"local_path", "raw_path", "raw_bytes", "text", "extracted_text", "parser_version", "parser_revision"}
    if forbidden_document_fields.intersection(document):
        _fail(f"company_documents.documents.{document_id}", "raw/text/parser state drifted into the metadata-only record")
    for key, expected in (
        ("id", document_id),
        ("source", SOURCE),
        ("source_type", "filing"),
        ("doc_type", "financial_results"),
        ("date", manifest.get("published_at", "")[:10]),
        ("published_at", manifest.get("published_at")),
        ("tickers", ["MLCF"]),
        ("title", manifest.get("title")),
        ("url", manifest.get("source_url")),
        ("official_document_id", document_id.split(":", 1)[1]),
    ):
        _require_equal(index.get(key), expected, f"research_index.documents.{document_id}.{key}")
    if not isinstance(reconciliation.get("facts"), list):
        _fail("reconciliation.facts", "must remain a list")
    candidate_source_ids = {
        str((fact.get("source") or {}).get("document_id"))
        for fact in reconciliation.get("facts") or []
        if isinstance(fact, dict) and (fact.get("source") or {}).get("document_id")
    }
    if document_id in candidate_source_ids:
        _fail(f"reconciliation.facts[{document_id}]", "candidate document has retained fact evidence")
    return {
        "document_id": document_id,
        "symbol": "MLCF",
        "period_end": safe_period.get("period_end"),
        "period_type": safe_period.get("period_type"),
        "title": manifest.get("title"),
        "published_at": manifest.get("published_at"),
        "available_on": manifest.get("published_at", "")[:10],
        "source": SOURCE,
        "source_url": manifest.get("source_url"),
        "content_sha256": manifest.get("content_sha256"),
        "raw_retained": False,
        "text_extractable": False,
        "parser_status": "image_only_under_financial_statement_v2_policy",
        "evidence_status": "metadata_only_blocked",
        "blocker_reason": BLOCKER,
        "facts": [],
    }


def build_case_from_retained_state(
    financial_truth_state: dict[str, Any],
    company_documents_state: dict[str, Any],
    review_manifest_state: dict[str, Any],
    research_index_state: dict[str, Any],
    reconciliation_state: dict[str, Any],
    *,
    as_of_date: str,
) -> dict[str, Any]:
    """Build the gap case from retained state; this function never writes or fetches."""
    qualification = _state_row((financial_truth_state.get("companies") or {}).get("MLCF"), "financial_truth.companies.MLCF")
    reconciliation = _state_row((reconciliation_state.get("companies") or {}).get("MLCF"), "reconciliation.companies.MLCF")
    if "MLCF" not in (financial_truth_state.get("pilot_symbols") or []):
        _fail("financial_truth.pilot_symbols", "MLCF is outside the retained qualification universe")
    if qualification.get("symbol") != "MLCF" or qualification.get("status") != "not_qualified":
        _fail("financial_truth.companies.MLCF", "qualification status drifted")
    if (qualification.get("financial_tie_out") or {}).get("status") != "blocked":
        _fail("financial_truth.companies.MLCF.financial_tie_out", "financial tie-out is no longer blocked")
    if (qualification.get("downstream") or {}).get("forecast") != "blocked_financial_truth_not_qualified":
        _fail("financial_truth.companies.MLCF.downstream.forecast", "formal forecast gate drifted")
    if (qualification.get("policy") or {}).get("raw_financial_values") != "not_emitted":
        _fail("financial_truth.companies.MLCF.policy.raw_financial_values", "raw financial output policy drifted")
    if reconciliation.get("symbol") != "MLCF" or reconciliation.get("source_conflict_count") != 0:
        _fail("reconciliation.companies.MLCF", "reconciliation conflict state drifted")
    share_state = qualification.get("share_count") or {}
    if share_state.get("status") != "missing_official_share_count_capital_note_tie_out" or share_state.get("available_on") is not None or share_state.get("source") is not None:
        _fail("financial_truth.companies.MLCF.share_count", "share-count tie-out status drifted")
    baseline = {
        "annual_income_triplets": copy.deepcopy(qualification.get("annual_income_triplets")),
        "qualified_reported_quarter_fact_sets": copy.deepcopy(qualification.get("qualified_reported_quarter_fact_sets")),
        "annual_operating_cash_flow": copy.deepcopy(qualification.get("annual_operating_cash_flow")),
        "share_count": {
            "required": 1,
            "present": 0 if (qualification.get("share_count") or {}).get("status") == "missing_official_share_count_capital_note_tie_out" else 1,
            "status": (qualification.get("share_count") or {}).get("status"),
        },
        "source_conflict_count": reconciliation.get("source_conflict_count"),
    }
    candidate_ids = set(RETAINED_MLCF_DOCUMENT_IDS)
    manifest_ids = set(review_manifest_state.get("document_ids") or [])
    if not candidate_ids.issubset(manifest_ids):
        _fail("review_manifest.document_ids", "retained MLCF tranche is incomplete")
    candidates = [
        _build_candidate_from_state(document_id, company_documents_state, review_manifest_state, research_index_state, reconciliation)
        for document_id in RETAINED_MLCF_DOCUMENT_IDS
    ]
    case = {
        "schema_version": CASE_SCHEMA,
        "symbol": "MLCF",
        "as_of_date": as_of_date,
        "baseline": baseline,
        "candidates": candidates,
    }
    validate_case(case)
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
    "RETAINED_MLCF_DOCUMENT_IDS",
    "build_case_from_retained_state",
    "evaluate_case",
    "validate_case",
]
