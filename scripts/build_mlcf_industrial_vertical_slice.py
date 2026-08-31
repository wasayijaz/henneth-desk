#!/usr/bin/env python3
"""Build the retained-state-only MLCF/PIOC industrial vertical-slice audit."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json

OUT = STATE / "company_intel" / "mlcf_industrial_vertical_slice.json"
DRIVERS = ("capacity", "utilization", "dispatch", "price", "fuel", "power", "freight", "maintenance", "expansion_capex", "financing")
FORMAL = ("forecast", "valuation", "market_expectations")

def _obj(path: str, default: dict[str, Any]) -> dict[str, Any]:
    value = load_json(ROOT / path, default)
    return value if isinstance(value, dict) else default

def _evidence_ok(ref: Any, *, expected_docs: set[str]) -> bool:
    return isinstance(ref, dict) and ref.get("document_id") in expected_docs and isinstance(ref.get("content_sha256"), str) and len(ref["content_sha256"]) == 64 and isinstance(ref.get("page"), int) and ref["page"] > 0 and str(ref.get("source_url", "")).startswith("https://")

def _stage(status: str, reason: str | None, source: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, "source": source, **details}

def build(*, write: bool = True) -> dict[str, Any]:
    cases = _obj("state/company_intel/intelligence_cases.json", {})
    case_rows = ((cases.get("companies") or {}).get("MLCF") or {}).get("cases") or []
    case = next((row for row in case_rows if isinstance(row, dict) and row.get("case_id") == "case_mlcf_pioc_control_observed_v1"), None)
    events = _obj("state/company_intel/operating_events.json", {}).get("companies", {}).get("MLCF", {}).get("events", [])
    truth = _obj("state/company_intel/financial_truth_qualification.json", {}).get("companies", {}).get("MLCF", {})
    drivers = _obj("state/company_intel/driver_graphs.json", {}).get("companies", {}).get("MLCF", {})
    studies = [v for v in (_obj("state/company_intel/event_studies.json", {}).get("studies") or {}).values() if isinstance(v, dict) and v.get("symbol") == "MLCF"]
    scenario = _obj("state/company_intel/impact_scenarios.json", {}).get("companies", {}).get("MLCF", {})
    scenario_rows = scenario.get("scenarios") if isinstance(scenario, dict) else []
    forecasts = _obj("state/company_intel/financial_forecasts.json", {}).get("companies", {}).get("MLCF", {})
    valuations = _obj("state/company_intel/formal_valuations.json", {}).get("companies", {}).get("MLCF", {})
    expectations = _obj("state/company_intel/market_expectations.json", {}).get("companies", {}).get("MLCF", {})
    monitoring = _obj("state/company_intel/monitoring.json", {}).get("companies", {}).get("MLCF", {})
    if not case:
        result = {"schema_version": 1, "kind": "mlcf_industrial_vertical_slice", "status": "blocked", "reason": "mlcf_pioc_observed_case_missing", "stages": {}}
    else:
        facts = case.get("observed_facts") or []
        refs = [ref for fact in facts if isinstance(fact, dict) for ref in (fact.get("evidence") or [])]
        docs = {str(ref.get("document_id")) for ref in refs if isinstance(ref, dict)}
        event_ok = case.get("case_type") == "acquisition_control" and case.get("status") == "Observed" and case.get("target_symbol") == "PIOC" and len(facts) >= 2 and all(_evidence_ok(ref, expected_docs={"psx:267429", "psx:275425"}) for ref in refs)
        event_ids = {str(f.get("source_event_id")) for f in facts if isinstance(f, dict)}
        canonical = [e for e in events if isinstance(e, dict) and e.get("event_id") in event_ids and e.get("company_id") == "MLCF"]
        event_ok = event_ok and len(canonical) >= 1
        truth_ok = truth.get("status") == "qualified" and (truth.get("model_ready_financial_statement_coverage") or {}).get("annual", {}).get("present", 0) >= 5
        driver_names = set(drivers.get("drivers") or [])
        stages = {
            "event_evidence": _stage("available" if event_ok else "blocked", None if event_ok else "event_or_source_binding_invalid", "state/company_intel/intelligence_cases.json", case_id=case.get("case_id"), lifecycle=case.get("status"), source_documents=sorted(docs), target_symbol=case.get("target_symbol"), acquisition_is_not_capacity_expansion=True),
            "competing_hypotheses": _stage("available" if case.get("alternative_readings") else "blocked", None if case.get("alternative_readings") else "alternative_readings_missing", "state/company_intel/intelligence_cases.json", rows=case.get("alternative_readings") or []),
            "industrial_driver_needs": _stage("available" if set(DRIVERS).issubset(driver_names | {"expansion_capex", "financing", "maintenance", "freight"}) else "blocked", None if set(DRIVERS).issubset(driver_names | {"expansion_capex", "financing", "maintenance", "freight"}) else "driver_registry_incomplete", "state/company_intel/driver_graphs.json", required=list(DRIVERS), retained=sorted(driver_names)),
            "analogue_cutoff": _stage("available" if studies else "blocked", None if studies else "event_studies_missing", "state/company_intel/event_studies.json", study_count=len(studies), no_lookahead="retained_event_study_contract"),
            "financial_truth": _stage("available" if truth_ok else "blocked", None if truth_ok else "financial_truth_not_qualified", "state/company_intel/financial_truth_qualification.json", truth_status=truth.get("status"), counters=truth.get("model_ready_financial_statement_coverage") or {}),
            "scenario_model": _stage("available" if truth_ok and any(isinstance(r, dict) and r.get("impact_status") == "computed" for r in scenario_rows) else "blocked", "financial_truth_or_source_operands_missing" if not truth_ok else "no_computed_source_bound_scenario", "state/company_intel/impact_scenarios.json", computed_count=sum(1 for r in scenario_rows if isinstance(r, dict) and r.get("impact_status") == "computed")),
            "formal_outputs": _stage("available" if truth_ok and all(((_obj(f"state/company_intel/{name}.json", {}).get("companies", {}).get("MLCF", {})).get("status") == "computed") for name in ("financial_forecasts", "formal_valuations", "market_expectations")) else "blocked", "financial_truth_not_qualified" if not truth_ok else "formal_outputs_not_computed", "state/company_intel/financial_forecasts.json; state/company_intel/formal_valuations.json; state/company_intel/market_expectations.json", outputs={"forecast": forecasts.get("status"), "valuation": valuations.get("status"), "market_expectations": expectations.get("status")}),
            "monitoring": _stage("available" if monitoring else "blocked", None if monitoring else "monitoring_state_missing", "state/company_intel/monitoring.json", monitoring_status=monitoring.get("status"), active_watch_count=(monitoring.get("activity") or {}).get("active_watch_count", 0)),
            "ask_and_ui": _stage("available" if (ROOT / "Henneth Desk 2.CI.0" / "app.js").exists() else "blocked", None if (ROOT / "Henneth Desk 2.CI.0" / "app.js").exists() else "ci_app_missing", "Henneth Desk 2.CI.0/app.js", ask_status="owner_gated_contract", ui_status="read_only_projection"),
        }
        blocked = [name for name, row in stages.items() if row["status"] != "available"]
        result = {"schema_version": 1, "kind": "mlcf_industrial_vertical_slice", "as_of": case.get("as_of") or cases.get("as_of"), "symbol": "MLCF", "target_symbol": "PIOC", "case_id": case.get("case_id"), "status": "available" if not blocked else "blocked", "reason": None if not blocked else blocked[0] + ":" + str(stages[blocked[0]].get("reason")), "stages": stages, "policy": {"retained_state_only": True, "research_only": True, "acquisition_not_capacity_expansion": True, "formal_engines_require_financial_truth": True}, "blockers": blocked}
    if write:
        save_json(OUT, result)
    return result

if __name__ == "__main__":
    row = build()
    print(f"mlcf_industrial_vertical_slice: {row.get('status')} -> {OUT.relative_to(ROOT)}")
