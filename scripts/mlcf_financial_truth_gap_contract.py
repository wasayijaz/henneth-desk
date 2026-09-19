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

from financial_truth_qualification import (
    ANNUAL_CASHFLOW_SCOPE,
    ANNUAL_INCOME_SCOPE,
    REPORTED_QUARTER_SCOPE,
    REQUIRED_ANNUAL_METRICS,
    TARGET_ANNUAL_PERIODS,
    TARGET_REPORTED_INTERIM_PERIODS,
    _eligible_cashflow_periods,
    _facts_by_period,
    _qualified_quarter_periods,
)
from build_ci_reprocess_manifest import APPROVED_REVIEW_SLOTS


CONTRACT_VERSION = "mlcf_financial_truth_gap_contract_v2"
CASE_SCHEMA = "mlcf_financial_truth_gap_case_v1"
SOURCE = "PSX DPS"
BLOCKER = "image_only_under_financial_statement_v2_geometry_gate"
IMMUTABLE_PUBLICATION_AUTHORITY_UNAVAILABLE = "immutable publication authority unavailable"
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


def _authority_unavailable(path: str) -> None:
    _fail(path, IMMUTABLE_PUBLICATION_AUTHORITY_UNAVAILABLE)


def _build_retained_mlcf_document_authority() -> dict[str, dict[str, str]]:
    authority: dict[str, dict[str, str]] = {}
    for slot in APPROVED_REVIEW_SLOTS:
        if not isinstance(slot, dict):
            continue
        document_id = slot.get("source_document_id")
        if document_id not in RETAINED_MLCF_DOCUMENT_IDS:
            continue
        path = f"approved_review_slots.{document_id}"
        if slot.get("symbol") != "MLCF" or slot.get("classification") != "financial_results":
            _authority_unavailable(path)
        if slot.get("period_type") != "interim" or slot.get("require_retained_hash") is not True:
            _authority_unavailable(path)
        period = slot.get("period")
        title_pattern = slot.get("title_pattern")
        content_sha256 = str(slot.get("source_content_sha256") or "").lower()
        if not isinstance(period, str) or not isinstance(title_pattern, str) or not _HASH_RE.fullmatch(content_sha256):
            _authority_unavailable(path)
        _iso_date(period, f"{path}.period")
        authority[document_id] = {
            "document_id": document_id,
            "symbol": "MLCF",
            "period_end": period,
            "period_type": "interim",
            "expected_title_pattern": title_pattern,
            "source": SOURCE,
            "source_url": f"https://dps.psx.com.pk/download/document/{document_id.split(':', 1)[1]}.pdf",
            "content_sha256": content_sha256,
            "research_index_hash": document_id,
        }
    missing = [document_id for document_id in RETAINED_MLCF_DOCUMENT_IDS if document_id not in authority]
    if missing:
        _authority_unavailable("approved_review_slots")
    return {document_id: authority[document_id] for document_id in RETAINED_MLCF_DOCUMENT_IDS}

