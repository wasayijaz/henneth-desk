#!/usr/bin/env python3
"""Audit the six-directory Company Intelligence information architecture.

This checker is intentionally strict while the UI is being migrated. It reads
the live TREE_GROUPS/route registries and reports each directory independently;
missing landing contracts or envelope wiring are failures, not silently
accepted legacy states.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "Henneth Desk 2.CI.0" / "app.js"
CSS = ROOT / "Henneth Desk 2.CI.0" / "styles.css"
SLICE = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"

EXPECTED_DIRECTORIES = ("overview", "intelligence", "financials", "events", "strategy", "ownership")
GOLDEN_CASES = {
    "MARI": (
        "case_mari_working_interest_observed_v1",
        "case_mari_sky47_karakoram1_launch_sales_observed_v1",
    ),
    "MLCF": ("case_mlcf_pioc_control_observed_v1",),
}
ANALYTICAL_SECTIONS = {
    "overview": ("Observation", "Conclusion", "Monitoring"),
    "intelligence": (
        "Observation",
        "Transmission mechanism",
        "Forecast trajectory",
        "Key assumptions",
        "Expectations gap",
        "Conclusion",
        "Monitoring",
    ),
    "financials": ("Forecast trajectory", "Key assumptions", "Expectations gap"),
    "events": ("Observation", "Monitoring"),
    "strategy": ("Transmission mechanism", "Forecast trajectory", "Expectations gap", "Conclusion"),
    "ownership": ("Monitoring",),
}
# Overview is the only directory whose folder itself currently owns a landing
# dashboard.  The remaining groups must add an explicit contract as they are
# migrated; keeping this map here makes that exception visible and testable.
IMPLEMENTED_LANDINGS = {
    "overview": "directory_overview",
}
# Sol's next migration target.  Keep this executable acceptance contract next
# to the checker so the intended Intelligence folder cannot silently shed a
# route while its landing page is added.
NEXT_DIRECTORY_TARGETS = {
    "intelligence": {
        "landing": "directory_intelligence",
        "routes": ("ask", "graph", "operating", "intelligence", "timeline"),
    },
}


def fail(message: str) -> None:
    raise AssertionError(message)


def _registry_block(source: str, name: str) -> str:
    match = re.search(rf"const\s+{re.escape(name)}\s*=\s*\[(?P<body>[\s\S]*?)\];", source)
    if not match:
        fail(f"{name} registry is missing")
    return match.group("body")


def _route_pairs(block: str) -> list[tuple[str, str]]:
    return [(key, label) for key, label in re.findall(r'\[\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\]', block)]


def _tree_groups(source: str) -> list[dict[str, Any]]:
    match = re.search(r"const\s+TREE_GROUPS\s*=\s*\[(?P<body>[\s\S]*?)\];", source)
    if not match:
        fail("TREE_GROUPS registry is missing")
    groups = []
    pattern = re.compile(
        r'\{\s*key:\s*"(?P<key>[^"]+)"\s*,\s*label:\s*"(?P<label>[^"]+)"\s*,\s*'
        r'(?P<landing>landing(?:_route)?\s*:\s*"[^"]+"\s*,\s*)?routes:\s*\[(?P<routes>[\s\S]*?)\]\s*\}',
    )
    for item in pattern.finditer(match.group("body")):
        landing = re.search(r'landing(?:_route)?\s*:\s*"([^"]+)"', item.group("landing") or "")
        groups.append({
            "key": item.group("key"),
            "label": item.group("label"),
            "landing": landing.group(1) if landing else None,
            "routes": _route_pairs(item.group("routes")),
        })
    return groups


def _function_body(source: str, name: str) -> str:
    """Return one top-level function without stopping at nested braces.

    The CI shell contains template literals and nested callbacks, so matching
    the first ``\n}`` is not a reliable function boundary.  The functions this
    checker audits are top-level declarations; the next top-level declaration
    is therefore a stable, parser-free boundary for this source contract.
    """
    match = re.search(rf"function\s+{re.escape(name)}\([^)]*\)\s*\{{", source)
    if not match:
        return ""
    next_function = re.search(r"\nfunction\s+[A-Za-z_$][\w$]*\s*\(", source[match.end():])
    end = match.end() + next_function.start() if next_function else len(source)
    return source[match.end():end]


def _visible_template_source(source: str) -> str:
    """Remove collapsed technical disclosures before visible-copy checks."""
    return re.sub(r"<details\b[\s\S]*?</details>", "", source, flags=re.IGNORECASE)


def _check_overview_contract(group: dict[str, Any], source: str, primary: list[tuple[str, str]], research: list[tuple[str, str]]) -> list[str]:
    errors: list[str] = []
    routes = [route for route, _label in group["routes"]]
    if routes != ["snapshot", "overview"]:
        errors.append(f"Overview child routes drifted: expected ['snapshot', 'overview'], found {routes}")
    route_keys = {route for route, _label in primary + research}
    if "business" in route_keys or re.search(r"state\.view\s*===\s*[\"']business[\"']", source):
        errors.append("obsolete duplicate business route remains")
    dashboard = _function_body(source, "renderOverviewDashboard")
    route_card = _function_body(source, "overviewRouteCard")
    snapshot = _function_body(source, "renderInvestorSnapshot")
    profile = _function_body(source, "renderCompanyProfile")
    for marker, label in (
        ('overviewRouteCard("snapshot"', "clickable Investor Snapshot landing card"),
        ('overviewRouteCard("overview"', "clickable Company Profile landing card"),
        ('data-research-route="${esc(route)}"', "overview route action contract"),
    ):
        if marker not in dashboard + route_card:
            errors.append(f"Overview missing {label}")
    if "function renderInvestorSnapshot" not in source or "function renderCompanyProfile" not in source:
        errors.append("Overview lacks distinct Investor Snapshot/Profile renderers")
    if 'data-research-route="overview"' not in snapshot or 'data-research-route="directory_overview"' not in profile:
        errors.append("Overview Snapshot/Profile pages do not expose return/navigation actions")
    visible = _visible_template_source(dashboard + snapshot + profile)
    if "ciHumanStatus" not in visible or "Formal outputs remain gated" not in visible:
        errors.append("Overview blockers are not visibly translated into plain language")
    visible_raw_markers = ("esc(section.status", "esc(section.reason", "esc(forecast.status", "esc(forecast.reason")
    if any(marker in visible for marker in visible_raw_markers):
        errors.append("Overview visible copy interpolates raw status/reason outside technical disclosure")
    if "ci-raw-status" not in snapshot or "formal_status" not in snapshot:
        errors.append("Overview technical status is not retained only in a collapsed disclosure")
    return errors


def _check_directory(group: dict[str, Any], source: str, intended: set[str]) -> list[str]:
    key = group["key"]
    errors: list[str] = []
    routes = [route for route, _label in group["routes"]]
    if not routes:
        errors.append("no routes declared")
    landing = group.get("landing") or IMPLEMENTED_LANDINGS.get(key)
    if landing is None:
        errors.append("missing explicit landing route contract (add landing or landing_route)")
    elif group.get("landing") and landing in routes:
        errors.append(f"landing route {landing!r} must be distinct from its child routes")
    elif group.get("landing"):
        if f'state.view === "{landing}"' not in source:
            errors.append(f"implemented landing {landing!r} has no renderer dispatch")
    elif key in IMPLEMENTED_LANDINGS:
        if f'key === "{key}" ? "{landing}"' not in source:
            errors.append(f"implemented landing {landing!r} is not wired from the {key} directory")
        if f'state.view === "{landing}"' not in source:
            errors.append(f"implemented landing {landing!r} has no renderer dispatch")
    next_target = NEXT_DIRECTORY_TARGETS.get(key)
    if next_target and group.get("landing") and group["landing"] != next_target["landing"]:
        errors.append(f"next-directory landing must be {next_target['landing']!r}")
    duplicates = sorted({route for route in routes if routes.count(route) > 1})
    if duplicates:
        errors.append(f"duplicate routes: {duplicates}")
    unknown = sorted(set(routes) - intended)
    if unknown:
        errors.append(f"routes not present in primary/research registries: {unknown}")
    required = ANALYTICAL_SECTIONS[key]
    bodies = [
        _function_body(source, "renderIntelligence"),
        _function_body(source, "ciEnvelopeBlocked"),
        _function_body(source, "ciHumanStatus"),
    ]
    analytical_source = "\n".join(bodies)
    for label in required:
        if label not in source:
            errors.append(f"analytical section missing: {label}")
    if key == "intelligence" and "explainability" not in analytical_source:
        errors.append("analytical sections do not read the row.explainability envelope")
    if key == "intelligence" and "missing_gates" not in analytical_source:
        errors.append("blocked analytical states lack plain-language missing_gates rendering")
    if key == "intelligence" and "ciHumanStatus" not in analytical_source:
        errors.append("analytical section does not translate machine status into plain language")
    if key == "intelligence" and group.get("landing"):
        dashboard = _function_body(source, "renderIntelligenceDashboard")
        if not dashboard:
            errors.append("Intelligence landing has no distinct dashboard renderer")
        for route in NEXT_DIRECTORY_TARGETS["intelligence"]["routes"]:
            if f'intelligenceDashboardCard("{route}"' not in dashboard:
                errors.append(f"Intelligence landing does not link child route {route!r}")
        if "overall readiness" in dashboard.lower() or "readiness score" in dashboard.lower():
            errors.append("Intelligence landing invents an overall readiness score")
    # A collapsed technical-status disclosure may retain the machine code for
    # auditability.  Only inspect ordinary visible rendering for raw codes.
    visible_case_body = _function_body(source, "renderCaseSectionBody")
    raw_markers = ("esc(section.status", "esc(section.reason", "section?.status || \"blocked\"")
    if key == "intelligence" and any(marker in visible_case_body for marker in raw_markers):
        errors.append("case analytical copy exposes raw machine-only status outside technical disclosure")
    return errors


def _case_contracts(payload: dict[str, Any], source: str) -> list[str]:
    errors: list[str] = []
    if "state.caseRoute" not in source or "renderIntelligenceCase" not in source:
        errors.append("case route dispatcher is missing")
    case_body = _function_body(source, "renderIntelligenceCase")
    route_source = source
    if "caseId" not in case_body or "findCase(r, caseId" not in case_body:
        errors.append("golden-case route does not resolve the requested case_id")
    if "state.caseRoute.caseId" not in route_source or "renderIntelligenceCase(row, state.caseRoute.caseId)" not in route_source:
        errors.append("active route does not pass state.caseRoute.caseId into the case renderer")
    rows = {row.get("symbol"): row for row in payload.get("tickers") or [] if isinstance(row, dict)}
    for symbol, case_ids in GOLDEN_CASES.items():
        row = rows.get(symbol) or {}
        cases = ((row.get("intelligence_cases") or {}).get("cases") or [])
        by_id = {case.get("case_id"): case for case in cases if isinstance(case, dict)}
        envelope = row.get("explainability") or {}
        observation = envelope.get("observation") or {}
        for case_id in case_ids:
            case = by_id.get(case_id)
            if not case:
                errors.append(f"{symbol}/{case_id}: IntelligenceCase missing")
                continue
            facts = case.get("observed_facts") or []
            if not any(isinstance(fact, dict) and fact.get("source_event_id") for fact in facts):
                errors.append(f"{symbol}/{case_id}: no explicit source_event_id binding")
            # The company-level envelope has one selected observation.  A case
            # route is case-bound by its URL case_id and backend findCase lookup;
            # do not require that one observation to equal every sibling case.
    return errors


def main() -> int:
    source = APP.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    payload = json.loads(SLICE.read_text(encoding="utf-8"))
    groups = _tree_groups(source)
    results: dict[str, list[str]] = {}
    global_errors: list[str] = []
    keys = [group.get("key") for group in groups]
    if len(groups) != 6:
        global_errors.append(f"expected exactly six directories, found {len(groups)}")
    if tuple(keys) != EXPECTED_DIRECTORIES:
        global_errors.append(f"directory order/keys drifted: expected {EXPECTED_DIRECTORIES}, found {tuple(keys)}")
    primary = _route_pairs(_registry_block(source, "PRIMARY_COMPANY_TABS"))
    research = _route_pairs(_registry_block(source, "RESEARCH_TOOL_TABS"))
    registry_routes = [route for route, _label in primary + research]
    intended = set(registry_routes)
    duplicate_registry_routes = sorted({route for route in registry_routes if registry_routes.count(route) > 1})
    if duplicate_registry_routes:
        global_errors.append(f"primary/research registries are not disjoint: {duplicate_registry_routes}")
    tree_routes = [route for group in groups for route, _label in group.get("routes", [])]
    tree_counts = {route: tree_routes.count(route) for route in set(tree_routes)}
    duplicate_tree_routes = sorted(route for route, count in tree_counts.items() if count > 1)
    missing_tree = sorted(route for route in registry_routes if tree_counts.get(route, 0) == 0)
    wrong_count_tree = sorted(route for route in registry_routes if tree_counts.get(route, 0) != 1)
    if duplicate_tree_routes:
        global_errors.append(f"TREE_GROUPS routes are not exact-once: {duplicate_tree_routes}")
    if wrong_count_tree and not duplicate_tree_routes:
        global_errors.append(f"TREE_GROUPS routes do not have exactly one owner: {wrong_count_tree}")
    extra_tree = sorted(set(tree_routes) - intended)
    if missing_tree:
        global_errors.append(f"intended routes missing from TREE_GROUPS: {missing_tree}")
    if extra_tree:
        global_errors.append(f"TREE_GROUPS contains routes outside intended registries: {extra_tree}")
    for group in groups:
        results[group["key"]] = _check_directory(group, source, intended)
    overview = next((group for group in groups if group.get("key") == "overview"), None)
    if overview:
        results["overview"].extend(_check_overview_contract(overview, source, primary, research))
    target = NEXT_DIRECTORY_TARGETS["intelligence"]
    intelligence = next((group for group in groups if group.get("key") == "intelligence"), None)
    if intelligence:
        actual = [route for route, _label in intelligence["routes"]]
        if actual != list(target["routes"]):
            global_errors.append(f"Intelligence acceptance target drifted: expected {list(target['routes'])}, found {actual}")
    analytical_source = _function_body(source, "renderIntelligence") + _function_body(source, "renderIntelligenceCase")
    if "aria-label=" not in analytical_source and "aria-labelledby=" not in analytical_source:
        global_errors.append("analytical explainability sections have no accessibility label")
    required_aria = (
        'aria-label="Company intelligence directory tree"',
        'aria-label="Primary company sections"',
        'aria-label="Company directory"',
        'aria-label="Research tools"',
    )
    missing_aria = [marker for marker in required_aria if marker not in source]
    if missing_aria:
        global_errors.append(f"missing required navigation accessibility labels: {missing_aria}")
    if "@media (max-width:900px)" not in css:
        global_errors.append("missing 900px responsive breakpoint")
    if "@media (max-width:560px)" not in css:
        global_errors.append("missing 560px responsive breakpoint")
    global_errors.extend(_case_contracts(payload, source))
    failed_directories = {key: errors for key, errors in results.items() if errors}
    passed_directories = [key for key, errors in results.items() if not errors]
    print(f"ci_directory_information_architecture: {'FAIL' if (global_errors or failed_directories) else 'PASS'}")
    for key in EXPECTED_DIRECTORIES:
        errors = results.get(key, ["directory missing from TREE_GROUPS"])
        if errors:
            print(f"  FAIL {key}:" if key in results else f"  FAIL {key}:")
            for error in errors:
                print(f"    - {error}")
        else:
            print(f"  PASS {key}")
    if global_errors:
        print("  GLOBAL:")
        for error in global_errors:
            print(f"    - {error}")
    target = NEXT_DIRECTORY_TARGETS["intelligence"]
    print(f"  NEXT INTELLIGENCE TARGET: landing_route=\"{target['landing']}\"; child routes={list(target['routes'])}")
    print(f"  SUMMARY: {len(passed_directories)}/6 directories pass; {len(global_errors)} global failures")
    return 1 if global_errors or failed_directories else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ci_directory_information_architecture: ERROR ({exc})", file=sys.stderr)
        raise SystemExit(2)
