#!/usr/bin/env python3
"""Build a secret-free owner-review handoff for formal-engine assumptions.

This manifest is a checklist, not an approval path.  It reads the existing
formal-engine gap state and makes the missing owner-approved records explicit
for the currently input-ready cement companies.  It never invents assumption
values, approves rows, writes Supabase, or activates formal outputs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from forecast_contract import FORMAL_ENGINE_REQUIRED_APPROVED_RECORDS
from formal_financial_engines import approved_records
from import_owner_financial_assumptions import ALLOWED_METRICS, STRICT_MINIMUM_METRICS
from psx_data import ROOT, STATE, load_json, save_json


OUT = ROOT / "config" / "owner_financial_assumption_handoff.json"
TARGET_SYMBOLS = ("MLCF", "DGKC")
KIND = "owner_financial_assumption_handoff"


def _metric_contract(metric: str) -> dict[str, Any]:
    unit, minimum, maximum = ALLOWED_METRICS[metric]
    return {
        "metric": metric,
        "unit": unit,
        "minimum": minimum,
        "maximum": maximum,
        "minimum_inclusive": metric not in STRICT_MINIMUM_METRICS,
        "maximum_inclusive": True,
    }


def _record_ref(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    return {
        "metric": record.get("metric"),
        "record_type": record.get("record_type"),
        "approval_scope": record.get("approval_scope"),
        "available_on": record.get("available_on") or source.get("available_on"),
        "source_id": source.get("id"),
        "source_label": source.get("label"),
        "source_path": source.get("path"),
        "source_url": source.get("url"),
        "generated_by": record.get("generated_by"),
        "imported_by": record.get("imported_by"),
        "value_present": "value" in record,
    }


def _reference_case_refs(assumption_row: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    refs = []
    for record in assumption_row.get("records") or []:
        if not isinstance(record, dict):
            continue
        if record.get("symbol") != symbol or record.get("record_type") != "derived_reference_case":
            continue
        source = record.get("source") or {}
        refs.append({
            "metric": record.get("metric"),
            "case_type": record.get("case_type"),
            "assumption_status": record.get("assumption_status"),
            "available_on": record.get("available_on"),
            "source_id": source.get("id"),
            "source_path": source.get("path"),
            "can_satisfy_approved_record": False,
        })
    return sorted(refs, key=lambda row: str(row.get("metric") or ""))


def _company_row(
    symbol: str,
    *,
    model_inputs: dict[str, Any],
    readiness: dict[str, Any],
    financial_truth: dict[str, Any],
    assumptions: dict[str, Any],
    gaps: dict[str, Any],
    as_of: str | None,
) -> dict[str, Any]:
    model_row = (model_inputs.get("companies") or {}).get(symbol) or {}
    readiness_row = (readiness.get("companies") or {}).get(symbol) or {}
    truth_row = (financial_truth.get("companies") or {}).get(symbol) or {}
    gap_row = (gaps.get("companies") or {}).get(symbol) or {}
    accepted = approved_records(assumptions, symbol, as_of)
    accepted_metrics = set(accepted)
    missing_prerequisites = []
    if model_row.get("status") != "ready":
        missing_prerequisites.append("financial_model_inputs_ready")
    if readiness_row.get("status") != "input_ready":
        missing_prerequisites.append("forecast_readiness_input_ready")
    if truth_row.get("status") != "qualified":
        missing_prerequisites.append("financial_truth_qualified")

    products: dict[str, Any] = {}
    missing_by_metric: dict[str, set[str]] = {}
    for product, required in FORMAL_ENGINE_REQUIRED_APPROVED_RECORDS.items():
        required_metrics = list(required)
        missing = [] if missing_prerequisites else [metric for metric in required_metrics if metric not in accepted_metrics]
        for metric in missing:
            missing_by_metric.setdefault(metric, set()).add(product)
        products[product] = {
            "status": (
                "not_evaluated_until_input_ready"
                if missing_prerequisites else
                "blocked_missing_approved_records"
                if missing else
                "ready_for_formal_engine"
            ),
            "required_approved_records": required_metrics,
            "accepted_records": [
                _record_ref(accepted[metric])
                for metric in required_metrics
                if metric in accepted
            ],
            "missing_approved_records": missing,
            "missing_prerequisites": list(missing_prerequisites),
        }

    handoff_records = []
    for metric in sorted(missing_by_metric):
        contract = _metric_contract(metric)
        handoff_records.append({
            "symbol": symbol,
            "metric": metric,
            "required_for_products": sorted(missing_by_metric[metric]),
            "contract": contract,
            "draft_requirements_before_append_copy_approval": {
                "approved": False,
                "approved_at": None,
                "unit": contract["unit"],
                "value_must_satisfy_contract": True,
                "available_on_must_not_exceed_manifest_as_of": True,
                "source_label_required": True,
                "rationale_required": True,
                "source_url_if_present_must_be_https": True,
            },
        })

    status = (
        "not_ready_for_assumption_handoff"
        if missing_prerequisites else
        "input_ready_pending_owner_drafts"
        if handoff_records else
        "no_missing_owner_approved_records"
    )
    return {
        "symbol": symbol,
        "status": status,
        "forecast_readiness_status": readiness_row.get("status"),
        "financial_model_inputs_status": model_row.get("status"),
        "financial_truth_status": truth_row.get("status"),
        "qualified_period_count": readiness_row.get("qualified_period_count"),
        "qualified_periods": [
            period.get("period_end")
            for period in readiness_row.get("qualified_periods") or []
            if isinstance(period, dict) and period.get("period_end")
        ],
        "gap_status_from_financial_engine_assumptions": gap_row.get("status"),
        "products": products,
        "handoff_records": handoff_records,
        "historical_reference_cases": _reference_case_refs(assumptions, symbol),
        "reference_cases_can_satisfy_missing_records": False,
        "next_required_action": (
            "owner_create_inert_drafts_then_run_local_handoff_checker_before_append_copy_approval"
            if handoff_records else
            "none"
        ),
    }


def build(write: bool = True, output_path: Path = OUT) -> dict[str, Any]:
    model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {})
    readiness = load_json(STATE / "company_intel" / "forecast_readiness.json", {})
    financial_truth = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {})
    assumptions = load_json(STATE / "company_intel" / "financial_engine_assumptions.json", {"records": []})
    gaps = assumptions.get("assumption_gaps") or {}
    as_of = assumptions.get("as_of") or gaps.get("as_of")
    companies = {
        symbol: _company_row(
            symbol,
            model_inputs=model_inputs,
            readiness=readiness,
            financial_truth=financial_truth,
            assumptions=assumptions,
            gaps=gaps,
            as_of=as_of,
        )
        for symbol in TARGET_SYMBOLS
    }
    missing_record_count = sum(len(row["handoff_records"]) for row in companies.values())
    product_missing_entry_count = sum(
        len(product["missing_approved_records"])
        for row in companies.values()
        for product in row["products"].values()
    )
    output = {
        "schema_version": 1,
        "kind": KIND,
        "as_of": as_of,
        "target_symbols": list(TARGET_SYMBOLS),
        "source": {
            "financial_engine_assumptions": "state/company_intel/financial_engine_assumptions.json",
            "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
            "forecast_readiness": "state/company_intel/forecast_readiness.json",
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
            "formal_engine_contract": "scripts/forecast_contract.py",
            "approval_script": "scripts/approve_owner_financial_assumptions.py",
        },
        "policy": {
            "review_only": True,
            "secret_free": True,
            "no_assumption_values_in_manifest": True,
            "no_supabase_read_or_write": True,
            "does_not_approve_rows": True,
            "does_not_activate_formal_engines": True,
            "append_copy_approval_remains_manual": True,
        },
        "approval_handoff": {
            "draft_table": "company_financial_assumptions",
            "drafts_must_remain_unapproved_until_append_copy": True,
            "local_validation_command": "python scripts/check_owner_financial_assumption_handoff.py --draft-export <drafts.json>",
            "manual_approval_dry_run_command": "python scripts/approve_owner_financial_assumptions.py --row-id <draft-row-uuid> --dry-run",
        },
        "companies": companies,
        "summary": {
            "company_count": len(companies),
            "input_ready_company_count": sum(row["status"] == "input_ready_pending_owner_drafts" for row in companies.values()),
            "unique_missing_company_metric_count": missing_record_count,
            "product_missing_entry_count": product_missing_entry_count,
            "formal_products_ready_count": sum(
                1
                for row in companies.values()
                for product in row["products"].values()
                if product["status"] == "ready_for_formal_engine"
            ),
        },
    }
    if write:
        save_json(output_path, output)
        print(
            "owner_financial_assumption_handoff: "
            f"{missing_record_count} unique company-metric drafts required, "
            f"{product_missing_entry_count} product gaps"
        )
    return output


if __name__ == "__main__":
    build()
