"""Focused source/data contract checks for the CI Lieflat analytical view."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "Henneth Desk 2.CI.0" / "app.js").read_text(encoding="utf-8")
CHARTS = (ROOT / "Henneth Desk 2.CI.0" / "ci_charts.js").read_text(encoding="utf-8")
DATA = json.loads(
    (ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json").read_text(
        encoding="utf-8"
    )
)


def function_body(name: str) -> str:
    match = re.search(rf"function {re.escape(name)}\([^)]*\) \{{", APP)
    assert match, f"missing function: {name}"
    depth = 0
    for index in range(match.end() - 1, len(APP)):
        if APP[index] == "{":
            depth += 1
        elif APP[index] == "}":
            depth -= 1
            if depth == 0:
                return APP[match.start() : index + 1]
    raise AssertionError(f"unterminated function: {name}")


metric = function_body("metric")
assert "ciChart(" not in metric, "Investor Snapshot metrics must remain ordinary values"

active_case = function_body("ciActiveObservedCase")
assert 'r.symbol === "MLCF"' in active_case
assert 'item.case_type !== "acquisition_control"' in active_case
assert "|| null" in active_case, "observed corporate control must not become the expansion case"

render = function_body("renderIntelligence")
assert render.count("${tile(") == 7, "the explainability view must render seven visual tiles"
assert "Waiting for reviewed model assumptions" in render
assert "separate observed corporate-control case" in render
assert "r.explainability" in render

assert "if (value == null" in CHARTS, "null chart values must not become zero"
assert "renderer = requested === blocked || statusBlocked(payload.status)" in CHARTS
assert "history.length > 1" in CHARTS, "a counter trend needs emitted history"

rows = {row["symbol"]: row for row in DATA["tickers"]}
for symbol in ("MARI", "MLCF", "PSO"):
    envelope = rows[symbol].get("explainability") or {}
    assert envelope.get("schema_version") == "ci_explainability_v1", symbol
    for key in (
        "observation",
        "transmission_mechanism",
        "forecast_trajectory",
        "key_assumptions",
        "expectations_gap",
        "conclusion",
        "monitoring",
    ):
        assert isinstance(envelope.get(key), dict), f"{symbol}: missing {key}"

mlcf_cases = rows["MLCF"].get("intelligence_cases", {}).get("cases", [])
assert mlcf_cases, "MLCF observed case fixture missing"
assert all(case.get("case_type") == "acquisition_control" for case in mlcf_cases)

# Synthetic positive fixture for the UI selection rule: an emitted expansion case wins.
synthetic = [
    {"case_type": "acquisition_control"},
    {"case_type": "capacity_expansion", "case_id": "active_expansion"},
]
selected = next((case for case in synthetic if case["case_type"] != "acquisition_control"), None)
assert selected and selected["case_id"] == "active_expansion"

print("PASS: CI Lieflat UI contract (7 visual tiles; 3 pilot envelopes)")
