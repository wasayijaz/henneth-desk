#!/usr/bin/env python3
"""Focused contract checks for the CI chronology visualizations."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "Henneth Desk 2.CI.0" / "app.js").read_text(encoding="utf-8")


def function_body(name: str) -> str:
    match = re.search(rf"function {re.escape(name)}\([^)]*\) \{{", APP)
    if not match:
        raise AssertionError(f"missing renderer: {name}")
    depth = 0
    for index in range(match.end() - 1, len(APP)):
        if APP[index] == "{":
            depth += 1
        elif APP[index] == "}":
            depth -= 1
            if depth == 0:
                return APP[match.start() : index + 1]
    raise AssertionError(f"unterminated renderer: {name}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    contracts = {
        "renderTimeline": (
            ("ciChart(\"dated_lineage\"", "dated_lineage chart"),
            ("observed: true", "observed chronology records"),
            ("ciBlockedChart(\"blocked_no_dated_company_records\"", "empty chronology state"),
            ("brain-timeline", "Company Brain detail list"),
            ("timeline-row", "event detail list"),
            ("change-row", "revision detail list"),
        ),
        "renderChangeIntelligence": (
            ("ciChart(\"dated_lineage\"", "dated_lineage chart"),
            ("observed: true", "observed change records"),
            ("ciBlockedChart(\"blocked_no_dated_change_records\"", "empty change state"),
            ("change-summary", "change summary"),
            ("change-list", "change detail list"),
            ("renderChangeItem", "change detail renderer"),
        ),
        "renderThesisMonitor": (
            ("ciChart(\"dated_lineage\"", "dated_lineage chart"),
            ("observed: true", "observed thesis records"),
            ("ciBlockedChart(\"blocked_no_dated_thesis_records\"", "empty thesis state"),
            ("renderPrivateTheses", "private thesis detail"),
            ("renderManagementDelivery", "management delivery detail"),
            ("thesisCards", "official thesis detail cards"),
        ),
        "renderCiMonitoring": (
            ("ciChart(\"dated_lineage\"", "dated_lineage chart"),
            ("observed: true", "observed monitoring records"),
            ("ciBlockedChart(\"blocked_no_dated_monitoring_records\"", "empty monitoring state"),
            ("monitoring-summary", "monitoring summary"),
            ("renderCiEventWindows", "event-window detail"),
            ("renderCiMonitoringAlert", "alert detail list"),
        ),
    }
    for renderer, requirements in contracts.items():
        body = function_body(renderer)
        for marker, description in requirements:
            require(marker in body, f"{renderer} is missing {description}")
        require(body.count('ciChart("dated_lineage"') == 1, f"{renderer} must have one chronology chart wiring")

    print("ci_chronology_routes: PASS (4 renderers; observed records; detail views and empty states preserved)")


if __name__ == "__main__":
    main()
