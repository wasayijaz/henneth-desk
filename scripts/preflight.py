#!/usr/bin/env python3
"""Pre-deploy guard for Henneth.

Runs AFTER the data pipeline and BEFORE anything is published. It re-reads
every state file the dashboard actually consumes and asserts the shape the
UI depends on. If a check fails, it exits non-zero so the deploy is aborted
with a blank/broken board never reaching the live site.

Design rule: this catches the class of bug where a fetch degrades and a file
ends up empty or missing a field the UI joins on (e.g. quant.json without
rsi14 -> every RSI cell blanks). Cheap, deterministic, no tokens, no network.

Usage:
    python scripts/preflight.py            # human report, exit 1 on FAIL
    python scripts/preflight.py --strict   # WARN also fails (use in CI)

Exit codes: 0 = safe to deploy, 1 = do not deploy.
"""
import argparse
import ast
from datetime import datetime, timezone
import glob
import json
import math
import os
import subprocess
import sys

import build_ci_slice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")

fails, warns = [], []


def fail(msg):
    fails.append(msg)


def warn(msg):
    warns.append(msg)


def checker_failure_detail(result, limit=500):
    """Keep a checker's actual stderr failure visible ahead of its stdout summary."""
    stderr = str(getattr(result, "stderr", "") or "").strip()
    stdout = str(getattr(result, "stdout", "") or "").strip()
    detail = stderr or stdout or "no output"
    return detail[-limit:]


def load(name):
    """Load a state file; None if missing/unparseable (recorded as FAIL by caller)."""
    p = os.path.join(STATE, name)
    if not os.path.exists(p):
        return None, "missing"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, str(e)


