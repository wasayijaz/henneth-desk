"""Build one deterministic historical benchmark study for every operating event."""
from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psx_data import STATE, load_json, save_json
from event_studies import HORIZONS, parse_date, last_before, horizon_result, first_on_or_after, raw_return, add_months

OUT = STATE / "company_intel" / "event_studies.json"

def _history(sym):
    rows = load_json(STATE / "history" / f"{sym}.json", [])
    return sorted([r for r in rows if isinstance(r, dict)], key=lambda r: r.get("date") or "")

def _index_history():
    return load_json(STATE / "indices.json", {}).get("history") or {}

def _last_day(rows):
    return parse_date(rows[-1].get("date")) if rows else None

def _event_cutoff_date(event):
    detected = event.get("detected_at") or event.get("published_at") or event.get("available_date")
    detected_day = parse_date(detected[:10]) if isinstance(detected, str) and len(detected) >= 10 else None
    effective_day = parse_date(event.get("effective_date"))
    if detected_day and effective_day and detected_day > effective_day:
        return detected_day, detected[:10] if isinstance(detected, str) else detected_day.isoformat()
    eff_str = event.get("effective_date")
    return effective_day, eff_str

def _analogue_outcomes(event, all_events, sectors, histories):
    target_day, _ = _event_cutoff_date(event); etype = event.get("event_type"); sym = event.get("symbol")
    target_sector = sectors.get(sym)
    candidates = []
    for candidate in all_events:
        if candidate.get("event_id") == event.get("event_id") or candidate.get("event_type") != etype: continue
        cday, _ = _event_cutoff_date(candidate)
        if not target_day or not cday or cday >= target_day: continue
        csym = candidate.get("symbol")
        classification = "same_company" if csym == sym else ("same_sector" if sectors.get(csym) == target_sector else None)
        if not classification: continue
        rows = histories.get(csym) or []; base = last_before(rows, cday)
        outcomes = {}
        for name, months in HORIZONS:
            endpoint = first_on_or_after(rows, add_months(cday, months), target_day - timedelta(days=1))
            ret = raw_return(base, endpoint)
            outcomes[name] = {"endpoint_date": endpoint.get("date") if endpoint else None, "return_pct": ret, "status": "mature" if ret is not None else "unavailable", "reason": None if ret is not None else "no_ex_ante_endpoint", "provenance": {"history_file": f"state/history/{csym}.json", "baseline_date": base.get("date") if base else None, "target_date": add_months(cday, months).isoformat(), "endpoint_date": endpoint.get("date") if endpoint else None}}
        candidates.append({"event_id": candidate.get("event_id"), "symbol": csym, "classification": classification, "effective_date": candidate.get("effective_date"), "outcomes": outcomes})
    candidates.sort(key=lambda x: (x.get("effective_date") or "", x.get("event_id") or ""), reverse=True)
    aggregate = {}
    for name, _ in HORIZONS:
        mature = [x for x in candidates if (x.get("outcomes", {}).get(name) or {}).get("status") == "mature"]
        aggregate[name] = {"n": len(mature), "mean_return_pct": sum(x["outcomes"][name]["return_pct"] for x in mature) / len(mature) if len(mature) >= 3 else None, "status": "available" if len(mature) >= 3 else "suppressed", "reason": None if len(mature) >= 3 else "n_lt_3"}
    return candidates, aggregate