_FINANCIAL_TRUTH_TOP_KEYS = {"schema_version", "pilot_symbols", "source", "policy", "selection", "companies", "summary", "_meta"}
_QUALIFICATION_KEYS = {
    "annual_income_triplets",
    "annual_operating_cash_flow",
    "candidate_documents",
    "candidate_rank",
    "documented_interim_metadata",
    "downstream",
    "evidence_gaps",
    "financial_tie_out",
    "model_ready_financial_statement_coverage",
    "operating_lane",
    "policy",
    "qualification_scope",
    "qualified_reported_quarter_fact_sets",
    "selection_status",
    "share_count",
    "status",
    "symbol",
}
_SHARE_COUNT_KEYS = {"status", "available_on", "source", "limitation"}
_SHARE_SOURCE_KEYS = {"id", "label", "path", "url"}
_FINANCIAL_TIE_OUT_KEYS = {"status", "reason"}
_DOWNSTREAM_KEYS = {"forecast", "valuation", "market_expectations"}
_QUALIFICATION_POLICY_KEYS = {"raw_financial_values", "restage", "forecasts", "valuation", "market_expectations"}
_RECONCILIATION_TOP_KEYS = {
    "schema_version",
    "reconciliation_version",
    "earnings_bridge_version",
    "pilot_symbols",
    "as_of",
    "source",
    "policy",
    "summary",
    "companies",
    "_meta",
}
_RECONCILIATION_COMPANY_KEYS = {
    "audit_only_fact_count",
    "conflicts",
    "eligible_fact_count",
    "facts",
    "derived_fact_lane",
    "missing_slot_count",
    "missing_slots",
    "qualified_periods",
    "quarantined_fact_count",
    "readiness",
    "source_conflict_count",
    "status",
    "symbol",
    "withheld_future_source_fact_count",
}
_RECONCILIATION_FACT_KEYS = {
    "confidence",
    "consolidation",
    "currency",
    "duration_months",
    "epistemic_type",
    "eligibility_scope",
    "evidence_id",
    "evidence_label",
    "derived_lineage_validated",
    "formula",
    "calculation_version",
    "lineage",
    "metric",
    "normalized_value",
    "parser",
    "period_end",
    "period_type",
    "raw_value",
    "reasons",
    "reconciliation_id",
    "source",
    "statement_type",
    "status",
    "symbol",
    "unit",
    "unit_multiplier",
}
_RECONCILIATION_FACT_SOURCE_KEYS = {
    "available_on",
    "content_sha256",
    "document_id",
    "fact_id",
    "page",
    "published_at",
    "retrieved_at",
    "source",
    "source_url",
    "text",
}
_DERIVED_FACT_LANE_KEYS = {
    "status",
    "accepted_fact_count",
    "document_id",
    "content_sha256",
    "formula_versions",
    "scope",
}
_REVIEW_TOP_KEYS = {"schema_version", "manifest_version", "manifest_id", "source", "policy", "pilot_symbols", "approved_review_slots", "document_ids", "documents", "summary"}
_REVIEW_DOCUMENT_KEYS = {"document_id", "symbol", "period", "classification", "title", "expected_title_pattern", "published_at", "source_url", "content_sha256", "content_identity", "safe_period", "approval_status", "reason"}
_REVIEW_SOURCE = {"financial_coverage": "state/company_intel/financial_coverage.json", "research_index": "state/research_index.json"}
_COMPANY_DOCUMENT_TOP_KEYS = {"schema_version", "documents", "_meta"}
_COMPANY_DOCUMENT_KEYS = {"schema_version", "doc_id", "tickers", "title", "doc_type", "published_at", "retrieved_at", "available_on", "source_url", "source", "content_sha256", "local_sha256", "content_length", "page_count", "media_type", "status", "stale", "error", "evidence", "events", "facts", "versions", "brief_evidence", "ledger_changes"}
_RESEARCH_INDEX_TOP_KEYS = {"documents", "by_ticker", "_meta"}
_RESEARCH_INDEX_DOCUMENT_KEYS = {"id", "hash", "source", "source_type", "doc_type", "date", "published_at", "tickers", "company_name", "title", "digest", "digest_level", "claims", "url", "source_page", "official_document_id", "omissions"}

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


RETAINED_MLCF_DOCUMENTS: dict[str, dict[str, str]] = _build_retained_mlcf_document_authority()


def _build_retained_mlcf_publication_authority() -> dict[str, dict[str, str] | None]:
    """Return only immutable publication bindings, never values from retained state.

    The approved slot constants currently pin identity, period, title and content
    hash, but do not pin publication/index dates (or a digest of those fields).
    Such metadata therefore cannot be treated as authority; callers must fail
    closed until the owner adds an immutable binding to the approved slots.
    """
    authority: dict[str, dict[str, str] | None] = {}
    for document_id in RETAINED_MLCF_DOCUMENT_IDS:
        slot = next(
            (item for item in APPROVED_REVIEW_SLOTS if isinstance(item, dict) and item.get("source_document_id") == document_id),
            None,
        )
        published_at = slot.get("published_at") if isinstance(slot, dict) else None
        research_index_date = slot.get("research_index_date") if isinstance(slot, dict) else None
        if not isinstance(published_at, str) or not isinstance(research_index_date, str):
            authority[document_id] = None
            continue
        authority[document_id] = {
            "published_at": published_at,
            "research_index_date": research_index_date,
        }
    return authority


