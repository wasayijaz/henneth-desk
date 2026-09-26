"""Screener layer: one compact row per universe ticker, aggregating the 37
screener variables (move/risk/value/income/quality/context) purely from
state files other producers already wrote. Writes state/screener.json.

No new computation of business facts happens here except five history-derived
move variables (chg_3m, chg_1y, off_high, off_low, vs200) that no other
producer emits yet, and two count/max aggregations (news30/impact, ins30)
over already-tagged records. Everything else is a straight read of a value
another script already computed (quant.py, liquidity.py, compute_fairvalue.py,
score_fundamentals.py, predictability.py, sectors, universe, backtest.py's
strategy_map, dividends, newslog, insider_activity) — this script does not
re-derive PE, fair value, beta, sector, etc.

Missing data is written as null (never guessed), per desk rule: "if the data
layer doesn't have it, the answer is unknown."
"""
import datetime as dt

from psx_data import STATE, load_json, save_json

HISTORY = STATE / "history"

# A single-session |return| at or above this is treated as an unadjusted
# split/bonus artifact (PSX's own per-session price cap is well under this),
# not a real move. When one is found inside a metric's lookback window, that
# history-derived metric is written as unknown for the ticker rather than
# risking a corrupted percentage. Detected live per run, not a frozen list of
# tickers, so it keeps working as new bonus/split events happen.
JUMP_GUARD_PCT = 0.20


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 1)


def _parse_date(s):
    try:
        return dt.date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def _history_vars(bars):
    """chg_3m, chg_1y, off_high, off_low, vs200 from a symbol's daily bars."""
    out = {"chg_3m": None, "chg_1y": None, "off_high": None, "off_low": None, "vs200": None}
    if not bars or len(bars) < 63:
        return out
    closes = [b["close"] for b in bars if b.get("close") is not None]
    if len(closes) < 63:
        return out

    window = closes[-252:] if len(closes) >= 252 else closes
    for i in range(1, len(window)):
        prev = window[i - 1]
        if prev and abs(window[i] / prev - 1) >= JUMP_GUARD_PCT:
            return out  # unadjusted split/bonus artifact in the lookback window

    c = closes[-1]
    out["chg_3m"] = _pct(c, closes[-63])
    if len(closes) >= 252:
        out["chg_1y"] = _pct(c, closes[-252])
    out["off_high"] = _pct(c, max(window))
    out["off_low"] = _pct(c, min(window))
    if len(closes) >= 200:
        out["vs200"] = _pct(c, sum(closes[-200:]) / 200)
    return out


def _income_vars(sym, div, cutoff):
    known_population = {e["symbol"] for e in div.get("history", [])} | \
        {e["symbol"] for e in div.get("upcoming", [])} | \
        {e["symbol"] for e in div.get("failed", [])}
    ndiv = None
    if sym in known_population:
        ndiv = sum(
            1 for e in div.get("history", [])
            if e.get("symbol") == sym and (_parse_date(e.get("bc_start")) or dt.date.min) >= cutoff
        )
    bc = "yes" if any(e.get("symbol") == sym for e in div.get("upcoming", [])) else "no"
    return ndiv, bc


def _context_news(sym, newslog, cutoff):
    matches = [
        item for item in newslog
        if sym in (item.get("tickers") or []) and (_parse_date(item.get("ts")) or dt.date.min) >= cutoff
    ]
    news30 = len(matches)
    impact = max((m["impact"] for m in matches if m.get("impact") is not None), default=None)
    return news30, impact


def _quality_strategies(entries):
    if entries is None:
        return None, None, None
    nprov = len(entries)
    if not entries:
        return nprov, None, None
    besthit = round(max(e["hit_rate"] for e in entries if e.get("hit_rate") is not None) * 100) \
        if any(e.get("hit_rate") is not None for e in entries) else None
    bestnet = round(max(e["net_expectancy_pct"] for e in entries if e.get("net_expectancy_pct") is not None), 2) \
        if any(e.get("net_expectancy_pct") is not None for e in entries) else None
    return nprov, besthit, bestnet


