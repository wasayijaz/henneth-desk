"""Golden-case checks for the MARI E&P analogue engine.

Not a test framework. A small deterministic script, in the spirit of
check_rule4.py, guarding the three behaviours that make the engine's
benchmarks trustworthy:

1. Cutoff invariants (no lookahead): price endpoints, financial period ends
   and financial availability dates must land strictly before the target
   event's cutoff, and nothing published after a candidate event may serve
   as its baseline.
2. Minimum-sample suppression: cohorts below MIN_SAMPLE never emit
   aggregates, carry the exact insufficient-evidence display text, and the
   target is flagged insufficient_evidence.
3. Mature-cohort arithmetic: with n >= MIN_SAMPLE the median/range/IQR
   statistics are computed, ordering holds (min <= q1 <= median <= q3 <= max)
   and the identities range = max - min, iqr = q3 - q1 hold.

The engine is exercised end to end (build) against synthetic state in a
temporary root with write=False, so real desk state is never touched.

Usage: python scripts/check_mari_enp_analogue_engine.py
"""
from __future__ import annotations

import statistics
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mari_enp_analogue_engine import (
    AGG_CLASSES,
    HORIZON_ORDER,
    INSUFFICIENT_EVIDENCE,
    MIN_SAMPLE,
    OUTCOME_METRICS,
    SYMBOL,
    UNIVERSE,
    aggregate_statistics,
    build,
    financial_outcomes,
    stock_return_outcome,
)
from psx_data import save_json

TOL = 1e-9
failures: list[str] = []
check_count = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global check_count
    check_count += 1
    if not condition:
        failures.append(f"{label}" + (f": {detail}" if detail else ""))


def close(left: float, right: float) -> bool:
    return abs(left - right) <= TOL


def _event(event_id: str, day: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "acquisition_divestment",
        "event_subtype": "working_interest",
        "effective_date": day,
        "evidence": [{"document_id": f"doc:{event_id}"}],
    }


def _fact(metric: str, period_end: str, available_on: str, value: float, readiness: str = "model_loadable") -> dict[str, Any]:
    return {
        "metric": metric,
        "period_end": period_end,
        "available_on": available_on,
        "normalized_value": value,
        "readiness": readiness,
    }


