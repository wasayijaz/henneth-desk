"""Synthetic and real-state checks for formal financial engines."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_formal_financial_engines as builder
from formal_financial_engines import build_company_engines
from psx_data import load_json


def fail(message: str) -> None:
    raise AssertionError(message)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def assert_clean_language(data: dict) -> None:
    text = json.dumps(data, sort_keys=True).lower()
    for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
        if phrase in text:
            fail(f"advice language leaked: {phrase}")


def assert_finite(data: dict) -> None:
    for key, value in walk(data):
        if isinstance(value, float) and not math.isfinite(value):
            fail(f"non-finite number at {key}")


def ready_model_row() -> dict:
    def fact(line, value):
        return {
            "fact_id": f"{line}-2023",
            "document_id": "psx:2023",
            "source_url": "https://dps.psx.com.pk/download/document/2023.pdf",
            "period_end": "2023-12-31",
            "available_on": "2024-02-15",
            "readiness": "model_loadable",
            "normalized_value": value,
        }
    return {
        "symbol": "MLCF",
        "status": "ready",
        "model_version": "cement_v1",
        "observations": {
            "revenue": [fact("revenue", 1000.0)],
            "profit_after_tax_attributable": [fact("profit_after_tax_attributable", 150.0)],
            "basic_eps": [fact("basic_eps", 1.5)],
        },
    }


def ready_assumptions(extra=None) -> dict:
    metrics = {
        "revenue_growth_pct": 10.0,
        "net_margin_pct": 20.0,
        "exit_pe": 5.0,
        "shares_out": 100.0,
        "net_debt": 50.0,
        "current_price": 11.0,
    }
    records = []
    for metric, value in metrics.items():
        records.append({
            "symbol": "MLCF",
            "metric": metric,
            "value": value,
            "approved": True,
            "available_on": "2024-02-20",
            "record_type": "approved_assumption" if metric.endswith("_pct") or metric == "exit_pe" else "approved_market_operand",
            "source": {
                "id": f"owner:{metric}:2024",
                "label": f"owner approved {metric}",
                "path": "state/company_intel/financial_engine_assumptions.json",
                "available_on": "2024-02-20",
            },
        })
    if extra:
        records.extend(extra)
    return {"records": records}


def qualified_financial_truth() -> dict:
    return {"status": "qualified", "financial_tie_out": {"status": "qualified"}}


def red_financial_truth() -> dict:
    return {"status": "not_qualified", "financial_tie_out": {"status": "blocked"}}


def assert_synthetic_ready() -> None:
    row = build_company_engines(
        "MLCF",
        ready_model_row(),
        {"status": "input_ready"},
        qualified_financial_truth(),
        ready_assumptions(),
        "2024-03-01",
    )
    forecast = row["forecast"]["result"]
    valuation = row["valuation"]["result"]
    expectations = row["market_expectations"]["result"]
    if not math.isclose(forecast["forecast_revenue"], 1100.0):
        fail("forecast revenue formula mismatch")
    if not math.isclose(forecast["forecast_profit_after_tax_attributable"], 220.0):
        fail("forecast PAT formula mismatch")
    if not math.isclose(forecast["forecast_basic_eps"], 2.2):
        fail("forecast EPS formula mismatch")
    if not math.isclose(valuation["formula_value_per_share"], 11.0):
        fail("valuation per-share formula mismatch")
    if not math.isclose(valuation["formula_enterprise_value"], 1150.0):
        fail("enterprise value formula mismatch")
    if not math.isclose(expectations["required_revenue_growth_pct"], 10.0):
        fail("reverse market expectations formula mismatch")
    expected_provenance = {"forecast": 6, "valuation": 8, "market_expectations": 8}
    for name, product in row.items():
        if product["status"] != "computed" or len(product["provenance"]) != expected_provenance[name]:
            fail("computed product missing provenance")
        assert_clean_language(product)
        assert_finite(product)


def assert_blocks() -> None:
    cases = {
        "missing_history": ({**ready_model_row(), "status": "partial"}, {"status": "input_ready"}, qualified_financial_truth(), ready_assumptions(), set()),
        "missing_readiness": (ready_model_row(), {"status": "blocked"}, qualified_financial_truth(), ready_assumptions(), set()),
        "missing_price": (ready_model_row(), {"status": "input_ready"}, qualified_financial_truth(), {"records": [r for r in ready_assumptions()["records"] if r["metric"] != "current_price"]}, {"forecast", "valuation"}),
        "missing_share_count": (ready_model_row(), {"status": "input_ready"}, qualified_financial_truth(), {"records": [r for r in ready_assumptions()["records"] if r["metric"] != "shares_out"]}, set()),
        "missing_net_debt": (ready_model_row(), {"status": "input_ready"}, qualified_financial_truth(), {"records": [r for r in ready_assumptions()["records"] if r["metric"] != "net_debt"]}, {"forecast", "market_expectations"}),
        "unapproved_assumption": (ready_model_row(), {"status": "input_ready"}, qualified_financial_truth(), {"records": [{**r, "approved": False} if r["metric"] == "exit_pe" else r for r in ready_assumptions()["records"]]}, {"forecast"}),
        "future_source": (ready_model_row(), {"status": "input_ready"}, qualified_financial_truth(), {"records": [{**r, "available_on": "2025-01-01"} if r["metric"] == "exit_pe" else r for r in ready_assumptions()["records"]]}, {"forecast"}),
        "audit_only_actual": ({**ready_model_row(), "observations": {**ready_model_row()["observations"], "revenue": [{**ready_model_row()["observations"]["revenue"][0], "readiness": "audit_only"}]}}, {"status": "input_ready"}, qualified_financial_truth(), ready_assumptions(), set()),
        "red_financial_truth": (ready_model_row(), {"status": "input_ready"}, red_financial_truth(), ready_assumptions(), set()),
    }
    for name, (model, readiness, financial_truth, assumptions, computed) in cases.items():
        row = build_company_engines("MLCF", model, readiness, financial_truth, assumptions, "2024-03-01")
        observed = {product for product, payload in row.items() if payload["status"] == "computed"}
        if observed != computed:
            fail(f"{name} computed {sorted(observed)}, expected {sorted(computed)}")
        for product, payload in row.items():
            if product not in computed and payload["result"] is not None:
                fail(f"{name} blocked product carried a result")
            if name == "red_financial_truth" and "financial_truth_qualified" not in payload.get("missing_requirements", []):
                fail("red financial truth did not fail-close every formal engine")


def assert_real_state() -> None:
    forecasts, valuations, expectations = builder.build()
    for state in (forecasts, valuations, expectations):
        assert_clean_language(state)
        assert_finite(state)
        if state["summary"]["computed_company_count"] != 0:
            fail(f"{state['kind']} unexpectedly computed real output")
        if state["summary"]["blocked_company_count"] != len(state["pilot_symbols"]):
            fail(f"{state['kind']} blocked count mismatch")
    before = [path.read_bytes() for path in (builder.OUT_FORECASTS, builder.OUT_VALUATIONS, builder.OUT_EXPECTATIONS)]
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_formal_financial_engines.py")], capture_output=True, text=True, timeout=30)
    after = [path.read_bytes() for path in (builder.OUT_FORECASTS, builder.OUT_VALUATIONS, builder.OUT_EXPECTATIONS)]
    if result.returncode != 0 or before != after:
        fail("builder is not byte-idempotent")
    slice_path = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
    if load_json(slice_path, {"tickers": []}).get("tickers") is None:
        fail("CI slice unreadable")


def assert_temp_builder_ready() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-formal-engines-") as td:
        root = Path(td)
        original_state = builder.STATE
        original_outs = builder.OUT_FORECASTS, builder.OUT_VALUATIONS, builder.OUT_EXPECTATIONS, builder.ASSUMPTIONS, builder.FINANCIAL_TRUTH
        try:
            builder.STATE = root
            builder.OUT_FORECASTS = root / "company_intel" / "financial_forecasts.json"
            builder.OUT_VALUATIONS = root / "company_intel" / "formal_valuations.json"
            builder.OUT_EXPECTATIONS = root / "company_intel" / "market_expectations.json"
            builder.ASSUMPTIONS = root / "company_intel" / "financial_engine_assumptions.json"
            builder.FINANCIAL_TRUTH = root / "company_intel" / "financial_truth_qualification.json"
            (root / "company_intel").mkdir(parents=True)
            (root / "company_profiles.json").write_text(json.dumps({"updated": "2024-03-01", "pilot": {"symbols": ["MLCF"]}}), encoding="utf-8")
            (root / "company_intel" / "financial_model_inputs.json").write_text(json.dumps({"companies": {"MLCF": ready_model_row()}}), encoding="utf-8")
            (root / "company_intel" / "forecast_readiness.json").write_text(json.dumps({"companies": {"MLCF": {"status": "input_ready"}}}), encoding="utf-8")
            (root / "company_intel" / "financial_truth_qualification.json").write_text(json.dumps({"companies": {"MLCF": qualified_financial_truth()}}), encoding="utf-8")
            (root / "company_intel" / "financial_engine_assumptions.json").write_text(json.dumps(ready_assumptions()), encoding="utf-8")
            forecasts, valuations, expectations = builder.build()
            if forecasts["summary"]["computed_company_count"] != 1:
                fail("temp builder did not compute forecast")
            if valuations["companies"]["MLCF"]["result"]["formula_enterprise_value"] != 1150.0:
                fail("temp builder valuation mismatch")
            if expectations["companies"]["MLCF"]["status"] != "computed":
                fail("temp builder expectations did not compute")
        finally:
            builder.STATE = original_state
            builder.OUT_FORECASTS, builder.OUT_VALUATIONS, builder.OUT_EXPECTATIONS, builder.ASSUMPTIONS, builder.FINANCIAL_TRUTH = original_outs


def main() -> None:
    assert_synthetic_ready()
    assert_blocks()
    assert_temp_builder_ready()
    assert_real_state()
    print("formal financial engines: PASS (synthetic computed, real state blocked)")


if __name__ == "__main__":
    main()
