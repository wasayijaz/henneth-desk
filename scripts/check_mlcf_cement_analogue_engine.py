"""Focused deterministic checks for the MLCF cement historical analogue and
event-study benchmark engine (Case B, Section 11).

Covers: point-in-time cutoff / no-lookahead discipline, mature/immature/
unavailable outcome status rules, sample-size handling (median/IQR/range at
n >= 3, "Insufficient evidence for a reliable benchmark" below that),
source-only provenance (no analyst estimates for historical facts),
fail-closed blocking when financial truth is not qualified, and input
validation.
"""
from __future__ import annotations

import copy
import json
import math
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mlcf_cement_analogue_engine as engine
import event_studies

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=tol)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def src(value_id="source:fixture:analogue", label="Fixture analogue source",
        url="https://example.invalid/fixture", available_on="2019-01-05"):
    return {"label_type": "source", "source_ref": {"id": value_id, "label": label, "url": url}, "available_on": available_on}


CUTOFF = "2026-08-31"
TARGET_EFFECTIVE = "2026-06-30"
ANALOGUE_EFFECTIVE = "2019-01-05"
HORIZON_ENDPOINTS = {"1Q": "2019-04-05", "2Q": "2019-07-05", "4Q": "2020-01-05", "8Q": "2021-01-05"}


def mature_outcome(horizon: str, seed: float) -> dict:
    endpoint = HORIZON_ENDPOINTS[horizon]
    return {
        "status": "mature", "endpoint_date": endpoint, "endpoint_available_on": endpoint,
        "utilization_change_pct_points": seed + 1.0, "revenue_change_pct": seed + 2.0,
        "ebitda_margin_change_pct_points": seed + 0.5, "eps_change_pct": seed + 3.0,
        "absolute_stock_return_pct": seed - 5.0, "sector_relative_return_pct": seed - 2.0,
    }


def immature_outcome() -> dict:
    return {
        "status": "immature", "endpoint_date": None, "endpoint_available_on": None,
        "utilization_change_pct_points": None, "revenue_change_pct": None,
        "ebitda_margin_change_pct_points": None, "eps_change_pct": None,
        "absolute_stock_return_pct": None, "sector_relative_return_pct": None,
    }


def unavailable_outcome() -> dict:
    out = immature_outcome()
    out["status"] = "unavailable"
    return out


def mature_outcomes(seeds: dict[str, float]) -> dict:
    return {horizon: mature_outcome(horizon, seeds[horizon]) for horizon in engine.HORIZONS}


def analogue_event(event_id: str, symbol: str, seed: float, *, effective_date: str = ANALOGUE_EFFECTIVE,
                    scale_tpd: float = 6000.0) -> dict:
    return {
        "event_id": event_id,
        "symbol": symbol,
        "event_type": "capacity_expansion",
        "effective_date": effective_date,
        "scale_tpd": scale_tpd,
        "pre_event_valuation_metric": "trailing_pe",
        "pre_event_valuation_multiple": 8.0,
        "pre_event_baseline_as_of_date": "2019-01-04",
        "economic_conditions": "neutral",
        "source": src(value_id=f"source:fixture:{event_id}"),
        "outcomes": mature_outcomes({h: seed for h in engine.HORIZONS}),
    }


def golden_case(n_events: int = 4) -> dict:
    symbols = ["LUCK", "DGKC", "PIOC", "FCCL", "MLCF"]
    events = [analogue_event(f"fixture-event-{i+1}", symbols[i], float(i + 1)) for i in range(n_events)]
    return {
        "symbol": "CEMANALOGUE",
        "project_name": "Fixture Analogue Pool",
        "event_ref": "fixture:mlcf-cement-analogue:v1",
        "cutoff_date": CUTOFF,
        "target_event": {
            "symbol": "MLCF", "event_type": "capacity_expansion",
            "effective_date": TARGET_EFFECTIVE, "scale_tpd": 7000.0,
            "source": src(value_id="source:fixture:target", available_on=TARGET_EFFECTIVE),
        },
        "analogue_events": events,
    }


def expect_reject(name, candidate, expected):
    violations = engine.validate_case(candidate)
    check(f"boundary {name}", any(expected in violation for violation in violations), repr(violations))


def qualified_truth_row() -> dict:
    schedule = {
        "required": 5, "present": 5,
        "direct_flow_statement_periods": [], "direct_balance_sheet_periods": [],
        "derived_ebitda_periods": [], "derived_free_cash_flow_periods": [],
    }
    quarter_schedule = dict(schedule, required=8, present=8)
    return {
        "status": "qualified",
        "financial_tie_out": {"status": "qualified"},
        "model_ready_financial_statement_coverage": {
            "annual": schedule, "reported_quarter": quarter_schedule,
        },
        "evidence_gaps": [],
    }


