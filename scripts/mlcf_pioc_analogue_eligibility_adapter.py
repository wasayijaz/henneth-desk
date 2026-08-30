"""Adapter that turns injected MLCF/PIOC observations into a narrow status.

The adapter performs validation and eligibility accounting only.  It never
looks up data, invents peers, computes an aggregate return, or emits a causal
or financial benchmark.
"""
from __future__ import annotations

from typing import Any, Mapping

from mlcf_pioc_analogue_eligibility_contract import (
    CANONICAL_INSUFFICIENCY_REASONS,
    CONTRACT_VERSION,
    FIXTURE_MODE,
    HORIZONS,
    MIN_SAMPLE,
    REAL_MODE,
    REAL_TARGET,
    STATUSES,
    observation_fingerprint,
    validate_payload,
)

TARGET_OUTPUT_KEYS = (
    "event_id", "symbol", "target_symbol", "event_type", "event_subtype",
    "effective_date", "mechanism", "scale", "official_sector",
)
SOURCE_OUTPUT_KEYS = ("id", "url", "path", "hash", "page", "available_on", "cutoff")


def _reason_rows() -> list[dict[str, str]]:
    return [dict(row) for row in CANONICAL_INSUFFICIENCY_REASONS]


def _safe_violations(violations: list[str]) -> list[dict[str, str]]:
    if not violations:
        return []
    return [{
        "code": "input_contract_violation",
        "label": "Input failed the closed analogue eligibility contract.",
    }]


def _target_row(target: Mapping[str, Any]) -> dict[str, Any]:
    return {key: target[key] for key in TARGET_OUTPUT_KEYS}


def _source_row(source: Mapping[str, Any]) -> dict[str, Any]:
    return {key: source[key] for key in SOURCE_OUTPUT_KEYS}


def adapt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic, display-safe eligibility result."""
    violations = validate_payload(payload)
    if violations:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "blocked",
            "reason": "invalid_or_unsafe_observations",
            "violations": _safe_violations(violations),
            "target_event": None,
            "insufficiency_reasons": _reason_rows(),
            "eligible_horizons": [],
            "candidate_count": 0,
            "mature_counts_by_horizon": {horizon: 0 for horizon in HORIZONS},
            "candidate_bindings": [],
            "policy": _policy(),
        }

    mode = payload["mode"]
    target = payload["target_event"]
    if mode == REAL_MODE:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "insufficient",
            "reason": "retained_mlcf_pioc_analogues_insufficient",
            "violations": [],
            "target_event": _target_row(REAL_TARGET),
            "insufficiency_reasons": _reason_rows(),
            "candidate_count": 0,
            "mature_counts_by_horizon": {horizon: 0 for horizon in HORIZONS},
            "eligible_horizons": [],
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
            "source": _source_row(candidate["source"]),
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
        "violations": [],
        "target_event": _target_row(target),
        "insufficiency_reasons": _reason_rows(),
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
        "real_mode_retained_snapshot_zero": True,
        "fixture_mode_only_can_be_eligible": True,
        "minimum_mature_sample": MIN_SAMPLE,
        "eligible_mode": FIXTURE_MODE,
        "allowed_statuses": list(STATUSES),
    }


__all__ = ["adapt"]
