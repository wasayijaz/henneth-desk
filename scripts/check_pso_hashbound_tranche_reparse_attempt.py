"""Regression checks for the PSO hash-bound tranche reparse attempt."""
from __future__ import annotations

import json
from pathlib import Path

import build_pso_hashbound_tranche_reparse_attempt as builder


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "company_intel" / "pso_hashbound_tranche_reparse_attempt.json"
EXPECTED_DOCS = {"psx:257951", "psx:263690", "psx:270316", "psx:275672"}


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> None:
    receipt = builder.build(write=True)
    again = builder.build(write=False)
    if json.dumps(receipt, sort_keys=True) != json.dumps(again, sort_keys=True):
        fail("builder is not deterministic")
    if not OUT.exists():
        fail("receipt was not written")
    if receipt.get("ticker") != "PSO":
        fail("receipt must be PSO-scoped")
    if set(receipt.get("tranche_document_ids") or []) != EXPECTED_DOCS:
        fail("tranche document set changed")
    if receipt.get("status") not in {"blocked_zero_delta", "parsed_zero_delta", "fresh_fact_review_required"}:
        fail("current retained tranche must remain fail-closed")

    parser = receipt.get("parser") or {}
    if parser.get("parser_version") != builder.PARSER_VERSION or parser.get("parser_revision") != builder.PARSER_REVISION:
        fail("parser identity drifted")
    if parser.get("no_fetch") is not True:
        fail("parser attempt must not fetch")

    before = receipt.get("coverage_before") or {}
    after = receipt.get("coverage_after") or {}
    if before != after:
        fail("coverage must remain unchanged")
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

    summary = receipt.get("attempt_summary") or {}
    expected_zero_keys = (
        "fresh_share_capital_candidate_count",
        "delta_series_fact_count",
        "delta_financial_truth_coverage_count",
        "eligible_reconciliation_fact_count",
    )
    if summary.get("document_count") != 4:
        fail("all four tranche documents must be represented")
    if receipt.get("status") in {"parsed_zero_delta", "fresh_fact_review_required"}:
        if summary.get("parser_invoked_document_count") != 4 or summary.get("blocked_document_count") != 0:
            fail("parsed zero-delta state must parse all four documents without blockers")
    elif summary.get("blocked_document_count") != 4 or summary.get("parser_invoked_document_count") != 0:
        fail("blocked zero-delta state must explicitly block all four documents")
    for key in expected_zero_keys:
        if summary.get(key) != 0:
            fail(f"{key}: expected zero")
    if receipt.get("status") == "fresh_fact_review_required":
        if summary.get("fresh_parser_fact_count", 0) <= 0 or summary.get("fresh_model_loadable_fact_count", 0) <= 0:
            fail("fresh-fact review state must contain parser output")
        review = receipt.get("review_candidate") or {}
        if review.get("status") != "owner_approval_required":
            fail("fresh-fact review must require explicit owner approval")
        if review.get("candidate_document_id") != "psx:275672":
            fail("review candidate must be bound to psx:275672")
        if review.get("candidate_fact_count") != summary.get("fresh_model_loadable_fact_count"):
            fail("review candidate count must match fresh model-loadable count")
        source = review.get("source") or {}
        if source.get("name") != "PSX DPS" or source.get("page") != [6]:
            fail("review source must remain bound to PSX page 6")
        if source.get("consolidation") != ["consolidated"] or source.get("currency") != ["PKR"]:
            fail("review source must remain consolidated PKR")
        if source.get("unit_multiplier") != [1, 1000]:
            fail("review source must preserve PKR and PKR/share scales")
        if source.get("unit_scale_by_unit") != {"PKR": [1000], "PKR/share": [1]}:
            fail("review source unit scaling must distinguish PKR from PKR/share")
        periods = review.get("period_mapping") or {}
        direct = periods.get("current_direct_quarter") or {}
        if direct.get("period_end") != "2026-03-31" or direct.get("duration_months") != 3:
            fail("current direct-quarter period mapping drifted")
        required_metrics = {"basic_eps", "profit_after_tax_attributable", "revenue"}
        if not required_metrics.issubset(set(direct.get("metrics") or [])):
            fail("current direct-quarter metric set is incomplete or changed")
        if direct.get("complete_direct_quarter_triplet") is not True:
            fail("current direct-quarter triplet must be complete in review")
        cumulative = periods.get("current_cumulative") or {}
        if cumulative.get("period_end") != "2026-03-31" or cumulative.get("duration_months") != 9:
            fail("current cumulative period mapping drifted")
        if not required_metrics.issubset(set(cumulative.get("metrics") or [])):
            fail("current cumulative metric set is incomplete or changed")
        if cumulative.get("complete_cumulative_income_triplet") is not True:
            fail("current cumulative income triplet must be complete in review")
        comparative = periods.get("comparative_direct_quarter") or {}
        if comparative.get("period_end") != "2025-03-31" or comparative.get("comparative_to_period_end") != "2026-03-31":
            fail("comparative direct-quarter mapping drifted")
        if not required_metrics.issubset(set(comparative.get("metrics") or [])):
            fail("comparative direct-quarter metric set is incomplete or changed")
        if review.get("canonical_source_conflict_count") != 0:
            fail("review must expose any canonical source conflicts")
        if review.get("conflict_status") != "no_canonical_conflicts_in_current_state":
            fail("unexpected canonical conflict status")
        if review.get("duplicate_status") != "no_duplicate_eligible_facts_written":
            fail("review must prove no eligible facts were written")
        if review.get("promotion_status") != "not_promoted":
            fail("review candidate must remain unpromoted")
        boundary = review.get("authoritative_delta") or {}
        if boundary.get("series_fact_count") != 0 or boundary.get("financial_truth_coverage_count") != 0:
            fail("review candidate must have zero canonical delta")
    elif summary.get("fresh_parser_fact_count") != 0 or summary.get("fresh_model_loadable_fact_count") != 0:
        fail("zero-delta state must not contain fresh parser facts")
    if summary.get("existing_audit_only_reconciliation_fact_count") != 4:
        fail("existing PSO audit-only reconciliation count must remain visible and unpromoted")

    docs = receipt.get("documents") or []
    if {doc.get("document_id") for doc in docs} != EXPECTED_DOCS:
        fail("receipt document rows do not match expected tranche")
    for doc in docs:
        doc_id = doc.get("document_id")
        if doc.get("company_documents_present") is not True:
            fail(f"{doc_id}: missing company_documents record")
        if doc.get("hash_bound") is not True:
            fail(f"{doc_id}: must be retained hash-bound before this tranche is eligible")
        if receipt.get("status") in {"parsed_zero_delta", "fresh_fact_review_required"}:
            if doc.get("attempt_status") != "parsed_exact_retained_bytes":
                fail(f"{doc_id}: expected exact retained bytes to be parsed")
            if doc.get("parser_invoked") is not True:
                fail(f"{doc_id}: parser invocation must be recorded")
        elif doc.get("attempt_status") != "blocked_exact_retained_bytes_absent":
            fail(f"{doc_id}: expected exact-bytes blocker")
        if receipt.get("status") != "fresh_fact_review_required":
            for key in ("fresh_parser_fact_count", "fresh_model_loadable_fact_count", "fresh_share_capital_candidate_count", "delta_series_fact_count", "delta_financial_truth_coverage_count"):
                if doc.get(key) != 0:
                    fail(f"{doc_id}: {key} must be zero")
            if doc.get("fresh_fact_ids") or doc.get("fresh_share_capital_fact_ids"):
                fail(f"{doc_id}: no fresh fact IDs may be emitted in a zero-delta state")
        else:
            if doc.get("attempt_status") != "parsed_exact_retained_bytes" or doc.get("parser_invoked") is not True:
                fail(f"{doc_id}: fresh review state must record exact-byte parsing")
            rows = doc.get("qualified_fact_rows_not_persisted") or []
            if len(rows) != doc.get("fresh_model_loadable_fact_count"):
                fail(f"{doc_id}: qualified fact inventory count mismatch")
            for row in rows:
                if row.get("readiness") != "model_loadable" or row.get("consolidation") != "consolidated":
                    fail(f"{doc_id}: fresh review facts must be consolidated/model-loadable")
                if row.get("document_id") != doc_id or row.get("content_sha256") != doc.get("content_sha256"):
                    fail(f"{doc_id}: fresh fact provenance mismatch")

    policy = receipt.get("policy") or {}
    required_policy = (
        "fail_closed",
        "no_fetch",
        "no_provider_change",
        "no_financial_series_write",
        "no_financial_truth_write",
        "no_relabel_legacy_audit_rows",
        "audit_only_values_not_promoted",
        "no_forecast",
        "no_valuation",
        "no_market_expectations",
    )
    for key in required_policy:
        if policy.get(key) is not True:
            fail(f"policy {key} must be true")
    print("pso_hashbound_tranche_reparse_attempt: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"pso_hashbound_tranche_reparse_attempt: FAIL - {error}")
        raise SystemExit(1)
