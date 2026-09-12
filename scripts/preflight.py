#!/usr/bin/env python3
"""Desk-only pre-deploy guard.

This gate validates the deterministic research desk and its served dashboard.
Company Intelligence has moved to its own repository and release contract.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timedelta
import glob
import json
import math
import os
import subprocess
import sys

from post_close_integrity import evaluate as evaluate_post_close
from check_research_publication import validate_publication
from fetch_indices import validate_daily_changes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")

fails, warns = [], []


def fail(msg):
    fails.append(msg)


def warn(msg):
    warns.append(msg)


def _detail(result, limit=500):
    err = (result.stderr or "").strip()
    out = (result.stdout or "").strip()
    combined = err + ("\n" + out if out else "") if err else out
    return combined[-limit:].strip()


def load(name):
    """Load a state file; None if missing/unparseable."""
    path = os.path.join(STATE, name)
    if not os.path.exists(path):
        return None, "missing"
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def has_nonfinite(obj):
    if isinstance(obj, float):
        return not math.isfinite(obj)
    if isinstance(obj, dict):
        return any(has_nonfinite(value) for value in obj.values())
    if isinstance(obj, list):
        return any(has_nonfinite(value) for value in obj)
    return False


def check(name, required=True, min_tickers=0, ticker_fields=(), top_keys=()):
    data, err = load(name)
    if data is None:
        (fail if required else warn)(f"{name}: {err}")
        return None
    if has_nonfinite(data):
        fail(f"{name}: contains NaN/Infinity — will break JSON.parse in the browser")
    for key in top_keys:
        if key not in data:
            fail(f"{name}: missing top-level key '{key}'")
    if min_tickers or ticker_fields:
        tickers = data.get("tickers", {})
        if not isinstance(tickers, dict) or len(tickers) < min_tickers:
            fail(f"{name}: only {len(tickers) if isinstance(tickers, dict) else 0} tickers (expected >= {min_tickers})")
        elif ticker_fields:
            for symbol, row in list(tickers.items())[:5]:
                for field in ticker_fields:
                    if not isinstance(row, dict) or row.get(field) is None:
                        fail(f"{name}: ticker {symbol} missing '{field}'")
                        break
    return data


def run_node_check(path):
    return subprocess.run(["node", path], capture_output=True, text=True, timeout=30)


def check_index_daily_change():
    indices, error = load("indices.json")
    if error:
        fail(f"indices.json daily change: {error}")
        return
    for problem in validate_daily_changes(indices):
        fail(f"indices.json daily change: {problem}")
    if isinstance(indices, dict) and not indices.get("daily_change"):
        warn("indices.json: official daily changes unavailable; render unknown, never history-derived daily moves")


def check_code_syntax():
    for path in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.py"))):
        try:
            with open(path, encoding="utf-8") as handle:
                ast.parse(handle.read(), filename=path)
        except SyntaxError as exc:
            fail(f"{os.path.relpath(path, ROOT)}: Python syntax error — {exc.msg} (line {exc.lineno})")

    js_files = sorted(
        path
        for root in (os.path.join(ROOT, "dashboard"), os.path.join(ROOT, "api"))
        for path in glob.glob(os.path.join(root, "*.js"))
        if os.path.isfile(path)
    )
    node_missing = False
    for path in js_files:
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        try:
            result = subprocess.run(["node", "-c", path], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                fail(f"{rel}: JS syntax error —\n{(result.stderr or result.stdout)[:300]}")
        except FileNotFoundError:
            if not node_missing:
                warn("shipped *.js: skipped JS syntax check — 'node' not found on this machine")
                node_missing = True
        except Exception as exc:  # noqa: BLE001
            warn(f"{rel}: JS syntax check errored — {exc}")


def check_provenance():
    path = os.path.join(ROOT, "scripts", "provenance_lint.py")
    if not os.path.exists(path):
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            lines = [line.strip()[2:] for line in result.stdout.splitlines() if line.strip().startswith("x ")]
            fail("provenance: " + ("; ".join(lines) if lines else "provenance_lint.py failed"))
    except Exception as exc:  # noqa: BLE001
        warn(f"provenance_lint.py did not run — {exc}")


def check_rule4():
    path = os.path.join(ROOT, "scripts", "check_rule4.py")
    if not os.path.exists(path):
        fail("check_rule4.py missing — Rule 4 golden cases cannot run")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            fail("check_rule4.py failed — " + _detail(result, 300))
    except Exception as exc:  # noqa: BLE001
        fail(f"check_rule4.py did not run — {exc}")


def check_generated_url_safety():
    path = os.path.join(ROOT, "scripts", "check_generated_url_safety.py")
    if not os.path.exists(path):
        fail("check_generated_url_safety.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            fail("generated URL safety check failed — " + _detail(result))
    except Exception as exc:  # noqa: BLE001
        fail(f"check_generated_url_safety.py did not run — {exc}")


def check_root_ask_hardening():
    path = os.path.join(ROOT, "scripts", "check_root_ask_hardening.mjs")
    if not os.path.exists(path):
        fail("check_root_ask_hardening.mjs missing")
        return
    try:
        result = run_node_check(path)
        if result.returncode != 0:
            fail("root Ask hardening check failed — " + _detail(result))
    except Exception as exc:  # noqa: BLE001
        fail(f"check_root_ask_hardening.mjs did not run — {exc}")
    ui_path = os.path.join(ROOT, "scripts", "check_root_ask_ui.mjs")
    try:
        result = run_node_check(ui_path)
        if result.returncode:
            fail("root Ask UI check failed — " + _detail(result))
    except Exception as exc:
        fail(f"check_root_ask_ui.mjs did not run — {exc}")


def check_root_state_publication():
    """Keep CI-private data off the Desk even if a stale writer recreates it."""
    path = os.path.join(ROOT, "scripts", "check_root_state_publication.py")
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode:
            fail("root state publication check failed — " + _detail(result))
    except Exception as exc:
        fail(f"check_root_state_publication.py did not run — {exc}")


def check_research_publication():
    """Reject restricted signal fields and named-ticker Room verdict fields."""
    signals, signals_err = load("signals.json")
    rooms, rooms_err = load("rooms.json")
    if signals is None:
        fail(f"signals.json: {signals_err}")
    if rooms is None:
        fail(f"rooms.json: {rooms_err}")
    if signals is None or rooms is None:
        return
    for problem in validate_publication(signals, rooms):
        fail(f"research publication: {problem}")
    health, _ = load("health.json")
    if (health or {}).get("status") != "ok" and signals.get("active"):
        fail("research publication: active signals require health status exactly ok")


def check_publish_safety():
    path = os.path.join(ROOT, "scripts", "check_publish_safety.py")
    if not os.path.exists(path):
        fail("check_publish_safety.py missing — publisher race boundary cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode:
            fail("publisher safety check failed — " + _detail(result))
    except Exception as exc:
        fail(f"check_publish_safety.py did not run — {exc}")


def check_routine_contract():
    path = os.path.join(ROOT, "scripts", "check_routine_contract.py")
    if not os.path.exists(path):
        fail("check_routine_contract.py missing — scheduled routine contracts cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode:
            fail("routine contract check failed — " + _detail(result))
    except Exception as exc:
        fail(f"check_routine_contract.py did not run — {exc}")


def check_price_intake():
    for name in ("check_security_identity.py", "check_history_intake.py", "check_market_capture.py",
                 "check_data_freshness.py", "check_signal_health.py", "check_index_daily_gate.py"):
        path = os.path.join(ROOT, "scripts", name)
        try:
            result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
            if result.returncode:
                fail(f"{name} failed — " + _detail(result))
        except Exception as exc:
            fail(f"{name} did not run — {exc}")


def check_today_ui():
    for name in ("check_today_article.mjs", "check_today_chart_data.mjs", "check_today_info.mjs"):
        path = os.path.join(ROOT, "scripts", name)
        if not os.path.exists(path):
            fail(f"{name} missing — Today surface cannot be verified")
            continue
        try:
            result = run_node_check(path)
            if result.returncode != 0:
                fail(f"{name} failed — " + _detail(result))
        except Exception as exc:  # noqa: BLE001
            fail(f"{name} did not run — {exc}")


def check_company_profiles():
    """Validate the shared issuer-profile seam used by Desk Room and explainers."""
    data, err = load("company_profiles.json")
    if data is None:
        fail(f"company_profiles.json: {err}")
        return
    rows = data.get("tickers")
    if not isinstance(rows, dict) or not rows:
        fail("company_profiles.json: missing populated tickers map")
        return
    expected = (data.get("pilot") or {}).get("symbols") or []
    if expected and len(rows) < len(expected):
        fail(f"company_profiles.json: {len(rows)} rows for {len(expected)} pilot symbols")
    for symbol, row in sorted(rows.items()):
        if not isinstance(row, dict):
            fail(f"company_profiles.json: {symbol} row is not an object")
            continue
        if row.get("symbol") != symbol:
            fail(f"company_profiles.json: {symbol} row symbol mismatch")
        if not row.get("source_url"):
            fail(f"company_profiles.json: {symbol} missing source_url")
        if not row.get("business_description") and not row.get("incorporation"):
            fail(f"company_profiles.json: {symbol} has neither business_description nor incorporation")
        if row.get("incorporation") is not None and not isinstance(row.get("incorporation"), dict):
            fail(f"company_profiles.json: {symbol} incorporation is not an object/null")


def check_no_raw_artifacts():
    for root in (
        os.path.join(ROOT, "dashboard"),
        os.path.join(ROOT, "site", "public"),
        os.path.join(ROOT, "site", "dist"),
    ):
        for dirpath, _, files in os.walk(root):
            normalized = dirpath.replace("\\", "/")
            if "node_modules" in normalized or ".cache" in normalized:
                continue
            for name in files:
                if name.lower() == "moon_ephem.bin":
                    continue
                if name.lower().endswith((".pdf", ".bin")) or "reprocess" in name.lower():
                    fail(f"served/raw artifact present: {os.path.relpath(os.path.join(dirpath, name), ROOT)}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--desk", action="store_true", help="accepted for publish.py compatibility")
    args = parser.parse_args()

    check_code_syntax()
    check_provenance()
    check_rule4()
    check_generated_url_safety()
    check_root_ask_hardening()
    check_root_state_publication()
    check_research_publication()
    check_publish_safety()
    check_routine_contract()
    check_price_intake()
    check_today_ui()
    check_index_daily_change()
    check_company_profiles()
    check_no_raw_artifacts()

    # Files the dashboard hard-depends on, with the exact shape the UI reads.
    check("health.json", top_keys=("status",))
    check("quant.json", min_tickers=20, ticker_fields=("rsi14", "ret_20d", "close"))
    check("predictability.json", min_tickers=20)
    check("fairvalue.json", min_tickers=10, ticker_fields=("methods", "composite_fair", "verdict"))
    check("global.json", top_keys=("instruments",))
    check("dashboard.json")
    check("macro.json", top_keys=("regime",))

    global_state, _ = load("global.json")
    if global_state and not global_state.get("instruments"):
        fail("global.json: instruments is empty — ticker tape and macro page go blank")

    fairvalue, _ = load("fairvalue.json")
    if fairvalue:
        empty = [symbol for symbol, row in list(fairvalue.get("tickers", {}).items())[:10] if not row.get("methods")]
        if empty:
            fail(f"fairvalue.json: tickers with empty methods: {', '.join(empty)}")

    universe, _ = load("universe.json")
    quant_previous, _ = load("quant.json")
    previous_symbols = set((quant_previous or {}).get("tickers", {})) if quant_previous else set()
    if universe and isinstance(universe.get("symbols"), dict):
        symbols = list(universe["symbols"])
        history_dir = os.path.join(STATE, "history")
        missing = []
        for symbol in symbols:
            path = os.path.join(history_dir, f"{symbol}.json")
            try:
                if not os.path.exists(path) or os.path.getsize(path) < 20:
                    missing.append(symbol)
                    continue
                with open(path, encoding="utf-8") as handle:
                    if len(json.load(handle)) < 2:
                        missing.append(symbol)
            except Exception:
                missing.append(symbol)
        regressed = [symbol for symbol in missing if symbol in previous_symbols]
        new_backfilling = [symbol for symbol in missing if symbol not in previous_symbols]
        if symbols and len(regressed) / len(symbols) > 0.10:
            fail(f"history/: {len(regressed)}/{len(symbols)} previously-covered tickers lost history")
        elif regressed:
            warn(f"history/: {len(regressed)} previously-covered ticker(s) missing history: {', '.join(regressed[:12])}")
        if new_backfilling:
            warn(f"history/: {len(new_backfilling)} newly-added universe ticker(s) still backfilling history: {', '.join(new_backfilling[:12])}")

    history_meta, _ = load("history_meta.json")
    coverage, _ = load("coverage.json")
    if history_meta and coverage:
        attempted_map = history_meta.get("last_attempt") or {}
        covered = list(coverage.get("bars") or {})
        cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
        unvisited = [symbol for symbol in covered if attempted_map.get(symbol, "") < cutoff]
        if covered and len(unvisited) > 0.10 * len(covered):
            warn(f"history_meta.json: {len(unvisited)}/{len(covered)} covered symbols not attempted since {cutoff}")
        skipped = history_meta.get("skipped_deadline")
        if skipped:
            warn(f"history_meta.json: {skipped} symbol(s) not reached before the fetch deadline")
        attempted = history_meta.get("attempted")
        if attempted is not None and covered and attempted < 0.90 * len(covered):
            warn(f"history_meta.json: last run attempted only {attempted} of {len(covered)} covered symbols")
        failed = history_meta.get("failed")
        ok = history_meta.get("ok")
        failed_count = len(failed) if isinstance(failed, list) else (failed or 0)
        base = attempted or ((ok or 0) + failed_count)
        if base and failed_count > 0.10 * base:
            reasons = Counter()
            if isinstance(failed, list):
                for item in failed:
                    error = (item.get("err") if isinstance(item, dict) else str(item)) or "unknown"
                    reasons[error.split(" on ")[0].strip()] += 1
            top = ", ".join(f"{key}×{value}" for key, value in reasons.most_common(3)) or "unknown"
            warn(f"history_meta.json: {failed_count}/{base} fetches FAILED (>10%); dominant error: {top}")

    post_close = evaluate_post_close()
    if post_close["required"] and post_close["status"] != "ok":
        for problem in post_close["problems"]:
            fail(f"post-close price integrity: {problem}")
    elif post_close["required"]:
        print(f"post-close price integrity: {post_close['same_day_symbols']}/{post_close['traded_symbols']} traded counters current")

    check("dossiers.json", required=False)
    check("room_queue.json", required=False)
    dossiers, _ = load("dossiers.json")
    if dossiers and dossiers.get("_meta", {}).get("n_tickers", 0) < 10:
        warn("dossiers.json: fewer than 10 tickers compiled")

    health, _ = load("health.json")
    if health and health.get("status") not in ("ok", "healthy", None):
        warn(f"health.json status = '{health.get('status')}' — desk is in degraded mode")

    print("Henneth - preflight")
    if warns:
        print(f"\n  WARN ({len(warns)}):")
        for message in warns:
            print(f"    ! {message}")
    if fails:
        print(f"\n  FAIL ({len(fails)}):")
        for message in fails:
            print(f"    x {message}")
        print("\n  RESULT: DO NOT DEPLOY — fix the above first.")
        raise SystemExit(1)
    if args.strict and warns:
        print("\n  RESULT: blocked (--strict, warnings present).")
        raise SystemExit(1)
    print(f"\n  RESULT: OK — all checks passed, safe to deploy.")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
