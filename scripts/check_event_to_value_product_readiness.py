from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ci_artifact_integrity import artifact_paths, rel  # noqa: E402
from build_event_to_value_product_readiness import (  # noqa: E402
    ALPHA_DENOMINATORS,
    OUT,
    PRODUCT_VERSION,
    READINESS_REL,
    REQUIRED_GOLDEN_COUNT,
    SOURCE_PATHS,
    build,
    derive_selected_symbols,
    financial_impact_computed,
    project_readiness,
    _engine_live_count,
)
from ci_checker_helpers import without_root_meta  # noqa: E402
from psx_data import ROOT, load_json  # noqa: E402

REQUIRED_IDS = (
    "model_ready_companies",
    "published_cases",
    "financially_computed_scenarios",
    "live_forecast_outputs",
    "live_valuation_outputs",
    "live_market_expectation_outputs",
    "ask_henneth_test_status",
    "active_thesis_monitoring_cases",
    "required_output_nulls",
    "provenance_coverage",
    "no_lookahead_status",
    "production_gate_status",
)
COUNTED_IDS = (
    "model_ready_companies",
    "published_cases",
    "financially_computed_scenarios",
    "live_forecast_outputs",
    "live_valuation_outputs",
    "live_market_expectation_outputs",
    "required_output_nulls",
)


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _load_pair(rel_path: str) -> tuple[dict, str]:
    payload = load_json(ROOT / rel_path, {})
    return payload, "available"


def _base_artifacts() -> dict[str, tuple[dict, str]]:
    return {name: _load_pair(path) for name, path in SOURCE_PATHS.items()}


def _metric_map(result: dict) -> dict[str, dict]:
    return {row["id"]: row for row in result.get("metrics") or [] if isinstance(row, dict) and row.get("id")}


