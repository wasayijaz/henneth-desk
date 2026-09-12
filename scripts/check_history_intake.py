"""Offline history-intake regression checks; all state writes use temporary directories."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import fetch_history as history


def bar(stamp="2026-09-11", **values):
    return {"date": stamp, "open": 4.12, "close": 4.18, "volume": 100, **values}


def check_storage(root):
    universe = {"symbols": {"TISL": {"tier": "listed"}, "CORE": {"tier": "core"}}}
    for symbol, count in (("TISL", 14), ("CORE", 1)):
        rows = [bar((date(2026, 8, 29) + timedelta(days=i)).isoformat())
                for i in range(count)]
        with patch.object(history, "eod_history", return_value=rows) as provider:
            deadline = time.monotonic() + 10
            assert history._fetch_one(symbol, universe, 3, "2026-01-01", deadline) == ("ok", None)
            provider.assert_called_once_with(symbol, deadline=deadline)
        assert history.load_json(root / "history" / f"{symbol}.json", None) == rows

    path = root / "history" / "TISL.json"
    old = [bar("2026-09-09"), bar("2026-09-10"), bar("2026-09-11")]
    history.save_json(path, old)
    original = path.read_bytes()
    bad = [[], None, {}, [None], [4], [bar(date=None)], [bar(date="2026-02-30")],
           [bar(date="20260911")], [bar(date="2026-09-11T00:00:00")],
           [bar(), bar()], list(reversed(old)), [bar(close="4.18")],
           [bar(volume=1.5)], [bar(volume=-1)], [bar(close=0)],
           [bar(close=-2)], [bar(open=-2)], [bar(volume=True)], [bar(close=False)]]
    for field in ("close", "open", "volume"):
        missing = bar()
        missing.pop(field)
        bad.append([missing])
        for value in (None, float("nan"), float("inf"), -float("inf")):
            bad.append([bar(**{field: value})])
    # Validate the full response: an invalid older bar must not disappear in cutoff filtering.
    bad.append([bar("2025-12-31", close=float("nan")), *old])
    for rows in bad:
        with patch.object(history, "eod_history", return_value=rows):
            status, _ = history._fetch_one("TISL", universe, 3, "2026-01-01")
        assert status == "fail", f"accepted invalid history: {rows!r}"
        assert path.read_bytes() == original, "bad feed changed cached history"

    partial = [old[:-1], old[1:], [old[0], old[-1]],
               [*old[1:], bar("2026-09-12")], [bar("2026-09-12")]]
    for rows in partial:
        with patch.object(history, "eod_history", return_value=rows):
            assert history._fetch_one("TISL", universe, 3, "2026-01-01")[0] == "fail"
        assert path.read_bytes() == original, "partial feed shrank/replaced old history"

    for error, expected in ((RuntimeError("provider outage"), "fail"),
                            (history.DeadlineExceeded("budget exhausted"), "skip")):
        with patch.object(history, "eod_history", side_effect=error):
            assert history._fetch_one("TISL", universe, 3, "2026-01-01")[0] == expected
        assert path.read_bytes() == original
    with patch.object(history, "eod_history") as provider:
        assert history._fetch_one("TISL", universe, 3, "2026-01-01", time.monotonic()-1)[0] == "skip"
        provider.assert_not_called()
    assert path.read_bytes() == original

    # Complete provider corrections may replace values while retaining dates; expiry at cutoff
    # is intentional trimming, not a partial-feed regression. Zero traded volume is valid.
    revised = [bar("2026-09-10", close=4.2, open=0), old[-1], bar("2026-09-12", volume=0)]
    with patch.object(history, "eod_history", return_value=revised):
        assert history._fetch_one("TISL", universe, 3, "2026-09-10") == ("ok", None)
    assert history.load_json(path, None) == revised
    with patch.object(history, "eod_history", return_value=[bar("2025-01-01")]):
        assert history._fetch_one("NEW", universe, 3, "2026-01-01")[0] == "fail"
    assert not (root / "history" / "NEW.json").exists()
    # Both provider routes share intake validation and old-history protection.
    foreign = {"symbols": {"TISL": {"market": "US", "tier": "listed"}}}
    with patch.object(history, "_yahoo_daily", return_value=[]):
        assert history._fetch_one("TISL", foreign, 3, "2026-01-01")[0] == "fail"
    assert history.load_json(path, None) == revised
    return len(bad)


def check_all_new_in_one_sweep(root):
    symbols = {f"NEW{i:03d}": {"tier": "listed"} for i in range(120)}
    symbols.update({"HASCOL": {"tier": "listed"}, "GCWLPRS": {"tier": "listed"},
                    "WAVESAPPR": {"tier": "listed"}, "RECENT_CORE": {"tier": "core"}})
    universe = {"symbols": symbols}
    todo, n_listed = history._pick(universe, {"RECENT_CORE": "2026-09-11 18:00"})
    assert len(todo) == len(set(todo)) == len(symbols)
    assert set(todo) == set(symbols) and n_listed == 123
    assert todo[-1] == "RECENT_CORE", "recent core ticker preempted never-attempted listed names"
    original = deepcopy(universe)
    with patch.object(history, "eod_history", return_value=[bar()]):
        deadline = time.monotonic() + 20
        results = history._collect_results(
            todo, lambda s: history._fetch_one(s, universe, 3, "2026-01-01", deadline), deadline,
        )
    assert len(results) == len(symbols)
    assert all(result == ("ok", None) for _, result in results)
    assert all((root / "history" / f"{s}.json").is_file() for s in symbols)
    assert universe == original, "intake changed source identities or metadata"


def check_attempt_order(root):
    attempts = {
        "BAD": "invalid", "NAIVE": "2099-01-01 00:00",
        "OLDER": "2026-09-12T22:00:00+05:00",
        "NEWER": "2026-09-12T18:00:00Z",
        "SAME": "2026-09-13T02:00:00+09:00",
    }
    universe = {"symbols": {s: {"tier": "listed"} for s in (*attempts, "NEVER")}}
    todo, _ = history._pick(universe, attempts)
    assert todo == ["BAD", "NEVER", "NAIVE", "OLDER", "SAME", "NEWER"], todo
    assert history._attempt_order(attempts["OLDER"]) == history._attempt_order(attempts["SAME"])
    assert attempts["NAIVE"] == "2099-01-01 00:00", "ordering rewrote legacy metadata"


def check_metadata(root):
    symbols = {s: {"tier": "listed"} for s in ("GOOD", "BAD", "SKIP", "QUEUED")}
    history.save_json(root / "universe.json", {"symbols": symbols})
    prior_attempts = {s: "2026-01-01 10:00" for s in symbols}
    history.save_json(root / "history_meta.json", {
        "last_attempt": prior_attempts, "probe_cursor": 90, "new_probe_per_run": 12,
    })
    cached = [bar(date.today().isoformat())]
    history.save_json(root / "history" / "BAD.json", cached)
    original = (root / "history" / "BAD.json").read_bytes()

    def provider(symbol, deadline=None):
        if symbol == "SKIP":
            raise history.DeadlineExceeded("simulated deadline")
        return [] if symbol == "BAD" else cached

    def collect(todo, worker, deadline):
        assert set(todo) == set(symbols)
        return [(s, worker(s)) for s in todo if s != "QUEUED"]

    with patch.object(history, "load_config", return_value={"backtest": {"history_years": 3}}), \
            patch.object(history, "eod_history", side_effect=provider), \
            patch.object(history, "_collect_results", side_effect=collect), \
            redirect_stdout(io.StringIO()):
        history.main()
    meta = history.load_json(root / "history_meta.json", None)
    coverage = history.load_json(root / "coverage.json", None)
    assert (meta["attempted"], meta["processed"], meta["ok"], meta["skipped_deadline"]) == (4, 2, 1, 2)
    assert [r["symbol"] for r in meta["failed"]] == ["BAD"]
    assert meta["last_attempt"]["SKIP"] == prior_attempts["SKIP"]
    assert meta["last_attempt"]["QUEUED"] == prior_attempts["QUEUED"]
    assert meta["last_attempt"]["GOOD"] != prior_attempts["GOOD"]
    assert meta["last_attempt"]["BAD"] != prior_attempts["BAD"]
    attempt = datetime.fromisoformat(meta["last_attempt"]["GOOD"].replace("Z", "+00:00"))
    assert attempt.utcoffset() == timedelta(0), "new attempt lacks explicit UTC offset"
    assert meta["last_attempt"]["GOOD"] == meta["last_attempt"]["BAD"]
    assert attempt <= datetime.fromisoformat(meta["completed_at"].replace("Z", "+00:00"))
    assert meta["completed_at"].endswith("Z")
    assert "probe_cursor" not in meta and "new_probe_per_run" not in meta
    assert coverage["bars"] == {"GOOD": 1, "BAD": 1}
    assert meta["with_history"] == coverage["n_with_history"] == 2
    assert (root / "history" / "BAD.json").read_bytes() == original
    assert "nonexistent" in coverage["note"] and "does not imply" in coverage["note"]


def main():
    with tempfile.TemporaryDirectory(prefix="history-intake-") as temp, \
            patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")):
        root = Path(temp)
        for name, check in (("storage", check_storage), ("sweep", check_all_new_in_one_sweep),
                            ("ordering", check_attempt_order)):
            state = root / name
            with patch.object(history, "STATE", state):
                check(state)
            print(f"history intake {name}: OK")
        # Simulate both host-local display clocks without changing the machine timezone.
        # Attempt/completion clocks must still explicitly request UTC, not use strftime.
        original_strftime = time.strftime
        for label, offset in (("UTC", 0), ("PKT", 5)):
            local_zone = timezone(timedelta(hours=offset))
            def local_strftime(fmt, *args):
                if fmt == "%Y-%m-%d %H:%M" and not args:
                    return datetime.now(local_zone).strftime(fmt)
                return original_strftime(fmt, *args)
            with patch.object(history, "STATE", root / label), \
                    patch.object(history.time, "strftime", side_effect=local_strftime):
                check_metadata(root / label)
            print(f"history intake {label} host metadata: OK")
    print("history intake: OK (short prices, invalid/partial retention, all-new sweep, honest metadata)")


if __name__ == "__main__":
    main()
