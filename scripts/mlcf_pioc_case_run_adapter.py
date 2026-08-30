"""Adapter for the narrow MLCF/PIOC case-run contract.

The real route consumes already-retained IntelligenceCase and readiness
objects supplied by its caller; it never reads or writes state and is blocked
until the existing financial-truth/event gates are complete.  The fixture
route is synthetic and test-only, and calls the existing cement engine for
isolated bear/base/bull scenarios.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Mapping

import cement_expansion_contract as cement
import cement_expansion_engine as engine
import build_intelligence_cases
from psx_data import STATE, load_json
from mlcf_pioc_case_run_contract import (
    CASE_ID,
    SCENARIOS,
    retained_real_source_lineage,
    validate_case_run,
)

FIXTURE_EVENT_REF = "fixture:mlcf-pioc-cement-expansion-v1"


def _dedupe(values: list[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _readiness(status: str, reasons: list[str], hard_block: bool = True) -> dict[str, Any]:
    reasons = _dedupe(reasons)
    return {
        "status": status,
        "blocked_reasons": reasons,
        "hard_block": bool(hard_block),
        "reason": reasons[0] if reasons else None,
    }


def _real_block_reasons(case: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if case.get("case_id") != CASE_ID:
        reasons.append("case_id_mismatch")
    if case.get("status") != "Observed":
        reasons.append(f"case_status_not_observed:{case.get('status')}")
    if manifest.get("status") != "blocked_missing_inputs":
        reasons.append(f"readiness_status:{manifest.get('status')}")
    for row in manifest.get("missing_inputs") or []:
        if isinstance(row, Mapping):
            input_id = str(row.get("input_id", "unknown_input"))
            status = str(row.get("status", "missing"))
            reasons.append(f"{input_id}:{status}")
    policy = manifest.get("formal_output_policy") or {}
    if policy.get("hard_block"):
        reasons.append("formal_output_policy:hard_block")
    if not reasons:
        reasons.append("event_model_inputs_not_source_qualified")
    return _dedupe(reasons)


def build_real_case_run(
    intelligence_case: Mapping[str, Any] | None = None,
    readiness_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the current real path, which is identity/provenance-only blocked."""
    authoritative = build_intelligence_cases.build(write=False)
    try:
        case = next(
            row for row in authoritative["companies"]["MLCF"]["cases"]
            if isinstance(row, Mapping) and row.get("case_id") == CASE_ID
        )
    except (KeyError, StopIteration, TypeError) as error:
        raise ValueError("authoritative MLCF IntelligenceCase is unavailable") from error
    if intelligence_case is not None:
        if not isinstance(intelligence_case, Mapping) or _canonical_json(intelligence_case) != _canonical_json(case):
            raise ValueError("without exact retained source lineage: caller IntelligenceCase is stale or not byte/equality-bound to build(write=False)")
    authoritative_manifest = (load_json(STATE / "company_intel" / "mlcf_pioc_readiness_manifest.json", {})
                              .get("companies", {}).get("MLCF", {}).get("manifest"))
    if not isinstance(authoritative_manifest, Mapping):
        raise ValueError("authoritative MLCF readiness manifest is unavailable")
    if readiness_manifest is not None:
        if not isinstance(readiness_manifest, Mapping) or _canonical_json(readiness_manifest) != _canonical_json(authoritative_manifest):
            raise ValueError("without exact retained source lineage: caller readiness manifest is stale or not equality-bound to retained state")
    manifest = authoritative_manifest
    reasons = _real_block_reasons(case, manifest)
    lineage, lineage_violations = retained_real_source_lineage(case, manifest)
    if lineage_violations:
        raise ValueError(
            "real case-run cannot be generated without exact retained source lineage: "
            + "; ".join(lineage_violations)
        )
    # The real route must not leak known deal amounts as economic operands.
    # A blocked real run exposes no scenario objects at all.  This prevents a
    # consumer from mistaking identity-only placeholders for model outputs.
    runs: list[dict[str, Any]] = []
    envelope = {
        "status": "blocked",
        "case_id": CASE_ID,
        "scenario_runs": runs,
        "blocked_reasons": reasons,
        "input_lineage": lineage,
        "analogue_readiness": _readiness("not_ready", ["no_case_specific_historical_analogue_gate"]),
        "formal_output_readiness": _readiness("blocked", reasons),
    }
    violations = validate_case_run(envelope)
    if violations:
        raise ValueError("real case-run contract violation: " + "; ".join(violations))
    return envelope


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _provenance(value: Any, note: str = "synthetic fixture only; not investor output") -> dict[str, Any]:
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "fixture:mlcf-pioc-case-run-v1", "note": note},
        "available_on": "2025-12-31",
    }


