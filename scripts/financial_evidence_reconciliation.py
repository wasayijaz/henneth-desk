"""Financial Evidence Reconciliation v1.

This module reconciles retained financial statement facts into an evidence
ledger for earnings-bridge readiness. It does not ingest documents, infer
values, select through conflicts, or activate forecasts/valuations.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any

from forecast_contract import (
    BLOCKED_OUTPUT_STATUS,
    REQUIRED_LINES,
    official_financial_fact_provenance,
    qualified_financial_fact_source,
    qualified_periods,
)


RECONCILIATION_VERSION = "financial_evidence_reconciliation_v1"
EARNINGS_BRIDGE_VERSION = "earnings_bridge_readiness_v1"
REQUIRED_STATUS = ("eligible", "audit_only", "quarantined", "missing")
ELIGIBLE_LINES = tuple(REQUIRED_LINES)
AUDIT_ONLY_REASONS = {
    "readiness_is_audit_only",
    "legacy_extractor_not_model_eligible",
    "legacy_parser_revision_quarantine",
    "missing_period_end",
    "missing_available_on",
    "missing_consolidation_basis",
}


def stable_id(prefix: str, *parts: Any) -> str:
    text = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]}"


def iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
        return text
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _retrieved_cutoff(financial_series: dict[str, Any], fallback: Any) -> str | None:
    """Advance a current reconciliation snapshot to facts actually observed by CI.

    ``available_on`` remains the per-fact publication gate.  It is deliberately
    excluded here so a future-dated filing cannot advance the snapshot merely
    by appearing in retained state.  A fact's retained ``retrieved_at`` is the
    actual Henneth availability boundary for a newly restaged source.
    """
    candidates = [str(fallback).strip()] if fallback else []
    for row in (financial_series.get("tickers") or {}).values():
        if not isinstance(row, dict):
            continue
        for fact in row.get("facts") or []:
            if isinstance(fact, dict) and fact.get("retrieved_at"):
                candidates.append(str(fact["retrieved_at"]).strip())

    def key(value: str) -> datetime | None:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    dated = [(value, key(value)) for value in candidates]
    dated = [(value, parsed) for value, parsed in dated if parsed is not None]
    if not dated:
        return str(fallback) if fallback else None
    return max(dated, key=lambda item: item[1])[0]


def _num(value: Any) -> float | int | None:
    import math

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def _first_evidence(fact: dict[str, Any]) -> dict[str, Any]:
    evidence = fact.get("evidence") or []
    return evidence[0] if evidence and isinstance(evidence[0], dict) else {}


def _evidence_row(fact: dict[str, Any]) -> dict[str, Any]:
    evidence = _first_evidence(fact)
    document_id = str(fact.get("document_id") or "")
    row = {
        "document_id": fact.get("document_id"),
        "fact_id": fact.get("fact_id"),
        "content_sha256": fact.get("content_sha256"),
        "source_url": fact.get("source_url"),
        "source": "PSX DPS" if document_id.startswith("psx:") else "Issuer registry" if document_id.startswith("issuer:") else "unknown",
        "page": evidence.get("page"),
        "text": evidence.get("text"),
        "available_on": fact.get("available_on"),
        "published_at": fact.get("published_at"),
        "retrieved_at": fact.get("retrieved_at"),
    }
    if document_id.startswith("issuer:"):
        row["issuer_registry_binding"] = fact.get("issuer_registry_binding")
    return row


def _source_ok(fact: dict[str, Any]) -> bool:
    return official_financial_fact_provenance(fact)


def classification_reasons(fact: dict[str, Any], as_of: str | None = None) -> list[str]:
    reasons: list[str] = []
    period_end = iso_date(fact.get("period_end"))
    available_on = iso_date(fact.get("available_on"))
    as_of_date = iso_date(as_of)
    if fact.get("line") not in ELIGIBLE_LINES:
        reasons.append("outside_required_earnings_bridge_metric_set")
    if not qualified_financial_fact_source(fact):
        reasons.append("unqualified_financial_fact_source")
    if fact.get("readiness") == "audit_only":
        reasons.append("readiness_is_audit_only")
    elif fact.get("readiness") != "model_loadable":
        reasons.append("readiness_not_model_loadable")
    if fact.get("duration_months") != 12:
        reasons.append("not_twelve_month_annual")
    if fact.get("period_type") != "annual":
        reasons.append("not_annual_period")
    if fact.get("consolidation") != "consolidated":
        reasons.append("missing_or_nonconsolidated_basis")
    if fact.get("currency") != "PKR":
        reasons.append("missing_or_non_pkr_currency")
    if fact.get("statement_type") != "income_statement":
        reasons.append("not_income_statement")
    if period_end is None:
        reasons.append("missing_period_end")
    if available_on is None:
        reasons.append("missing_available_on")
    elif period_end is not None and available_on <= period_end:
        reasons.append("available_on_not_after_period_end")
    elif as_of_date is not None and available_on > as_of_date:
        reasons.append("available_on_after_reconciliation_as_of")
    if _num(fact.get("normalized_value")) is None:
        reasons.append("missing_numeric_normalized_value")
    if not _source_ok(fact):
        reasons.append("missing_required_provenance")
    for field in ("quality_flags", "conflict_flags"):
        flags = fact.get(field)
        if isinstance(flags, list):
            reasons.extend(str(flag) for flag in flags if flag)
    return sorted(set(reasons))


def fact_status(fact: dict[str, Any], as_of: str | None = None) -> str:
    reasons = classification_reasons(fact, as_of)
    if not reasons:
        return "eligible"
    if fact.get("readiness") == "audit_only":
        return "audit_only"
    return "quarantined"


def _period_sort_key(value: Any) -> str:
    return str(value or "9999-99-99")


def _fact_sort_key(fact: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(fact.get("line") or fact.get("metric") or ""),
        _period_sort_key(fact.get("period_end")),
        str(fact.get("document_id") or ""),
        str(fact.get("fact_id") or ""),
    )


def _published_facts_as_of(facts: list[dict[str, Any]], as_of: str | None) -> tuple[list[dict[str, Any]], int]:
    """Keep future-dated evidence in the durable series, never in this snapshot."""
    cutoff = iso_date(as_of)
    if cutoff is None:
        return list(facts), 0
    published: list[dict[str, Any]] = []
    withheld = 0
    for fact in facts:
        available_on = iso_date(fact.get("available_on"))
        if available_on is not None and available_on > cutoff:
            withheld += 1
            continue
        published.append(fact)
    return published, withheld


def _fact_record(symbol: str, fact: dict[str, Any], as_of: str | None = None) -> dict[str, Any]:
    status = fact_status(fact, as_of)
    reasons = classification_reasons(fact, as_of)
    fact_id = fact.get("fact_id")
    period_end = fact.get("period_end")
    metric = fact.get("line") or fact.get("metric")
    return {
        "reconciliation_id": stable_id("finrec", symbol, metric, period_end, fact_id),
        "evidence_id": stable_id("finev", symbol, fact.get("document_id"), fact_id, _first_evidence(fact).get("page")),
        "symbol": symbol,
        "metric": metric,
        "period_end": period_end,
        "period_type": fact.get("period_type") or "unknown",
        "duration_months": fact.get("duration_months"),
        "statement_type": fact.get("statement_type"),
        "consolidation": fact.get("consolidation") or "unknown",
        "currency": fact.get("currency"),
        "unit": fact.get("unit"),
        "unit_multiplier": fact.get("unit_multiplier"),
        "raw_value": fact.get("raw_value"),
        "normalized_value": fact.get("normalized_value"),
        "status": status,
        "reasons": reasons,
        "source": _evidence_row(fact),
        "parser": {
            "version": fact.get("parser_version"),
            "revision": fact.get("parser_revision"),
        },
        "evidence_label": "fact_source_reported" if status == "eligible" else "missing_required_source" if "missing_required_provenance" in reasons else "stale_source" if "legacy_parser_revision_quarantine" in reasons else "unknown",
        "confidence": "high" if status == "eligible" else "low",
    }


def _same_slot_key(fact: dict[str, Any]) -> tuple[Any, ...]:
    return (
        fact.get("line") or fact.get("metric"),
        fact.get("period_end"),
        fact.get("period_type"),
        fact.get("duration_months"),
        fact.get("consolidation"),
        fact.get("currency"),
        fact.get("statement_type"),
        fact.get("unit"),
        fact.get("unit_multiplier"),
    )


def _conflict_eligible_fact(fact: dict[str, Any], as_of: str | None) -> bool:
    """Only otherwise qualified load-bearing facts can create blocking conflicts."""
    return (
        fact.get("line") in ELIGIBLE_LINES
        and not classification_reasons(fact, as_of)
    )


def _conflicts(symbol: str, facts: list[dict[str, Any]], as_of: str | None = None) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for fact in facts:
        if not _conflict_eligible_fact(fact, as_of):
            continue
        grouped.setdefault(_same_slot_key(fact), []).append(fact)
    rows = []
    for key, group in sorted(grouped.items(), key=lambda item: tuple(str(v or "") for v in item[0])):
        values = {_num(fact.get("normalized_value")) for fact in group}
        values.discard(None)
        if len(group) > 1 and len(values) > 1:
            metric, period_end, period_type, duration_months, consolidation, currency, statement_type, unit, unit_multiplier = key
            rows.append({
                "conflict_id": stable_id("finconflict", symbol, metric, period_end, consolidation, currency, statement_type, unit, unit_multiplier),
                "symbol": symbol,
                "metric": metric,
                "period_end": period_end,
                "period_type": period_type,
                "duration_months": duration_months,
                "consolidation": consolidation,
                "currency": currency,
                "statement_type": statement_type,
                "unit": unit,
                "unit_multiplier": unit_multiplier,
                "status": "quarantined",
                "reason": "conflicting_values_retained_no_silent_selection",
                "values": [
                    {
                        "fact_id": fact.get("fact_id"),
                        "document_id": fact.get("document_id"),
                        "normalized_value": fact.get("normalized_value"),
                        "source_url": fact.get("source_url"),
                        "page": _first_evidence(fact).get("page"),
                    }
                    for fact in sorted(group, key=lambda item: str(item.get("fact_id") or ""))
                ],
            })
    return rows


def _coverage_periods(coverage_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows = coverage_row.get("required_annual_periods")
    return rows if isinstance(rows, list) else []


def _missing_slots(symbol: str, coverage_row: dict[str, Any], facts: list[dict[str, Any]], as_of: str | None = None) -> list[dict[str, Any]]:
    eligible = [
        fact for fact in facts
        if fact_status(fact, as_of) == "eligible"
    ]
    present = {
        (fact.get("line"), fact.get("period_end"))
        for fact in eligible
    }
    rows = []
    for slot in _coverage_periods(coverage_row):
        period_end = slot.get("period_end")
        for metric in ELIGIBLE_LINES:
            if period_end and (metric, period_end) in present:
                continue
            rows.append({
                "reconciliation_id": stable_id("finmissing", symbol, metric, period_end or slot.get("slot")),
                "symbol": symbol,
                "metric": metric,
                "period_end": period_end,
                "period_type": "annual",
                "status": "missing",
                "reason": "missing_eligible_reported_fact_for_required_annual_slot",
                "slot": slot.get("slot"),
                "period_evidence_status": "explicit" if period_end else "missing_explicit_annual_period_evidence",
                "source": {
                    "document_id": slot.get("document_id"),
                    "title": slot.get("title"),
                    "matched_text": slot.get("matched_text"),
                },
            })
    return rows


def company_reconciliation(
    symbol: str,
    facts: list[dict[str, Any]],
    coverage_row: dict[str, Any] | None,
    model_row: dict[str, Any] | None,
    readiness_row: dict[str, Any] | None,
    as_of: str | None = None,
) -> dict[str, Any]:
    facts = [fact for fact in facts if isinstance(fact, dict)]
    facts, future_source_fact_count = _published_facts_as_of(facts, as_of)
    coverage_row = coverage_row or {}
    model_row = model_row or {}
    readiness_row = readiness_row or {}
    conflicts = _conflicts(symbol, facts, as_of)
    conflicted_fact_ids = {
        value.get("fact_id")
        for conflict in conflicts
        for value in conflict.get("values") or []
        if value.get("fact_id")
    }
    fact_records = [_fact_record(symbol, fact, as_of) for fact in sorted(facts, key=_fact_sort_key)]
    for record in fact_records:
        if record.get("source", {}).get("fact_id") not in conflicted_fact_ids:
            continue
        record["status"] = "quarantined"
        record["reasons"] = sorted(set((record.get("reasons") or []) + ["conflicting_values_retained_no_silent_selection"]))
        record["evidence_label"] = "contradicted_source"
        record["confidence"] = "low"
    missing_slots = _missing_slots(symbol, coverage_row, facts, as_of)
    status_counts = {status: 0 for status in REQUIRED_STATUS}
    for record in fact_records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
    status_counts["missing"] = len(missing_slots)
    qualified = qualified_periods(facts)
    readiness_qualified_count = readiness_row.get("qualified_period_count") or 0
    earnings_bridge_status = "ready_for_bridge_calculation" if len(qualified) >= 2 and not conflicts else "blocked"
    if readiness_qualified_count == 0:
        earnings_bridge_status = "blocked"
    return {
        "symbol": symbol,
        "status": "blocked" if status_counts["eligible"] == 0 or conflicts or missing_slots else "eligible_for_review",
        "eligible_fact_count": status_counts.get("eligible", 0),
        "audit_only_fact_count": status_counts.get("audit_only", 0),
        "quarantined_fact_count": status_counts.get("quarantined", 0),
        "missing_slot_count": len(missing_slots),
        "source_conflict_count": len(conflicts),
        "withheld_future_source_fact_count": future_source_fact_count,
        "facts": fact_records,
        "conflicts": conflicts,
        "missing_slots": missing_slots,
        "qualified_periods": qualified,
        "readiness": {
            "forecast_readiness_status": readiness_row.get("status") or "blocked",
            "forecast_qualified_period_count": readiness_qualified_count,
            "financial_model_input_status": model_row.get("status") or "unknown",
            "earnings_bridge_status": earnings_bridge_status,
            "forecast": BLOCKED_OUTPUT_STATUS["forecast"],
            "valuation": BLOCKED_OUTPUT_STATUS["valuation"],
            "market_expectations": BLOCKED_OUTPUT_STATUS["market_expectations"],
            "reason": "formal_forecast_readiness_remains_blocked",
        },
    }


def build_reconciliation(
    pilot_symbols: list[str],
    financial_series: dict[str, Any],
    financial_coverage: dict[str, Any],
    financial_model_inputs: dict[str, Any],
    forecast_readiness: dict[str, Any],
) -> dict[str, Any]:
    companies = {}
    series_rows = financial_series.get("tickers") or {}
    coverage_rows = financial_coverage.get("companies") or {}
    model_rows = financial_model_inputs.get("companies") or {}
    readiness_rows = forecast_readiness.get("companies") or {}
    as_of = _retrieved_cutoff(financial_series, forecast_readiness.get("as_of"))
    for symbol in pilot_symbols:
        facts = (series_rows.get(symbol) or {}).get("facts") or []
        companies[symbol] = company_reconciliation(
            symbol,
            facts,
            coverage_rows.get(symbol),
            model_rows.get(symbol),
            readiness_rows.get(symbol),
            as_of,
        )
    total = {
        "eligible_fact_count": sum(row["eligible_fact_count"] for row in companies.values()),
        "audit_only_fact_count": sum(row["audit_only_fact_count"] for row in companies.values()),
        "quarantined_fact_count": sum(row["quarantined_fact_count"] for row in companies.values()),
        "missing_slot_count": sum(row["missing_slot_count"] for row in companies.values()),
        "source_conflict_count": sum(row["source_conflict_count"] for row in companies.values()),
        "withheld_future_source_fact_count": sum(row["withheld_future_source_fact_count"] for row in companies.values()),
        "forecast_ready_company_count": sum(1 for row in (readiness_rows.values()) if row.get("status") == "input_ready"),
    }
    return {
        "schema_version": 1,
        "reconciliation_version": RECONCILIATION_VERSION,
        "earnings_bridge_version": EARNINGS_BRIDGE_VERSION,
        "pilot_symbols": list(pilot_symbols),
        "as_of": as_of,
        "source": {
            "company_financial_series": "state/company_financial_series.json",
            "financial_coverage": "state/company_intel/financial_coverage.json",
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
            "forecast_readiness": "state/company_intel/forecast_readiness.json",
        },
        "policy": {
            "research_only": True,
            "official_sources_only": True,
            "no_external_document_ingestion": True,
            "no_audit_only_promotion": True,
            "no_silent_conflict_selection": True,
            "no_lookahead": True,
            "no_numeric_forecast": True,
            "no_numeric_valuation": True,
            "forecast": "blocked_insufficient_qualified_history",
            "valuation": "blocked_insufficient_qualified_history",
            "market_expectations": "blocked_insufficient_qualified_history",
        },
        "summary": {
            "company_count": len(companies),
            **total,
        },
        "companies": companies,
    }
