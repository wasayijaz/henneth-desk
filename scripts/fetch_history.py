"""Fetch/refresh daily EOD history for universe symbols.

Full history cached per symbol in state/history/{SYM}.json. Trims to config history_years.

EVERY SYMBOL, EVERY RUN. This script used to refresh only a rotating slice (LISTED_PER_RUN) of the
long tail each run, on the assumption that the 30-minute cron fires ~18 times a weekday so the whole
universe gets covered over a few cycles. That assumption is false in the cloud: GitHub's scheduled-
workflow queue is best-effort and load-sheds ticks — since 2026-08-27 the cron that DECLARES 18
runs/weekday has actually fired 1-2 times/day. A rotation that needs ~4 runs to sweep the tail
simply never completes when only one run honours per day, and 263 symbols drifted weeks stale while
health stayed green. See docs/GOTCHAS.md "The cron is a wish, not a schedule".

Every run attempts the entire source universe, including symbols without a cached series,
using a small ThreadPoolExecutor (WORKERS) and the shared provider rate gate.
DEADLINE_S is the monotonic request/intake budget: symbols without a completed result before it are
NOT stamped in the attempt clock, so they lead the next run (rare — the full sweep finishes long
before it).

Price storage accepts a valid series of any length. Research eligibility belongs to downstream
consumers; missing history does not establish whether an instrument exists or traded.
"""
import math
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timezone

import requests

from psx_data import (DeadlineExceeded, STATE, eod_history, load_config, load_json, market_of,
                      save_json, yahoo_symbol)

WORKERS = 6                # concurrent fetchers — a LATENCY-hiding knob only. The aggregate request
                           # rate is capped centrally by psx_data._throttle, so raising this hides
                           # network latency without raising the DPS request rate (no 429 storm).
DEADLINE_S = 1200          # 20 min wall-clock guard, inside the workflow job cap
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) psx-desk/1.0"}


def _yahoo_daily(symbol: str, universe: dict, years: int, deadline=None) -> list[dict]:
    """Daily EOD for a NON-PSX market, in the exact shape psx_data.eod_history returns.

    The shape is the whole point. `state/history/{SYM}.json` is the seam every expensive consumer
    reads — quant.py, backtest.py, predictability.py, compute_fairvalue.py, correlation.py — and
    none of them contains PSX-specific logic. Write a US series in the same shape and the entire
    analysis stack works on it unmodified. Nothing downstream needed changing to cover a second
    market; that is why this is four characters of URL and one dispatch, not a port."""
    rng = f"{max(2, years + 1)}y"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(symbol, universe)}"
           f"?interval=1d&range={rng}")
    remaining = deadline - time.monotonic() if deadline is not None else None
    if remaining is not None and remaining <= 0:
        raise DeadlineExceeded("history refresh deadline exceeded")
    r = requests.get(url, headers=UA, timeout=min(20, remaining) if remaining is not None else 20)
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


def _attempt_order(value):
    """Unknown/naive attempts lead; aware attempts sort by their actual UTC instant.

    Legacy naive clocks are ordering hints only, never evidence of a completed refresh.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return (0, parsed.isoformat())
        return (1, parsed.astimezone(timezone.utc).isoformat())
    except (AttributeError, TypeError, ValueError):
        return (0, "")


def _pick(universe, attempts):
    """Every source identity once, least-recently-attempted first across both tiers.

    Persisted attempt timestamps survive cloud checkout; file mtimes do not. An unstamped
    deadline skip gets priority next run. Core tier breaks ties, never excludes listed names.
    """
    syms = universe["symbols"]
    todo = sorted(syms, key=lambda s: (
        _attempt_order(attempts.get(s)), (syms[s] or {}).get("tier", "core") != "core", s,
    ))
    n_listed = sum((m or {}).get("tier", "core") != "core" for m in syms.values())
    return todo, n_listed


def _validate_history(rows):
    """Validate the provider-normalized series before filtering or replacing cached prices."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty or malformed history series")
    previous = ""
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("history row is not an object")
        stamp = row.get("date")
        if not isinstance(stamp, str) or date.fromisoformat(stamp).isoformat() != stamp:
            raise ValueError("history date must be YYYY-MM-DD")
        if stamp <= previous:
            raise ValueError("history dates must be unique and oldest-first")
        previous = stamp
        for field in ("open", "close", "volume"):
            value = row.get(field)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"history {field} must be a finite number")
            if field == "volume":
                if value < 0 or value != int(value):
                    raise ValueError("history volume must be nonnegative whole shares")
            elif field == "close" and value <= 0:
                raise ValueError("history close must be positive")
            elif field == "open" and value < 0:
                raise ValueError("history open must be nonnegative")
            # DPS has zero opens even on some positive-volume days. Preserve that existing
            # source representation; do not fabricate an opening price from the close.