def _history(start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day = start
    index = 0
    while day <= end:
        rows.append({"date": day.isoformat(), "close": 100.0 + (index % 13) * 2.5})
        day += timedelta(days=7)
        index += 1
    return rows


def _write_state(root: Path, events: list[dict[str, Any]]) -> None:
    events_state = {"companies": {SYMBOL: {"events": events}, "OGDC": {"events": []}, "PPL": {"events": []}}}
    save_json(root / "state" / "company_intel" / "operating_events.json", events_state)
    for symbol in UNIVERSE:
        rows = _history(date(2022, 10, 3), date(2025, 12, 15)) if symbol == SYMBOL else []
        save_json(root / "state" / "history" / f"{symbol}.json", rows)
    save_json(root / "state" / "company_financial_series.json", {"tickers": {SYMBOL: {"facts": [], "metrics": {}}}})


def _build_synthetic(events: list[dict[str, Any]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mari_engine_check_") as tmp:
        root = Path(tmp)
        _write_state(root, events)
        return build(root, write=False)


def _target_by_id(payload: dict[str, Any], event_id: str) -> dict[str, Any]:
    for target in payload["targets"]:
        if target["target_event"]["event_id"] == event_id:
            return target
    raise KeyError(event_id)


def _check_suppressed(path: str, agg: dict[str, Any]) -> None:
    check(f"{path} status suppressed", agg["status"] == "suppressed", f"got {agg['status']!r}")
    check(f"{path} reason n_lt_{MIN_SAMPLE}", agg["reason"] == f"n_lt_{MIN_SAMPLE}", f"got {agg['reason']!r}")
    check(f"{path} display text", agg["display"] == INSUFFICIENT_EVIDENCE, f"got {agg['display']!r}")
    check(f"{path} stats null while suppressed", all(value is None for value in agg["stats"].values()))


def _check_available(path: str, agg: dict[str, Any], values: list[float]) -> None:
    check(f"{path} n equals mature outcome count", agg["n"] == len(values), f"n={agg['n']} values={len(values)}")
    check(f"{path} status available", agg["status"] == "available", f"got {agg['status']!r}")
    check(f"{path} no display while available", agg["display"] is None and agg["reason"] is None)
    stats = agg["stats"]
    check(f"{path} stats all finite", all(value is not None for value in stats.values()))
    low, q1, median, q3, high = stats["min"], stats["q1"], stats["median"], stats["q3"], stats["max"]
    check(f"{path} ordering min<=q1<=median<=q3<=max", low <= q1 <= median <= q3 <= high, f"{low} {q1} {median} {q3} {high}")
    check(f"{path} range identity", close(stats["range"], high - low))
    check(f"{path} iqr identity", close(stats["iqr"], q3 - q1))
    check(f"{path} median recompute", close(median, statistics.median(values)))


def _stock_values(target: dict[str, Any], horizon: str, label: str) -> list[float]:
    rows = target["candidates"] if label == "combined" else [row for row in target["candidates"] if row["classification"] == label]
    return [
        float(row["outcomes"][horizon]["stock_return_pct"]["value"])
        for row in rows
        if row["outcomes"][horizon]["stock_return_pct"]["status"] == "mature"
        and row["outcomes"][horizon]["stock_return_pct"]["value"] is not None
    ]


def check_aggregate_statistics() -> None:
    thin = aggregate_statistics([10.0, 20.0])
    check("stats n=2 thin", thin["n"] == 2)
    _check_suppressed("stats n=2", thin)
    empty = aggregate_statistics([])
    check("stats n=0 thin", empty["n"] == 0)
    _check_suppressed("stats n=0", empty)
    boundary = aggregate_statistics([4.0, 4.0, 4.0])
    check("stats n=3 boundary available", boundary["status"] == "available", f"got {boundary['status']!r}")
    _check_available("stats n=3 boundary", boundary, [4.0, 4.0, 4.0])
    junk = aggregate_statistics([True, "x", None, float("inf"), 4.0, 4.0, 4.0])
    check("stats non-finite junk dropped", junk["n"] == 3, f"got n={junk['n']}")
    golden = aggregate_statistics([10.0, 2.0, 3.0, 4.0, 1.0])
    expected = {"median": 3.0, "min": 1.0, "max": 10.0, "range": 9.0, "q1": 2.0, "q3": 4.0, "iqr": 2.0}
    check(
        "stats golden inclusive-quartile values",
        golden["status"] == "available" and all(close(golden["stats"][key], value) for key, value in expected.items()),
        f"got {golden['stats']}",
    )


def check_stock_cutoff() -> None:
    rows = [{"date": "2024-01-02", "close": 100.0}, {"date": "2024-04-15", "close": 110.0}]
    candidate = date(2024, 1, 10)
    mature = stock_return_outcome(rows, candidate, 3, date(2024, 6, 30))
    check("stock mature before cutoff", mature["status"] == "mature", f"got {mature['status']!r}")
    check("stock mature value", close(mature["value"], 10.0), f"got {mature['value']}")
    check("stock baseline strictly before event", mature["baseline_date"] == "2024-01-02")
    check("stock endpoint on/after horizon target", mature["endpoint_date"] == "2024-04-15")
    on_cutoff = stock_return_outcome(rows, candidate, 3, date(2024, 4, 15))
    check("stock endpoint on cutoff excluded", on_cutoff["status"] == "excluded_lookahead", f"got {on_cutoff['status']!r}")
    check(
        "stock lookahead reason",
        on_cutoff["reason"] == "endpoint_not_available_strictly_before_target_cutoff",
        f"got {on_cutoff['reason']!r}",
    )
    check(
        "stock excluded slot carries no endpoint numbers",
        on_cutoff["value"] is None and on_cutoff["endpoint_date"] is None and on_cutoff["endpoint_close"] is None,
    )
    day_before = stock_return_outcome(rows, candidate, 3, date(2024, 4, 16))
    check("stock endpoint day before cutoff mature", day_before["status"] == "mature", f"got {day_before['status']!r}")


def check_financial_cutoff() -> None:
    candidate = date(2024, 1, 10)
    cutoff = date(2024, 12, 31)
    metrics = ("revenue", "eps")
    baseline = [
        _fact("revenue", "2023-09-30", "2023-11-15", 100.0),
        _fact("eps", "2023-09-30", "2023-11-15", 10.0),
    ]
    outcome = [
        _fact("revenue", "2024-03-31", "2024-05-01", 150.0),
        _fact("eps", "2024-03-31", "2024-05-01", 12.0),
    ]
    late_period = [_fact("revenue", "2025-01-15", "2025-02-01", 180.0)]

    mature = financial_outcomes(baseline + outcome + late_period, metrics, candidate, 1, cutoff)
    check("fin revenue mature before cutoff", mature["revenue"]["status"] == "mature", f"got {mature['revenue']['status']!r}")
    check("fin revenue delta", close(mature["revenue"]["value"], 50.0), f"got {mature['revenue']['value']}")
    check("fin eps mature before cutoff", mature["eps"]["status"] == "mature", f"got {mature['eps']['status']!r}")
    check("fin eps delta", close(mature["eps"]["value"], 20.0), f"got {mature['eps']['value']}")
    check(
        "fin margin fails closed without profit series",
        mature["margin"]["status"] == "unavailable" and mature["margin"]["reason"] == "margin_requires_revenue_and_profit_series",
        f"got {mature['margin']['status']!r}/{mature['margin']['reason']!r}",
    )
    check(
        "fin mature slot binds availability date",
        mature["revenue"]["period_end"] == "2024-03-31"
        and mature["revenue"]["available_on"] == "2024-05-01"
        and mature["revenue"]["baseline_period_end"] == "2023-09-30",
    )

    ahead = financial_outcomes(baseline + outcome + late_period, metrics, candidate, 2, cutoff)
    for slot in ("revenue", "margin", "eps"):
        check(
            f"fin {slot} period past cutoff excluded",
            ahead[slot]["status"] == "excluded_lookahead" and ahead[slot]["reason"] == "period_end_not_strictly_before_target_cutoff",
            f"got {ahead[slot]['status']!r}/{ahead[slot]['reason']!r}",
        )

    late_avail = [
        _fact("revenue", "2023-09-30", "2023-11-15", 100.0),
        _fact("eps", "2023-09-30", "2023-11-15", 10.0),
        _fact("revenue", "2024-03-31", "2025-01-10", 150.0),
        _fact("eps", "2024-03-31", "2025-01-10", 12.0),
    ]
    avail = financial_outcomes(late_avail, metrics, candidate, 1, cutoff)
    for slot, metric in (("revenue", "revenue"), ("eps", "eps")):
        check(
            f"fin {slot} available_on past cutoff excluded",
            avail[slot]["status"] == "excluded_lookahead"
            and avail[slot]["reason"] == f"{metric}_available_on_not_strictly_before_target_cutoff",
            f"got {avail[slot]['status']!r}/{avail[slot]['reason']!r}",
        )

    audit = financial_outcomes(
        baseline
        + [
            _fact("revenue", "2024-03-31", "2024-05-01", 150.0, readiness="audit_only"),
            _fact("eps", "2024-03-31", "2024-05-01", 12.0, readiness="audit_only"),
        ],
        metrics,
        candidate,
        1,
        cutoff,
    )
    check(
        "fin audit-only facts fail closed",
        audit["revenue"]["status"] == "unavailable" and audit["revenue"]["reason"] == "revenue_facts_not_model_eligible",
        f"got {audit['revenue']['status']!r}/{audit['revenue']['reason']!r}",
    )

    no_baseline = financial_outcomes(outcome, metrics, candidate, 1, cutoff)
    check(
        "fin missing pre-event baseline unavailable",
        no_baseline["revenue"]["status"] == "unavailable" and no_baseline["revenue"]["reason"] == "no_pre_event_eligible_revenue_baseline",
        f"got {no_baseline['revenue']['status']!r}/{no_baseline['revenue']['reason']!r}",
    )

    future_baseline = financial_outcomes(
        [
            _fact("revenue", "2023-09-30", "2024-02-01", 100.0),
            _fact("eps", "2023-09-30", "2024-02-01", 10.0),
        ]
        + outcome,
        metrics,
        candidate,
        1,
        cutoff,
    )
    check(
        "fin baseline published after event not used",
        future_baseline["revenue"]["status"] == "unavailable"
        and future_baseline["revenue"]["reason"] == "no_pre_event_eligible_revenue_baseline",
        f"got {future_baseline['revenue']['status']!r}/{future_baseline['revenue']['reason']!r}",
    )


def check_thin_cohort() -> None:
    events = [
        _event("cand-1", "2023-01-10"),
        _event("cand-2", "2023-04-11"),
        _event("target-main", "2025-12-31"),
    ]
    payload = _build_synthetic(events)
    check("thin target count equals dated MARI events", payload["target_count"] == len(events), f"got {payload['target_count']}")
    total = 0
    for target in payload["targets"]:
        for horizon, metric_map in target["aggregates"].items():
            for metric, class_map in metric_map.items():
                for label, agg in class_map.items():
                    total += 1
                    _check_suppressed(f"thin {target['target_event']['event_id']} {horizon} {metric} {label}", agg)
        check(
            f"thin {target['target_event']['event_id']} insufficient_evidence flag",
            target["insufficient_evidence"] is True,
        )
    expected_total = len(events) * len(HORIZON_ORDER) * len(OUTCOME_METRICS) * len(AGG_CLASSES)
    check("thin every aggregate suppressed", total == expected_total, f"counted {total} of {expected_total}")
    main = _target_by_id(payload, "target-main")
    for horizon in HORIZON_ORDER:
        agg = main["aggregates"][horizon]["stock_return_pct"]["same_company"]
        check(
            f"thin {horizon} stock same_company n=2 mature but suppressed",
            agg["n"] == 2 and agg["status"] == "suppressed",
            f"got n={agg['n']} status={agg['status']!r}",
        )


def check_mature_cohort() -> None:
    events = [
        _event("cand-1", "2023-01-10"),
        _event("cand-2", "2023-04-11"),
        _event("cand-3", "2023-07-11"),
        _event("target-main", "2025-12-31"),
        _event("target-sameday", "2025-12-31"),
    ]
    payload = _build_synthetic(events)
    main = _target_by_id(payload, "target-main")
    excluded_ids = {row["event_id"] for row in main["excluded_candidates"]}
    check("mature same-day event fails strict-before cutoff", "target-sameday" in excluded_ids)
    check(
        "mature candidate counts",
        main["candidate_count"] == {"same_company": 3, "peer": 0, "combined": 3},
        f"got {main['candidate_count']}",
    )
    for horizon in HORIZON_ORDER:
        for label in ("same_company", "combined"):
            agg = main["aggregates"][horizon]["stock_return_pct"][label]
            _check_available(f"mature {horizon} stock {label}", agg, _stock_values(main, horizon, label))
        peer = main["aggregates"][horizon]["stock_return_pct"]["peer"]
        check(f"mature {horizon} stock peer empty", peer["n"] == 0)
        _check_suppressed(f"mature {horizon} stock peer", peer)
    revenue = main["aggregates"]["1Q"]["revenue_delta_pct"]["same_company"]
    check("mature 1Q revenue_delta_pct same_company n=0", revenue["n"] == 0)
    _check_suppressed("mature 1Q revenue_delta_pct same_company", revenue)
    check("mature target insufficient_evidence False", main["insufficient_evidence"] is False)
    sameday = _target_by_id(payload, "target-sameday")
    check("mature same-day target also has available aggregates", sameday["insufficient_evidence"] is False)


def main() -> None:
    check_aggregate_statistics()
    check_stock_cutoff()
    check_financial_cutoff()
    check_thin_cohort()
    check_mature_cohort()
    print("Henneth - check_mari_enp_analogue_engine")
    if failures:
        print(f"\n  FAIL ({len(failures)} of {check_count}):")
        for item in failures:
            print(f"    x {item}")
        print("\n  RESULT: DO NOT DEPLOY - a cutoff, suppression or aggregate invariant is broken.")
        sys.exit(1)
    print(f"\n  RESULT: OK - {check_count} cutoff/suppression/aggregate checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
