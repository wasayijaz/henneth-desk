"""Build Forecast/Valuation Readiness Contract v1 state."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forecast_contract import (
    CONTRACT_VERSION,
    POLICIES,
    available_adapter_source_owners,
    available_adapter_versions,
    readiness_row,
    supported_registry_versions,
)
from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "forecast_readiness.json"


def _source_as_of(*states: dict) -> str | None:
    dates: list[str] = []
    for state in states:
        if not isinstance(state, dict):
            continue
        for key in ("updated", "fetched", "profile_updated"):
            value = state.get(key)
            if value:
                dates.append(str(value))
        meta = state.get("_meta") or state.get("meta") or {}
        if isinstance(meta, dict):
            for key in ("updated", "built", "as_of"):
                value = meta.get(key)
                if value:
                    dates.append(str(value))
    return max(dates) if dates else None


def build() -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    sectors = load_json(STATE / "sectors.json", {})
    financial_series = load_json(STATE / "company_financial_series.json", {"tickers": {}})
    financial_coverage = load_json(STATE / "company_intel" / "financial_coverage.json", {"companies": {}})
    pilot = sorted((profiles.get("pilot") or {}).get("symbols") or [])
    sector_rows = sectors.get("tickers") or {}
    companies = {}
    for symbol in pilot:
        facts = ((financial_series.get("tickers") or {}).get(symbol) or {}).get("facts") or []
        coverage_row = (financial_coverage.get("companies") or {}).get(symbol) or {}
        exchange_sector = (sector_rows.get(symbol) or {}).get("sector")
        companies[symbol] = readiness_row(symbol, exchange_sector, facts, coverage_row)
    result = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "as_of": _source_as_of(profiles, sectors, financial_series, financial_coverage),
        "pilot_symbols": pilot,
        "registry_versions": supported_registry_versions(),
        "adapter_versions": available_adapter_versions(),
        "adapter_source_owners": available_adapter_source_owners(),
        "policies": dict(POLICIES),
        "source": {
            "company_profiles": "state/company_profiles.json",
            "sectors": "state/sectors.json",
            "company_financial_series": "state/company_financial_series.json",
            "financial_coverage": "state/company_intel/financial_coverage.json",
            "sector_driver_models": "scripts/sector_driver_models.py",
        },
        "summary": {
            "company_count": len(companies),
            "ready_company_count": sum(1 for row in companies.values() if row.get("status") == "input_ready"),
            "history_qualified_company_count": sum(
                1 for row in companies.values()
                if row.get("status") in {"input_ready", "blocked_model_adapter_unavailable"}
            ),
            "adapter_unavailable_company_count": sum(
                1 for row in companies.values()
                if row.get("status") == "blocked_model_adapter_unavailable"
            ),
            "insufficient_history_company_count": sum(
                1 for row in companies.values()
                if row.get("status") == "blocked_insufficient_qualified_history"
            ),
            "blocked_company_count": sum(1 for row in companies.values() if row.get("status") != "input_ready"),
            "qualified_fact_company_count": sum(1 for row in companies.values() if row.get("qualified_period_count", 0) >= 1),
        },
        "companies": companies,
    }
    save_json(OUT, result)
    print(f"forecast_readiness: {result['summary']['ready_company_count']} ready / {len(companies)} pilot")
    return result


if __name__ == "__main__":
    build()
