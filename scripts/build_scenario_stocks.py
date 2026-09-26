"""Which named stocks actually move with which macro factor? Measured, not assumed.

Stock-level companion to sector_macro.py. Same discipline, same machinery, one level
deeper: instead of asking "does oil move Refinery" this asks "does oil move NRL" for
every named PSX stock the sector links already cover.

Scope is deliberately the SAME 7 macro factors sector_macro.py tests (oil, gold, usdpkr,
sp500, em_equity, us10y, dollar) — see state/macro_history.json["factors"]. The desk's
factor history does not (yet) carry the other series some older drafts assumed (vix,
coal, brent, cotton, metals, softs, china/india/hangseng, us2y, us3m, fed); adding a
stock-level factor that does not exist in macro_history.json would silently ship
mockup-only data, which the desk rules forbid.

METHOD (identical to sector_macro.py's, applied per stock instead of per sector; the two
files intentionally duplicate the factor-alignment step rather than share it — see the
comment in sector_macro.py's main() pointing back here):
  * Stock return = day-over-day %% change of an un-adjusted history_deep close.
  * Factor return = day-over-day %% change of each macro series, LAGGED ONE PSX TRADING
    DAY (global markets close after Karachi does). us10y is measured in yield POINTS,
    not %%, same as sector_macro.py.
  * Effect = OLS beta of stock return on the single factor, plus correlation (r).
  * Significance = circular-shift permutation (2,000 draws, refined to 50,000 when
    p <= 0.01), preserving each side's own autocorrelation.
  * False-discovery control is its OWN Benjamini-Hochberg family over every stock x factor
    test — kept separate from sector_macro.py's sector-level family (different test
    population, same correction machinery). Bonferroni is also reported per test.
  * Minimum 750 shared trading days per test, same floor as the sector level.

UNIVERSE: history_deep symbols that are also named in sectors.json's ticker map (100 PSX
names at last count). ETF and US-index proxy files that also live in history_deep
(ACWI, GLD, XLE, US500, ...) are not PSX securities and are skipped.

SPLIT GUARD: history_deep is not split-adjusted. A day is dropped from a stock's return
series when the close moved >= 25%%, or > 10.5%% on a stock priced >= Rs 10 (sector_macro.py
uses the simpler 25%% guard only, because sector returns are an equal-weight mean across
>=3 members and a single un-adjusted jump is diluted; a single stock's own series has no
such dilution, so the tighter secondary guard applies here). A small bonus issue under
roughly 10%% cannot be told apart from an ordinary move without corporate-action data and
may still slip through — documented caveat, not a defect.

No advice, no forecast: the note field on the output says so, and the dashboard caption
repeats it next to every named stock. Writes state/scenario_stocks.json. Free,
deterministic, same weekly cadence as sector_macro.py.
"""
import datetime as dt
import json
import pathlib
import sys
import time

import numpy as np

from psx_data import save_json
from sector_macro import circular_p

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
HIST = STATE / "history_deep"

# Same 7 factors sector_macro.py tests — the only ones state/macro_history.json carries.
IN_SCOPE_FACTORS = {"oil", "gold", "usdpkr", "sp500", "em_equity", "us10y", "dollar"}

MIN_DAYS = 750
N_PERM = 2000
N_PERM_FINE = 50000
FINE_TRIGGER = 0.01
ALPHA = 0.05
STALE_DAYS = 7
SPLIT_GUARD_ABS = 0.25          # any stock/sector: drop if the move is this big or bigger
SPLIT_GUARD_LOWPRICE = 0.105    # additionally, drop if priced >= Rs 10 and move exceeds this


