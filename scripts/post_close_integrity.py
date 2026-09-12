#!/usr/bin/env python3
"""Hard deterministic coherence gate for PSX post-close market data."""
from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
import json
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from psx_data import STATE, load_json


PKT = ZoneInfo("Asia/Karachi")
MIN_TRADED_SYMBOLS = 100
MIN_SAME_DAY_FRACTION = 0.99


def session_close(now: datetime) -> datetime:
    local = now.astimezone(PKT)
    close = time(16, 30) if local.weekday() == 4 else time(15, 30)
    return datetime.combine(local.date(), close, tzinfo=PKT)


def _parse_stamp(value: str | None) -> datetime | None:
    if not value:
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


def _positive_volume(row: object) -> bool:
    try:
        return float((row or {}).get("volume") or 0) > 0
    except (AttributeError, TypeError, ValueError):
        return False


def _check_history_refresh(
    problems: list[str], meta: object, covered_count: int, close: datetime, now: datetime
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
    if type(with_history) is int and with_history != covered_count:
        problems.append(
            f"history_meta.json with_history ({with_history}) does not match coverage.json "
            f"({covered_count})"
        )


def evaluate(root: Path = STATE, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(PKT)
    today = local.date().isoformat()
    calendar = load_json(root / "calendar.json", {})
    trading_day = local.weekday() < 5 and today not in set(calendar.get("holidays") or [])
    required = trading_day and local >= session_close(now)
    result = {
        "required": required,
        "session_date": today,
        "checked_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "not_required" if not required else "fail",
        "problems": [],
        "traded_symbols": 0,
        "same_day_symbols": 0,
        "same_day_fraction": None,
    }
    if not required:
        return result

    indices = load_json(root / "indices.json", {})
    today_index = (indices.get("history") or {}).get(today) or {}
    if today_index.get("KSE100") is None:
        result["problems"].append("indices.json has no KSE100 close for this session")
    close = session_close(now)
    _check_stamp(result["problems"], indices.get("live_at"), "indices.json capture", close, now)
    index_capture = _parse_stamp(indices.get("live_at"))
    if index_capture is not None and index_capture <= now and index_capture.astimezone(PKT) >= close and (indices.get("live") or {}).get("KSE100") != today_index.get("KSE100"):
        result["problems"].append("indices.json session value does not match its post-close live capture")

    universe = load_json(root / "universe.json", {"symbols": {}}).get("symbols") or {}
    coverage = load_json(root / "coverage.json", {})
    covered = set((coverage.get("bars") or {}).keys())
    meta = load_json(root / "history_meta.json", {})
    _check_history_refresh(result["problems"], meta, len(covered), close, now)
    ohlc = load_json(root / "ohlc_daily" / f"{today}.json", {})
    traded = {
        symbol for symbol, row in ohlc.items()
        if symbol in universe
        and ((universe.get(symbol) or {}).get("market") or "PSX") == "PSX"
        and _positive_volume(row)
    }
    current = set()
    for symbol in traded:
        history = load_json(root / "history" / f"{symbol}.json", [])
        if history and history[-1].get("date") == today:
            current.add(symbol)

    result["traded_symbols"] = len(traded)
    result["same_day_symbols"] = len(current)
    if traded:
        result["same_day_fraction"] = round(len(current) / len(traded), 4)
    if len(traded) < MIN_TRADED_SYMBOLS:
        result["problems"].append(
            f"only {len(traded)} traded counters identified; expected at least {MIN_TRADED_SYMBOLS}"
        )
    elif len(current) / len(traded) < MIN_SAME_DAY_FRACTION:
        missing = sorted(traded - current)
        result["problems"].append(
            f"only {len(current)}/{len(traded)} traded counters have today's EOD bar "
            f"(<{MIN_SAME_DAY_FRACTION:.0%}); e.g. {', '.join(missing[:8])}"
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
            "live": {"KSE100": 1.0},
            "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
        })
        write(root / "ohlc_daily" / "2026-09-11.json", {
            s: {"volume": 1} for s in symbols
        })
        for symbol in symbols:
            write(root / "history" / f"{symbol}.json", [{"date": "2026-09-11"}])
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
        })
        missing_coverage = evaluate(root, friday_late)
        assert missing_coverage["traded_symbols"] == 100
        assert missing_coverage["same_day_symbols"] == 99
        assert missing_coverage["status"] == "ok"
        write(root / "coverage.json", {"bars": {s: 2 for s in symbols}})
        write(root / "history" / "T000.json", [{"date": "2026-09-11"}])

        # Completion is a finalized result, not merely a post-close timestamp.
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 99,
            "failed": [], "with_history": 100,
        })
        partial_history = evaluate(root, friday_late)
        assert partial_history["status"] == "fail"
        assert any("finalized only 99/100" in problem for problem in partial_history["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
        })

        # Naive completion stamps fail rather than being silently treated as PKT.
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T16:31:00", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
        })
        naive_history = evaluate(root, friday_late)
        assert naive_history["status"] == "fail"
        assert any("no timezone-aware timestamp" in problem for problem in naive_history["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
        })

        write(root / "indices.json", {
            "live_at": "2026-09-11T11:32:00Z",
            "live": {"KSE100": 1.0},
            "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        future_index = evaluate(root, friday_late)
        assert future_index["status"] == "fail"
        assert any("indices.json capture is in the future" in problem for problem in future_index["problems"])
        write(root / "indices.json", {
            "live_at": "2026-09-11T16:31:00+05:00",
            "live": {"KSE100": 1.0},
            "history": {"2026-09-11": {"KSE100": 1.0}},
        })
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:32:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
        })
        future_history = evaluate(root, friday_late)
        assert future_history["status"] == "fail"
        assert any("history refresh completion is in the future" in problem for problem in future_history["problems"])
        write(root / "history_meta.json", {
            "completed_at": "2026-09-11T11:31:00Z", "skipped_deadline": 0,
            "ok": 100, "attempted": 100, "processed": 100,
            "failed": [], "with_history": 100,
        })
        for symbol in list(symbols)[:2]:
            write(root / "history" / f"{symbol}.json", [{"date": "2026-09-10"}])
        assert evaluate(root, friday_late)["status"] == "fail"
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
    raise SystemExit(1 if result["required"] and result["status"] != "ok" else 0)


if __name__ == "__main__":
    main()