def build():
    profiles = load_json(STATE / "company_profiles.json", {}); pilot = set((profiles.get("pilot") or {}).get("symbols") or [])
    # The CI artifact finalizer stamps this generated file with a release envelope.
    # Preserve that envelope when rebuilding so a checker-triggered repeat run is
    # byte-stable; the finalizer will refresh it at the end of the next full cycle.
    existing = load_json(OUT, {})
    existing_meta = existing.get("_meta") if isinstance(existing, dict) else None
    event_state = load_json(STATE / "company_intel" / "operating_events.json", {}); sector_state = load_json(STATE / "sectors.json", {}).get("tickers") or {}
    sectors = {s: (sector_state.get(s) or {}).get("sector") for s in pilot}; histories = {s: _history(s) for s in pilot}; indices = _index_history()
    events = [e for s in sorted(pilot) for e in ((event_state.get("companies", {}).get(s) or {}).get("events") or [])]
    studies = {}
    for event in events:
        sym = event.get("symbol"); rows = histories.get(sym) or []; day, info_avail = _event_cutoff_date(event); baseline = last_before(rows, day) if day else None; last_day = _last_day(rows)
        horizons = {name: horizon_result(rows, baseline, day, months, last_day) for name, months in HORIZONS}
        rel = {name: None for name, _ in HORIZONS}; stock_map = {name: None for name, _ in HORIZONS}; index_map = {name: None for name, _ in HORIZONS}; reasons = {name: ("invalid_effective_date" if not day else "missing_exact_index_dates") for name, _ in HORIZONS}
        if day and baseline:
            for name, months in HORIZONS:
                h = horizons[name]; stock_dates = (baseline.get("date"), h.get("selected_date"))
                if h.get("status") == "mature" and all(d in indices and isinstance(indices[d].get("KSE100"), (int, float)) for d in stock_dates):
                    stock_ret = h.get("return_pct"); index_ret = raw_return({"close": indices[stock_dates[0]]["KSE100"]}, {"close": indices[stock_dates[1]]["KSE100"]})
                    stock_map[name], index_map[name] = stock_ret, index_ret; rel[name] = stock_ret - index_ret if stock_ret is not None and index_ret is not None else None; reasons[name] = None if rel[name] is not None else "missing_index_value"
        analogues, aggregate = _analogue_outcomes(event, events, sectors, histories)
        for name, h in horizons.items(): h["provenance"] = {"history_file": f"state/history/{sym}.json", "baseline_date": baseline.get("date") if baseline else None, "endpoint_date": h.get("selected_date"), "target_date": h.get("target_date")}
        studies[event["event_id"]] = {"study_id": "study_" + event["event_id"].removeprefix("evt_"), "event_id": event["event_id"], "symbol": sym, "event_type": event.get("event_type"), "effective_date": event.get("effective_date"), "information_available_at": info_avail, "data_cutoff": last_day.isoformat() if last_day else None, "baseline": {"selected_date": baseline.get("date") if baseline else None, "selected_close": baseline.get("close") if baseline else None, "status": "available" if baseline else "unavailable", "reason": None if baseline else ("invalid_effective_date" if not day else "no_baseline_close"), "provenance": {"history_file": f"state/history/{sym}.json", "selected_date": baseline.get("date") if baseline else None}}, "horizons": horizons, "kse100_relative": {"stock_return_pct": stock_map, "index_return_pct": index_map, "relative_return_pct": rel, "returns_pct": rel, "semantics": "stock_raw_price_return_minus_KSE100_raw_price_return", "reasons": reasons, "provenance": {"indices_file": "state/indices.json", "selected_dates": {name: [baseline.get("date") if baseline else None, (horizons[name].get("selected_date"))] for name, _ in HORIZONS}}}, "analogues": analogues, "analogue_aggregate": aggregate, "financial_outcomes": {"revenue": None, "margin": None, "eps": None, "roic": None, "fcf": None, "valuation": None, "missing_inputs": ["period_aligned_financials", "event_attribution_model"]}, "limitations": ["raw_price_return_not_adjusted_or_total_return", "historical_association_not_causal", "current_sector_analogues_survivorship_bias"]}
    out = {"schema_version": 1, "pilot_symbols": sorted(pilot), "study_count": len(studies), "studies": studies, "source": "state/company_intel/operating_events.json + state/history + state/indices.json"}
    if isinstance(existing_meta, dict):
        out["_meta"] = existing_meta
    save_json(OUT, out); print(f"event_studies: {len(studies)} studies across {len(pilot)} pilot companies"); return out
if __name__ == "__main__": build()
