"""Data health gate. Writes state/health.json. If status != ok, the desk
generates NO new signals this cycle (monitoring continues). Checks:
- universe exists and is fresh enough
- history covers >= 90% of universe and the freshest last date is recent (weekends/holidays allowed)
- the FLEET is fresh, not just the freshest symbol — see STALE_FLEET_DAYS
- a live spot-check price is sane vs cached close (catches decimal/parse breakage)."""
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from psx_data import STATE, intraday_last, load_json, save_json
from post_close_integrity import evaluate as evaluate_post_close

MAX_STALE_SESSIONS_DAYS = 5  # last EOD date may lag this many calendar days
STALE_FLEET_DAYS = 12
REFRESH_RECENT_HOURS = 24
ATTEMPT_COMPLETION_MAX_MINUTES = 30
PKT = ZoneInfo("Asia/Karachi")


def _aware_stamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _positive_volume(row):
    try:
        return float((row or {}).get("volume") or 0) > 0
    except (AttributeError, TypeError, ValueError):
        return False


def _verified_snapshot_session(root: Path, post_close: dict, now: datetime):
    live = load_json(root / "live.json", {})
    session = live.get("session_date")
    source_at = _aware_stamp(live.get("source_at"))
    if not isinstance(session, str) or source_at is None:
        return None, "snapshot source/session is missing or timezone-ambiguous"
    if source_at > now or source_at.astimezone(PKT).date().isoformat() != session:
        return None, "snapshot source/session is future-dated or mismatched"
    if post_close.get("required"):
        if post_close.get("status") != "ok":
            return None, "post-close snapshot verification is not ok"
        if post_close.get("session_date") != session:
            return None, "snapshot session does not match the post-close target"
    elif now - source_at > timedelta(hours=REFRESH_RECENT_HOURS):
        return None, "snapshot source is not recent"
    return session, None


def _history_refresh_proof(root: Path, universe: dict, post_close: dict, now: datetime) -> dict:
    """Return proof that each symbol was part of the completed refresh run.

    `last_attempt` must declare its offset; legacy naive clocks cannot certify freshness.
    A run is proven only when every source identity shares one recent UTC attempt minute, the
    completion is recent, the full universe was processed, and the verified snapshot identifies
    the target session. A missing or ambiguous proof never downgrades stale data to an advisory.
    """
    symbols = set((universe.get("symbols") or {}))
    meta = load_json(root / "history_meta.json", None)
    coverage = load_json(root / "coverage.json", None)
    reasons = []
    failed = set()
    completed = None

    if not isinstance(meta, dict):
        reasons.append("history_meta.json is missing or not an object")
    else:
        completed = _aware_stamp(meta.get("completed_at"))
        if completed is None:
            reasons.append("completed_at is missing or timezone-ambiguous")
        elif completed > now or now - completed > timedelta(hours=REFRESH_RECENT_HOURS):
            reasons.append("completed_at is not recent")
        failed_rows = meta.get("failed")
        if not isinstance(failed_rows, list):
            reasons.append("failed results are missing")
        else:
            for row in failed_rows:
                symbol = row.get("symbol") if isinstance(row, dict) else None
                if not isinstance(symbol, str) or symbol not in symbols or symbol in failed:
                    reasons.append("failed results contain an unknown or duplicate symbol")
                    continue
                failed.add(symbol)
        if type(meta.get("skipped_deadline")) is not int or meta.get("skipped_deadline") != 0:
            reasons.append("refresh has skipped symbols")
        if type(meta.get("attempted")) is not int or type(meta.get("processed")) is not int or \
                meta.get("attempted") != len(symbols) or meta.get("processed") != len(symbols):
            reasons.append("refresh did not attempt and process the full universe")
        if type(meta.get("ok")) is not int or meta.get("ok") + len(failed) != len(symbols):
            reasons.append("refresh result counts do not account for the full universe")
        attempts = meta.get("last_attempt")
        parsed_attempts = []
        if not isinstance(attempts, dict):
            reasons.append("last_attempt is missing")
        else:
            for symbol in symbols:
                parsed = _aware_stamp(attempts.get(symbol))
                if parsed is None:
                    reasons.append(f"last_attempt is missing, invalid, or timezone-ambiguous for {symbol}")
                else:
                    parsed_attempts.append(parsed)
        if parsed_attempts and completed is not None:
            run_minutes = set(parsed.astimezone(timezone.utc).replace(second=0, microsecond=0)
                              for parsed in parsed_attempts)
            completed_minute = completed.astimezone(timezone.utc).replace(second=0, microsecond=0)
            if len(run_minutes) != 1:
                reasons.append("last_attempt does not identify one completed run")
            else:
                run_minute = next(iter(run_minutes))
                if run_minute > completed_minute or completed_minute - run_minute > timedelta(minutes=ATTEMPT_COMPLETION_MAX_MINUTES):
                    reasons.append("last_attempt is not from the completed refresh run")

    if not isinstance(coverage, dict) or not isinstance(coverage.get("bars"), dict):
        reasons.append("coverage bars are missing")
    else:
        bars = set(coverage["bars"])
        if (type(coverage.get("n_universe")) is not int or
                type(coverage.get("n_with_history")) is not int or
                coverage.get("n_universe") != len(symbols) or
                coverage.get("n_with_history") != len(bars)):
            reasons.append("coverage metadata does not describe the full universe")
        if bars != symbols:
            reasons.append("coverage does not contain every source identity")

    _session, snapshot_problem = _verified_snapshot_session(root, post_close, now)
    if snapshot_problem:
        reasons.append(snapshot_problem)

    return {
        "ok": not reasons,
        "successful": symbols - failed if not reasons else set(),
        "failed": failed,
        "reason": "; ".join(dict.fromkeys(reasons)),
    }


