"""Fail-closed qualification for model-ready reported financial truth.

The legacy three-line earnings readiness remains descriptive elsewhere. This
module is the authoritative activation gate: a company needs five source-bound
annual statement schedules, eight source-bound reported-quarter schedules,
derived EBITDA/FCF lineage, a share-count tie-out, and no canonical conflicts.
It never parses, fetches, promotes, or emits a financial value.
"""
from __future__ import annotations

from typing import Any


TARGET_ANNUAL_PERIODS = 5
TARGET_REPORTED_INTERIM_PERIODS = 8
REQUIRED_ANNUAL_METRICS = ("revenue", "profit_after_tax_attributable", "basic_eps")
INCOME_STATEMENT_METRICS = (
    "revenue", "gross_profit", "operating_profit", "finance_cost",
    "profit_before_tax", "tax_expense", "profit_after_tax_attributable", "basic_eps",
)
BALANCE_SHEET_METRICS = (
    "cash_and_cash_equivalents", "trade_receivables", "inventories",
    "total_current_assets", "property_plant_equipment", "total_assets",
    "short_term_borrowings", "long_term_borrowings", "trade_payables", "total_equity",
)
CASH_FLOW_METRICS = (
    "operating_cash_flow", "capital_expenditure", "net_cash_from_investing_activities",
    "net_cash_from_financing_activities", "dividends_paid",
)
ANNUAL_QUARTERLY_INCOME_METRICS = INCOME_STATEMENT_METRICS + ("ebitda",)
ANNUAL_QUARTERLY_CASHFLOW_METRICS = CASH_FLOW_METRICS + ("depreciation_amortization",)
REPORTED_QUARTER_SCOPE = "reported_quarter_financial_truth_gate"
REPORTED_QUARTER_BALANCE_SCOPE = "reported_quarter_balance_sheet_financial_truth_gate"
ANNUAL_INCOME_SCOPE = "annual_income_financial_truth_gate"
ANNUAL_BALANCE_SCOPE = "annual_balance_sheet_financial_truth_gate"
ANNUAL_CASHFLOW_SCOPE = "annual_cash_flow_financial_truth_gate"


def _eligible_facts(row: dict[str, Any], scopes: set[str]) -> list[dict[str, Any]]:
    return [fact for fact in row.get("facts") or [] if isinstance(fact, dict)
            and fact.get("status") == "eligible" and fact.get("eligibility_scope") in scopes
            and fact.get("consolidation") == "consolidated" and fact.get("period_end")]


def _periods_with_metrics(row: dict[str, Any], metrics: tuple[str, ...], scopes: set[str]) -> list[str]:
    periods: dict[str, set[str]] = {}
    for fact in _eligible_facts(row, scopes):
        metric = str(fact.get("metric") or "")
        if metric in metrics:
            periods.setdefault(str(fact["period_end"]), set()).add(metric)
    required = set(metrics)
    return sorted((period for period, found in periods.items() if required.issubset(found)), reverse=True)


def _facts_by_period(row: dict[str, Any], metric_set: tuple[str, ...]) -> dict[str, set[str]]:
    periods: dict[str, set[str]] = {}
    for fact in _eligible_facts(row, {ANNUAL_INCOME_SCOPE}):
        if fact.get("period_type") != "annual" or fact.get("statement_type") != "income_statement":
            continue
        metric = str(fact.get("metric") or "")
        if metric in metric_set:
            periods.setdefault(str(fact["period_end"]), set()).add(metric)
    return periods


def _eligible_cashflow_periods(row: dict[str, Any]) -> list[str]:
    return _periods_with_metrics(row, ("operating_cash_flow",), {ANNUAL_CASHFLOW_SCOPE})


def _documented_interim_periods(coverage_row: dict[str, Any]) -> list[str]:
    periods = {str((doc.get("safe_period") or {}).get("period_end")) for doc in coverage_row.get("indexed_official_financial_docs") or [] if isinstance(doc, dict) and (doc.get("safe_period") or {}).get("period_type") == "interim" and (doc.get("safe_period") or {}).get("period_end")}
    return sorted(periods, reverse=True)


def _qualified_quarter_periods(row: dict[str, Any]) -> list[str]:
    return _periods_with_metrics(row, REQUIRED_ANNUAL_METRICS, {REPORTED_QUARTER_SCOPE})


def _derived_schedule_periods(row: dict[str, Any], annual: bool) -> dict[str, list[str]]:
    scopes = {ANNUAL_INCOME_SCOPE, ANNUAL_CASHFLOW_SCOPE} if annual else {REPORTED_QUARTER_SCOPE}
    found: dict[str, set[str]] = {}
    for fact in _eligible_facts(row, scopes):
        found.setdefault(str(fact["period_end"]), set()).add(str(fact.get("metric") or ""))
    return {
        "ebitda": sorted((period for period, metrics in found.items() if "ebitda" in metrics or {"operating_profit", "depreciation_amortization"}.issubset(metrics)), reverse=True),
        "free_cash_flow": sorted((period for period, metrics in found.items() if {"operating_cash_flow", "capital_expenditure"}.issubset(metrics)), reverse=True),
    }


