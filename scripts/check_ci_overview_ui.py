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

logo_map = re.search(r"const COMPANY_LOGO_DOMAINS = Object\.freeze\(\{(.*?)\}\);", APP, re.S)
assert logo_map, "missing issuer-logo registry"
assert len(re.findall(r"\b[A-Z]{2,7}:\s*\"[^\"]+\"", logo_map.group(1))) == 20
for token in (
    "companyLogoUrl(r.symbol)",
    'class="company-logo-frame"',
    'class="hero-summary"',
    'class="hero-context"',
    "companyBusinessSummary(p.business_description)",
):
    assert token in APP, token

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
    'class="snapshot-story-heading"',
    'icon="lucide:building-2"',
    'icon="lucide:scan-search"',
    'icon="lucide:history"',
    'icon="lucide:chart-no-axes-combined"',
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
    'class="overview-fact-label"',
    'icon="lucide:file-check-2"',
):
    assert token in profile, token

for token in (
    ".overview-dashboard-card:hover",
    ".overview-route-button:hover",
    ".tree-folder-label[type=\"button\"]:focus-visible",
    "@container (max-width:760px)",
    "@media (max-width:560px)",
    ".snapshot-signal-grid b,.profile-fact-grid b",
    ".overview-detail-header h2{font-size:clamp(20px,2vw,27px)",
    ".snapshot-story-heading{display:flex",
    ".overview-fact-label{display:flex!important",
    ".ci-chart-readable-summary",
    ".overview-route-button,.overview-back-button,.snapshot-story-grid button{min-height:36px",
):
    assert token in CSS, token

close_drawers = function_body("closeMobileDrawers")
open_drawer = function_body("openMobileDrawer")
assert "restoreFocus" in close_drawers and "mobileDrawerOpener" in close_drawers
assert "mobileDrawerOpener =" in open_drawer
assert 'event.key === "Escape") closeMobileDrawers(true)' in APP

print("PASS: CI Overview directory UI contract")
