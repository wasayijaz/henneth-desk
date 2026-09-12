"""Capture the real PSX index levels, daily, and keep them.

Two things needed this and neither could be fixed with what the desk had:
  * MARKET-RELATIVE CLAIMS. The astro readings claim a name "underperforms the KSE100". Scoring
    that needs the index level at the claim and at resolution. Without it, room_score would grade
    a market-relative claim on the ABSOLUTE price move — marking a stock that fell 2% while the
    market fell 8% as a HIT for "underperforms", when it plainly outperformed. Silent, and it would
    have discredited the whole scorecard.
  * NO INDEX HISTORY EXISTS. Yahoo's ^KSE is monthly and stops in 2021; stooq has nothing; DPS
    publishes indices live-only. So astro_backtest had to rebuild KSE100/KMI30 from constituents
    and label them proxies. Nobody can hand us the past — but from today we can simply keep it.
    In a year this file IS the index history the desk currently lacks.

Source: dps.psx.com.pk/indices (PSX's own live board). One row per PKT trading date, never rewrites
a PAST date's row. Today's own row gets one correction at/after that day's PSX close (so it holds
the true close, not whatever was live on the day's first run) — still never touched again after.
Network failure -> keep what we have, exit 0.
Writes state/indices.json.
"""
import datetime as dt
import json
import math
import pathlib
import sys
import time

from psx_data import _get, _parse_table_rows, save_json, intraday_last

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
OUT = STATE / "indices.json"
PKT = dt.timezone(dt.timedelta(hours=5))
# KSE100/KMI30/KSE30 are the headline benchmarks. The two ALL-SHARE indices matter more for this
# desk than their profile suggests: the universe runs well past the KSE100 constituents, so a
# claim about a mid-cap graded against the KSE100 is graded against an index it isn't in.
# ALLSHR covers every listed company; KMIALLSHR is its Shariah-compliant counterpart. Keep every
# official PSX index row as well, so the data layer does not silently omit valid board indices.

BOARD_ROUNDING_TOLERANCE = 0.011


