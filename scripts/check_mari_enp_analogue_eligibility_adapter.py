"""Focused positive and hostile checks for the MARI analogue adapter."""
from __future__ import annotations
import copy, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mari_enp_analogue_eligibility_adapter as adapter
import mari_enp_analogue_eligibility_contract as contract

def main() -> None:
    real = adapter.build_real_payload(); fixture = adapter.build_fixture_payload()
    assert contract.validate_payload(real) == [], contract.validate_payload(real)
    assert contract.validate_payload(fixture) == [], contract.validate_payload(fixture)
    rr = adapter.adapt(real); fr = adapter.adapt(fixture)
    assert rr["status"] == "insufficient" and rr["observed_candidate_count"] == 1
    assert rr["qualified_candidate_count"] == 0 and rr["eligible_horizons"] == []
    assert fr["status"] == "eligible" and fr["eligible_horizons"] == ["1Q"]
    assert fr["mature_counts_by_horizon"] == {"1Q": 3, "2Q": 0, "4Q": 0, "8Q": 0}
    assert all("outcome_return_pct" not in b for b in rr["candidate_bindings"] + fr["candidate_bindings"])
    for p in (real, fixture):
        assert all(k in p for k in ("target_event", "candidate_observations"))

    # The exported validator is independently fail-closed, even when callers
    # bypass the adapter and provide unhashable/malformed structures directly.
    direct_malformed = []
    m = copy.deepcopy(fixture); m["candidate_observations"][0]["horizon"] = ["1Q"]; direct_malformed.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"][0]["event_id"] = {"id": "nested"}; direct_malformed.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"][0]["source"]["id"] = ["fixture:candidate-1"]; direct_malformed.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"][0]["candidate_id"] = {"id": "nested"}; direct_malformed.append(m)
    m = copy.deepcopy(fixture); m["target_event"]["source"] = ["malformed-source"]; direct_malformed.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"] = {"row": "malformed-list"}; direct_malformed.append(m)
    m = copy.deepcopy(fixture); m["target_event"]["event_id"] = ["malformed-id"]; direct_malformed.append(m)
    for index, malformed in enumerate(direct_malformed):
        try:
            violations = contract.validate_payload(malformed)
            repeat_violations = contract.validate_payload(malformed)
        except Exception as exc:  # pragma: no cover - assertion gives context
            raise AssertionError(f"direct validator raised on malformed case {index}: {exc}") from exc
        assert isinstance(violations, list) and violations and all(isinstance(v, str) for v in violations)
        assert violations == repeat_violations

    hostile = []
    # Every fixture field is sealed to build_fixture_payload(); any drift must
    # produce the sanitized blocked schema rather than leaking caller values.
    fixture_mutations = [
        lambda x: x["target_event"].update({"operator_status": "operator"}),
        lambda x: x["target_event"].update({"working_interest_pct": 20}),
        lambda x: x["target_event"].update({"effective_date": contract.CANDIDATE_DATE}),
        lambda x: x["target_event"]["source"].update({"url": "https://evil.invalid/source.pdf"}),
        lambda x: x["target_event"]["source"].update({"content_sha256": "c" * 64}),
        lambda x: x["target_event"]["source"].update({"page": 99}),
        lambda x: x["candidate_observations"].reverse(),
        lambda x: x["candidate_observations"].__getitem__(0).update({"horizon": "8Q"}),
        lambda x: x["candidate_observations"].__getitem__(0).update({"endpoint_date": "2025-11-12"}),
        lambda x: x["candidate_observations"].__getitem__(0).update({"endpoint_available_on": "2025-11-13"}),
        lambda x: x["candidate_observations"].__getitem__(0).update({"outcome_return_pct": 999.0}),
        lambda x: x.update({"observed_candidate_count": 999}),
        lambda x: x.update({"retained_candidate_note": "caller prose"}),
    ]
    for mutate in fixture_mutations:
        m = copy.deepcopy(fixture); mutate(m); hostile.append(m)
    m = copy.deepcopy(real); m["target_event"]["source"]["id"] = contract.CANDIDATE_SOURCE_ID; hostile.append(m)
    m = copy.deepcopy(real); m["target_event"]["mechanism"] = "working_interest_acquisition"; hostile.append(m)
    m = copy.deepcopy(real); m["target_event"]["operator_status"] = "operator"; hostile.append(m)
    m = copy.deepcopy(real); m["target_event"]["working_interest_pct"] = 20; hostile.append(m)
    m = copy.deepcopy(real); m["target_event"]["effective_date"] = contract.CANDIDATE_DATE; hostile.append(m)
    m = copy.deepcopy(real); m["candidate_observations"][0]["effective_date"] = contract.TARGET_DATE; hostile.append(m)
    m = copy.deepcopy(real); m["candidate_observations"][0]["mechanism"] = "unrelated_mechanism"; hostile.append(m)
    m = copy.deepcopy(real); m["candidate_observations"][0]["scale"] = "unrelated_scale"; hostile.append(m)
    m = copy.deepcopy(real); m["candidate_observations"][0]["endpoint_date"] = contract.TARGET_DATE; m["candidate_observations"][0]["endpoint_status"] = "mature"; m["candidate_observations"][0]["endpoint_available_on"] = contract.TARGET_DATE; m["candidate_observations"][0]["outcome_return_pct"] = 1.0; hostile.append(m)
    m = copy.deepcopy(fixture); m["extra"] = 1; hostile.append(m)
    m = copy.deepcopy(fixture); m["target_event"]["source"]["extra"] = 1; hostile.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"].append(copy.deepcopy(m["candidate_observations"][0])); hostile.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"][0]["outcome_return_pct"] = math.nan; hostile.append(m)
    m = copy.deepcopy(fixture); m["retained_candidate_note"] = "you should buy"; hostile.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"][0]["source"]["id"] = "psx:265594"; hostile.append(m)
    # Non-mapping and malformed rows must fail closed, never raise AttributeError.
    m = copy.deepcopy(fixture); m["candidate_observations"][0] = "not-a-row"; hostile.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"][0] = ["list-row"]; hostile.append(m)
    m = copy.deepcopy(fixture); m["target_event"] = ["list-target"]; hostile.append(m)
    m = copy.deepcopy(fixture); m["candidate_observations"] = "not-a-list"; hostile.append(m)
    m = copy.deepcopy(fixture); m["source"] = "caller-source"; hostile.append(m)
    for x in hostile:
        result = adapter.adapt(x)
        assert result["status"] == "blocked"
        assert result["target_event"] is None and result["candidate_bindings"] == []
        assert "caller prose" not in repr(result) and "evil.invalid" not in repr(result)
    assert adapter.adapt({"mode":"real"})["status"] == "blocked"
    assert adapter.adapt({"mode":"fixture"})["status"] == "blocked"
    print(f"mari_enp_analogue_eligibility_adapter: PASS ({len(hostile)+len(direct_malformed)+6} checks)")

if __name__ == "__main__": main()
