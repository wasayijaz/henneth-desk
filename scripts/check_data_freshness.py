"""Offline checks for stale-history classification and full-universe health gating."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import data_health


NOW = datetime(2026, 9, 12, 17, 5, 4, tzinfo=timezone.utc)
SESSION = "2026-09-11"
POST_CLOSE_OK = {"required": True, "status": "ok", "session_date": SESSION}


def write_json(root: Path, name: str, value: object) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def base_state(root: Path) -> None:
    symbols = {s: {"market": "PSX"} for s in ("INACTIVE", "ACTIVE", "FRESH", "MISSING")}
    write_json(root, "universe.json", {"updated": "2026-09-12", "symbols": symbols})
    write_json(root, "live.json", {
        "source_at": "2026-09-11T16:50:00+05:00",
        "session_date": SESSION,
        "tickers": {"INACTIVE": {"volume": 0}, "ACTIVE": {"volume": 100}},
    })
    write_json(root, "history/INACTIVE.json", [{"date": "2026-08-01", "close": 10, "volume": 0}])
    write_json(root, "history/ACTIVE.json", [{"date": "2026-08-01", "close": 10, "volume": 0}])
    write_json(root, "history/FRESH.json", [{"date": SESSION, "close": 10, "volume": 100}])
    write_json(root, "history/MISSING.json", [{"date": "2024-09-26", "close": 10, "volume": 0}])
    write_json(root, "coverage.json", {
        "n_universe": 4,
        "n_with_history": 4,
        "bars": {s: 1 for s in ("INACTIVE", "ACTIVE", "FRESH", "MISSING")},
    })
    write_json(root, "history_meta.json", {
        "completed_at": "2026-09-12T17:05:04Z",
        "skipped_deadline": 0,
        "ok": 4,
        "attempted": 4,
        "processed": 4,
        "failed": [],
        "with_history": 4,
        "last_attempt": {s: "2026-09-12T22:05:00+05:00" for s in symbols},
    })


class DataFreshnessChecks(unittest.TestCase):
    def test_attempt_offsets_and_existing_duration_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_state(root)
            universe = json.loads((root / "universe.json").read_text())
            meta = json.loads((root / "history_meta.json").read_text())
            # Same instant on UTC and PKT hosts, including a full 20-minute sweep.
            for stamp in ("2026-09-12T17:05:00Z", "2026-09-12T22:05:00+05:00",
                          "2026-09-12T16:45:04+00:00", "2026-09-12T21:45:04+05:00"):
                with self.subTest(stamp=stamp):
                    meta["last_attempt"] = {s: stamp for s in universe["symbols"]}
                    write_json(root, "history_meta.json", meta)
                    proof = data_health._history_refresh_proof(root, universe, POST_CLOSE_OK, NOW)
                    self.assertTrue(proof["ok"], proof["reason"])
            # Different spellings of the same minute are one run, not separate clocks.
            meta["last_attempt"] = dict(zip(universe["symbols"], (
                "2026-09-12T17:05:00Z", "2026-09-12T22:05:00+05:00",
                "2026-09-13T02:05:00+09:00", "2026-09-12T12:05:00-05:00")))
            write_json(root, "history_meta.json", meta)
            self.assertTrue(data_health._history_refresh_proof(root, universe, POST_CLOSE_OK, NOW)["ok"])
            # No timezone repair by inference, even for the previously observed local stamp.
            for stamp in ("2026-09-12 22:05", "2026-09-12 17:05", None, "bad",
                          "2026-09-12T22:05:00Z", "2026-09-12T16:34:00Z"):
                with self.subTest(invalid_stamp=stamp):
                    meta["last_attempt"] = {s: stamp for s in universe["symbols"]}
                    write_json(root, "history_meta.json", meta)
                    result = data_health.assess_history_freshness(root, universe, POST_CLOSE_OK, NOW)
                    self.assertTrue(any("proof unavailable" in p for p in result["problems"]))
                    self.assertFalse(result["advisories"])

    def test_successful_old_inactive_is_advisory_with_date(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_state(root)
            result = data_health.assess_history_freshness(root, json.loads((root / "universe.json").read_text()), POST_CLOSE_OK, NOW)
            self.assertNotIn("INACTIVE=2026-08-01", " ".join(result["problems"]))
            self.assertIn("INACTIVE=2026-08-01", " ".join(result["advisories"]))
            self.assertIn("no suspension inferred", result["advisories"][0])

    def test_active_positive_volume_with_old_history_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_state(root)
            result = data_health.assess_history_freshness(root, json.loads((root / "universe.json").read_text()), POST_CLOSE_OK, NOW)
            self.assertTrue(any("ACTIVE=2026-08-01" in p for p in result["problems"]))
            self.assertNotIn("; ACTIVE=2026-08-01", " ".join(result["advisories"]))

    def test_failed_or_unproven_refresh_never_downgrades_old_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_state(root)
            meta = json.loads((root / "history_meta.json").read_text())
            meta.update({"ok": 3, "failed": [{"symbol": "INACTIVE", "err": "provider outage"}]})
            write_json(root, "history_meta.json", meta)
            result = data_health.assess_history_freshness(root, json.loads((root / "universe.json").read_text()), POST_CLOSE_OK, NOW)
            self.assertTrue(any("history refresh failed" in p for p in result["problems"]))
            self.assertTrue(any("INACTIVE=2026-08-01" in p for p in result["problems"]))
            self.assertNotIn("INACTIVE=2026-08-01", " ".join(result["advisories"]))

            meta = json.loads((root / "history_meta.json").read_text())
            meta["completed_at"] = None
            meta["failed"] = []
            meta["ok"] = 4
            meta["with_history"] = 3
            write_json(root, "history_meta.json", meta)
            result = data_health.assess_history_freshness(root, json.loads((root / "universe.json").read_text()), POST_CLOSE_OK, NOW)
            self.assertTrue(any("proof unavailable" in p for p in result["problems"]))
            self.assertFalse(result["advisories"])

            meta["completed_at"] = "2026-09-12T17:05:04Z"
            meta["with_history"] = 4
            write_json(root, "history_meta.json", meta)
            live = json.loads((root / "live.json").read_text())
            live["source_at"] = None
            write_json(root, "live.json", live)
            result = data_health.assess_history_freshness(root, json.loads((root / "universe.json").read_text()), POST_CLOSE_OK, NOW)
            self.assertTrue(any("proof unavailable" in p for p in result["problems"]))
            self.assertFalse(result["advisories"])

    def test_missing_history_does_not_shrink_denominators(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_state(root)
            (root / "history/MISSING.json").unlink()
            coverage = json.loads((root / "coverage.json").read_text())
            coverage["n_with_history"] = 3
            coverage["bars"].pop("MISSING")
            write_json(root, "coverage.json", coverage)
            meta = json.loads((root / "history_meta.json").read_text())
            meta.update({"ok": 3, "failed": [{"symbol": "MISSING", "err": "no history"}], "with_history": 3})
            write_json(root, "history_meta.json", meta)
            result = data_health.assess_history_freshness(root, json.loads((root / "universe.json").read_text()), POST_CLOSE_OK, NOW)
            self.assertIn("history coverage 75%", result["problems"])
            self.assertEqual(result["stale_fleet_fraction"], 0.5)
            self.assertEqual(result["stale_fleet"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