def _finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _valid_source_at(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _valid_session_date(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def validate_daily_changes(indices):
    """Validate optional PSX board daily-change metadata.

    An absent field means the daily move is unavailable and is allowed. Once present, every
    entry must be source/session-consistent and internally coherent; callers must not fall back
    to historical subtraction when this contract fails.
    """
    if not isinstance(indices, dict):
        return ["indices must be an object"]
    if "daily_change" not in indices:
        return []
    daily = indices["daily_change"]
    if not isinstance(daily, dict):
        return ["daily_change must be an object"]
    if not daily:
        return []

    live = indices.get("live")
    source_at = indices.get("source_at")
    session = indices.get("live_session_date")
    parsed_source = _valid_source_at(source_at)
    parsed_session = _valid_session_date(session)
    errors = []
    if parsed_source is None:
        errors.append("source_at is missing or timezone-naive")
    if parsed_session is None:
        errors.append("live_session_date is missing or invalid")
    elif parsed_source is not None and parsed_source.astimezone(PKT).date() != parsed_session:
        errors.append("source_at and live_session_date disagree")

    required = ("current", "change", "percent", "derived_previous_close", "source_at", "session_date")
    for name, entry in daily.items():
        label = f"daily_change[{name!r}]"
        if not isinstance(name, str) or not name.strip():
            errors.append("daily_change has an invalid index key")
            continue
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in required:
            if field not in entry:
                errors.append(f"{label}.{field} is missing")

        current = entry.get("current")
        change = entry.get("change")
        percent = entry.get("percent")
        previous = entry.get("derived_previous_close")
        if not _finite_number(current) or current <= 0:
            errors.append(f"{label}.current must be finite and positive")
        if not _finite_number(change):
            errors.append(f"{label}.change must be finite numeric")
        if not _finite_number(percent):
            errors.append(f"{label}.percent must be finite numeric")
        if not _finite_number(previous) or previous <= 0:
            errors.append(f"{label}.derived_previous_close must be finite and positive")

        live_current = live.get(name) if isinstance(live, dict) else None
        if not _finite_number(live_current) or live_current <= 0:
            errors.append(f"{label}.current has no positive live counterpart")
        elif _finite_number(current) and abs(current - live_current) > BOARD_ROUNDING_TOLERANCE:
            errors.append(f"{label}.current disagrees with live")

        if entry.get("source_at") != source_at:
            errors.append(f"{label}.source_at disagrees with source_at")
        if entry.get("session_date") != session:
            errors.append(f"{label}.session_date disagrees with live_session_date")

        if _finite_number(current) and _finite_number(change) and _finite_number(previous):
            if abs(previous - (current - change)) > BOARD_ROUNDING_TOLERANCE:
                errors.append(f"{label}.derived_previous_close is not current minus change")
        if _finite_number(change) and _finite_number(percent) and _finite_number(previous) and previous > 0:
            expected_percent = change / previous * 100
            if abs(percent - expected_percent) > BOARD_ROUNDING_TOLERANCE:
                errors.append(f"{label}.percent disagrees with change and derived previous close")
    return errors


def _board_columns(rows):
    for cells in rows:
        normalized = [" ".join(str(cell or "").strip().lower().split()) for cell in cells]
        if not normalized or normalized[0] != "index":
            continue
        aliases = {"name": "index", "current": "current", "change": "change", "percent": "% change"}
        if all(value in normalized for value in aliases.values()):
            return {key: normalized.index(value) for key, value in aliases.items()}
    raise ValueError("PSX index board headers missing or changed")


def _board_number(cells, position):
    if position >= len(cells):
        return None
    raw = str(cells[position] or "").strip().replace(",", "").replace("%", "")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def main():
    STATE.mkdir(exist_ok=True)
    data = {"history": {}, "live": {}}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
            data.setdefault("history", {})
            data.setdefault("live", {})
        except Exception:
            pass

    try:
        html = _get("/indices").text
        rows = _parse_table_rows(html)
        columns = _board_columns(rows)
        tick = intraday_last("KSE100")
        if not tick:
            raise ValueError("exchange session timestamp missing")
    except Exception as e:
        print(f"indices: fetch failed ({type(e).__name__}) — keeping {len(data['history'])} stored days")
        sys.exit(0)

    live = {}
    daily_change = {}
    for cells in rows:
        if len(cells) <= columns["current"]:
            continue
        raw_name = (cells[columns["name"]] or "").strip().upper()
        name = raw_name.split()[0]
        if not name or name == "INDEX":
            continue
        current = _board_number(cells, columns["current"])
        if current is None or current <= 0:
            continue
        live[name] = current
        change = _board_number(cells, columns["change"])
        percent = _board_number(cells, columns["percent"])
        previous = current - change if change is not None else None
        if (change is not None and percent is not None and previous is not None
                and previous > 0):
            daily_change[name] = {
                "current": current,
                "change": change,
                "percent": percent,
                "derived_previous_close": previous,
            }

    if "KSE100" not in live:
        print("indices: KSE100 not found in the DPS board — markup may have changed; keeping stored data")
        sys.exit(0)

    now_dt = dt.datetime.now(PKT)
    source_at = dt.datetime.fromtimestamp(tick["ts"], PKT)
    if source_at > now_dt or abs(live["KSE100"] - tick["price"]) > 0.01:
        print("indices: source clock/value inconsistent with board — preserving stored data")
        return
    today = source_at.date().isoformat()
    previous_source = _valid_source_at(data.get("source_at"))
    newest = max(data["history"], default=today)
    if today < newest or (previous_source is not None and source_at < previous_source):
        print("indices: source clock moved backwards — preserving stored data")
        return
    data["live"] = live
    data["source_at"] = source_at.isoformat()
    data["live_session_date"] = today
    data["daily_change"] = {
        name: {**entry, "source_at": data["source_at"], "session_date": today}
        for name, entry in daily_change.items()
    }
    # The post-close integrity gate compares this instant with the official close. Preserve the
    # offset so the value is unambiguous across machines and cannot be silently reinterpreted.
    data["live_at"] = now_dt.isoformat(timespec="minutes")
    # First capture of a date always seeds history[today], so an intraday read has something.
    # PSX closes Mon-Thu 15:30 PKT, Fri (later of the two sessions) 16:30 PKT — a run at/after
    # that time corrects the entry to the true close instead of leaving it frozen at whatever
    # level happened to be live on the day's first run. Post-close reruns just rewrite the same
    # settled value, so this stays idempotent and never looks past the current run's own fetch.
    close_time = dt.time(16, 30) if source_at.weekday() == 4 else dt.time(15, 30)
    after_close = source_at.time() >= close_time
    if today >= newest and (today not in data["history"] or after_close):
        data["history"][today] = live
    data["updated"] = time.strftime("%Y-%m-%d %H:%M")
    data["source"] = "https://dps.psx.com.pk/indices (PSX's own board), captured once per trading day"
    data["note"] = ("Append-only index levels. The desk started keeping these on the first run of "
                    "this script because no daily PSX index history is purchasable or scrapeable "
                    "anywhere the desk can reach — Yahoo's ^KSE is monthly and dead since 2021. "
                     "Everything before the earliest date here is unavailable, and the backtests say "
                     "so by labelling their constituent-rebuilt indices as proxies.")
    errors = validate_daily_changes(data)
    if errors:
        print(f"indices: invalid daily-change metadata — {'; '.join(errors)}; preserving stored data")
        return
    save_json(OUT, data)
    hist = sorted(data["history"])
    print(f"indices: {' · '.join(f'{k} {v:,.0f}' for k, v in live.items())}")
    print(f"  history: {len(hist)} day(s) kept ({hist[0]} -> {hist[-1]})")


if __name__ == "__main__":
    main()