def not_qualified_truth_row() -> dict:
    return {"status": "not_qualified"}


def test_horizon_date_arithmetic_reuse() -> None:
    # This module must reuse event_studies.add_months rather than re-deriving
    # horizon target dates; assert the fixture endpoints are actually valid
    # against that shared function (not just internally self-consistent).
    effective = event_studies.parse_date(ANALOGUE_EFFECTIVE)
    for horizon, months in engine.HORIZON_MONTHS.items():
        target = event_studies.add_months(effective, months)
        endpoint = event_studies.parse_date(HORIZON_ENDPOINTS[horizon])
        check(f"fixture endpoint on/after target {horizon}", endpoint >= target)


def test_sample_size_handling() -> None:
    # n = 2: insufficient evidence at every horizon/metric.
    case = golden_case(n_events=2)
    result = engine.evaluate_case(case)
    for horizon in engine.HORIZONS:
        b = result["benchmarks"][horizon]
        check(f"n=2 mature sample size {horizon}", b["mature_sample_size"] == 2)
        for metric in engine.OUTCOME_METRICS:
            m = b["metrics"][metric]
            check(f"n=2 insufficient {horizon}.{metric}", m["status"] == "insufficient_evidence")
            check(f"n=2 message {horizon}.{metric}", m["message"] == engine.INSUFFICIENT_EVIDENCE_MESSAGE)
            check(f"n=2 no stats leak {horizon}.{metric}",
                  m["median"] is None and m["q1"] is None and m["q3"] is None and m["iqr"] is None
                  and m["min"] is None and m["max"] is None)

    # n = 3: exactly at MIN_SAMPLE, must produce real statistics.
    case3 = golden_case(n_events=3)
    result3 = engine.evaluate_case(case3)
    revenue_values = sorted(seed + 2.0 for seed in (1.0, 2.0, 3.0))
    expected_median = statistics.median(revenue_values)
    expected_q1, _, expected_q3 = statistics.quantiles(revenue_values, n=4, method="inclusive")
    for horizon in engine.HORIZONS:
        m = result3["benchmarks"][horizon]["metrics"]["revenue_change_pct"]
        check(f"n=3 sufficient {horizon}", m["status"] == "sufficient" and m["message"] is None)
        check(f"n=3 median {horizon}", close(m["median"], expected_median))
        check(f"n=3 q1 {horizon}", close(m["q1"], expected_q1))
        check(f"n=3 q3 {horizon}", close(m["q3"], expected_q3))
        check(f"n=3 iqr {horizon}", close(m["iqr"], expected_q3 - expected_q1))
        check(f"n=3 min {horizon}", close(m["min"], min(revenue_values)))
        check(f"n=3 max {horizon}", close(m["max"], max(revenue_values)))

    # n = 4: full fixture, independently recompute all six metrics for 1Q.
    case4 = golden_case(n_events=4)
    result4 = engine.evaluate_case(case4)
    seeds = [1.0, 2.0, 3.0, 4.0]
    metric_offsets = {
        "utilization_change_pct_points": 1.0, "revenue_change_pct": 2.0,
        "ebitda_margin_change_pct_points": 0.5, "eps_change_pct": 3.0,
        "absolute_stock_return_pct": -5.0, "sector_relative_return_pct": -2.0,
    }
    for metric, offset in metric_offsets.items():
        values = sorted(seed + offset for seed in seeds)
        m = result4["benchmarks"]["1Q"]["metrics"][metric]
        check(f"n=4 {metric} median", close(m["median"], statistics.median(values)))
        check(f"n=4 {metric} sample size", m["sample_size"] == 4)


