#!/usr/bin/env python3
"""Focused financial-series eligibility checks for retained MLCF FY25 facts."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf

from financial_evidence_reconciliation import (
    ANNUAL_BALANCE_SCOPE,
    ANNUAL_CASHFLOW_SCOPE,
    ANNUAL_INCOME_SCOPE,
    eligibility_scope,
    fact_status,
)
from financial_series import (
    _STRUCTURED_BALANCE_SHEET_LINES,
    _STRUCTURED_CASH_FLOW_LINES,
    _STRUCTURED_STATEMENT_TYPES,
    normalize_fact,
)
from financial_statement_facts import (
    MLCF_FY25_CONTENT_SHA256,
    MLCF_FY25_DOCUMENT_ID,
    extract_facts,
)


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / ".cache" / "company_intel" / "raw" / "manual" / "260032.pdf"
SOURCE_URL = "https://dps.psx.com.pk/download/document/260032.pdf"
PAGES = (291, 292, 293, 295, 361)

EXPECTED_BALANCE_LINES = {
    "cash_and_cash_equivalents", "trade_receivables", "inventories",
    "total_current_assets", "property_plant_equipment", "total_assets",
    "short_term_borrowings", "long_term_borrowings", "trade_payables", "total_equity",
}
EXPECTED_CASH_FLOW_LINES = {
    "operating_cash_flow", "capital_expenditure", "depreciation_amortization",
    "net_cash_from_investing_activities", "net_cash_from_financing_activities",
    "dividends_paid",
}
EXPECTED_MLCF_LINES = {
    **{line: 2 for line in EXPECTED_BALANCE_LINES},
    "revenue": 2,
    "gross_profit": 2,
    "operating_profit": 2,
    "finance_cost": 2,
    "profit_before_tax": 2,
    "tax_expense": 2,
    "profit_after_tax_attributable": 2,
    "basic_eps": 2,
    "operating_cash_flow": 2,
    "capital_expenditure": 2,
    "net_cash_from_investing_activities": 2,
    "net_cash_from_financing_activities": 2,
    "dividends_paid": 2,
}


def _check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def _doc() -> dict[str, Any]:
    return {
        "doc_id": MLCF_FY25_DOCUMENT_ID,
        "title": "MLCF Transmission of Annual Financial Statements for the Year Ended 30.06.2025",
        "source_url": SOURCE_URL,
        "content_sha256": MLCF_FY25_CONTENT_SHA256,
        "period": "2025-06-30",
        "period_end": "2025-06-30",
        "period_type": "annual",
        "available_on": "2025-09-25",
        "published_at": "2025-09-25T00:00:00+05:00",
        "retrieved_at": "2026-08-31T11:27:26Z",
        "tickers": ["MLCF"],
        "status": "ready",
        "media_type": "application/pdf",
        "page_count": 401,
    }


def _records() -> list[dict[str, Any]]:
    _check("retained_pdf_exists", PDF.exists(), str(PDF))
    records: list[dict[str, Any]] = []
    with pymupdf.open(PDF) as pdf:
        for page_no in PAGES:
            page = pdf[page_no - 1]
            records.append({
                "page": page_no,
                "text": page.get_text("text"),
                "words": page.get_text("words"),
            })
    return records


def _extracted() -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    doc = _doc()
    records = _records()
    pages = [str(record["text"]) for record in records]
    words = [list(record["words"]) for record in records]
    facts = extract_facts(doc, pages, words=words, page_records=records)
    return doc, pages, facts


def _normalized(doc: dict[str, Any], pages: list[str], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [normalize_fact(doc, fact, pages=pages, source_registry={}) for fact in facts]
    _check("all_facts_normalized", all(row is not None for row in rows), str(rows))
    return [row for row in rows if row is not None]


def _assert_allowlists_are_exact() -> None:
    _check("balance_allowlist", set(_STRUCTURED_BALANCE_SHEET_LINES) == EXPECTED_BALANCE_LINES,
           str(sorted(_STRUCTURED_BALANCE_SHEET_LINES)))
    _check("cash_flow_allowlist", set(_STRUCTURED_CASH_FLOW_LINES) == EXPECTED_CASH_FLOW_LINES,
           str(sorted(_STRUCTURED_CASH_FLOW_LINES)))
    for line in EXPECTED_BALANCE_LINES:
        _check("balance_statement_type", _STRUCTURED_STATEMENT_TYPES.get(line) == "balance_sheet", line)
    for line in EXPECTED_CASH_FLOW_LINES:
        _check("cash_flow_statement_type", _STRUCTURED_STATEMENT_TYPES.get(line) == "cash_flow_statement", line)


def _assert_mlcf_facts_classify() -> list[dict[str, Any]]:
    doc, pages, facts = _extracted()
    rows = _normalized(doc, pages, facts)
    _check("parsed_fact_count", len(facts) == 46, str(len(facts)))
    _check("normalized_row_count", len(rows) == 46, str(len(rows)))
    _check("parser_model_loadable", Counter(fact.get("readiness") for fact in facts) == {"model_loadable": 46},
           str(Counter(fact.get("readiness") for fact in facts)))
    _check("fact_lines", Counter(fact.get("line") for fact in facts) == EXPECTED_MLCF_LINES,
           str(Counter(fact.get("line") for fact in facts)))
    _check("series_model_loadable", Counter(row.get("readiness") for row in rows) == {"model_loadable": 46},
           str(Counter(row.get("readiness") for row in rows)))
    _check("series_clean_flags", all(not row.get("quality_flags") for row in rows),
           str([row.get("quality_flags") for row in rows if row.get("quality_flags")]))
    _check("eligible_statuses", Counter(fact_status(row) for row in rows) == {"eligible": 46},
           str(Counter(fact_status(row) for row in rows)))
    _check("eligibility_scopes", Counter(eligibility_scope(row) for row in rows) == {
        ANNUAL_BALANCE_SCOPE: 20,
        ANNUAL_INCOME_SCOPE: 16,
        ANNUAL_CASHFLOW_SCOPE: 10,
    }, str(Counter(eligibility_scope(row) for row in rows)))
    return rows


def _assert_row_is_audit_only(name: str, doc: dict[str, Any], pages: list[str],
                              fact: dict[str, Any], expected_flag: str) -> None:
    row = normalize_fact(doc, fact, pages=pages, source_registry={})
    _check(f"{name}_normalized", row is not None, "")
    assert row is not None
    flags = set(row.get("quality_flags") or [])
    _check(f"{name}_flag", expected_flag in flags, str(sorted(flags)))
    _check(f"{name}_readiness", row.get("readiness") == "audit_only", str(row.get("readiness")))
    _check(f"{name}_status", fact_status(row) == "audit_only", fact_status(row))


def _assert_adversarial_rows_stay_audit_only() -> None:
    doc, pages, facts = _extracted()
    balance_fact = next(fact for fact in facts if fact.get("line") == "total_assets")
    cash_flow_fact = next(fact for fact in facts if fact.get("line") == "net_cash_from_investing_activities")

    unsupported = copy.deepcopy(balance_fact)
    unsupported["line"] = "management_commentary"
    unsupported["fact_type"] = "management_commentary"
    _assert_row_is_audit_only("unsupported_line", doc, pages, unsupported, "unsupported_structured_line")

    wrong_statement = copy.deepcopy(cash_flow_fact)
    wrong_statement["statement_type"] = "balance_sheet"
    _assert_row_is_audit_only("wrong_statement_type", doc, pages, wrong_statement,
                              "invalid_structured_statement_type")

    mismatched_line = copy.deepcopy(balance_fact)
    mismatched_line["fact_type"] = "revenue"
    _assert_row_is_audit_only("line_fact_type_mismatch", doc, pages, mismatched_line,
                              "line_fact_type_mismatch")


def main() -> None:
    _assert_allowlists_are_exact()
    _assert_mlcf_facts_classify()
    _assert_adversarial_rows_stay_audit_only()
    print("MLCF FY25 financial-series eligibility check: ok")


if __name__ == "__main__":
    main()
