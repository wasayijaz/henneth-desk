"""Contract and negative checks for the bounded MLCF derived-fact lane."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from mlcf_derived_dna import DerivedDnaError, validate_derived_receipt

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "state/company_intel/mlcf_fy25_full_schedule_audit.json"
RECONCILIATION = ROOT / "state/company_intel/financial_evidence_reconciliation.json"
TRUTH = ROOT / "state/company_intel/financial_truth_qualification.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reject(candidate: dict, label: str) -> None:
    try:
        validate_derived_receipt(candidate)
    except (DerivedDnaError, TypeError, ValueError):
        return
    raise AssertionError(f"forged derived receipt accepted: {label}")


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
    mlcf = reconciliation["companies"]["MLCF"]
    lane = mlcf.get("derived_fact_lane") or {}
    if lane.get("status") != "validated" or lane.get("accepted_fact_count") != 4:
        raise AssertionError(f"reconciliation did not accept only validated derived facts: {lane}")
    accepted = [row for row in mlcf.get("facts") or [] if row.get("epistemic_type") == "derived_fact"]
    if len(accepted) != 4 or any(row.get("status") != "eligible" or not row.get("derived_lineage_validated") for row in accepted):
        raise AssertionError("reconciliation derived-fact records are not source-bound eligible records")

    truth = _load(TRUTH)["companies"]["MLCF"]
    if truth["annual_operating_cash_flow"]["present"] != 2 or truth["annual_operating_cash_flow"]["required"] != 5:
        raise AssertionError("MLCF annual OCF gate moved from proven 2/5")
    if truth["qualified_reported_quarter_fact_sets"]["present"] != 0 or truth["qualified_reported_quarter_fact_sets"]["required"] != 8:
        raise AssertionError("MLCF direct-quarter gate moved from proven 0/8")
    schedule = truth["model_ready_financial_statement_coverage"]
    if schedule["annual"]["present"] != 0 or schedule["reported_quarter"]["present"] != 0:
        raise AssertionError("formal schedules unexpectedly activated")
    if any(not str(value).startswith("blocked") for value in truth["downstream"].values()):
        raise AssertionError("formal engines are not blocked")
    print("MLCF derived facts: PASS (4 validated facts; forged/missing/mismatched inputs rejected; formal engines blocked at 2/5 annual OCF and 0/8 quarters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
