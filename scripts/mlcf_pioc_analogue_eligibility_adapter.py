"""Adapter that turns injected MLCF/PIOC observations into a narrow status.

The adapter performs validation and eligibility accounting only.  It never
looks up data, invents peers, computes an aggregate return, or emits a causal
or financial benchmark.
"""
from __future__ import annotations

from typing import Any, Mapping

from mlcf_pioc_analogue_eligibility_contract import (
    CONTRACT_VERSION,
    HORIZONS,
    MIN_SAMPLE,
    STATUSES,
    observation_fingerprint,
    validate_payload,
)


def adapt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic, display-safe eligibility result."""
    violations = validate_payload(payload)
    target = payload.get("target_event") if isinstance(payload, Mapping) and isinstance(payload.get("target_event"), Mapping) else None
    reasons = payload.get("existing_mlcf_analogues_insufficient") if isinstance(payload, Mapping) else None
    reasons = list(reasons) if isinstance(reasons, list) else ["retained MLCF analogue evidence did not clear the injected contract"]
    if violations:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "blocked",
            "reason": "invalid_or_unsafe_observations",
            "violations": violations,
            "target_event": None,
            "existing_mlcf_analogues_insufficient": ["invalid input prevented evaluation; retained analogue insufficiency is unchanged"],
            "eligible_horizons": [],
            "candidate_count": 0,
            "mature_counts_by_horizon": {horizon: 0 for horizon in HORIZONS},
            "candidate_bindings": [],
            "policy": _policy(),
        }

    candidates = payload["candidate_observations"]
    mature_counts = {
        horizon: sum(
            1
            for candidate in candidates
            if candidate.get("horizon") == horizon and candidate.get("endpoint_status") == "mature"
        )
        for horizon in HORIZONS
    }
    eligible_horizons = [horizon for horizon in HORIZONS if mature_counts[horizon] >= MIN_SAMPLE]
    status = "eligible" if eligible_horizons else "insufficient"
    bindings = [
        {
            "candidate_id": candidate["candidate_id"],
            "event_id": candidate["event_id"],
            "tier": candidate["tier"],
            "horizon": candidate["horizon"],
            "source": dict(candidate["source"]),
            "endpoint_date": candidate["endpoint_date"],
            "endpoint_available_on": candidate["endpoint_available_on"],
            "endpoint_status": candidate["endpoint_status"],
            "observation_fingerprint": observation_fingerprint(candidate),
        }
        for candidate in candidates
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "reason": "mature_ex_ante_sample_at_least_three" if status == "eligible" else "fewer_than_three_mature_ex_ante_observations_per_horizon",
        "target_event": {key: target[key] for key in ("event_id", "symbol", "target_symbol", "event_type", "event_subtype", "effective_date", "mechanism", "scale", "official_sector")},
        "existing_mlcf_analogues_insufficient": reasons,
        "candidate_count": len(candidates),
        "mature_counts_by_horizon": mature_counts,
        "eligible_horizons": eligible_horizons,
        "candidate_bindings": bindings,
        "policy": _policy(),
    }


def _policy() -> dict[str, Any]:
    return {
        "descriptive_only": True,
        "no_aggregate_return": True,
        "no_financial_benchmark": True,
        "no_causal_claim": True,
        "no_forecast_or_valuation": True,
        "no_advice": True,
        "exact_target_event_identity": True,
        "strict_ex_ante_endpoint": True,
        "fixture_real_boundary": True,
        "minimum_mature_sample": MIN_SAMPLE,
        "allowed_statuses": list(STATUSES),
    }


__all__ = ["adapt"]
