#!/usr/bin/env python3
"""Build retained-state-only CNERGY sales-led vertical slice."""
from __future__ import annotations
from typing import Any
from psx_data import ROOT, STATE, load_json, save_json

OUT = STATE / "company_intel" / "cnergy_sales_vertical_slice.json"
STAGES = ("source_record", "sales_expansion_eligibility", "fact_gap", "financial_truth", "scenario_model", "formal_outputs", "monitoring", "ask_ui")

def _load(path: str, default: dict[str, Any]) -> dict[str, Any]:
    value = load_json(ROOT / path, default)
    return value if isinstance(value, dict) else default

def _stage(status: str, reason: str | None, source: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, "source": source, **extra}

def build(*, write: bool = True) -> dict[str, Any]:
    receipt = _load("state/company_intel/cnergy_sales_event_intake_receipt.json", {})
    primary = receipt.get("primary_event") or {}
    alt = receipt.get("verified_alternative") or {}
    truth = _load("state/company_intel/financial_truth_qualification.json", {}).get("companies", {}).get("CNERGY", {})
    cases = _load("state/company_intel/intelligence_cases.json", {}).get("companies", {}).get("CNERGY", {})
    forecasts = _load("state/company_intel/financial_forecasts.json", {}).get("companies", {}).get("CNERGY", {})
    valuations = _load("state/company_intel/formal_valuations.json", {}).get("companies", {}).get("CNERGY", {})
    expectations = _load("state/company_intel/market_expectations.json", {}).get("companies", {}).get("CNERGY", {})
    monitoring = _load("state/company_intel/monitoring.json", {}).get("companies", {}).get("CNERGY", {})
    primary_ok = receipt.get("ticker") == "CNERGY" and primary.get("event_type") == "sales_performance_record" and primary.get("evidence_class") == "exact_hash_page_backed_text" and isinstance(primary.get("issuer_index_publication_date"), str) and isinstance(primary.get("content_sha256"), str) and len(primary.get("content_sha256", "")) == 64 and primary.get("citation_page") == 1 and str(primary.get("source_url", "")).startswith("https://")
    alt_ok = alt.get("event_type") == "sales_mix_expansion" and alt.get("evidence_class", "").startswith("exact_hash_page_backed") and isinstance(alt.get("original_document_date"), str) and isinstance(alt.get("content_sha256"), str) and len(alt.get("content_sha256", "")) == 64 and alt.get("citation_page") == 1
    financial_ok = truth.get("status") == "qualified"
    stages = {
        "source_record": _stage("available" if primary_ok and alt_ok else "blocked", None if primary_ok and alt_ok else "source_hash_page_date_binding_invalid", "state/company_intel/cnergy_sales_event_intake_receipt.json", primary_event_type=primary.get("event_type"), alternative_event_type=alt.get("event_type"), primary_status=primary.get("event_status"), alternative_status=alt.get("event_status")),
        "sales_expansion_eligibility": _stage("blocked", "performance_and_sales_mix_outcome_not_sales_infrastructure_expansion", "state/company_intel/cnergy_sales_event_intake_receipt.json", case_eligible=False, rejected_categories=["sales_team", "channel", "geography", "customer", "product_sales_infrastructure"]),
        "fact_gap": _stage("blocked", "no_case_eligible_sales_expansion_operating_event", "state/company_intel/cnergy_sales_event_intake_receipt.json", unverified_registry_leads=True, required=["attributable_action", "effective_date", "hash", "page", "sales_expansion_scope"]),
        "financial_truth": _stage("available" if financial_ok else "blocked", None if financial_ok else "financial_truth_not_qualified", "state/company_intel/financial_truth_qualification.json", truth_status=truth.get("status"), annual=(truth.get("model_ready_financial_statement_coverage") or {}).get("annual", {})),
        "scenario_model": _stage("blocked", "no_case_eligible_event_or_source_qualified_operands", "state/company_intel/impact_scenarios.json", computed_count=0),
        "formal_outputs": _stage("available" if financial_ok and all(r.get("status") == "computed" for r in (forecasts, valuations, expectations)) else "blocked", "financial_truth_not_qualified_or_outputs_not_computed", "state/company_intel/financial_forecasts.json; state/company_intel/formal_valuations.json; state/company_intel/market_expectations.json", statuses={"forecast": forecasts.get("status"), "valuation": valuations.get("status"), "market_expectations": expectations.get("status")}),
        "monitoring": _stage("available" if monitoring else "not_generated", None if monitoring else "monitoring_state_missing", "state/company_intel/monitoring.json", status_value=monitoring.get("status"), active_watch_count=(monitoring.get("activity") or {}).get("active_watch_count", 0)),
        "ask_ui": _stage("available" if (ROOT / "Henneth Desk 2.CI.0" / "app.js").exists() else "not_generated", None if (ROOT / "Henneth Desk 2.CI.0" / "app.js").exists() else "ci_app_missing", "Henneth Desk 2.CI.0/app.js", ask_status="owner_gated_contract", ui_status="read_only_projection"),
    }
    blockers = [name for name, row in stages.items() if row["status"] != "available"]
    result = {"schema_version": 1, "kind": "cnergy_sales_vertical_slice", "symbol": "CNERGY", "status": "available" if not blockers else "blocked", "reason": None if not blockers else blockers[0] + ":" + str(stages[blockers[0]]["reason"]), "stages": stages, "blockers": blockers, "policy": {"retained_state_only": True, "no_case_seed": True, "no_promotion": True, "performance_not_expansion": True, "formal_outputs_require_financial_truth": True}}
    if write: save_json(OUT, result)
    return result

if __name__ == "__main__":
    row = build(); print(f"cnergy_sales_vertical_slice: {row['status']} -> {OUT.relative_to(ROOT)}")
