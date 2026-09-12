"""Deterministic active-signal generator — populates state/signals.json from
PROVEN strategies that are TRIGGERING on the latest bar. No LLM, no tokens, so it
runs free in the cloud pipeline every cycle.

For each universe ticker, for each strategy proven on it (strategy_map.json), it
evaluates the strategy's rules on the ticker's own history; if the rule fires on
the most recent bar, it's a candidate setup. Entry = last close, stop/target from
the strategy's own %s, size from config risk params. Candidates are ranked by
(net expectancy x hit rate) and filtered by portfolio risk limits.

HONESTY: these are BACKTEST-PROVEN candidate setups, not auditor-verified signals.
The LLM auditor (local agent pipeline) can later upgrade a candidate to "audited".
Labelled `basis: "backtest-proven, unaudited"` so the desk never overstates them."""
import json
import math
import time

from psx_data import ROOT, STATE, load_config, load_json, save_json

LIBRARY = None
HEALTH_BLOCKED_NOTE = (
    "health blocked: state/health.json status is not exactly ok; "
    "new signals are suppressed while positions and history remain untouched."
)


def _load_library():
    return {s["id"]: s for s in json.loads(
        (ROOT / "strategies" / "library.json").read_text(encoding="utf-8")
    )}


def _last_date(series):
    return series[-1].get("date") if series else None


def latest_series(sym):
    deep = load_json(STATE / "history_deep" / f"{sym}.json", None)
    dps = load_json(STATE / "history" / f"{sym}.json", None)
    choices = [series for series in (deep, dps) if series]
    if not choices:
        return None
    # Freshness wins. Depth is only a tie-breaker for the same final date; a longer stale
    # Yahoo series must never displace the current DPS series.
    return max(choices, key=lambda series: (_last_date(series) or "", len(series)))


def _write_health_blocked():
    save_json(STATE / "signals.json", {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "note": HEALTH_BLOCKED_NOTE,
        "active": [],
        "n_candidates": 0,
    })
    print("signals: blocked by data health")