def load(p, default=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def stock_returns(bars):
    """Day-over-day close returns with the tighter per-stock split guard."""
    out = {}
    prev_c = None
    for b in bars:
        c = b.get("close")
        d = b.get("date")
        if prev_c and c and prev_c > 0 and d:
            r = c / prev_c - 1
            if abs(r) >= SPLIT_GUARD_ABS:
                prev_c = c
                continue
            if prev_c >= 10 and abs(r) > SPLIT_GUARD_LOWPRICE:
                prev_c = c
                continue
            out[d] = r
        prev_c = c or prev_c
    return out


def factor_returns(mh):
    """Mirrors sector_macro.py's fr/aligned construction — see module docstring."""
    fr = {}
    for name, rec in mh["factors"].items():
        if name not in IN_SCOPE_FACTORS:
            continue
        s = rec["series"]
        ds = sorted(s)
        out = {}
        for a, b in zip(ds, ds[1:]):
            if name == "us10y":
                out[b] = (s[b] - s[a]) / 10.0
            elif s[a]:
                out[b] = s[b] / s[a] - 1
        fr[name] = out
    return fr


def align(psx_days, fr, fnames):
    aligned = {n: [] for n in fnames}
    for d in psx_days:
        for n in fnames:
            prior = None
            for back in range(1, 8):
                q = (dt.date.fromisoformat(d) - dt.timedelta(days=back)).isoformat()
                if q in fr[n]:
                    prior = fr[n][q]
                    break
            aligned[n].append(prior if prior is not None else np.nan)
    return {n: np.array(v) for n, v in aligned.items()}


def main():
    if "--force" not in sys.argv:
        prev = load(STATE / "scenario_stocks.json")
        if prev and prev.get("updated"):
            try:
                age = (dt.datetime.now() - dt.datetime.strptime(prev["updated"], "%Y-%m-%d %H:%M")).days
                if age < STALE_DAYS:
                    print(f"build_scenario_stocks: last run {age}d ago — weekly cadence, skipping (--force to override)")
                    sys.exit(0)
            except Exception:
                pass

    t0 = time.time()
    mh = load(STATE / "macro_history.json")
    sectors_doc = load(STATE / "sectors.json", {}) or {}
    tickers = sectors_doc.get("tickers", {})
    universe = (load(STATE / "universe.json", {}) or {}).get("symbols", {})
    if not mh or not tickers or not HIST.is_dir():
        print("build_scenario_stocks: need macro_history.json + sectors.json + history_deep first")
        save_json(STATE / "scenario_stocks.json", {
            "updated": time.strftime("%Y-%m-%d %H:%M"), "status": "degraded",
            "reason": "missing macro_history.json, sectors.json or history_deep",
            "by_factor": {}, "stocks": {}, "method": {}, "headline": {},
        })
        sys.exit(0)

    fr = factor_returns(mh)
    fnames = sorted(fr)
    if not fnames:
        print("build_scenario_stocks: none of the in-scope factors are present in macro_history.json")
        sys.exit(0)

    # ---- per-stock daily returns, PSX names only (skip ETF/US-index files also in history_deep)
    stock_rets = {}
    for f in sorted(HIST.glob("*.json")):
        sym = f.stem
        if sym not in tickers:
            continue
        bars = load(f, [])
        r = stock_returns(bars)
        if r:
            stock_rets[sym] = r

    all_days = sorted({d for r in stock_rets.values() for d in r})
    F = align(all_days, fr, fnames)
    day_index = {d: i for i, d in enumerate(all_days)}

    rng = np.random.default_rng(20260718)
    tests = []
    for sym, r in sorted(stock_rets.items()):
        idx = np.array([day_index[d] for d in r])
        y0 = np.full(len(all_days), np.nan)
        y0[idx] = list(r.values())
        for fn in fnames:
            x0 = F[fn]
            ok = np.isfinite(y0) & np.isfinite(x0)
            if ok.sum() < MIN_DAYS:
                continue
            y, x = y0[ok], x0[ok]
            b, c, p = circular_p(y, x, rng, N_PERM)
            if p <= FINE_TRIGGER:
                b, c, p = circular_p(y, x, rng, N_PERM_FINE)
            tests.append({"stock": sym, "factor": fn, "beta": round(b, 4), "corr": round(c, 4),
                          "days": int(ok.sum()), "p_value": float(f"{p:.3g}")})

    tests.sort(key=lambda t: t["p_value"])
    m = len(tests)
    bonf = ALPHA / max(1, m)
    bh_cut = 0.0
    for i, t in enumerate(tests, 1):
        if t["p_value"] <= i / m * ALPHA:
            bh_cut = t["p_value"]
    for t in tests:
        t["survives_bonferroni"] = bool(t["p_value"] < bonf)
        t["survives_fdr"] = bool(t["p_value"] <= bh_cut)
    surv = [t for t in tests if t["survives_bonferroni"]]
    fdr = [t for t in tests if t["survives_fdr"]]

    by_factor = {fn: [] for fn in fnames}
    for t in tests:
        by_factor[t["factor"]].append({
            "stock": t["stock"], "beta": t["beta"], "corr": t["corr"], "p_value": t["p_value"],
            "days": t["days"], "survives_bonferroni": t["survives_bonferroni"],
            "survives_fdr": t["survives_fdr"],
        })
    for fn in by_factor:
        by_factor[fn].sort(key=lambda row: row["p_value"])

    stocks_meta = {}
    for sym in stock_rets:
        u = universe.get(sym, {})
        stocks_meta[sym] = {
            "name": u.get("name") or sym,
            "sector": (tickers.get(sym) or {}).get("sector") or "unknown",
            "weight_pct": u.get("weight_pct") or 0,
        }

    out = {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "window": {"from": all_days[0] if all_days else None,
                   "to": all_days[-1] if all_days else None,
                   "psx_days": len(all_days), "stocks": len(stock_rets)},
        "method": {
            "lag": "every factor is lagged one PSX day, same as sector_macro.py — see that "
                   "file's method note for why.",
            "test": "circular-shift permutation (same machinery as sector_macro.py), "
                    "Bonferroni + Benjamini-Hochberg both reported",
            "split_guard": f"a stock-day is dropped when the close moved >= {SPLIT_GUARD_ABS*100:.0f}%, "
                            f"or > {SPLIT_GUARD_LOWPRICE*100:.1f}% while priced >= Rs 10 "
                            "(history_deep is not split-adjusted)",
            "us10y_units": "beta is per PERCENTAGE-POINT change in the US 10y yield",
            "hypotheses": m, "bonferroni_bar": float(f"{bonf:.2e}"), "fdr_cutoff": float(f"{bh_cut:.2e}"),
            "family": "separate Benjamini-Hochberg family from sector_macro.py's sector-level tests",
        },
        "headline": {
            "hypotheses_tested": m,
            "survivors_bonferroni": len(surv),
            "survivors_fdr": len(fdr),
        },
        "by_factor": by_factor,
        "stocks": stocks_meta,
        "note": "Descriptive attribution, not a trading signal and not advice. A demonstrated beta "
                "says what a stock's price HAS tended to do alongside a factor, not what it will do.",
    }
    save_json(STATE / "scenario_stocks.json", out)

    print(f"build_scenario_stocks: {m} stock x factor tests over {len(stock_rets)} stocks in {time.time()-t0:.0f}s")
    print(f"  survivors: {len(surv)} bonferroni | {len(fdr)} fdr (bar {bonf:.1e}, fdr cut {bh_cut:.1e})")


if __name__ == "__main__":
    main()
