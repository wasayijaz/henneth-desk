#!/usr/bin/env python3
"""Focused checks for the Historical State Map -> CI data seam.

The default check is read-only and validates the in-memory CI projection built
from committed state.  ``--require-generated`` additionally checks the checked
in CI JSON, which is useful after the owner regenerates that file.  It is kept
optional because generated CI data can be dirty while another session is
working; this checker must not overwrite it.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from build_ci_slice import OUT, _historical_state_map_meta, build  # noqa: E402
from psx_data import STATE, load_json  # noqa: E402


MIN_SAMPLE = 3
FORBIDDEN_DERIVED_KEYS = {
    "similarity",
    "similarity_score",
    "mae",
    "mfe",
    "time_to_resolution",
}


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _historical_state() -> dict:
    return load_json(STATE / "company_intel" / "historical_state_map.json", {})


def _contexts_by_symbol(state: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for context in state.get("contexts") or []:
        if not isinstance(context, dict):
            raise AssertionError("historical state map contains a non-object context")
        symbol = ((context.get("case") or {}).get("symbol"))
        if not symbol:
            raise AssertionError("historical state map context is missing case.symbol")
        result.setdefault(symbol, []).append(deepcopy(context))
    return result


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _check_context(context: dict) -> None:
    past = context.get("past_context") or {}
    if past.get("semantics") != "historical_context/not_forecast":
        raise AssertionError("context semantics must remain historical_context/not_forecast")
    if not past.get("evidence_trust_separation"):
        raise AssertionError("context must state that evidence trust is separate")

    contract = context.get("answer_contract") or {}
    if contract.get("can_feed_forecast_or_valuation") is not False:
        raise AssertionError("historical context cannot feed forecast or valuation")
    if contract.get("can_publish_benchmark_stats") is not False:
        raise AssertionError("unqualified historical context cannot publish benchmark stats")

    benchmark = past.get("strict_analogue_benchmark") or {}
    for horizon, row in (benchmark.get("horizon_aggregates") or {}).items():
        if not isinstance(row, dict):
            raise AssertionError(f"{horizon} benchmark aggregate is not an object")
        n = int(row.get("n") or 0)
        if n < MIN_SAMPLE:
            stats = row.get("stats") or {}
            if row.get("status") == "available":
                raise AssertionError(f"{horizon} benchmark aggregate is available with n<{MIN_SAMPLE}")
            if any(stats.get(key) is not None for key in ("mean_return_pct", "median_return_pct", "min_return_pct", "max_return_pct")):
                raise AssertionError(f"{horizon} benchmark aggregate leaked thin-sample stats")


def _check_projection(payload: dict, source: dict) -> None:
    expected_by_symbol = _contexts_by_symbol(source)
    meta = payload.get("meta") or {}
    expected_meta = _historical_state_map_meta(source)
    actual_meta = meta.get("historical_state_map")
    if _dump(actual_meta) != _dump(expected_meta):
        raise AssertionError("CI meta historical_state_map is not a structural projection of state")

    seen = 0
    for row in payload.get("tickers") or []:
        symbol = row.get("symbol")
        projected = row.get("historical_state_map")
        if not isinstance(projected, dict):
            raise AssertionError(f"{symbol}: missing historical_state_map row projection")
        expected_contexts = expected_by_symbol.get(symbol, [])
        if _dump(projected.get("contexts") or []) != _dump(expected_contexts):
            raise AssertionError(f"{symbol}: historical contexts do not match committed state")
        if _dump({key: projected.get(key) for key in expected_meta}) != _dump(expected_meta):
            raise AssertionError(f"{symbol}: map metadata drifted from committed state")
        for context in projected.get("contexts") or []:
            _check_context(context)
            seen += 1
        count = ((row.get("intelligence") or {}).get("historical_state_context_count"))
        if count != len(expected_contexts):
            raise AssertionError(f"{symbol}: historical context count is inconsistent")

    forbidden = FORBIDDEN_DERIVED_KEYS.intersection(_walk_keys(payload))
    if forbidden:
        raise AssertionError(f"CI projection manufactured unsupported historical fields: {sorted(forbidden)}")
    return seen


def _check_generated_file(payload: dict, source: dict) -> None:
    if not OUT.exists():
        raise AssertionError(f"generated CI slice is missing: {OUT}")
    generated = load_json(OUT, {})
    _check_projection(generated, source)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-generated", action="store_true", help="also validate the checked CI JSON")
    args = parser.parse_args()

    source = _historical_state()
    if source.get("product_version") != "historical_state_map_v1":
        raise AssertionError("unexpected historical state map product version")
    projection = build(write=False)
    count = _check_projection(projection, source)
    if args.require_generated:
        _check_generated_file(projection, source)
    suffix = "; generated slice checked" if args.require_generated else "; generated slice not required"
    print(f"ci_historical_state_map_seam: PASS ({count} contexts{suffix})")


if __name__ == "__main__":
    main()