def has_nonfinite(obj):
    """True if any float in the structure is NaN/Infinity (breaks browser JSON.parse)."""
    if isinstance(obj, float):
        return not math.isfinite(obj)
    if isinstance(obj, dict):
        return any(has_nonfinite(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_nonfinite(v) for v in obj)
    return False


def check(name, required=True, min_tickers=0, ticker_fields=(), top_keys=()):
    """Generic structural check for a state file."""
    data, err = load(name)
    if data is None:
        (fail if required else warn)(f"{name}: {err}")
        return None
    if has_nonfinite(data):
        fail(f"{name}: contains NaN/Infinity — will break JSON.parse in the browser")
    for k in top_keys:
        if k not in data:
            fail(f"{name}: missing top-level key '{k}'")
    if min_tickers or ticker_fields:
        t = data.get("tickers", {})
        if not isinstance(t, dict) or len(t) < min_tickers:
            fail(f"{name}: only {len(t) if isinstance(t, dict) else 0} tickers (expected >= {min_tickers})")
        elif ticker_fields:
            # sample up to 5 tickers; every one must carry the joined fields
            sample = list(t.items())[:5]
            for sym, v in sample:
                for fld in ticker_fields:
                    if fld not in v or v[fld] is None:
                        fail(f"{name}: ticker {sym} missing '{fld}' (the UI joins on this — cells would blank)")
                        break
    return data


def check_code_syntax():
    """Tier-1 code QA: a free, instant syntax gate on every publish (cloud + local + app
    tasks all route through this file). Catches "someone broke the build" before it ever
    reaches the live site — nothing else in the desk checked CODE syntax before this.
    This is NOT a substitute for the weekly /code-review deep pass (correctness, security,
    design) — just the fast, zero-cost first line that runs on literally every publish."""
    for path in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.py"))):
        try:
            with open(path, encoding="utf-8") as f:
                ast.parse(f.read(), filename=path)
        except SyntaxError as e:
            fail(f"{os.path.relpath(path, ROOT)}: Python syntax error — {e.msg} (line {e.lineno})")

    # Every shipped dashboard/root-API/CI JavaScript file. Fail closed before either live surface builds.
    js_roots = [os.path.join(ROOT, "dashboard"), os.path.join(ROOT, "api"), os.path.join(ROOT, "Henneth Desk 2.CI.0")]
    js_files = sorted(
        p for js_root in js_roots for p in glob.glob(os.path.join(js_root, "*.js"))
        if os.path.isfile(p)
    )
    node_missing = False
    for js_path in js_files:
        rel = os.path.relpath(js_path, ROOT).replace("\\", "/")
        try:
            r = subprocess.run(["node", "-c", js_path], capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                fail(f"{rel}: JS syntax error —\n{(r.stderr or r.stdout)[:300]}")
        except FileNotFoundError:
            if not node_missing:
                warn("shipped *.js: skipped JS syntax check — 'node' not found on this machine")
                node_missing = True
        except Exception as e:  # noqa: BLE001 — never let the checker itself crash the gate
            warn(f"{rel}: JS syntax check errored — {e}")


def check_ci_contract_workflow():
    """Verify the committed CI workflow still carries the repository's local gates."""
    path = os.path.join(ROOT, "scripts", "check_ci_contract_workflow.py")
    if not os.path.exists(path):
        fail("check_ci_contract_workflow.py missing — CI contract workflow cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            detail = (result.stdout or result.stderr or "").strip().splitlines()
            fail("CI contract workflow check failed — " + (detail[-1] if detail else "no details"))
    except Exception as e:  # noqa: BLE001 — never let the checker itself crash the gate
        fail(f"check_ci_contract_workflow.py did not run — {e}")


def check_provenance():
    """Tier-1 accuracy QA: run provenance_lint.py (placeholder/hollow/stale rendered content).
    A hard FAIL there means an assumed/empty/out-of-date value would reach users — block it."""
    lint = os.path.join(ROOT, "scripts", "provenance_lint.py")
    if not os.path.exists(lint):
        return
    try:
        r = subprocess.run([sys.executable, lint], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            # surface the lint's own FAIL lines (skip its header/blank lines)
            for line in r.stdout.splitlines():
                if line.strip().startswith("x "):
                    fail("provenance: " + line.strip()[2:])
            if not any(f.startswith("provenance:") for f in fails):
                fail("provenance_lint.py failed (see its output) — assumed/hollow/stale content")
    except Exception as e:  # noqa: BLE001
        warn(f"provenance_lint.py did not run — {e}")


def check_rule4():
    """Tier-1 maths QA: Rule 4 share counts and the payout-ratio sign guard.
    A FAIL here means a published golden case no longer matches CLAUDE.md — block deploy.
    The checker does not import production calculators, so it cannot rewrite them."""
    path = os.path.join(ROOT, "scripts", "check_rule4.py")
    if not os.path.exists(path):
        fail("check_rule4.py missing — Rule 4 golden cases cannot run")
        return
    try:
        r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            for line in (r.stdout or "").splitlines():
                if line.strip().startswith("x "):
                    fail("rule4: " + line.strip()[2:])
            if not any(f.startswith("rule4:") for f in fails):
                fail("check_rule4.py failed — " + ((r.stdout or r.stderr or "")[-200:]))
    except Exception as e:  # noqa: BLE001
        fail(f"check_rule4.py did not run — {e}")


def check_root_state_publication():
    """Root deployment must not publish CI-owner-only artifacts under /state."""
    path = os.path.join(ROOT, "scripts", "check_root_state_publication.py")
    if not os.path.exists(path):
        fail("check_root_state_publication.py missing — root /state CI-private boundary cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            fail("root state publication check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:  # noqa: BLE001
        fail(f"check_root_state_publication.py did not run — {e}")


def check_generated_url_safety():
    """Generated URLs must be absolute http(s) before the browser turns them into links."""
    path = os.path.join(ROOT, "scripts", "check_generated_url_safety.py")
    if not os.path.exists(path):
        fail("check_generated_url_safety.py missing — generated URL link safety cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            fail("generated URL safety check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:  # noqa: BLE001
        fail(f"check_generated_url_safety.py did not run — {e}")


def check_document_intelligence():
    """Offline fixtures plus live-state provenance for the CI document layer."""
    path = os.path.join(ROOT, "scripts", "check_document_intelligence.py")
    if not os.path.exists(path):
        fail("check_document_intelligence.py missing — CI evidence cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            detail = (result.stdout or result.stderr or "")[-500:].strip()
            fail("document intelligence check failed — " + detail)
    except Exception as e:  # noqa: BLE001
        fail(f"check_document_intelligence.py did not run — {e}")


def check_company_intelligence_phase2():
    """Financial normalization, graph provenance, and synthesis training gates."""
    scripts = (
        ("check_financial_graph.py", []),
        ("stage_issuer_documents.py", ["--self-check"]),
        ("build_change_intelligence.py", ["--self-check"]),
        ("prepare_synthesis_batch.py", ["--self-check"]),
        ("company_brief_review.py", ["self-check"]),
        ("check_training_receipt_reconciliation.py", []),
    )
    for name, args in scripts:
        path = os.path.join(ROOT, "scripts", name)
        if not os.path.exists(path):
            fail(f"{name} missing — CI phase-2 gate cannot run")
            continue
        try:
            result = subprocess.run([sys.executable, path, *args], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                fail(f"{name} failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
        except Exception as e:  # noqa: BLE001
            fail(f"{name} did not run — {e}")

    series, err = load("company_financial_series.json")
    if series is None:
        fail(f"company_financial_series.json: {err}")
    else:
        for ticker, bucket in (series.get("tickers") or {}).items():
            for fact in bucket.get("facts") or []:
                label = f"company_financial_series.json:{ticker}:{fact.get('series_id')}"
                if not fact.get("document_id") or not fact.get("source_url") or not fact.get("evidence"):
                    fail(f"{label} missing document/source/page provenance")
                if ".test/" in str(fact.get("source_url")) or str(fact.get("document_id")).startswith("psx:fixture"):
                    fail(f"{label} contains test-fixture provenance")
                evidence = (fact.get("evidence") or [{}])[0]
                if not isinstance(evidence.get("page"), int) or evidence["page"] < 1:
                    fail(f"{label} has invalid evidence page")
                period = fact.get("period_end")
                if period:
                    try:
                        __import__("datetime").date.fromisoformat(period)
                    except (TypeError, ValueError):
                        fail(f"{label} period_end is not ISO date")
                if str(fact.get("unit") or "").lower().endswith("/share") and fact.get("unit_multiplier") != 1:
                    fail(f"{label} per-share value has scaled multiplier")
            for conflict in bucket.get("conflicts") or []:
                if not conflict.get("period_end") or conflict.get("consolidation") in (None, "unknown"):
                    fail(f"company_financial_series.json:{ticker} has an incomparable conflict")

    source_qa, err = load("company_source_qa.json")
    if source_qa is None:
        fail(f"company_source_qa.json: {err}")
    elif len(source_qa.get("tickers") or {}) < 20:
        fail("company_source_qa.json: fewer than 20 pilot ticker rows")

    graph_path = os.path.join(STATE, "company_intel", "company_graph.json")
    try:
        with open(graph_path, encoding="utf-8") as f:
            graph = json.load(f)
    except Exception as e:
        fail(f"company_intel/company_graph.json: {e}")
        graph = {}
    node_ids = {node.get("id") for node in graph.get("nodes") or [] if isinstance(node, dict)}
    factual = {"FILED", "SUPPORTS_FACT", "REPORTS_PERIOD", "HAS_EVENT", "EVIDENCED_BY",
               "REVISION_OF", "HAS_CHANGE", "HAS_SOURCE"}
    for edge in graph.get("edges") or []:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            fail(f"company_intel/company_graph.json: dangling edge {edge.get('id')}")
        if edge.get("type") in factual and not (edge.get("evidence") or {}).get("source_url"):
            fail(f"company_intel/company_graph.json: factual edge missing source {edge.get('id')}")

    change_path = os.path.join(STATE, "company_intel", "change_intelligence.json")
    try:
        with open(change_path, encoding="utf-8") as f:
            changes = json.load(f)
    except Exception as e:
        fail(f"company_intel/change_intelligence.json: {e}")
        changes = {}
    if changes and len(changes.get("companies") or {}) < 20:
        fail("company_intel/change_intelligence.json: fewer than 20 pilot company rows")
    for ticker, row in (changes.get("companies") or {}).items():
        for item in row.get("items") or []:
            label = f"company_intel/change_intelligence.json:{ticker}:{item.get('id')}"
            if item.get("kind") not in {"document", "event", "financial", "source", "issuer_document"}:
                fail(f"{label} invalid change kind")
            evidence = item.get("evidence") or {}
            if not item.get("source_url") and not evidence.get("source_url"):
                fail(f"{label} missing source URL")
            if item.get("kind") in {"event", "financial"} and evidence.get("page") is not None:
                if not isinstance(evidence.get("page"), int) or evidence["page"] < 1:
                    fail(f"{label} invalid evidence page")


def check_company_profiles():
    data, err = load("company_profiles.json")
    if data is None:
        fail(f"company_profiles.json: {err}")
        return
    rows = data.get("tickers")
    if not isinstance(rows, dict) or not rows:
        fail("company_profiles.json: missing populated tickers map")
        return
    pilot = data.get("pilot", {})
    expected = pilot.get("symbols") or []
    if expected and len(rows) < len(expected):
        fail(f"company_profiles.json: {len(rows)} rows for {len(expected)} pilot symbols")
    for sym, row in sorted(rows.items()):
        if not isinstance(row, dict):
            fail(f"company_profiles.json: {sym} row is not an object")
            continue
        if row.get("symbol") != sym:
            fail(f"company_profiles.json: {sym} row symbol mismatch")
        if not row.get("source_url"):
            fail(f"company_profiles.json: {sym} missing source_url")
        if not row.get("business_description") and not row.get("incorporation"):
            fail(f"company_profiles.json: {sym} has neither business_description nor incorporation")
        inc = row.get("incorporation")
        if inc is not None and not isinstance(inc, dict):
            fail(f"company_profiles.json: {sym} incorporation is not an object/null")


def check_ci_slice():
    path = os.path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json")
    if not os.path.exists(path):
        fail("Henneth Desk 2.CI.0/data/company_intelligence.json: missing generated CI slice")
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {e}")
        return
    if has_nonfinite(data):
        fail("Henneth Desk 2.CI.0/data/company_intelligence.json: contains NaN/Infinity")
    rows = data.get("tickers")
    if not isinstance(rows, list) or not rows:
        fail("Henneth Desk 2.CI.0/data/company_intelligence.json: no ticker rows")
        return
    profiles, _ = load("company_profiles.json")
    pilot = set(((profiles or {}).get("pilot") or {}).get("symbols") or [])
    row_symbols = {row.get("symbol") for row in rows if isinstance(row, dict) and row.get("symbol")}
    if pilot and row_symbols != pilot:
        fail("Henneth Desk 2.CI.0/data/company_intelligence.json: ticker boundary does not match company_profiles.pilot.symbols")
    # Wave 1 CI seam: the generated slice must exactly reflect the three authoritative
    # state products. This catches a stale slice even when its legacy fields still look valid.
    wave1 = {}
    for name in ("operating_events", "driver_graphs", "impact_scenarios", "event_studies", "conditional_benchmarks", "causal_foundations", "financial_model_inputs", "financial_evidence_reconciliation", "earnings_bridges", "financial_coverage", "financial_truth_qualification", "forecast_readiness", "financial_forecasts", "formal_valuations", "market_expectations", "scenario_lab", "company_brains", "thesis_monitoring", "intelligence_confidence", "intelligence_cases", "mlcf_pioc_readiness_manifest", "management_delivery", "guidance_contradictions", "evidence_watchlist", "monitoring", "peer_registry"):
        wave_path = os.path.join(STATE, "company_intel", f"{name}.json")
        try:
            with open(wave_path, encoding="utf-8") as f:
                wave1[name] = json.load(f)
        except Exception as e:
            fail(f"state/company_intel/{name}.json: {e}")
    expected_event_total = expected_scenario_total = 0
    expected_study_total = 0
    thesis_state = wave1.get("thesis_monitoring") or {}
    confidence_state = wave1.get("intelligence_confidence") or {}
    intelligence_cases_state = wave1.get("intelligence_cases") or {}
    mlcf_pioc_readiness_manifest_state = wave1.get("mlcf_pioc_readiness_manifest") or {}
    management_delivery_state = wave1.get("management_delivery") or {}
    guidance_contradictions_state = wave1.get("guidance_contradictions") or {}
    evidence_watchlist_state = wave1.get("evidence_watchlist") or {}
    monitoring_state = wave1.get("monitoring") or {}
    peer_registry_state = wave1.get("peer_registry") or {}
    if set(thesis_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/thesis_monitoring.json: pilot boundary mismatch")
    if set(thesis_state.get("companies") or {}) != pilot:
        fail("state/company_intel/thesis_monitoring.json: company boundary mismatch")
    if set(confidence_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/intelligence_confidence.json: pilot boundary mismatch")
    if set(confidence_state.get("companies") or {}) != pilot:
        fail("state/company_intel/intelligence_confidence.json: company boundary mismatch")
    if set(intelligence_cases_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/intelligence_cases.json: pilot boundary mismatch")
    if set(intelligence_cases_state.get("companies") or {}) != pilot:
        fail("state/company_intel/intelligence_cases.json: company boundary mismatch")
    if set(mlcf_pioc_readiness_manifest_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/mlcf_pioc_readiness_manifest.json: pilot boundary mismatch")
    if set(mlcf_pioc_readiness_manifest_state.get("companies") or {}) != pilot:
        fail("state/company_intel/mlcf_pioc_readiness_manifest.json: company boundary mismatch")
    if set(management_delivery_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/management_delivery.json: pilot boundary mismatch")
    if set(management_delivery_state.get("companies") or {}) != pilot:
        fail("state/company_intel/management_delivery.json: company boundary mismatch")
    if set(guidance_contradictions_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/guidance_contradictions.json: pilot boundary mismatch")
    if set(guidance_contradictions_state.get("companies") or {}) != pilot:
        fail("state/company_intel/guidance_contradictions.json: company boundary mismatch")
    if set(evidence_watchlist_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/evidence_watchlist.json: pilot boundary mismatch")
    if set(evidence_watchlist_state.get("companies") or {}) != pilot:
        fail("state/company_intel/evidence_watchlist.json: company boundary mismatch")
    if set(monitoring_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/monitoring.json: pilot boundary mismatch")
    if set(monitoring_state.get("companies") or {}) != pilot:
        fail("state/company_intel/monitoring.json: company boundary mismatch")
    if peer_registry_state.get("method") != "pilot_official_sector_cohort_v1":
        fail("state/company_intel/peer_registry.json: method mismatch")
    if set(peer_registry_state.get("pilot_symbols") or []) != pilot:
        fail("state/company_intel/peer_registry.json: pilot boundary mismatch")
    if set(peer_registry_state.get("companies") or {}) != pilot:
        fail("state/company_intel/peer_registry.json: company boundary mismatch")
    for row in rows:
        sym = row.get("symbol") if isinstance(row, dict) else None
        if not sym:
            continue
        expected_events = ((wave1.get("operating_events", {}).get("companies", {}).get(sym) or {}).get("events") or [])
        expected_graph = wave1.get("driver_graphs", {}).get("companies", {}).get(sym)
        expected_scenarios = ((wave1.get("impact_scenarios", {}).get("companies", {}).get(sym) or {}).get("scenarios") or [])
        expected_studies = [v for v in (wave1.get("event_studies", {}).get("studies") or {}).values() if v.get("symbol") == sym]
        conditional_benchmark_state = (wave1.get("conditional_benchmarks", {}).get("companies", {}).get(sym) or {})
        causal_foundations_state = (wave1.get("causal_foundations", {}).get("companies", {}).get(sym) or {})
        model_state = (wave1.get("financial_model_inputs", {}).get("companies", {}).get(sym) or {})
        financial_reconciliation_state = (wave1.get("financial_evidence_reconciliation", {}).get("companies", {}).get(sym) or {})
        earnings_bridge_state = (wave1.get("earnings_bridges", {}).get("companies", {}).get(sym) or {})
        financial_coverage_state = (wave1.get("financial_coverage", {}).get("companies", {}).get(sym) or {})
        financial_truth_state = (wave1.get("financial_truth_qualification", {}).get("companies", {}).get(sym) or {})
        forecast_readiness_state = (wave1.get("forecast_readiness", {}).get("companies", {}).get(sym) or {})
        financial_forecast_state = build_ci_slice._formal_engine_product(
            wave1.get("financial_forecasts", {}), sym, "financial_forecasts", financial_truth_state
        )
        formal_valuation_state = build_ci_slice._formal_engine_product(
            wave1.get("formal_valuations", {}), sym, "formal_valuations", financial_truth_state
        )
        market_expectations_state = build_ci_slice._formal_engine_product(
            wave1.get("market_expectations", {}), sym, "market_expectations", financial_truth_state
        )
        scenario_lab_state = (wave1.get("scenario_lab", {}).get("companies", {}).get(sym) or {})
        company_brain_state = (wave1.get("company_brains", {}).get("companies", {}).get(sym) or {})
        thesis_state_row = (thesis_state.get("companies") or {}).get(sym)
        confidence_state_row = (confidence_state.get("companies") or {}).get(sym)
        evidence_watchlist_state_row = (evidence_watchlist_state.get("companies") or {}).get(sym)
        intelligence_case_state_row = build_ci_slice._intelligence_case_row(
            intelligence_cases_state,
            sym,
            confidence_row=confidence_state_row,
            watchlist_row=evidence_watchlist_state_row,
        )
        mlcf_pioc_readiness_state_row = (mlcf_pioc_readiness_manifest_state.get("companies") or {}).get(sym)
        management_delivery_state_row = (management_delivery_state.get("companies") or {}).get(sym)
        guidance_contradictions_state_row = (guidance_contradictions_state.get("companies") or {}).get(sym)
        monitoring_state_row = (monitoring_state.get("companies") or {}).get(sym)
        peer_registry_state_row = (peer_registry_state.get("companies") or {}).get(sym)
        if "operating_events" not in row or not isinstance(row.get("operating_events"), list):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} operating_events missing/not list")
        elif row.get("operating_events") != expected_events:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} operating_events stale/mismatch")
        if "driver_graph" not in row or not isinstance(row.get("driver_graph"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} driver_graph missing/not dict")
        elif expected_graph is not None and row.get("driver_graph") != expected_graph:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} driver_graph stale/mismatch")
        if "impact_scenarios" not in row or not isinstance(row.get("impact_scenarios"), list):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} impact_scenarios missing/not list")
        elif row.get("impact_scenarios") != expected_scenarios:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} impact_scenarios stale/mismatch")
        if "event_studies" not in row or not isinstance(row.get("event_studies"), list):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} event_studies missing/not list")
        elif row.get("event_studies") != expected_studies:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} event_studies stale/mismatch")
        if row.get("conditional_benchmarks") != conditional_benchmark_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} conditional_benchmarks stale/mismatch")
        if not isinstance(row.get("conditional_benchmarks"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} conditional_benchmarks missing/not object")
        if row.get("causal_foundations") != causal_foundations_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} causal_foundations stale/mismatch")
        if not isinstance(row.get("causal_foundations"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} causal_foundations missing/not object")
        if row.get("financial_model_inputs") != model_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_model_inputs stale/mismatch")
        if row.get("financial_evidence_reconciliation") != financial_reconciliation_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_evidence_reconciliation stale/mismatch")
        if not isinstance(row.get("financial_evidence_reconciliation"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_evidence_reconciliation missing/not object")
        if row.get("earnings_bridges") != earnings_bridge_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} earnings_bridges stale/mismatch")
        if not isinstance(row.get("earnings_bridges"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} earnings_bridges missing/not object")
        if row.get("financial_coverage") != financial_coverage_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_coverage stale/mismatch")
        if not isinstance(row.get("financial_coverage"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_coverage missing/not object")
        if row.get("financial_truth_qualification") != financial_truth_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_truth_qualification stale/mismatch")
        if not isinstance(row.get("financial_truth_qualification"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_truth_qualification missing/not object")
        if row.get("forecast_readiness") != forecast_readiness_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} forecast_readiness stale/mismatch")
        if not isinstance(row.get("forecast_readiness"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} forecast_readiness missing/not object")
        if row.get("financial_forecasts") != financial_forecast_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_forecasts stale/mismatch")
        if not isinstance(row.get("financial_forecasts"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial_forecasts missing/not object")
        if row.get("formal_valuations") != formal_valuation_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} formal_valuations stale/mismatch")
        if not isinstance(row.get("formal_valuations"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} formal_valuations missing/not object")
        if row.get("market_expectations") != market_expectations_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} market_expectations stale/mismatch")
        if not isinstance(row.get("market_expectations"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} market_expectations missing/not object")
        if row.get("scenario_lab") != scenario_lab_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} scenario_lab stale/mismatch")
        if row.get("company_brain") != company_brain_state:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} company_brain stale/mismatch")
        if row.get("thesis_monitoring") != thesis_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} thesis_monitoring stale/mismatch")
        if not isinstance(row.get("thesis_monitoring"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} thesis_monitoring missing/not object")
        if row.get("intelligence_confidence") != confidence_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} intelligence_confidence stale/mismatch")
        if not isinstance(row.get("intelligence_confidence"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} intelligence_confidence missing/not object")
        if row.get("intelligence_cases") != intelligence_case_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} intelligence_cases stale/mismatch")
        if not isinstance(row.get("intelligence_cases"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} intelligence_cases missing/not object")
        if row.get("mlcf_pioc_readiness_manifest") != mlcf_pioc_readiness_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} mlcf_pioc_readiness_manifest stale/mismatch")
        if not isinstance(row.get("mlcf_pioc_readiness_manifest"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} mlcf_pioc_readiness_manifest missing/not object")
        if row.get("management_delivery") != management_delivery_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} management_delivery stale/mismatch")
        if not isinstance(row.get("management_delivery"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} management_delivery missing/not object")
        if row.get("guidance_contradictions") != guidance_contradictions_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} guidance_contradictions stale/mismatch")
        if not isinstance(row.get("guidance_contradictions"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} guidance_contradictions missing/not object")
        if row.get("evidence_watchlist") != evidence_watchlist_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} evidence_watchlist stale/mismatch")
        if not isinstance(row.get("evidence_watchlist"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} evidence_watchlist missing/not object")
        if row.get("monitoring") != monitoring_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} monitoring stale/mismatch")
        if not isinstance(row.get("monitoring"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} monitoring missing/not object")
        if row.get("peer_registry") != peer_registry_state_row:
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} peer_registry stale/mismatch")
        if not isinstance(row.get("peer_registry"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} peer_registry missing/not object")
        expected_event_total += len(expected_events)
        expected_scenario_total += len(expected_scenarios)
        expected_study_total += len(expected_studies)
    actual_event_total = sum(len(row.get("operating_events") or []) for row in rows if isinstance(row, dict))
    actual_scenario_total = sum(len(row.get("impact_scenarios") or []) for row in rows if isinstance(row, dict))
    actual_study_total = sum(len(row.get("event_studies") or []) for row in rows if isinstance(row, dict))
    if actual_event_total != expected_event_total:
        fail(f"CI slice operating event aggregate mismatch: {actual_event_total} != {expected_event_total}")
    if actual_scenario_total != expected_scenario_total:
        fail(f"CI slice scenario aggregate mismatch: {actual_scenario_total} != {expected_scenario_total}")
    if actual_study_total != expected_study_total:
        fail(f"CI slice event-study aggregate mismatch: {actual_study_total} != {expected_study_total}")
    for row in rows:
        sym = row.get("symbol") if isinstance(row, dict) else None
        if not sym:
            fail("Henneth Desk 2.CI.0/data/company_intelligence.json: row missing symbol")
            continue
        profile = row.get("profile") or {}
        if not profile.get("source_url"):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} profile missing source_url")
        if not profile.get("business_description") and not profile.get("incorporation"):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} profile has no parsed content")
        for key in ("filings", "timeline", "changes"):
            if not isinstance(row.get(key), list):
                fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} {key} is not a list")
        if not isinstance(row.get("financial_series"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} missing financial series")
        else:
            for fact in (row.get("financial_series") or {}).get("facts") or []:
                if not fact.get("document_id") or not fact.get("source_url") or not fact.get("evidence"):
                    fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial fact missing provenance")
                if fact.get("quality_flags") is None or not isinstance(fact.get("quality_flags"), list):
                    fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} financial fact flags invalid")
        graph = row.get("graph")
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} missing graph")
        change_digest = row.get("change_intelligence")
        if not isinstance(change_digest, dict) or not isinstance(change_digest.get("items"), list):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} missing change intelligence")
        else:
            for item in change_digest.get("items") or []:
                if not item.get("source_url") and not (item.get("evidence") or {}).get("source_url"):
                    fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} change item missing source")
        if not isinstance(row.get("brief"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} missing brief status")
        if not isinstance(row.get("sources"), dict) or not isinstance(row.get("intelligence"), dict):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} missing intelligence/source maps")
        if (row.get("sources") or {}).get("status") not in ("ok", "degraded"):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} issuer monitor status missing")
        if not any(filing.get("status") == "ready" for filing in (row.get("filings") or [])):
            fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} has no ready official filing")
        for filing in row.get("filings") or []:
            if not filing.get("doc_id") or not filing.get("url"):
                fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} filing missing provenance")
            if filing.get("status") == "ready" and not filing.get("content_sha256"):
                fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} ready filing missing content hash")
            for evidence in filing.get("evidence") or []:
                if not isinstance(evidence.get("page"), int) or evidence["page"] < 1:
                    fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} invalid evidence page")
                if not evidence.get("text") or not evidence.get("source_url"):
                    fail(f"Henneth Desk 2.CI.0/data/company_intelligence.json: {sym} incomplete evidence")


def check_operating_intelligence():
    path = os.path.join(ROOT, "scripts", "check_operating_intelligence.py")
    if not os.path.exists(path):
        fail("check_operating_intelligence.py missing — Wave 1 CI contracts cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("operating intelligence check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_operating_intelligence.py did not run — {e}")

def check_event_studies():
    path = os.path.join(ROOT, "scripts", "check_event_studies.py")
    if not os.path.exists(path):
        fail("check_event_studies.py missing — historical benchmark gate cannot run")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("event studies check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_event_studies.py did not run — {e}")

def check_conditional_benchmarks():
    path = os.path.join(ROOT, "scripts", "check_conditional_benchmarks.py")
    if not os.path.exists(path):
        fail("check_conditional_benchmarks.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("conditional benchmarks check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_conditional_benchmarks.py did not run — {e}")

def check_conditional_benchmarks_ui():
    path = os.path.join(ROOT, "scripts", "check_conditional_benchmarks_ui.mjs")
    if not os.path.exists(path):
        fail("check_conditional_benchmarks_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("conditional benchmarks UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_conditional_benchmarks_ui.mjs did not run — {e}")

def check_signal_clusters():
    path = os.path.join(ROOT, "scripts", "check_signal_clusters.py")
    if not os.path.exists(path):
        fail("check_signal_clusters.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0: fail(f"signal clusters check failed — {result.stdout[-400:] or result.stderr[-400:]}")
    except Exception as e: fail(f"signal clusters check did not run — {e}")

def check_thesis_monitoring():
    path = os.path.join(ROOT, "scripts", "check_thesis_monitoring.py")
    if not os.path.exists(path):
        fail("check_thesis_monitoring.py missing — thesis monitoring contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("thesis monitoring check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_thesis_monitoring.py did not run — {e}")

def check_intelligence_confidence():
    path = os.path.join(ROOT, "scripts", "check_intelligence_confidence.py")
    if not os.path.exists(path):
        fail("check_intelligence_confidence.py missing — intelligence confidence contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("intelligence confidence check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_intelligence_confidence.py did not run — {e}")

def check_intelligence_cases():
    path = os.path.join(ROOT, "scripts", "check_intelligence_cases.py")
    if not os.path.exists(path):
        fail("check_intelligence_cases.py missing — intelligence case contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("intelligence cases check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_intelligence_cases.py did not run — {e}")

def check_mlcf_pioc_readiness_manifest():
    path = os.path.join(ROOT, "scripts", "check_mlcf_pioc_readiness_manifest.py")
    if not os.path.exists(path):
        fail("check_mlcf_pioc_readiness_manifest.py missing — MLCF/PIOC readiness contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("MLCF/PIOC readiness manifest check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_mlcf_pioc_readiness_manifest.py did not run — {e}")

def check_management_delivery():
    path = os.path.join(ROOT, "scripts", "check_management_delivery.py")
    if not os.path.exists(path):
        fail("check_management_delivery.py missing — management delivery contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("management delivery check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_management_delivery.py did not run — {e}")

def check_guidance_contradictions():
    path = os.path.join(ROOT, "scripts", "check_guidance_contradictions.py")
    if not os.path.exists(path):
        fail("check_guidance_contradictions.py missing — guidance/contradiction contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("guidance contradictions check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_guidance_contradictions.py did not run — {e}")

def check_evidence_watchlist():
    path = os.path.join(ROOT, "scripts", "check_evidence_watchlist.py")
    if not os.path.exists(path):
        fail("check_evidence_watchlist.py missing — evidence watchlist contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("evidence watchlist check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_evidence_watchlist.py did not run — {e}")

def check_ci_monitoring():
    path = os.path.join(ROOT, "scripts", "check_ci_monitoring.py")
    if not os.path.exists(path):
        fail("check_ci_monitoring.py missing — CI monitoring contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("CI monitoring check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_ci_monitoring.py did not run — {e}")

def check_ci_work_routing_policy():
    path = os.path.join(ROOT, "scripts", "check_ci_work_routing_policy.py")
    if not os.path.exists(path):
        fail("check_ci_work_routing_policy.py missing — CI work-routing contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("CI work-routing policy check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_ci_work_routing_policy.py did not run — {e}")

def check_peer_registry():
    path = os.path.join(ROOT, "scripts", "check_peer_registry.py")
    if not os.path.exists(path):
        fail("check_peer_registry.py missing — formal peer registry contract cannot be verified")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("peer registry check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_peer_registry.py did not run — {e}")

def check_evidence_watchlist_ui():
    path = os.path.join(ROOT, "scripts", "check_evidence_watchlist_ui.mjs")
    if not os.path.exists(path):
        fail("check_evidence_watchlist_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("evidence watchlist UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_evidence_watchlist_ui.mjs did not run — {e}")

def check_ci_monitoring_ui():
    path = os.path.join(ROOT, "scripts", "check_ci_monitoring_ui.mjs")
    if not os.path.exists(path):
        fail("check_ci_monitoring_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("CI monitoring UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_ci_monitoring_ui.mjs did not run — {e}")

def check_management_delivery_ui():
    path = os.path.join(ROOT, "scripts", "check_management_delivery_ui.mjs")
    if not os.path.exists(path):
        fail("check_management_delivery_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("management delivery UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_management_delivery_ui.mjs did not run — {e}")

def check_guidance_contradictions_ui():
    path = os.path.join(ROOT, "scripts", "check_guidance_contradictions_ui.mjs")
    if not os.path.exists(path):
        fail("check_guidance_contradictions_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("guidance contradictions UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_guidance_contradictions_ui.mjs did not run — {e}")

def check_ask_henneth():
    path = os.path.join(ROOT, "scripts", "check_ask_henneth.mjs")
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0: fail(f"ask contract check failed — {result.stdout[-400:] or result.stderr[-400:]}")
    except Exception as e: fail(f"ask contract check did not run — {e}")

def check_root_ask_hardening():
    path = os.path.join(ROOT, "scripts", "check_root_ask_hardening.mjs")
    if not os.path.exists(path):
        fail("check_root_ask_hardening.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("root ask hardening check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"root ask hardening check did not run — {e}")

def check_ask_henneth_endpoint():
    path = os.path.join(ROOT, "scripts", "check_ask_henneth_endpoint.mjs")
    if not os.path.exists(path):
        fail("check_ask_henneth_endpoint.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail(f"ask endpoint check failed — {result.stdout[-400:] or result.stderr[-400:]}")
    except Exception as e:
        fail(f"ask endpoint check did not run — {e}")

def check_ask_henneth_ui():
    path = os.path.join(ROOT, "scripts", "check_ask_henneth_ui.mjs")
    if not os.path.exists(path):
        fail("check_ask_henneth_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail(f"ask UI check failed — {result.stdout[-400:] or result.stderr[-400:]}")
    except Exception as e:
        fail(f"ask UI check did not run — {e}")

def check_financial_model_inputs():
    path = os.path.join(ROOT, "scripts", "check_financial_model_inputs.py")
    if not os.path.exists(path):
        fail("check_financial_model_inputs.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("financial model inputs check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))

def check_cement_operating_series():
    path = os.path.join(ROOT, "scripts", "check_cement_operating_series.py")
    if not os.path.exists(path):
        fail("check_cement_operating_series.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("cement operating series check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))


def check_cement_historical_reconciliation():
    path = os.path.join(ROOT, "scripts", "check_cement_historical_reconciliation.py")
    if not os.path.exists(path):
        fail("check_cement_historical_reconciliation.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("cement historical reconciliation check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))


def check_supabase_archive_receipt():
    path = os.path.join(ROOT, "scripts", "check_supabase_archive_receipt.py")
    if not os.path.exists(path):
        fail("check_supabase_archive_receipt.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("Supabase archive receipt check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))


def check_private_thesis_storage_receipt():
    path = os.path.join(ROOT, "scripts", "check_private_thesis_storage_receipt.py")
    if not os.path.exists(path):
        fail("check_private_thesis_storage_receipt.py missing — private thesis activation boundary cannot be verified")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("private thesis storage receipt check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))


def check_financial_coverage():
    path = os.path.join(ROOT, "scripts", "check_financial_coverage.py")
    if not os.path.exists(path):
        fail("check_financial_coverage.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial coverage check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_coverage.py did not run — {e}")

def check_financial_truth_qualification():
    path = os.path.join(ROOT, "scripts", "check_financial_truth_qualification.py")
    if not os.path.exists(path):
        fail("check_financial_truth_qualification.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial truth qualification check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_truth_qualification.py did not run — {e}")

def check_mlcf_financial_audits():
    """Run the committed MLCF derived-fact contract."""
    for name in (
        "check_mlcf_derived_facts.py",
        "check_mlcf_canonical_promotion_acceptance.py",
    ):
        path = os.path.join(ROOT, "scripts", name)
        if not os.path.exists(path):
            fail(f"{name} missing — MLCF audit contract cannot be verified")
            continue
        try:
            result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=45)
            if result.returncode != 0:
                fail(f"{name} failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
        except Exception as e:
            fail(f"{name} did not run — {e}")

def check_official_share_capital_approvals():
    path = os.path.join(ROOT, "scripts", "check_official_share_capital_approvals.py")
    if not os.path.exists(path):
        fail("check_official_share_capital_approvals.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("official share-capital approval check failed: " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_official_share_capital_approvals.py did not run: {e}")


def check_financial_statement_v2_candidate_queue():
    path = os.path.join(ROOT, "scripts", "check_financial_statement_v2_candidate_queue.py")
    if not os.path.exists(path):
        fail("check_financial_statement_v2_candidate_queue.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial statement v2 candidate queue check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_statement_v2_candidate_queue.py did not run — {e}")

def check_financial_reprocess_blockers():
    path = os.path.join(ROOT, "scripts", "check_financial_reprocess_blockers.py")
    if not os.path.exists(path):
        fail("check_financial_reprocess_blockers.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial reprocess blockers check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_reprocess_blockers.py did not run — {e}")

def check_forecast_contract():
    path = os.path.join(ROOT, "scripts", "check_forecast_contract.py")
    if not os.path.exists(path):
        fail("check_forecast_contract.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("forecast readiness contract check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_forecast_contract.py did not run — {e}")

def check_financial_engine_assumptions():
    path = os.path.join(ROOT, "scripts", "check_financial_engine_assumptions.py")
    if not os.path.exists(path):
        fail("check_financial_engine_assumptions.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial engine assumptions check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_engine_assumptions.py did not run — {e}")

def check_owner_financial_assumptions():
    path = os.path.join(ROOT, "scripts", "check_owner_financial_assumptions.py")
    if not os.path.exists(path):
        fail("check_owner_financial_assumptions.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("owner financial assumptions check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_owner_financial_assumptions.py did not run — {e}")

def check_formal_financial_engines():
    path = os.path.join(ROOT, "scripts", "check_formal_financial_engines.py")
    if not os.path.exists(path):
        fail("check_formal_financial_engines.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("formal financial engines check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_formal_financial_engines.py did not run — {e}")

def check_ci_reference_cases():
    path = os.path.join(ROOT, "scripts", "check_ci_reference_cases.py")
    if not os.path.exists(path):
        fail("check_ci_reference_cases.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("CI reference-case check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_ci_reference_cases.py did not run — {e}")

def check_financial_evidence_reconciliation():
    path = os.path.join(ROOT, "scripts", "check_financial_evidence_reconciliation.py")
    if not os.path.exists(path):
        fail("check_financial_evidence_reconciliation.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial evidence reconciliation check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_evidence_reconciliation.py did not run — {e}")

def check_earnings_bridges():
    path = os.path.join(ROOT, "scripts", "check_earnings_bridges.py")
    if not os.path.exists(path):
        fail("check_earnings_bridges.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("earnings bridges check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_earnings_bridges.py did not run — {e}")

def check_earnings_bridges_ui():
    path = os.path.join(ROOT, "scripts", "check_earnings_bridges_ui.mjs")
    if not os.path.exists(path):
        fail("check_earnings_bridges_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("earnings bridges UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_earnings_bridges_ui.mjs did not run — {e}")

def check_forecast_readiness_ui():
    path = os.path.join(ROOT, "scripts", "check_forecast_readiness_ui.mjs")
    if not os.path.exists(path):
        fail("check_forecast_readiness_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("forecast readiness UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_forecast_readiness_ui.mjs did not run — {e}")

def check_cement_operating_series_ui():
    path = os.path.join(ROOT, "scripts", "check_cement_operating_series_ui.mjs")
    if not os.path.exists(path):
        fail("check_cement_operating_series_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("cement operating series UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_cement_operating_series_ui.mjs did not run — {e}")

def check_causal_foundations():
    path = os.path.join(ROOT, "scripts", "check_causal_foundations.py")
    if not os.path.exists(path):
        fail("check_causal_foundations.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("causal foundations check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_causal_foundations.py did not run — {e}")

def check_causal_foundations_ui():
    path = os.path.join(ROOT, "scripts", "check_causal_foundations_ui.mjs")
    if not os.path.exists(path):
        fail("check_causal_foundations_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("causal foundations UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_causal_foundations_ui.mjs did not run — {e}")

def check_financial_coverage_ui():
    path = os.path.join(ROOT, "scripts", "check_financial_coverage_ui.mjs")
    if not os.path.exists(path):
        fail("check_financial_coverage_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial coverage UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_coverage_ui.mjs did not run — {e}")

def check_financial_truth_qualification_ui():
    path = os.path.join(ROOT, "scripts", "check_financial_truth_qualification_ui.mjs")
    if not os.path.exists(path):
        fail("check_financial_truth_qualification_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial truth qualification UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_truth_qualification_ui.mjs did not run — {e}")

def check_historical_reference_cases_ui():
    path = os.path.join(ROOT, "scripts", "check_historical_reference_cases_ui.mjs")
    if not os.path.exists(path):
        fail("check_historical_reference_cases_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("historical reference cases UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_historical_reference_cases_ui.mjs did not run — {e}")

def check_financial_evidence_reconciliation_ui():
    path = os.path.join(ROOT, "scripts", "check_financial_evidence_reconciliation_ui.mjs")
    if not os.path.exists(path):
        fail("check_financial_evidence_reconciliation_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("financial evidence reconciliation UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_financial_evidence_reconciliation_ui.mjs did not run — {e}")

def check_company_scenario_lab():
    path = os.path.join(ROOT, "scripts", "check_company_scenario_lab.py")
    if not os.path.exists(path):
        fail("check_company_scenario_lab.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company scenario lab check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_scenario_lab.py did not run — {e}")

def check_company_scenario_lab_ui():
    path = os.path.join(ROOT, "scripts", "check_company_scenario_lab_ui.mjs")
    if not os.path.exists(path):
        fail("check_company_scenario_lab_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company scenario lab UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_scenario_lab_ui.mjs did not run — {e}")

def check_company_brains():
    path = os.path.join(ROOT, "scripts", "check_company_brains.py")
    if not os.path.exists(path):
        fail("check_company_brains.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company brain check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_brains.py did not run — {e}")

def check_company_brain_formal_engines():
    path = os.path.join(ROOT, "scripts", "check_company_brain_formal_engines.py")
    if not os.path.exists(path):
        fail("check_company_brain_formal_engines.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("Company Brain formal engine check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_brain_formal_engines.py did not run — {e}")

def check_company_brain_source_index():
    path = os.path.join(ROOT, "scripts", "check_company_brain_source_index.py")
    if not os.path.exists(path):
        fail("check_company_brain_source_index.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("Company Brain source-index check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_brain_source_index.py did not run — {e}")

def check_company_brain_ui():
    path = os.path.join(ROOT, "scripts", "check_company_brain_ui.mjs")
    if not os.path.exists(path):
        fail("check_company_brain_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company brain UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_brain_ui.mjs did not run — {e}")

def check_ci_completion_matrix():
    path = os.path.join(ROOT, "scripts", "check_ci_completion_matrix.py")
    if not os.path.exists(path):
        fail("check_ci_completion_matrix.py missing")
        return
    try:
        matrix_env = dict(os.environ)
        # Preflight has already executed each product checker directly. Avoid running the same
        # aggregate a second time while retaining the completion-matrix consistency check.
        matrix_env["HENNETH_CI_PRODUCT_CONTRACTS_VERIFIED_BY_PREFLIGHT"] = "1"
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30, env=matrix_env)
        if result.returncode != 0:
            fail("CI completion matrix check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_ci_completion_matrix.py did not run — {e}")


def check_ci_global_no_lookahead():
    """Consumer-facing CI dates must not exceed an explicit product cutoff."""
    path = os.path.join(ROOT, "scripts", "check_ci_global_no_lookahead.py")
    if not os.path.exists(path):
        fail("check_ci_global_no_lookahead.py missing")
        return
    try:
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=45)
        if result.returncode != 0:
            fail("CI global no-lookahead check failed — " + checker_failure_detail(result))
    except Exception as e:
        fail(f"check_ci_global_no_lookahead.py did not run — {e}")


def check_ci_artifact_integrity(build_cutoff_at=None):
    """Stamp the completed CI state, then verify the envelope as the final gate."""
    finalizer = os.path.join(ROOT, "scripts", "build_ci_artifact_integrity.py")
    path = os.path.join(ROOT, "scripts", "check_ci_artifact_integrity.py")
    if not os.path.exists(finalizer):
        fail("build_ci_artifact_integrity.py missing — final CI envelope cannot be produced")
        return
    if not os.path.exists(path):
        fail("check_ci_artifact_integrity.py missing")
        return
    try:
        # A preflight invocation owns one UTC build boundary.  Pass that exact
        # cutoff through to the finalizer so it cannot sample a later ``now``
        # while the rest of the gate is still running.
        finalizer_env = dict(os.environ)
        if build_cutoff_at:
            finalizer_env["HENNETH_CI_BUILD_CUTOFF_AT"] = str(build_cutoff_at)
        built = subprocess.run(
            [sys.executable, finalizer], capture_output=True, text=True, timeout=45, env=finalizer_env
        )
        if built.returncode != 0:
            fail("CI artifact finalizer failed — " + ((built.stdout or built.stderr or "")[-500:].strip()))
            return
        result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=45)
        if result.returncode != 0:
            fail("CI artifact-integrity check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_ci_artifact_integrity.py did not run — {e}")


def check_company_navigation_ui():
    path = os.path.join(ROOT, "scripts", "check_company_navigation_ui.mjs")
    if not os.path.exists(path):
        fail("check_company_navigation_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company navigation UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_navigation_ui.mjs did not run — {e}")

def check_thesis_monitoring_ui():
    path = os.path.join(ROOT, "scripts", "check_thesis_monitoring_ui.mjs")
    if not os.path.exists(path):
        fail("check_thesis_monitoring_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("thesis monitoring UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_thesis_monitoring_ui.mjs did not run — {e}")

def check_intelligence_confidence_ui():
    path = os.path.join(ROOT, "scripts", "check_intelligence_confidence_ui.mjs")
    if not os.path.exists(path):
        fail("check_intelligence_confidence_ui.mjs missing")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("intelligence confidence UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_intelligence_confidence_ui.mjs did not run — {e}")

def check_company_theses_security():
    path = os.path.join(ROOT, "scripts", "check_company_theses_security.mjs")
    if not os.path.exists(path):
        fail("check_company_theses_security.mjs missing — private thesis RLS contract cannot be verified")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company theses security check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_theses_security.mjs did not run — {e}")

def check_company_theses_ui():
    path = os.path.join(ROOT, "scripts", "check_company_theses_ui.mjs")
    if not os.path.exists(path):
        fail("check_company_theses_ui.mjs missing — private thesis UI contract cannot be verified")
        return
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            fail("company theses UI check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))
    except Exception as e:
        fail(f"check_company_theses_ui.mjs did not run — {e}")

def check_reprocess_documents():
    if os.environ.get("HENNETH_REPROCESS_TRANSACTION") == "1":
        print("  INFO: reprocess document self-check skipped inside active reprocess transaction")
        return
    path = os.path.join(ROOT, "scripts", "check_reprocess_company_documents.py")
    if not os.path.exists(path):
        fail("check_reprocess_company_documents.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        fail("reprocess document check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))

def check_ocr_quarantine():
    path = os.path.join(ROOT, "scripts", "check_ocr_quarantine.py")
    if not os.path.exists(path):
        fail("check_ocr_quarantine.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("OCR quarantine check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))

def check_ci_reprocess_manifest():
    path = os.path.join(ROOT, "scripts", "check_ci_reprocess_manifest.py")
    if not os.path.exists(path):
        fail("check_ci_reprocess_manifest.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("CI reprocess manifest check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))

def check_mari_sales_event_intake():
    path = os.path.join(ROOT, "scripts", "check_mari_sales_event_intake.py")
    if not os.path.exists(path):
        fail("check_mari_sales_event_intake.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("MARI sales event intake check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))

def check_ownership_source_manifest():
    path = os.path.join(ROOT, "scripts", "check_ownership_source_manifest.py")
    if not os.path.exists(path):
        fail("check_ownership_source_manifest.py missing")
        return
    result = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        fail("ownership source manifest check failed — " + ((result.stdout or result.stderr or "")[-500:].strip()))

def check_no_raw_artifacts():
    for root in (os.path.join(ROOT, "Henneth Desk 2.CI.0"), os.path.join(ROOT, "dashboard"), os.path.join(ROOT, "site", "public"), os.path.join(ROOT, "site", "dist")):
        for dirpath, _, files in os.walk(root):
            if "node_modules" in dirpath.replace("\\", "/") or ".cache" in dirpath.replace("\\", "/"): continue
            for name in files:
                if name.lower() == "moon_ephem.bin": continue
                if name.lower().endswith((".pdf", ".bin")) or "reprocess" in name.lower():
                    fail(f"served/raw artifact present: {os.path.relpath(os.path.join(dirpath,name), ROOT)}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # never die on a unicode dash in a message
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--self-test", action="store_true", help="run isolated preflight helper checks")
    args = ap.parse_args()

    if args.self_test:
        class _Result:
            stdout = "summary: harmless opaque example"
            stderr = "failure: actual no-lookahead violation"

        if checker_failure_detail(_Result()) != _Result.stderr:
            raise SystemExit("preflight self-test failed: stderr must take priority over stdout")
        _Result.stderr = ""
        if checker_failure_detail(_Result()) != _Result.stdout:
            raise SystemExit("preflight self-test failed: stdout fallback missing")
        print("preflight self-test: PASS")
        raise SystemExit(0)
    # Capture one explicit UTC cutoff at invocation start.  All generated CI
    # artifacts finalized below share this boundary, regardless of gate duration.
    build_cutoff_at = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Tier-1 code QA: instant, free, blocks a broken build before anything else runs ---
    check_code_syntax()
    check_ci_contract_workflow()
    # --- Tier-1 accuracy QA: block assumed/hollow/stale content from reaching users ---
    check_provenance()
    # --- Tier-1 maths QA: Rule 4 + payout sign guard ---
    check_rule4()
    # --- Root deployment boundary: CI-owner-only artifacts never ship from desk.henneth.app ---
    check_root_state_publication()
    # --- Generated URL safety: state URLs can only become http(s) browser links ---
    check_generated_url_safety()
    check_document_intelligence()
    check_company_intelligence_phase2()
    check_operating_intelligence()
    check_event_studies()
    check_conditional_benchmarks()
    check_conditional_benchmarks_ui()
    check_signal_clusters()
    check_root_ask_hardening()
    check_ask_henneth()
    check_ask_henneth_endpoint()
    check_ask_henneth_ui()
    check_causal_foundations()
    check_causal_foundations_ui()
    check_financial_model_inputs()
    check_cement_operating_series()
    check_cement_historical_reconciliation()
    check_supabase_archive_receipt()
    check_private_thesis_storage_receipt()
    check_cement_operating_series_ui()
    check_financial_coverage()
    check_financial_truth_qualification()
    check_mlcf_financial_audits()
    check_official_share_capital_approvals()
    check_financial_statement_v2_candidate_queue()
    check_financial_reprocess_blockers()
    check_forecast_contract()
    check_owner_financial_assumptions()
    check_financial_engine_assumptions()
    check_formal_financial_engines()
    check_ci_reference_cases()
    check_financial_evidence_reconciliation()
    check_earnings_bridges()
    check_earnings_bridges_ui()
    check_forecast_readiness_ui()
    check_financial_coverage_ui()
    check_financial_truth_qualification_ui()
    check_historical_reference_cases_ui()
    check_financial_evidence_reconciliation_ui()
    check_company_scenario_lab()
    check_company_scenario_lab_ui()
    check_company_brains()
    check_company_brain_formal_engines()
    check_company_brain_source_index()
    check_company_brain_ui()
    check_ci_completion_matrix()
    check_ci_global_no_lookahead()
    check_company_navigation_ui()
    check_thesis_monitoring_ui()
    check_intelligence_confidence_ui()
    check_company_theses_security()
    check_company_theses_ui()
    check_intelligence_confidence()
    check_intelligence_cases()
    check_mlcf_pioc_readiness_manifest()
    check_management_delivery()
    check_guidance_contradictions()
    check_evidence_watchlist()
    check_ci_monitoring()
    check_ci_work_routing_policy()
    check_peer_registry()
    check_evidence_watchlist_ui()
    check_ci_monitoring_ui()
    check_management_delivery_ui()
    check_guidance_contradictions_ui()
    check_reprocess_documents()
    check_ocr_quarantine()
    check_ci_reprocess_manifest()
    check_mari_sales_event_intake()
    check_ownership_source_manifest()
    check_no_raw_artifacts()
    # --- Company intelligence shape: every populated row, not a sample ---
    check_company_profiles()
    check_ci_slice()
    check_thesis_monitoring()

    # --- files the dashboard hard-depends on, with the exact shape the UI reads ---
    check("health.json", top_keys=("status",))
    check("quant.json", min_tickers=20, ticker_fields=("rsi14", "ret_20d", "close"))
    check("predictability.json", min_tickers=20)
    check("fairvalue.json", min_tickers=10, ticker_fields=("methods", "composite_fair", "verdict"))
    check("global.json", top_keys=("instruments",))
    check("dashboard.json")
    check("macro.json", top_keys=("regime",))

    # global.json must actually carry instruments (the ticker tape + macro page)
    gl, _ = load("global.json")
    if gl and not gl.get("instruments"):
        fail("global.json: instruments is empty — ticker tape and macro page go blank")

    # fairvalue methods must be non-empty per ticker (the new value working depends on it)
    fv, _ = load("fairvalue.json")
    if fv:
        empties = [s for s, v in list(fv.get("tickers", {}).items())[:10]
                   if not v.get("methods")]
        if empties:
            fail(f"fairvalue.json: tickers with empty methods: {', '.join(empties)}")

    # Per-ticker history completeness — the "No data for XXX" class: a symbol in the
    # universe with a missing/empty history/{sym}.json renders a dead ticker page that
    # the client CANNOT self-heal (the file genuinely isn't on the server). Gate it here.
    #
    # Distinguish REGRESSED tickers (previously covered — present in quant.json — now
    # missing, a real broken-cycle signal) from BRAND-NEW-TO-THE-UNIVERSE tickers (never
    # covered before, still backfilling — e.g. right after a universe expansion). Only
    # regressions count toward the hard FAIL threshold; new tickers only ever WARN, so
    # widening the universe can never block publishing everything else while it backfills.
    uni, _ = load("universe.json")
    quant_prev, _ = load("quant.json")
    prev_covered = set((quant_prev or {}).get("tickers", {})) if quant_prev else set()
    if uni and isinstance(uni.get("symbols"), dict):
        symbols = list(uni["symbols"])
        hist_dir = os.path.join(STATE, "history")
        missing = []
        for s in symbols:
            p = os.path.join(hist_dir, f"{s}.json")
            try:
                if not os.path.exists(p) or os.path.getsize(p) < 20:
                    missing.append(s)
                    continue
                with open(p, encoding="utf-8") as f:
                    if len(json.load(f)) < 2:      # need at least a couple of bars to render
                        missing.append(s)
            except Exception:
                missing.append(s)
        if symbols:
            regressed = [s for s in missing if s in prev_covered]
            new_backfilling = [s for s in missing if s not in prev_covered]
            frac = len(regressed) / len(symbols)
            # a few missing is tolerable (a new listing mid-fetch); a broad REGRESSION is a broken cycle
            if frac > 0.10:
                fail(f"history/: {len(regressed)}/{len(symbols)} previously-covered tickers lost their "
                     f"history ({frac:.0%}) — their ticker pages would show 'No data'. e.g. {', '.join(regressed[:8])}")
            elif regressed:
                warn(f"history/: {len(regressed)} previously-covered ticker(s) missing history (pages "
                     f"self-heal-retry but stay empty until refetched): {', '.join(regressed[:12])}")
            if new_backfilling:
                warn(f"history/: {len(new_backfilling)} newly-added universe ticker(s) still backfilling "
                     f"history (never gates publish): {', '.join(new_backfilling[:12])}")

    # Desk Room layer (advisory — WARN not FAIL while the loop is young, so a missing
    # dossier can't block the core desk from deploying)
    check("dossiers.json", required=False)
    check("room_queue.json", required=False)
    dj, _ = load("dossiers.json")
    if dj and dj.get("_meta", {}).get("n_tickers", 0) < 10:
        warn("dossiers.json: fewer than 10 tickers compiled")

    # health gate: if the desk itself says data is bad, warn loudly
    h, _ = load("health.json")
    if h and h.get("status") not in ("ok", "healthy", None):
        warn(f"health.json status = '{h.get('status')}' — desk is in degraded mode")

    # Final CI release step. Ordinary checks above may rebuild state artifacts; stamp only after
    # they all finish, and keep integrity verification immediately last so no checker can erase
    # the envelope before the deploy decision is reported.
    check_ci_artifact_integrity(build_cutoff_at)

    # --- report ---
    print("Henneth - preflight")
    if warns:
        print(f"\n  WARN ({len(warns)}):")
        for w in warns:
            print(f"    ! {w}")
    if fails:
        print(f"\n  FAIL ({len(fails)}):")
        for f in fails:
            print(f"    x {f}")
        print("\n  RESULT: DO NOT DEPLOY — fix the above first.")
        sys.exit(1)
    if args.strict and warns:
        print("\n  RESULT: blocked (--strict, warnings present).")
        sys.exit(1)
    print(f"\n  RESULT: OK — {0 if fails else 'all'} checks passed, safe to deploy.")
    sys.exit(0)


if __name__ == "__main__":
    main()
