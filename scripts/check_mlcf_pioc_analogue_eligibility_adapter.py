"""Deterministic adversarial and fixture-only positive checks."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mlcf_pioc_analogue_eligibility_adapter import adapt
from mlcf_pioc_analogue_eligibility_contract import (
    CANONICAL_INSUFFICIENCY_REASONS,
    CONTRACT_VERSION,
    FIXTURE_CANDIDATES,
    FIXTURE_TARGET,
    HORIZONS,
    REAL_TARGET,
    validate_payload,
)

OUTPUT_KEYS = {
    "contract_version", "status", "reason", "violations", "target_event",
    "insufficiency_reasons", "candidate_count", "mature_counts_by_horizon",
    "eligible_horizons", "candidate_bindings", "policy",
}
OUTPUT_TARGET_KEYS = {
    "event_id", "symbol", "target_symbol", "event_type", "event_subtype",
    "effective_date", "mechanism", "scale", "official_sector",
}
REASON_KEYS = {"code", "label"}
VIOLATION_KEYS = {"code", "label"}
OUTPUT_BINDING_KEYS = {
    "candidate_id", "event_id", "tier", "horizon", "source",
    "endpoint_date", "endpoint_available_on", "endpoint_status",
    "observation_fingerprint",
}
OUTPUT_SOURCE_KEYS = {"id", "url", "path", "hash", "page", "available_on", "cutoff"}


def source(identifier: str, available: str = "2025-01-01", cutoff: str = "2026-01-01") -> dict:
    suffix = identifier.split(":", 1)[-1]
    return {
        "id": identifier,
        "url": f"fixture://mlcf-pioc-analogue/{suffix}",
        "path": f"fixtures/mlcf_pioc_analogue/{suffix}.json",
        "hash": "a" * 64,
        "page": 1,
        "available_on": available,
        "cutoff": cutoff,
    }


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
        "target_event": copy.deepcopy(FIXTURE_TARGET),
        "candidate_observations": [copy.deepcopy(row) for row in FIXTURE_CANDIDATES[:count]],
    }


def real_payload() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "mode": "real",
        "cutoff": "2026-08-31",
        "target_event": copy.deepcopy(REAL_TARGET),
        "candidate_observations": [],
    }


def assert_output_closed(result: dict, *, blocked: bool = False) -> None:
    assert set(result) == OUTPUT_KEYS, result
    assert set(result["mature_counts_by_horizon"]) == set(HORIZONS), result
    assert isinstance(result["insufficiency_reasons"], list)
    assert result["insufficiency_reasons"] == list(CANONICAL_INSUFFICIENCY_REASONS)
    for row in result["insufficiency_reasons"]:
        assert set(row) == REASON_KEYS, row
        assert "<script>" not in row["label"].lower()
    assert set(result["policy"]) == {
        "descriptive_only", "no_aggregate_return", "no_financial_benchmark",
        "no_causal_claim", "no_forecast_or_valuation", "no_advice",
        "exact_target_event_identity", "strict_ex_ante_endpoint",
        "fixture_real_boundary", "real_mode_retained_snapshot_zero",
        "fixture_mode_only_can_be_eligible", "minimum_mature_sample",
        "eligible_mode", "allowed_statuses",
    }, result["policy"]
    if blocked:
        assert result["target_event"] is None
        assert result["violations"]
        for row in result["violations"]:
            assert set(row) == VIOLATION_KEYS, row
            assert "<script>" not in row["label"].lower()
    else:
        assert set(result["target_event"]) == OUTPUT_TARGET_KEYS, result["target_event"]
        assert result["violations"] == []
    for binding in result["candidate_bindings"]:
        assert set(binding) == OUTPUT_BINDING_KEYS, binding
        assert set(binding["source"]) == OUTPUT_SOURCE_KEYS, binding["source"]
    rendered = repr(result).casefold()
    assert not any(term in rendered for term in ("you should", "target price", "<script>", "outcome_return_pct"))
    assert "outcome_return_pct" not in rendered
    assert "aggregate_return" not in set(result)


def expect_blocked(name: str, mutated: dict) -> None:
    result = adapt(mutated)
    assert result["status"] == "blocked", (name, result)
    assert result["reason"] == "invalid_or_unsafe_observations", (name, result)
    assert_output_closed(result, blocked=True)


def main() -> None:
    good = payload()
    assert validate_payload(good) == [], validate_payload(good)
    result = adapt(good)
    assert result["status"] == "eligible"
    assert result["eligible_horizons"] == ["1Q"]
    assert result["mature_counts_by_horizon"] == {"1Q": 3, "2Q": 0, "4Q": 0, "8Q": 0}
    assert result["candidate_count"] == 3
    assert all("outcome_return_pct" not in binding for binding in result["candidate_bindings"])
    assert result["insufficiency_reasons"] == list(CANONICAL_INSUFFICIENCY_REASONS)
    assert_output_closed(result)

    thin = payload(2)
    thin_result = adapt(thin)
    assert thin_result["status"] == "insufficient"
    assert thin_result["candidate_count"] == 2
    assert thin_result["insufficiency_reasons"] == list(CANONICAL_INSUFFICIENCY_REASONS)
    assert_output_closed(thin_result)

    retained = real_payload()
    assert validate_payload(retained) == [], validate_payload(retained)
    retained_result = adapt(retained)
    assert retained_result["status"] == "insufficient"
    assert retained_result["reason"] == "retained_mlcf_pioc_analogues_insufficient"
    assert retained_result["candidate_count"] == 0
    assert retained_result["mature_counts_by_horizon"] == {horizon: 0 for horizon in HORIZONS}
    assert retained_result["eligible_horizons"] == []
    assert retained_result["insufficiency_reasons"] == list(CANONICAL_INSUFFICIENCY_REASONS)
    assert_output_closed(retained_result)

    tests = []
    m = copy.deepcopy(good); m["target_event"]["event_id"] = ""; tests.append(("missing target identity", m))
    m = copy.deepcopy(good); m["target_event"]["source"]["hash"] = "bad"; tests.append(("bad hash", m))
    m = copy.deepcopy(good); m["target_event"]["source"]["url"] = "https://example.test/wrong.pdf"; tests.append(("bad target source URL", m))
    m = copy.deepcopy(good); m["target_event"]["source"]["path"] = "state/wrong.json"; tests.append(("bad target source path", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["effective_date"] = "2025-02-01"; tests.append(("lookahead candidate", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["mechanism"] = "unrelated"; tests.append(("mechanism mismatch", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["scale"] = "unknown scale"; tests.append(("scale mismatch", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["event_subtype"] = "contract"; tests.append(("generic contract analogue", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["endpoint_available_on"] = "2026-02-01"; tests.append(("endpoint after cutoff", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["outcome_return_pct"] = math.nan; tests.append(("nonfinite", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["id"] = "real:source"; tests.append(("fixture/real boundary", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["url"] = "https://example.test/wrong.pdf"; tests.append(("fixture source URL boundary", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["path"] = "state/company_documents.json"; tests.append(("fixture source path boundary", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["page"] = 0; tests.append(("bad source page", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["available_on"] = "2026-01-02"; tests.append(("source date after cutoff", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["cutoff"] = "2026-01-02"; tests.append(("source cutoff after product cutoff", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["advice"] = "you should buy"; tests.append(("unknown/advice key", m))
    m = copy.deepcopy(good); m["candidate_observations"].append(copy.deepcopy(m["candidate_observations"][0])); tests.append(("duplicate observation", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["endpoint_available_on"] = "2025-01-02"; tests.append(("endpoint evidence lookahead", m))
    m = real_payload(); m["candidate_observations"] = [
        {
            **candidate(i),
            "source": {
                "id": f"psx:real{i}",
                "url": f"https://dps.psx.com.pk/download/document/{1000 + i}.pdf",
                "path": "state/company_intel/event_studies.json",
                "hash": "b" * 64,
                "page": 1,
                "available_on": "2023-12-01",
                "cutoff": "2026-01-01",
            },
        }
        for i in range(3)
    ]
    fake_real_result = adapt(m)
    assert fake_real_result["status"] == "insufficient"
    assert fake_real_result["candidate_count"] == 0
    assert fake_real_result["eligible_horizons"] == []
    assert fake_real_result["mature_counts_by_horizon"] == {horizon: 0 for horizon in HORIZONS}
    assert_output_closed(fake_real_result)
    m = real_payload(); m["target_event"]["source"]["page"] = 4; tests.append(("real target source page binding", m))
    m = real_payload(); m["target_event"]["source"]["url"] = "https://dps.psx.com.pk/download/document/999999.pdf"; tests.append(("real target source URL binding", m))
    m = real_payload(); m["target_event"]["source"]["path"] = "state/research_index.json"; tests.append(("real target source path binding", m))
    m = copy.deepcopy(good); m["existing_mlcf_analogues_insufficient"] = ["<script>alert(1)</script>"]; tests.append(("caller reason text removed", m))
    m = copy.deepcopy(good); m["candidate_observations"][1]["event_id"] = m["candidate_observations"][0]["event_id"]; tests.append(("duplicate event horizon count", m))
    m = copy.deepcopy(good); m["candidate_observations"][1]["source"]["id"] = m["candidate_observations"][0]["source"]["id"]; tests.append(("duplicate source horizon count", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["event_subtype"] = "tender"; tests.append(("generic tender analogue", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["endpoint_available_on"] = "2024-03-31"; tests.append(("endpoint available before endpoint", m))
    m = copy.deepcopy(good); m["candidate_observations"][0]["source"]["extra"] = "x"; tests.append(("nested unknown source", m))
    bad_blocked = adapt({"contract_version": CONTRACT_VERSION, "mode": "real", "cutoff": "2026-08-31", "target_event": {"symbol": "<script>alert(1)</script>"}, "candidate_observations": [], "existing_mlcf_analogues_insufficient": ["<script>alert(1)</script>"]})
    assert bad_blocked["status"] == "blocked"
    assert "<script>" not in repr(bad_blocked).casefold()
    assert bad_blocked["target_event"] is None
    assert_output_closed(bad_blocked, blocked=True)
    for name, mutated in tests:
        expect_blocked(name, mutated)
    print(f"mlcf_pioc_analogue_eligibility_adapter: PASS ({len(tests) + 3} positive/adversarial checks)")


if __name__ == "__main__":
    main()
