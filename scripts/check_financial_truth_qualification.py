"""Checks for strict financial-truth qualification state."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import build_financial_truth_qualification as builder
from financial_truth_qualification import build_qualification
from psx_data import load_json


ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise AssertionError(message)


def _strict_fixture_facts(include_quarter_scope: bool = True) -> list[dict]:
    annual_periods = [f"202{year}-06-30" for year in range(0, 5)]
    quarter_periods = [
        "2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31",
        "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
    ]
    facts = []
    for period in annual_periods:
        for metric in ("revenue", "profit_after_tax_attributable", "basic_eps"):
            facts.append({
                "status": "eligible",
                "metric": metric,
                "period_end": period,
                "period_type": "annual",
                "statement_type": "income_statement",
                "consolidation": "consolidated",
                "eligibility_scope": "annual_income_financial_truth_gate",
            })
        facts.append({
            "status": "eligible",
            "metric": "operating_cash_flow",
            "period_end": period,
            "period_type": "annual",
            "statement_type": "cash_flow_statement",
            "consolidation": "consolidated",
            "eligibility_scope": "annual_operating_cash_flow_truth_gate",
        })
    for period in quarter_periods:
        for metric in ("revenue", "profit_after_tax_attributable", "basic_eps"):
            facts.append({
                "status": "eligible",
                "metric": metric,
                "period_end": period,
                "period_type": "quarter",
                "duration_months": 3,
                "statement_type": "income_statement",
                "consolidation": "consolidated",
                "eligibility_scope": (
                    "reported_quarter_financial_truth_gate"
                    if include_quarter_scope
                    else "annual_income_financial_truth_gate"
                ),
            })
    return facts


def _share_tie_out(symbol: str = "AAA") -> dict:
    return {
        "symbol": symbol,
        "metric": "shares_out",
        "record_type": "official_share_count_capital_note_tie_out",
        "approved": True,
        "available_on": "2025-01-01",
        "source": {
            "id": "psx:fixture",
            "label": "official capital note",
            "url": "https://dps.psx.com.pk/download/document/1.pdf",
        },
    }


def assert_quarter_scope_fixtures() -> None:
    scoped_fixture = build_qualification(
        ["AAA"],
        {"companies": {"AAA": {"facts": _strict_fixture_facts(), "source_conflict_count": 0}}},
        {"companies": {"AAA": {"indexed_official_financial_docs": []}}},
        {"records": [_share_tie_out()]},
        {"companies": {}},
    )
    scoped_row = scoped_fixture["companies"]["AAA"]
    if scoped_row.get("status") != "qualified":
        fail("scoped quarter fixture did not become qualified")
    if scoped_row.get("qualified_reported_quarter_fact_sets", {}).get("present") != 8:
        fail("scoped quarter fixture did not satisfy exactly eight reported-quarter fact sets")
    if scoped_row.get("downstream", {}).get("forecast") != "not_activated_owner_approved_forward_inputs_required":
        fail("qualified financial truth activated forecast without owner-approved forward inputs")

    unscoped_fixture = build_qualification(
        ["AAA"],
        {"companies": {"AAA": {"facts": _strict_fixture_facts(include_quarter_scope=False), "source_conflict_count": 0}}},
        {"companies": {"AAA": {"indexed_official_financial_docs": []}}},
        {"records": [_share_tie_out()]},
        {"companies": {}},
    )
    unscoped_row = unscoped_fixture["companies"]["AAA"]
    if unscoped_row.get("status") == "qualified":
        fail("unscoped quarter-like fixture became qualified")
    if unscoped_row.get("qualified_reported_quarter_fact_sets", {}).get("present") != 0:
        fail("unscoped quarter-like facts counted toward the eight-quarter gate")
    if unscoped_row.get("annual_income_triplets", {}).get("present") != 5:
        fail("unscoped quarter-like facts polluted annual income triplets")


def main() -> None:
    expected = builder.build()
    if json.dumps(expected, sort_keys=True) != json.dumps(builder.build(), sort_keys=True):
        fail("builder output is not deterministic")
    pilot = expected.get("pilot_symbols") or []
    companies = expected.get("companies") or {}
    if len(pilot) != 20 or set(companies) != set(pilot):
        fail("financial truth state must contain exactly the CI pilot")
    if expected.get("selection", {}).get("status") != "leading_candidate_not_golden":
        fail("current retained evidence must not claim a golden candidate")
    leader = expected.get("selection", {}).get("leader_symbol")
    if not leader or (companies.get(leader) or {}).get("selection_status") != "leading_candidate_not_golden":
        fail("leader selection is not reflected in its company row")
    for symbol in pilot:
        row = companies.get(symbol) or {}
        if row.get("status") != "not_qualified":
            fail(f"{symbol}: financial truth cannot be qualified without every strict gate")
        if row.get("financial_tie_out", {}).get("status") != "blocked":
            fail(f"{symbol}: financial tie-out must remain blocked")
        if row.get("downstream", {}).get("forecast") != "blocked_financial_truth_not_qualified":
            fail(f"{symbol}: forecast must remain blocked")
        if row.get("policy", {}).get("raw_financial_values") != "not_emitted":
            fail(f"{symbol}: qualification must not emit raw financial values")
        if not isinstance(row.get("candidate_rank"), int) or row["candidate_rank"] < 1:
            fail(f"{symbol}: missing deterministic rank")
        for key, required in (("annual_income_triplets", 5), ("qualified_reported_quarter_fact_sets", 8), ("annual_operating_cash_flow", 5)):
            value = row.get(key) or {}
            if value.get("required") != required or not isinstance(value.get("present"), int):
                fail(f"{symbol}: invalid {key} requirement")
    fixture = build_qualification(
        ["AAA", "BBB"],
        {"companies": {"AAA": {"facts": []}, "BBB": {"facts": []}}},
        {"companies": {"AAA": {"indexed_official_financial_docs": []}, "BBB": {"indexed_official_financial_docs": []}}},
        {"records": []},
        {"companies": {}},
    )
    if fixture["selection"]["leader_symbol"] != "AAA" or fixture["companies"]["AAA"]["status"] != "not_qualified":
        fail("deterministic empty-evidence fixture failed")
    qualified_fixture = build_qualification(
        ["AAA"],
        {"companies": {"AAA": {"facts": _strict_fixture_facts(), "source_conflict_count": 0}}},
        {"companies": {"AAA": {"indexed_official_financial_docs": []}}},
        {"records": [_share_tie_out()]},
        {"companies": {}},
    )
    qualified_row = qualified_fixture["companies"]["AAA"]
    if qualified_row.get("status") != "qualified" or qualified_row.get("financial_tie_out", {}).get("status") != "qualified":
        fail("complete strict-evidence fixture did not become qualified")
    if qualified_fixture.get("summary", {}).get("qualified_company_count") != 1 or qualified_fixture.get("selection", {}).get("status") != "qualified_financial_truth":
        fail("complete strict-evidence fixture did not transition selection state")
    assert_quarter_scope_fixtures()
    before = builder.OUT.read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_financial_truth_qualification.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or builder.OUT.read_bytes() != before:
        fail("builder output is not byte-idempotent")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail(result.stdout + result.stderr)
    slice_data = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {"tickers": []})
    for row in slice_data.get("tickers") or []:
        if row.get("financial_truth_qualification") != companies.get(row.get("symbol")):
            fail(f"{row.get('symbol')}: CI slice financial truth qualification mismatch")
    print(f"financial_truth_qualification: PASS ({len(pilot)} companies, leader {leader})")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"financial_truth_qualification: FAIL - {error}")
        raise SystemExit(1)
