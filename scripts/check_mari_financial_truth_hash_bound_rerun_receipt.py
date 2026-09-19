"""Focused checks for MARI's hash-bound parser rerun receipt."""
from __future__ import annotations

import json
from pathlib import Path

import build_mari_financial_truth_hash_bound_rerun_receipt as builder


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "company_intel" / "mari_financial_truth_hash_bound_rerun_receipt.json"
EXPECTED_COVERAGE = {
    "annual_income_triplets": (5, 0),
    "reported_quarter_fact_sets": (8, 0),
    "annual_operating_cash_flow": (5, 0),
    "annual_full_statement_schedules": (5, 0),
    "reported_quarter_full_statement_schedules": (8, 0),
    "official_share_count_capital_note_tie_out": (1, 0),
}


def fail(message: str) -> None:
    raise AssertionError(message)


def _document_ids(rows: list[dict]) -> set[str]:
    return {str(row.get("document_id")) for row in rows}


def main() -> None:
    receipt = builder.build(write=True)
    if json.dumps(receipt, sort_keys=True) != json.dumps(builder.build(write=False), sort_keys=True):
        fail("receipt builder is not deterministic")
    if not OUT.exists():
        fail("receipt was not written")
    if receipt.get("ticker") != "MARI":
        fail("receipt must be scoped to MARI")
    if receipt.get("receipt_version") != builder.RECEIPT_VERSION:
        fail("unexpected receipt version")
    if receipt.get("status") != "zero_delta_parser_rerun_blocked_missing_retained_bytes_or_geometry":
        fail("current retained tranche must remain a zero-delta parser rerun")

    parser = receipt.get("parser") or {}
    if parser.get("version") != "financial_statement_v2" or parser.get("revision") != "block_geometry_v6":
        fail("receipt must be bound to the approved v6 statement parser")
    policy = receipt.get("policy") or {}
    if policy.get("no_fetch") is not True or policy.get("no_audit_only_relabel") is not True:
        fail("receipt policy must prohibit fetches and audit-only relabels")
    if policy.get("no_canonical_fact_write") is not True:
        fail("receipt must not write canonical facts")

    before = receipt.get("coverage_before") or {}
    after = receipt.get("coverage_after") or {}
    if before != after:
        fail("coverage must remain unchanged after a zero-delta rerun")
    for key, (required, present) in EXPECTED_COVERAGE.items():
        node = before.get(key) or {}
        if node.get("required") != required or node.get("present") != present:
            fail(f"{key}: expected {present}/{required}, got {node.get('present')}/{node.get('required')}")

    delta = receipt.get("state_delta") or {}
    if delta.get("financial_truth_state_changed") is not False:
        fail("financial truth state must not change")
    if delta.get("company_financial_series_changed") is not False:
        fail("company financial series must not change")
    if delta.get("canonical_facts_written") != 0 or delta.get("audit_only_relabels") != 0:
        fail("canonical fact writes and relabels must both be zero")
    if delta.get("fact_level_outputs_emitted_to_receipt") != 0:
        fail("no v6 facts may be emitted without exact retained PDF bytes and geometry")

    source = receipt.get("source_receipt") or {}
    source_docs = source.get("hash_bound_statement_restage_wave") or {}
    if source_docs != builder.TARGET_DOCUMENTS:
        fail("source next-intake receipt tranche/hash binding drifted")

    documents = receipt.get("documents") or []
    if _document_ids(documents) != set(builder.TARGET_DOCUMENTS):
        fail("target document set changed")
    for row in documents:
        doc_id = row.get("document_id")
        if row.get("hash_bound") is not True:
            fail(f"{doc_id}: retained document is not hash-bound")
        if row.get("content_sha256") != builder.TARGET_DOCUMENTS[doc_id]:
            fail(f"{doc_id}: content hash drift")
        if row.get("document_status") != "ready":
            fail(f"{doc_id}: document is not retained ready")
        byte_check = row.get("retained_byte_check") or {}
        if byte_check.get("exact_local_pdf_bytes_present") is not False:
            fail(f"{doc_id}: checker expected no exact local PDF bytes in this retained state")
        geometry = row.get("retained_geometry_check") or {}
        if geometry.get("has_any_persisted_geometry_or_full_pages") is not False:
            fail(f"{doc_id}: checker expected no persisted page geometry")
        if row.get("parser_run_attempted") is not False:
            fail(f"{doc_id}: parser run must not be attempted without bytes")
        if row.get("parser_blocker") != "exact_retained_pdf_bytes_missing_and_no_persisted_text_geometry":
            fail(f"{doc_id}: unexpected parser blocker")
        if row.get("facts_emitted") != 0 or row.get("fact_level_output") != []:
            fail(f"{doc_id}: zero-delta document emitted facts")
        if row.get("canonical_facts_written") != 0 or row.get("audit_only_relabels") != 0:
            fail(f"{doc_id}: document-level writes/relabels must be zero")

    inventory = receipt.get("retained_series_inventory_before") or {}
    if inventory.get("fact_count") != 29 or inventory.get("model_loadable_count") != 0:
        fail("retained tranche inventory must remain 29 facts / 0 model-loadable")
    for doc_id, expected_count in {"psx:275583": 8, "psx:271327": 11, "psx:264550": 10}.items():
        node = (inventory.get("by_document") or {}).get(doc_id) or {}
        if node.get("fact_count") != expected_count or node.get("model_loadable_count") != 0:
            fail(f"{doc_id}: retained series inventory changed")

    print("mari_financial_truth_hash_bound_rerun_receipt: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"mari_financial_truth_hash_bound_rerun_receipt: FAIL - {error}")
        raise SystemExit(1)
