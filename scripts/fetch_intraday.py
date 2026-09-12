"""Fetch today's intraday tick series for universe symbols from DPS (the only
non-delayed PSX source). Powers the ticker page's 1D chart. Downsamples ticks to
~1-minute points to keep files small. Writes state/intraday/{SYM}.json (today only).

Note: DPS intraday returns the CURRENT session only, so a true multi-day 4H chart
isn't available from any free PSX feed — the desk is daily-timeframe anyway. This
gives the 1D view. Runs in light cycles during market hours."""
import time
from datetime import datetime, timedelta, timezone

import requests

from psx_data import HEADERS, STATE, load_json, market_symbols, save_json

BASE = "https://dps.psx.com.pk"


def fetch(symbol, sess):
    r = sess.get(f"{BASE}/timeseries/int/{symbol}", timeout=15)
    if r.status_code != 200:
        return None
    rows = r.json().get("data") or []
    # rows newest-first: [ts, price, cumulative? volume]; downsample to 1/min
    out, seen = [], set()
    for ts, price, vol in reversed(rows):
        minute = ts // 60
        if minute in seen:
            out[-1] = {"t": int(ts), "p": float(price), "v": int(vol)}
        else:
            seen.add(minute)
            out.append({"t": int(ts), "p": float(price), "v": int(vol)})
    return out


def main():
    universe = load_json(STATE / "universe.json", {"symbols": {}})
    sess = requests.Session()
    sess.headers.update(HEADERS)
    ok = 0
    # Intraday ticks only matter for names the desk actually watches trade-by-trade, and one
    # request per symbol across 554 listed names would dominate the cycle. Core tier only.
    #
    # PSX ONLY, and the market filter is load-bearing: non-PSX symbols are also tier=core, so
    # without it this would ask DPS for XLE on every 30-minute cycle. The source here is the DPS
    # tick feed, which has no concept of a US symbol. config/markets.json also sets
    # US.intraday:false — US regular hours are 18:30-01:00 PKT, outside every cycle the desk runs.
    core = [s for s, m in universe["symbols"].items() if (m or {}).get("tier", "core") == "core"]
    for sym in market_symbols("PSX", core):
        try:
            pts = fetch(sym, sess)
            if pts and len(pts) > 3:
                captured = datetime.now(timezone.utc)
                source_at = datetime.fromtimestamp(pts[-1]["t"], timezone(timedelta(hours=5)))
                if source_at > captured:
                    continue
                save_json(STATE / "intraday" / f"{sym}.json",
                          {"date": source_at.date().isoformat(), "points": pts,
                           "source_at": source_at.isoformat(), "captured_at": captured.isoformat()})
                ok += 1
        except requests.RequestException:
            pass
        time.sleep(0.15)
    print(f"intraday: {ok} symbols captured")


if __name__ == "__main__":
    main()
