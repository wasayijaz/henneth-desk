"""Focused checks for the CI Historical State Map."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_historical_state_map as builder
from ci_checker_helpers import without_root_meta
from psx_data import ROOT, STATE, load_json


REQUIRED_POLICY = {
    "retained_state_only",
    "strict_no_lookahead",
    "descriptive_not_causal",
    "no_forecast_or_valuation_activation",
    "minimum_sample_three_for_benchmark_stats",
}


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _load_selected_cases() -> list[dict]:
    cases = load_json(STATE / "company_intel" / "intelligence_cases.json", {"selected_symbols": [], "companies": {}})
    rows = []
    for symbol in cases.get("selected_symbols") or []:
        rows.extend([
            case for case in (((cases.get("companies") or {}).get(symbol) or {}).get("cases") or [])
            if isinstance(case, dict)
        ])
    return rows


def _check_no_advice_or_causality(payload: dict) -> None:
    text = _dump(payload).lower()
    banned = (
        "you should buy",
        "you should sell",
        "price target",
        "target price",
        "caused the return",
        "will lead",
    )
    for phrase in banned:
        if re.search(r"\b" + re.escape(phrase) + r"\b", text):
            raise AssertionError(f"disallowed advice/causal phrase leaked: {phrase}")


def _assert_pre_event_only(context: dict) -> None:
    event_day = builder._as_date(((context.get("event_binding") or {}).get("effective_date")))
    market = ((context.get("current_state_vector") or {}).get("market_setup") or {})
    baseline = market.get("baseline") or {}
    baseline_day = builder._as_date(baseline.get("date"))
    if event_day and baseline_day and baseline_day >= event_day:
        raise AssertionError(f"{context['map_id']}: baseline is not strictly pre-event")
    for key, window in (market.get("pre_event_returns") or {}).items():
        if not isinstance(window, dict):
            raise AssertionError(f"{context['map_id']}: {key} window missing")
        for field in ("start_date", "end_date"):
            day = builder._as_date(window.get(field))
            if event_day and day and day >= event_day:
                raise AssertionError(f"{context['map_id']}: {key}.{field} is not strictly pre-event")


def _assert_benchmark_sample_gate(context: dict) -> None:
    benchmark = (((context.get("past_context") or {}).get("strict_analogue_benchmark") or {}))
    for horizon, row in (benchmark.get("horizon_aggregates") or {}).items():
        n = int(row.get("n") or 0)
        stats = row.get("stats") or {}
        if n < builder.MIN_SAMPLE:
            if row.get("status") == "available":
                raise AssertionError(f"{context['map_id']}: {horizon} n<{builder.MIN_SAMPLE} marked available")
            if any(stats.get(field) is not None for field in ("mean_return_pct", "median_return_pct", "min_return_pct", "max_return_pct")):
                raise AssertionError(f"{context['map_id']}: {horizon} leaked small-sample stats")
    contract = context.get("answer_contract") or {}
    if contract.get("can_feed_forecast_or_valuation") is not False:
        raise AssertionError(f"{context['map_id']}: context may feed forecast/valuation")
    if (((context.get("past_context") or {}).get("usable_for_scenario_calibration") is True)
            and "financial_truth_not_qualified" in ((context.get("past_context") or {}).get("calibration_blockers") or [])):
        raise AssertionError(f"{context['map_id']}: calibration ready while financial truth is blocked")


def _assert_state_categories(context: dict) -> None:
    csv = context.get("current_state_vector")
    if not isinstance(csv, dict):
        raise AssertionError(f"{context['map_id']}: missing current_state_vector")
    for key in ("market_setup", "operating_event", "financial_truth", "policy_regime"):
        if key not in csv or not isinstance(csv[key], dict):
            raise AssertionError(f"{context['map_id']}: missing current_state_vector category {key}")
    pr = csv["policy_regime"]
    if pr.get("status") != "unavailable" or pr.get("load_bearing_gap") is not True:
        raise AssertionError(f"{context['map_id']}: policy_regime load-bearing gap must be explicitly represented")
    past = context.get("past_context") or {}
    if past.get("semantics") != "historical_context/not_forecast":
        raise AssertionError(f"{context['map_id']}: past_context semantics must be historical_context/not_forecast")
    if not past.get("evidence_trust_separation"):
        raise AssertionError(f"{context['map_id']}: missing evidence_trust_separation disclaimer")


def _assert_defensible_binding(context: dict) -> None:
    binding = context.get("event_binding") or {}
    policy = binding.get("match_policy")
    allowed_policies = {"direct_canonical_event_id", "exact_source_document_and_hash", "exact_source_document_id"}
    if policy not in allowed_policies:
        raise AssertionError(f"{context['map_id']}: non-defensible binding policy '{policy}'")
    matched_event_id = binding.get("matched_operating_event_id")
    if not matched_event_id:
        raise AssertionError(f"{context['map_id']}: missing matched_operating_event_id")
    if not binding.get("effective_date"):
        raise AssertionError(f"{context['map_id']}: missing effective_date in bound event")
    if not binding.get("matched_source_document_id"):
        raise AssertionError(f"{context['map_id']}: missing matched_source_document_id in bound event")


def _fixture_regression() -> None:
    rows = [
        {"date": "2026-01-01", "close": 10.0, "volume": 100},
        {"date": "2026-01-02", "close": 12.0, "volume": 100},
        {"date": "2026-01-03", "close": 14.0, "volume": 100},
        {"date": "2026-01-04", "close": 16.0, "volume": 100},
        {"date": "2026-01-05", "close": 18.0, "volume": 100},
        {"date": "2026-01-06", "close": 20.0, "volume": 100},
        {"date": "2026-01-07", "close": 99.0, "volume": 999},
    ]
    setup = builder._pre_event_market_setup("TEST", "2026-01-07", rows)
    if setup["baseline"]["date"] != "2026-01-06":
        raise AssertionError("pre-event setup used the event day or later")
    if setup["pre_event_returns"]["5d"]["start_date"] != "2026-01-01":
        raise AssertionError("5-session setup did not use the strict prior window")
    setup_with_future = builder._pre_event_market_setup("TEST", "2026-01-07", rows + [{"date": "2026-02-01", "close": 200.0}])
    if setup_with_future["baseline"]["date"] != "2026-01-06":
        raise AssertionError("future row changed pre-event baseline")


def _fixture_adversarial_lookahead_and_leakage() -> None:
    # Adversarial test 1: Event-day price spike must be completely excluded
    poisoned_rows = [
        {"date": "2026-01-01", "close": 100.0, "volume": 1000},
        {"date": "2026-01-02", "close": 100.0, "volume": 1000},
        {"date": "2026-01-03", "close": 100.0, "volume": 1000},
        {"date": "2026-01-04", "close": 100.0, "volume": 1000},
        {"date": "2026-01-05", "close": 100.0, "volume": 1000},
        {"date": "2026-01-06", "close": 100.0, "volume": 1000},
        {"date": "2026-01-07", "close": 99999.0, "volume": 999999},  # event day spike
        {"date": "2026-01-08", "close": 100000.0, "volume": 999999}, # post-event
    ]
    setup = builder._pre_event_market_setup("TEST", "2026-01-07", poisoned_rows)
    if setup["baseline"]["close"] != 100.0 or setup["baseline"]["date"] != "2026-01-06":
        raise AssertionError("Adversarial lookahead: event-day or post-event close leaked into baseline")
    ret_5d = setup["pre_event_returns"]["5d"]["return_pct"]
    if ret_5d != 0.0:
        raise AssertionError(f"Adversarial lookahead: returns contaminated by post-event jump: {ret_5d}")

    # Adversarial test 2: No pre-event history must fail closed gracefully
    future_only_rows = [
        {"date": "2026-01-07", "close": 100.0, "volume": 1000},
        {"date": "2026-01-08", "close": 105.0, "volume": 1000},
    ]
    empty_setup = builder._pre_event_market_setup("TEST", "2026-01-07", future_only_rows)
    if empty_setup["status"] != "unavailable" or empty_setup["baseline"]["date"] is not None:
        raise AssertionError("Adversarial lookahead: future-only rows did not yield unavailable status")

    # Adversarial test 3: Thin-sample synthetic benchmark with n=2 leaking stats must be suppressed
    fake_thin_benchmark = {
        "status": "candidate_history_present",
        "readiness_ledger": {"strict_candidate_count": 2, "aggregate_ready_horizons": []},
        "horizon_aggregates": {
            "1Q": {
                "status": "available",
                "n": 2,
                "stats": {"mean_return_pct": 25.0, "median_return_pct": 25.0, "min_return_pct": 20.0, "max_return_pct": 30.0},
            }
        }
    }
    proj = builder._benchmark_projection(fake_thin_benchmark)
    if proj["horizon_aggregates"]["1Q"]["status"] != "suppressed":
        raise AssertionError("Adversarial sample gate: n=2 was marked available")
    if proj["horizon_aggregates"]["1Q"]["stats"]["mean_return_pct"] is not None:
        raise AssertionError("Adversarial sample gate: n=2 leaked mean return")

    # Adversarial test 4: Sample n >= 3 but financial truth unqualified must block calibration
    fake_case = {
        "case_id": "test_case",
        "symbol": "MARI",
        "case_family": "e_and_p",
        "case_type": "test",
        "status": "Observed",
        "as_of": "2026-01-01",
    }
    fake_qualified_benchmark = {
        "status": "candidate_history_present",
        "readiness_ledger": {"strict_candidate_count": 3, "aggregate_ready_horizons": ["1Q"]},
        "horizon_aggregates": {
            "1Q": {
                "status": "available",
                "n": 3,
                "stats": {"mean_return_pct": 10.0, "median_return_pct": 10.0, "min_return_pct": 5.0, "max_return_pct": 15.0},
            }
        }
    }
    fake_unqualified_truth = {"companies": {"MARI": {"status": "not_qualified"}}}
    ctx = builder._context_for_case(
        fake_case,
        operating_events={"companies": {}},
        event_study_state={"studies": {}},
        benchmarks={"companies": {"MARI": {"benchmarks": [{"target_event": {"event_id": "test_evt"}, **fake_qualified_benchmark}]}}},
        truth=fake_unqualified_truth,
    )
    if ctx["past_context"]["usable_for_scenario_calibration"] is True:
        raise AssertionError("Adversarial truth gate: unqualified truth allowed scenario calibration")
    if "financial_truth_not_qualified" not in ctx["past_context"]["calibration_blockers"]:
        raise AssertionError("Adversarial truth gate: missing financial_truth_not_qualified blocker")

    # Adversarial test 5: Unbound case must fail closed and never compute valid market setup
    unbound_case = {
        "case_id": "test_unbound_case",
        "symbol": "MARI",
        "case_family": "unsupported_family",
        "case_type": "unsupported_type",
        "status": "Observed",
        "as_of": "2026-05-01",
        "source_lineage": [{"document_id": "psx:999999", "content_sha256": "0" * 64}],
    }
    unbound_ctx = builder._context_for_case(
        unbound_case,
        operating_events={"companies": {"MARI": {"events": []}}},
        event_study_state={"studies": {}},
        benchmarks={"companies": {}},
        truth={"companies": {}},
    )
    if unbound_ctx["event_binding"]["match_policy"] != "unbound_no_defensible_operating_event_match":
        raise AssertionError("Adversarial unbound test: match policy was not unbound")
    if unbound_ctx["current_state_vector"]["market_setup"]["status"] != "unavailable":
        raise AssertionError("Adversarial unbound test: market setup was not unavailable")
    if unbound_ctx["current_state_vector"]["operating_event"]["status"] != "blocked":
        raise AssertionError("Adversarial unbound test: operating event was not blocked")
    if unbound_ctx["answer_contract"]["can_answer_then_vs_now"] is True:
        raise AssertionError("Adversarial unbound test: can_answer_then_vs_now must be False")


def main() -> None:
    path = builder.OUT
    if not path.exists():
        raise AssertionError("historical_state_map.json is missing")
    state = load_json(path, {})
    rebuilt = builder.build(write=False)
    if _dump(without_root_meta(state)) != _dump(without_root_meta(rebuilt)):
        raise AssertionError("historical state map rebuild is not deterministic")
    if state.get("schema_version") != 1 or state.get("product_version") != builder.PRODUCT_VERSION:
        raise AssertionError("historical state map schema/version mismatch")
    if state.get("kind") != "historical_state_map":
        raise AssertionError("historical state map kind mismatch")
    policy = state.get("policy") or {}
    missing = [key for key in REQUIRED_POLICY if policy.get(key) is not True]
    if missing:
        raise AssertionError(f"missing historical state map policy keys: {missing}")
    contexts = state.get("contexts")
    if not isinstance(contexts, list):
        raise AssertionError("contexts must be a list")
    if len(contexts) != len(_load_selected_cases()):
        raise AssertionError("context count must equal selected-symbol IntelligenceCase count")
    seen_map_ids = set()
    seen_case_ids = set()
    seen_symbol_event_pairs = set()
    for context in contexts:
        if not isinstance(context, dict):
            raise AssertionError("context row must be an object")
        case = context.get("case") or {}
        case_id = case.get("case_id")
        symbol = case.get("symbol")
        if not case_id or case_id in seen_case_ids:
            raise AssertionError(f"duplicate or missing case_id: {case_id}")
        seen_case_ids.add(case_id)
        map_id = context.get("map_id")
        if not isinstance(map_id, str) or not map_id or map_id in seen_map_ids:
            raise AssertionError(f"invalid or duplicate map_id: {map_id}")
        seen_map_ids.add(map_id)
        matched_evt = (context.get("event_binding") or {}).get("matched_operating_event_id")
        if matched_evt:
            pair = (symbol, matched_evt)
            if pair in seen_symbol_event_pairs:
                raise AssertionError(f"duplicate matched operating event for symbol {symbol}: {matched_evt}")
            seen_symbol_event_pairs.add(pair)
        _assert_pre_event_only(context)
        _assert_benchmark_sample_gate(context)
        _assert_state_categories(context)
        _assert_defensible_binding(context)
        if (context.get("case") or {}).get("symbol") not in builder.ALPHA_CASES:
            raise AssertionError("context escaped selected golden symbols")
    _check_no_advice_or_causality(state)
    _fixture_regression()
    _fixture_adversarial_lookahead_and_leakage()
    before = path.read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_historical_state_map.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(result.stdout or result.stderr)
    if path.read_bytes() != before:
        raise AssertionError("historical state map builder is not idempotent")
    print(f"historical_state_map: PASS ({len(contexts)} contexts)")


if __name__ == "__main__":
    main()
