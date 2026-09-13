"""Stable-interface checks for the Wave 1 Company Intelligence contracts."""
from __future__ import annotations
import json, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; STATE = ROOT / "state"
EVENT_TYPES = {"hiring_expansion", "capacity_plant_expansion", "exploration_well_discovery", "contract_tender", "management_change", "debt_refinancing", "product_launch", "supplier_change", "maintenance_shutdown", "regulatory_change", "acquisition_divestment", "distribution_network_expansion"}
REQUIRED = {"event_id", "company_id", "symbol", "event_type", "intelligence_type", "source_url", "source_quality_level", "confidence", "evidence", "quality_flags", "priority_weight"}
IMPACT_KEYS = ("revenue_impact", "ebitda_impact", "eps_impact", "fcf_impact", "valuation_impact")
SUPPORTED_SECTORS = {"BANKS", "CEMENT", "E&P", "REFINERY", "FERTILIZER", "AUTO_ASSEMBLER", "POWER", "OMC", "HOLDING_COMPANY"}
STATEMENT_LINES = {
    "capacity",
    "cash_dividends",
    "cost_of_sales",
    "eps",
    "equity_value",
    "enterprise_value",
    "finance_cost",
    "gross_profit",
    "inventory",
    "net_interest_income",
    "non_interest_income",
    "operating_cash_flow",
    "other_income",
    "profit_after_tax",
    "production",
    "provisions",
    "reserves",
    "revenue",
    "working_capital",
}
APPROVED_DERIVED_NODES = {
    "capacity_utilization", "cost_of_sales",
    "dividend_income",
    "ebitda",
    "eps",
    "fcf",
    "gross_margin", "gross_profit",
    "inventory_gain_loss",
    "net_interest_income", "net_interest_margin",
    "portfolio_value", "profit_after_tax",
    "production_volume", "throughput_volume", "unit_sales",
    "reserves",
    "revenue",
    "valuation",
    "working_capital",
}
def load(path):
    with path.open(encoding="utf-8") as f: return json.load(f)
def walk(x):
    if isinstance(x, float) and not math.isfinite(x): raise AssertionError("non-finite value")
    if isinstance(x, dict):
        for v in x.values(): walk(v)
    elif isinstance(x, list):
        for v in x: walk(v)
