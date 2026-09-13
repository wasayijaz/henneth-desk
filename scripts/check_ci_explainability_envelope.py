#!/usr/bin/env python3
"""Check the deterministic Company Intelligence presentation envelope."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_ci_slice import _explainability_observation, build


PILOT = {"MARI", "MLCF", "PSO"}
SECTOR_DRIVERS = {
    "MARI": {"oil_price", "gas_price", "production_volume"},
    "MLCF": {"dispatch_volume", "realized_price", "coal_cost"},
    "PSO": {"product_price", "sales_volume", "import_parity"},
}
SECTIONS = (
    "observation",
    "transmission_mechanism",
    "forecast_trajectory",
    "key_assumptions",
    "expectations_gap",
    "conclusion",
    "monitoring",
)


def fail(message: str) -> None:
    raise AssertionError(message)


def test_case_bound_event_is_selected() -> None:
    events = [
        {"event_id": "evt_wrong", "event_type": "acquisition", "description": "Wrong positional event."},
        {"event_id": "evt_bound", "event_type": "dispatch_follow_through", "description": "Bound operating event."},
    ]
    case = {
        "cases": [{
            "case_id": "case_cement_vertical",
            "case_type": "cement_expansion",
            "status": "Observed",
            "observed_facts": [{"source_event_id": "evt_bound"}],
        }]
    }
    result = _explainability_observation("MLCF", events, {}, [], case)
    if result.get("event_type") != "dispatch_follow_through" or result.get("case_id") != "case_cement_vertical":
        fail("positive case-binding test: bound operating event was not selected")


def test_array_order_cannot_override_case_binding() -> None:
    events = [
        {"event_id": "evt_bound", "event_type": "dispatch_follow_through", "description": "Bound operating event."},
        {"event_id": "evt_wrong", "event_type": "acquisition", "description": "Wrong positional event."},
    ]
    case = {
        "cases": [{
            "case_id": "case_cement_vertical",
            "case_type": "cement_expansion",
            "status": "Observed",
            "observed_facts": [{"source_event_id": "evt_bound"}],
        }]
    }
    result = _explainability_observation("MLCF", events, {}, [], case)
    if result.get("event_id") == "evt_wrong" or result.get("event_type") != "dispatch_follow_through":
        fail("negative array-order test: positional event overrode case binding")


def test_missing_case_binding_stays_blocked() -> None:
    events = [{"event_id": "evt_wrong", "event_type": "acquisition", "description": "Unbound event."}]
    case = {"cases": [{"case_id": "case_cement_vertical", "case_type": "cement_expansion", "status": "Observed", "observed_facts": []}]}
    result = _explainability_observation("MLCF", events, {}, [], case)
    if result.get("status") != "blocked_no_observation" or "unbound" in str(result.get("text") or "").lower():
        fail("missing-binding test: unbound event was presented as the active case")


def main() -> int:
    test_case_bound_event_is_selected()
    test_array_order_cannot_override_case_binding()
    test_missing_case_binding_stays_blocked()
    payload = build(write=False)
    rows = {row.get("symbol"): row for row in payload.get("tickers") or []}
    missing = PILOT - rows.keys()
    if missing:
        fail(f"pilot rows missing: {sorted(missing)}")
    for symbol in sorted(PILOT):
        row = rows[symbol]
        envelope = row.get("explainability")
        if not isinstance(envelope, dict) or envelope.get("schema_version") != "ci_explainability_v1":
            fail(f"{symbol}: explainability envelope missing or wrong schema")
        for section in SECTIONS:
            if not isinstance(envelope.get(section), dict):
                fail(f"{symbol}: explainability.{section} missing")
        policy = envelope.get("policy") or {}
        for key in ("research_only", "no_advice", "formal_outputs_fail_closed_on_unqualified_financial_truth"):
            if policy.get(key) is not True:
                fail(f"{symbol}: explainability policy missing {key}")
        mechanism = envelope["transmission_mechanism"]
        if not (set(mechanism.get("drivers") or []) & SECTOR_DRIVERS[symbol]):
            fail(f"{symbol}: sector driver map was not preserved")
        if symbol == "MLCF":
            observation = envelope["observation"]
            if observation.get("case_type") != "acquisition_control":
                fail("MLCF: observation is not labeled from the bound PIOC case")
            vertical = observation.get("vertical_case") or {}
            if vertical.get("status") != "blocked_no_case_bound_expansion_event":
                fail("MLCF: PIOC observation was substituted for a cement expansion case")
        truth = row.get("financial_truth_qualification") or {}
        forecast = envelope["forecast_trajectory"]
        expectations = envelope["expectations_gap"]
        formal = [row.get("financial_forecasts"), row.get("formal_valuations"), row.get("market_expectations")]
        if truth.get("status") != "qualified":
            if forecast.get("available") is True or forecast.get("result") is not None:
                fail(f"{symbol}: forecast envelope opened while financial truth is {truth.get('status')}")
            if expectations.get("result") is not None or expectations.get("delta") is not None:
                fail(f"{symbol}: expectations gap opened while financial truth is {truth.get('status')}")
            if any(isinstance(item, dict) and item.get("result") is not None for item in formal):
                fail(f"{symbol}: formal engine result bypassed fail-closed gate")
            if not forecast.get("missing_gates"):
                fail(f"{symbol}: blocked forecast has no plain-language missing gates")
            if not expectations.get("missing_gates"):
                fail(f"{symbol}: blocked expectations gap has no plain-language missing gates")
        conclusion = envelope["conclusion"].get("text") or ""
        if "recommendation" not in conclusion.lower() or "blocked" not in conclusion.lower():
            fail(f"{symbol}: conclusion does not explain research/block state")
    print(f"ci_explainability_envelope: PASS ({len(PILOT)} pilot rows; sections={len(SECTIONS)})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ci_explainability_envelope: FAIL ({exc})", file=sys.stderr)
        raise SystemExit(1)
