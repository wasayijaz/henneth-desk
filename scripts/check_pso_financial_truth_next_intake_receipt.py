"""Focused checks for PSO's fail-closed financial-truth next-intake receipt."""
from __future__ import annotations

import json
from pathlib import Path

import build_pso_financial_truth_next_intake_receipt as builder


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "company_intel" / "pso_financial_truth_next_intake_receipt.json"


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
    if receipt.get("status") != "next_intake_required_no_parser_correction":
        fail("receipt must remain a next-intake gap, not a financial-truth correction")
    decision = receipt.get("decision") or {}
    if decision.get("parser_correction_eligible") is not False:
        fail("parser correction must be explicitly rejected for current PSO evidence")
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
    if facts.get("series_audit_only_fact_count") != 4:
        fail("PSO must retain exactly four audit-only series facts in the current inventory")
    if facts.get("reconciliation_eligible_fact_count") != 0:
        fail("PSO must not have eligible reconciliation facts")
    if facts.get("financial_statement_v2_candidate_count") != 0:
        fail("PSO v2 candidate queue must remain empty")
    share = facts.get("share_capital") or {}
    if share.get("approved_tie_out_count") != 0 or share.get("candidate_count") != 0:
        fail("PSO must not have a retained approved or candidate share-capital tie-out")

    docs = receipt.get("retained_official_candidate_documents") or {}
    primary = docs.get("primary_hash_bound_fact_qualification_wave") or []
    restage = docs.get("metadata_only_restage_wave") or []
    if _ids(primary) != {"psx:257951", "psx:263690", "psx:270316", "psx:275672"}:
        fail("primary hash-bound target set changed")
    if _ids(restage) != {"psx:260771", "psx:264179", "psx:276065"}:
        fail("metadata-only restage target set changed")
    if not all(row.get("hash_bound") for row in primary):
        fail("primary targets must be retained hash-bound documents")
    if any(row.get("hash_bound") for row in restage):
        fail("metadata-only restage targets must not be treated as hash-bound")
    for row in primary + restage:
        if not (row.get("company_documents_present") or row.get("source_registry_or_research_index_present")):
            fail(f"{row.get('document_id')}: candidate ID must resolve to retained official metadata")
    for row in restage:
        if row.get("source_registry_or_research_index_present") is not True or not row.get("url") or not row.get("published_at"):
            fail(f"{row.get('document_id')}: metadata-only restage target must retain official URL and publication timestamp")

    policy = receipt.get("policy") or {}
    if policy.get("fail_closed") is not True or policy.get("audit_only_values_not_promoted") is not True:
        fail("receipt policy must fail closed and refuse audit-only promotion")
    if policy.get("do_not_touch_sales_expansion_receipt") is not True:
        fail("receipt must preserve the sales-expansion artifact boundary")
    print("pso_financial_truth_next_intake_receipt: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"pso_financial_truth_next_intake_receipt: FAIL - {error}")
        raise SystemExit(1)
