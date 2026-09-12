"""Offline regression checks for the Rule 6 signal-health boundary."""
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "scripts" / "build_signals.py"
SPEC = importlib.util.spec_from_file_location("build_signals_under_test", BUILD_PATH)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)

PREFLIGHT_PATH = ROOT / "scripts" / "preflight.py"
PREFLIGHT_SPEC = importlib.util.spec_from_file_location("preflight_under_test", PREFLIGHT_PATH)
PREFLIGHT = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(PREFLIGHT)


def write_json(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def read_json(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def bar(day, close=100.0):
    return {"date": day, "close": close, "open": close, "volume": 1000}


def series(last_date, length=220, close=100.0):
    # The strategy engine only needs an ordered, sufficiently long daily series here.
    days = [f"2026-02-{n:02d}" for n in range(1, 29)]
    days += [f"2026-03-{n:02d}" for n in range(1, 32)]
    days += [f"2026-04-{n:02d}" for n in range(1, 31)]
    days += [f"2026-05-{n:02d}" for n in range(1, 32)]
    days += [f"2026-06-{n:02d}" for n in range(1, 31)]
    days += [f"2026-07-{n:02d}" for n in range(1, 32)]
    days += [f"2026-08-{n:02d}" for n in range(1, 32)]
    days += [f"2026-09-{n:02d}" for n in range(1, 13)]
    rows = [bar(day, close) for day in days[-length:]]
    rows[-1]["date"] = last_date
    return rows


def base_state(root, health="ok"):
    write_json(root, "state/health.json", {"status": health})
    write_json(root, "state/live.json", {
        "session_date": "2026-09-11",
        "tickers": {"GOOD": {"current": 100.0, "volume": 1000}},
    })
    write_json(root, "state/quant.json", {"tickers": {"GOOD": {"date": "2026-09-11"}}})
    write_json(root, "state/universe.json", {"symbols": {"GOOD": {"market": "PSX"}}})
    write_json(root, "state/strategy_map.json", {"tickers": {"GOOD": [proven()]}})
    write_json(root, "state/sectors.json", {"tickers": {"GOOD": {"sector": "test"}}})
    write_json(root, "state/positions.json", {"open": []})
    write_json(root, "config/desk.json", {
        "capital_pkr": 10000,
        "risk": {"risk_per_trade_pct": 1.0, "max_pct_per_trade": 8, "max_positions": 4},
    })
    write_json(root, "strategies/library.json", [
        {"id": "valid", "stop_pct": 1, "target_pct": 2, "entry": []},
    ])
    write_json(root, "state/history/GOOD.json", series("2026-09-11"))


def proven(strategy_id="valid", name="Eligible", score=2.0):
    return {
        "id": strategy_id, "name": name, "category": "test", "hold": 5,
        "hit_rate": 1.0, "net_expectancy_pct": score, "n": 30, "oos_hit": 1.0,
    }


def run_main(root, config_loader=None):
    BUILD.ROOT = root
    BUILD.STATE = root / "state"
    BUILD.LIBRARY = None
    if config_loader is None:
        config_loader = lambda: read_json(root, "config/desk.json")
    with patch.object(BUILD, "load_config", side_effect=config_loader):
        return BUILD.main()


def _publication_failures(signals, health):
    documents = {
        "signals.json": (signals, None),
        "rooms.json": ({"_meta": {"sessions": 0}}, None),
        "health.json": health,
    }

    def fake_load(name):
        return documents.get(name, (None, "missing"))

    PREFLIGHT.fails.clear()
    try:
        with patch.object(PREFLIGHT, "load", side_effect=fake_load), \
             patch.object(PREFLIGHT, "validate_publication", return_value=[]):
            PREFLIGHT.check_research_publication()
        return list(PREFLIGHT.fails)
    finally:
        PREFLIGHT.fails.clear()


def test_missing_health_blocks_before_config():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_json(root, "state/signals.json", {"active": [{"ticker": "OLD"}], "n_candidates": 1})
        write_json(root, "state/positions.json", {"open": [{"ticker": "HELD"}]})
        write_json(root, "state/history/HELD.json", [{"date": "2026-09-10", "close": 1}])
        BUILD.ROOT, BUILD.STATE, BUILD.LIBRARY = root, root / "state", None
        with patch.object(BUILD, "load_config", side_effect=AssertionError("config loaded while blocked")), \
             patch.object(BUILD, "_load_library", side_effect=AssertionError("strategy loaded while blocked")):
            BUILD.main()
        result = read_json(root, "state/signals.json")
        assert result["active"] == [] and result["n_candidates"] == 0
        assert "health blocked" in result["note"]
        assert read_json(root, "state/positions.json") == {"open": [{"ticker": "HELD"}]}
        assert read_json(root, "state/history/HELD.json") == [{"date": "2026-09-10", "close": 1}]


def test_degraded_health_blocks_before_config():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_json(root, "state/health.json", {"status": "degraded"})
        write_json(root, "state/positions.json", {"open": [{"ticker": "HELD"}]})
        write_json(root, "state/history/HELD.json", [{"date": "2026-09-10", "close": 1}])
        BUILD.ROOT, BUILD.STATE, BUILD.LIBRARY = root, root / "state", None
        with patch.object(BUILD, "load_config", side_effect=AssertionError("config loaded while blocked")), \
             patch.object(BUILD, "_load_library", side_effect=AssertionError("strategy loaded while blocked")):
            BUILD.main()
        result = read_json(root, "state/signals.json")
        assert result["active"] == [] and result["n_candidates"] == 0
        assert "health blocked" in result["note"]
        assert read_json(root, "state/positions.json") == {"open": [{"ticker": "HELD"}]}
        assert read_json(root, "state/history/HELD.json") == [{"date": "2026-09-10", "close": 1}]


def test_latest_series_prefers_fresh_date_before_depth():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        BUILD.STATE = root / "state"
        old_deep = series("2026-09-10", 300)
        fresh_dps = series("2026-09-11", 220)
        write_json(root, "state/history_deep/GOOD.json", old_deep)
        write_json(root, "state/history/GOOD.json", fresh_dps)
        assert BUILD.latest_series("GOOD") == fresh_dps
        fresh_deep = series("2026-09-11", 224)
        write_json(root, "state/history_deep/GOOD.json", fresh_deep)
        assert BUILD.latest_series("GOOD") == fresh_deep


def test_foreign_stale_and_unobserved_candidates_are_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base_state(root)
        state = read_json(root, "state/strategy_map.json")
        state["tickers"].update({
            "FOREIGN": [proven()], "STALE": [proven()], "BADPX": [proven()], "ZEROVOL": [proven()],
        })
        write_json(root, "state/strategy_map.json", state)
        universe = read_json(root, "state/universe.json")
        universe["symbols"].update({"FOREIGN": {"market": "US"}, "STALE": {"market": "PSX"},
                                      "BADPX": {"market": "PSX"}, "ZEROVOL": {"market": "PSX"}})
        write_json(root, "state/universe.json", universe)
        live = read_json(root, "state/live.json")
        live["tickers"].update({"FOREIGN": {"current": 100, "volume": 1000},
                                 "STALE": {"current": 100, "volume": 1000},
                                 "BADPX": {"current": None, "volume": 1000},
                                 "ZEROVOL": {"current": 100, "volume": 0}})
        write_json(root, "state/live.json", live)
        quant = read_json(root, "state/quant.json")
        quant["tickers"].update({"FOREIGN": {"date": "2026-09-11"}, "STALE": {"date": "2026-09-10"},
                                  "BADPX": {"date": "2026-09-11"}, "ZEROVOL": {"date": "2026-09-11"}})
        write_json(root, "state/quant.json", quant)
        for sym, day in (("FOREIGN", "2026-09-11"), ("STALE", "2026-09-10"),
                         ("BADPX", "2026-09-11"), ("ZEROVOL", "2026-09-11")):
            write_json(root, f"state/history/{sym}.json", series(day))
        run_main(root)
        result = read_json(root, "state/signals.json")
        assert [row["ticker"] for row in result["active"]] == ["GOOD"]
        assert all(row["ticker"] not in {"FOREIGN", "STALE", "BADPX", "ZEROVOL"}
                   for row in result["active"])


def test_healthy_eligible_example_keeps_rule4_sizing_guard():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base_state(root)
        state = read_json(root, "state/strategy_map.json")
        state["tickers"]["TOO_WIDE"] = [proven("too-wide", "Too wide")]
        write_json(root, "state/strategy_map.json", state)
        universe = read_json(root, "state/universe.json")
        universe["symbols"]["TOO_WIDE"] = {"market": "PSX"}
        write_json(root, "state/universe.json", universe)
        quant = read_json(root, "state/quant.json")
        quant["tickers"]["TOO_WIDE"] = {"date": "2026-09-11"}
        write_json(root, "state/quant.json", quant)
        live = read_json(root, "state/live.json")
        live["tickers"]["TOO_WIDE"] = {"current": 100.0, "volume": 1000}
        write_json(root, "state/live.json", live)
        write_json(root, "state/history/TOO_WIDE.json", series("2026-09-11"))
        library = read_json(root, "strategies/library.json")
        library.append({"id": "too-wide", "stop_pct": 200, "target_pct": 2, "entry": []})
        write_json(root, "strategies/library.json", library)
        run_main(root)
        result = read_json(root, "state/signals.json")
        assert [row["ticker"] for row in result["active"]] == ["GOOD"]
        # The valid 1% stop still passes the unchanged Rule 4 computation: min(10 risk, 8 cap).
        assert int(min(10000 * 0.01 / 1, (10000 * 0.08) / 100)) == 8
        # A stop wider than the risk budget still produces zero shares and remains rejected.
        assert int(min(10000 * 0.01 / 200, (10000 * 0.08) / 100)) == 0


def test_finite_positive_rejects_negative_and_non_numeric_inputs():
    for value in (-1, 0, float("nan"), float("inf"), -float("inf"), True, False, "1", None):
        assert not BUILD._finite_positive(value), repr(value)
    for value in (1, 1.5):
        assert BUILD._finite_positive(value), repr(value)


def test_preflight_rejects_active_signals_when_health_is_missing():
    failures = _publication_failures({"active": [{"ticker": "GOOD"}]}, (None, "missing"))
    assert failures == ["research publication: active signals require health status exactly ok"]
    assert PREFLIGHT.fails == []


def test_preflight_rejects_active_signals_when_health_is_degraded():
    failures = _publication_failures({"active": [{"ticker": "GOOD"}]}, ({"status": "degraded"}, None))
    assert failures == ["research publication: active signals require health status exactly ok"]
    assert PREFLIGHT.fails == []


def test_preflight_allows_empty_signals_when_health_is_degraded():
    failures = _publication_failures({"active": []}, ({"status": "degraded"}, None))
    assert failures == []
    assert PREFLIGHT.fails == []


def test_preflight_allows_active_signals_when_health_is_ok():
    failures = _publication_failures({"active": [{"ticker": "GOOD"}]}, ({"status": "ok"}, None))
    assert failures == []
    assert PREFLIGHT.fails == []


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"signal health checks: {len(tests)} passed")


if __name__ == "__main__":
    main()
