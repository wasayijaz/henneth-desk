"""Validate the audit-only receipt for the retained MLCF FY24 comparative source."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mlcf_fy24_full_schedule_audit as audit
from mlcf_derived_dna import DERIVED_LINEAGE_VERSION, DerivedDnaError, NOTE_PAGE, SOURCE_PAGE_SCOPE, extract_operands, read_note_page, validate_derived_receipt
from ci_checker_helpers import without_root_meta
from psx_data import load_json

EXPECTED_REVENUE = 66452348000.0
EXPECTED_PAT = 6891064000.0
EXPECTED_EPS = 6.51
EXPECTED_OCF = 12781233000.0
EXPECTED_CAPEX = -5453903000.0
EXPECTED_EQUITY = 57643643000.0
EXPECTED_ASSETS = 100343986000.0

def _fail(message: str) -> None:
    raise AssertionError(message)

def main() -> None:
    if not audit.OUT.exists():
        _fail("mlcf_fy24_full_schedule_audit.json is missing")
    saved = load_json(audit.OUT, {})
    rebuilt = audit.build()
    if json.dumps(without_root_meta(saved), sort_keys=True) != json.dumps(without_root_meta(rebuilt), sort_keys=True):
        _fail("rebuilt receipt is not deterministic with saved artifact")

    if saved.get("schema_version") != 2 or saved.get("receipt_version") != "mlcf_fy24_full_schedule_audit_v2":
        _fail("schema or receipt version mismatch")
    if saved.get("derived_lineage_version") != DERIVED_LINEAGE_VERSION:
        _fail("derived lineage version mismatch")
    if saved.get("symbol") != "MLCF" or saved.get("document_id") != "psx:260032":
        _fail("symbol or document_id mismatch")

    src = saved.get("source") or {}
    if src.get("expected_content_sha256") != audit.EXPECTED_HASH:
        _fail("content hash mismatch")
    if src.get("published_at") != "2025-09-25T12:43:00+05:00":
        _fail("published_at mismatch")
    if src.get("available_on") != "2025-09-25":
        _fail("available_on mismatch")
    if src.get("page_scope") != list(SOURCE_PAGE_SCOPE) or src.get("statement_page_scope") != [291, 292, 293, 295] or src.get("derived_page_scope") != [NOTE_PAGE]:
        _fail("page scope mismatch")

    period = saved.get("period") or {}
    if period.get("period_end") != "2024-06-30" or period.get("duration_months") != 12:
        _fail("period_end must be 2024-06-30 for 12 months")

    qual = saved.get("qualification") or {}
    if qual.get("promotion_eligible") is not False or qual.get("promotion_status") != "quarantined_audit_only":
        _fail("audit receipt must be quarantined_audit_only and not promotion eligible")

    candidates = saved.get("candidates") or []
    if len(candidates) != 23:
        _fail(f"expected exactly 23 full-schedule candidate lines, got {len(candidates)}")

    facts_by_line = {f.get("canonical_line"): f for f in candidates}
    if facts_by_line.get("revenue", {}).get("normalized_value") != EXPECTED_REVENUE:
        _fail(f"revenue mismatch: {facts_by_line.get('revenue')}")
    if facts_by_line.get("profit_after_tax_attributable", {}).get("normalized_value") != EXPECTED_PAT:
        _fail(f"PAT mismatch: {facts_by_line.get('profit_after_tax_attributable')}")
    if facts_by_line.get("basic_eps", {}).get("normalized_value") != EXPECTED_EPS:
        _fail(f"EPS mismatch: {facts_by_line.get('basic_eps')}")
    if facts_by_line.get("operating_cash_flow", {}).get("normalized_value") != EXPECTED_OCF:
        _fail(f"OCF mismatch: {facts_by_line.get('operating_cash_flow')}")
    if facts_by_line.get("capital_expenditure", {}).get("normalized_value") != EXPECTED_CAPEX:
        _fail(f"Capex mismatch: {facts_by_line.get('capital_expenditure')}")
    if facts_by_line.get("total_equity", {}).get("normalized_value") != EXPECTED_EQUITY:
        _fail(f"Total equity mismatch: {facts_by_line.get('total_equity')}")
    if facts_by_line.get("total_assets", {}).get("normalized_value") != EXPECTED_ASSETS:
        _fail(f"Total assets mismatch: {facts_by_line.get('total_assets')}")

    derived = saved.get("derived") or {}
    dna = derived.get("depreciation_amortization") or {}
    if dna.get("reported") is not False:
        _fail("derived D&A must be marked not reported")
    if dna.get("epistemic_type") != "derived_fact":
        _fail("derived D&A epistemic type mismatch")
    periods = dna.get("periods") or {}
    if periods.get("2024-06-30", {}).get("sum_normalized_value") != 4868386000.0:
        _fail("FY24 derived D&A sum mismatch")
    if periods.get("2025-06-30", {}).get("sum_normalized_value") != 4856392000.0:
        _fail("FY25 derived D&A sum mismatch")
    if (dna.get("source") or {}).get("page") != NOTE_PAGE or (dna.get("source") or {}).get("content_sha256") != audit.EXPECTED_HASH:
        _fail("derived D&A source binding mismatch")
    ebitda = (derived.get("ebitda") or {}).get("periods", {}).get("2024-06-30") or {}
    if ebitda.get("normalized_value") != 19086956000.0:
        _fail(f"FY24 derived EBITDA mismatch: {ebitda}")
    if ebitda.get("operating_profit_normalized_value") != 14218570000.0:
        _fail("FY24 derived EBITDA operating profit operand mismatch")
    if dna.get("formula", {}).get("calculation_version") != DERIVED_LINEAGE_VERSION or not dna.get("formula", {}).get("rou_included"):
        _fail("derived D&A formula metadata mismatch")
    if (derived.get("policy") or {}).get("financial_truth_gate_effect") != "derived_ebitda_lineage_only":
        _fail("derived lane must not affect the financial-truth gate")
    if derived.get("pbt_basis_discrepancy", {}).get("periods", {}).get("2024-06-30", {}).get("normalized_value") != 45804000.0:
        _fail("FY24 PBT basis discrepancy mismatch")
    validate_derived_receipt(saved)

    raw = audit.LOCAL_SOURCE.read_bytes()
    note_text, note_words = read_note_page(raw)
    try:
        extract_operands([w for w in note_words if "right-of-use" not in w[4] and "right" != w[4]], note_text)
        raise AssertionError("missing operand was not rejected")
    except DerivedDnaError as exc:
        if not str(exc).startswith("operand_row_missing:"):
            raise AssertionError(f"unexpected rejection: {exc}")
    try:
        extract_operands([], note_text)
        raise AssertionError("empty geometry was not rejected")
    except DerivedDnaError as exc:
        if not str(exc).startswith(("note_heading_missing", "note_token_missing", "year_header_missing")):
            raise AssertionError(f"unexpected rejection: {exc}")

    print(f"check_mlcf_fy24_full_schedule_audit: PASS (23 candidate facts validated for FY24 comparative)")

if __name__ == "__main__":
    main()
