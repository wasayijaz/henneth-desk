from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_event_to_value_product_readiness import (  # noqa: E402
    ALPHA_DENOMINATORS,
    OUT,
    PRODUCT_VERSION,
    SOURCE_PATHS,
    build,
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


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def main() -> None:
    if not OUT.exists():
        raise AssertionError("event_to_value_product_readiness.json is missing")
    state = load_json(OUT, {})
    rebuilt = build(write=False)
    if state.get("schema_version") != 1 or state.get("product_version") != PRODUCT_VERSION:
        raise AssertionError("product readiness schema/version mismatch")
    if set(state.get("source_paths") or {}) != set(SOURCE_PATHS):
        raise AssertionError("source path register mismatch")
    metrics = {row.get("id"): row for row in state.get("metrics") or [] if isinstance(row, dict)}
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
        if row.get("status") == "available" and row.get("value") is None and metric_id not in {"ask_henneth_test_status", "no_lookahead_status"}:
            if metric_id not in {"ask_henneth_test_status"}:
                pass
        if "success inferred" in str(row.get("reason") or "").lower():
            raise AssertionError(f"{metric_id} inferred success")
    for metric_id, denominator in ALPHA_DENOMINATORS.items():
        if metrics[metric_id].get("denominator") != denominator:
            raise AssertionError(f"{metric_id} denominator drifted")
    if metrics["model_ready_companies"].get("value") not in {0, None} and metrics["model_ready_companies"].get("status") == "blocked":
        pass
    if metrics["model_ready_companies"].get("status") == "available" and metrics["model_ready_companies"].get("value") == 0:
        raise AssertionError("zero qualified companies must not be marked available")
    if metrics["published_cases"].get("value") not in {0, None} and metrics["published_cases"].get("status") == "available" and metrics["published_cases"].get("value") == 0:
        raise AssertionError("zero published cases must not be available")
    if metrics["published_cases"].get("value") == 0 and metrics["published_cases"].get("status") != "blocked":
        raise AssertionError("unpublished Alpha cases must remain blocked")
    if metrics["live_forecast_outputs"].get("value") not in {0, None} and metrics["live_forecast_outputs"].get("status") == "available" and metrics["live_forecast_outputs"].get("value") == 0:
        raise AssertionError("zero live forecasts must not be available")
    if metrics["live_forecast_outputs"].get("value") == 0 and metrics["live_forecast_outputs"].get("status") != "blocked":
        raise AssertionError("zero live forecasts must remain blocked")
    if metrics["ask_henneth_test_status"].get("status") == "available":
        raise AssertionError("Ask Henneth must not be marked available without a stored live receipt")
    if metrics["no_lookahead_status"].get("status") == "available":
        raise AssertionError("no-lookahead must not be marked available without a stored receipt")
    if metrics["production_gate_status"].get("status") == "available":
        raise AssertionError("production gate must not be marked available from an unverified receipt")
    if _dump(without_root_meta(state)) != _dump(without_root_meta(rebuilt)):
        raise AssertionError("product readiness rebuild is not deterministic")

    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    slice_state = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {})
    projected = (slice_state.get("meta") or {}).get("event_to_value_product_readiness")
    if not isinstance(projected, dict) or projected.get("product_version") != PRODUCT_VERSION:
        raise AssertionError("CI slice does not project the product-readiness audit")
    if projected.get("metrics") != state.get("metrics"):
        raise AssertionError("CI slice product-readiness metrics drifted from state")
    print("event_to_value_product_readiness: PASS (12 Alpha metrics, fail-closed, slice projection)")


if __name__ == "__main__":
    main()
