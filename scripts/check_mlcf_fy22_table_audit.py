"""Check the fail-closed FY2022 MLCF audit-only geometry receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / ".cache/company_intel/mlcf_official_intake/194111.pdf"
RECEIPT = ROOT / "state/company_intel/mlcf_fy22_table_audit.json"
SHA = "5103d0a5eaaa8ce2c8c435ae50de6ee5000248ad05094e3f0ac086212e687aae"


def main() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA
    assert receipt["receipt_version"] == "mlcf_fy22_table_audit_v1"
    assert receipt["policy"] == {
        "official_hash_bound_original_only": True,
        "consolidated_statement_only": True,
        "current_period_header_geometry_required": True,
        "no_network": True,
        "no_ocr": True,
        "audit_only": True,
        "canonical_financial_facts_written": False,
        "financial_truth_changed": False,
        "formal_outputs_activated": False,
    }
    expected = {"revenue": (273, 48_519_622_000), "profit_after_tax": (273, 4_553_125_000), "basic_eps": (273, 4.15), "operating_cash_flow": (275, 9_389_176_000)}
    assert {row["metric"] for row in receipt["candidates"]} == set(expected)
    for row in receipt["candidates"]:
        page, normalized = expected[row["metric"]]
        assert row["document_id"] == "psx:194111" and row["content_sha256"] == SHA
        assert row["original_page"] == page and row["normalized_value"] == normalized
        assert row["statement_identity"] == "consolidated"
        assert row["status"] == "audit_only"
        assert row["promotion_status"] == "blocked_pending_independent_statement_and_period_tie_out"
        assert row["current_period_header_geometry"]["text"] == "2022"
        assert row["cell_geometry"]["text"] == str(row["reported_value"]).replace(".0", "").replace("48519622", "48,519,622").replace("4553125", "4,553,125").replace("9389176", "9,389,176")
    print("mlcf_fy22_table_audit: PASS (4 geometry-bound audit candidates; zero promotion)")


if __name__ == "__main__":
    main()