def _schedule(row: dict[str, Any], annual: bool) -> dict[str, Any]:
    flow_scopes = {ANNUAL_INCOME_SCOPE, ANNUAL_CASHFLOW_SCOPE} if annual else {REPORTED_QUARTER_SCOPE}
    balance_scope = {ANNUAL_BALANCE_SCOPE} if annual else {REPORTED_QUARTER_BALANCE_SCOPE}
    flow_metrics = INCOME_STATEMENT_METRICS + CASH_FLOW_METRICS
    direct = _periods_with_metrics(row, flow_metrics, flow_scopes)
    balance = _periods_with_metrics(row, BALANCE_SHEET_METRICS, balance_scope)
    derived = _derived_schedule_periods(row, annual)
    qualified = sorted(set(direct) & set(balance) & set(derived["ebitda"]) & set(derived["free_cash_flow"]), reverse=True)
    return {
        "required": TARGET_ANNUAL_PERIODS if annual else TARGET_REPORTED_INTERIM_PERIODS,
        "present": len(qualified), "qualified_periods": qualified,
        "direct_flow_statement_periods": direct, "direct_balance_sheet_periods": balance,
        "derived_ebitda_periods": derived["ebitda"], "derived_free_cash_flow_periods": derived["free_cash_flow"],
        "required_direct_metrics": list(flow_metrics + BALANCE_SHEET_METRICS),
        "derived_metric_lineage": {
            "ebitda": "reported_ebitda OR operating_profit + depreciation_amortization",
            "free_cash_flow": "operating_cash_flow + capital_expenditure (reported signed cash-flow value)",
        },
    }


def _share_count_tie_out(records: list[dict[str, Any]], symbol: str) -> dict[str, Any]:
    matches = [record for record in records if isinstance(record, dict) and record.get("symbol") == symbol and record.get("metric") == "shares_out" and record.get("record_type") == "official_share_count_capital_note_tie_out" and record.get("approved") is True and record.get("available_on") and isinstance(record.get("source"), dict)]
    if not matches:
        return {"status": "missing_official_share_count_capital_note_tie_out", "available_on": None, "source": None}
    record = sorted(matches, key=lambda item: str(item.get("available_on")), reverse=True)[0]
    source = record.get("source") or {}
    return {"status": "official_share_count_capital_note_tied_out", "available_on": record.get("available_on"), "source": {key: source.get(key) for key in ("id", "label", "path", "url")}, "limitation": "The source-bound official capital-note record satisfies the share-count tie-out gate."}


def _candidate_documents(coverage_row: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"document_id": doc.get("document_id"), "title": doc.get("title"), "published_at": doc.get("published_at"), "source_url": doc.get("source_url"), "safe_period": doc.get("safe_period"), "reason": "retained official document candidate; owner approval is required before any restage"} for doc in (coverage_row.get("qualification_queue") or {}).get("candidate_documents") or [] if isinstance(doc, dict) and doc.get("document_id") and doc.get("source_url")][:5]


