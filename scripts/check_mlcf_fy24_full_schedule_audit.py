"""Validate the audit-only receipt for the retained MLCF FY24 comparative source."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mlcf_fy24_full_schedule_audit as audit
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

    if saved.get("schema_version") != 1 or saved.get("receipt_version") != "mlcf_fy24_full_schedule_audit_v1":
        _fail("schema or receipt version mismatch")
    if saved.get("symbol") != "MLCF" or saved.get("document_id") != "psx:260032":
        _fail("symbol or document_id mismatch")

    src = saved.get("source") or {}
    if src.get("expected_content_sha256") != audit.EXPECTED_HASH:
        _fail("content hash mismatch")
    if src.get("published_at") != "2025-09-25T12:43:00+05:00":
        _fail("published_at mismatch")
    if src.get("available_on") != "2025-09-25":
        _fail("available_on mismatch")
    if src.get("page_scope") != [291, 292, 293, 295]:
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

    print(f"check_mlcf_fy24_full_schedule_audit: PASS (23 candidate facts validated for FY24 comparative)")

if __name__ == "__main__":
    main()
