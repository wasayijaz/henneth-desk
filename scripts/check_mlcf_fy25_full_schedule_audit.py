"""Fail-closed checker for the MLCF FY25 full-schedule audit receipt."""
from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from financial_statement_facts import PARSER_REVISION, PARSER_VERSION
from mlcf_derived_dna import (
    CURRENT_PERIOD_END,
    DERIVED_LINEAGE_VERSION,
    DerivedDnaError,
    NOTE_PAGE,
    SOURCE_PAGE_SCOPE,
    extract_operands,
    read_note_page,
    validate_derived_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/ci_reprocess_review_manifest.json"
DOCUMENTS = ROOT / "state/company_documents.json"
LOCAL_SOURCE = ROOT / ".cache/company_intel/raw/manual/260032.pdf"
RECEIPT = ROOT / "state/company_intel/mlcf_fy25_full_schedule_audit.json"
DOC = "psx:260032"
SHA = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"
EXPECTED_CANDIDATES = 23
EXPECTED_OMISSIONS = 2


def main() -> int:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    documents = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
    doc = manifest["documents"][DOC]
    retained_document = documents["documents"][DOC]
    assert receipt["schema_version"] == 2
    assert receipt["receipt_version"] == "mlcf_fy25_full_schedule_audit_v2"
    assert receipt["derived_lineage_version"] == DERIVED_LINEAGE_VERSION
    assert receipt["document_id"] == DOC and receipt["symbol"] == "MLCF"
    source = receipt["source"]
    assert source["source_url"] == doc["source_url"] == "https://dps.psx.com.pk/download/document/260032.pdf"
    assert source["content_sha256"] == doc["content_sha256"] == SHA
    assert source["raw_path"] == ".cache/company_intel/raw/manual/260032.pdf"
    assert source["local_bytes_status"] == "retained_hash_verified" and LOCAL_SOURCE.exists()
    assert source["local_sha256"] == SHA
    assert source["page_scope"] == list(SOURCE_PAGE_SCOPE)
    assert source["statement_page_scope"] == [291, 292, 293, 295]
    assert source["derived_page_scope"] == [NOTE_PAGE]
    assert source["page_count"] == 401
    availability = source["official_availability"]
    assert availability["status"] == "proven_from_retained_manifest_and_document_state"
    assert availability["published_at"] == doc["published_at"]
    assert availability["available_on"] == retained_document["available_on"] == "2025-09-25"
    assert availability["no_date_inferred"] is True
    policy = receipt["policy"]
    for key in ("official_hash_bound_original_only", "consolidated_statement_only", "local_scale_required", "current_column_header_required", "row_geometry_required", "no_network", "no_ocr", "audit_only"):
        assert policy[key] is True
    for key in ("canonical_financial_facts_written", "coverage_changed", "lifecycle_changed", "forecasts_changed", "valuation_changed", "expectations_changed"):
        assert policy[key] is False
    parser = receipt["parser"]
    assert parser == {
        "version": PARSER_VERSION,
        "revision": PARSER_REVISION,
        "page_scope": list(SOURCE_PAGE_SCOPE),
        "current_period_fact_count": EXPECTED_CANDIDATES,
        "all_period_fact_count": 46,
    }
    assert len(receipt["candidates"]) == EXPECTED_CANDIDATES
    assert all(
        candidate["period_end"] == "2025-06-30"
        and candidate["column_role"] == "current_period"
        and candidate["consolidation"] == "consolidated"
        and candidate["parser_version"] == PARSER_VERSION
        and candidate["parser_revision"] == PARSER_REVISION
        and candidate["readiness"] == "model_loadable"
        for candidate in receipt["candidates"]
    )
    by_line = {candidate["canonical_line"]: candidate for candidate in receipt["candidates"]}
    assert by_line["profit_before_tax"]["page"] == 293
    assert by_line["profit_before_tax"]["raw_value"] == "16,329,735"
    assert by_line["profit_before_tax"]["normalized_value"] == 16329735000.0
    assert by_line["tax_expense"]["page"] == 293
    assert by_line["tax_expense"]["raw_value"] == "(4,826,457)"
    assert by_line["tax_expense"]["normalized_value"] == -4826457000.0
    assert by_line["capital_expenditure"]["page"] == 295
    assert by_line["capital_expenditure"]["raw_value"] == "(3,611,410)"
    assert by_line["capital_expenditure"]["normalized_value"] == -3611410000.0
    assert len(receipt["omissions"]) == EXPECTED_OMISSIONS
    assert receipt["counts"] == {"candidate_count": EXPECTED_CANDIDATES, "omission_count": EXPECTED_OMISSIONS}
    assert all(
        o["reason"] == "current_parser_did_not_emit_required_fact"
        and o["parser_revision"] == PARSER_REVISION
        for o in receipt["omissions"]
    )
    assert receipt["qualification"] == {
        "status": "blocked",
        "full_schedule_qualified": False,
        "reason": "current parser emitted 23 of 25 required current-period lines; 2 required lines remain absent",
    }
    assert "exact local source bytes absent" not in json.dumps(receipt["blockers"], sort_keys=True)
    assert "cannot alter canonical facts, coverage, lifecycle, forecasts, valuation, or expectations" in receipt["non_effects"]
    derived = receipt["derived"]
    assert derived["schema_version"] == 2
    assert derived["derived_lineage_version"] == DERIVED_LINEAGE_VERSION
    assert derived["policy"] == {
        "derived_only_not_reported": True,
        "no_manual_source_method": True,
        "canonical_promotion": "blocked",
        "financial_truth_gate_effect": "derived_ebitda_lineage_only",
    }
    dna = derived["depreciation_amortization"]
    assert dna["reported"] is False
    assert dna["epistemic_type"] == "derived_fact"
    assert dna["source"]["page"] == NOTE_PAGE and dna["source"]["content_sha256"] == SHA
    assert dna["source"]["unit"] == "PKR" and dna["source"]["scale"] == 1000
    assert dna["formula"]["reported_as_single_line"] is False
    assert dna["formula"]["calculation_version"] == DERIVED_LINEAGE_VERSION
    assert dna["formula"]["rou_included"] is True
    assert "right-of-use" in dna["formula"]["rou_definition"]
    periods = dna["periods"]
    assert periods["2025-06-30"]["sum_normalized_value"] == 4856392000.0
    assert periods["2025-06-30"]["sum_raw_value_thousand"] == "4,856,392"
    assert periods["2024-06-30"]["sum_normalized_value"] == 4868386000.0
    assert periods["2024-06-30"]["sum_raw_value_thousand"] == "4,868,386"
    for node in periods.values():
        assert node["operand_count"] == 3
        operands = {row["operand_key"]: row for row in node["operands"]}
        assert operands["depreciation_operating_fixed_assets"]["note_reference"] == "19.1.1"
        assert operands["depreciation_right_of_use"]["note_reference"] == "19.4.1"
        assert operands["amortisation_intangible_assets"]["note_reference"] == "20.1"
        assert all(row["reported_label"] not in ("19.1.1", "19.4.1", "20.1") for row in operands.values())
        assert all(row["epistemic_type"] == "reported_fact" for row in operands.values())
        assert all(row["page"] == NOTE_PAGE and row["unit"] == "PKR" and row["scale"] == 1000 for row in operands.values())
        assert all(row["period_end"] == ("2025-06-30" if node is periods["2025-06-30"] else "2024-06-30") for row in operands.values())
    ebitda = derived["ebitda"]
    assert ebitda["reported"] is False
    assert ebitda["epistemic_type"] == "derived_fact"
    node = ebitda["periods"]["2025-06-30"]
    assert node["operating_profit_normalized_value"] == 19107711000.0
    assert node["derived_depreciation_amortization_normalized_value"] == 4856392000.0
    assert node["normalized_value"] == 23964103000.0
    assert node["formula"]["calculation_version"] == DERIVED_LINEAGE_VERSION
    assert node["formula"]["rou_included"] is True
    assert derived["pbt_basis_discrepancy"]["periods"]["2025-06-30"]["normalized_value"] == 38972000.0
    assert derived["pbt_basis_discrepancy"]["periods"]["2024-06-30"]["normalized_value"] == 45804000.0
    assert len(derived["facts"]) == 4
    validate_derived_receipt(receipt)

    raw = LOCAL_SOURCE.read_bytes()
    note_text, note_words = read_note_page(raw)
    try:
        extract_operands([w for w in note_words if "Amortisation" not in w[4]], note_text)
        raise AssertionError("missing operand was not rejected")
    except DerivedDnaError as exc:
        assert str(exc).startswith("operand_row_missing:")
    try:
        extract_operands(note_words, note_text.replace("Rupees in thousand", "Unknown unit"))
        raise AssertionError("wrong unit was not rejected")
    except DerivedDnaError as exc:
        assert str(exc) == "unit_evidence_missing"
    try:
        extract_operands([w for w in note_words if w[4] != "2024"], note_text)
        raise AssertionError("wrong period/year header was not rejected")
    except DerivedDnaError as exc:
        assert str(exc) == "year_header_missing:2024"
    try:
        shifted = note_words + [(w[0], w[1] + 50.0, w[2], w[3], w[4], w[5], w[6], w[7]) for w in note_words if abs(w[1] - 292.1) < 2]
        extract_operands(shifted, note_text)
        raise AssertionError("ambiguous duplicate row was not rejected")
    except DerivedDnaError as exc:
        assert str(exc).startswith("ambiguous_operand_rows:")
    try:
        extract_operands([w for w in note_words if w[4] != "43.1"], note_text)
        raise AssertionError("missing note token was not rejected")
    except DerivedDnaError as exc:
        assert str(exc) == "note_token_missing"
    print(f"mlcf_fy25_full_schedule_audit: PASS ({EXPECTED_CANDIDATES} parser candidates; {EXPECTED_OMISSIONS} explicit omissions; blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