RETAINED_MLCF_PUBLICATION_AUTHORITY = _build_retained_mlcf_publication_authority()


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
    expected = _expected_document(document_id, f"{path}.document_id")
    for key in ("symbol", "period_end", "period_type", "source", "source_url", "content_sha256"):
        _require_equal(value.get(key), expected[key], f"{path}.{key}")
    if not isinstance(value.get("title"), str) or re.fullmatch(expected["expected_title_pattern"], value["title"]) is None:
        _fail(f"{path}.title", "does not match immutable approved title authority")
    _iso_datetime(value.get("published_at"), f"{path}.published_at")
    available_on = _iso_date(value.get("available_on"), f"{path}.available_on")
    if available_on > as_of_date or value["published_at"][:10] > as_of_date:
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


def _expected_document(document_id: Any, path: str) -> dict[str, str]:
    if not isinstance(document_id, str) or document_id not in RETAINED_MLCF_DOCUMENTS:
        _fail(path, "is not an approved retained MLCF document")
    return RETAINED_MLCF_DOCUMENTS[document_id]


def _build_candidate_from_state(
    document_id: str,
    company_documents: dict[str, Any],
    review_manifest: dict[str, Any],
    research_index: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    expected = _expected_document(document_id, f"review_manifest.documents.{document_id}.document_id")
    publication_authority = RETAINED_MLCF_PUBLICATION_AUTHORITY.get(document_id)
    if publication_authority is None:
        _authority_unavailable(f"approved_review_slots.{document_id}.publication")
    _iso_datetime(publication_authority["published_at"], f"approved_review_slots.{document_id}.published_at")
    _iso_date(publication_authority["research_index_date"], f"approved_review_slots.{document_id}.research_index_date")
    manifest = _state_row((review_manifest.get("documents") or {}).get(document_id), f"review_manifest.documents.{document_id}")
    document = _state_row((company_documents.get("documents") or {}).get(document_id), f"company_documents.documents.{document_id}")
    index = _state_row((research_index.get("documents") or {}).get(document_id), f"research_index.documents.{document_id}")
    _closed_keys(manifest, _REVIEW_DOCUMENT_KEYS, f"review_manifest.documents.{document_id}")
    _closed_keys(document, _COMPANY_DOCUMENT_KEYS, f"company_documents.documents.{document_id}")
    _closed_keys(index, _RESEARCH_INDEX_DOCUMENT_KEYS, f"research_index.documents.{document_id}")
    if manifest.get("approval_status") != "owner_approved" or manifest.get("classification") != "financial_results":
        _fail(f"review_manifest.documents.{document_id}", "source is not an approved financial-results tranche")
    safe_period = _state_row(manifest.get("safe_period"), f"review_manifest.documents.{document_id}.safe_period")
    _closed_keys(safe_period, {"period_end", "period_type", "source"}, f"review_manifest.documents.{document_id}.safe_period")
    if safe_period.get("period_type") != "interim" or safe_period.get("source") != "owner_approved_exact_source":
        _fail(f"review_manifest.documents.{document_id}.safe_period", "period provenance is not exact")
    for key in ("document_id", "symbol", "period", "title", "published_at", "source_url", "content_sha256"):
        if not manifest.get(key):
            _fail(f"review_manifest.documents.{document_id}.{key}", "required retained-source metadata is missing")
    _require_equal(manifest.get("document_id"), document_id, f"review_manifest.documents.{document_id}.document_id")
    _require_equal(manifest.get("symbol"), "MLCF", f"review_manifest.documents.{document_id}.symbol")
    _require_equal(safe_period.get("period_end"), manifest.get("period"), f"review_manifest.documents.{document_id}.safe_period.period_end")
    if manifest.get("expected_title_pattern") != expected["expected_title_pattern"]:
        _fail(f"review_manifest.documents.{document_id}.expected_title_pattern", "does not match immutable approved title authority")
    if not isinstance(manifest.get("title"), str) or re.fullmatch(expected["expected_title_pattern"], manifest["title"]) is None:
        _fail(f"review_manifest.documents.{document_id}.expected_title_pattern", "title does not match the retained exact-title pattern")
    published_at = _iso_datetime(manifest.get("published_at"), f"review_manifest.documents.{document_id}.published_at")
    title_date = re.search(r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})", manifest["title"])
    if not title_date:
        _fail(f"review_manifest.documents.{document_id}.title", "retained title has no exact reporting period")
    _require_equal(
        manifest.get("period"),
        f"{title_date.group('year')}-{title_date.group('month')}-{title_date.group('day')}",
        f"review_manifest.documents.{document_id}.period",
    )
    for key in ("source_url", "content_sha256"):
        _require_equal(manifest.get(key), expected[key], f"review_manifest.documents.{document_id}.{key}")
    _require_equal(manifest.get("period"), expected["period_end"], f"review_manifest.documents.{document_id}.period")
    _require_equal(manifest.get("content_identity"), "retained_hash", f"review_manifest.documents.{document_id}.content_identity")
    _require_equal(document.get("doc_id"), document_id, f"company_documents.documents.{document_id}.doc_id")
    _require_equal(document.get("tickers"), ["MLCF"], f"company_documents.documents.{document_id}.tickers")
    _require_equal(document.get("doc_type"), "results", f"company_documents.documents.{document_id}.doc_type")
    _require_equal(document.get("title"), manifest.get("title"), f"company_documents.documents.{document_id}.title")
    _require_equal(document.get("published_at"), published_at, f"company_documents.documents.{document_id}.published_at")
    _require_equal(manifest.get("published_at"), publication_authority["published_at"], f"review_manifest.documents.{document_id}.published_at")
    _require_equal(document.get("published_at"), publication_authority["published_at"], f"company_documents.documents.{document_id}.published_at")
    for key in ("source_url", "content_sha256"):
        _require_equal(document.get(key), expected[key], f"company_documents.documents.{document_id}.{key}")
    _require_equal(document.get("source"), SOURCE, f"company_documents.documents.{document_id}.source")
    _require_equal(document.get("local_sha256"), expected["content_sha256"], f"company_documents.documents.{document_id}.local_sha256")
    for key, expected_value in (("status", "ready"), ("stale", False), ("error", None), ("media_type", "application/pdf"), ("content_length", None)):
        _require_equal(document.get(key), expected_value, f"company_documents.documents.{document_id}.{key}")
    for key in ("evidence", "events", "facts", "versions"):
        _require_equal(document.get(key), [], f"company_documents.documents.{document_id}.{key}")
    for key in ("brief_evidence", "ledger_changes"):
        if key in document:
            _require_equal(document.get(key), [], f"company_documents.documents.{document_id}.{key}")
    forbidden_document_fields = {"local_path", "raw_path", "raw_bytes", "text", "extracted_text", "parser_version", "parser_revision"}
    if forbidden_document_fields.intersection(document):
        _fail(f"company_documents.documents.{document_id}", "raw/text/parser state drifted into the metadata-only record")
    for key, expected_value in (
        ("id", document_id),
        ("hash", expected["research_index_hash"]),
        ("source", SOURCE),
        ("source_type", "filing"),
        ("doc_type", "financial_results"),
        ("date", published_at[:10]),
        ("published_at", published_at),
        ("tickers", ["MLCF"]),
        ("title", manifest.get("title")),
        ("url", expected["source_url"]),
        ("source_page", "https://dps.psx.com.pk/announcements/companies"),
        ("official_document_id", document_id.split(":", 1)[1]),
    ):
        _require_equal(index.get(key), expected_value, f"research_index.documents.{document_id}.{key}")
    _require_equal(index.get("published_at"), publication_authority["published_at"], f"research_index.documents.{document_id}.published_at")
    _require_equal(index.get("date"), publication_authority["research_index_date"], f"research_index.documents.{document_id}.date")
    if not isinstance(reconciliation.get("facts"), list):
        _fail("reconciliation.facts", "must remain a list")
    candidate_source_ids = {
        str((source or {}).get("document_id"))
        for fact in reconciliation.get("facts") or []
        if isinstance(fact, dict)
        for source in [fact.get("source") if isinstance(fact.get("source"), dict) else None]
        if source and source.get("document_id")
    }
    if document_id in candidate_source_ids:
        _fail(f"reconciliation.facts[{document_id}]", "candidate document has retained fact evidence")
    return {
        "document_id": document_id,
        "symbol": "MLCF",
        "period_end": expected["period_end"],
        "period_type": expected["period_type"],
        "title": manifest.get("title"),
        "published_at": published_at,
        "available_on": published_at[:10],
        "source": SOURCE,
        "source_url": expected["source_url"],
        "content_sha256": expected["content_sha256"],
        "raw_retained": False,
        "text_extractable": False,
        "parser_status": "image_only_under_financial_statement_v2_policy",
        "evidence_status": "metadata_only_blocked",
        "blocker_reason": BLOCKER,
        "facts": [],
    }


