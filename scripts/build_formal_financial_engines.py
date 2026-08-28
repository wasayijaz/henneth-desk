"""Build source-gated formal financial engine state files."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from formal_financial_engines import (
    ENGINE_VERSION,
    EXPECTATIONS_FORMULA_ID,
    FORECAST_FORMULA_ID,
    VALUATION_FORMULA_ID,
    build_company_engines,
)
from psx_data import STATE, load_json, save_json


OUT_FORECASTS = STATE / "company_intel" / "financial_forecasts.json"
OUT_VALUATIONS = STATE / "company_intel" / "formal_valuations.json"
OUT_EXPECTATIONS = STATE / "company_intel" / "market_expectations.json"
ASSUMPTIONS = STATE / "company_intel" / "financial_engine_assumptions.json"
FINANCIAL_TRUTH = STATE / "company_intel" / "financial_truth_qualification.json"


def _as_of(*states: dict) -> str | None:
    values: list[str] = []
    for state in states:
        if not isinstance(state, dict):
            continue
        for key in ("as_of", "updated", "built"):
            value = state.get(key)
            if isinstance(value, str):
                values.append(value[:10])
        meta = state.get("meta") or state.get("_meta") or {}
        if isinstance(meta, dict):
            for key in ("as_of", "updated", "built"):
                value = meta.get(key)
                if isinstance(value, str):
                    values.append(value[:10])
    return max(values) if values else None


def _envelope(kind: str, formula_id: str, as_of: str | None, pilot: list[str], companies: dict) -> dict:
    return {
        "schema_version": 1,
        "engine_version": ENGINE_VERSION,
        "kind": kind,
        "as_of": as_of,
        "pilot_symbols": pilot,
        "formula_id": formula_id,
        "source": {
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
            "forecast_readiness": "state/company_intel/forecast_readiness.json",
            "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
            "financial_engine_assumptions": "state/company_intel/financial_engine_assumptions.json",
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_output_without_approved_source_labelled_assumptions": True,
            "no_audit_only_financial_facts": True,
            "financial_truth_is_authoritative_activation_gate": True,
        },
        "summary": {
            "company_count": len(companies),
            "computed_company_count": sum(1 for row in companies.values() if row.get("status") == "computed"),
            "blocked_company_count": sum(1 for row in companies.values() if row.get("status") != "computed"),
        },
        "companies": companies,
    }


def build() -> tuple[dict, dict, dict]:
    profiles = load_json(STATE / "company_profiles.json", {})
    model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    readiness = load_json(STATE / "company_intel" / "forecast_readiness.json", {"companies": {}})
    financial_truth = load_json(FINANCIAL_TRUTH, {"companies": {}})
    assumptions = load_json(ASSUMPTIONS, {"records": []})
    pilot = list((profiles.get("pilot") or {}).get("symbols") or model_inputs.get("pilot_symbols") or readiness.get("pilot_symbols") or [])
    as_of = _as_of(profiles, model_inputs, readiness, financial_truth, assumptions)
    forecasts, valuations, expectations = {}, {}, {}
    for symbol in pilot:
        built = build_company_engines(
            symbol,
            (model_inputs.get("companies") or {}).get(symbol) or {},
            (readiness.get("companies") or {}).get(symbol) or {},
            (financial_truth.get("companies") or {}).get(symbol) or {},
            assumptions,
            as_of,
        )
        forecasts[symbol] = built["forecast"]
        valuations[symbol] = built["valuation"]
        expectations[symbol] = built["market_expectations"]
    forecast_state = _envelope("financial_forecasts", FORECAST_FORMULA_ID, as_of, pilot, forecasts)
    valuation_state = _envelope("formal_valuations", VALUATION_FORMULA_ID, as_of, pilot, valuations)
    expectations_state = _envelope("market_expectations", EXPECTATIONS_FORMULA_ID, as_of, pilot, expectations)
    save_json(OUT_FORECASTS, forecast_state)
    save_json(OUT_VALUATIONS, valuation_state)
    save_json(OUT_EXPECTATIONS, expectations_state)
    print(
        "formal_financial_engines: "
        f"{forecast_state['summary']['computed_company_count']} computed / {len(pilot)} pilot"
    )
    return forecast_state, valuation_state, expectations_state


if __name__ == "__main__":
    build()