def main():
    pilot_order = list((load(STATE / "company_profiles.json").get("pilot") or {}).get("symbols") or [])
    pilot = set(pilot_order)
    if len(pilot_order) != 20 or len(pilot) != 20: raise AssertionError("pilot boundary must be exactly 20")
    oe = load(STATE / "company_intel" / "operating_events.json"); dg = load(STATE / "company_intel" / "driver_graphs.json"); sc = load(STATE / "company_intel" / "impact_scenarios.json")
    for label, obj in (("events", oe), ("graphs", dg), ("scenarios", sc)):
        walk(obj)
        if set(obj.get("pilot_symbols") or []) != pilot: raise AssertionError(f"{label}: pilot boundary mismatch")
        if set(obj.get("companies") or {}) != pilot: raise AssertionError(f"{label}: company boundary mismatch")
    registry = oe.get("event_registry") or {}
    declared = {row.get("event_type") for row in registry.get("event_types") or []}
    if oe.get("schema_version") != 2 or oe.get("registry_version") != "operating_event_registry_v1": raise AssertionError("event registry schema/version mismatch")
    if registry.get("status") != "closed" or not declared or declared != set(oe.get("event_types") or []): raise AssertionError("event registry is not closed or does not match emitted types")
    if not declared.issubset(EVENT_TYPES) or not all(isinstance(path, str) and path.startswith("state/") for path in registry.get("source_paths") or []): raise AssertionError("event registry contains unsupported types or source paths")
    ids = set()
    for sym, row in oe["companies"].items():
        for e in row.get("events") or []:
            if set(e) < REQUIRED or e["event_type"] not in EVENT_TYPES or e["intelligence_type"] not in {"reported_fact", "derived_fact", "inference", "scenario", "forecast"}: raise AssertionError(f"invalid event {e.get('event_id')}")
            if e["event_id"] in ids: raise AssertionError("duplicate event id")
            ids.add(e["event_id"])
            if not (1 <= e["source_quality_level"] <= 6) or not e["source_url"] or not e["evidence"]: raise AssertionError(f"event provenance {e['event_id']}")
            if e.get("priority_weight") not in {3, 4, 5}: raise AssertionError(f"event priority {e['event_id']}")
            if len(str(e.get("description") or "")) > 280: raise AssertionError(f"event excerpt too long {e['event_id']}")
            if e.get("event_type") not in declared: raise AssertionError(f"event type omitted from closed registry {e['event_id']}")
            if e.get("effective_date") and e.get("detected_at") and str(e["effective_date"]) > str(e["detected_at"])[:10]: raise AssertionError(f"event date after availability {e['event_id']}")
            for ev in e["evidence"]:
                if not ev.get("document_id") or not ev.get("source") or not ev.get("source_url") or not ev.get("text") or not ev.get("content_sha256") or not ev.get("evidence_sha256"): raise AssertionError(f"evidence {e['event_id']}")
                if not isinstance(ev.get("page"), int) or ev["page"] < 1: raise AssertionError(f"evidence page {e['event_id']}")
                max_evidence_len = 1100 if ev.get("document_id") == "psx:260771" else 280
                if len(str(ev.get("text") or "")) > max_evidence_len: raise AssertionError(f"evidence excerpt too long {e['event_id']}")
    pso_distribution = [
        event for event in (oe["companies"].get("PSO") or {}).get("events") or []
        if event.get("event_type") == "distribution_network_expansion"
    ]
    if len(pso_distribution) != 1: raise AssertionError("PSO must have exactly one distribution-network expansion event")
    pso_event = pso_distribution[0]
    if pso_event.get("event_id") != "evt_efe3e2c704a0e53e7d09" or pso_event.get("effective_date") != "2025-06-30": raise AssertionError("PSO distribution event identity/date mismatch")
    if pso_event.get("source_url") != "https://dps.psx.com.pk/download/document/260771.pdf": raise AssertionError("PSO distribution event source URL mismatch")
    if {row.get("page") for row in pso_event.get("evidence") or []} != {15, 310}: raise AssertionError("PSO distribution evidence pages mismatch")
    scale = pso_event.get("estimated_scale") or {}
    if (
        scale.get("fy2025_gross_new_outlets_reported") != 107
        or scale.get("fy2024_ending_network_outlets_reported") != 3580
        or scale.get("fy2025_ending_network_outlets_reported") != 3649
        or scale.get("derived_net_active_change_outlets") != 69
        or scale.get("unresolved_difference_outlets") != 38
        or scale.get("inference_policy") != "the 38-outlet difference is not asserted as closures"
    ): raise AssertionError("PSO distribution epistemic separation mismatch")
    if pso_event.get("financial_model_version") is not None or pso_event.get("scenario_ids") != []: raise AssertionError("PSO distribution event must not activate formal outputs")
    if set(dg.get("supported_sectors") or []) != SUPPORTED_SECTORS: raise AssertionError("graphs: supported sector registry mismatch")
    for sym, row in dg["companies"].items():
        if row.get("sector") not in SUPPORTED_SECTORS: raise AssertionError(f"unsupported sector {sym}")
        if sym == "ENGROH" and row.get("sector") != "HOLDING_COMPANY": raise AssertionError("ENGROH must use HOLDING_COMPANY override")
        if row.get("quality_flags") != []: raise AssertionError(f"graph flags {sym}")
        nodes = set(row.get("drivers") or [])
        if not nodes or not row.get("edges"): raise AssertionError(f"empty graph {sym}")
        used_sources = set()
        for edge in row.get("edges") or []:
            if not edge.get("from") or not edge.get("to") or not edge.get("statement_line") or not edge.get("unit"): raise AssertionError(f"graph edge {sym}")
            if edge.get("basis") != "declarative_assumption": raise AssertionError(f"graph basis {sym}")
            if edge.get("statement_line") not in STATEMENT_LINES: raise AssertionError(f"graph statement line {sym}:{edge.get('statement_line')}")
            if edge.get("from") not in nodes and edge.get("from") not in APPROVED_DERIVED_NODES: raise AssertionError(f"graph source node {sym}:{edge.get('from')}")
            if edge.get("to") not in nodes and edge.get("to") not in APPROVED_DERIVED_NODES: raise AssertionError(f"graph target node {sym}:{edge.get('to')}")
            if edge.get("from") in nodes: used_sources.add(edge.get("from"))
        unused = nodes - used_sources
        if unused: raise AssertionError(f"graph unused drivers {sym}:{sorted(unused)}")
    for sym, row in sc["companies"].items():
        by_event = {}
        for s in row.get("scenarios") or []:
            if s.get("intelligence_type") != "scenario" or s.get("scenario_type") != "scenario": raise AssertionError("scenario typed as fact")
            by_event.setdefault(s.get("event_id"), 0.0)
            by_event[s.get("event_id")] += float(s.get("probability") or 0)
            if not isinstance(s.get("assumptions"), dict) or "missing_inputs" not in s["assumptions"]: raise AssertionError(f"scenario assumptions {sym}")
            if not s.get("impact_status") or not s.get("quality_flags"): raise AssertionError(f"scenario flags {sym}")
            if any(s.get(k) is not None for k in IMPACT_KEYS): raise AssertionError("numeric impact without sourced ready inputs")
        for event_id, total in by_event.items():
            if round(total, 10) != 1.0: raise AssertionError(f"probabilities {sym}:{event_id}")
    for path in (STATE / "company_intel" / "operating_events.json", STATE / "company_intel" / "impact_scenarios.json"):
        text = path.read_text(encoding="utf-8").lower()
        if "you should buy" in text or "you should sell" in text: raise AssertionError("advice language")
    print(f"operating_intelligence: PASS ({len(pilot)} pilot companies, {sum(len(x.get('events') or []) for x in oe['companies'].values())} events)")
if __name__ == "__main__": main()
