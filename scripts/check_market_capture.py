"""Offline capture regressions. Run: python -B scripts/check_market_capture.py.

Provider boundaries are mocked; real JSON writers operate only in a temporary directory.
The intraday timestamp parser is tested separately by its owner.
"""
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
from time import strftime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import data_health
import fetch_indices
import fetch_intraday
import psx_data
import snapshot


PKT = timezone(timedelta(hours=5))
FRIDAY = datetime(2026, 9, 11, 16, 35, tzinfo=PKT)
SATURDAY = datetime(2026, 9, 12, 10, 0, tzinfo=PKT)
PRICE = 123456.75  # Synthetic fixture, not market data.


class CaptureClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return SATURDAY.astimezone(tz) if tz else SATURDAY.replace(tzinfo=None)


class MarketCaptureChecks(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.state = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        # Redirect all producer storage before invoking any producer or loading any JSON.
        for module in (snapshot, fetch_indices, fetch_intraday, data_health, psx_data):
            self.stack.enter_context(patch.object(module, "STATE", self.state))
        self.stack.enter_context(patch.object(fetch_indices, "OUT", self.state / "indices.json"))
        self.stack.enter_context(patch.object(psx_data, "load_config", side_effect=AssertionError("config read forbidden")))
        self.stack.enter_context(patch.object(psx_data.requests.sessions.Session, "request",
                                            side_effect=AssertionError("network forbidden")))
        self.stack.enter_context(patch.object(snapshot, "datetime", CaptureClock))
        self.stack.enter_context(patch.object(fetch_indices.dt, "datetime", CaptureClock))
        self.stack.enter_context(patch.object(snapshot.time, "strftime", return_value="2026-09-12 10:00"))
        self.tick = {"ts": int(FRIDAY.timestamp()), "price": PRICE, "volume": 10}
        self.snapshot_tick = self.stack.enter_context(patch.object(snapshot, "intraday_last", return_value=self.tick))
        self.index_tick = self.stack.enter_context(patch.object(fetch_indices, "intraday_last", return_value=self.tick))
        self.rows = {f"S{i:03d}": {"open": 10, "high": 12, "low": 9, "current": 11, "volume": 100}
                     for i in range(100)}
        self.watch = self.stack.enter_context(patch.object(snapshot, "market_watch", return_value=self.rows))
        self.index_get = self.stack.enter_context(patch.object(fetch_indices, "_get", return_value=SimpleNamespace(
            text=f"<table><tr><th>Index</th><th>High</th><th>Low</th><th>Current</th><th>Change</th><th>% Change</th></tr>"
                 f"<tr><td>KSE100</td><td>0</td><td>0</td><td>{PRICE}</td><td>246.75</td><td>0.20</td></tr>"
                 "<tr><td>KMI30</td><td>0</td><td>0</td><td>222.5</td><td>-2.5</td><td>-1.11</td></tr></table>")))
        self.put("universe.json", {"symbols": {s: {} for s in self.rows}})
        self.put("live.json", {"sentinel": "prior live"})
        self.put("ohlc_daily/2026-09-10.json", {"OLD": {"current": 8}})
        self.put("ohlc_daily/2026-09-11.json", {"UNRELATED": {"current": 7}})
        self.history = {"2026-09-09": {"KSE100": 111}, "2026-09-10": {"KSE100": 112},
                        "2026-09-11": {"KSE100": 113, "KMI30": 114}}
        self.put("indices.json", {"history": self.history, "live": {"KSE100": 113}})

    def put(self, name, value):
        path = self.state / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=3) + "\n", encoding="utf-8")

    def read(self, name):
        return json.loads((self.state / name).read_text(encoding="utf-8"))

    def all_bytes(self):
        return {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}

    def rejected(self, module):
        before = self.all_bytes()
        with patch.object(module, "save_json", wraps=module.save_json) as save:
            try:
                module.main()
            except SystemExit as exc:
                self.assertEqual(exc.code, 0)
            except (ValueError, TypeError):
                # Current snapshot reports rejected captures with ValueError; a malformed
                # raw timestamp can raise TypeError. Neither may reach the write boundary.
                pass
            save.assert_not_called()
        self.assertEqual(self.all_bytes(), before)

    def test_snapshot_friday_source_captured_saturday_at_100_rows(self):
        old = (self.state / "ohlc_daily/2026-09-10.json").read_bytes()
        snapshot.main()
        live = self.read("live.json")
        self.assertEqual(live["session_date"], "2026-09-11")
        self.assertEqual(datetime.fromisoformat(live["source_at"]), FRIDAY)
        self.assertEqual(datetime.fromisoformat(live["captured_at"]), SATURDAY)
        self.assertEqual(len(live["tickers"]), 100)
        friday = self.read("ohlc_daily/2026-09-11.json")
        self.assertEqual(friday["S000"]["current"], 11)
        self.assertEqual(friday["UNRELATED"], {"current": 7})
        self.assertFalse((self.state / "ohlc_daily/2026-09-12.json").exists())
        self.assertEqual((self.state / "ohlc_daily/2026-09-10.json").read_bytes(), old)

    def test_snapshot_99_matched_rows_preserve_bytes_even_with_extra_board_rows(self):
        self.watch.return_value = {s: r for s, r in self.rows.items() if s != "S099"}
        self.watch.return_value.update({f"OUTSIDE{i}": self.rows["S000"] for i in range(5)})
        self.rejected(snapshot)

    def test_snapshot_ambiguous_board_preserves_bytes(self):
        self.watch.side_effect = ValueError("ambiguous DPS security identity")
        self.rejected(snapshot)

    def test_snapshot_missing_ambiguous_and_future_clock_preserve_bytes(self):
        for tick in (None, {**self.tick, "ts": "2026-09-11 16:35"},
                     {**self.tick, "ts": int((SATURDAY + timedelta(seconds=1)).timestamp())}):
            with self.subTest(tick=tick):
                self.snapshot_tick.return_value = tick
                self.rejected(snapshot)

    def test_snapshot_timestamp_provider_rejection_preserves_bytes(self):
        self.snapshot_tick.side_effect = ValueError("ambiguous exchange timestamp")
        self.rejected(snapshot)

    def test_snapshot_traded_rows_reject_invalid_current_without_writes(self):
        for bad in (None, 0, -1, float("nan"), float("inf"), -float("inf"), True, "1"):
            with self.subTest(current=bad):
                self.watch.return_value = {
                    symbol: {**row, "current": bad} for symbol, row in self.rows.items()
                }
                self.rejected(snapshot)

    def test_snapshot_accepts_valid_source_price_one(self):
        self.watch.return_value = {
            symbol: {**row, "current": 1} for symbol, row in self.rows.items()
        }
        snapshot.main()
        live = self.read("live.json")
        self.assertEqual({row["current"] for row in live["tickers"].values()}, {1})

    def test_snapshot_canonical_collision_preserves_bytes(self):
        universe = {"symbols": {**{symbol: {} for symbol in self.rows}, "KEL": {}}}
        self.put("universe.json", universe)
        watch = dict(self.rows)
        watch["KEL"] = self.rows["S000"]
        watch["KELXD"] = self.rows["S001"]
        self.watch.return_value = watch
        self.rejected(snapshot)

    def test_snapshot_source_destination_ambiguity_preserves_bytes(self):
        universe = {"symbols": {**{symbol: {} for symbol in self.rows}, "KEL": {}, "KELXD": {}}}
        self.put("universe.json", universe)
        watch = dict(self.rows)
        watch["KELXD"] = self.rows["S000"]
        self.watch.return_value = watch
        self.rejected(snapshot)

    def test_indices_friday_latest_is_corrected_on_saturday_retaining_older_records(self):
        fetch_indices.main()
        data = self.read("indices.json")
        self.assertEqual(data["live_session_date"], "2026-09-11")
        self.assertEqual(datetime.fromisoformat(data["source_at"]), FRIDAY)
        self.assertEqual(datetime.fromisoformat(data["live_at"]), SATURDAY)
        self.assertEqual(data["history"]["2026-09-11"], {"KSE100": PRICE, "KMI30": 222.5})
        self.assertEqual(data["daily_change"]["KSE100"]["current"], PRICE)
        self.assertEqual(data["daily_change"]["KSE100"]["change"], 246.75)
        self.assertEqual(data["daily_change"]["KSE100"]["derived_previous_close"], PRICE - 246.75)
        self.assertEqual(data["daily_change"]["KSE100"]["session_date"], "2026-09-11")
        for day in ("2026-09-09", "2026-09-10"):
            self.assertEqual(data["history"][day], self.history[day])
        self.assertNotIn("2026-09-12", data["history"])
        before = self.all_bytes()
        fetch_indices.main()
        self.assertEqual(self.all_bytes(), before, "same capture must be idempotent")

    def test_indices_missing_friday_is_seeded_in_friday_bucket(self):
        self.put("indices.json", {"history": {"2026-09-10": {"KSE100": 112}}, "live": {}})
        fetch_indices.main()
        history = self.read("indices.json")["history"]
        self.assertEqual(set(history), {"2026-09-10", "2026-09-11"})
        self.assertEqual(history["2026-09-11"]["KSE100"], PRICE)

    def test_indices_source_older_than_latest_preserves_all_bytes(self):
        self.index_tick.return_value = {**self.tick, "ts": int((FRIDAY - timedelta(days=1)).timestamp())}
        self.rejected(fetch_indices)

    def test_indices_source_older_same_session_preserves_all_bytes(self):
        fetch_indices.main()
        self.index_tick.return_value = {**self.tick, "ts": int((FRIDAY - timedelta(minutes=1)).timestamp())}
        self.rejected(fetch_indices)

    def test_indices_missing_ambiguous_and_future_clock_preserve_bytes(self):
        for tick in (None, {**self.tick, "ts": "2026-09-11 16:35"},
                     {**self.tick, "ts": int((SATURDAY + timedelta(seconds=1)).timestamp())}):
            with self.subTest(tick=tick):
                self.index_tick.return_value = tick
                self.rejected(fetch_indices)

    def test_indices_timestamp_provider_rejection_preserves_bytes(self):
        self.index_tick.side_effect = ValueError("ambiguous exchange timestamp")
        self.rejected(fetch_indices)

    def test_indices_board_clock_price_mismatch_preserves_bytes(self):
        self.index_tick.return_value = {**self.tick, "price": PRICE + 1}
        self.rejected(fetch_indices)

    def test_indices_header_drift_preserves_bytes(self):
        self.index_get.return_value.text = (
            f"<table><tr><th>Index</th><th>High</th><th>Low</th><th>Last</th><th>Change</th><th>% Change</th></tr>"
            f"<tr><td>KSE100</td><td>0</td><td>0</td><td>{PRICE}</td><td>1</td><td>0.1</td></tr></table>")
        self.rejected(fetch_indices)

    def test_daily_change_validator_allows_absent_and_empty_metadata(self):
        self.assertEqual(fetch_indices.validate_daily_changes({"live": {}}), [])
        self.assertEqual(fetch_indices.validate_daily_changes({"daily_change": {}, "live": {}}), [])

    def test_daily_change_validator_checks_coherence_and_source_session(self):
        base = {
            "live": {"KSE100": 100.0},
            "source_at": "2026-09-10T19:00:00+00:00",  # 2026-09-11 in PKT
            "live_session_date": "2026-09-11",
            "daily_change": {"KSE100": {
                "current": 100.0, "change": 0.0, "percent": 0.0,
                "derived_previous_close": 100.0,
                "source_at": "2026-09-10T19:00:00+00:00", "session_date": "2026-09-11",
            }},
        }
        self.assertEqual(fetch_indices.validate_daily_changes(base), [])
        missing = json.loads(json.dumps(base))
        del missing["daily_change"]["KSE100"]["percent"]
        self.assertTrue(fetch_indices.validate_daily_changes(missing))
        for field, value in (("current", 0), ("change", "bad"), ("percent", float("nan")),
                             ("derived_previous_close", -1), ("source_at", "wrong"),
                             ("session_date", "2026-09-10"), ("percent", 1.0)):
            with self.subTest(field=field):
                bad = json.loads(json.dumps(base, allow_nan=True))
                bad["daily_change"]["KSE100"][field] = value
                self.assertTrue(fetch_indices.validate_daily_changes(bad))

    def test_health_counts_missing_histories_against_full_psx_universe(self):
        today = SATURDAY.date().isoformat()
        self.put("universe.json", {"updated": today,
                                 "symbols": {s: {"market": "PSX"} for s in self.rows}})
        cached = list(self.rows)[:50]
        for symbol in cached:
            self.put(f"history/{symbol}.json", [{"date": FRIDAY.date().isoformat(), "close": 11}])
        self.put("coverage.json", {"n_with_history": 50, "n_universe": 100,
                                   "bars": {s: 1 for s in cached}})
        self.put("calendar.json", {"session_times_updated": today})
        post_close = {"required": False, "status": "not_required", "problems": []}
        with patch.object(data_health, "date") as clock, \
                patch.object(data_health, "intraday_last", return_value=None), \
                patch.object(data_health, "evaluate_post_close", return_value=post_close), \
                patch.object(data_health.time, "strftime",
                             side_effect=lambda fmt, value=SATURDAY.timetuple(): strftime(fmt, value)):
            # Honour explicit tuples for strptime's locale setup; default to the fixture clock.
            clock.today.return_value = SATURDAY.date()
            with self.assertRaises(SystemExit) as exited:
                data_health.main()
            self.assertEqual(exited.exception.code, 0)
        health = self.read("health.json")
        self.assertEqual(health["checked"], "2026-09-12 10:00")
        self.assertEqual(health["history_symbols"], 50)
        self.assertEqual(health["universe_symbols"], 100)
        self.assertEqual(health["history_coverage_fraction"], 0.5)
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["problems"], ["history coverage 50%"])

    def test_intraday_friday_points_captured_saturday_keep_friday_pkt_date(self):
        self.put("universe.json", {"symbols": {"S000": {"market": "PSX", "tier": "core"}}})
        # Friday just after PKT midnight is Thursday in UTC: catches UTC-date bucketing too.
        source = FRIDAY.replace(hour=0, minute=3)
        points = [{"t": int((source - timedelta(minutes=3 - i)).timestamp()), "p": 10 + i, "v": 100 + i}
                  for i in range(4)]
        with patch.object(fetch_intraday, "datetime", CaptureClock), \
                patch.object(fetch_intraday, "market_symbols", return_value=["S000"]) as markets, \
                patch.object(fetch_intraday, "fetch", return_value=points) as fetch, \
                patch.object(fetch_intraday.requests, "Session") as session, \
                patch.object(fetch_intraday.time, "sleep"):
            fetch_intraday.main()
            markets.assert_called_once_with("PSX", ["S000"])
            fetch.assert_called_once_with("S000", session.return_value)
        saved = self.read("intraday/S000.json")
        self.assertEqual(saved["date"], "2026-09-11")
        self.assertEqual(saved["points"], points)
        source_at = datetime.fromisoformat(saved["source_at"])
        captured_at = datetime.fromisoformat(saved["captured_at"])
        self.assertEqual(source_at, source)
        self.assertEqual(source_at.utcoffset(), timedelta(hours=5))
        self.assertEqual(captured_at, SATURDAY)
        self.assertEqual(captured_at.utcoffset(), timedelta(0))
        self.assertEqual(captured_at.date().isoformat(), "2026-09-12")


if __name__ == "__main__":
    unittest.main(verbosity=1)
