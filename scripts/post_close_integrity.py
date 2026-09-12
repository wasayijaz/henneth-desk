#!/usr/bin/env python3
"""Hard deterministic coherence gate for PSX post-close market data."""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from psx_data import STATE, load_json


PKT = ZoneInfo("Asia/Karachi")
MIN_TRADED_SYMBOLS = 100
MIN_SAME_DAY_FRACTION = 0.99
MAX_SESSION_LOOKBACK_DAYS = 31


def session_close(now: datetime) -> datetime:
    local = now.astimezone(PKT)
    close = time(16, 30) if local.weekday() == 4 else time(15, 30)
    return datetime.combine(local.date(), close, tzinfo=PKT)


def _parse_stamp(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # A missing offset is ambiguous. State timestamps must identify their instant;
        # never reinterpret a naive value as PKT at the gate.
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _check_stamp(problems: list[str], value: str | None, label: str, close: datetime, now: datetime) -> None:
    stamp = _parse_stamp(value)
    if stamp is None:
        problems.append(f"{label} has no timezone-aware timestamp")
        return
    if stamp > now:
        problems.append(f"{label} is in the future")
    if stamp < close:
        problems.append(f"{label} was recorded before the official session close")


def _target_close(now: datetime, holidays: set[str]) -> datetime | None:
    """Pre-close trading days need no gate; closed days check the last session."""
    local = now.astimezone(PKT)
    if local.weekday() < 5 and local.date().isoformat() not in holidays:
        close = session_close(local)
        return close if local >= close else None
    for offset in range(1, MAX_SESSION_LOOKBACK_DAYS + 1):
        candidate = local - timedelta(days=offset)
        if candidate.weekday() < 5 and candidate.date().isoformat() not in holidays:
            return session_close(candidate)
    raise ValueError(f"no trading session found within {MAX_SESSION_LOOKBACK_DAYS} days")


def _check_source(
    problems: list[str], value: object, session: object, label: str,
    close: datetime, now: datetime,
) -> None:
    _check_stamp(problems, value, f"{label} source", close, now)
    stamp = _parse_stamp(value)
    target = close.date().isoformat()
    if stamp is not None and stamp.astimezone(PKT).date().isoformat() != target:
        problems.append(f"{label} source date does not match target session {target}")
    if session != target:
        problems.append(f"{label} session date does not match target session {target}")


def _positive_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _positive_volume(row: object) -> bool:
    return isinstance(row, dict) and _positive_number(row.get("volume"))


def _valid_close(row: object) -> bool:
    return isinstance(row, dict) and _positive_number(row.get("close"))


def _check_history_refresh(
    problems: list[str], meta: object, universe_symbols: set[str], covered_symbols: set[str],
    close: datetime, now: datetime
) -> None:
    if not isinstance(meta, dict):
        problems.append("history_meta.json is missing or not an object")
        return

    _check_stamp(problems, meta.get("completed_at"), "history refresh completion", close, now)

    skipped = meta.get("skipped_deadline")
    if type(skipped) is not int or skipped != 0:
        problems.append("history refresh did not complete the full sweep")

    attempted = meta.get("attempted")
    processed = meta.get("processed")
    ok = meta.get("ok")
    failed = meta.get("failed")
    with_history = meta.get("with_history")
    if type(attempted) is not int or type(processed) is not int or type(ok) is not int:
        problems.append("history_meta.json lacks numeric attempted, processed, or ok counts")
    if not isinstance(failed, list):
        problems.append("history_meta.json lacks the finalized failed-results list")
    if type(with_history) is not int:
        problems.append("history_meta.json lacks the finalized with_history count")

    if type(attempted) is int and type(processed) is int and processed != attempted:
        problems.append(
            f"history refresh finalized only {processed}/{attempted} attempted symbols"
        )
    if type(ok) is int and isinstance(failed, list) and type(processed) is int:
        if ok + len(failed) != processed:
            problems.append(
                "history_meta.json result counts do not account for every processed symbol"
            )
        if ok <= 0:
            problems.append("history refresh has no successful fetches")
    if type(attempted) is int and attempted != len(universe_symbols):
        problems.append(
            f"history refresh attempted count {attempted} does not match actual universe "
            f"count {len(universe_symbols)}"
        )
    if type(processed) is int and processed != len(universe_symbols):
        problems.append(
            f"history refresh processed count {processed} does not match actual universe "
            f"count {len(universe_symbols)}"
        )
    if type(with_history) is int and with_history != len(covered_symbols):
        problems.append(
            f"history_meta.json with_history ({with_history}) does not match coverage.json "
            f"({len(covered_symbols)})"
        )
    attempts = meta.get("last_attempt")
    if not isinstance(attempts, dict):
        problems.append("history_meta.json lacks the finalized last_attempt identity map")
    elif set(attempts) != universe_symbols:
        problems.append(
            "history_meta.json last_attempt identities do not match the actual universe "
            f"({len(set(attempts))} vs {len(universe_symbols)})"
        )


def evaluate(root: Path = STATE, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(PKT)
    today = local.date().isoformat()
    calendar = load_json(root / "calendar.json", {})
    selection_problem = None
    try:
        close = _target_close(now, set(calendar.get("holidays") or []))
    except ValueError as exc:
        close = None
        selection_problem = str(exc)
    required = close is not None or selection_problem is not None
    target = close.date().isoformat() if close is not None else today
    result = {
        "required": required,
        "session_date": target if selection_problem is None else None,
        "checked_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "not_required" if not required else "fail",
        "problems": [],
        "traded_symbols": 0,
        "same_day_symbols": 0,
        "same_day_fraction": None,
        "missing_symbols": [],
    }
    if not required:
        return result
    if selection_problem is not None:
        result["problems"].append(selection_problem)
        return result

    indices = load_json(root / "indices.json", {})
    today_index = (indices.get("history") or {}).get(target) or {}
    if today_index.get("KSE100") is None:
        result["problems"].append("indices.json has no KSE100 close for this session")
    _check_stamp(result["problems"], indices.get("live_at"), "indices.json capture", close, now)
    _check_source(result["problems"], indices.get("source_at"),
                  indices.get("live_session_date"), "indices.json", close, now)
    index_capture = _parse_stamp(indices.get("live_at"))
    if index_capture is not None and index_capture <= now and index_capture.astimezone(PKT) >= close and (indices.get("live") or {}).get("KSE100") != today_index.get("KSE100"):
        result["problems"].append("indices.json session value does not match its post-close live capture")

    live = load_json(root / "live.json", {})
    if not isinstance(live, dict):
        result["problems"].append("live.json is not an object")
        live = {}
    _check_source(result["problems"], live.get("source_at"),
                  live.get("session_date"), "live.json", close, now)

    universe = load_json(root / "universe.json", {"symbols": {}}).get("symbols") or {}
    universe_symbols = set(universe)
    psx_symbols = {
        symbol for symbol, metadata in universe.items()
        if ((metadata or {}).get("market") or "PSX") == "PSX"
    }
    coverage = load_json(root / "coverage.json", {})
    covered = set((coverage.get("bars") or {}).keys())
    meta = load_json(root / "history_meta.json", {})
    _check_history_refresh(result["problems"], meta, universe_symbols, covered, close, now)
    ohlc = load_json(root / "ohlc_daily" / f"{target}.json", {})
    if not isinstance(ohlc, dict):
        result["problems"].append(f"ohlc_daily/{target}.json is not an object")
        ohlc = {}
    tickers = live.get("tickers")
    if not isinstance(tickers, dict):
        result["problems"].append("live.json tickers is not an object")
        tickers = {}
    live_declared = set(tickers) if isinstance(tickers, dict) else set()
    ohlc_declared = set(ohlc)
    live_unknown = live_declared - universe_symbols
    if live_unknown:
        result["problems"].append(
            "live.json declares identities outside universe.json: "
            + ", ".join(sorted(live_unknown)[:8])
        )
    live_non_psx = sorted(live_declared & (universe_symbols - psx_symbols))
    ohlc_non_psx = sorted(ohlc_declared & (universe_symbols - psx_symbols))
    ohlc_unknown = sorted(ohlc_declared - universe_symbols)
    result["snapshot_declared_symbols"] = len(live_declared)
    result["snapshot_matched_symbols"] = len(live_declared & universe_symbols)
    result["ignored_non_psx_symbols"] = sorted(
        set(live_non_psx) | set(ohlc_non_psx) | set(ohlc_unknown) | set(live_unknown)
    )
    live_traded = {
        symbol for symbol, row in tickers.items()
        if symbol in psx_symbols and _positive_volume(row)
    }
    ohlc_traded = {
        symbol for symbol, row in ohlc.items()
        if symbol in psx_symbols
        and _positive_volume(row)
    }
    traded = live_traded | ohlc_traded
    missing_ohlc = sorted(live_traded - ohlc_traded)
    missing_live = sorted(ohlc_traded - live_traded)
    if missing_ohlc:
        result["problems"].append(
            f"{len(missing_ohlc)} positive-volume live identities lack a positive-volume OHLC row: "
            + ", ".join(missing_ohlc[:8])
        )
    if missing_live:
        result["problems"].append(
            f"{len(missing_live)} positive-volume OHLC identities lack a positive-volume live snapshot: "
            + ", ".join(missing_live[:8])
        )
    current = set()
    invalid_history_close = []
    for symbol in traded:
        history = load_json(root / "history" / f"{symbol}.json", [])
        if (history and isinstance(history[-1], dict)
                and history[-1].get("date") == target):
            if _valid_close(history[-1]):
                current.add(symbol)
            else:
                invalid_history_close.append(symbol)
    if invalid_history_close:
        result["problems"].append(
            f"{len(invalid_history_close)} traded securities have no valid positive close on "
            f"{target}: " + ", ".join(sorted(invalid_history_close)[:8])
        )

    bad_prices = []
    for symbol in traded:
        row = tickers.get(symbol)
        price = row.get("current") if isinstance(row, dict) else None
        if not _positive_number(price):
            bad_prices.append(symbol)
    if bad_prices:
        result["problems"].append(
            f"{len(bad_prices)} traded securities lack a valid live snapshot price: "
            + ", ".join(sorted(bad_prices)[:8]))

    result["traded_symbols"] = len(traded)
    result["same_day_symbols"] = len(current)
    result["missing_symbols"] = sorted(traded - current)
    if traded:
        result["same_day_fraction"] = round(len(current) / len(traded), 4)
    if len(traded) < MIN_TRADED_SYMBOLS:
        result["problems"].append(
            f"only {len(traded)} traded counters identified; expected at least {MIN_TRADED_SYMBOLS}"
        )
    if result["missing_symbols"] and len(traded) >= MIN_TRADED_SYMBOLS:
        missing = result["missing_symbols"]
        if len(current) / len(traded) < MIN_SAME_DAY_FRACTION:
            result["problems"].append(
                f"only {len(current)}/{len(traded)} traded counters have the {target} valid EOD bar "
                f"(<{MIN_SAME_DAY_FRACTION:.0%}); missing: {', '.join(missing[:8])}"
            )
    if not result["problems"]:
        result["status"] = "ok"
    return result


def _self_test() -> None:
    thursday = datetime(2026, 9, 10, 10, 31, tzinfo=timezone.utc)
    friday_early = datetime(2026, 9, 11, 11, 0, tzinfo=timezone.utc)
    friday_late = datetime(2026, 9, 11, 11, 31, tzinfo=timezone.utc)
    assert session_close(thursday).hour == 15
    assert friday_early.astimezone(PKT) < session_close(friday_early)
    assert friday_late.astimezone(PKT) >= session_close(friday_late)
    assert _parse_stamp("2026-09-11T11:31:00Z").tzinfo is not None
    assert _parse_stamp("2026-09-11T16:31:00") is None
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "history").mkdir()
        (root / "ohlc_daily").mkdir()
        symbols = {f"T{i:03d}": {"market": "PSX"} for i in range(100)}
        def write(path: Path, payload: object) -> None:
            path.write_text(json.dumps(payload), encoding="utf-8")
        write(root / "calendar.json", {"holidays": []})
        write(root / "universe.json", {"symbols": symbols})
        write(root / "coverage.json", {"bars": {s: 2 for s in symbols}})
        write(root / "indices.json", {
            "live_at": "2026-09-11T16:31:00+05:00",
            "source_at": "2026-09-11T16:31:00+05:00",
            "live_session_date": "2026-09-11",
            "live": {"KSE100": 1.0},
            "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        write(root / "ohlc_daily" / "2026-09-11.json", {
            s: {"volume": 1} for s in symbols
        })
        for symbol in symbols:
            write(root / "history" / f"{symbol}.json", [{"date": "2026-09-11", "close": 1.0}])
        write(root / "live.json", {
            "source_at": "2026-09-11T16:31:00+05:00",
            "session_date": "2026-09-11",
            "tickers": {s: {"current": 1.0, "volume": 1} for s in symbols},
        })
        assert evaluate(root, friday_late)["status"] == "ok"
        valid_live = load_json(root / "live.json", {})
        for bad in (None, 0, -1, "1", True):
            invalid_live = json.loads(json.dumps(valid_live))
            invalid_live["tickers"]["T000"]["current"] = bad
            write(root / "live.json", invalid_live)
            assert evaluate(root, friday_late)["status"] == "fail"
        write(root / "live.json", valid_live)

        # Trading-day pre-close stays exempt, including Friday's later close.
        assert evaluate(root, friday_early)["status"] == "not_required"
        assert evaluate(root, datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc))["status"] == "not_required"

        # Capture may happen Saturday, but the market source must remain Friday.
        friday_indices = load_json(root / "indices.json", {})
        friday_live = load_json(root / "live.json", {})
        saturday = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
        write(root / "indices.json", {**friday_indices, "live_at": saturday.isoformat()})
        write(root / "live.json", {**friday_live, "captured_at": saturday.isoformat()})
        for check_now in (saturday, saturday + timedelta(days=1)):
            weekend = evaluate(root, check_now)
            assert weekend["required"] and weekend["status"] == "ok", weekend
            assert weekend["session_date"] == "2026-09-11"

        # Consecutive holidays must walk back over the weekend to Friday.
        write(root / "calendar.json", {"holidays": ["2026-09-14", "2026-09-15"]})
        holiday = evaluate(root, saturday + timedelta(days=3))
        assert holiday["status"] == "ok" and holiday["session_date"] == "2026-09-11", holiday
        write(root / "calendar.json", {"holidays": ["2026-09-11"]})
        friday_holiday = evaluate(root, saturday)
        assert friday_holiday["required"] and friday_holiday["session_date"] == "2026-09-10"
        assert friday_holiday["status"] == "fail"  # Friday evidence cannot stand in for Thursday.

        # A bounded search fails closed when the calendar has no recent session.
        write(root / "calendar.json", {"holidays": [
            (saturday - timedelta(days=offset)).date().isoformat()
            for offset in range(MAX_SESSION_LOOKBACK_DAYS + 1)
        ]})
        bounded = evaluate(root, saturday)
        assert bounded["required"] and bounded["status"] == "fail"
        assert bounded["session_date"] is None
        assert any("no trading session" in p for p in bounded["problems"])
        write(root / "calendar.json", {"holidays": []})
        write(root / "indices.json", friday_indices)
        write(root / "live.json", friday_live)

        # Fresh captures cannot rehabilitate stale, naive, missing, or future source clocks.
        for filename, original, session_key in (
            ("indices.json", friday_indices, "live_session_date"),
            ("live.json", friday_live, "session_date"),
        ):
            for invalid_source in (None, "2026-09-10T16:31:00+05:00",
                                   "2026-09-11T16:29:59+05:00",
                                   "2026-09-11T16:31:00", "2026-09-11T16:32:00+05:00"):
                write(root / filename, {**original, "source_at": invalid_source})
                rejected = evaluate(root, friday_late)
                assert rejected["status"] == "fail", (filename, invalid_source, rejected)
                assert any(f"{filename} source" in p for p in rejected["problems"])
            # Saturday is in the past at evaluation, but is not the market session.
            write(root / filename, {**original, "source_at": saturday.isoformat()})
            wrong_date = evaluate(root, saturday + timedelta(hours=1))
            assert any(f"{filename} source date" in p for p in wrong_date["problems"])
            write(root / filename, {**original, session_key: "2026-09-10"})
            mismatch = evaluate(root, friday_late)
            assert any(f"{filename} session date" in p for p in mismatch["problems"])
            write(root / filename, original)
        assert evaluate(root, friday_late)["status"] == "ok"

        # A positive PSX trade remains in the denominator even when coverage omits it.
        coverage = {s: 2 for s in symbols}
        coverage.pop("T000")
        write(root / "coverage.json", {"bars": coverage})
        write(root / "history" / "T000.json", [])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 99,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        missing_coverage = evaluate(root, friday_late)
        assert missing_coverage["traded_symbols"] == 100
        assert missing_coverage["same_day_symbols"] == 99
        assert missing_coverage["status"] == "ok"
        assert missing_coverage["missing_symbols"] == ["T000"]
        write(root / "coverage.json", {"bars": {s: 2 for s in symbols}})
        write(root / "history" / "T000.json", [{"date": "2026-09-11", "close": 1.0}])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })

        # A matching date alone is not a valid close; bad numeric close values fail closed.
        write(root / "history" / "T000.json", [{"date": "2026-09-11"}])
        date_only = evaluate(root, friday_late)
        assert date_only["status"] == "fail"
        assert date_only["missing_symbols"] == ["T000"]
        assert any("no valid positive close" in p for p in date_only["problems"])
        write(root / "history" / "T000.json", [{"date": "2026-09-11", "close": 1.0}])
        for bad_close in (0, -1, "1", True, float("nan"), float("inf")):
            write(root / "history" / "T000.json", [{"date": "2026-09-11", "close": bad_close}])
            bad_history = evaluate(root, friday_late)
            assert bad_history["status"] == "fail"
            assert bad_history["missing_symbols"] == ["T000"]
        write(root / "history" / "T000.json", [{"date": "2026-09-11", "close": 1.0}])

        # A positive-volume live identity must have a positive-volume OHLC row.
        ohlc = load_json(root / "ohlc_daily" / "2026-09-11.json", {})
        del ohlc["T000"]
        write(root / "ohlc_daily" / "2026-09-11.json", ohlc)
        missing_ohlc = evaluate(root, friday_late)
        assert missing_ohlc["status"] == "fail"
        assert any("lack a positive-volume OHLC row" in p for p in missing_ohlc["problems"])
        write(root / "ohlc_daily" / "2026-09-11.json", {s: {"volume": 1} for s in symbols})

        # A source identity outside the actual universe is reported, never added to PSX counts.
        outside_live = json.loads(json.dumps(friday_live))
        outside_live["tickers"]["ETF"] = {"current": 1.0, "volume": 1}
        write(root / "live.json", outside_live)
        outside = evaluate(root, friday_late)
        assert outside["traded_symbols"] == 100
        assert outside["snapshot_declared_symbols"] == 101
        assert outside["snapshot_matched_symbols"] == 100
        assert "ETF" in outside["ignored_non_psx_symbols"]
        assert any("outside universe.json" in p for p in outside["problems"])
        write(root / "live.json", friday_live)

        # Non-positive-volume rows are not traded identities and must not inflate the denominator.
        negative_ohlc = load_json(root / "ohlc_daily" / "2026-09-11.json", {})
        negative_ohlc["T000"] = {"volume": -1}
        write(root / "ohlc_daily" / "2026-09-11.json", negative_ohlc)
        negative_live = json.loads(json.dumps(friday_live))
        negative_live["tickers"]["T000"]["volume"] = -1
        write(root / "live.json", negative_live)
        negative_volume = evaluate(root, friday_late)
        assert negative_volume["traded_symbols"] == 99
        assert "T000" not in negative_volume["missing_symbols"]
        write(root / "live.json", friday_live)
        write(root / "ohlc_daily" / "2026-09-11.json", {s: {"volume": 1} for s in symbols})

        # Self-reported counts cannot hide a partial run from the actual universe denominator.
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 99, "attempted": 99, "processed": 99,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        partial_attempt = evaluate(root, friday_late)
        assert partial_attempt["status"] == "fail"
        assert any("actual universe count 100" in p for p in partial_attempt["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })

        # Completion is a finalized result, not merely a post-close timestamp.
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 99,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        partial_history = evaluate(root, friday_late)
        assert partial_history["status"] == "fail"
        assert any("finalized only 99/100" in problem for problem in partial_history["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })

        # Naive completion stamps fail rather than being silently treated as PKT.
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T16:31:00", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        naive_history = evaluate(root, friday_late)
        assert naive_history["status"] == "fail"
        assert any("no timezone-aware timestamp" in problem for problem in naive_history["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })

        write(root / "indices.json", {
            "live_at": "2026-09-11T11:32:00Z",
            "source_at": "2026-09-11T16:31:00+05:00",
            "live_session_date": "2026-09-11",
            "live": {"KSE100": 1.0},
            "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        future_index = evaluate(root, friday_late)
        assert future_index["status"] == "fail"
        assert any("indices.json capture is in the future" in problem for problem in future_index["problems"])
        write(root / "indices.json", {
            "live_at": "2026-09-11T16:31:00+05:00",
            "source_at": "2026-09-11T16:31:00+05:00",
            "live_session_date": "2026-09-11",
            "live": {"KSE100": 1.0},
            "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:32:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        future_history = evaluate(root, friday_late)
        assert future_history["status"] == "fail"
        assert any("history refresh completion is in the future" in problem for problem in future_history["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        for symbol in list(symbols)[:2]:
            write(root / "history" / f"{symbol}.json", [{"date": "2026-09-10"}])
        assert evaluate(root, friday_late)["status"] == "fail"

    # 487/491 remains above the 99% failure threshold, but the four exceptions are explicit.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "history").mkdir()
        (root / "ohlc_daily").mkdir()
        symbols = {f"T{i:03d}": {"market": "PSX"} for i in range(491)}
        def write(path: Path, payload: object) -> None:
            path.write_text(json.dumps(payload), encoding="utf-8")
        write(root / "calendar.json", {"holidays": []})
        write(root / "universe.json", {"symbols": symbols})
        write(root / "coverage.json", {"bars": {s: 2 for s in symbols}})
        write(root / "indices.json", {
            "live_at": "2026-09-11T16:31:00+05:00",
            "source_at": "2026-09-11T16:31:00+05:00",
            "live_session_date": "2026-09-11",
            "live": {"KSE100": 1.0}, "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 491, "attempted": 491, "processed": 491,
            "failed": [], "with_history": 491,
            "last_attempt": {s: "2026-09-11 16:31" for s in symbols},
        })
        write(root / "ohlc_daily" / "2026-09-11.json", {s: {"volume": 1} for s in symbols})
        write(root / "live.json", {
            "source_at": "2026-09-11T16:31:00+05:00", "session_date": "2026-09-11",
            "tickers": {s: {"current": 1.0, "volume": 1} for s in symbols},
        })
        for symbol in list(symbols)[:487]:
            write(root / "history" / f"{symbol}.json", [{"date": "2026-09-11", "close": 1.0}])
        threshold = evaluate(root, friday_late)
        assert threshold["traded_symbols"] == 491
        assert threshold["same_day_symbols"] == 487
        assert threshold["status"] == "ok"
        assert threshold["missing_symbols"] == ["T487", "T488", "T489", "T490"]
    print("post-close integrity self-test: OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return
    result = evaluate()
    print(
        f"post-close integrity: {result['status']} — "
        f"{result['same_day_symbols']}/{result['traded_symbols']} traded counters current"
    )
    for problem in result["problems"]:
        print(f"  ! {problem}")
    if result.get("missing_symbols"):
        print("  missing exceptions: " + ", ".join(result["missing_symbols"]))
    raise SystemExit(1 if result["required"] and result["status"] != "ok" else 0)


if __name__ == "__main__":
    main()