def _fetch_one(sym, universe, years, cutoff, deadline=None):
    """Fetch and cache one symbol. Runs on a worker thread, so it takes only immutable args and
    touches no shared mutable state — save_json writes a per-symbol temp file then os.replace, which
    is safe across distinct symbols. Returns ('ok', None), ('fail', reason), or ('skip', reason)
    for deadline exhaustion; never raises, so one bad symbol never takes down the pool."""
    try:
        if deadline is not None and time.monotonic() >= deadline:
            raise DeadlineExceeded("history refresh deadline exceeded")
        mkt = market_of(sym, universe)
        # DPS is authoritative for PSX (CLAUDE.md: prices come from the data layer). Every other
        # market has no DPS entry, so it routes to Yahoo — same output shape.
        if mkt == "PSX":
            # The provider owns DPS parsing, throttling, retries, and the optional deadline.
            src = eod_history(sym, deadline=deadline)
        else:
            src = _yahoo_daily(sym, universe, years, deadline)
        _validate_history(src)
        hist = [d for d in src if d["date"] >= cutoff]
        if not hist:
            return ("fail", "no history inside configured window")
        path = STATE / "history" / f"{sym}.json"
        old = load_json(path, [])
        if old:
            _validate_history(old)
            retained_dates = {d["date"] for d in old if d["date"] >= cutoff}
            if not retained_dates.issubset({d["date"] for d in hist}):
                return ("fail", "partial history response omits cached dates inside window")
        # A valid one-bar series is price coverage, not permission to compute research metrics.
        if deadline is not None and time.monotonic() >= deadline:
            raise DeadlineExceeded("history refresh deadline exceeded")
        save_json(path, hist)
        return ("ok", None)
    except DeadlineExceeded as e:
        return ("skip", str(e))
    except Exception as e:  # noqa: BLE001 — degrade, don't crash the cycle
        if deadline is not None and time.monotonic() >= deadline:
            return ("skip", "history refresh deadline exceeded")
        return ("fail", str(e)[:80])
    # Politeness is enforced GLOBALLY by psx_data._throttle (a shared rate gate across all
    # workers), not by a per-worker sleep here. A per-worker sleep scales politeness with 1/WORKERS
    # — the opposite of what's needed — so raising WORKERS silently raised the request rate and
    # tripped DPS 429s. The gate makes worker count purely a latency-hiding knob.


def _collect_results(todo, worker, deadline):
    """Collect only results received before deadline; cancel queued work and join running work.

    Running requests are not force-cancelled: their provider calls receive the same deadline and
    must return through their bounded timeout/backoff path before the non-daemon pool is joined.
    """
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    fut_to_sym = {pool.submit(worker, sym): sym for sym in todo}
    pending = set(fut_to_sym)
    results = []
    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                break
            if time.monotonic() >= deadline:
                pending.update(done)
                break
            for fut in done:
                if time.monotonic() >= deadline:
                    pending.add(fut)
                    continue
                sym = fut_to_sym[fut]
                try:
                    results.append((sym, fut.result()))
                except Exception as e:  # noqa: BLE001 — a worker must not abort the sweep
                    results.append((sym, ("fail", str(e)[:80])))
    finally:
        for fut in pending:
            fut.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
    return results


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
    todo, n_listed = _pick(universe, attempts)
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ok, failed, processed = 0, [], 0

    # Fetch the whole run concurrently. A symbol is stamped in the attempt clock ONLY once its
    # result is in hand before the real monotonic deadline, so anything cut off stays unstamped
    # and leads the next run.
    deadline = time.monotonic() + DEADLINE_S
    results = _collect_results(
        todo,
        lambda sym: _fetch_one(sym, universe, years, cutoff, deadline),
        deadline,
    )
    for sym, (status, err) in results:
        if status == "skip":
            continue
        attempts[sym] = stamp
        processed += 1
        if status == "ok":
            ok += 1
        else:
            failed.append((sym, err))
    skipped_deadline = len(todo) - processed

    # Coverage reports cached price availability, including short series and retained older data.
    # It does not establish freshness, research eligibility, or why a ticker has no history.
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
        "note": ("Symbols with cached price history, including valid short series. Counts do not "
                 "establish freshness or research eligibility. Missing history does not imply an "
                 "inactive or nonexistent instrument; consult history_meta.json for fetch results."),
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
        "note": ("Every universe symbol is scheduled each run, including names without history. "
                 "Valid short series are stored independently of research eligibility. Fetch runs "
                 "concurrently (workers) with one monotonic request/intake deadline. "
                 "skipped_deadline counts symbols without a completed result before deadline_s; "
                 "unfinished requests are bounded by their remaining request/retry budget and are "
                 "not stamped or counted as processed. Failed or partial responses retain cached "
                 "prices and are reported as failures, not fresh successes. "
                 "last_attempt records the timezone-aware UTC run start for completed results. "
                 "Legacy naive attempts receive oldest ordering priority, never freshness proof. "
                 "This ordering clock MUST be persisted state — file mtimes are "
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
