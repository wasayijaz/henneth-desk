"""Contract and negative checks for the bounded MLCF derived-fact lane."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from mlcf_derived_dna import (
    DERIVED_LINEAGE_VERSION,
    EXPECTED_CONTENT_SHA256,
    EXPECTED_DOCUMENT_ID,
    EXPECTED_SOURCE_URL,
    DerivedDnaError,
    validate_derived_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "state/company_intel/mlcf_fy25_full_schedule_audit.json"
RECONCILIATION = ROOT / "state/company_intel/financial_evidence_reconciliation.json"
TRUTH = ROOT / "state/company_intel/financial_truth_qualification.json"
FORMAL_OUTPUTS = {
    "forecast": ROOT / "state/company_intel/financial_forecasts.json",
    "valuation": ROOT / "state/company_intel/formal_valuations.json",
    "expectations": ROOT / "state/company_intel/market_expectations.json",
}
EXPECTED_PERIODS = ["2025-06-30", "2024-06-30"]
EXPECTED_DERIVED_FACT_KEYS = {
    ("depreciation_amortization", "2024-06-30"),
    ("depreciation_amortization", "2025-06-30"),
    ("ebitda", "2024-06-30"),
    ("ebitda", "2025-06-30"),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reject(candidate: dict, label: str) -> None:
    try:
        validate_derived_receipt(candidate)
    except (DerivedDnaError, TypeError, ValueError):
        return
    raise AssertionError(f"forged derived receipt accepted: {label}")


def _assert_post_consume_state(
    reconciliation: dict,
    truth: dict,
    formal_outputs: dict[str, dict],
) -> None:
    """Require the exact consumed annual lane and fail-closed downstream state."""
    mlcf_reconciliation = reconciliation["companies"]["MLCF"]
    if mlcf_reconciliation.get("source_conflict_count") != 0 or mlcf_reconciliation.get("conflicts") != []:
        raise AssertionError("MLCF canonical reconciliation contains source conflicts")

    lane = mlcf_reconciliation.get("derived_fact_lane") or {}
    if lane != {
        "status": "validated",
        "accepted_fact_count": 4,
        "document_id": EXPECTED_DOCUMENT_ID,
        "content_sha256": EXPECTED_CONTENT_SHA256,
        "formula_versions": [DERIVED_LINEAGE_VERSION],
        "scope": "MLCF psx:260032 only",
    }:
        raise AssertionError(f"reconciliation derived-fact lane is not the approved source-bound lane: {lane}")

    accepted = [row for row in mlcf_reconciliation.get("facts") or [] if row.get("epistemic_type") == "derived_fact"]
    if {(row.get("metric"), row.get("period_end")) for row in accepted} != EXPECTED_DERIVED_FACT_KEYS:
        raise AssertionError("MLCF accepted derived facts are missing or out of scope")
    for row in accepted:
        source = row.get("source") or {}
        if (
            row.get("status") != "eligible"
            or row.get("derived_lineage_validated") is not True
            or source.get("document_id") != EXPECTED_DOCUMENT_ID
            or source.get("content_sha256") != EXPECTED_CONTENT_SHA256
            or source.get("source_url") != EXPECTED_SOURCE_URL
            or source.get("page") != 361
        ):
            raise AssertionError("MLCF derived fact is not an eligible source-bound record")

    mlcf_truth = truth["companies"]["MLCF"]
    if mlcf_truth.get("status") != "not_qualified":
        raise AssertionError("MLCF became formally qualified before the five/eight-period gate")
    if mlcf_truth["annual_operating_cash_flow"] != {"required": 5, "present": 2, "qualified_periods": EXPECTED_PERIODS}:
        raise AssertionError("MLCF annual OCF gate is not exactly 2/5 for FY2024/FY2025")
    if mlcf_truth["qualified_reported_quarter_fact_sets"]["present"] != 0 or mlcf_truth["qualified_reported_quarter_fact_sets"]["required"] != 8:
        raise AssertionError("MLCF direct-quarter gate moved from 0/8")

    annual = mlcf_truth["model_ready_financial_statement_coverage"]["annual"]
    if annual.get("required") != 5 or annual.get("present") != 2 or annual.get("qualified_periods") != EXPECTED_PERIODS:
        raise AssertionError("MLCF annual full-schedule gate is not exactly FY2024/FY2025 at 2/5")
    quarter = mlcf_truth["model_ready_financial_statement_coverage"]["reported_quarter"]
    if quarter.get("required") != 8 or quarter.get("present") != 0 or quarter.get("qualified_periods") != []:
        raise AssertionError("MLCF reported-quarter full-schedule gate is not exactly 0/8")
    if mlcf_truth.get("downstream") != {key: "blocked_financial_truth_not_qualified" for key in ("forecast", "valuation", "market_expectations")}:
        raise AssertionError("MLCF formal downstream gate activated early")

    for label, output in formal_outputs.items():
        if output.get("status") != "blocked_financial_truth_not_qualified" or output.get("truth_status") != "not_qualified" or output.get("result") is not None or output.get("provenance") != []:
            raise AssertionError(f"MLCF formal {label} output activated early")


def _reject_state(reconciliation: dict, truth: dict, formal_outputs: dict[str, dict], label: str, mutate) -> None:
    forged_reconciliation = copy.deepcopy(reconciliation)
    forged_truth = copy.deepcopy(truth)
    forged_outputs = copy.deepcopy(formal_outputs)
    mutate(forged_reconciliation, forged_truth, forged_outputs)
    try:
        _assert_post_consume_state(forged_reconciliation, forged_truth, forged_outputs)
    except AssertionError:
        return
    raise AssertionError(f"forged MLCF post-consume state accepted: {label}")


def main() -> int:
    receipt = _load(RECEIPT)
    facts = validate_derived_receipt(receipt)
    if len(facts) != 4:
        raise AssertionError(f"expected four bounded MLCF derived facts, got {len(facts)}")
    if any(fact.get("epistemic_type") != "derived_fact" or fact.get("reported") is not False for fact in facts):
        raise AssertionError("derived facts are reported/manual masquerades")
    for label, mutate in (
        ("normalized-value", lambda row: row.__setitem__("normalized_value", row["normalized_value"] + 1)),
        ("source-hash", lambda row: row["source"].__setitem__("content_sha256", "0" * 64)),
        ("formula-version", lambda row: row.update({"calculation_version": "forged"})),
        ("missing-input", lambda row: row["lineage"]["inputs"].pop()),
        ("reported-masquerade", lambda row: row.__setitem__("epistemic_type", "reported_fact")),
        ("page-mismatch", lambda row: row["lineage"]["inputs"][0]["source"].__setitem__("page", 360)),
        ("operand-metric", lambda row: row["lineage"]["inputs"][0].__setitem__("metric", "revenue")),
        ("operand-period", lambda row: row["lineage"]["inputs"][0].__setitem__("period_end", "1900-01-01")),
        ("operand-value", lambda row: row["lineage"]["inputs"][0].__setitem__("normalized_value", 999999999)),
        ("operand-geometry", lambda row: row["lineage"]["inputs"][0]["geometry"].__setitem__("row_y", -1)),
    ):
        forged = copy.deepcopy(receipt)
        mutate(forged["derived"]["facts"][0])
        _reject(forged, label)
    duplicate = copy.deepcopy(receipt)
    duplicate["derived"]["facts"].append(copy.deepcopy(duplicate["derived"]["facts"][0]))
    _reject(duplicate, "duplicate-fact")
    missing = copy.deepcopy(receipt)
    missing["derived"]["facts"].pop()
    _reject(missing, "missing-fact")
    duplicate_id = copy.deepcopy(receipt)
    duplicate_id["derived"]["facts"][1]["fact_id"] = duplicate_id["derived"]["facts"][0]["fact_id"]
    _reject(duplicate_id, "duplicate-fact-id")

    reconciliation = _load(RECONCILIATION)
    truth = _load(TRUTH)
    formal_outputs = {label: _load(path)["companies"]["MLCF"] for label, path in FORMAL_OUTPUTS.items()}
    _assert_post_consume_state(reconciliation, truth, formal_outputs)
    _reject_state(
        reconciliation, truth, formal_outputs, "missing-source-bound-derived-fact",
        lambda state, _truth, _outputs: state["companies"]["MLCF"]["facts"].remove(
            next(row for row in state["companies"]["MLCF"]["facts"] if row.get("epistemic_type") == "derived_fact")
        ),
    )
    _reject_state(
        reconciliation, truth, formal_outputs, "nonzero-conflict",
        lambda state, _truth, _outputs: state["companies"]["MLCF"].update({"source_conflict_count": 1, "conflicts": [{"status": "quarantined"}]}),
    )
    _reject_state(
        reconciliation, truth, formal_outputs, "premature-overall-qualification",
        lambda _state, state, _outputs: state["companies"]["MLCF"].update({"status": "qualified"}),
    )
    _reject_state(
        reconciliation, truth, formal_outputs, "early-formal-activation",
        lambda _state, _truth, outputs: outputs["forecast"].update({"status": "computed", "result": {"forecast": 1}}),
    )
    print("MLCF derived facts: PASS (4 source-bound facts; FY2024/FY2025 annual schedules accepted at 2/5; conflicts, qualification and formal activation fail closed; quarters remain 0/8)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
