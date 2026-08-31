"""Build the retained-evidence financial-truth qualification scorecard."""
from __future__ import annotations

from financial_truth_qualification import build_qualification
from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "financial_truth_qualification.json"


def build() -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = list((profiles.get("pilot") or {}).get("symbols") or [])
    assumptions = load_json(STATE / "company_intel" / "financial_engine_assumptions.json", {"records": []})
    approved_shares = load_json(STATE / "company_intel" / "official_share_capital_approvals.json", {"records": []})
    result = build_qualification(
        pilot,
        load_json(STATE / "company_intel" / "financial_evidence_reconciliation.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "financial_coverage.json", {"companies": {}}),
        {"records": list(assumptions.get("records") or []) + list(approved_shares.get("records") or [])},
        load_json(STATE / "company_intel" / "cement_operating_series.json", {"companies": {}}),
    )
    save_json(OUT, result)
    print(f"financial_truth_qualification: {result['summary']['company_count']} companies, leader {result['selection']['leader_symbol'] or 'none'}")
    return result


if __name__ == "__main__":
    build()