def _fixture_case(label: str) -> dict[str, Any]:
    # Deliberately synthetic values exercise the production cement kernel;
    # no state, filing, price, valuation or recommendation is represented.
    scale = {"bear": 0.75, "base": 1.0, "bull": 1.2}[label]
    quarters = [
        "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30",
        "2026-12-31", "2027-03-31", "2027-06-30", "2027-09-30",
    ]
    def schedule(value: float) -> list[float]:
        return [value * scale] * 8
    return {
        "case_id": CASE_ID,
        "symbol": "MLCF-FIXTURE",
        "event_ref": FIXTURE_EVENT_REF,
        "case_label": label,
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
        "inputs": {
            "quarter_ends": _provenance(quarters),
            "commissioning_quarter_index": _provenance(2),
            "incremental_capacity_units": _provenance(100_000.0),
            "starting_utilization_pct": _provenance(20.0),
            "utilization_ramp_pct_schedule": _provenance([20.0, 40.0, 55.0, 70.0, 80.0, 85.0, 90.0, 90.0]),
            "starting_revenue_pkr": _provenance(100_000_000.0),
            "selling_price_pkr_per_unit_schedule": _provenance(schedule(2_000.0)),
            "fuel_cost_pkr_per_unit_schedule": _provenance(schedule(300.0)),
            "power_cost_pkr_per_unit_schedule": _provenance(schedule(100.0)),
            "freight_cost_pkr_per_unit_schedule": _provenance(schedule(50.0)),
            "fixed_cost_pkr_schedule": _provenance(schedule(10_000_000.0)),
            "capex_schedule_pkr": _provenance([50_000_000.0, 100_000_000.0, 50_000_000.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            "depreciation_pkr_schedule": _provenance([0.0, 5_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0]),
            "gross_margin_pct": _provenance(50.0),
            "working_capital_pct_revenue": _provenance(10.0),
            "debt_financing_pkr": _provenance(50_000_000.0),
            "equity_financing_pkr": _provenance(150_000_000.0),
            "annual_interest_rate_pct": _provenance(12.0),
            "effective_tax_pct": _provenance(30.0),
            "shares_out": _provenance(100_000_000.0),
            "discount_rate_pct_annual": _provenance(12.0),
        },
    }


def build_fixture_case_run() -> dict[str, Any]:
    """Compute three synthetic scenarios through the existing cement engine."""
    runs: list[dict[str, Any]] = []
    for label in SCENARIOS:
        case = _fixture_case(label)
        result = engine.evaluate_case(case)
        result["case_id"] = CASE_ID
        runs.append({"scenario": label, "status": "computed", "blocked_reasons": [], "result": result})
    lineage = copy.deepcopy(runs[0]["result"]["inputs_lineage"])
    envelope = {
        "status": "computed",
        "case_id": CASE_ID,
        "scenario_runs": runs,
        "blocked_reasons": [],
        "input_lineage": lineage,
        "analogue_readiness": _readiness("not_ready", ["fixture_has_no_historical_analogue"]),
        "formal_output_readiness": _readiness("not_ready", ["synthetic_fixture_not_formal_output"]),
    }
    violations = validate_case_run(envelope)
    if violations:
        raise ValueError("fixture case-run contract violation: " + "; ".join(violations))
    return envelope


def build_case_run(
    intelligence_case: Mapping[str, Any] | None = None,
    readiness_manifest: Mapping[str, Any] | None = None,
    *,
    fixture: bool = False,
) -> dict[str, Any]:
    """Select real blocked route or explicitly requested synthetic fixture."""
    if fixture:
        return build_fixture_case_run()
    return build_real_case_run(intelligence_case, readiness_manifest)


__all__ = ["build_case_run", "build_real_case_run", "build_fixture_case_run"]
