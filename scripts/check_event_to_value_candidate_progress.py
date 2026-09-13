"""Focused checks for Event-to-Value candidate-lane partial progress.

This intentionally avoids the retained readiness artifact so stored-state or
integrity-manifest drift cannot mask the candidate-progress contract.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_event_to_value_product_readiness import (  # noqa: E402
    ALPHA_DENOMINATORS,
    SOURCE_PATHS,
    build,
    candidate_lane_progress,
    derive_selected_symbols,
)
from psx_data import ROOT, load_json  # noqa: E402

ACCEPTANCE_METRIC_IDS = tuple(ALPHA_DENOMINATORS) + ("required_output_nulls",)


def _load_pair(rel_path: str) -> tuple[dict, str]:
    payload = load_json(ROOT / rel_path, {})
    return payload, "available"


def _base_artifacts() -> dict[str, tuple[dict, str]]:
    return {name: _load_pair(path) for name, path in SOURCE_PATHS.items()}


def _metric_map(result: dict) -> dict[str, dict]:
    return {
        row["id"]: row
        for row in result.get("metrics") or []
        if isinstance(row, dict) and row.get("id")
    }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fixture_companies = {symbol: {"symbol": symbol, "cases": []} for symbol in ("MARI", "MLCF", "PSO")}
    two_symbol_selection = derive_selected_symbols(
        {"selected_symbols": ["MARI", "MLCF"], "companies": fixture_companies},
        "available",
    )
    partial = candidate_lane_progress(
        two_symbol_selection,
        cases={
            "as_of": "2026-09-01T00:00:00Z",
            "companies": {
                "MARI": {"status": "observed_seed_available", "cases": [{"status": "Observed"}]},
                "MLCF": {"status": "observed_seed_available", "cases": [{"status": "Observed"}]},
            },
        },
        truth={"companies": {"MARI": {}, "MLCF": {}}},
        forecasts={"companies": {}},
        valuations={"companies": {}},
        expectations={"companies": {}},
    )
    _assert(isinstance(partial, dict), "valid two-symbol lane must expose partial progress")
    _assert(partial["status"] == "partial", "two-symbol candidate progress status drifted")
    _assert(partial["symbols"] == ["MARI", "MLCF"], "two-symbol candidate symbols drifted")
    _assert(partial["selected_symbol_count"] == 2, "two-symbol candidate count drifted")
    _assert(partial["missing_symbol_count"] == 1, "two-symbol missing count drifted")
    _assert(partial["alpha_gate_status"] == "blocked", "partial lane weakened Alpha gate status")
    _assert(partial["does_not_change_alpha_gate"] is True, "partial lane must remain informational")
    _assert(set(partial["lanes"]) == {"MARI", "MLCF"}, "partial lane rows drifted")

    full_selection = derive_selected_symbols(
        {"selected_symbols": ["MARI", "MLCF", "PSO"], "companies": fixture_companies},
        "available",
    )
    full_progress = candidate_lane_progress(
        full_selection,
        cases={"as_of": "2026-09-01T00:00:00Z", "companies": fixture_companies},
        truth={"companies": {}},
        forecasts={"companies": {}},
        valuations={"companies": {}},
        expectations={"companies": {}},
    )
    _assert(full_selection["status"] == "available", "exact-three selection should be available")
    _assert(full_progress is None, "exact-three selection must not emit a partial envelope")

    unknown_selection = derive_selected_symbols(
        {"selected_symbols": ["MARI", "UNKNOWN"], "companies": fixture_companies},
        "available",
    )
    unknown_progress = candidate_lane_progress(
        unknown_selection,
        cases={"as_of": "2026-09-01T00:00:00Z", "companies": fixture_companies},
        truth={"companies": {}},
        forecasts={"companies": {}},
        valuations={"companies": {}},
        expectations={"companies": {}},
    )
    _assert(unknown_selection["reason"] == "selected_symbol_unknown:UNKNOWN", "unknown-symbol reason drifted")
    _assert(unknown_progress is None, "unknown selection must not emit a partial envelope")

    malformed_selection = derive_selected_symbols(
        {"selected_symbols": ["MARI", ""], "companies": fixture_companies},
        "available",
    )
    malformed_progress = candidate_lane_progress(
        malformed_selection,
        cases={"as_of": "2026-09-01T00:00:00Z", "companies": fixture_companies},
        truth={"companies": {}},
        forecasts={"companies": {}},
        valuations={"companies": {}},
        expectations={"companies": {}},
    )
    _assert(malformed_selection["reason"] == "selected_symbols_invalid", "malformed-symbol reason drifted")
    _assert(malformed_progress is None, "malformed selection must not emit a partial envelope")

    artifacts = _base_artifacts()
    cases = copy.deepcopy(artifacts["intelligence_cases"][0])
    cases["selected_symbols"] = ["MARI", "MLCF"]
    cases.setdefault("companies", {}).update(fixture_companies)
    artifacts["intelligence_cases"] = (cases, "available")
    result = build(write=False, artifacts=artifacts)
    metrics = _metric_map(result)
    _assert(result["lineage"]["selected_symbols_status"] == "blocked", "partial selection should keep readiness blocked")
    _assert(isinstance(result["lineage"]["candidate_lane_progress"], dict), "partial build should expose candidate progress")
    for metric_id in ACCEPTANCE_METRIC_IDS:
        metric = metrics.get(metric_id)
        _assert(isinstance(metric, dict), f"{metric_id} missing from readiness metrics")
        _assert(metric.get("status") != "available", f"{metric_id} activated from partial candidate progress")
        _assert(metric.get("value") is None, f"{metric_id} produced a value from partial candidate progress")

    print("event_to_value_candidate_progress: PASS")


if __name__ == "__main__":
    main()
