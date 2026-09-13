"""Focused source contract for the CI Overview directory milestone."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "Henneth Desk 2.CI.0" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "Henneth Desk 2.CI.0" / "styles.css").read_text(encoding="utf-8")


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


assert 'view: "directory_overview"' in APP
assert 'key === "overview" ? "directory_overview" : null' in APP
assert 'state.view === "directory_overview" ? renderOverviewDashboard(r)' in APP
assert '["business", "Business"]' not in APP
assert "renderCompanyBusiness" not in APP

metric = function_body("metric")
assert "ciChart(" not in metric, "ordinary snapshot values must not become charts"

dashboard = function_body("renderOverviewDashboard")
assert 'overviewRouteCard("snapshot"' in dashboard
assert 'overviewRouteCard("overview"' in dashboard
assert dashboard.count('ciChart("') == 3
assert "comparable: true" in dashboard

snapshot = function_body("renderInvestorSnapshot")
for token in (
    'class="snapshot-kpis"',
    'class="snapshot-story-grid"',
    'class="snapshot-signal-grid"',
    'class="ci-raw-status"',
    "r.explainability?.forecast_trajectory",
    "ciHumanStatus(catalystDomain.status)",
    "ciHumanStatus(riskDomain.status)",
    "ciHumanStatus(r.monitoring?.status)",
):
    assert token in snapshot, token

visible_snapshot = snapshot.split('<details class="ci-raw-status">', 1)[0]
assert '${esc(catalystDomain.status' not in visible_snapshot
assert '${esc(riskDomain.status' not in visible_snapshot
assert '${esc(r.monitoring?.status' not in visible_snapshot

profile = function_body("renderCompanyProfile")
for token in (
    'class="profile-fact-grid"',
    'class="profile-domain-grid"',
    "ciHumanStatus(domain.status)",
    'ciChart("assumptions"',
):
    assert token in profile, token

for token in (
    ".overview-dashboard-card:hover",
    ".overview-route-button:hover",
    ".tree-folder-label[type=\"button\"]:focus-visible",
    "@container (max-width:760px)",
    "@media (max-width:560px)",
    ".snapshot-signal-grid b,.profile-fact-grid b",
):
    assert token in CSS, token

print("PASS: CI Overview directory UI contract")
