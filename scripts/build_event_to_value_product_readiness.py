"""Build the Event-to-Value Alpha product-readiness audit.

Read-only over retained CI artifacts. It does not fetch, qualify financials,
compute forecasts/valuations, or invent a passing production gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json

OUT = STATE / "company_intel" / "event_to_value_product_readiness.json"
PRODUCT_VERSION = "event_to_value_product_readiness_v1"
ALPHA_DENOMINATORS = {
    "model_ready_companies": 3,
    "published_cases": 3,
    "financially_computed_scenarios": 9,
    "live_forecast_outputs": 3,
    "live_valuation_outputs": 3,
    "live_market_expectation_outputs": 3,
}
SOURCE_PATHS = {
    "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
    "forecast_readiness": "state/company_intel/forecast_readiness.json",
    "intelligence_cases": "state/company_intel/intelligence_cases.json",
    "impact_scenarios": "state/company_intel/impact_scenarios.json",
    "financial_forecasts": "state/company_intel/financial_forecasts.json",
    "formal_valuations": "state/company_intel/formal_valuations.json",
    "market_expectations": "state/company_intel/market_expectations.json",
    "thesis_monitoring": "state/company_intel/thesis_monitoring.json",
    "artifact_integrity": "state/company_intel/artifact_integrity.json",
    "release_integrity_receipt": "state/company_intel/release_integrity_receipt.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(rel: str, default: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
    path = ROOT / rel
    if not path.exists():
        return None, "not_generated"
    payload = load_json(path, default if default is not None else {})
    if not isinstance(payload, dict):
        return None, "blocked"
    return payload, "available"


def _as_of(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    for key in ("as_of", "generated_at", "build_cutoff_at", "recorded_at"):
        value = payload.get(key) or meta.get(key)
        if value:
            return str(value)
    return None


def _metric(metric_id: str, label: str, *, status: str, value: Any, denominator: Any, definition: str, source_path: str, as_of: str | None, reason: str | None, notes: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": metric_id,
        "label": label,
        "status": status,
        "value": value,
        "denominator": denominator,
        "display": None if value is None or denominator is None else f"{value}/{denominator}",
        "definition": definition,
        "source_path": source_path,
        "as_of": as_of,
        "reason": reason,
        "notes": notes or [],
    }


def _engine_live_count(payload: dict[str, Any] | None, load_status: str) -> tuple[int | None, str, str | None, list[str]]:
    if load_status != "available" or payload is None:
        return None, load_status, "source_artifact_not_generated" if load_status == "not_generated" else "source_artifact_blocked", []
    computed = 0
    notes: list[str] = []
    for symbol, row in (payload.get("companies") or {}).items():
        if not isinstance(row, dict):
            continue
        if row.get("status") == "computed" and row.get("result") not in (None, {}, []):
            computed += 1
            notes.append(str(symbol))
    status = "available" if computed else "blocked"
    reason = None if computed else (payload.get("summary") and "formal_engine_computed_company_count_is_zero") or "no_live_computed_result"
    if not notes:
        reason = str((payload.get("companies") or {}).get("MLCF", {}).get("reason") or reason or "no_live_computed_result")
    return computed, status, reason, notes[:12]


def _financial_impact_computed(scenario: dict[str, Any]) -> bool:
    for key in ("revenue_impact", "ebitda_impact", "eps_impact", "fcf_impact", "valuation_impact"):
        value = scenario.get(key)
        if value in (None, "", {}, []):
            continue
        if isinstance(value, dict) and value.get("value") in (None, "", {}, []):
            continue
        return True
    return False


def _null_required_outputs(forecasts: dict[str, Any] | None, valuations: dict[str, Any] | None, expectations: dict[str, Any] | None) -> tuple[int, list[str]]:
    nulls = 0
    notes: list[str] = []
    for label, payload in (
        ("financial_forecasts", forecasts),
        ("formal_valuations", valuations),
        ("market_expectations", expectations),
    ):
        if not payload:
            nulls += 1
            notes.append(f"{label}:source_missing")
            continue
        companies = payload.get("companies") or {}
        for symbol, row in companies.items():
            if not isinstance(row, dict):
                continue
            if row.get("result") in (None, {}, []) or row.get("status") != "computed":
                nulls += 1
                notes.append(f"{label}:{symbol}:{row.get('reason') or row.get('status') or 'result_null'}")
    return nulls, notes[:24]


def build(write: bool = True) -> dict[str, Any]:
    truth, truth_status = _load(SOURCE_PATHS["financial_truth_qualification"])
    forecast_readiness, forecast_ready_status = _load(SOURCE_PATHS["forecast_readiness"])
    cases, cases_status = _load(SOURCE_PATHS["intelligence_cases"])
    scenarios, scenarios_status = _load(SOURCE_PATHS["impact_scenarios"])
    forecasts, forecasts_status = _load(SOURCE_PATHS["financial_forecasts"])
    valuations, valuations_status = _load(SOURCE_PATHS["formal_valuations"])
    expectations, expectations_status = _load(SOURCE_PATHS["market_expectations"])
    theses, theses_status = _load(SOURCE_PATHS["thesis_monitoring"])
    integrity, integrity_status = _load(SOURCE_PATHS["artifact_integrity"])
    receipt, receipt_status = _load(SOURCE_PATHS["release_integrity_receipt"])

    model_ready_notes: list[str] = []
    model_ready_value: int | None = None
    model_ready_metric_status = truth_status
    model_ready_reason = None
    if truth_status == "available" and truth is not None:
        qualified = []
        for symbol, row in (truth.get("companies") or {}).items():
            if isinstance(row, dict) and row.get("status") == "qualified":
                qualified.append(symbol)
        model_ready_value = len(qualified)
        model_ready_notes = qualified
        model_ready_metric_status = "available" if qualified else "blocked"
        model_ready_reason = None if qualified else str((truth.get("selection") or {}).get("reason") or "no_company_has_qualified_financial_truth")
    else:
        model_ready_reason = "financial_truth_qualification_not_generated" if truth_status == "not_generated" else "financial_truth_qualification_blocked"

    published_value = None
    published_status = cases_status
    published_reason = None
    published_notes: list[str] = []
    if cases_status == "available" and cases is not None:
        published = []
        observed = []
        for row in (cases.get("companies") or {}).values():
            for case in (row or {}).get("cases") or []:
                if not isinstance(case, dict):
                    continue
                identity = f"{case.get('symbol')}:{case.get('case_id')}:{case.get('status')}"
                if case.get("status") == "Published":
                    published.append(identity)
                elif case.get("status"):
                    observed.append(identity)
        published_value = len(published)
        published_notes = published or observed
        published_status = "available" if published else "blocked"
        published_reason = None if published else "no_published_intelligence_case"
        if not published and cases.get("summary", {}).get("observed_case_count"):
            published_reason = "observed_cases_exist_but_none_are_published"
    else:
        published_reason = "intelligence_cases_not_generated" if cases_status == "not_generated" else "intelligence_cases_blocked"

    scenario_value = None
    scenario_metric_status = scenarios_status
    scenario_reason = None
    scenario_notes: list[str] = []
    if scenarios_status == "available" and scenarios is not None:
        computed = 0
        blocked = 0
        unknown = 0
        for row in (scenarios.get("companies") or {}).values():
            for scenario in (row or {}).get("scenarios") or []:
                if not isinstance(scenario, dict):
                    continue
                if _financial_impact_computed(scenario):
                    computed += 1
                    scenario_notes.append(str(scenario.get("scenario_id") or scenario.get("event_id")))
                elif scenario.get("impact_status") in {"insufficient_data", "blocked", "unknown"}:
                    blocked += 1
                else:
                    unknown += 1
        scenario_value = computed
        scenario_metric_status = "available" if computed else "blocked"
        scenario_reason = None if computed else f"no_financially_computed_scenario_impacts:blocked={blocked}:unknown={unknown}"
    else:
        scenario_reason = "impact_scenarios_not_generated" if scenarios_status == "not_generated" else "impact_scenarios_blocked"

    forecast_count, forecast_metric_status, forecast_reason, forecast_notes = _engine_live_count(forecasts, forecasts_status)
    valuation_count, valuation_metric_status, valuation_reason, valuation_notes = _engine_live_count(valuations, valuations_status)
    expectation_count, expectation_metric_status, expectation_reason, expectation_notes = _engine_live_count(expectations, expectations_status)

    ask_status = "blocked"
    ask_reason = "ask_henneth_live_runtime_not_recorded_in_authoritative_ci_state"
    ask_notes = ["Focused contract checkers exist at scripts/check_ask_henneth.mjs, but they are not a live production Ask receipt."]

    thesis_value = None
    thesis_metric_status = theses_status
    thesis_reason = None
    thesis_notes: list[str] = []
    if theses_status == "available" and theses is not None:
        active_cases = 0
        for row in (theses.get("companies") or {}).values():
            if not isinstance(row, dict):
                continue
            count = row.get("active_thesis_count")
            if isinstance(count, int):
                active_cases += count
            if row.get("status") == "active_monitoring":
                thesis_notes.append(f"{row.get('symbol')}:{count}")
        thesis_value = active_cases
        thesis_metric_status = "available"
        thesis_reason = None if active_cases else "no_active_thesis_monitoring_cases"
    else:
        thesis_reason = "thesis_monitoring_not_generated" if theses_status == "not_generated" else "thesis_monitoring_blocked"

    nulls_value = None
    nulls_status = "blocked"
    nulls_reason = None
    nulls_notes: list[str] = []
    if forecasts_status == "available" and valuations_status == "available" and expectations_status == "available":
        nulls_value, nulls_notes = _null_required_outputs(forecasts, valuations, expectations)
        nulls_status = "available"
    else:
        nulls_reason = "required_output_artifacts_not_all_available"

    provenance_status = integrity_status
    provenance_value = None
    provenance_reason = None
    provenance_notes: list[str] = []
    if integrity_status == "available" and integrity is not None:
        artifacts = integrity.get("artifacts") or []
        hashed = [row for row in artifacts if isinstance(row, dict) and row.get("sha256") and row.get("path")]
        provenance_value = f"{len(hashed)}/{len(artifacts)}" if artifacts else "0/0"
        if artifacts and len(hashed) == len(artifacts) and integrity.get("source_commit_sha"):
            provenance_status = "available"
            provenance_notes = [str(integrity.get("source_commit_sha")), f"artifact_count={len(artifacts)}"]
        else:
            provenance_status = "blocked"
            provenance_reason = "artifact_integrity_incomplete"
    else:
        provenance_reason = "artifact_integrity_not_generated" if integrity_status == "not_generated" else "artifact_integrity_blocked"

    lookahead_status = "blocked"
    lookahead_reason = "no_lookahead_pass_is_not_stored_as_authoritative_state; scripts/check_ci_global_no_lookahead.py must be run to prove the current tree"
    lookahead_notes = ["Checker exists. This audit does not treat a missing stored receipt as a pass."]

    production_status = receipt_status if receipt_status != "available" else str((receipt or {}).get("release_status") or "unknown")
    production_reason = None
    production_notes: list[str] = []
    if receipt_status != "available" or receipt is None:
        production_status = receipt_status
        production_reason = "release_integrity_receipt_not_generated" if receipt_status == "not_generated" else "release_integrity_receipt_blocked"
    else:
        evidence = receipt.get("required_evidence") or {}
        missing = [key for key, row in evidence.items() if not isinstance(row, dict) or row.get("status") != "pass"]
        production_notes = [f"{key}:{(evidence.get(key) or {}).get('status')}" for key in evidence]
        if receipt.get("release_status") == "verified" and not missing:
            production_status = "available"
        else:
            production_status = "blocked"
            production_reason = str(receipt.get("release_status") or "not_verified")
            if missing:
                production_reason = f"{production_reason}:missing_evidence={','.join(missing)}"

    lineage = {
        "product_version": PRODUCT_VERSION,
        "generated_at": (integrity or {}).get("generated_at") if integrity_status == "available" else _as_of(receipt) or _as_of(cases) or _as_of(truth),
        "source_as_of": {
            key: _as_of(payload)
            for key, payload in {
                "financial_truth_qualification": truth,
                "forecast_readiness": forecast_readiness,
                "intelligence_cases": cases,
                "impact_scenarios": scenarios,
                "financial_forecasts": forecasts,
                "formal_valuations": valuations,
                "market_expectations": expectations,
                "thesis_monitoring": theses,
                "artifact_integrity": integrity,
                "release_integrity_receipt": receipt,
            }.items()
        },
        "source_commit_sha": (integrity or {}).get("source_commit_sha") if integrity_status == "available" else None,
        "build_cutoff_at": (integrity or {}).get("build_cutoff_at") if integrity_status == "available" else None,
    }

    metrics = [
        _metric("model_ready_companies", "Model-ready companies", status=model_ready_metric_status, value=model_ready_value, denominator=ALPHA_DENOMINATORS["model_ready_companies"], definition="Count of companies whose financial_truth_qualification.status is qualified. Forecast-readiness input_ready is not treated as model-ready.", source_path=SOURCE_PATHS["financial_truth_qualification"], as_of=_as_of(truth), reason=model_ready_reason, notes=model_ready_notes),
        _metric("published_cases", "Published Intelligence Cases", status=published_status, value=published_value, denominator=ALPHA_DENOMINATORS["published_cases"], definition="Count of intelligence_cases with status Published. Observed seeds are listed in notes but do not count.", source_path=SOURCE_PATHS["intelligence_cases"], as_of=_as_of(cases), reason=published_reason, notes=published_notes),
        _metric("financially_computed_scenarios", "Financially computed scenarios", status=scenario_metric_status, value=scenario_value, denominator=ALPHA_DENOMINATORS["financially_computed_scenarios"], definition="Count of impact_scenarios rows whose revenue/EBITDA/EPS/FCF/valuation impact is non-null. Bear/Base/Bull shells with insufficient_data do not count.", source_path=SOURCE_PATHS["impact_scenarios"], as_of=_as_of(scenarios), reason=scenario_reason, notes=scenario_notes),
        _metric("live_forecast_outputs", "Live forecast outputs", status=forecast_metric_status, value=forecast_count, denominator=ALPHA_DENOMINATORS["live_forecast_outputs"], definition="Count of financial_forecasts companies with status computed and a non-null result.", source_path=SOURCE_PATHS["financial_forecasts"], as_of=_as_of(forecasts), reason=forecast_reason, notes=forecast_notes),
        _metric("live_valuation_outputs", "Live valuation outputs", status=valuation_metric_status, value=valuation_count, denominator=ALPHA_DENOMINATORS["live_valuation_outputs"], definition="Count of formal_valuations companies with status computed and a non-null result.", source_path=SOURCE_PATHS["formal_valuations"], as_of=_as_of(valuations), reason=valuation_reason, notes=valuation_notes),
        _metric("live_market_expectation_outputs", "Live market-expectation outputs", status=expectation_metric_status, value=expectation_count, denominator=ALPHA_DENOMINATORS["live_market_expectation_outputs"], definition="Count of market_expectations companies with status computed and a non-null result.", source_path=SOURCE_PATHS["market_expectations"], as_of=_as_of(expectations), reason=expectation_reason, notes=expectation_notes),
        _metric("ask_henneth_test_status", "Ask Henneth test status", status=ask_status, value=None, denominator=None, definition="Live Ask runtime proof must be a stored receipt. Local contract checkers are not treated as a production pass.", source_path="scripts/check_ask_henneth.mjs", as_of=None, reason=ask_reason, notes=ask_notes),
        _metric("active_thesis_monitoring_cases", "Active thesis-monitoring cases", status=thesis_metric_status, value=thesis_value, denominator=None, definition="Sum of thesis_monitoring.active_thesis_count across the 20-company pilot.", source_path=SOURCE_PATHS["thesis_monitoring"], as_of=_as_of(theses), reason=thesis_reason, notes=thesis_notes),
        _metric("required_output_nulls", "Required-output nulls", status=nulls_status, value=nulls_value, denominator=None, definition="Count of forecast, valuation, and market-expectation company rows whose result is null or not computed.", source_path="state/company_intel/financial_forecasts.json", as_of=_as_of(forecasts), reason=nulls_reason, notes=nulls_notes),
        _metric("provenance_coverage", "Provenance coverage", status=provenance_status, value=provenance_value, denominator=None, definition="Hashed artifact_integrity rows versus artifact_count, plus source_commit_sha from the finalizer envelope.", source_path=SOURCE_PATHS["artifact_integrity"], as_of=_as_of(integrity), reason=provenance_reason, notes=provenance_notes),
        _metric("no_lookahead_status", "No-lookahead status", status=lookahead_status, value=None, denominator=None, definition="No stored no-lookahead receipt exists. A pass requires scripts/check_ci_global_no_lookahead.py against the current tree.", source_path="scripts/check_ci_global_no_lookahead.py", as_of=None, reason=lookahead_reason, notes=lookahead_notes),
        _metric("production_gate_status", "Production gate status", status=production_status, value=(receipt or {}).get("release_status") if receipt_status == "available" else None, denominator=None, definition="Release is verified only when release_integrity_receipt.release_status is verified and every required_evidence row is pass for one commit.", source_path=SOURCE_PATHS["release_integrity_receipt"], as_of=_as_of(receipt), reason=production_reason, notes=production_notes),
    ]

    blocked = [row["id"] for row in metrics if row["status"] != "available"]
    result = {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "kind": "event_to_value_product_readiness",
        "as_of": lineage["generated_at"],
        "policy": {
            "research_only": True,
            "read_only_audit": True,
            "no_inferred_success": True,
            "no_advice": True,
            "distinct_from_intelligence_case_ui": True,
        },
        "source_paths": SOURCE_PATHS,
        "lineage": lineage,
        "summary": {
            "metric_count": len(metrics),
            "available_metric_count": len(metrics) - len(blocked),
            "blocked_metric_count": len(blocked),
            "blocked_metric_ids": blocked,
            "alpha_denominators": ALPHA_DENOMINATORS,
            "forecast_readiness_input_ready_count": ((forecast_readiness or {}).get("summary") or {}).get("ready_company_count") if forecast_ready_status == "available" else None,
            "forecast_readiness_is_not_model_ready": True,
        },
        "metrics": metrics,
    }
    if write:
        save_json(OUT, result)
        print(f"event_to_value_product_readiness: {result['summary']['available_metric_count']}/{result['summary']['metric_count']} available")
    return result


if __name__ == "__main__":
    build()