def _finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def main():
    health = load_json(STATE / "health.json", {})
    if (health or {}).get("status") != "ok":
        _write_health_blocked()
        return

    global LIBRARY
    from strategy_engine import compute_indicators, signals

    LIBRARY = _load_library()
    cfg = load_config()
    risk = cfg["risk"]
    capital = cfg["capital_pkr"]
    smap = load_json(STATE / "strategy_map.json", {"tickers": {}})["tickers"]
    quant = load_json(STATE / "quant.json", {"tickers": {}})["tickers"]
    live_doc = load_json(STATE / "live.json", {"tickers": {}})
    live = live_doc.get("tickers") or {}
    session_date = live_doc.get("session_date")
    universe = load_json(STATE / "universe.json", {"symbols": {}}).get("symbols") or {}
    psx_symbols = {
        sym for sym, meta in universe.items()
        if ((meta or {}).get("market") or "PSX") == "PSX"
    }
    # Real PSX sectors (fetch_sectors.py). CLAUDE.md Rule 4 caps the desk at one position per
    # sector — that limit was previously keyed on the COMPANY NAME, which is unique per ticker, so
    # it could never bind and four banks could pass as four different "sectors".
    sectors = load_json(STATE / "sectors.json", {"tickers": {}})["tickers"]
    positions = load_json(STATE / "positions.json", {"open": []})
    held = {p["ticker"] for p in positions.get("open", [])}

    candidates = []
    for sym, proven in smap.items():
        if sym not in psx_symbols:
            continue
        if sym in held:
            continue
        series = latest_series(sym)
        if not series or len(series) < 220:
            continue
        if _last_date(series) != session_date:
            continue
        ind = compute_indicators(series)
        q = quant.get(sym, {})
        if q.get("date") != session_date:
            continue
        live_meta = live.get(sym) or {}
        px = live_meta.get("current")
        if not _finite_positive(px) or not _finite_positive(live_meta.get("volume")):
            continue

        for p in proven:
            spec = LIBRARY.get(p["id"])
            if not spec:
                continue
            sig = signals(spec, ind)
            if not bool(sig[-1]):
                continue  # not triggering on the most recent bar
            stop = round(px * (1 - spec["stop_pct"] / 100), 2)
            target = round(px * (1 + spec["target_pct"] / 100), 2)
            risk_per_share = px - stop
            if risk_per_share <= 0:
                continue
            # Position sizing — CLAUDE.md Rule 4, the ONE formula (Strategist & Auditor identical):
            # size by stop distance (risk_per_trade_pct of capital), then hard-cap position VALUE
            # at max_pct_per_trade (8%) of capital.
            #
            # STILL COMPUTED, NO LONGER PUBLISHED (docs/PUBLICATION_RESTRUCTURE.md §3). A share
            # count against a capital figure the desk holds is the single most advisory-looking
            # output in the product — the difference between "here is the setup" and "here is what
            # you should buy". The reader sizes it themselves at /tools/position-size-calculator/,
            # against their own capital, in their own browser.
            #
            # The computation stays because `shares <= 0` is the Rule 4 VALIDITY GUARD: it rejects
            # a setup whose stop is too wide for the risk budget at this price. Delete the maths
            # along with the output fields and invalid setups start publishing.
            risk_budget = capital * risk.get("risk_per_trade_pct", 1.0) / 100
            shares_by_risk = risk_budget / risk_per_share
            shares_by_cap = (capital * risk["max_pct_per_trade"] / 100) / px
            shares = int(min(shares_by_risk, shares_by_cap))
            if shares <= 0:
                continue  # stop too wide for the risk budget at this price — invalid setup
            score = p["net_expectancy_pct"] * (p["hit_rate"] or 0)
            # PUBLICATION_RESTRUCTURE_V2 §4a — the published record carries NO named-security level:
            # no entry, stop, target, rr or risk_per_share. Under SECP Reg 2(ha) (S.R.O.7(I)/2026) a
            # price target or stop-loss on a named security IS a "research service"; without the Reg 3
            # licence the product must stay inside the 2(h) general-commentary exemption — describe,
            # never direct. The reader derives their own levels from the strategy's published %s at
            # /tools/strategy-level-calculator/. stop/target/risk_per_share above are still computed
            # because `shares <= 0` (Rule 4 validity guard) rejects setups whose stop is too wide;
            # they are computed and thrown away, exactly like the sizing fields.
            candidates.append({
                "id": f"{time.strftime('%Y%m%d')}-{sym}-{p['id']}",
                "ticker": sym, "strategy": p["id"], "template": p["name"],
                "category": p["category"], "sector": sectors.get(sym, {}).get("sector", ""),
                "hold_sessions": p["hold"],
                "backtest": {"hit_rate": p["hit_rate"], "net_expectancy_pct": p["net_expectancy_pct"],
                             "n": p["n"], "oos_hit": p.get("oos_hit")},
                # Confidence label is capped by sample size, not just score — min_trades (8) is the
                # bare eligibility floor, not enough to call anything "high confidence". A strategy
                # proven on 8-15 trades can't outrank one proven on 50+ just because its expectancy
                # score happens to be higher.
                "confidence": (
                    "high" if score > 1.5 and p["n"] >= 30
                    else "medium" if score > 0.7 and p["n"] >= 15
                    else "low"
                ),
                "basis": "backtest-proven, unaudited",
                "thesis": f"{p['name']} is triggering now; on {sym}'s own history it won "
                          f"{round((p['hit_rate'] or 0)*100)}% over {p['n']} trades ({p['net_expectancy_pct']:+.1f}% net/trade), "
                          f"still profitable out-of-sample.",
                "_score": score,
            })

    # rank, then apply portfolio limits: max positions, one per sector, best per ticker
    candidates.sort(key=lambda c: -c["_score"])
    active, used_sectors, used_tickers = [], set(), set()
    for c in candidates:
        if len(active) >= risk["max_positions"]:
            break
        if c["ticker"] in used_tickers:
            continue
        # An unmapped ticker collapses into one shared "unknown" bucket rather than becoming its
        # own sector: this is a RISK limit, so the unknown case must fail safe (block), not open.
        sec = c["sector"] or "unknown"
        if sec in used_sectors:
            continue
        c.pop("_score", None)
        active.append(c)
        used_tickers.add(c["ticker"])
        used_sectors.add(sec)

    save_json(STATE / "signals.json", {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "note": "deterministic candidate setups from proven strategies triggering on the latest bar; "
                "backtest-proven but NOT auditor-verified. Research, not advice.",
        "active": active,
        "n_candidates": len(candidates),
    })
    print(f"signals: {len(active)} active from {len(candidates)} triggering candidates")
    for s in active:
        print(f"  {s['ticker']:6} {s['template']:24} {s['category']:12} ({s['confidence']})")


if __name__ == "__main__":
    main()