def company_qualification(symbol: str, reconciliation: dict[str, Any], coverage: dict[str, Any], records: list[dict[str, Any]], cement: dict[str, Any]) -> dict[str, Any]:
    metric_periods = _facts_by_period(reconciliation, REQUIRED_ANNUAL_METRICS)
    annual_periods = sorted((period for period, metrics in metric_periods.items() if set(REQUIRED_ANNUAL_METRICS).issubset(metrics)), reverse=True)
    quarter_periods, cashflow_periods = _qualified_quarter_periods(reconciliation), _eligible_cashflow_periods(reconciliation)
    annual_schedule, quarter_schedule = _schedule(reconciliation, True), _schedule(reconciliation, False)
    shares, conflict_count = _share_count_tie_out(records, symbol), int(reconciliation.get("source_conflict_count") or 0)
    gaps = []
    for requirement, section in (("qualified_annual_income_triplets", {"required": TARGET_ANNUAL_PERIODS, "present": len(annual_periods)}), ("qualified_reported_quarter_fact_sets", {"required": TARGET_REPORTED_INTERIM_PERIODS, "present": len(quarter_periods)}), ("qualified_annual_operating_cash_flow", {"required": TARGET_ANNUAL_PERIODS, "present": len(cashflow_periods)}), ("qualified_annual_financial_statement_schedules", annual_schedule), ("qualified_reported_quarter_financial_statement_schedules", quarter_schedule)):
        if int(section["present"]) < int(section["required"]): gaps.append({"requirement": requirement, "required": section["required"], "present": section["present"], "status": "blocked"})
    share_tied_out = shares.get("status") == "official_share_count_capital_note_tied_out"
    if not share_tied_out: gaps.append({"requirement": "official_share_count_capital_note_tie_out", "required": 1, "present": 0, "status": "blocked"})
    if conflict_count: gaps.append({"requirement": "unresolved_financial_source_conflicts", "required": 0, "present": conflict_count, "status": "blocked"})
    qualified = annual_schedule["present"] >= TARGET_ANNUAL_PERIODS and quarter_schedule["present"] >= TARGET_REPORTED_INTERIM_PERIODS and share_tied_out and conflict_count == 0
    reason = "all strict model-ready financial-truth gates satisfied" if qualified else "requires five annual and eight direct reported-quarter full-statement schedules, deterministic EBITDA/FCF operand lineage, an official share-count capital-note tie-out, and no unresolved canonical conflicts"
    return {"symbol": symbol, "status": "qualified" if qualified else "not_qualified", "qualification_scope": "retained_reported_model_ready_financial_truth", "annual_income_triplets": {"required": TARGET_ANNUAL_PERIODS, "present": len(annual_periods), "qualified_periods": annual_periods}, "qualified_reported_quarter_fact_sets": {"required": TARGET_REPORTED_INTERIM_PERIODS, "present": len(quarter_periods), "qualified_periods": quarter_periods}, "documented_interim_metadata": {"present": len(_documented_interim_periods(coverage)), "documented_periods": _documented_interim_periods(coverage), "limitation": "Document metadata proves a retained official reporting period, not parsed qualified quarterly financial facts and does not satisfy any financial-truth gate."}, "annual_operating_cash_flow": {"required": TARGET_ANNUAL_PERIODS, "present": len(cashflow_periods), "qualified_periods": cashflow_periods}, "model_ready_financial_statement_coverage": {"annual": annual_schedule, "reported_quarter": quarter_schedule, "limitation": "This is the authoritative full-statement gate. Legacy three-line counters remain visibility-only and cannot activate formal engines."}, "share_count": shares, "financial_tie_out": {"status": "qualified" if qualified else "blocked", "reason": reason}, "operating_lane": {"status": cement.get("status") or "not_applicable", "activation_status": cement.get("activation_status") or "not_applicable"}, "evidence_gaps": gaps, "candidate_documents": _candidate_documents(coverage), "downstream": {key: "not_activated_owner_approved_forward_inputs_required" if qualified else "blocked_financial_truth_not_qualified" for key in ("forecast", "valuation", "market_expectations")}, "policy": {"raw_financial_values": "not_emitted", "restage": "owner_approval_required", "forecasts": "not_emitted", "valuation": "not_emitted", "market_expectations": "not_emitted"}}


def build_qualification(pilot: list[str], reconciliation_state: dict[str, Any], coverage_state: dict[str, Any], assumptions_state: dict[str, Any], cement_state: dict[str, Any]) -> dict[str, Any]:
    reconciliations, coverages, cements = reconciliation_state.get("companies") or {}, coverage_state.get("companies") or {}, cement_state.get("companies") or {}
    records = [record for record in assumptions_state.get("records") or [] if isinstance(record, dict)]
    companies = {symbol: company_qualification(symbol, reconciliations.get(symbol) or {}, coverages.get(symbol) or {}, records, cements.get(symbol) or {}) for symbol in pilot}
    ordered = sorted(companies.values(), key=lambda row: (-int((row.get("model_ready_financial_statement_coverage") or {}).get("annual", {}).get("present") or 0), -int((row.get("model_ready_financial_statement_coverage") or {}).get("reported_quarter", {}).get("present") or 0), 0 if (row.get("operating_lane") or {}).get("status") == "audit_only_series_available" else 1, row.get("symbol") or ""))
    for rank, row in enumerate(ordered, 1):
        row["candidate_rank"] = rank
        row["selection_status"] = "qualified_financial_truth" if rank == 1 and row.get("status") == "qualified" else ("leading_candidate_not_golden" if rank == 1 else "not_selected")
    leader = ordered[0] if ordered else None
    return {"schema_version": "financial_truth_qualification_v2", "pilot_symbols": pilot, "source": "retained_state_only", "policy": {"does_not_fetch": True, "does_not_parse_documents": True, "does_not_promote_audit_only_facts": True, "does_not_emit_financial_values": True, "does_not_activate_formal_engines": True}, "selection": {"status": ("qualified_financial_truth" if leader and leader.get("status") == "qualified" else "leading_candidate_not_golden") if leader else "no_candidate", "leader_symbol": leader.get("symbol") if leader else None, "reason": "ranked only by retained source-grounded full-statement coverage; the leader remains unqualified until every financial-truth gate is satisfied"}, "companies": companies, "summary": {"company_count": len(companies), "qualified_company_count": sum(1 for row in companies.values() if row.get("status") == "qualified"), "leader_symbol": leader.get("symbol") if leader else None}}
