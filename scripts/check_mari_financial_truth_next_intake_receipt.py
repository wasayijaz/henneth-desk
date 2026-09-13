"""Focused checks for MARI's fail-closed financial-truth next-intake receipt."""
from __future__ import annotations

import json
from pathlib import Path

import build_mari_financial_truth_next_intake_receipt as builder


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "company_intel" / "mari_financial_truth_next_intake_receipt.json"


def fail(message: str) -> None:
    raise AssertionError(message)


def _ids(rows: list[dict]) -> set[str]:
    return {row.get("document_id") for row in rows}


def main() -> None:
    receipt = builder.build(write=True)
    if json.dumps(receipt, sort_keys=True) != json.dumps(builder.build(write=False), sort_keys=True):
        fail("receipt builder is not deterministic")
    if not OUT.exists():
        fail("receipt was not written")
    if receipt.get("ticker") != "MARI":
        fail("receipt must be scoped to MARI")
    if receipt.get("status") != "next_intake_required_no_parser_correction":
        fail("receipt must remain a next-intake gap, not a financial-truth correction")

    decision = receipt.get("decision") or {}
    if decision.get("parser_correction_eligible") is not False:
        fail("parser correction must be explicitly rejected for current MARI evidence")
    if decision.get("financial_truth_state_changed") is not False:
        fail("receipt must not claim a financial-truth state change")

    before = receipt.get("coverage_before") or {}
    after = receipt.get("coverage_after") or {}
    if before != after:
        fail("coverage must be unchanged before/after this fail-closed receipt")
    expectations = {
        "annual_income_triplets": (5, 0),
        "reported_quarter_fact_sets": (8, 0),
        "annual_operating_cash_flow": (5, 0),
        "annual_full_statement_schedules": (5, 0),
        "reported_quarter_full_statement_schedules": (8, 0),
        "official_share_count_capital_note_tie_out": (1, 0),
    }
    for key, (required, present) in expectations.items():
        node = before.get(key) or {}
        if node.get("required") != required or node.get("present") != present:
            fail(f"{key}: expected {present}/{required}, got {node.get('present')}/{node.get('required')}")

    facts = receipt.get("fact_inventory") or {}
    if facts.get("series_fact_count") != 60 or facts.get("series_audit_only_fact_count") != 60:
        fail("MARI must retain exactly sixty audit-only financial series facts in the current inventory")
    if facts.get("reconciliation_eligible_fact_count") != 0:
        fail("MARI must not have eligible reconciliation facts")
    if facts.get("financial_statement_v2_candidate_count") != 0:
        fail("MARI v2 candidate queue must remain empty")
    share = facts.get("share_capital") or {}
    if share.get("approved_tie_out_count") != 0 or share.get("candidate_count") != 0:
        fail("MARI must not have a retained approved or candidate share-capital tie-out")

    docs = receipt.get("retained_official_candidate_documents") or {}
    hash_bound = docs.get("hash_bound_statement_restage_wave") or []
    metadata = docs.get("metadata_only_financial_restage_wave") or []
    if _ids(hash_bound) != {"psx:275583", "psx:271327", "psx:264550"}:
        fail("hash-bound statement target set changed")
    if not all(row.get("hash_bound") and row.get("company_documents_present") for row in hash_bound):
        fail("hash-bound statement targets must be retained in company_documents")
    if _ids(metadata) != {
        "psx:280901",
        "psx:274864",
        "psx:269182",
        "psx:bd312748aa6ef5cd050cfc1a",
        "psx:258895",
        "psx:257577",
    }:
        fail("metadata-only target set changed")
    if any(row.get("hash_bound") for row in metadata):
        fail("metadata-only targets must not be treated as hash-bound")

    slots = {slot.get("slot"): slot for slot in receipt.get("missing_slots") or []}
    sector = slots.get("sector_kpi_schedule") or {}
    if sector.get("present") != 0 or sector.get("status") != "observed_only":
        fail("MARI E&P sector KPI schedule must remain observed-only and unactivated")

    policy = receipt.get("policy") or {}
    if policy.get("fail_closed") is not True or policy.get("audit_only_values_not_promoted") is not True:
        fail("receipt policy must fail closed and refuse audit-only promotion")
    print("mari_financial_truth_next_intake_receipt: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"mari_financial_truth_next_intake_receipt: FAIL - {error}")
        raise SystemExit(1)
