#!/usr/bin/env python3
"""Check the Intelligence-directory data contract against the live CI slice."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "Henneth Desk 2.CI.0" / "app.js"
SLICE = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
DOC = ROOT / "docs" / "CI-INTELLIGENCE-DIRECTORY-DATA-CONTRACT.md"
ROUTES = ("research", "ask", "graph", "operating", "intelligence", "timeline")
FUNCTIONS = {
    "research": "renderCompanyResearch",
    "ask": "renderAskHenneth",
    "graph": "renderGraph",
    "operating": "renderOperatingIntelligence",
    "intelligence": "renderIntelligence",
    "timeline": "renderTimeline",
}
FIELDS = {
    "graph": "graph",
    "operating": "operating_events",
    "intelligence": "explainability",
    "timeline": "timeline",
}


def function_exists(source: str, name: str) -> bool:
    return bool(re.search(rf"function\s+{re.escape(name)}\s*\(", source))


def main() -> int:
    source = APP.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")
    payload = json.loads(SLICE.read_text(encoding="utf-8"))
    errors: list[str] = []
    for route in ROUTES:
        if route not in doc:
            errors.append(f"{route}: missing from data contract")
        if not function_exists(source, FUNCTIONS[route]):
            errors.append(f"{route}: renderer {FUNCTIONS[route]} is missing")
    if 'landing_route="intelligence"' not in doc:
        errors.append('contract missing landing_route="intelligence"')
    if not all(f'"{route}"' in doc for route in ROUTES):
        errors.append("contract does not enumerate all six child routes")
    rows = [row for row in payload.get("tickers", []) if isinstance(row, dict)]
    if not rows:
        errors.append("slice has no ticker rows")
    for route, field in FIELDS.items():
        missing = [str(row.get("symbol", "unknown")) for row in rows if field not in row]
        if missing:
            errors.append(f"{route}: authoritative row field {field!r} missing for {missing}")
    # Ask is deliberately server/session-owned rather than a row field.
    ask_body = source[source.find("function renderAskHenneth"):source.find("function readableAskError")]
    if "state.ask.bySymbol" not in ask_body or "api/ask" not in source:
        errors.append("ask: session/server-owned API seam is not present")
    if errors:
        print("ci_intelligence_directory_data_contract: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"ci_intelligence_directory_data_contract: PASS ({len(rows)} slice rows; routes={len(ROUTES)})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ci_intelligence_directory_data_contract: ERROR ({exc})", file=sys.stderr)
        raise SystemExit(2)
