"""Deterministic MARI offshore analogue eligibility adapter."""
from __future__ import annotations
from typing import Any, Mapping
import copy
import json
import mari_enp_analogue_eligibility_contract as contract

def _source(prefix: str, i: int, d: str, event_id: str) -> dict[str, Any]:
    return {"id": f"fixture:{prefix}-{i}", "event_id": event_id,
            "url": f"https://fixture.invalid/{prefix}/{i}.pdf", "page": 1,
            "content_sha256": "a" * 64, "evidence_sha256": "b" * 64,
            "date": d, "cutoff": "2025-11-13"}

def build_real_payload() -> dict[str, Any]:
    return {"contract_version": contract.CONTRACT_VERSION, "mode": "real", "cutoff": contract.TARGET_DATE,
            "target_event": copy.deepcopy(contract.REAL_TARGET),
            "candidate_observations": [{**copy.deepcopy(contract.REAL_CANDIDATE), "horizon": "1Q",
                "endpoint_date": None, "endpoint_available_on": None, "endpoint_status": "unavailable",
                "outcome_return_pct": None}],
            "observed_candidate_count": 1,
            "retained_candidate_note": "One retained Peshawar working-interest acquisition was observed; it is not case-qualified for the offshore block case."}

def build_fixture_payload() -> dict[str, Any]:
    target = copy.deepcopy(contract.REAL_TARGET)
    target["source"] = _source("target", 0, contract.TARGET_DATE, contract.TARGET_EVENT_ID)
    rows = []
    for i, d in enumerate(("2023-01-01", "2023-06-01", "2024-01-01"), 1):
        rows.append({"candidate_id": f"fixture-candidate-{i}", "event_id": f"fixture-event-{i}",
            "symbol": "MARI", "event_type": "acquisition_divestment", "event_subtype": "acquisition",
            "effective_date": d, "mechanism": target["mechanism"], "scale": target["scale"],
            "operator_status": None, "working_interest_pct": None, "source": _source("candidate", i, d, f"fixture-event-{i}"),
            "horizon": "1Q", "endpoint_date": {"2023-01-01":"2023-04-01","2023-06-01":"2023-09-01","2024-01-01":"2024-04-01"}[d],
            "endpoint_available_on": {"2023-01-01":"2023-04-02","2023-06-01":"2023-09-02","2024-01-01":"2024-04-02"}[d],
            "endpoint_status": "mature", "outcome_return_pct": float(i)})
    return {"contract_version": contract.CONTRACT_VERSION, "mode": "fixture", "cutoff": contract.TARGET_DATE,
            "target_event": target, "candidate_observations": rows, "observed_candidate_count": 3,
            "retained_candidate_note": "Synthetic fixture observations only; not retained evidence."}

def _blocked(violation_count: int = 1) -> dict[str, Any]:
    """Return the only response allowed for malformed or caller-drifted input."""
    return {"contract_version": contract.CONTRACT_VERSION, "status": "blocked", "reason": "invalid_or_unsafe_observations",
            "violations": ["invalid_payload"], "violation_count": max(1, int(violation_count)), "target_event": None,
            "observed_candidate_count": 0, "qualified_candidate_count": 0,
            "mature_counts_by_horizon": {h: 0 for h in contract.HORIZONS}, "eligible_horizons": [],
            "candidate_bindings": [], "policy": _policy()}


def _canonical_equal(payload: Any, canonical: Mapping[str, Any]) -> bool:
    """Compare canonical JSON only; malformed values fail closed without inspection errors."""
    try:
        return json.dumps(payload, sort_keys=True, allow_nan=False) == json.dumps(canonical, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return False


def adapt(payload: Mapping[str, Any]) -> dict[str, Any]:
    # Both modes are sealed to their deterministic builders before validation or
    # eligibility computation.  This prevents caller-controlled source/prose,
    # dates, counts, ordering, and endpoint values from reaching the output.
    if not isinstance(payload, Mapping):
        return _blocked()
    mode = payload.get("mode")
    if mode == "real":
        canonical = build_real_payload()
        if not _canonical_equal(payload, canonical):
            return _blocked()
        payload = canonical
    elif mode == "fixture":
        canonical = build_fixture_payload()
        if not _canonical_equal(payload, canonical):
            return _blocked()
        payload = canonical
    violations = contract.validate_payload(payload)
    if violations:
        return _blocked(len(violations))
    target = payload["target_event"]; rows = payload["candidate_observations"]
    qualified = [c for c in rows if c.get("mechanism") == target.get("mechanism")
                 and c.get("scale") == target.get("scale")
                 and c.get("operator_status") == target.get("operator_status")
                 and c.get("working_interest_pct") == target.get("working_interest_pct")]
    mature = {h: sum(1 for c in qualified if c["horizon"] == h and c["endpoint_status"] == "mature") for h in contract.HORIZONS}
    eligible = [h for h in contract.HORIZONS if mature[h] >= contract.MIN_SAMPLE]
    bindings = [{"candidate_id": c["candidate_id"], "event_id": c["event_id"], "horizon": c["horizon"],
                 "case_qualified": c in qualified,
                 "qualification_reasons": [] if c in qualified else (["mechanism_mismatch", "scale_mismatch", "target_operator_unknown", "target_working_interest_unknown", "no_mature_endpoint"] if c.get("event_id") == contract.CANDIDATE_EVENT_ID else ["case_traits_not_exact"]),
                 "source": copy.deepcopy(c["source"]), "endpoint_date": c["endpoint_date"],
                 "endpoint_available_on": c["endpoint_available_on"], "endpoint_status": c["endpoint_status"],
                 "observation_fingerprint": contract.fingerprint(c)} for c in rows]
    return {"contract_version": contract.CONTRACT_VERSION, "status": "eligible" if eligible else "insufficient",
            "reason": "mature_ex_ante_sample_at_least_three" if eligible else "fewer_than_three_case_qualified_mature_observations",
            "target_event": {k: target[k] for k in ("event_id","case_id","symbol","event_type","event_subtype","effective_date","mechanism","scale")},
            "observed_candidate_count": payload["observed_candidate_count"], "qualified_candidate_count": len(qualified),
            "mature_counts_by_horizon": mature, "eligible_horizons": eligible, "candidate_bindings": bindings,
            "policy": _policy()}

def _policy() -> dict[str, Any]:
    return {"descriptive_only": True, "no_returns": True, "no_aggregate_return": True, "no_causal_output": True,
            "no_forecast": True, "no_valuation": True, "no_advice": True, "strict_target_binding": True,
            "strict_ex_ante_endpoint": True, "fixture_real_boundary": True, "minimum_mature_sample": contract.MIN_SAMPLE}

__all__ = ["build_real_payload", "build_fixture_payload", "adapt"]

build_retained_analogue_payload = build_real_payload
build_synthetic_fixture_payload = build_fixture_payload
