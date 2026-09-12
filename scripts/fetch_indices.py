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
import pathlib
import sys
import time

from psx_data import _get, _parse_table_rows, save_json

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
OUT = STATE / "indices.json"
PKT = dt.timezone(dt.timedelta(hours=5))
# KSE100/KMI30/KSE30 are the headline benchmarks. The two ALL-SHARE indices matter more for this
# desk than their profile suggests: the universe runs well past the KSE100 constituents, so a
# claim about a mid-cap graded against the KSE100 is graded against an index it isn't in.
# ALLSHR covers every listed company; KMIALLSHR is its Shariah-compliant counterpart. Keep every
# official PSX index row as well, so the data layer does not silently omit valid board indices.


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
    except Exception as e:
        print(f"indices: fetch failed ({type(e).__name__}) — keeping {len(data['history'])} stored days")
        sys.exit(0)

    live = {}
    for cells in rows:
        if len(cells) < 4:
            continue
        raw_name = (cells[0] or "").strip().upper()
        name = raw_name.split()[0]
        if not name or name == "INDEX":
            continue
        try:
            live[name] = float(str(cells[3]).replace(",", ""))
        except (ValueError, IndexError):
            continue

    if "KSE100" not in live:
        print("indices: KSE100 not found in the DPS board — markup may have changed; keeping stored data")
        sys.exit(0)

    now_dt = dt.datetime.now(PKT)
    today = now_dt.date().isoformat()
    data["live"] = live
    # The post-close integrity gate compares this instant with the official close. Preserve the
    # offset so the value is unambiguous across machines and cannot be silently reinterpreted.
    data["live_at"] = now_dt.isoformat(timespec="minutes")
    # First capture of a date always seeds history[today], so an intraday read has something.
    # PSX closes Mon-Thu 15:30 PKT, Fri (later of the two sessions) 16:30 PKT — a run at/after
    # that time corrects the entry to the true close instead of leaving it frozen at whatever
    # level happened to be live on the day's first run. Post-close reruns just rewrite the same
    # settled value, so this stays idempotent and never looks past the current run's own fetch.
    close_time = dt.time(16, 30) if now_dt.weekday() == 4 else dt.time(15, 30)
    after_close = now_dt.time() >= close_time
    if today not in data["history"] or after_close:
        data["history"][today] = live
    data["updated"] = time.strftime("%Y-%m-%d %H:%M")
    data["source"] = "https://dps.psx.com.pk/indices (PSX's own board), captured once per trading day"
    data["note"] = ("Append-only index levels. The desk started keeping these on the first run of "
                    "this script because no daily PSX index history is purchasable or scrapeable "
                    "anywhere the desk can reach — Yahoo's ^KSE is monthly and dead since 2021. "
                    "Everything before the earliest date here is unavailable, and the backtests say "
                    "so by labelling their constituent-rebuilt indices as proxies.")
    save_json(OUT, data)
    hist = sorted(data["history"])
    print(f"indices: {' · '.join(f'{k} {v:,.0f}' for k, v in live.items())}")
    print(f"  history: {len(hist)} day(s) kept ({hist[0]} -> {hist[-1]})")


if __name__ == "__main__":
    main()
