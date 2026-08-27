#!/usr/bin/env python3
"""Validate the Company Intelligence completion matrix."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_ci_completion_matrix as builder
import check_ci_product_contracts
from psx_data import load_json

IMPACT_KEYS = ("revenue_impact", "ebitda_impact", "eps_impact", "fcf_impact", "valuation_impact")
IMPACT_STATUSES = {"insufficient_data", "unmodeled_driver"}


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _fail(message: str) -> None:
    raise AssertionError(message)


def _synthetic_status_rules() -> None:
    ok = [{"ok": True}]
    bad = [{"ok": False}]
    if builder.requirement_status([], []) != "not_started":
        _fail("empty evidence must be not_started")
    if builder.requirement_status(bad, []) != "not_started":
        _fail("all-false evidence must be not_started")
    if builder.requirement_status(ok, []) != "complete":
        _fail("all-ok evidence without blockers must be complete")
    if builder.requirement_status([ok[0], bad[0]], []) != "partial":
        _fail("mixed evidence must be partial")
    if builder.requirement_status(ok, ["needs live proof"]) != "partial":
        _fail("blockers on implemented evidence must be partial")
    if builder.requirement_status(ok, ["qualified inputs missing"], hard_blocked=True) != "blocked":
        _fail("hard-blocked rows must stay blocked even with evidence")


def _assert_shape(matrix: dict) -> None:
    if matrix.get("schema_version") != 2:
        _fail("schema version mismatch")
    if matrix.get("source_policy") != "retained repo/state evidence only; no fetching, model calls, SQL, publish, deploy, or source mutation":
        _fail("source policy drifted")
    pilot = matrix.get("pilot_symbols") or []
    if len(pilot) != 20 or len(set(pilot)) != 20:
        _fail("pilot boundary must be exactly 20")
    rows = matrix.get("requirements") or []
    ids = [row.get("id") for row in rows]
    if tuple(ids) != builder.REQUIREMENT_IDS:
        _fail("requirement registry mismatch")
    expected_requirement_count = len(builder.REQUIREMENT_IDS)
    if len(ids) != expected_requirement_count:
        _fail(f"requirement registry must have {expected_requirement_count} granular rows")
    if len(ids) != len(set(ids)):
        _fail("duplicate requirement id")
    counts = {status: 0 for status in builder.STATUSES}
    for row in rows:
        status = row.get("status")
        if status not in builder.STATUSES:
            _fail(f"{row.get('id')}: invalid status {status}")
        counts[status] += 1
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            _fail(f"{row.get('id')}: missing evidence")
        for item in evidence:
            if not isinstance(item.get("ok"), bool) or not item.get("label") or not item.get("path"):
                _fail(f"{row.get('id')}: malformed evidence row")
        if status == "complete" and not all(item.get("ok") for item in evidence):
            _fail(f"{row.get('id')}: complete row has failed evidence")
        if status in {"partial", "blocked", "not_started", "unknown"} and not row.get("next_required_evidence"):
            _fail(f"{row.get('id')}: incomplete row missing next required evidence")
    if (matrix.get("summary") or {}).get("counts") != counts:
        _fail("summary counts mismatch")


def _assert_conservative_statuses(matrix: dict) -> None:
    by_id = {row["id"]: row for row in matrix.get("requirements") or []}
    forecast_readiness = by_id["forecast_readiness_live_inputs"]
    forecast_outputs = by_id["formal_forecast_live_outputs"]
    valuation_outputs = by_id["formal_valuation_live_outputs"]
    expectations_outputs = by_id["market_expectations_live_outputs"]
    readiness = load_json(ROOT / "state" / "company_intel" / "forecast_readiness.json", {})
    ready_count = ((readiness.get("summary") or {}).get("ready_company_count") or 0)
    history_qualified_count = ((readiness.get("summary") or {}).get("history_qualified_company_count") or 0)
    companies = readiness.get("companies") or {}
    ready_symbols = [symbol for symbol, row in companies.items() if row.get("status") == "input_ready"]
    history_qualified_symbols = [
        symbol for symbol, row in companies.items()
        if row.get("status") in {"input_ready", "blocked_model_adapter_unavailable"}
    ]
    if ready_count != len(ready_symbols):
        _fail("forecast readiness summary ready count mismatch")
    if history_qualified_count != len(history_qualified_symbols) or not history_qualified_symbols:
        _fail("forecast readiness summary must match at least one history-qualified company")
    if any(
        not all(str((row.get("downstream_status") or {}).get(key) or "").startswith("blocked")
                for key in ("forecast", "valuation", "market_expectations", "numeric_impact"))
        for row in companies.values()
    ):
        _fail("forecast readiness downstream outputs must remain blocked")
    if forecast_readiness.get("status") != "partial":
        _fail("forecast readiness live-input row must be partial while formal outputs remain blocked")
    if not any(f"Real history-qualified company count is {history_qualified_count}" in blocker for blocker in forecast_readiness.get("blockers") or []):
        _fail("forecast readiness row did not record real readiness blocker")
    for row_id, row in (
        ("formal_forecast_live_outputs", forecast_outputs),
        ("formal_valuation_live_outputs", valuation_outputs),
        ("market_expectations_live_outputs", expectations_outputs),
    ):
        if row.get("status") != "blocked":
            _fail(f"{row_id} must remain blocked while real computed output count is zero")
    for row_id in ("private_thesis_live_storage",):
        if by_id[row_id].get("status") == "complete":
            _fail(f"{row_id} cannot be complete from repo evidence alone")
    ownership_manifest = load_json(ROOT / "config" / "ownership_source_review_manifest.json", {})
    ownership_summary = ownership_manifest.get("summary") or {}
    if by_id["ownership_source_review_manifest"].get("status") != "complete":
        _fail("ownership source review manifest must be credited as a complete review-only source gate")
    if ownership_summary.get("activated_company_count") != 0:
        _fail("ownership source review manifest must not activate ownership facts")
    if set(ownership_manifest.get("companies") or {}) != set(readiness.get("companies") or {}):
        _fail("ownership source review manifest pilot boundary drifted")
    if by_id["training_owner_receipts"].get("status") != "complete":
        _fail("append-only receipt reconciliation must be credited without claiming future approvals")
    if by_id["impact_scenario_shells"].get("status") != "partial":
        _fail("impact scenario shells must stay partial while numeric impacts are null")
    _assert_impact_scenario_numeric_contract(matrix)
    for row_id in ("formal_forecast_engine_code", "formal_valuation_engine_code", "market_expectations_engine_code"):
        if by_id[row_id].get("status") != "complete":
            _fail(f"{row_id} should distinguish implemented source-gated engine code from blocked live outputs")


def _assert_impact_scenario_numeric_contract(matrix: dict) -> None:
    scenarios = load_json(ROOT / "state" / "company_intel" / "impact_scenarios.json", {})
    pilot = set(matrix.get("pilot_symbols") or [])
    companies = scenarios.get("companies") or {}
    if not pilot or set(companies) != pilot:
        _fail("impact scenario pilot boundary mismatch")
    scenario_count = 0
    for symbol, row in companies.items():
        for scenario in row.get("scenarios") or []:
            scenario_count += 1
            if scenario.get("impact_status") not in IMPACT_STATUSES:
                _fail(f"{symbol}: scenario impact status is not explicitly blocked")
            assumptions = scenario.get("assumptions") or {}
            if not isinstance(assumptions.get("missing_inputs"), list):
                _fail(f"{symbol}: scenario missing_inputs must be explicit")
            for key in IMPACT_KEYS:
                if key not in scenario:
                    _fail(f"{symbol}: scenario missing numeric impact field {key}")
                if scenario.get(key) is not None:
                    _fail(f"{symbol}: scenario numeric impact {key} must stay null without sourced inputs")
    if scenario_count == 0:
        _fail("impact scenarios must contain retained scenario shells")


def _assert_event_study_evidence(matrix: dict) -> None:
    studies = load_json(ROOT / "state" / "company_intel" / "event_studies.json", {})
    strict, baseline_available, total = builder.strict_baseline_available_count(studies)
    if not total or not baseline_available or strict != baseline_available:
        _fail(f"strict event-study derivation mismatch: {strict}/{baseline_available} baseline-available, {total} total")
    by_id = {row["id"]: row for row in matrix.get("requirements") or []}
    strict_row = by_id["event_study_strict_baselines"]
    details = " ".join(str(item.get("detail") or "") for item in strict_row.get("evidence") or [])
    if f"{strict}/{baseline_available}" not in details:
        _fail("strict event-study evidence did not report the derived strict count")
    serialized = _dump(strict_row)
    if "strict_no_lookahead" in serialized:
        _fail("matrix must not depend on an invented strict_no_lookahead event-study field")


def _assert_slice_summary(matrix: dict) -> None:
    slice_path = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
    ci_slice = load_json(slice_path, {})
    expected = builder.slice_summary(matrix)
    actual = (ci_slice.get("meta") or {}).get("completion_matrix")
    if actual != expected:
        _fail("CI slice completion_matrix summary is missing or stale")


def main() -> None:
    delegated_to_preflight = os.environ.get("HENNETH_CI_PRODUCT_CONTRACTS_VERIFIED_BY_PREFLIGHT") == "1"
    contract_results = [] if delegated_to_preflight else check_ci_product_contracts.run_checks()
    if not delegated_to_preflight:
        contract_failures = [result for result in contract_results if result.status != "passed"]
        if contract_failures:
            check_ci_product_contracts.print_report(contract_results)
            failed_names = ", ".join(result.name for result in contract_failures)
            _fail(f"CI product contract aggregate failed before completion credit: {failed_names}")
    _synthetic_status_rules()
    if not builder.OUT.exists():
        _fail("completion_matrix.json is missing")
    matrix = load_json(builder.OUT, {})
    rebuilt = builder.build(write=False)
    if _dump(matrix) != _dump(rebuilt):
        _fail("completion matrix is not current/deterministic")
    _assert_shape(matrix)
    _assert_conservative_statuses(matrix)
    _assert_event_study_evidence(matrix)
    _assert_slice_summary(matrix)
    summary = matrix["summary"]["counts"]
    print(
        "ci_completion_matrix: PASS "
        f"({len(matrix['requirements'])} requirements; "
        f"{summary['complete']} complete, {summary['partial']} partial, {summary['blocked']} blocked; "
        + (
            "product checks executed by the aggregate)"
            if not delegated_to_preflight
            else "product checks executed by preflight direct gates)"
        )
    )


if __name__ == "__main__":
    main()