def _current_positive_volume(root: Path, symbol: str, session: str) -> bool:
    ohlc = load_json(root / "ohlc_daily" / f"{session}.json", {})
    if _positive_volume(ohlc.get(symbol)):
        return True
    live = load_json(root / "live.json", {})
    return _positive_volume((live.get("tickers") or {}).get(symbol))


def assess_history_freshness(root: Path, universe: dict, post_close: dict, now: datetime) -> dict:
    """Classify old bars without inferring that an instrument is suspended."""
    symbols = [s for s, m in (universe.get("symbols") or {}).items()
               if ((m or {}).get("market") or "PSX") == "PSX"]
    fleet_cutoff = (now.astimezone(PKT).date() - timedelta(days=STALE_FLEET_DAYS)).isoformat()
    have, latest, oldest = 0, None, None
    stale = {}
    for symbol in symbols:
        history = load_json(root / "history" / f"{symbol}.json", None)
        if not history:
            continue
        have += 1
        last_date = history[-1]["date"]
        latest = max(latest, last_date) if latest else last_date
        oldest = min(oldest, last_date) if oldest else last_date
        if last_date < fleet_cutoff:
            stale[symbol] = last_date

    problems = []
    advisories = []
    if symbols:
        coverage = have / len(symbols)
        if coverage < 0.9:
            problems.append(f"history coverage {coverage:.0%}")
        if latest and (now.astimezone(PKT).date() - datetime.strptime(latest, "%Y-%m-%d").date()).days > MAX_STALE_SESSIONS_DAYS:
            problems.append(f"history stale (latest {latest})")

    proof = _history_refresh_proof(root, universe, post_close, now)
    if proof["failed"]:
        problems.append("history refresh failed for " + ", ".join(sorted(proof["failed"])))

    dated = {}
    gated = {}
    if stale:
        if proof["ok"]:
            session, _ = _verified_snapshot_session(root, post_close, now)
            for symbol, last_date in stale.items():
                if symbol in proof["successful"] and session and not _current_positive_volume(root, symbol, session):
                    dated[symbol] = last_date
                else:
                    gated[symbol] = last_date
            if dated:
                details = "; ".join(f"{s}={dated[s]}" for s in sorted(dated))
                advisories.append("dated_last_trade (informational; no suspension inferred): " + details)
            if gated:
                details = "; ".join(f"{s}={gated[s]}" for s in sorted(gated))
                problems.append("active positive-volume or unproven stale history remains gating: " + details)
        else:
            details = "; ".join(f"{s}={stale[s]}" for s in sorted(stale))
            problems.append(
                f"history freshness proof unavailable ({proof['reason']}); stale history remains gating: {details}")

    return {
        "problems": problems,
        "advisories": advisories,
        "history_symbols": have,
        "latest_eod": latest,
        "oldest_eod": oldest,
        "stale_fleet": len(stale),
        "stale_fleet_fraction": round(len(stale) / len(symbols), 4) if symbols else None,
        "stale_fleet_cutoff": fleet_cutoff,
    }


