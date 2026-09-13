#!/usr/bin/env python3
"""Focused, read-only contract checks for the CI Past Context experience."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "Henneth Desk 2.CI.0" / "app.js"
CHARTS = ROOT / "Henneth Desk 2.CI.0" / "ci_charts.js"
CSS = ROOT / "Henneth Desk 2.CI.0" / "styles.css"
SLICE = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app = APP.read_text(encoding="utf-8")
    charts = CHARTS.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    payload = json.loads(SLICE.read_text(encoding="utf-8"))

    require('["past_context", "Past Context"]' in app, "Past Context is missing from the Intelligence directory")
    require('state.view === "past_context" ? renderPastContext(r)' in app, "Past Context route is not dispatched")
    require("function renderPastContext(r)" in app, "Past Context renderer is missing")
    require(app.count("pastContextCard(") == 6, "Past Context must retain exactly five high-signal cards")
    for phrase in (
        "Historical context · not forecast",
        "No similarity score or ranked analogue identity is emitted",
        "Exact event binding",
        "No prior exact analogue context retained",
        "Case state, not live state",
        "MAE / MFE",
        "Time to resolution",
        "Forecast / valuation feed",
        "Prohibited",
    ):
        require(phrase in app, f"Past Context epistemic boundary is missing: {phrase}")
    require("horizon_aggregates" not in app[app.index("function renderPastContext(r)"):app.index("function renderEventsDashboard")], "UI must not read suppressed aggregate statistics")
    chart_types = ("state_colonnade", "evidence_convergence", "dated_lineage", "horizon_outcomes", "permission_tree")
    for chart_type in chart_types:
        require(f'ciChart("{chart_type}"' in app, f"Past Context does not wire {chart_type}")
        require(f"function {chart_type}(host" in charts, f"{chart_type} renderer is missing")
    require("G10 Diverging Bar" in charts and "L5 Radial Convergence" in charts, "Past Context Lieflat audit is incomplete")
    require("L20 was rejected" in charts and "F15 was rejected" in charts, "Lieflat rejection audit is incomplete")
    for marker in (".past-context-card:hover", "@media (prefers-reduced-motion:no-preference)", "@media (max-width:560px)", "pastContextReveal", "pastContextBar"):
        require(marker in css, f"Premium interaction/mobile contract is missing: {marker}")

    rows = payload.get("tickers") or []
    contexts = []
    mapped_symbols = set()
    for row in rows:
        product = row.get("historical_state_map") or {}
        row_contexts = product.get("contexts") or []
        contexts.extend(row_contexts)
        if row_contexts:
            mapped_symbols.add(row.get("symbol"))
        require(product.get("semantics") == "historical_context/not_forecast", f"{row.get('symbol')} map semantics drifted")
    require(len(contexts) == 4, f"expected 4 retained contexts, found {len(contexts)}")
    require(mapped_symbols == {"MARI", "MLCF", "PSO"}, f"unexpected mapped symbols: {sorted(mapped_symbols)}")
    for context in contexts:
        require((context.get("answer_contract") or {}).get("can_feed_forecast_or_valuation") is False, "historical context activated a formal output")
        benchmark = (context.get("past_context") or {}).get("strict_analogue_benchmark") or {}
        for row in (benchmark.get("horizon_aggregates") or {}).values():
            if int(row.get("n") or 0) < 3:
                require(row.get("status") == "suppressed", "thin historical sample is not suppressed")

    print(f"ci_past_context_ui: PASS ({len(contexts)} contexts; 5 cards; desktop/mobile contracts present)")


if __name__ == "__main__":
    main()
