"""Focused negative and positive checks for the DGKC commissioning seed."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dgkc_commissioning_seed_contract as contract


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)


def event(data: dict, event_id: str) -> dict:
    return next(row for row in data["companies"]["DGKC"]["events"] if row.get("event_id") == event_id)


def main() -> None:
    check("retained chain validates", contract.validate_retained_chain() == [])
    seed = contract.build_seed()
    check("evidence-only unselected no-go", seed["status"] == "evidence_only" and seed["corroboration_status"] == "uncorroborated" and seed["selection_status"] == "unselected" and seed["go_no_go"] == "no_go")
    check("MLCF remains selected industrial case", seed["selected_industrial_case"] == "MLCF" and seed["intelligence_case_eligible"] is False)
    check("formal gate blocked", seed["formal_status"] == "blocked" and seed["model_or_publish_eligible"] is False)
    check("seed validates", contract.validate_seed(seed) == [])
    check("transition exact", [row["stage"] for row in seed["event"]["transition"]] == ["lc_opened", "installation", "commissioned_q3_fy25"])
    check("no event date", seed["event"]["event_date"] is None and seed["event"]["availability_date"] is None)
    check("no event hash invented", seed["event"]["event_evidence_hash"] is None)
    check("economics blocked", seed["reported_operating_operands"]["capex"] is None and seed["reported_operating_operands"]["ramp_or_utilization"] is None)
    check("blockers explicit", len(seed["blockers"]) >= 5)
    baseline = json.dumps(seed, sort_keys=True)

    for label, mutate in (
        ("event id", lambda data: event(data, "evt_c66c444c35780cf5951e").update(event_id="evt_substituted")),
        ("document id", lambda data: event(data, "evt_c66c444c35780cf5951e").update(doc_id="issuer:wrong")),
        ("hash", lambda data: data["documents"]["issuer:bdd12208b3af905c0658a716"].update(content_sha256="wrong")),
        ("page", lambda data: event(data, "evt_c66c444c35780cf5951e")["evidence"][0].update(page=99)),
        ("capacity", lambda data: event(data, "evt_c66c444c35780cf5951e")["evidence"][0].update(text="capacity 80 million bags")),
        ("timing", lambda data: event(data, "evt_c66c444c35780cf5951e")["evidence"][0].update(text="commissioned in Q4 FY25")),
    ):
        ledger = json.loads((ROOT / "state" / "company_event_ledger.json").read_text(encoding="utf-8"))
        documents = json.loads((ROOT / "state" / "company_documents.json").read_text(encoding="utf-8"))
        mutate({"companies": ledger["companies"], "documents": documents["documents"]})
        violations = contract.validate_retained_chain(ledger, documents)
        check(f"negative {label}", violations)

    for bad_status in ("Observed", "Corroborated", "Modelled", "Published"):
        candidate = copy.deepcopy(seed)
        candidate["status"] = bad_status
        check(f"negative status {bad_status}", contract.validate_seed(candidate))
    for bad_formal in ("Modelled", "Published", "validated"):
        candidate = copy.deepcopy(seed)
        candidate["formal_status"] = bad_formal
        check(f"negative formal status {bad_formal}", contract.validate_seed(candidate))
    for forbidden in ("forecast", "valuation", "probability", "advice"):
        candidate = copy.deepcopy(seed)
        candidate[forbidden] = None
        check(f"forbidden key {forbidden}", contract.validate_seed(candidate))

    # Closed shape and hostile/malformed inputs must report deterministic
    # violations, never leak TypeError/KeyError/hostile repr exceptions.
    malformed = [None, [], {"event": []}, {"event": {"transition": [{"event_id": []}]}}]
    for index, candidate in enumerate(malformed):
        check(f"malformed seed {index}", contract.validate_seed(candidate))
    hostile = copy.deepcopy(seed)
    hostile["event"]["transition"][0]["event_id"] = []
    check("malformed transition event id", contract.validate_seed(hostile))
    hostile_key = copy.deepcopy(seed)
    hostile_key["reported_operating_operands"]["forecast"] = 1
    check("hostile forbidden key", contract.validate_seed(hostile_key))
    huge = copy.deepcopy(seed)
    huge["reported_operating_operands"]["capacity_bags"] = 10**99
    check("huge numeric value", contract.validate_seed(huge))
    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        candidate = copy.deepcopy(seed)
        candidate["reported_operating_operands"]["capacity_bags"] = nonfinite
        check("non-finite numeric value", contract.validate_seed(candidate))
    bad_chain = {"companies": {"DGKC": {"events": [None, {"event_id": []}]}}}
    check("malformed chain", contract.validate_retained_chain(bad_chain, {"documents": {}}))
    check("deterministic", json.dumps(contract.build_seed(), sort_keys=True) == baseline)
    print("DGKC commissioning seed checks passed")


if __name__ == "__main__":
    main()