def test_point_in_time_cutoff_discipline() -> None:
    # Lookahead: analogue event effective_date after cutoff must be rejected.
    lookahead = golden_case()
    lookahead["analogue_events"][0]["effective_date"] = "2026-09-30"
    expect_reject("event after cutoff", lookahead, "effective_date: must be on or before cutoff_date")

    # Lookahead: mature outcome endpoint after cutoff must be rejected.
    endpoint_lookahead = golden_case()
    endpoint_lookahead["analogue_events"][0]["outcomes"]["8Q"]["endpoint_date"] = "2026-09-30"
    expect_reject("endpoint after cutoff", endpoint_lookahead, "after cutoff_date (lookahead)")

    # Lookahead: evidence availability after cutoff must be rejected even if
    # the endpoint date itself is fine.
    availability_lookahead = golden_case()
    availability_lookahead["analogue_events"][0]["outcomes"]["1Q"]["endpoint_available_on"] = "2026-09-30"
    expect_reject("availability after cutoff", availability_lookahead, "after cutoff_date (lookahead)")

    # A mature outcome whose horizon target date is still in the future
    # relative to cutoff must fail closed (the target date has not happened
    # yet, so it cannot be mature no matter what numbers are supplied).
    premature = golden_case()
    premature["analogue_events"][0]["effective_date"] = "2026-08-01"
    premature["analogue_events"][0]["outcomes"]["8Q"] = mature_outcome("8Q", 1.0)
    premature["analogue_events"][0]["outcomes"]["8Q"]["endpoint_date"] = "2028-08-01"
    premature["analogue_events"][0]["outcomes"]["8Q"]["endpoint_available_on"] = "2028-08-01"
    # also fix the other horizons' effective-date-relative endpoints so only 8Q is being tested
    for h in ("1Q", "2Q", "4Q"):
        premature["analogue_events"][0]["outcomes"][h] = immature_outcome()
    expect_reject("mature but target date after cutoff", premature, "horizon target date")

    # An immature outcome whose horizon target date has already passed as of
    # cutoff must fail closed (it should have been marked mature or
    # unavailable, not immature).
    stale_immature = golden_case()
    stale_immature["analogue_events"][0]["outcomes"]["1Q"] = immature_outcome()
    expect_reject("immature but target date already passed", stale_immature, "already on or before cutoff_date")

    # Endpoint before the horizon target date (too early) must be rejected.
    early_endpoint = golden_case()
    early_endpoint["analogue_events"][0]["outcomes"]["4Q"]["endpoint_date"] = "2019-02-01"
    expect_reject("endpoint before horizon target", early_endpoint, "must be on or after the horizon target date")

    # Valid immature and unavailable statuses (target after cutoff for
    # immature; any status for unavailable) must both validate cleanly.
    valid_statuses = golden_case()
    valid_statuses["analogue_events"][0]["effective_date"] = "2026-08-01"
    valid_statuses["analogue_events"][0]["outcomes"] = {
        "1Q": unavailable_outcome(), "2Q": unavailable_outcome(),
        "4Q": unavailable_outcome(), "8Q": immature_outcome(),
    }
    check("immature/unavailable statuses validate", engine.validate_case(valid_statuses) == [])


def test_source_only_provenance() -> None:
    # Historical analogue facts must be source-labelled; analyst estimates
    # are not accepted (unlike the scenario-lab module's assumptions).
    analyst_labelled = golden_case()
    analyst_labelled["analogue_events"][0]["source"] = {
        "value": 1.0, "label_type": "analyst",
        "analyst_ref": {"note_id": "n", "note": "estimate"}, "available_on": "2019-01-05",
    }
    expect_reject("analyst-labelled source rejected", analyst_labelled, "provenance record must carry label_type=source")
    check("provenance_ok rejects analyst records", not engine.provenance_ok(analyst_labelled["analogue_events"][0]["source"]))
    check("provenance_ok accepts source records", engine.provenance_ok(src()))


def test_fail_closed_financial_truth_gate() -> None:
    case = golden_case()

    blocked = engine.evaluate_with_financial_truth_gate(case, not_qualified_truth_row())
    check("not-qualified blocks", blocked["status"] == "blocked_financial_truth_not_qualified")
    check("not-qualified reason recorded", blocked["blocked_reasons"] == ["financial_truth_status:not_qualified"])
    check("not-qualified withholds analogue pool", blocked["analogue_pool"] is None)
    check("not-qualified withholds benchmarks", blocked["benchmarks"] is None)
    check("not-qualified withholds target event", blocked["target_event"] is None)

    missing = engine.evaluate_with_financial_truth_gate(case, {})
    check("missing truth row blocks", missing["status"] == "blocked_financial_truth_not_qualified"
          and missing["blocked_reasons"] == ["financial_truth_status:missing"])

    computed = engine.evaluate_with_financial_truth_gate(case, qualified_truth_row())
    check("qualified computes", computed["status"] == "computed")
    check("qualified matches pure kernel",
          json.dumps(computed, sort_keys=True) == json.dumps(engine.evaluate_case(case), sort_keys=True))

    invalid_case = golden_case()
    invalid_case["analogue_events"][0]["scale_tpd"] = -1.0
    invalid_blocked = engine.evaluate_with_financial_truth_gate(invalid_case, qualified_truth_row())
    check("qualified but invalid case blocks on inputs", invalid_blocked["status"] == "blocked_invalid_inputs")
    check("invalid input reason present",
          any("scale_tpd" in reason for reason in invalid_blocked["blocked_reasons"]))


