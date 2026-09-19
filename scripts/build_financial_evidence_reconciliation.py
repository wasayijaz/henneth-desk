"""Build retained-state Financial Evidence Reconciliation v1."""
from __future__ import annotations

from psx_data import STATE, load_json, save_json
from financial_evidence_reconciliation import build_reconciliation


OUT = STATE / "company_intel" / "financial_evidence_reconciliation.json"


def build() -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = list((profiles.get("pilot") or {}).get("symbols") or [])
    financial_series = load_json(STATE / "company_financial_series.json", {"tickers": {}})
    financial_coverage = load_json(STATE / "company_intel" / "financial_coverage.json", {"companies": {}})
    financial_model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    forecast_readiness = load_json(STATE / "company_intel" / "forecast_readiness.json", {"companies": {}})
    derived_receipts = {
        "MLCF": load_json(STATE / "company_intel" / "mlcf_fy25_full_schedule_audit.json", {}),
    }
    result = build_reconciliation(
        pilot,
        financial_series,
        financial_coverage,
        financial_model_inputs,
        forecast_readiness,
        derived_receipts,
    )
    save_json(OUT, result)
    summary = result.get("summary") or {}
    print(
        "financial_evidence_reconciliation: "
        f"{summary.get('company_count', 0)} companies, "
        f"{summary.get('eligible_fact_count', 0)} eligible facts, "
        f"{summary.get('missing_slot_count', 0)} missing slots"
    )
    return result


if __name__ == "__main__":
    build()
