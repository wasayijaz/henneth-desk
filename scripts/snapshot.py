"""Intraday snapshot for the light cycle: pulls market-watch once, writes
state/live.json for universe symbols (includes intraday high/low, which the EOD
feed lacks — these accumulate real OHLC going forward via state/ohlc_daily/)."""
import math
import time
from datetime import datetime, timedelta, timezone

from psx_data import STATE, load_json, market_watch, save_json, intraday_last
from psx_data import canonical_symbol


def _positive_number(value):
    return (type(value) in (int, float)
            and math.isfinite(value)
            and value > 0)


def _validate_traded_prices(live):
    for symbol, row in live.items():
        if not isinstance(row, dict):
            raise ValueError(f"snapshot: malformed market-watch row for {symbol}")
        if _positive_number(row.get("volume")) and not _positive_number(row.get("current")):
            raise ValueError(
                f"snapshot: invalid current for traded security {symbol}; preserving prior state"
            )


def main():
    universe = load_json(STATE / "universe.json", {"symbols": {}})
    snap = market_watch()
    # A weekend fetch still contains the last trading session. Use the exchange clock,
    # not the local capture date, for the session bucket; retain capture time separately.
    tick = intraday_last("KSE100")
    if not tick:
        raise ValueError("snapshot: exchange session timestamp missing; preserving prior state")
    source_at = datetime.fromtimestamp(tick["ts"], timezone(timedelta(hours=5)))
    captured = datetime.now(timezone.utc)
    if source_at > captured:
        raise ValueError("snapshot: exchange timestamp is in the future")
    today = source_at.date().isoformat()
    # Market-watch keys may carry a temporary XD/XB/XR suffix on an ex-day. Store the
    # print under the canonical ticker so live.json matches history/FFC.json, not a
    # second identity. Unknown suffixes are left as-is (canonical_symbol is a no-op).
    live = {}
    source_for_destination = {}
    for src_sym, row in snap.items():
        if not isinstance(src_sym, str):
            raise ValueError("snapshot: non-string DPS security identity; preserving prior state")
        source = src_sym.strip().upper()
        dest = canonical_symbol(source)
        symbols = universe["symbols"]
        if dest in symbols and source in symbols and dest != source:
            raise ValueError(
                f"snapshot: source/destination identity ambiguity for {source} -> {dest}; "
                "preserving prior state"
            )
        key = dest if dest in symbols else (source if source in symbols else None)
        if not key:
            continue
        prior_source = source_for_destination.get(key)
        if prior_source is not None and prior_source != source:
            raise ValueError(
                f"snapshot: canonical identity collision for {prior_source} and {source} -> {key}; "
                "preserving prior state"
            )
        source_for_destination[key] = source
        live[key] = row
    _validate_traded_prices(live)
    if len(live) < 100:
        raise ValueError("snapshot: insufficient matched securities; preserving prior state")
    save_json(STATE / "live.json", {"updated": time.strftime("%Y-%m-%d %H:%M"),
              "captured_at": captured.isoformat(), "source_at": source_at.isoformat(),
              "session_date": today, "tickers": live})

    # accumulate true OHLC per day (survives multiple snapshots; last one of the day wins)
    ohlc = load_json(STATE / "ohlc_daily" / f"{today}.json", {})
    for s, row in live.items():
        if row.get("open") is not None:
            ohlc[s] = {k: row[k] for k in ("open", "high", "low", "current", "volume")}
    save_json(STATE / "ohlc_daily" / f"{today}.json", ohlc)
    print(f"snapshot: {len(live)} universe symbols live")


if __name__ == "__main__":
    main()
