"""Stable-interface and golden checks for Wave 2 event studies."""
from __future__ import annotations
import json, math
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_studies import add_months, last_before, first_on_or_after, raw_return, HORIZONS, parse_date
from build_event_studies import _analogue_outcomes
import subprocess

ROOT = Path(__file__).resolve().parents[1]; STATE = ROOT / "state"
def load(path):
    with path.open(encoding="utf-8") as f: return json.load(f)
def walk(value):
    if isinstance(value, float) and not math.isfinite(value): raise AssertionError("non-finite value")
    if isinstance(value, dict):
        for x in value.values(): walk(x)
    elif isinstance(value, list):
        for x in value: walk(x)
def main():
    pilot = set((load(STATE / "company_profiles.json").get("pilot") or {}).get("symbols") or [])
    events = load(STATE / "company_intel" / "operating_events.json"); studies = load(STATE / "company_intel" / "event_studies.json")
    walk(studies)
    if set(studies.get("pilot_symbols") or []) != pilot: raise AssertionError("pilot boundary mismatch")
    all_events = [e for row in (events.get("companies") or {}).values() for e in row.get("events") or []]
    sectors_state = load(STATE / "sectors.json").get("tickers") or {}; sectors = {s: (sectors_state.get(s) or {}).get("sector") for s in pilot}; histories = {s: sorted([r for r in load(STATE / "history" / f"{s}.json") if isinstance(r, dict)], key=lambda r: r.get("date") or "") for s in pilot}
    if set(studies.get("studies") or {}) != {e.get("event_id") for e in all_events}: raise AssertionError("one study per canonical event violated")
    for eid, s in studies.get("studies", {}).items():
        day = None
        info_day = s.get("information_available_at") or s.get("effective_date")
        if info_day:
            try: day = date.fromisoformat(info_day[:10])
            except ValueError: pass
        baseline = s.get("baseline") or {}; sym = s.get("symbol"); rows = sorted([r for r in load(STATE / "history" / f"{sym}.json") if isinstance(r, dict)], key=lambda r: r.get("date") or "")
        cutoff = parse_date(rows[-1].get("date")) if rows else None
        if s.get("data_cutoff") != (cutoff.isoformat() if cutoff else None): raise AssertionError(f"cutoff mismatch {eid}")
        expected = None
        if day:
            expected = last_before(rows, day)
            if (baseline.get("selected_date"), baseline.get("selected_close")) != ((expected or {}).get("date"), (expected or {}).get("close")): raise AssertionError(f"baseline not last prior close {eid}")
        expected_baseline_prov = {"history_file": f"state/history/{sym}.json", "selected_date": (expected or {}).get("date") if day else None}
        if baseline.get("provenance") != expected_baseline_prov: raise AssertionError(f"baseline provenance mismatch {eid}")
        if day and set((s.get("horizons") or {})) != {x[0] for x in HORIZONS}: raise AssertionError(f"horizon keys {eid}")
        for name, months in HORIZONS:
            h = (s.get("horizons") or {}).get(name) or {}
            if day and h.get("target_date") != add_months(day, months).isoformat(): raise AssertionError(f"target date {eid}:{name}")
            if h.get("selected_date"):
                if not (parse_date(h["selected_date"]) >= parse_date(h["target_date"])): raise AssertionError(f"endpoint before target {eid}:{name}")
                expected_endpoint = first_on_or_after(rows, parse_date(h["target_date"]), parse_date(s["data_cutoff"]) if s.get("data_cutoff") else None)
                if (expected_endpoint or {}).get("date") != h["selected_date"]: raise AssertionError(f"not first endpoint {eid}:{name}")
                if h.get("return_pct") != raw_return(expected, expected_endpoint): raise AssertionError(f"return mismatch {eid}:{name}")
            expected_endpoint = first_on_or_after(rows, parse_date(h.get("target_date")) if h.get("target_date") else date.max, cutoff)
            expected_horizon_prov = {"history_file": f"state/history/{sym}.json", "baseline_date": (expected or {}).get("date") if day else None, "endpoint_date": h.get("selected_date"), "target_date": h.get("target_date")}
            if h.get("provenance") != expected_horizon_prov: raise AssertionError(f"horizon provenance mismatch {eid}:{name}")
        if day and baseline.get("selected_date") and not (baseline["selected_date"] < (s.get("information_available_at") or s["effective_date"])): raise AssertionError(f"baseline lookahead {eid}")
        idx = load(STATE / "indices.json").get("history") or {}
        for name, _ in HORIZONS:
            kse = s.get("kse100_relative") or {}; value = (kse.get("relative_return_pct") or {}).get(name)
            h = (s.get("horizons") or {}).get(name) or {}
            d0, d1 = baseline.get("selected_date"), h.get("selected_date"); available = bool(d0 and d1 and d0 in idx and d1 in idx and isinstance((idx.get(d0) or {}).get("KSE100"), (int, float)) and isinstance((idx.get(d1) or {}).get("KSE100"), (int, float)) and h.get("return_pct") is not None and h.get("status") == "mature")
            expected_stock = h.get("return_pct") if available else None; expected_index = raw_return({"close": idx[d0]["KSE100"]}, {"close": idx[d1]["KSE100"]}) if available else None; expected_rel = expected_stock - expected_index if available else None
            if (kse.get("stock_return_pct") or {}).get(name) != expected_stock or (kse.get("index_return_pct") or {}).get(name) != expected_index or value != expected_rel: raise AssertionError(f"KSE full value mismatch {eid}:{name}")
            expected_reason = None if available else ("missing_exact_index_dates" if d0 and d1 else ("invalid_effective_date" if not day else "missing_exact_index_dates"))
            if (kse.get("reasons") or {}).get(name) != expected_reason: raise AssertionError(f"KSE reason mismatch {eid}:{name}")
            if kse.get("semantics") != "stock_raw_price_return_minus_KSE100_raw_price_return": raise AssertionError(f"KSE semantics {eid}:{name}")
            prov = kse.get("provenance") or {}
            if prov.get("indices_file") != "state/indices.json" or (prov.get("selected_dates") or {}).get(name) != [d0, d1]: raise AssertionError(f"KSE provenance {eid}:{name}")
        if not day and baseline.get("status") != "unavailable": raise AssertionError(f"malformed date {eid}")
        for name, h in (s.get("horizons") or {}).items():
            if h.get("status") == "mature" and (h.get("selected_date") is None or h.get("return_pct") is None): raise AssertionError(f"mature horizon incomplete {eid}:{name}")
            if h.get("status") == "immature" and h.get("return_pct") is not None: raise AssertionError(f"immature horizon numeric {eid}:{name}")
        expected_analogues, expected_aggregate = _analogue_outcomes(next(e for e in all_events if e.get("event_id") == eid), all_events, sectors, histories)
        if s.get("analogues") != expected_analogues or s.get("analogue_aggregate") != expected_aggregate: raise AssertionError(f"analogue recomputation mismatch {eid}")
        for a in s.get("analogues") or []:
            if a.get("event_id") == eid: raise AssertionError(f"analogue self inclusion {eid}")
            if a.get("classification") not in {"same_company", "same_sector"}: raise AssertionError(f"analogue class {eid}")
            for name, _ in HORIZONS:
                o = (a.get("outcomes") or {}).get(name) or {}
                crows = histories.get(a.get("symbol")) or []; cday = parse_date(a.get("effective_date")); cbase = last_before(crows, cday) if cday else None; target = add_months(cday, dict(HORIZONS)[name]) if cday else None
                expected_a_prov = {"history_file": f"state/history/{a.get('symbol')}.json", "baseline_date": cbase.get("date") if cbase else None, "target_date": target.isoformat() if target else None, "endpoint_date": o.get("endpoint_date")}
                if o.get("provenance") != expected_a_prov: raise AssertionError(f"analogue provenance mismatch {eid}:{name}")
        agg = s.get("analogue_aggregate") or {}
        if set(agg) != {x[0] for x in HORIZONS}: raise AssertionError(f"aggregate horizons {eid}")
        for name, _ in HORIZONS:
            if agg[name].get("n", 0) < 3 and agg[name].get("mean_return_pct") is not None: raise AssertionError(f"thin analogue aggregate {eid}:{name}")
        financial = s.get("financial_outcomes") or {}
        if set(financial) != {"revenue", "margin", "eps", "roic", "fcf", "valuation", "missing_inputs"}: raise AssertionError(f"financial outcome keys {eid}")
        if any(financial.get(k) is not None for k in ("revenue", "margin", "eps", "roic", "fcf", "valuation")) or not financial.get("missing_inputs"): raise AssertionError(f"financial outcomes {eid}")
        if any(x in json.dumps(s).lower() for x in ("caused", "will lead", "you should buy", "you should sell")): raise AssertionError(f"causal/advice copy {eid}")
    # Golden helper cases: month-end clamping, strict baseline, first on/after, raw return.
    if add_months(date(2024, 1, 31), 1) != date(2024, 2, 29): raise AssertionError("calendar horizon")
    rows = [{"date": "2024-01-01", "close": 10}, {"date": "2024-01-10", "close": 11}, {"date": "2024-02-01", "close": 12}]
    if last_before(rows, date(2024, 1, 10))["date"] != "2024-01-01": raise AssertionError("strict baseline")
    if first_on_or_after(rows, date(2024, 1, 15))["date"] != "2024-02-01": raise AssertionError("first on/after")
    if round(raw_return(rows[0], rows[2]), 4) != 20.0: raise AssertionError("raw return")
    # Exact-date KSE golden: 10->12 stock (+20%), 100->110 index (+10%) => +10% relative.
    if round(raw_return({"close": 10}, {"close": 12}) - raw_return({"close": 100}, {"close": 110}), 4) != 10.0: raise AssertionError("KSE relative subtraction")
    exact_idx = {"2024-01-01": {"KSE100": 100.0}, "2024-02-01": {"KSE100": 110.0}}
    if round(raw_return({"close": exact_idx["2024-01-01"]["KSE100"]}, {"close": exact_idx["2024-02-01"]["KSE100"]}), 6) != 10.0: raise AssertionError("KSE exact-date available")
    if "2024-01-15" in exact_idx: raise AssertionError("KSE missing-date fixture")
    # Explicit regression: PSO FY25 network expansion published 2025-10-02 must use 2025-10-01 baseline
    pso_study = (studies.get("studies") or {}).get("evt_efe3e2c704a0e53e7d09")
    if not pso_study:
        raise AssertionError("missing PSO network expansion study evt_efe3e2c704a0e53e7d09")
    if pso_study.get("effective_date") != "2025-06-30":
        raise AssertionError("PSO study effective_date must be 2025-06-30")
    if pso_study.get("information_available_at") != "2025-10-02":
        raise AssertionError("PSO study information_available_at must be 2025-10-02")
    if (pso_study.get("baseline") or {}).get("selected_date") != "2025-10-01":
        raise AssertionError("PSO study baseline date must be 2025-10-01 (day before publication)")
    if (pso_study.get("baseline") or {}).get("selected_close") != 470.09:
        raise AssertionError("PSO study baseline close must be 470.09 PKR on 2025-10-01")
    # Explicit regression: future-effective announcement (published 2026-01-10, effective 2026-12-31)
    from build_event_studies import _event_cutoff_date
    future_announcement = {"event_id": "evt_future_test", "published_at": "2026-01-10T10:00:00+05:00", "effective_date": "2026-12-31"}
    cutoff_dt, cutoff_str = _event_cutoff_date(future_announcement)
    if cutoff_str != "2026-01-10" or cutoff_dt != date(2026, 1, 10):
        raise AssertionError(f"future-effective announcement did not anchor on publication date 2026-01-10: got {cutoff_str}")
    # Re-run the authoritative builder and require byte-identical output.
    target = STATE / "company_intel" / "event_studies.json"; before = target.read_bytes(); result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_event_studies.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or target.read_bytes() != before: raise AssertionError("builder is not idempotent")
    print(f"event_studies: PASS ({len(all_events)} studies, {len(pilot)} pilot companies)")
if __name__ == "__main__": main()
