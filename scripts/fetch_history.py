"""Fetch/refresh daily EOD history for universe symbols.

Full history cached per symbol in state/history/{SYM}.json. Trims to config history_years.

EVERY SYMBOL, EVERY RUN. This script used to refresh only a rotating slice (LISTED_PER_RUN) of the
long tail each run, on the assumption that the 30-minute cron fires ~18 times a weekday so the whole
universe gets covered over a few cycles. That assumption is false in the cloud: GitHub's scheduled-
workflow queue is best-effort and load-sheds ticks — since 2026-08-27 the cron that DECLARES 18
runs/weekday has actually fired 1-2 times/day. A rotation that needs ~4 runs to sweep the tail
simply never completes when only one run honours per day, and 263 symbols drifted weeks stale while
health stayed green. See docs/GOTCHAS.md "The cron is a wish, not a schedule".

The fix is to stop depending on run COUNT. One run now reprices the ENTIRE universe (~490 symbols)
by fetching concurrently with a small ThreadPoolExecutor (WORKERS). At ~1.3 req/s that is ~6 min,
well inside the job cap — so even a single honoured cron tick per day keeps every price ≤1 day old.
DEADLINE_S bounds the wall clock as a guard: symbols not reached before the deadline are NOT stamped
in the attempt clock, so they lead the next run (rare — the full sweep finishes long before it).

Symbols with NO history file yet still get their own bounded round-robin probe (NEW_PROBE_PER_RUN)
so the ~100 permanently-empty PSX board counters can never crowd the run — see the note on _pick().
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from psx_data import (STATE, eod_history, load_config, load_json, market_of, save_json,
                      yahoo_symbol)

WORKERS = 6                # concurrent fetchers — a LATENCY-hiding knob only. The aggregate request
                           # rate is capped centrally by psx_data._throttle, so raising this hides
                           # network latency without raising the DPS request rate (no 429 storm).
DEADLINE_S = 1200          # 20 min wall-clock guard, inside the workflow job cap
IN_FLIGHT_DRAIN_S = 180    # bounded DPS retry/request drain after completion intake stops
NEW_PROBE_PER_RUN = 12     # separate, round-robin budget for symbols with no history file yet
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) psx-desk/1.0"}


def _yahoo_daily(symbol: str, universe: dict, years: int) -> list[dict]:
    """Daily EOD for a NON-PSX market, in the exact shape psx_data.eod_history returns.

    The shape is the whole point. `state/history/{SYM}.json` is the seam every expensive consumer
    reads — quant.py, backtest.py, predictability.py, compute_fairvalue.py, correlation.py — and
    none of them contains PSX-specific logic. Write a US series in the same shape and the entire
    analysis stack works on it unmodified. Nothing downstream needed changing to cover a second
    market; that is why this is four characters of URL and one dispatch, not a port."""
    rng = f"{max(2, years + 1)}y"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(symbol, universe)}"
           f"?interval=1d&range={rng}")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    res = (r.json().get("chart") or {}).get("result")
    if not res:
        raise RuntimeError("no result")
    ts = res[0].get("timestamp") or []
    q = res[0]["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        c, o, v = q["close"][i], q["open"][i], q["volume"][i]
        if c is None:
            continue
        out.append({
            "date": time.strftime("%Y-%m-%d", time.gmtime(t)),
            "close": round(float(c), 2),
            "volume": int(v) if v else 0,
            # An index (^GSPC, ^VIX) has no open on some bars; fall back to the close rather than
            # dropping the bar, which would silently shorten the series the backtest sees.
            "open": round(float(o if o is not None else c), 2),
        })
    return out


def _pick(universe, cursor, attempts):
    """core + a bounded probe of never-fetched symbols + EVERY listed symbol that has a series.

    Every symbol with a history file is refreshed every run — the long tail is no longer rationed
    (see the module docstring: run count is unreliable in the cloud, so we cannot rely on covering
    the tail over several runs). The tail is still ORDERED least-recently-attempted first so that
    if a run is cut short by DEADLINE_S, the symbols that got skipped are exactly the ones already
    freshest, and the stalest lead the next run.

    THE PROBE BUDGET STAYS SEPARATE, AND THAT SEPARATION IS THE WHOLE POINT. The All Share
    constituent list carries ~103 PSX board counters (…NC non-compliant, …XD ex-dividend,
    …XB ex-bonus, rights) that are not companies and permanently return zero bars, so they never
    gain a history file. Fetching all of them every run would waste minutes on dead counters; the
    probe visits only NEW_PROBE_PER_RUN of them per run on a round-robin cursor, enough to onboard a
    genuinely new listing within a few runs without ever crowding the real refresh.

    THE ATTEMPT CLOCK IS PERSISTED STATE, NOT THE FILESYSTEM. It used to be the history file's
    st_mtime, which is meaningless in the cloud: every run starts with actions/checkout, which
    writes all files fresh in git index order — alphabetical. The attempt timestamps live in
    state/history_meta.json, committed by the cycle, so the ordering survives checkout.

    Returns (todo, n_listed, next_cursor). The cursor is persisted in history_meta.json.
    """
    syms = universe["symbols"]
    core, listed = [], []
    for s, m in syms.items():
        (core if (m or {}).get("tier", "core") == "core" else listed).append(s)

    def has_file(s):
        return (STATE / "history" / f"{s}.json").exists()
    # Sorted, not universe-ordered, so the cursor addresses a stable list across runs.
    never = sorted(s for s in listed if not has_file(s))
    # Least-recently-attempted first; a symbol absent from the map has never been attempted under
    # the current clock and goes to the front. Alphabetical only as a tiebreak. This ordering only
    # matters if DEADLINE_S cuts a run short — otherwise the whole list is fetched anyway.
    have = sorted((s for s in listed if has_file(s)), key=lambda s: (attempts.get(s, ""), s))
    probe, nxt = [], 0
    if never:
        start = cursor % len(never)
        n = min(NEW_PROBE_PER_RUN, len(never))
        probe = [never[(start + i) % len(never)] for i in range(n)]
        nxt = (start + n) % len(never)
    return core + probe + have, len(listed), nxt


def _fetch_one(sym, universe, years, cutoff):
    """Fetch and cache one symbol. Runs on a worker thread, so it takes only immutable args and
    touches no shared mutable state — save_json writes a per-symbol temp file then os.replace, which
    is safe across distinct symbols. Returns ('ok', None) or ('fail', reason); never raises, so one
    bad symbol never takes down the pool."""
    try:
        mkt = market_of(sym, universe)
        # DPS is authoritative for PSX (CLAUDE.md: prices come from the data layer). Every other
        # market has no DPS entry, so it routes to Yahoo — same output shape.
        src = eod_history(sym) if mkt == "PSX" else _yahoo_daily(sym, universe, years)
        hist = [d for d in src if d["date"] >= cutoff]
        # A recent listing legitimately has few bars — not a failure, and dropping it would make the
        # company invisible again. Keep anything with a usable series; only the core tier needs the
        # long history that signals and backtests depend on.
        tier = ((universe["symbols"].get(sym) or {}).get("tier", "core"))
        floor = 100 if tier == "core" else 20
        if len(hist) < floor:
            return ("fail", f"only {len(hist)} rows (tier {tier})")
        save_json(STATE / "history" / f"{sym}.json", hist)
        return ("ok", None)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash the cycle
        return ("fail", str(e)[:80])
    # Politeness is enforced GLOBALLY by psx_data._throttle (a shared rate gate across all
    # workers), not by a per-worker sleep here. A per-worker sleep scales politeness with 1/WORKERS
    # — the opposite of what's needed — so raising WORKERS silently raised the request rate and
    # tripped DPS 429s. The gate makes worker count purely a latency-hiding knob.


def main():
    cfg = load_config()
    universe = load_json(STATE / "universe.json", None)
    if not universe:
        print("FATAL: no universe.json — run update_universe.py first", file=sys.stderr)
        sys.exit(1)

    years = cfg["backtest"]["history_years"]
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - years * 365.25 * 86400))
    prior = load_json(STATE / "history_meta.json", {}) or {}
    attempts = dict(prior.get("last_attempt") or {})
    todo, n_listed, next_cursor = _pick(universe, int(prior.get("probe_cursor") or 0), attempts)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    ok, failed, processed = 0, [], 0

    # Fetch the whole run concurrently. A symbol is stamped in the attempt clock ONLY once its
    # result is in hand, so anything cut off by DEADLINE_S stays unstamped and leads the next run.
    # Leave enough room for the at-most-WORKERS requests already in flight to finish their
    # bounded retry loops. Without this allowance, the executor's orderly shutdown could make
    # the advertised wall-clock guard overrun even after this loop stopped accepting results.
    deadline = time.time() + DEADLINE_S - IN_FLIGHT_DRAIN_S
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_to_sym = {pool.submit(_fetch_one, s, universe, years, cutoff): s for s in todo}
        for fut in as_completed(fut_to_sym):
            if time.time() > deadline:
                break
            sym = fut_to_sym[fut]
            status, err = fut.result()
            attempts[sym] = stamp
            processed += 1
            if status == "ok":
                ok += 1
            else:
                failed.append((sym, err))
        # Anything not yet started is cancelled so the pool shuts down promptly; the ≤WORKERS still
        # in flight finish during the `with` exit. Neither group was stamped, so both lead next run.
        for fut in fut_to_sym:
            fut.cancel()
    skipped_deadline = len(todo) - processed

    # Coverage map: which symbols actually have a usable price series. The All Share constituent
    # list includes PSX board artifacts that are not tradeable companies — ex-dividend (…XD) and
    # ex-bonus (…XB) counters, and non-compliant (…NC) counters — which return zero bars. Surfacing
    # those in search would be a worse bug than the one that started this (a missing real company),
    # so the dashboard filters search to symbols listed here. Written every run, never guessed.
    cov = {}
    for sym in universe["symbols"]:
        p = STATE / "history" / f"{sym}.json"
        try:
            n = len(load_json(p, []))
        except Exception:
            n = 0
        if n > 0:
            cov[sym] = n
    save_json(STATE / "coverage.json", {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "n_with_history": len(cov),
        "n_universe": len(universe["symbols"]),
        "note": ("Symbols with a usable price series. Universe members absent here returned zero "
                 "bars from DPS — almost always non-tradeable board counters (…XD ex-dividend, "
                 "…XB ex-bonus, …NC non-compliant), not real listed companies."),
        "bars": cov,
    })

    save_json(STATE / "history_meta.json", {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        # Unambiguous completion clock for the post-close publication gate. The legacy
        # local-time `updated` field remains for existing displays.
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ok": ok,
        "attempted": len(todo),
        "processed": processed,
        "skipped_deadline": skipped_deadline,
        "with_history": len(cov),
        "listed_total": n_listed,
        "workers": WORKERS,
        "deadline_s": DEADLINE_S,
        "in_flight_drain_s": IN_FLIGHT_DRAIN_S,
        "new_probe_per_run": NEW_PROBE_PER_RUN,
        "probe_cursor": next_cursor,
        "note": ("EVERY symbol with a series is repriced EVERY run — one honoured cron tick keeps "
                 "the whole universe ≤1 day old, so cloud cron load-shedding no longer strands "
                 "prices (see docs/GOTCHAS.md 'The cron is a wish, not a schedule'). Fetch runs "
                 "concurrently (workers). skipped_deadline counts symbols not reached before "
                 "deadline_s cut the run short — normally 0; a non-zero value is expected to be "
                 "rare and preflight WARNs on it. Symbols with no series yet get a separate "
                 "round-robin probe (new_probe_per_run, resumed from probe_cursor) so the ~100 "
                 "permanently-empty PSX board counters never consume the refresh budget. "
                 "last_attempt is the ordering clock and MUST be persisted state — file mtimes are "
                 "rewritten by actions/checkout on every cloud run. It orders the run so that if "
                 "deadline_s does cut it short, the freshest symbols are the ones skipped and the "
                 "stalest lead the next run."),
        "last_attempt": {s: t for s, t in sorted(attempts.items()) if s in universe["symbols"]},
        "failed": [{"symbol": s, "err": e} for s, e in failed],
    })
    print(f"history: {ok} ok, {len(failed)} failed, {skipped_deadline} skipped "
          f"(attempted {len(todo)} of {len(universe['symbols'])}; {n_listed} listed)")
    if failed:
        for s, e in failed[:10]:
            print(f"  {s}: {e}")


if __name__ == "__main__":
    main()