def build():
    quant = load_json(STATE / "quant.json", {}).get("tickers", {})
    liquidity = load_json(STATE / "liquidity.json", {}).get("tickers", {})
    fairvalue = load_json(STATE / "fairvalue.json", {}).get("tickers", {})
    fscores = load_json(STATE / "fundamental_scores.json", {}).get("tickers", {})
    predictability = load_json(STATE / "predictability.json", {}).get("tickers", {})
    sectors = load_json(STATE / "sectors.json", {}).get("tickers", {})
    universe = load_json(STATE / "universe.json", {}).get("symbols", {})
    strategy_map = load_json(STATE / "strategy_map.json", {}).get("tickers", {})
    dividends = load_json(STATE / "dividends.json", {})
    newslog = load_json(STATE / "newslog.json", [])
    insider = load_json(STATE / "insider_activity.json", {}).get("symbols", {})

    asof_raw = load_json(STATE / "quant.json", {}).get("updated", "")
    asof = _parse_date(asof_raw) or dt.date.today()
    cutoff_30d = asof - dt.timedelta(days=30)
    cutoff_5y = asof - dt.timedelta(days=5 * 365)

    rows = {}
    for sym, uni in sorted(universe.items()):
        q = quant.get(sym)
        liq = liquidity.get(sym)
        fv = fairvalue.get(sym)
        fs = fscores.get(sym)
        pred = predictability.get(sym)
        sec = sectors.get(sym)
        bars = load_json(HISTORY / f"{sym}.json", None)

        hist_vars = _history_vars(bars)
        ndiv, bc = _income_vars(sym, dividends, cutoff_5y)
        news30, impact = _context_news(sym, newslog, cutoff_30d)
        ins30 = sum(
            1 for e in insider.get(sym, [])
            if (_parse_date(e.get("date")) or dt.date.min) >= cutoff_30d
        )
        nprov, besthit, bestnet = _quality_strategies(strategy_map.get(sym))

        fs_metrics = (fs or {}).get("metrics", {})
        market_cap = fs_metrics.get("market_cap")

        rows[sym] = {
            "name": uni.get("name"),
            "sector": (sec or {}).get("sector"),
            # move
            "chg_1w": q.get("ret_5d") if q else None,
            "chg_1m": q.get("ret_20d") if q else None,
            "chg_3m": hist_vars["chg_3m"],
            "chg_1y": hist_vars["chg_1y"],
            "off_high": hist_vars["off_high"],
            "off_low": hist_vars["off_low"],
            "vs50": _pct(q.get("close"), q.get("sma50")) if q else None,
            "vs200": hist_vars["vs200"],
            "rsi": q.get("rsi14") if q else None,
            "price": q.get("close") if q else None,
            # risk
            "vol": liq.get("daily_sigma_pct") if liq else None,
            "beta": fs_metrics.get("beta"),
            "adtv": liq.get("adtv_m") if liq else None,
            "spread": liq.get("spread_pct") if liq else None,
            "surge": q.get("vol_surge") if q else None,
            "liqb": liq.get("sec_bucket") if liq else None,
            # value
            "pe": (fv or {}).get("pe") if fv else fs_metrics.get("pe"),
            "fpe": fs_metrics.get("forward_pe"),
            "gap": (fv or {}).get("upside_pct"),
            "verdict": (fv or {}).get("verdict"),
            "mcap": round(market_cap / 1e9, 1) if market_cap is not None else None,
            # income
            "dy": fs_metrics.get("div_yield"),
            "payout": fs_metrics.get("payout_ratio"),
            "ndiv": ndiv,
            "bc": bc,
            # quality
            "margin": fs_metrics.get("net_margin"),
            "rating": (fs or {}).get("rating"),
            "pred": (pred or {}).get("score"),
            "nprov": nprov,
            "besthit": besthit,
            "bestnet": bestnet,
            # context
            "kse100": "yes" if "KSE100" in (uni.get("in") or []) else "no",
            "kmi": "yes" if "KMIALLSHR" in (uni.get("in") or []) else "no",
            "news30": news30,
            "impact": impact,
            "ins30": ins30,
        }

    save_json(STATE / "screener.json", {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "asof": asof.isoformat(),
        "note": "Screener rollup: reads only, aggregates existing per-symbol state. "
                "Missing values are null, never guessed. Research, not advice.",
        "sources": [
            "quant.json", "liquidity.json", "fairvalue.json", "fundamental_scores.json",
            "predictability.json", "sectors.json", "universe.json", "strategy_map.json",
            "dividends.json", "newslog.json", "insider_activity.json", "history/*.json",
        ],
        "n": len(rows),
        "tickers": rows,
    })


if __name__ == "__main__":
    try:
        build()
    except Exception as e:  # never crash the cycle
        save_json(STATE / "screener.json", {
            "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "degraded",
            "error": str(e),
            "n": 0,
            "tickers": {},
        })
    raise SystemExit(0)