def _validate_qualification_against_reconciliation(
    qualification: dict[str, Any],
    reconciliation: dict[str, Any],
    company_documents: dict[str, Any],
    research_index: dict[str, Any],
) -> None:
    """Re-derive every load-bearing period set from retained eligible facts."""
    annual_by_period = _facts_by_period(reconciliation, REQUIRED_ANNUAL_METRICS)
    derived = {
        "annual_income_triplets": sorted(
            (period for period, metrics in annual_by_period.items() if set(REQUIRED_ANNUAL_METRICS).issubset(metrics)),
            reverse=True,
        ),
        "qualified_reported_quarter_fact_sets": _qualified_quarter_periods(reconciliation),
        "annual_operating_cash_flow": _eligible_cashflow_periods(reconciliation),
    }
    for key, periods in derived.items():
        path = f"financial_truth.companies.MLCF.{key}"
        row = _state_row(qualification.get(key), path)
        _validate_coverage(row, path)
        expected_required = TARGET_REPORTED_INTERIM_PERIODS if key == "qualified_reported_quarter_fact_sets" else TARGET_ANNUAL_PERIODS
        if row.get("required") != expected_required or row.get("present") != len(periods) or row.get("qualified_periods") != periods:
            _fail(path, "coverage periods/counts do not match retained reconciliation facts")
    documents = company_documents.get("documents") or {}
    index_documents = research_index.get("documents") or {}
    lane = reconciliation.get("derived_fact_lane")
    if not isinstance(lane, dict):
        _fail("reconciliation.companies.MLCF.derived_fact_lane", "must be an object")
    _closed_keys(lane, _DERIVED_FACT_LANE_KEYS, "reconciliation.companies.MLCF.derived_fact_lane")
    if lane != {
        "status": "validated",
        "accepted_fact_count": 4,
        "document_id": "psx:260032",
        "content_sha256": lane.get("content_sha256"),
        "formula_versions": ["mlcf_derived_lineage_v2"],
        "scope": "MLCF psx:260032 only",
    }:
        _fail("reconciliation.companies.MLCF.derived_fact_lane", "bounded derived-fact lane drifted")
    if not isinstance(lane.get("content_sha256"), str) or not _HASH_RE.fullmatch(lane["content_sha256"]):
        _fail("reconciliation.companies.MLCF.derived_fact_lane.content_sha256", "must be a lowercase SHA-256")
    if not isinstance(reconciliation.get("facts"), list):
        _fail("reconciliation.companies.MLCF.facts", "must be a list")
    for index, fact in enumerate(reconciliation["facts"]):
        if not isinstance(fact, dict) or fact.get("status") != "eligible":
            continue
        _closed_keys(fact, _RECONCILIATION_FACT_KEYS, f"reconciliation.companies.MLCF.facts[{index}]")
        if fact.get("epistemic_type") == "derived_fact":
            if fact.get("derived_lineage_validated") is not True or fact.get("calculation_version") != "mlcf_derived_lineage_v2":
                _fail(f"reconciliation.companies.MLCF.facts[{index}]", "derived fact lineage is not validated")
            if not isinstance(fact.get("formula"), dict) or not isinstance(fact.get("lineage"), dict):
                _fail(f"reconciliation.companies.MLCF.facts[{index}]", "derived fact formula/lineage missing")
            if fact.get("source", {}).get("document_id") != "psx:260032" or fact.get("source", {}).get("page") != 361:
                _fail(f"reconciliation.companies.MLCF.facts[{index}]", "derived fact source is outside bounded MLCF lane")
        source = _state_row(fact.get("source"), f"reconciliation.companies.MLCF.facts[{index}].source")
        _closed_keys(source, _RECONCILIATION_FACT_SOURCE_KEYS, f"reconciliation.companies.MLCF.facts[{index}].source")
        if fact.get("eligibility_scope") not in {ANNUAL_INCOME_SCOPE, REPORTED_QUARTER_SCOPE, ANNUAL_CASHFLOW_SCOPE, "annual_balance_sheet_financial_truth_gate", "reported_quarter_balance_sheet_financial_truth_gate"}:
            continue
        if not source.get("document_id"):
            _fail("reconciliation.companies.MLCF.facts", "eligible fact lacks a retained source reference")
        document_id = source["document_id"]
        document = _state_row(documents.get(document_id), f"company_documents.documents.{document_id}")
        index = _state_row(index_documents.get(document_id), f"research_index.documents.{document_id}")
        _closed_keys(document, _COMPANY_DOCUMENT_KEYS, f"company_documents.documents.{document_id}")
        _closed_keys(index, _RESEARCH_INDEX_DOCUMENT_KEYS, f"research_index.documents.{document_id}")
        _require_equal(source.get("content_sha256"), document.get("content_sha256"), f"reconciliation source hash {document_id}")
        _require_equal(source.get("source_url"), document.get("source_url"), f"reconciliation source URL {document_id}")
        _require_equal(source.get("source"), document.get("source"), f"reconciliation source label {document_id}")
        _require_equal(index.get("id"), document_id, f"research index source {document_id}")


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
    _closed_keys(financial_truth_state, _FINANCIAL_TRUTH_TOP_KEYS, "financial_truth")
    _closed_keys(company_documents_state, _COMPANY_DOCUMENT_TOP_KEYS, "company_documents")
    _closed_keys(review_manifest_state, _REVIEW_TOP_KEYS, "review_manifest")
    _closed_keys(research_index_state, _RESEARCH_INDEX_TOP_KEYS, "research_index")
    _closed_keys(reconciliation_state, _RECONCILIATION_TOP_KEYS, "reconciliation")
    _closed_keys(qualification, _QUALIFICATION_KEYS, "financial_truth.companies.MLCF")
    _closed_keys(reconciliation, _RECONCILIATION_COMPANY_KEYS, "reconciliation.companies.MLCF")
    if review_manifest_state.get("source") != _REVIEW_SOURCE:
        _fail("review_manifest.source", "manifest source bindings drifted")
    if "MLCF" not in (financial_truth_state.get("pilot_symbols") or []):
        _fail("financial_truth.pilot_symbols", "MLCF is outside the retained qualification universe")
    if qualification.get("symbol") != "MLCF" or qualification.get("status") != "not_qualified":
        _fail("financial_truth.companies.MLCF", "qualification status drifted")
    financial_tie_out = _state_row(qualification.get("financial_tie_out"), "financial_truth.companies.MLCF.financial_tie_out")
    downstream = _state_row(qualification.get("downstream"), "financial_truth.companies.MLCF.downstream")
    qualification_policy = _state_row(qualification.get("policy"), "financial_truth.companies.MLCF.policy")
    share_state = _state_row(qualification.get("share_count"), "financial_truth.companies.MLCF.share_count")
    _closed_keys(financial_tie_out, _FINANCIAL_TIE_OUT_KEYS, "financial_truth.companies.MLCF.financial_tie_out")
    _closed_keys(downstream, _DOWNSTREAM_KEYS, "financial_truth.companies.MLCF.downstream")
    _closed_keys(qualification_policy, _QUALIFICATION_POLICY_KEYS, "financial_truth.companies.MLCF.policy")
    share_path = "financial_truth.companies.MLCF.share_count"
    _closed_keys(share_state, _SHARE_COUNT_KEYS, share_path)
    full_coverage = _state_row(qualification.get("model_ready_financial_statement_coverage"), "financial_truth.companies.MLCF.model_ready_financial_statement_coverage")
    _closed_keys(full_coverage, {"annual", "reported_quarter", "limitation"}, "financial_truth.companies.MLCF.model_ready_financial_statement_coverage")
    for key, required in (("annual", TARGET_ANNUAL_PERIODS), ("reported_quarter", TARGET_REPORTED_INTERIM_PERIODS)):
        schedule = _state_row(full_coverage.get(key), f"financial_truth.companies.MLCF.model_ready_financial_statement_coverage.{key}")
        _closed_keys(schedule, {"required", "present", "qualified_periods", "direct_flow_statement_periods", "direct_balance_sheet_periods", "derived_ebitda_periods", "derived_free_cash_flow_periods", "required_direct_metrics", "derived_metric_lineage"}, f"financial_truth.companies.MLCF.model_ready_financial_statement_coverage.{key}")
        _validate_coverage({field: schedule.get(field) for field in _COVERAGE_KEYS}, f"financial_truth.companies.MLCF.model_ready_financial_statement_coverage.{key}")
        if schedule.get("required") != required or schedule.get("present") != 0:
            _fail(f"financial_truth.companies.MLCF.model_ready_financial_statement_coverage.{key}", "full-statement schedule unexpectedly qualified")
    if financial_tie_out.get("status") != "blocked":
        _fail("financial_truth.companies.MLCF.financial_tie_out", "financial tie-out is no longer blocked")
    if downstream.get("forecast") != "blocked_financial_truth_not_qualified":
        _fail("financial_truth.companies.MLCF.downstream.forecast", "formal forecast gate drifted")
    if qualification_policy.get("raw_financial_values") != "not_emitted":
        _fail("financial_truth.companies.MLCF.policy.raw_financial_values", "raw financial output policy drifted")
    if reconciliation.get("symbol") != "MLCF" or reconciliation.get("source_conflict_count") != 0:
        _fail("reconciliation.companies.MLCF", "reconciliation conflict state drifted")
    share_status = share_state.get("status")
    if share_status == "missing_official_share_count_capital_note_tie_out":
        if share_state.get("available_on") is not None or share_state.get("source") is not None:
            _fail(share_path, "missing share-count status cannot carry source metadata")
    elif share_status == "official_share_count_capital_note_tied_out":
        _iso_date(share_state.get("available_on"), f"{share_path}.available_on")
        source = share_state.get("source")
        if not isinstance(source, dict):
            _fail(f"{share_path}.source", "tied-out share count requires a source object")
        _closed_keys(source, _SHARE_SOURCE_KEYS, f"{share_path}.source")
        for key in ("id", "label", "url"):
            if not isinstance(source.get(key), str) or not source[key].strip():
                _fail(f"{share_path}.source.{key}", "must be a non-empty string")
        if source.get("path") is not None and not isinstance(source.get("path"), str):
            _fail(f"{share_path}.source.path", "must be a string or null")
        if not isinstance(share_state.get("limitation"), str) or not share_state["limitation"].strip():
            _fail(f"{share_path}.limitation", "tied-out share count requires a limitation")
    else:
        _fail(share_path, "share-count tie-out status drifted")
    _validate_qualification_against_reconciliation(qualification, reconciliation, company_documents_state, research_index_state)
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


def evaluate_case(case: dict[str, Any], *, retained_state: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if not isinstance(retained_state, dict) or set(retained_state) != {"financial_truth", "company_documents", "review_manifest", "research_index", "reconciliation"}:
        _fail("retained_state", "authoritative state snapshot is required")
    validate_case(case)
    authoritative = build_case_from_retained_state(
        retained_state["financial_truth"],
        retained_state["company_documents"],
        retained_state["review_manifest"],
        retained_state["research_index"],
        retained_state["reconciliation"],
        as_of_date=case["as_of_date"],
    )
    if case != authoritative:
        _fail("case", "evaluated case does not match retained authoritative state")
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
    "IMMUTABLE_PUBLICATION_AUTHORITY_UNAVAILABLE",
    "RETAINED_MLCF_DOCUMENT_IDS",
    "build_case_from_retained_state",
    "evaluate_case",
    "validate_case",
]