def main():
    problems = []
    now = datetime.now(timezone.utc)
    universe = load_json(STATE / "universe.json", None)
    if not universe:
        problems.append("universe.json missing")
        syms, foreign = [], []
    else:
        # The denominator is the actual source universe, not the subset successfully fetched.
        # Compliance badges are not separate securities. Excluding missing histories from both
        # numerator and denominator would hide intake failures behind a 100% coverage claim.
        #
        # NON-PSX SYMBOLS ARE EXCLUDED FROM THIS GATE, deliberately. Under Rule 6 a degraded
        # status halts every new signal, and the desk's signals are PSX-only (US coverage is
        # research-tier — config/markets.json signals_enabled:false). A Yahoo hiccup on XLE must
        # not be able to stop the desk publishing PSX research. Their freshness is still reported
        # below as `foreign_*`, so a US outage is visible; it just cannot gate the home market.
        home = [s for s, m in universe["symbols"].items()
                if ((m or {}).get("market") or "PSX") == "PSX"]
        syms = list(home)
        foreign = [s for s in universe["symbols"] if s not in set(home)]
        upd = datetime.strptime(universe["updated"][:10], "%Y-%m-%d").date()
        if (date.today() - upd).days > 10:
            problems.append(f"universe stale ({universe['updated']})")

    post_close = evaluate_post_close(now=now)
    history_result = assess_history_freshness(
        STATE, universe or {"symbols": {}}, post_close, now,
    )
    problems.extend(history_result["problems"])

    # live sanity spot-check on a heavyweight
    spot = None
    for probe in ("HUBC", "OGDC", "LUCK"):
        try:
            tick = intraday_last(probe)
            h = load_json(STATE / "history" / f"{probe}.json", None)
            if tick and h:
                ref = h[-1]["close"]
                dev = abs(tick["price"] / ref - 1)
                spot = {"symbol": probe, "live": tick["price"], "cached_close": ref,
                        "deviation_pct": round(dev * 100, 2)}
                if dev > 0.15:
                    problems.append(f"{probe} live {tick['price']} vs cached {ref} deviates {dev:.0%}")
                break   # a comparison was actually made — that is what ends the loop
            # No exception, but no usable pair either (intraday_last returned nothing, or the
            # history file is missing). The `break` used to sit out here, so the fallbacks after
            # HUBC were unreachable and a silent None left spot_check null with no problem logged.
        except Exception:  # noqa: BLE001
            continue

    # TradingView cross-check (if run this session): only a GENUINE error degrades health.
    # tv_crosscheck now separates real glitches (`fails`: close off >12%, i.e. decimal/split/
    # wrong-symbol) from explainable `drift` (TV's 15-min lag + adjusted-vs-unadjusted feed).
    # Per CLAUDE.md a TV-vs-DPS mismatch is NOT an error, so `drift` never degrades health.
    cc = load_json(STATE / "crosscheck.json", None)
    cc_drift = []
    if cc and cc.get("updated", "")[:10] == time.strftime("%Y-%m-%d"):
        if cc.get("fails"):
            problems.append(f"tv_crosscheck ERROR (likely data glitch): {', '.join(cc['fails'])}")
        cc_drift = cc.get("drift", [])

    # Calendar freshness (Ramadan guard, CLAUDE.md): if session times haven't been re-verified
    # in 60 days, degrade — force a human check rather than silently trading wrong hours.
    cal = load_json(STATE / "calendar.json", {})
    stu = cal.get("session_times_updated")
    try:
        age = (date.today() - datetime.strptime(stu, "%Y-%m-%d").date()).days if stu else 9999
        if age > 60:
            problems.append(f"stale_calendar: session times last verified {stu or 'never'} ({age}d ago) — re-check vs PSX/SBP notice")
    except (ValueError, TypeError):
        problems.append("stale_calendar: session_times_updated missing/unparseable in calendar.json")

    # Non-PSX coverage: REPORTED, never gating (see the note above `home`). A US outage shows up
    # here as an advisory so it is visible and fixable, without halting PSX signals under Rule 6.
    f_have = sum(1 for s in foreign if load_json(STATE / "history" / f"{s}.json", None))

    if post_close["required"] and post_close["status"] != "ok":
        problems.extend(f"post_close_integrity: {p}" for p in post_close["problems"])
    advisories = list(history_result["advisories"])
    if cc_drift:
        advisories.insert(0, f"tv drift (lag/adjustment, not an error): {', '.join(cc_drift)}")
    if foreign and f_have < len(foreign):
        advisories.append(f"non-PSX history {f_have}/{len(foreign)} — research-tier only, does not gate signals")
    status = "ok" if not problems else "degraded"
    save_json(STATE / "health.json", {
        "checked": time.strftime("%Y-%m-%d %H:%M"),
        "status": status,
        "problems": problems,
        "advisories": advisories,
        "history_symbols": history_result["history_symbols"],
        "universe_symbols": len(syms),
        "history_coverage_fraction": round(history_result["history_symbols"] / len(syms), 4) if syms else None,
        "foreign_symbols": len(foreign),
        "foreign_with_history": f_have,
        "latest_eod": history_result["latest_eod"],
        # Reported even when under threshold: `latest_eod` alone reads green during a total
        # rotation failure, so the fleet numbers are what make that failure visible at a glance.
        "oldest_eod": history_result["oldest_eod"],
        "stale_fleet": history_result["stale_fleet"],
        "stale_fleet_fraction": history_result["stale_fleet_fraction"],
        "stale_fleet_cutoff": history_result["stale_fleet_cutoff"],
        "spot_check": spot,
        "post_close_integrity": post_close,
    })
    print(f"health: {status}" + (f" — {'; '.join(problems)}" if problems else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
