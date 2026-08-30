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
    _source_contract_reason,
    _engine_live_count,
    _integrity_status,
)
from build_ci_slice import build as build_ci_slice  # noqa: E402
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


def _case_fixture(selected_symbols: list[object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "case_product_version": "observed_intelligence_case_seed_v2",
        "as_of": "2026-08-30T21:42:58+05:00",
        "pilot_symbols": ["MLCF", "MARI", "PSO"],
        "selected_symbols": selected_symbols,
        "status_lifecycle": ["Observed", "Corroborated", "Modelled", "Validated", "Published"],
        "policy": {},
        "summary": {"company_count": 3, "observed_case_count": 0, "published_case_count": 0},
        "companies": {"MLCF": {}, "MARI": {}, "PSO": {}},
    }


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
    canonical_artifacts = _base_artifacts()
    canonical_rebuilt = build(write=False, artifacts=canonical_artifacts)
    canonical_metrics = _metric_map(canonical_rebuilt)
    if canonical_rebuilt.get("reason") != "selected_symbols_not_exactly_three:count=2":
        raise AssertionError(f"canonical sources rejected for wrong reason: {canonical_rebuilt.get('reason')}")
    canonical_provenance = canonical_metrics["provenance_coverage"]
    allowed_integrity_blockers = {
        "artifact_integrity_manifest_paths_drifted",
        "artifact_integrity_incomplete",
        "artifact_integrity_manifest_hashes_stale",
        "event_to_value_product_readiness_not_in_artifact_integrity_manifest",
        "event_to_value_product_readiness_hash_mismatch",
        "event_to_value_product_readiness_not_generated",
    }
    if canonical_provenance.get("status") == "available":
        details = canonical_rebuilt.get("lineage", {}).get("artifact_integrity") or {}
        if details.get("covered") is not True or details.get("hash_status") != "verified":
            raise AssertionError(f"canonical sealed manifest lacked verified readiness coverage: {details}")
    elif canonical_provenance.get("reason") not in allowed_integrity_blockers:
        raise AssertionError(f"canonical manifest failed for an unexpected integrity reason: {canonical_provenance.get('reason')}")
    expected_canonical_contract_reasons = {}
    for name, (payload, _) in canonical_artifacts.items():
        if name in {"artifact_integrity", "release_integrity_receipt"}:
            continue
        reason = _source_contract_reason(name, payload)
        if reason and ("kind" in reason or "status_missing" in reason):
            raise AssertionError(f"canonical {name} was rejected for synthetic envelope fields: {reason}")
        if name in expected_canonical_contract_reasons and reason != expected_canonical_contract_reasons[name]:
            raise AssertionError(f"canonical {name} should fail only on strict freshness today: {reason}")
        if name not in expected_canonical_contract_reasons and reason is not None:
            raise AssertionError(f"canonical {name} failed producer-specific contract: {reason}")

    missing = derive_selected_symbols({**_case_fixture([]), "selected_symbols": None}, "available")
    if missing["reason"] != "selected_symbols_missing":
        raise AssertionError(f"missing selection reason drifted: {missing}")
    duplicate = derive_selected_symbols(_case_fixture(["MLCF", "MARI", "MLCF"]), "available")
    if duplicate["reason"] != "selected_symbols_duplicate":
        raise AssertionError(f"duplicate selection reason drifted: {duplicate}")
    non_string = derive_selected_symbols(_case_fixture(["MLCF", 7, "MARI"]), "available")
    if non_string["reason"] != "selected_symbols_invalid":
        raise AssertionError(f"non-string selection reason drifted: {non_string}")
    unknown_symbol = derive_selected_symbols(_case_fixture(["MLCF", "MARI", "FAKE"]), "available")
    if unknown_symbol["reason"] != "selected_symbol_unknown:FAKE":
        raise AssertionError(f"unknown selection reason drifted: {unknown_symbol}")
    missing_source_field = derive_selected_symbols({"schema_version": 1, "selected_symbols": ["MLCF", "MARI", "PSO"], "companies": {"MLCF": {}, "MARI": {}, "PSO": {}}}, "available")
    if missing_source_field["reason"] != "intelligence_cases_case_product_version_missing":
        raise AssertionError(f"missing source field was accepted: {missing_source_field}")
    garbage_source = derive_selected_symbols({**_case_fixture(["MLCF", "MARI", "PSO"]), "status": "garbage"}, "available")
    if not str(garbage_source["reason"]).startswith("intelligence_cases_status_not_healthy"):
        raise AssertionError(f"garbage source status was accepted: {garbage_source}")
    partial_source = derive_selected_symbols({**_case_fixture(["MLCF", "MARI", "PSO"]), "status": "partial"}, "available")
    if not str(partial_source["reason"]).startswith("intelligence_cases_status_not_healthy"):
        raise AssertionError(f"partial source status was accepted: {partial_source}")
    wrong_kind_source = derive_selected_symbols({**_case_fixture(["MLCF", "MARI", "PSO"]), "kind": "financial_forecasts"}, "available")
    if not str(wrong_kind_source["reason"]).startswith("intelligence_cases_kind_invalid"):
        raise AssertionError(f"wrong source kind was accepted: {wrong_kind_source}")
    bogus_time_source = derive_selected_symbols({**_case_fixture(["MLCF", "MARI", "PSO"]), "as_of": "2026-01-01junk"}, "available")
    if not str(bogus_time_source["reason"]).startswith("intelligence_cases_as_of_invalid"):
        raise AssertionError(f"bogus source timestamp was accepted: {bogus_time_source}")
    loose_time_source = derive_selected_symbols({**_case_fixture(["MLCF", "MARI", "PSO"]), "as_of": "2026-01-01 00:00:00"}, "available")
    if not str(loose_time_source["reason"]).startswith("intelligence_cases_as_of_invalid"):
        raise AssertionError(f"space-separated source timestamp was accepted: {loose_time_source}")
    not_three = derive_selected_symbols(_case_fixture(["MARI", "MLCF"]), "available")
    if not str(not_three["reason"] or "").startswith("selected_symbols_not_exactly_three"):
        raise AssertionError(f"not-three selection reason drifted: {not_three}")

    import build_event_to_value_product_readiness as readiness_module
    original_load_json = readiness_module.load_json
    try:
        def json_error_for_cases(path, default):
            if str(path).replace("\\", "/").endswith("state/company_intel/intelligence_cases.json"):
                raise json.JSONDecodeError("broken", "{", 0)
            return original_load_json(path, default)
        readiness_module.load_json = json_error_for_cases
        malformed_json_result = build(write=False)
    finally:
        readiness_module.load_json = original_load_json
    if malformed_json_result.get("status") != "blocked" or malformed_json_result.get("reason") != "intelligence_cases_load_error:JSONDecodeError":
        raise AssertionError(f"malformed source JSON did not fail closed: {malformed_json_result.get('reason')}")

    try:
        def oserror_for_forecasts(path, default):
            if str(path).replace("\\", "/").endswith("state/company_intel/financial_forecasts.json"):
                raise OSError("simulated read failure")
            return original_load_json(path, default)
        readiness_module.load_json = oserror_for_forecasts
        oserror_result = build(write=False)
    finally:
        readiness_module.load_json = original_load_json
    if oserror_result.get("lineage", {}).get("source_reason", {}).get("financial_forecasts") != "financial_forecasts_load_error:OSError":
        raise AssertionError("OSError source load did not encode a deterministic source blocker")

    artifacts = _base_artifacts()
    cases = copy.deepcopy(artifacts["intelligence_cases"][0])
    cases["kind"] = "intelligence_cases"
    cases["status"] = "available"
    cases["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    companies = cases.setdefault("companies", {})
    for symbol in ("MARI", "MLCF", "PSO"):
        companies.setdefault(symbol, {"symbol": symbol, "cases": []})
    forecasts = copy.deepcopy(artifacts["financial_forecasts"][0])
    forecasts.setdefault("companies", {})["DGKC"] = {
        "symbol": "DGKC",
        "status": "computed",
        "result": {"forecast_basic_eps": 1},
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
    mismatched_case_artifacts = copy.deepcopy(artifacts)
    mismatched_cases = copy.deepcopy(cases)
    mismatched_cases.setdefault("companies", {}).setdefault("MARI", {"symbol": "MARI", "cases": []})["cases"] = [
        {"case_id": "case_wrong_symbol", "symbol": "DGKC", "status": "Published"}
    ]
    mismatched_case_artifacts["intelligence_cases"] = (mismatched_cases, "available")
    mismatched_case_result = build(write=False, artifacts=mismatched_case_artifacts)
    if _metric_map(mismatched_case_result)["published_cases"].get("value") != 0:
        raise AssertionError("mismatched nested case symbol counted as selected published case")
    bad_engine = {
        "schema_version": 1,
        "engine_version": "formal_financial_engines_v1",
        "kind": "financial_forecasts",
        "as_of": "2026-08-29",
        "pilot_symbols": ["MARI", "MLCF", "PSO"],
        "formula_id": "formal_financial_engines_v1",
        "source": {},
        "policy": {},
        "summary": {"company_count": 3, "computed_company_count": 0, "blocked_company_count": 0},
        "companies": {
            "MARI": {"symbol": "MARI", "status": "computed", "result": {"forecast_basic_eps": "1.2"}, "provenance": [{"run_id": "x"}]},
            "MLCF": {"symbol": "MLCF", "status": "computed", "result": {"forecast_basic_eps": float("nan")}, "provenance": [{"run_id": "x"}]},
            "PSO": {"symbol": "PSO", "status": "computed", "result": {"forecast_basic_eps": 1.2}, "provenance": [{"source": "inferred"}]},
            "DGKC": {"symbol": "DGKC", "status": "computed", "result": {"forecast_basic_eps": 1.2}, "provenance": [{"run_id": "x"}]},
        },
    }
    bad_count, bad_status, bad_reason, bad_notes = _engine_live_count(bad_engine, "available", ["MARI", "MLCF", "PSO"], "financial_forecasts")
    if bad_count != 0 or bad_status != "blocked" or bad_notes:
        raise AssertionError(f"invalid engine rows counted: {bad_count}, {bad_status}, {bad_reason}, {bad_notes}")
    junk_engine = copy.deepcopy(bad_engine)
    junk_engine["companies"]["MARI"] = {
        "symbol": "MARI",
        "status": "computed",
        "result": {"junk": 1},
        "provenance": [{"source_path": "state/company_intel/financial_forecasts.json", "run_id": "test-run"}],
    }
    junk_count, junk_status, _, junk_notes = _engine_live_count(junk_engine, "available", ["MARI"], "financial_forecasts")
    if junk_count != 0 or junk_status != "blocked" or junk_notes:
        raise AssertionError("junk formal output key must not count as a live engine output")
    weak_lineage_engine = copy.deepcopy(bad_engine)
    weak_lineage_engine["companies"]["MARI"] = {
        "symbol": "MARI",
        "status": "computed",
        "result": {"forecast_basic_eps": 1.2},
        "provenance": [{"run_id": "test-run"}],
    }
    weak_count, weak_status, _, weak_notes = _engine_live_count(weak_lineage_engine, "available", ["MARI"], "financial_forecasts")
    if weak_count != 0 or weak_status != "blocked" or weak_notes:
        raise AssertionError("run-only engine lineage must not count as a live output")
    evil_lineage_engine = copy.deepcopy(bad_engine)
    evil_lineage_engine["companies"]["MARI"] = {
        "symbol": "MARI",
        "status": "computed",
        "result": {
            "forecast_revenue": 1.2,
            "forecast_profit_after_tax_attributable": 1.2,
            "forecast_basic_eps": 1.2,
        },
        "provenance": [{"source_path": "evil.json", "run_id": "test-run"}],
    }
    evil_count, evil_status, _, evil_notes = _engine_live_count(evil_lineage_engine, "available", ["MARI"], "financial_forecasts")
    if evil_count != 0 or evil_status != "blocked" or evil_notes:
        raise AssertionError("engine provenance with arbitrary source_path must not count")
    partial_result_engine = copy.deepcopy(bad_engine)
    partial_result_engine["companies"]["MARI"] = {
        "symbol": "MARI",
        "status": "computed",
        "result": {"forecast_basic_eps": 1.2},
        "provenance": [{"source_path": "state/company_intel/financial_forecasts.json", "run_id": "test-run"}],
    }
    partial_count, partial_status, _, partial_notes = _engine_live_count(partial_result_engine, "available", ["MARI"], "financial_forecasts")
    if partial_count != 0 or partial_status != "blocked" or partial_notes:
        raise AssertionError("partial engine result contract must not count")
    good_engine = copy.deepcopy(bad_engine)
    good_engine["companies"]["MARI"] = {
        "symbol": "MARI",
        "status": "computed",
        "result": {
            "forecast_revenue": 1.2,
            "forecast_profit_after_tax_attributable": 1.2,
            "forecast_basic_eps": 1.2,
        },
        "provenance": [{"source_path": "state/company_intel/financial_forecasts.json", "run_id": "test-run"}],
    }
    good_count, good_status, _, good_notes = _engine_live_count(good_engine, "available", ["MARI", "MLCF", "PSO"], "financial_forecasts")
    if good_count != 1 or good_status != "available" or good_notes != ["MARI"]:
        raise AssertionError(f"valid source-bound engine row was not counted: {good_count}, {good_status}, {good_notes}")
    mismatched_engine = copy.deepcopy(good_engine)
    mismatched_engine["companies"]["MARI"]["symbol"] = "DGKC"
    mismatched_count, mismatched_status, _, mismatched_notes = _engine_live_count(mismatched_engine, "available", ["MARI"], "financial_forecasts")
    if mismatched_count != 0 or mismatched_status != "blocked" or mismatched_notes:
        raise AssertionError("mismatched nested engine row identity must not count")

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
    source_only = {
        "impact_status": "computed",
        "revenue_impact": 1.5,
        "lineage": {"source_path": "state/company_intel/impact_scenarios.json"},
    }
    if financial_impact_computed(source_only):
        raise AssertionError("source-only computed impact must remain uncounted")
    evil_impact_path = {
        "scenario_id": "scn_test",
        "event_id": "evt_test",
        "company_id": "MARI",
        "impact_status": "computed",
        "revenue_impact": 1.5,
        "ebitda_impact": 1.5,
        "eps_impact": 1.5,
        "fcf_impact": 1.5,
        "valuation_impact": 1.5,
        "lineage": {"source_path": "evil.json", "run_id": "test-run"},
    }
    if financial_impact_computed(evil_impact_path):
        raise AssertionError("impact provenance with arbitrary source_path must not count")
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
    if not financial_impact_computed(valid, "MARI"):
        raise AssertionError("explicit computed finite impact with matching selected identity must count")
    mismatched_impact = copy.deepcopy(valid)
    mismatched_impact["company_id"] = "DGKC"
    if financial_impact_computed(mismatched_impact, "MARI"):
        raise AssertionError("mismatched nested scenario company_id must not count")
    partial_impact = copy.deepcopy(valid)
    partial_impact.pop("fcf_impact")
    if financial_impact_computed(partial_impact):
        raise AssertionError("partial impact contract must remain uncounted")

    if not any(rel(path) == READINESS_REL for path in artifact_paths()):
        raise AssertionError("readiness artifact is not in the normal integrity path")
    original_artifact_paths = readiness_module.artifact_paths
    try:
        def raise_oserror():
            raise OSError("simulated missing slice")
        readiness_module.artifact_paths = raise_oserror
        _, os_status, os_reason, _, _ = _integrity_status({
            "schema_version": 1,
            "kind": "ci_artifact_integrity_manifest",
            "source_commit_sha": "0" * 40,
            "build_cutoff_at": "2026-08-30T17:58:30Z",
            "generated_at": "2026-08-30T17:58:30Z",
            "artifact_count": 0,
            "artifacts": [],
        })
    finally:
        readiness_module.artifact_paths = original_artifact_paths
    if os_status != "blocked" or os_reason != "artifact_integrity_expected_paths_unavailable:OSError":
        raise AssertionError(f"artifact path OSError did not fail closed: {os_status}, {os_reason}")

    slice_state = build_ci_slice(write=False)
    projected = (slice_state.get("meta") or {}).get("event_to_value_product_readiness")
    expected = project_readiness(state)
    if not isinstance(projected, dict):
        raise AssertionError("CI slice does not project the product-readiness audit")
    if projected.get("status") != expected.get("status") or projected.get("reason") != expected.get("reason"):
        raise AssertionError("CI slice projected an inferred-available readiness payload")
    stored_slice = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {})
    stored_projected = (stored_slice.get("meta") or {}).get("event_to_value_product_readiness")
    if not isinstance(stored_projected, dict):
        raise AssertionError("stored CI slice does not include product-readiness projection")
    if stored_projected.get("status") != expected.get("status") or stored_projected.get("reason") != expected.get("reason"):
        raise AssertionError(
            "stored CI slice product-readiness projection is stale: "
            f"{stored_projected.get('status')}:{stored_projected.get('reason')} != "
            f"{expected.get('status')}:{expected.get('reason')}"
        )
    if _dump(without_root_meta(stored_slice)) != _dump(without_root_meta(slice_state)):
        raise AssertionError("stored CI slice differs from build_ci_slice(write=False)")
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
    wrong_count = copy.deepcopy(state)
    wrong_count["status"] = "available"
    wrong_count.setdefault("summary", {})["available_metric_count"] = "0"
    projected_wrong_count = project_readiness(wrong_count)
    if projected_wrong_count.get("status") != "blocked" or "available_metric_count" not in str(projected_wrong_count.get("reason")):
        raise AssertionError("string summary available count must fail closed")
    missing_count = copy.deepcopy(state)
    missing_count["status"] = "available"
    missing_count.setdefault("summary", {}).pop("available_metric_count", None)
    projected_missing_count = project_readiness(missing_count)
    if projected_missing_count.get("status") != "blocked" or "available_metric_count" not in str(projected_missing_count.get("reason")):
        raise AssertionError("missing summary available count must fail closed")
    all_blocked_available = copy.deepcopy(state)
    all_blocked_available["status"] = "available"
    all_blocked_available["reason"] = None
    for row in all_blocked_available.get("metrics") or []:
        row["status"] = "blocked"
        row["reason"] = row.get("reason") or "adversarial_all_blocked"
        row.setdefault("lineage", {})["status"] = "blocked"
        row["lineage"]["reason"] = row["reason"]
    all_blocked_available.setdefault("summary", {})["available_metric_count"] = 0
    all_blocked_available["summary"]["blocked_metric_count"] = 12
    all_blocked_available["summary"]["blocked_metric_ids"] = [row["id"] for row in all_blocked_available.get("metrics") or []]
    all_blocked_available["summary"]["selected_symbols_status"] = "available"
    all_blocked_available["summary"]["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    all_blocked_available.setdefault("lineage", {})["selected_symbols_status"] = "available"
    all_blocked_available["lineage"]["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    all_blocked_available["lineage"].setdefault("source_as_of", {})["forecast_readiness"] = "2026-08-29T16:39:00+05:00"
    original_current_source_maps = readiness_module._current_source_maps
    try:
        readiness_module._current_source_maps = lambda: (
            all_blocked_available["lineage"]["source_as_of"],
            all_blocked_available["lineage"]["source_schema_version"],
            all_blocked_available["lineage"]["source_kind"],
            all_blocked_available["lineage"]["source_status"],
            all_blocked_available["lineage"]["source_reason"],
        )
        projected_all_blocked_available = project_readiness(all_blocked_available)
    finally:
        readiness_module._current_source_maps = original_current_source_maps
    if projected_all_blocked_available.get("status") != "blocked" or projected_all_blocked_available.get("reason") != "event_to_value_product_readiness_all_metrics_blocked":
        raise AssertionError("all-blocked metrics must override top-level available")
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
    bad_commit_projection = copy.deepcopy(state)
    bad_commit_projection.setdefault("lineage", {})["source_commit_sha"] = "0" * 40
    projected_bad_commit = project_readiness(bad_commit_projection)
    if projected_bad_commit.get("status") != "blocked" or "source_commit_sha" not in str(projected_bad_commit.get("reason")):
        raise AssertionError("projected readiness with bad source_commit_sha must bind to current integrity")
    fake_integrity_projection = copy.deepcopy(state)
    fake_integrity_projection.setdefault("summary", {})["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    fake_integrity_projection["summary"]["selected_symbols_status"] = "available"
    fake_integrity_projection["summary"]["selected_symbols_reason"] = None
    fake_integrity_projection.setdefault("lineage", {})["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    fake_integrity_projection["lineage"]["selected_symbols_status"] = "available"
    fake_integrity_projection["lineage"]["selected_symbols_reason"] = None
    fake_integrity_projection["lineage"].setdefault("source_status", {})["intelligence_cases"] = "available"
    fake_integrity_projection["lineage"].setdefault("source_reason", {})["intelligence_cases"] = None
    fake_integrity_projection.setdefault("lineage", {})["artifact_integrity"] = {
        "covered": False,
        "manifest_artifact_count": 0,
        "expected_artifact_count": 43,
        "missing_paths": [],
        "extra_paths": [],
        "hash_status": "verified",
    }
    original_current_source_maps = readiness_module._current_source_maps
    try:
        readiness_module._current_source_maps = lambda: (
            fake_integrity_projection["lineage"]["source_as_of"],
            fake_integrity_projection["lineage"]["source_schema_version"],
            fake_integrity_projection["lineage"]["source_kind"],
            fake_integrity_projection["lineage"]["source_status"],
            fake_integrity_projection["lineage"]["source_reason"],
        )
        projected_fake_integrity = project_readiness(fake_integrity_projection)
    finally:
        readiness_module._current_source_maps = original_current_source_maps
    if projected_fake_integrity.get("status") != "blocked" or "artifact_integrity" not in str(projected_fake_integrity.get("reason")):
        raise AssertionError("projected readiness with fake artifact_integrity details must fail closed")
    future_metric = copy.deepcopy(state)
    future_metric.setdefault("metrics", [])[0]["as_of"] = "2099-01-01T00:00:00Z"
    projected_future_metric = project_readiness(future_metric)
    if projected_future_metric.get("status") != "blocked" or "as_of_after_build_cutoff" not in str(projected_future_metric.get("reason")):
        raise AssertionError("metric as_of after build cutoff must fail closed")
    bogus_metric_time = copy.deepcopy(state)
    bogus_metric_time.setdefault("metrics", [])[0]["as_of"] = "bogus"
    projected_bogus_metric_time = project_readiness(bogus_metric_time)
    if projected_bogus_metric_time.get("status") != "blocked" or "metric_as_of_invalid" not in str(projected_bogus_metric_time.get("reason")):
        raise AssertionError("bogus metric as_of must fail closed")
    loose_metric_time = copy.deepcopy(state)
    loose_metric_time.setdefault("metrics", [])[0]["as_of"] = "2026-01-01 00:00:00"
    projected_loose_metric_time = project_readiness(loose_metric_time)
    if projected_loose_metric_time.get("status") != "blocked" or "metric_as_of_invalid" not in str(projected_loose_metric_time.get("reason")):
        raise AssertionError("space-separated metric as_of must fail closed")
    bogus_source_time = copy.deepcopy(state)
    bogus_source_time.setdefault("lineage", {}).setdefault("source_as_of", {})["intelligence_cases"] = "2026-01-01junk"
    projected_bogus_source_time = project_readiness(bogus_source_time)
    if projected_bogus_source_time.get("status") != "blocked" or "source_as_of_invalid" not in str(projected_bogus_source_time.get("reason")):
        raise AssertionError("bogus source_as_of must fail closed")
    conflicting_summary = copy.deepcopy(state)
    conflicting_summary.setdefault("summary", {})["selected_symbols"] = ["MARI", "MARI", "MLCF"]
    projected_conflicting_summary = project_readiness(conflicting_summary)
    if projected_conflicting_summary.get("status") != "blocked" or "selected_symbols_mismatch" not in str(projected_conflicting_summary.get("reason")):
        raise AssertionError("conflicting summary/lineage selected symbols must fail closed")
    conflicting_source_status = copy.deepcopy(state)
    conflicting_source_status.setdefault("lineage", {}).setdefault("source_status", {})["artifact_integrity"] = "available"
    conflicting_source_status["lineage"].setdefault("source_as_of", {})["forecast_readiness"] = "2026-08-29T16:39:00+05:00"
    original_current_source_maps = readiness_module._current_source_maps
    actual_source_status = copy.deepcopy(conflicting_source_status["lineage"]["source_status"])
    actual_source_status["artifact_integrity"] = "blocked"
    try:
        readiness_module._current_source_maps = lambda: (
            conflicting_source_status["lineage"]["source_as_of"],
            conflicting_source_status["lineage"]["source_schema_version"],
            conflicting_source_status["lineage"]["source_kind"],
            actual_source_status,
            conflicting_source_status["lineage"]["source_reason"],
        )
        projected_conflicting_source_status = project_readiness(conflicting_source_status)
    finally:
        readiness_module._current_source_maps = original_current_source_maps
    if projected_conflicting_source_status.get("status") != "blocked" or "source_status_mismatch" not in str(projected_conflicting_source_status.get("reason")):
        raise AssertionError("projected source status must bind back to canonical source artifacts")
    bad_metric_lineage = copy.deepcopy(state)
    bad_metric_lineage.setdefault("metrics", [])[0]["lineage"] = "not-a-lineage-object"
    projected_bad_metric_lineage = project_readiness(bad_metric_lineage)
    if projected_bad_metric_lineage.get("status") != "blocked" or "metric_lineage" not in str(projected_bad_metric_lineage.get("reason")):
        raise AssertionError("metric lineage shape must fail closed")
    bad_source_maps = copy.deepcopy(state)
    bad_source_maps.setdefault("summary", {})["available_metric_count"] = sum(1 for row in bad_source_maps.get("metrics") or [] if row.get("status") == "available")
    bad_source_maps["summary"]["blocked_metric_count"] = sum(1 for row in bad_source_maps.get("metrics") or [] if row.get("status") != "available")
    bad_source_maps["summary"]["blocked_metric_ids"] = [row["id"] for row in bad_source_maps.get("metrics") or [] if row.get("status") != "available"]
    bad_source_maps["summary"]["selected_symbols_status"] = "available"
    bad_source_maps["summary"]["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    bad_source_maps.setdefault("lineage", {})["selected_symbols_status"] = "available"
    bad_source_maps["lineage"]["selected_symbols"] = ["MARI", "MLCF", "PSO"]
    bad_source_maps.setdefault("lineage", {}).setdefault("source_as_of", {})["forecast_readiness"] = "2026-08-29T16:39:00+05:00"
    bad_source_maps.setdefault("lineage", {}).pop("source_status", None)
    projected_bad_source_maps = project_readiness(bad_source_maps)
    if projected_bad_source_maps.get("status") != "blocked" or "source_status" not in str(projected_bad_source_maps.get("reason")):
        raise AssertionError("missing source_status lineage must fail closed")
    print("event_to_value_product_readiness: PASS (selected-three, computed-status, integrity path, fail-closed projection)")


if __name__ == "__main__":
    main()
