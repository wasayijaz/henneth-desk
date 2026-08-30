"""Deterministic adversarial and fixture-only positive checks."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mlcf_pioc_analogue_eligibility_adapter import adapt
from mlcf_pioc_analogue_eligibility_contract import CONTRACT_VERSION, HORIZONS, validate_payload


def source(identifier: str, available: str = "2025-01-01", cutoff: str = "2026-01-01") -> dict:
    return {"id": identifier, "hash": "a" * 64, "page": 1, "available_on": available, "cutoff": cutoff}


def candidate(i: int, horizon: str = "1Q") -> dict:
    return {
        "candidate_id": f"cand-{i}", "event_id": f"evt-{i}", "symbol": "MLCF",
        "event_type": "acquisition_divestment", "event_subtype": "acquisition",
        "effective_date": "2024-01-01", "tier": "same_company", "mechanism": "cement_acquisition_control",
        "scale": "dispatch_inclusion", "horizon": horizon, "source": source(f"fixture:cand-{i}", available="2023-12-01", cutoff="2026-01-01"),
        "endpoint_date": "2024-04-01", "endpoint_available_on": "2024-04-02",
        "endpoint_status": "mature", "outcome_return_pct": 1.0,
    }


def payload(count: int = 3) -> dict:
    return {
        "contract_version": CONTRACT_VERSION, "mode": "fixture", "cutoff": "2026-01-01",
        "target_event": {
            "event_id": "evt-target", "symbol": "MLCF", "target_symbol": "PIOC",
            "event_type": "acquisition_divestment", "event_subtype": "acquisition",
            "effective_date": "2025-01-01", "mechanism": "cement_acquisition_control",
            "scale": "dispatch_inclusion", "official_sector": "Cement", "source": source("fixture:target"),
        },
        "candidate_observations": [candidate(i) for i in range(count)],
        "existing_mlcf_analogues_insufficient": ["existing MLCF retained analogue set has fewer than three mature ex-ante observations"],
    }


def expect_blocked(name: str, mutated: dict) -> None:
    result = adapt(mutated)
    assert result["status"] == "blocked", (name, result)
    assert result["reason"] == "invalid_or_unsafe_observations", (name, result)


def main() -> None:
    good = payload()
    assert validate_payload(good) == [], validate_payload(good)
    result = adapt(good)
    assert result["status"] == "eligible"
    assert result["eligible_horizons"] == ["1Q"]
    assert result["mature_counts_by_horizon"] == {"1Q": 3, "2Q": 0, "4Q": 0, "8Q": 0}
    assert all("outcome_return_pct" not in binding for binding in result["candidate_bindings"])
    assert result["existing_mlcf_analogues_insufficient"] == good["existing_mlcf_analogues_insufficient"]

    thin = payload(2)
    assert adapt(thin)["status"] == "insufficient"
    assert adapt(thin)["existing_mlcf_analogues_insufficient"] == thin["existing_mlcf_analogues_insufficient"]
    retained = copy.deepcopy(good)
    retained["candidate_observations"] = []
    retained["existing_mlcf_analogues_insufficient"] = [
        "zero same-company exact acquisition/control analogues",
        "zero same-official-sector exact acquisition/control analogues",
        "all horizons n=0",
    ]
    retained_result = adapt(retained)
    assert retained_result["status"] == "insufficient"
    assert retained_result["mature_counts_by_horizon"] == {horizon: 0 for horizon in HORIZONS}
    assert retained_result["existing_mlcf_analogues_insufficient"] == retained["existing_mlcf_analogues_insufficient"]

    tests = []
    m = copy.deepcopy(good); m["target_event"]["event_id"] = ""; tests.append(("missing target identity", m))
    m = copy.deepcopy(good); m["target_event"]["source"]["hash"] = "bad"; tests.append(("bad hash", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["effective_date"] = "2025-02-01"; tests.append(("lookahead candidate", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["mechanism"] = "unrelated"; tests.append(("mechanism mismatch", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["scale"] = "unknown scale"; tests.append(("scale mismatch", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["event_subtype"] = "contract"; tests.append(("generic contract analogue", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["endpoint_available_on"] = "2026-02-01"; tests.append(("endpoint after cutoff", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["outcome_return_pct"] = math.nan; tests.append(("nonfinite", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["id"] = "real:source"; tests.append(("fixture/real boundary", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["advice"] = "you should buy"; tests.append(("unknown/advice key", m))
    m = copy.deepcopy(good); m["candidate_observations"].append(copy.deepcopy(m["candidate_observations"][0])); tests.append(("duplicate observation", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["endpoint_available_on"] = "2025-01-02"; tests.append(("endpoint evidence lookahead", m))
    real = copy.deepcopy(good); real["mode"] = "real"; real["target_event"] = {**real["target_event"], "event_id": "evt_6e9b520a122b8f2d4a59", "source": {"id": "psx:267429", "hash": "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54", "page": 3, "available_on": "2025-12-18", "cutoff": "2025-12-18"}}; assert adapt(real)["status"] == "blocked"
    for name, mutated in tests:
        expect_blocked(name, mutated)
    print(f"mlcf_pioc_analogue_eligibility_adapter: PASS ({len(tests) + 2} positive/adversarial checks)")


if __name__ == "__main__":
    main()