def test_real_build_blocks_against_current_state() -> None:
    # The real MLCF financial_truth_qualification.json row is not_qualified
    # today; the real build must fail closed and never leak numbers, and must
    # not fabricate an analogue pool.
    result = engine.build(write=False)
    check("real build blocks", result["status"] == "blocked_financial_truth_not_qualified")
    check("real build no numbers", result["analogue_pool"] is None and result["benchmarks"] is None)
    check("real build identity", result["project"]["symbol"] == engine.REAL_SYMBOL
          and result["project"]["project_name"] == engine.REAL_PROJECT_NAME)

    written = engine.build(write=True)
    on_disk = json.loads(engine.OUTPUT_PATH.read_text(encoding="utf-8"))
    check("generated state file matches build output", on_disk == written)
    check("generated state file path", engine.OUTPUT_PATH.name == "mlcf_cement_analogue_engine.json"
          and engine.OUTPUT_PATH.parent.name == "company_intel")


def test_input_validation() -> None:
    case = golden_case()
    check("module version", engine.MODULE_VERSION == "mlcf_cement_analogue_engine_v1")
    check("formula id", engine.FORMULA_ID == "mlcf_cement_analogue_engine.historical_benchmark.v1")
    check("result schema", engine.RESULT_SCHEMA == "mlcf_cement_analogue_engine_result_v1")
    check("golden validates", engine.validate_case(case) == [])
    check("min sample constant", engine.MIN_SAMPLE == 3)

    mutations = [
        ("missing project name", lambda c: c.update(project_name=""), "project_name: must be a non-empty string"),
        ("missing cutoff", lambda c: c.pop("cutoff_date"), "cutoff_date: must be an ISO date"),
        ("bad cutoff format", lambda c: c.update(cutoff_date="31-08-2026"), "cutoff_date: must be an ISO date"),
        ("target symbol not allowed",
         lambda c: c["target_event"].update(symbol="OGDC"),
         "target_event.symbol: must be one of"),
        ("target event type invalid",
         lambda c: c["target_event"].update(event_type="acquisition"),
         "target_event.event_type: must be one of"),
        ("target scale zero",
         lambda c: c["target_event"].update(scale_tpd=0.0),
         "target_event.scale_tpd: must be > 0"),
        ("target source missing",
         lambda c: c["target_event"].pop("source"),
         "target_event.source: provenance record must carry"),
        ("target unknown field",
         lambda c: c["target_event"].update(extra=1.0),
         "target_event.extra: unknown field"),
        ("analogue not a list", lambda c: c.update(analogue_events="oops"), "analogue_events: must be a list"),
        ("analogue symbol not allowed",
         lambda c: c["analogue_events"][0].update(symbol="OGDC"),
         "analogue_events[0].symbol: must be one of"),
        ("analogue event type invalid",
         lambda c: c["analogue_events"][0].update(event_type="dividend"),
         "analogue_events[0].event_type: must be one of"),
        ("analogue scale bool",
         lambda c: c["analogue_events"][0].update(scale_tpd=True),
         "analogue_events[0].scale_tpd: must be a finite number"),
        ("analogue scale negative",
         lambda c: c["analogue_events"][0].update(scale_tpd=-500.0),
         "analogue_events[0].scale_tpd: must be > 0"),
        ("analogue valuation metric invalid",
         lambda c: c["analogue_events"][0].update(pre_event_valuation_metric="p_b"),
         "analogue_events[0].pre_event_valuation_metric: must be one of"),
        ("analogue valuation multiple nan",
         lambda c: c["analogue_events"][0].update(pre_event_valuation_multiple=float("nan")),
         "analogue_events[0].pre_event_valuation_multiple: must be a finite number"),
        ("analogue baseline after effective",
         lambda c: c["analogue_events"][0].update(pre_event_baseline_as_of_date="2019-02-01"),
         "analogue_events[0].pre_event_baseline_as_of_date: must be on or before effective_date"),
        ("analogue economic conditions invalid",
         lambda c: c["analogue_events"][0].update(economic_conditions="booming"),
         "analogue_events[0].economic_conditions: must be one of"),
        ("analogue missing event_id",
         lambda c: c["analogue_events"][0].pop("event_id"),
         "analogue_events[0].event_id: missing required field"),
        ("analogue duplicate event_id",
         lambda c: c["analogue_events"].append(dict(c["analogue_events"][0])),
         "analogue_events[4].event_id: duplicate event_id"),
        ("analogue outcomes not mapping",
         lambda c: c["analogue_events"][0].update(outcomes="oops"),
         "analogue_events[0].outcomes: must be a mapping"),
        ("analogue outcomes missing horizon",
         lambda c: c["analogue_events"][0]["outcomes"].pop("1Q"),
         "analogue_events[0].outcomes.1Q: missing required horizon"),
        ("analogue outcomes unknown horizon",
         lambda c: c["analogue_events"][0]["outcomes"].update({"16Q": mature_outcome("1Q", 1.0)}),
         "analogue_events[0].outcomes.16Q: unknown horizon"),
        ("mature outcome missing metric",
         lambda c: c["analogue_events"][0]["outcomes"]["2Q"].pop("revenue_change_pct"),
         "revenue_change_pct: mature outcome requires a finite number"),
        ("mature outcome bool metric",
         lambda c: c["analogue_events"][0]["outcomes"]["2Q"].update(revenue_change_pct=True),
         "revenue_change_pct: mature outcome requires a finite number"),
        ("mature outcome extra numeric on immature",
         lambda c: c["analogue_events"][0]["outcomes"].__setitem__("4Q", dict(immature_outcome(), revenue_change_pct=1.0)),
         "only a mature outcome may carry a numeric value"),
        ("outcome status invalid",
         lambda c: c["analogue_events"][0]["outcomes"]["1Q"].update(status="bullish"),
         "status: must be one of"),
        ("unknown outcome field",
         lambda c: c["analogue_events"][0]["outcomes"]["1Q"].update(extra_field=1.0),
         "extra_field: unknown outcome field"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        expect_reject(name, candidate, expected)

    try:
        engine.evaluate_case({"symbol": "CEMANALOGUE"})
    except ValueError as error:
        check("evaluate raises named violations", "; " in str(error) and "project_name" in str(error))
    else:
        raise AssertionError("evaluate should reject invalid case")

    empty_pool = golden_case(n_events=0)
    empty_result = engine.evaluate_case(empty_pool)
    check("empty pool validates", engine.validate_case(empty_pool) == [])
    for horizon in engine.HORIZONS:
        for metric in engine.OUTCOME_METRICS:
            check(f"empty pool insufficient {horizon}.{metric}",
                  empty_result["benchmarks"][horizon]["metrics"][metric]["status"] == "insufficient_evidence")


def test_envelope_shape_and_no_advice() -> None:
    case = golden_case()
    result = engine.evaluate_case(case)
    expected_keys = {
        "schema_version", "formula_id", "module_version", "run_receipt", "status",
        "blocked_reasons", "project", "target_event", "analogue_pool", "benchmarks",
        "confidence_limitations",
    }
    check("envelope shape", set(result) == expected_keys)
    check("computed status", result["status"] == "computed" and result["blocked_reasons"] == [])
    expected_order = sorted(
        case["analogue_events"],
        key=lambda ev: (ev["effective_date"], ev["event_id"]),
    )
    check("analogue pool sorted by effective_date then event_id",
          [e["event_id"] for e in result["analogue_pool"]["events"]]
          == [ev["event_id"] for ev in expected_order])

    repeat = engine.evaluate_case(case)
    copied = engine.evaluate_case(copy.deepcopy(case))
    dump = json.dumps(result, sort_keys=True)
    check("same object deterministic", json.dumps(repeat, sort_keys=True) == dump)
    check("deepcopy deterministic", json.dumps(copied, sort_keys=True) == dump)

    blocked = engine.blocked_result(golden_case(), ["zeta", "alpha", "alpha"])
    check("blocked envelope reasons sorted and deduped", blocked["blocked_reasons"] == ["alpha", "zeta"])

    for label, payload in (("computed", result), ("blocked", blocked)):
        text_payload = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
            check(f"{label} no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text_payload) is None)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))


def main() -> None:
    test_horizon_date_arithmetic_reuse()
    test_sample_size_handling()
    test_point_in_time_cutoff_discipline()
    test_source_only_provenance()
    test_fail_closed_financial_truth_gate()
    test_real_build_blocks_against_current_state()
    test_input_validation()
    test_envelope_shape_and_no_advice()
    print(f"mlcf cement analogue engine: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
