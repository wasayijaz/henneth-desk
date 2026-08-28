"""Deterministically qualify retained financial evidence without promoting it.

This is a strict Part 1 scorecard, not a forecasting or valuation model.  It
uses only already-reconciled eligible facts and retained document metadata. It
never reads a PDF, fetches a provider, writes a source record, or emits a
financial value.
"""
from __future__ import annotations

from typing import Any


REQUIRED_ANNUAL_METRICS = ("revenue", "profit_after_tax_attributable", "basic_eps")
TARGET_ANNUAL_PERIODS = 5
TARGET_REPORTED_INTERIM_PERIODS = 8


def _facts_by_period(row: dict[str, Any], metric_set: tuple[str, ...]) -> dict[str, set[str]]:
    periods: dict[str, set[str]] = {}
    for fact in row.get("facts") or []:
        if not isinstance(fact, dict) or fact.get("status") != "eligible":
            continue
        if fact.get("period_type") != "annual" or fact.get("statement_type") != "income_statement":
            continue
        if fact.get("consolidation") != "consolidated" or fact.get("metric") not in metric_set:
            continue
        period_end = str(fact.get("period_end") or "")
        if period_end:
            periods.setdefault(period_end, set()).add(str(fact.get("metric")))
    return periods


def _eligible_cashflow_periods(row: dict[str, Any]) -> list[str]:
    periods = set()
    for fact in row.get("facts") or []:
        if not isinstance(fact, dict) or fact.get("status") != "eligible":
            continue
        if (
            fact.get("metric") == "operating_cash_flow"
            and fact.get("period_type") == "annual"
            and fact.get("statement_type") == "cash_flow_statement"
            and fact.get("consolidation") == "consolidated"
            and fact.get("period_end")
        ):
            periods.add(str(fact["period_end"]))
    return sorted(periods, reverse=True)


def _documented_interim_periods(coverage_row: dict[str, Any]) -> list[str]:
    periods = set()
    for doc in coverage_row.get("indexed_official_financial_docs") or []:
        if not isinstance(doc, dict):
            continue
        period = doc.get("safe_period") or {}
        if period.get("period_type") == "interim" and period.get("period_end"):
            periods.add(str(period["period_end"]))
    return sorted(periods, reverse=True)


def _qualified_quarter_periods(row: dict[str, Any]) -> list[str]:
    periods: dict[str, set[str]] = {}
    for fact in row.get("facts") or []:
        if not isinstance(fact, dict) or fact.get("status") != "eligible":
            continue
        if fact.get("period_type") not in {"quarterly", "interim"} or fact.get("duration_months") != 3:
            continue
        if fact.get("statement_type") != "income_statement" or fact.get("consolidation") != "consolidated":
            continue
        if fact.get("metric") not in REQUIRED_ANNUAL_METRICS or not fact.get("period_end"):
            continue
        periods.setdefault(str(fact["period_end"]), set()).add(str(fact["metric"]))
    return sorted(
        (period for period, metrics in periods.items() if set(REQUIRED_ANNUAL_METRICS).issubset(metrics)),
        reverse=True,
    )


def _share_count_tie_out(records: list[dict[str, Any]], symbol: str) -> dict[str, Any]:
    matches = [
        record for record in records
        if isinstance(record, dict)
        and record.get("symbol") == symbol
        and record.get("metric") == "shares_out"
        and record.get("record_type") == "official_share_count_capital_note_tie_out"
        and record.get("approved") is True
        and record.get("available_on")
        and isinstance(record.get("source"), dict)
    ]
    if not matches:
        return {"status": "missing_official_share_count_capital_note_tie_out", "available_on": None, "source": None}
    record = sorted(matches, key=lambda item: str(item.get("available_on")), reverse=True)[0]
    source = record.get("source") or {}
    return {
        "status": "official_share_count_capital_note_tied_out",
        "available_on": record.get("available_on"),
        "source": {
            "id": source.get("id"),
            "label": source.get("label"),
            "path": source.get("path"),
            "url": source.get("url"),
        },
        "limitation": "The source-bound official capital-note record satisfies the share-count tie-out gate.",
    }


def _candidate_documents(coverage_row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": doc.get("document_id"),
            "title": doc.get("title"),
            "published_at": doc.get("published_at"),
            "source_url": doc.get("source_url"),
            "safe_period": doc.get("safe_period"),
            "reason": "retained official document candidate; owner approval is required before any restage",
        }
        for doc in (coverage_row.get("qualification_queue") or {}).get("candidate_documents") or []
        if isinstance(doc, dict) and doc.get("document_id") and doc.get("source_url")
    ][:5]


