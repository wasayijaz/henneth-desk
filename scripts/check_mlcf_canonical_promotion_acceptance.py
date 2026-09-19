"""Acceptance check for the consumed MLCF annual filing promotion.

This is a read-only post-consume check.  The audit receipts remain quarantined;
the canonical ledger is accepted only when the consumed document supplies the
exact FY2024/FY2025 full annual schedules and all downstream gates stay closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
CI = STATE / "company_intel"

DOCUMENT_ID = "psx:260032"
SOURCE_HASH = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"
SOURCE_URL = "https://dps.psx.com.pk/download/document/260032.pdf"
PERIODS = ("2024-06-30", "2025-06-30")
EXPECTED_IDENTITY_COUNT = 73
EXPECTED_EVENT_ID_DIGEST = "06fac5816ebd8fd68e6ed35fb705de01ed74e5fc93b7a4c708e08ea014be50e0"
EXPECTED_STUDY_ID_DIGEST = "4723daa2e6d058c8de296c23d93e78df83a6ca1b0c21eaa136b13211a1f83578"

DIRECT_METRICS = {
    "revenue", "gross_profit", "operating_profit", "finance_cost",
    "profit_before_tax", "tax_expense", "profit_after_tax_attributable",
    "basic_eps", "operating_cash_flow", "capital_expenditure",
    "net_cash_from_investing_activities", "net_cash_from_financing_activities",
    "dividends_paid", "cash_and_cash_equivalents", "trade_receivables",
    "inventories", "total_current_assets", "property_plant_equipment",
    "total_assets", "short_term_borrowings", "long_term_borrowings",
    "trade_payables", "total_equity",
}
DERIVED_METRICS = {"depreciation_amortization", "ebitda"}
ANNUAL_SCOPES = {
    "annual_income_financial_truth_gate",
    "annual_balance_sheet_financial_truth_gate",
    "annual_cash_flow_financial_truth_gate",
}


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"missing artifact: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _identity(path: Path, key: str) -> tuple[int, str]:
    data = _load(path)
    if key == "event_id":
        rows = [event for company in (data.get("companies") or {}).values() for event in company.get("events") or []]
    else:
        rows = list((data.get("studies") or {}).values())
    identities = sorted(str(row.get(key)) for row in rows if row.get(key))
    payload = json.dumps(identities, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return len(identities), hashlib.sha256(payload).hexdigest()


def _check_identity_surface() -> None:
    for name, key, expected_digest in (("operating_events.json", "event_id", EXPECTED_EVENT_ID_DIGEST), ("event_studies.json", "study_id", EXPECTED_STUDY_ID_DIGEST)):
        count, digest = _identity(CI / name, key)
        _assert(count == EXPECTED_IDENTITY_COUNT, f"{name}: expected {EXPECTED_IDENTITY_COUNT} identities, got {count}")
        _assert(digest == expected_digest, f"{name}: identity set changed ({digest})")


def _check_annual_schedule() -> None:
    truth = _load(CI / "financial_truth_qualification.json")["companies"]["MLCF"]
    annual = truth["model_ready_financial_statement_coverage"]["annual"]
    _assert(annual["required"] == 5, "annual gate must remain five periods")

    reconciliation = _load(CI / "financial_evidence_reconciliation.json")["companies"]["MLCF"]
    _assert(reconciliation["source_conflict_count"] == 0 and reconciliation.get("conflicts") == [], "MLCF has load-bearing canonical conflicts")
    for period in PERIODS:
        facts = [fact for fact in reconciliation.get("facts") or []
                 if fact.get("status") == "eligible"
                 and fact.get("period_end") == period
                 and fact.get("source", {}).get("document_id") == DOCUMENT_ID]
        _assert(len(facts) == 25, f"{period}: expected 25 consumed schedule facts, got {len(facts)}")
        by_metric = {fact.get("metric"): fact for fact in facts}
        _assert(set(by_metric) == DIRECT_METRICS | DERIVED_METRICS, f"{period}: annual metric coverage mismatch")
        for metric, fact in by_metric.items():
            _assert(fact.get("period_type") == "annual" and fact.get("duration_months") == 12, f"{period}/{metric}: not annual")
            _assert(fact.get("consolidation") == "consolidated", f"{period}/{metric}: not consolidated")
            _assert(fact.get("source", {}).get("content_sha256") == SOURCE_HASH, f"{period}/{metric}: source hash mismatch")
            _assert(fact.get("source", {}).get("source_url") == SOURCE_URL, f"{period}/{metric}: source URL mismatch")
            _assert(fact.get("eligibility_scope") in ANNUAL_SCOPES, f"{period}/{metric}: wrong annual eligibility scope")
            if metric in DERIVED_METRICS:
                _assert(fact.get("epistemic_type") == "derived_fact" and fact.get("derived_lineage_validated") is True, f"{period}/{metric}: derived lineage not validated")
            else:
                _assert(fact.get("epistemic_type") == "reported_fact", f"{period}/{metric}: direct fact is not reported")
    _assert(annual["present"] in (0, 2), "annual qualification summary has an invalid coverage count")
    if annual["present"] == 2:
        _assert(annual["qualified_periods"] == ["2025-06-30", "2024-06-30"], "MLCF annual summary coverage is not exactly FY2024/FY2025")


def _check_source_and_share_tie_out() -> None:
    receipts = _load(CI / "reprocess_receipts.json").get("receipts") or []
    matching = [row for row in receipts if row.get("doc_id") == DOCUMENT_ID and row.get("status") == "success"]
    _assert(matching and matching[-1].get("canonical_state_committed") is True, "MLCF consume receipt is not a successful canonical commit")
    _assert(matching[-1].get("content_sha256") == SOURCE_HASH and matching[-1].get("source_url") == SOURCE_URL, "MLCF consume receipt source identity mismatch")

    approvals = _load(CI / "official_share_capital_approvals.json").get("records") or []
    row = next((item for item in approvals if item.get("symbol") == "MLCF" and item.get("metric") == "shares_out"), None)
    _assert(row and row.get("approved") is True and row.get("source", {}).get("id") == DOCUMENT_ID, "MLCF share-count approval is not bound to psx:260032")
    tie = row.get("tie_out") or {}
    _assert(tie.get("status") == "tied_out", "MLCF share-count tie-out is not tied_out")
    _assert(abs(int(tie.get("nominal_pkr")) - int(tie.get("reported_paid_up_pkr"))) <= int(tie.get("rounding_tolerance_pkr")), "MLCF share-count capital-note arithmetic does not tie out")


def _check_downstream_block() -> None:
    truth = _load(CI / "financial_truth_qualification.json")["companies"]["MLCF"]
    _assert(truth.get("status") == "not_qualified", "MLCF must remain below the full financial-truth gate")
    _assert(truth["model_ready_financial_statement_coverage"]["reported_quarter"]["required"] == 8, "quarter gate must remain eight periods")
    _assert(truth["model_ready_financial_statement_coverage"]["reported_quarter"]["present"] == 0, "unqualified quarters must not activate formal outputs")
    _assert(truth.get("downstream") == {key: "blocked_financial_truth_not_qualified" for key in ("forecast", "valuation", "market_expectations")}, "truth downstream gate is not fail-closed")
    for name in ("financial_forecasts.json", "formal_valuations.json", "market_expectations.json"):
        row = _load(CI / name)["companies"]["MLCF"]
        _assert(row.get("status") == "blocked_financial_truth_not_qualified" and row.get("truth_status") == "not_qualified", f"{name}: formal output is not blocked")
        _assert(row.get("result") is None and row.get("provenance") == [], f"{name}: blocked output contains a result or provenance")


def main() -> None:
    _check_annual_schedule()
    _check_source_and_share_tie_out()
    _check_identity_surface()
    _check_downstream_block()
    print("mlcf canonical promotion acceptance: PASS (FY2024/FY2025 exact schedules; zero conflicts; 73 event/study identities preserved; share tie-out valid; formal outputs blocked at 2/5 annual and 0/8 quarters)")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"mlcf canonical promotion acceptance: FAIL - {exc}")
        raise SystemExit(1)
