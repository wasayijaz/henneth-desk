from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ci_artifact_integrity import artifact_paths, canonical_hash, rel  # noqa: E402
from build_event_to_value_product_readiness import (  # noqa: E402
    ALPHA_DENOMINATORS,
    OUT,
    PRODUCT_VERSION,
    READINESS_REL,
    REQUIRED_GOLDEN_COUNT,
    SOURCE_PATHS,
    build,
    candidate_lane_progress,
    derive_selected_symbols,
    financial_impact_computed,
    project_readiness,
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

    fixture_companies = {symbol: {} for symbol in ("MARI", "MLCF", "PSO")}
    missing = derive_selected_symbols({"selected_symbols": None, "companies": fixture_companies}, "available")
    if missing["reason"] != "selected_symbols_missing":
        raise AssertionError(f"missing selection reason drifted: {missing}")
    duplicate = derive_selected_symbols({"selected_symbols": ["MLCF", "MARI", "MLCF"], "companies": fixture_companies}, "available")
    if duplicate["reason"] != "selected_symbols_duplicate":
        raise AssertionError(f"duplicate selection reason drifted: {duplicate}")
    not_three = derive_selected_symbols({"selected_symbols": ["MARI", "MLCF"], "companies": fixture_companies}, "available")
    if not str(not_three["reason"] or "").startswith("selected_symbols_not_exactly_three"):
        raise AssertionError(f"not-three selection reason drifted: {not_three}")

    partial = candidate_lane_progress(
        not_three,
        cases={"as_of": "2026-09-01T00:00:00Z", "companies": {"MARI": {"status": "observed_seed_available", "cases": []}, "MLCF": {"status": "observed_seed_available", "cases": []}}},
        truth={"companies": {"MARI": {}, "MLCF": {}}},
        forecasts={"companies": {}},
        valuations={"companies": {}},
        expectations={"companies": {}},
    )
    if not isinstance(partial, dict) or partial.get("status") != "partial":
        raise AssertionError(f"valid incomplete selection lost candidate progress: {partial}")
    if partial.get("alpha_gate_status") != "blocked" or partial.get("does_not_change_alpha_gate") is not True:
        raise AssertionError("candidate progress weakened the exact-three Alpha gate")
    if partial.get("selected_symbol_count") != 2 or partial.get("missing_symbol_count") != 1:
        raise AssertionError(f"candidate progress counts drifted: {partial}")
    full = derive_selected_symbols({"selected_symbols": ["MARI", "MLCF", "PSO"], "companies": fixture_companies}, "available")
    if candidate_lane_progress(full, cases={}, truth={}, forecasts={}, valuations={}, expectations={}) is not None:
        raise AssertionError("complete trio incorrectly emitted partial candidate progress")
    malformed_partial = derive_selected_symbols({"selected_symbols": ["MARI", "UNKNOWN"], "companies": fixture_companies}, "available")
    if candidate_lane_progress(malformed_partial, cases={}, truth={}, forecasts={}, valuations={}, expectations={}) is not None:
        raise AssertionError("unknown selection incorrectly emitted candidate progress")

    artifacts = _base_artifacts()
    cases = copy.deepcopy(artifacts["intelligence_cases"][0])
    cases["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    companies = cases.setdefault("companies", {})
    for symbol in ("MARI", "MLCF", "PSO"):
        companies.setdefault(symbol, {"symbol": symbol, "cases": []})
    forecasts = copy.deepcopy(artifacts["financial_forecasts"][0])
    forecasts.setdefault("companies", {})["DGKC"] = {"symbol": "DGKC", "status": "computed", "result": {"eps": 1}, "reason": None}
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

    malformed = {
        "impact_status": "unmodeled_driver",
        "quality_flags": ["unmodeled_driver"],
        "revenue_impact": 12.5,
        "lineage": {"source": "inferred"},
    }
    if financial_impact_computed(malformed):
        raise AssertionError("malformed non-null unmodeled impact must remain uncounted")
    valid = {
        "scenario_id": "scn_test",
        "event_id": "evt_test",
        "company_id": "MARI",
        "impact_status": "computed",
        "revenue_impact": 1.5,
        "ebitda_impact": 1.5,
        "eps_impact": 1.5,
        "fcf_impact": 1.5,
        "valuation_impact": 1.5,
        "lineage": {"source_path": "state/company_intel/impact_scenarios.json", "formula_id": "formal_scenario.v1", "run_id": "test-run"},
    }
    if not financial_impact_computed(valid):
        raise AssertionError("explicit computed finite impact with lineage must count")

    if not any(rel(path) == READINESS_REL for path in artifact_paths()):
        raise AssertionError("readiness artifact is not in the normal integrity path")
    manifest = load_json(ROOT / "state/company_intel/artifact_integrity.json", {})
    manifest_row = next((row for row in manifest.get("artifacts", []) if isinstance(row, dict) and row.get("path") == READINESS_REL), None)
    if not manifest_row or manifest_row.get("sha256") != canonical_hash(state):
        raise AssertionError("readiness artifact is not covered by the canonical integrity manifest")
    tampered = copy.deepcopy(state)
    tampered.setdefault("summary", {})["metric_count"] = 999
    if manifest_row.get("sha256") == canonical_hash(tampered):
        raise AssertionError("tampered readiness artifact unexpectedly matched manifest hash")

    import build_ci_slice
    slice_state = build_ci_slice.build(write=False)
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
    print("event_to_value_product_readiness: PASS (selected-three, computed-status, integrity path, fail-closed projection)")


if __name__ == "__main__":
    main()
