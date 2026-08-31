"""Deterministic retained-state checks for MARI E&P evidence preconditions.

This is a read-only CI check.  It deliberately keeps lifecycle and financial
qualification separate from the E&P event contract: a synthetic future filing
may satisfy event-evidence preconditions without promoting the live case or
unlocking formal finance products.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import enp_event_contract


PASS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASS += 1


def load(relative: str) -> Any:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def originators(rows: list[Mapping[str, Any]]) -> set[str]:
    """Return source-originator identities; distributor copies do not count."""
    return {str(row.get("source", "")).strip().lower() for row in rows if row.get("source")}


def exact_receipt(row: Mapping[str, Any]) -> bool:
    required = ("document_id", "source", "source_url", "page", "content_sha256", "evidence_sha256")
    return (
        all(row.get(key) for key in required)
        and isinstance(row.get("page"), int)
        and len(str(row["content_sha256"])) == 64
        and len(str(row["evidence_sha256"])) == 64
    )


def mechanism_receipt(row: Mapping[str, Any]) -> bool:
    """Retained event lineage may omit an evidence hash on older rows."""
    required = ("document_id", "source", "source_url", "page", "content_sha256")
    return all(row.get(key) for key in required) and isinstance(row.get("page"), int) and len(str(row["content_sha256"])) == 64


def source_record(value: Any, field: str, document_id: str, source: str, available_on: str) -> dict[str, Any]:
    return {
        "value": value,
        "label_type": "source",
        "source_ref": {
            "id": document_id,
            "label": f"{source} numeric E&P filing ({field})",
            "url": f"https://example.invalid/{document_id}.pdf",
        },
        "available_on": available_on,
    }


def future_numeric_fixture() -> dict[str, Any]:
    """A complete, independent-source event fixture; not live state."""
    fields: dict[str, Any] = {
        "working_interest_pct": 65.0,
        "consideration_pkr": 1.0e9,
        "consideration_non_recoverable": True,
        "consideration_quarter_end": "2026-06-30",
        "spend_schedule": [
            {"quarter_end": "2026-06-30", "phase": "exploration", "amount_pkr": 2.0e8},
            {"quarter_end": "2026-09-30", "phase": "appraisal", "amount_pkr": 3.0e8},
        ],
        "first_production_quarter_end": "2027-06-30",
        "production_horizon_quarters": 4,
        "initial_production_boe_pd": 1000.0,
        "quarterly_decline_pct": 5.0,
        "oil_share_pct": 60.0,
        "oil_price_usd_bbl": 70.0,
        "gas_price_usd_mmbtu": 4.0,
        "gas_mmbtu_per_boe": 5.8,
        "fx_pkr_usd": 280.0,
        "opex_usd_boe": 12.0,
        "royalty_pct": 10.0,
        "effective_tax_pct": 30.0,
        "discount_rate_pct_annual": 12.0,
        "geological_success_pct": 25.0,
        "commercial_success_pct": 60.0,
        "shares_out": 1_200_000_000.0,
        "operator_status": "operator",
    }
    return {
        "symbol": "MARI",
        "event_ref": "evt_future_independent_peshawar_v1",
        "case_label": "base",
        "effective_date": "2026-03-31",
        "valuation_date": "2026-04-30",
        "inputs": {
            key: source_record(value, key, "partner:future-peshawar-001", "Hycarbex-American Energy Inc.", "2026-04-01")
            for key, value in fields.items()
        },
    }


def main() -> None:
    cases = load("state/company_intel/intelligence_cases.json")
    mari_cases = cases["companies"]["MARI"]["cases"]
    active = next(row for row in mari_cases if row["case_id"] == "case_mari_working_interest_observed_v1")
    check("active MARI case remains Observed", active["status"] == "Observed")
    check("active case cannot claim corroboration", "not independent-originator corroboration" in active["promotion_blocks"]["Corroborated"])

    retained = [row for row in active["source_lineage"] if row["document_id"] in {"psx:260446", "psx:271327"}]
    check("retained mechanism receipts are hash/page bound", len(retained) == 2 and all(mechanism_receipt(row) for row in retained))
    check("retained mechanism is same-origin", originators(retained) == {"psx dps"})
    check("later same-origin filing does not add corroboration", originators(retained + [{"source": "PSX DPS", "document_id": "psx:280901"}]) == {"psx dps"})

    readiness = load("state/company_intel/mari_enp_evidence_readiness.json")
    check("live E&P operands are blocked", readiness["ep_operands"]["status"] == "blocked_missing_numeric_operands")
    check("live activation remains blocked", readiness["activation"]["status"] == "blocked" and not readiness["activation"]["kernel_activated"])
    unavailable = {row["operand"] for row in readiness["ep_operands"]["items"] if row["status"] == "unavailable"}
    check("numeric E&P operands are explicitly missing", {"working_interest_pct", "consideration_pkr", "reserves"}.issubset(unavailable))

    fixture = future_numeric_fixture()
    check("independent numeric fixture has complete provenance", enp_event_contract.validate_case(fixture) == [])
    fixture_evidence = [
        {"document_id": "psx:260446", "source": "PSX DPS", "source_url": "https://dps.psx.com.pk/download/document/260446.pdf", "page": 1, "content_sha256": "a" * 64, "evidence_sha256": "b" * 64},
        {"document_id": "partner:future-peshawar-001", "source": "Hycarbex-American Energy Inc.", "source_url": "https://example.invalid/partner-future-peshawar-001.pdf", "page": 2, "content_sha256": "c" * 64, "evidence_sha256": "d" * 64},
    ]
    check("independent fixture receipts are exact", all(exact_receipt(row) for row in fixture_evidence))
    check("independent fixture reaches two originators", len(originators(fixture_evidence)) >= 2)
    check("financial gates remain separate", readiness["financial_history"]["annual"]["status"] == "blocked" and readiness["financial_history"]["quarterly"]["status"] == "blocked")
    print(f"mari enp evidence preconditions: PASS ({PASS} checks)")


if __name__ == "__main__":
    main()