def company_qualification(
    symbol: str,
    reconciliation: dict[str, Any],
    coverage: dict[str, Any],
    records: list[dict[str, Any]],
    cement: dict[str, Any],
) -> dict[str, Any]:
    metric_periods = _facts_by_period(reconciliation, REQUIRED_ANNUAL_METRICS)
    annual_periods = sorted(
        (period for period, metrics in metric_periods.items() if set(REQUIRED_ANNUAL_METRICS).issubset(metrics)),
        reverse=True,
    )
    documented_interim_periods = _documented_interim_periods(coverage)
    quarter_periods = _qualified_quarter_periods(reconciliation)
    cashflow_periods = _eligible_cashflow_periods(reconciliation)
    shares = _share_count_tie_out(records, symbol)
    conflict_count = int(reconciliation.get("source_conflict_count") or 0)
    gaps = []
    if len(annual_periods) < TARGET_ANNUAL_PERIODS:
        gaps.append({"requirement": "qualified_annual_income_triplets", "required": TARGET_ANNUAL_PERIODS, "present": len(annual_periods), "status": "blocked"})
    if len(quarter_periods) < TARGET_REPORTED_INTERIM_PERIODS:
        gaps.append({"requirement": "qualified_reported_quarter_fact_sets", "required": TARGET_REPORTED_INTERIM_PERIODS, "present": len(quarter_periods), "status": "blocked"})
    if len(cashflow_periods) < TARGET_ANNUAL_PERIODS:
        gaps.append({"requirement": "qualified_annual_operating_cash_flow", "required": TARGET_ANNUAL_PERIODS, "present": len(cashflow_periods), "status": "blocked"})
    share_tied_out = shares.get("status") == "official_share_count_capital_note_tied_out"
    if not share_tied_out:
        gaps.append({"requirement": "official_share_count_capital_note_tie_out", "required": 1, "present": 0, "status": "blocked"})
    if conflict_count:
        gaps.append({"requirement": "unresolved_financial_source_conflicts", "required": 0, "present": conflict_count, "status": "blocked"})
    qualified = (
        len(annual_periods) >= TARGET_ANNUAL_PERIODS
        and len(quarter_periods) >= TARGET_REPORTED_INTERIM_PERIODS
        and len(cashflow_periods) >= TARGET_ANNUAL_PERIODS
        and share_tied_out
        and conflict_count == 0
    )
    return {
        "symbol": symbol,
        "status": "qualified" if qualified else "not_qualified",
        "qualification_scope": "retained_reported_financial_truth",
        "annual_income_triplets": {"required": TARGET_ANNUAL_PERIODS, "present": len(annual_periods), "qualified_periods": annual_periods},
        "qualified_reported_quarter_fact_sets": {"required": TARGET_REPORTED_INTERIM_PERIODS, "present": len(quarter_periods), "qualified_periods": quarter_periods},
        "documented_interim_metadata": {"present": len(documented_interim_periods), "documented_periods": documented_interim_periods, "limitation": "Document metadata proves a retained official reporting period, not parsed qualified quarterly financial facts and does not satisfy the eight-quarter gate."},
        "annual_operating_cash_flow": {"required": TARGET_ANNUAL_PERIODS, "present": len(cashflow_periods), "qualified_periods": cashflow_periods},
        "share_count": shares,
        "financial_tie_out": {"status": "qualified" if qualified else "blocked", "reason": "all strict financial-truth gates satisfied" if qualified else "requires five qualified annual income triplets, eight qualified reported-quarter fact sets, five qualified annual operating-cash-flow periods, an official share-count capital-note tie-out, and no unresolved conflicts"},
        "operating_lane": {"status": cement.get("status") or "not_applicable", "activation_status": cement.get("activation_status") or "not_applicable"},
        "evidence_gaps": gaps,
        "candidate_documents": _candidate_documents(coverage),
        "downstream": {"forecast": "not_activated_owner_approved_forward_inputs_required" if qualified else "blocked_financial_truth_not_qualified", "valuation": "not_activated_owner_approved_valuation_inputs_required" if qualified else "blocked_financial_truth_not_qualified", "market_expectations": "not_activated_owner_approved_forward_inputs_required" if qualified else "blocked_financial_truth_not_qualified"},
        "policy": {"raw_financial_values": "not_emitted", "restage": "owner_approval_required", "forecasts": "not_emitted", "valuation": "not_emitted", "market_expectations": "not_emitted"},
    }


def build_qualification(
    pilot: list[str],
    reconciliation_state: dict[str, Any],
    coverage_state: dict[str, Any],
    assumptions_state: dict[str, Any],
    cement_state: dict[str, Any],
) -> dict[str, Any]:
    reconciliations = reconciliation_state.get("companies") or {}
    coverages = coverage_state.get("companies") or {}
    cements = cement_state.get("companies") or {}
    records = [record for record in assumptions_state.get("records") or [] if isinstance(record, dict)]
    companies = {
        symbol: company_qualification(symbol, reconciliations.get(symbol) or {}, coverages.get(symbol) or {}, records, cements.get(symbol) or {})
        for symbol in pilot
    }
    ordered = sorted(
        companies.values(),
        key=lambda row: (
            -int((row.get("annual_income_triplets") or {}).get("present") or 0),
            -int((row.get("qualified_reported_quarter_fact_sets") or {}).get("present") or 0),
            -int((row.get("annual_operating_cash_flow") or {}).get("present") or 0),
            0 if (row.get("operating_lane") or {}).get("status") == "audit_only_series_available" else 1,
            row.get("symbol") or "",
        ),
    )
    for rank, row in enumerate(ordered, start=1):
        row["candidate_rank"] = rank
        row["selection_status"] = "qualified_financial_truth" if rank == 1 and row.get("status") == "qualified" else ("leading_candidate_not_golden" if rank == 1 else "not_selected")
    leader = ordered[0] if ordered else None
    return {
        "schema_version": "financial_truth_qualification_v1",
        "pilot_symbols": pilot,
        "source": "retained_state_only",
        "policy": {"does_not_fetch": True, "does_not_parse_documents": True, "does_not_promote_audit_only_facts": True, "does_not_emit_financial_values": True, "does_not_activate_formal_engines": True},
        "selection": {
            "status": ("qualified_financial_truth" if leader and leader.get("status") == "qualified" else "leading_candidate_not_golden") if leader else "no_candidate",
            "leader_symbol": leader.get("symbol") if leader else None,
            "reason": "ranked only by retained source-grounded coverage; the leader remains unqualified until every financial-truth gate is satisfied",
        },
        "companies": companies,
        "summary": {"company_count": len(companies), "qualified_company_count": sum(1 for row in companies.values() if row.get("status") == "qualified"), "leader_symbol": leader.get("symbol") if leader else None},
    }