def main() -> None:
    if not OUT.exists():
        raise AssertionError("event_to_value_product_readiness.json is missing")
    state = load_json(OUT, {})
    rebuilt = build(write=False)
    if state.get("schema_version") != 1 or state.get("product_version") != PRODUCT_VERSION:
        raise AssertionError("product readiness schema/version mismatch")
    if set(state.get("source_paths") or {}) != set(SOURCE_PATHS):
        raise AssertionError("source path register mismatch")
    metrics = _metric_map(state)
    if tuple(metrics) != REQUIRED_IDS:
        raise AssertionError(f"metric identity/order mismatch: {list(metrics)}")
    for metric_id, row in metrics.items():
        for key in ("label", "status", "definition", "source_path"):
            if not row.get(key):
                raise AssertionError(f"{metric_id} missing {key}")
        if row.get("status") not in {"available", "blocked", "unknown", "not_generated"}:
            raise AssertionError(f"{metric_id} has non-explicit status {row.get('status')}")
        if row.get("status") != "available" and not row.get("reason"):
            raise AssertionError(f"{metric_id} blocked/unknown without reason")
    for metric_id, denominator in ALPHA_DENOMINATORS.items():
        if metrics[metric_id].get("denominator") != denominator:
            raise AssertionError(f"{metric_id} denominator drifted")
    lineage = state.get("lineage") or {}
    selected = lineage.get("selected_symbols") or []
    if lineage.get("selected_symbols_status") == "available" and len(selected) != REQUIRED_GOLDEN_COUNT:
        raise AssertionError("available selection must be exactly three symbols")
    if lineage.get("selected_symbols_status") != "available":
        if not lineage.get("selected_symbols_reason"):
            raise AssertionError("blocked selection missing reason")
        for metric_id in COUNTED_IDS:
            if metrics[metric_id].get("value") not in {None, 0} and metrics[metric_id].get("status") == "available":
                raise AssertionError(f"{metric_id} must not be available without a valid selected trio")
    if metrics["ask_henneth_test_status"].get("status") == "available":
        raise AssertionError("Ask Henneth must not be marked available without a stored live receipt")
    if metrics["no_lookahead_status"].get("status") == "available":
        raise AssertionError("no-lookahead must not be marked available without a stored receipt")
    if metrics["production_gate_status"].get("status") == "available":
        raise AssertionError("production gate must not be marked available from an unverified receipt")
    if _dump(without_root_meta(state)) != _dump(without_root_meta(rebuilt)):
        raise AssertionError("product readiness rebuild is not deterministic")

    missing = derive_selected_symbols({"selected_symbols": None, "companies": {}}, "available")
    if missing["reason"] != "selected_symbols_missing":
        raise AssertionError(f"missing selection reason drifted: {missing}")
    duplicate = derive_selected_symbols({"selected_symbols": ["MLCF", "MARI", "MLCF"], "companies": {"MLCF": {}, "MARI": {}}}, "available")
    if duplicate["reason"] != "selected_symbols_duplicate":
        raise AssertionError(f"duplicate selection reason drifted: {duplicate}")
    non_string = derive_selected_symbols({"selected_symbols": ["MLCF", 7, "MARI"], "companies": {"MLCF": {}, "MARI": {}}}, "available")
    if non_string["reason"] != "selected_symbols_invalid":
        raise AssertionError(f"non-string selection reason drifted: {non_string}")
    unknown_symbol = derive_selected_symbols({"selected_symbols": ["MLCF", "MARI", "FAKE"], "companies": {"MLCF": {}, "MARI": {}}}, "available")
    if unknown_symbol["reason"] != "selected_symbol_unknown:FAKE":
        raise AssertionError(f"unknown selection reason drifted: {unknown_symbol}")
    garbage_source = derive_selected_symbols({"status": "garbage", "selected_symbols": ["MLCF", "MARI", "PSO"], "companies": {"MLCF": {}, "MARI": {}, "PSO": {}}}, "available")
    if not str(garbage_source["reason"]).startswith("intelligence_cases_status_invalid"):
        raise AssertionError(f"garbage source status was accepted: {garbage_source}")
    not_three = derive_selected_symbols({"selected_symbols": ["MARI", "MLCF"], "companies": {"MARI": {}, "MLCF": {}}}, "available")
    if not str(not_three["reason"] or "").startswith("selected_symbols_not_exactly_three"):
        raise AssertionError(f"not-three selection reason drifted: {not_three}")

    artifacts = _base_artifacts()
    cases = copy.deepcopy(artifacts["intelligence_cases"][0])
    cases["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    companies = cases.setdefault("companies", {})
    for symbol in ("MARI", "MLCF", "PSO"):
        companies.setdefault(symbol, {"symbol": symbol, "cases": []})
    forecasts = copy.deepcopy(artifacts["financial_forecasts"][0])
    forecasts.setdefault("companies", {})["DGKC"] = {
        "symbol": "DGKC",
        "status": "computed",
        "result": {"eps": 1},
        "reason": None,
        "provenance": [{"source_path": "state/company_intel/financial_forecasts.json", "run_id": "test-run"}],
    }
    companies.setdefault("DGKC", {"symbol": "DGKC", "cases": [{"case_id": "case_unselected", "symbol": "DGKC", "status": "Published"}]})
    artifacts["intelligence_cases"] = (cases, "available")
    artifacts["financial_forecasts"] = (forecasts, "available")
    injected = build(write=False, artifacts=artifacts)
    injected_metrics = _metric_map(injected)
    if injected["lineage"]["selected_symbols"] != ["MARI", "MLCF", "PSO"]:
        raise AssertionError("injected selected trio was not used")
    if injected_metrics["published_cases"].get("value") != 0:
        raise AssertionError("unselected Published case changed published_cases")
    if injected_metrics["live_forecast_outputs"].get("value") != 0:
        raise AssertionError("unselected computed forecast changed live_forecast_outputs")
    bad_engine = {
        "status": "available",
        "companies": {
            "MARI": {"symbol": "MARI", "status": "computed", "result": {"eps": "1.2"}, "provenance": [{"run_id": "x"}]},
            "MLCF": {"symbol": "MLCF", "status": "computed", "result": {"eps": float("nan")}, "provenance": [{"run_id": "x"}]},
            "PSO": {"symbol": "PSO", "status": "computed", "result": {"eps": 1.2}, "provenance": [{"source": "inferred"}]},
            "DGKC": {"symbol": "DGKC", "status": "computed", "result": {"eps": 1.2}, "provenance": [{"run_id": "x"}]},
        },
    }
    bad_count, bad_status, bad_reason, bad_notes = _engine_live_count(bad_engine, "available", ["MARI", "MLCF", "PSO"])
    if bad_count != 0 or bad_status != "blocked" or bad_notes:
        raise AssertionError(f"invalid engine rows counted: {bad_count}, {bad_status}, {bad_reason}, {bad_notes}")
    good_engine = copy.deepcopy(bad_engine)
    good_engine["companies"]["MARI"] = {
        "symbol": "MARI",
        "status": "computed",
        "result": {"eps": 1.2},
        "provenance": [{"source_path": "state/company_intel/financial_forecasts.json", "run_id": "test-run"}],
    }
    good_count, good_status, _, good_notes = _engine_live_count(good_engine, "available", ["MARI", "MLCF", "PSO"])
    if good_count != 1 or good_status != "available" or good_notes != ["MARI"]:
        raise AssertionError(f"valid source-bound engine row was not counted: {good_count}, {good_status}, {good_notes}")

    malformed = {
        "impact_status": "unmodeled_driver",
        "quality_flags": ["unmodeled_driver"],
        "revenue_impact": 12.5,
        "lineage": {"source": "inferred"},
    }
    if financial_impact_computed(malformed):
        raise AssertionError("malformed non-null unmodeled impact must remain uncounted")
    inferred = {
        "impact_status": "computed",
        "revenue_impact": 1.5,
        "lineage": {"source": "inferred"},
    }
    if financial_impact_computed(inferred):
        raise AssertionError("inferred-only computed impact must remain uncounted")
    string_number = {
        "impact_status": "computed",
        "revenue_impact": "1.5",
        "lineage": {"source_path": "state/company_intel/impact_scenarios.json", "run_id": "test-run"},
    }
    if financial_impact_computed(string_number):
        raise AssertionError("string numeric impact must remain uncounted")
    nan_number = {
        "impact_status": "computed",
        "revenue_impact": float("nan"),
        "lineage": {"source_path": "state/company_intel/impact_scenarios.json", "run_id": "test-run"},
    }
    if financial_impact_computed(nan_number):
        raise AssertionError("NaN impact must remain uncounted")
    valid = {
        "impact_status": "computed",
        "revenue_impact": 1.5,
        "lineage": {"source_path": "state/company_intel/impact_scenarios.json", "formula_id": "formal_scenario.v1", "run_id": "test-run"},
    }
    if not financial_impact_computed(valid):
        raise AssertionError("explicit computed finite impact with lineage must count")

    if not any(rel(path) == READINESS_REL for path in artifact_paths()):
        raise AssertionError("readiness artifact is not in the normal integrity path")

    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    slice_state = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {})
    projected = (slice_state.get("meta") or {}).get("event_to_value_product_readiness")
    expected = project_readiness(state)
    if not isinstance(projected, dict):
        raise AssertionError("CI slice does not project the product-readiness audit")
    if projected.get("status") != expected.get("status") or projected.get("reason") != expected.get("reason"):
        raise AssertionError("CI slice projected an inferred-available readiness payload")
    if projected.get("status") == "available" and projected.get("metrics") != state.get("metrics"):
        raise AssertionError("CI slice product-readiness metrics drifted from state")
    bogus = project_readiness({"metrics": [{"id": "model_ready_companies", "value": 3}]})
    if bogus.get("status") == "available":
        raise AssertionError("truthy metrics must not project available")
    garbage_status = copy.deepcopy(state)
    garbage_status["status"] = "garbage"
    projected_garbage = project_readiness(garbage_status)
    if projected_garbage.get("status") != "blocked" or "status_invalid" not in str(projected_garbage.get("reason")):
        raise AssertionError("garbage readiness status must fail closed")
    duplicate_projection = copy.deepcopy(state)
    duplicate_projection.setdefault("lineage", {})["selected_symbols_status"] = "available"
    duplicate_projection["lineage"]["selected_symbols"] = ["MARI", "MARI", "MLCF"]
    projected_duplicate = project_readiness(duplicate_projection)
    if projected_duplicate.get("status") != "blocked":
        raise AssertionError("duplicate projected selection must fail closed")
    stale_projection = copy.deepcopy(state)
    stale_projection.setdefault("lineage", {})["selected_symbols_status"] = "available"
    stale_projection["lineage"]["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    stale_projection["status"] = "available"
    stale_projection["reason"] = None
    stale_projection["lineage"]["source_commit_sha"] = "671a59e50c66b10226bc897fbb37862d597147e3"
    stale_projection["lineage"]["build_cutoff_at"] = "2026-08-30T17:58:30Z"
    stale_projection["lineage"]["generated_at"] = "2026-08-30T17:58:30Z"
    projected_stale = project_readiness(stale_projection)
    if projected_stale.get("status") != "blocked" or not projected_stale.get("reason"):
        raise AssertionError("stale or unsealed projected readiness must fail closed")
    print("event_to_value_product_readiness: PASS (selected-three, computed-status, integrity path, fail-closed projection)")


if __name__ == "__main__":
    main()
