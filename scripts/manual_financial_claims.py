"""Deterministic gate for owner-verified manual financial claims.

Manual claims are not parser output and must never impersonate canonical
financial-statement facts.  This module accepts only owner-approved,
dual-reviewed official PSX claims and emits series-shaped rows with a distinct
source method/revision.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from psx_data import STATE, load_json


LEDGER_PATH = STATE / "company_intel" / "verified_manual_financial_claims.json"
MANUAL_SOURCE_METHOD = "owner_verified_manual_financial_claim_v1"
DEFAULT_SOURCE_REVISION = "manual_vision_v1"
ALLOWED_LINES = {"revenue", "profit_after_tax_attributable", "basic_eps"}
OFFICIAL_URL_RE = re.compile(r"^https://dps\.psx\.com\.pk/download/document/(\d+)\.pdf$")
PSX_DOC_RE = re.compile(r"^psx:(\d+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _stable_id(*parts: Any, prefix: str) -> str:
    text = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:24]}"


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _numeric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def _same_value(left: Any, right: Any) -> bool:
    lnum = _numeric(left)
    rnum = _numeric(right)
    return lnum is not None and rnum is not None and float(lnum) == float(rnum)


def _claim_key(claim: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(claim.get("symbol") or "").upper(),
        claim.get("line"),
        claim.get("period_end"),
        claim.get("consolidation"),
        claim.get("currency") or "PKR",
        claim.get("statement_type"),
        claim.get("unit"),
        claim.get("unit_multiplier"),
    )


def _series_conflict_index(existing_facts: list[dict[str, Any]]) -> dict[tuple[Any, ...], set[float]]:
    index: dict[tuple[Any, ...], set[float]] = {}
    for fact in existing_facts:
        if not isinstance(fact, dict) or fact.get("readiness") != "model_loadable":
            continue
        value = _numeric(fact.get("normalized_value"))
        if value is None:
            continue
        key = (
            str(fact.get("ticker") or "").upper(),
            fact.get("line") or fact.get("metric"),
            fact.get("period_end"),
            fact.get("consolidation"),
            fact.get("currency"),
            fact.get("statement_type"),
            fact.get("unit"),
            fact.get("unit_multiplier"),
        )
        index.setdefault(key, set()).add(float(value))
    return index


def _ledger_claims_by_id(path: Path = LEDGER_PATH) -> dict[str, dict[str, Any]]:
    ledger = load_json(path, {}) if path.exists() else {}
    claims = ledger.get("claims") if isinstance(ledger, dict) else []
    return {str(claim.get("claim_id")): claim for claim in claims or [] if isinstance(claim, dict) and claim.get("claim_id")}


def _validate_claim(
    claim: dict[str, Any],
    *,
    approval_ok: bool,
    seen_claim_ids: set[str],
    seen_claim_keys: dict[tuple[Any, ...], dict[str, Any]],
    existing_values: dict[tuple[Any, ...], set[float]],
) -> list[str]:
    flags: list[str] = []
    claim_id = str(claim.get("claim_id") or "")
    symbol = str(claim.get("symbol") or "").upper()
    line = claim.get("line")
    value = _numeric(claim.get("value"))
    page = claim.get("page")
    document_id = str(claim.get("document_id") or "")
    source_url = str(claim.get("source_url") or "")
    content_sha256 = str(claim.get("content_sha256") or "")
    period_end = _parse_iso_date(claim.get("period_end"))
    available_on = _parse_iso_date(claim.get("available_on"))
    doc_match = PSX_DOC_RE.fullmatch(document_id)
    url_match = OFFICIAL_URL_RE.fullmatch(source_url)
    if not approval_ok:
        flags.append("missing_owner_or_dual_review_approval")
    if claim.get("source_method") or claim.get("parser_version") or claim.get("parser_revision"):
        flags.append("manual_claim_must_not_supply_source_identity")
    if claim.get("review_status") != "pending_deterministic_gate":
        flags.append("invalid_manual_review_status")
    if not claim_id:
        flags.append("missing_claim_id")
    elif claim_id in seen_claim_ids:
        flags.append("duplicate_claim_id")
    if not symbol:
        flags.append("missing_symbol")
    if line not in ALLOWED_LINES:
        flags.append("unsupported_manual_line")
    if value is None:
        flags.append("nonfinite_manual_value")
    if claim.get("unit_multiplier") != 1:
        flags.append("invalid_manual_unit_multiplier")
    if claim.get("currency") not in (None, "PKR"):
        flags.append("invalid_manual_currency")
    if line == "basic_eps":
        if claim.get("unit") != "PKR/share":
            flags.append("invalid_manual_eps_unit")
    elif claim.get("unit") != "PKR":
        flags.append("invalid_manual_monetary_unit")
    if claim.get("consolidation") != "consolidated":
        flags.append("invalid_manual_consolidation")
    if claim.get("statement_type") != "income_statement":
        flags.append("invalid_manual_statement_type")
    if not doc_match:
        flags.append("invalid_manual_document_id")
    if not url_match:
        flags.append("non_official_manual_source_url")
    if doc_match and url_match and doc_match.group(1) != url_match.group(1):
        flags.append("manual_document_source_mismatch")
    if not SHA256_RE.fullmatch(content_sha256):
        flags.append("invalid_manual_content_sha256")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        flags.append("invalid_manual_page")
    if period_end is None:
        flags.append("invalid_manual_period_end")
    if available_on is None:
        flags.append("missing_or_invalid_manual_availability")
    elif period_end is not None and available_on <= period_end:
        flags.append("manual_available_before_period_end")
    column_role = claim.get("column_role") or "current_period"
    comparative_period = _parse_iso_date(claim.get("comparative_to_period_end"))
    if column_role == "current_period":
        if claim.get("comparative_to_period_end") not in (None, ""):
            flags.append("manual_current_has_comparative_linkage")
    elif column_role == "comparative_prior_period":
        if period_end is None or comparative_period is None or comparative_period <= period_end:
            flags.append("invalid_manual_comparative_linkage")
    else:
        flags.append("invalid_manual_column_role")

    key = _claim_key(claim)
    prior = seen_claim_keys.get(key)
    if prior:
        flags.append("duplicate_manual_claim_key")
        if not _same_value(prior.get("value"), value):
            flags.append("duplicate_manual_claim_conflict")
    if value is not None and any(float(value) != existing for existing in existing_values.get(key, set())):
        flags.append("manual_claim_conflicts_with_existing_model_fact")

    if claim_id:
        seen_claim_ids.add(claim_id)
    seen_claim_keys.setdefault(key, claim)
    return sorted(set(flags))


def _series_row(claim: dict[str, Any], source_revision: str) -> dict[str, Any]:
    claim_id = str(claim["claim_id"])
    symbol = str(claim["symbol"]).upper()
    line = str(claim["line"])
    source_url = str(claim["source_url"])
    page = int(claim["page"])
    value = claim["value"]
    fact_id = _stable_id(claim_id, claim.get("document_id"), claim.get("content_sha256"), page, prefix="manual_fact")
    series_id = _stable_id(symbol, line, claim_id, prefix="series")
    return {
        "series_id": series_id,
        "ticker": symbol,
        "metric": line,
        "line": line,
        "fact_id": fact_id,
        "parser_version": None,
        "parser_revision": None,
        "source_method": MANUAL_SOURCE_METHOD,
        "source_revision": source_revision,
        "manual_claim_id": claim_id,
        "available_on": claim.get("available_on"),
        "published_at": claim.get("available_on"),
        "retrieved_at": None,
        "statement_type": claim.get("statement_type"),
        "reported_label": line,
        "duration_months": 12,
        "column_role": claim.get("column_role") or "current_period",
        "comparative_to_period_end": claim.get("comparative_to_period_end"),
        "period_end": claim.get("period_end"),
        "period_type": "annual",
        "consolidation": claim.get("consolidation"),
        "currency": "PKR",
        "unit": claim.get("unit"),
        "unit_multiplier": claim.get("unit_multiplier"),
        "raw_value": str(value),
        "normalized_value": value,
        "document_id": claim.get("document_id"),
        "content_sha256": claim.get("content_sha256"),
        "source_url": source_url,
        "evidence": [{"page": page, "text": f"{symbol} {claim.get('period_end')} {line} owner-verified manual claim", "source_url": source_url}],
        "quality_flags": [],
        "readiness": "model_loadable",
    }


def qualified_manual_rows(
    ledger_path: Path = LEDGER_PATH,
    *,
    existing_facts: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ledger = load_json(ledger_path, {}) if ledger_path.exists() else {}
    claims = ledger.get("claims") if isinstance(ledger, dict) else []
    approval = ledger.get("approval") if isinstance(ledger, dict) else {}
    source_revision = str(ledger.get("review_revision") or DEFAULT_SOURCE_REVISION)
    approval_ok = (
        isinstance(approval, dict)
        and ledger.get("schema_version") == 1
        and ledger.get("append_only") is True
        and ledger.get("review_revision") == DEFAULT_SOURCE_REVISION
        and approval.get("owner_confirmed") is True
        and isinstance(approval.get("reviewers"), list)
        and len({str(item) for item in approval.get("reviewers") if item}) >= 2
    )
    ledger_flags = []
    if not isinstance(ledger, dict):
        ledger_flags.append("manual_ledger_not_object")
    else:
        if ledger.get("schema_version") != 1:
            ledger_flags.append("invalid_manual_ledger_schema_version")
        if ledger.get("append_only") is not True:
            ledger_flags.append("manual_ledger_not_append_only")
        if ledger.get("review_revision") != DEFAULT_SOURCE_REVISION:
            ledger_flags.append("invalid_manual_source_revision")
        if not isinstance(claims, list):
            ledger_flags.append("manual_claims_not_list")
    existing_values = _series_conflict_index(existing_facts or [])
    seen_claim_ids: set[str] = set()
    seen_claim_keys: dict[tuple[Any, ...], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for claim in claims or []:
        if not isinstance(claim, dict):
            rejected.append({"claim_id": None, "flags": ["malformed_manual_claim"]})
            continue
        flags = _validate_claim(
            claim,
            approval_ok=approval_ok,
            seen_claim_ids=seen_claim_ids,
            seen_claim_keys=seen_claim_keys,
            existing_values=existing_values,
        )
        if flags:
            rejected.append({"claim_id": claim.get("claim_id"), "flags": flags})
            continue
        rows.append(_series_row(claim, source_revision))
    if ledger_flags:
        rejected = [{"claim_id": item.get("claim_id") if isinstance(item, dict) else None, "flags": ledger_flags} for item in claims or []] or [{"claim_id": None, "flags": ledger_flags}]
        rows = []
    meta = {
        "source": "state/company_intel/verified_manual_financial_claims.json",
        "source_method": MANUAL_SOURCE_METHOD,
        "source_revision": source_revision,
        "claim_count": len(claims or []),
        "qualified_count": len(rows),
        "rejected_count": len(rejected),
        "rejected_claims": rejected,
    }
    return rows, meta


def is_qualified_manual_fact(fact: dict[str, Any]) -> bool:
    if not isinstance(fact, dict):
        return False
    if fact.get("source_method") != MANUAL_SOURCE_METHOD or fact.get("source_revision") != DEFAULT_SOURCE_REVISION or not fact.get("manual_claim_id"):
        return False
    if fact.get("parser_version") or fact.get("parser_revision"):
        return False
    evidence = fact.get("evidence") if isinstance(fact.get("evidence"), list) else []
    first_evidence = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
    page = first_evidence.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        return False
    expected_fact_id = _stable_id(fact.get("manual_claim_id"), fact.get("document_id"), fact.get("content_sha256"), page, prefix="manual_fact")
    if fact.get("fact_id") != expected_fact_id:
        return False
    if fact.get("duration_months") != 12 or fact.get("period_type") != "annual":
        return False
    if fact.get("consolidation") != "consolidated" or fact.get("currency") != "PKR":
        return False
    if fact.get("statement_type") != "income_statement" or fact.get("line") not in ALLOWED_LINES:
        return False
    if fact.get("line") == "basic_eps":
        if fact.get("unit") != "PKR/share" or fact.get("unit_multiplier") != 1:
            return False
    elif fact.get("unit") != "PKR" or fact.get("unit_multiplier") != 1:
        return False
    if _numeric(fact.get("normalized_value")) is None:
        return False
    if _parse_iso_date(fact.get("period_end")) is None:
        return False
    available = _parse_iso_date(fact.get("available_on"))
    period = _parse_iso_date(fact.get("period_end"))
    if available is None or period is None or available <= period:
        return False
    doc_match = PSX_DOC_RE.fullmatch(str(fact.get("document_id") or ""))
    url_match = OFFICIAL_URL_RE.fullmatch(str(fact.get("source_url") or ""))
    if not (doc_match and url_match and doc_match.group(1) == url_match.group(1)):
        return False
    if not SHA256_RE.fullmatch(str(fact.get("content_sha256") or "")):
        return False
    claim = _ledger_claims_by_id().get(str(fact.get("manual_claim_id") or ""))
    if not isinstance(claim, dict):
        return False
    if (
        str(claim.get("symbol") or "").upper() != fact.get("ticker")
        or claim.get("line") != fact.get("line")
        or claim.get("period_end") != fact.get("period_end")
        or claim.get("document_id") != fact.get("document_id")
        or claim.get("source_url") != fact.get("source_url")
        or claim.get("content_sha256") != fact.get("content_sha256")
        or claim.get("available_on") != fact.get("available_on")
        or claim.get("unit") != fact.get("unit")
        or claim.get("unit_multiplier") != fact.get("unit_multiplier")
        or not _same_value(claim.get("value"), fact.get("normalized_value"))
    ):
        return False
    claim_role = claim.get("column_role") or "current_period"
    if fact.get("column_role") != claim_role:
        return False
    if claim_role == "current_period":
        return claim.get("comparative_to_period_end") in (None, "") and fact.get("comparative_to_period_end") in (None, "")
    if claim_role != "comparative_prior_period":
        return False
    comparative = _parse_iso_date(claim.get("comparative_to_period_end"))
    return (
        comparative is not None
        and comparative > period
        and fact.get("comparative_to_period_end") == claim.get("comparative_to_period_end")
    )
