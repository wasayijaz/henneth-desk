#!/usr/bin/env python3
"""Run the independent, deterministic Company Intelligence refresh.

This is intentionally separate from ``run_cloud.py`` and the Henneth Desk
workflow. It polls only official-source producers and, when their retained
source seams change, immediately runs the existing CI evidence consumers. No
LLM, Desk script, or per-company scheduled task is involved. A scheduler may
invoke this once daily; issuer discovery is limited to Mondays in UTC unless
``--force`` is explicitly used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from build_ci_refresh_receipt import RECEIPT, source_inventory, build_receipt, validate_receipt, utc_now
from psx_data import ROOT, save_json, load_json


# This is the bounded evidence path described in docs/ARCHITECTURE.md. Keep it
# explicit: adding a Desk producer, an LLM orchestrator, or a roster-wide AI
# stage here would turn a maintenance refresh into a full cycle.
CI_PIPELINE: tuple[tuple[str, str, str | None], ...] = (
    ("document-intelligence", "document_intelligence.py", "state/company_documents.json"),
    ("financial-series", "build_financial_series.py", "state/company_financial_series.json"),
    # CI-only deterministic segment, kept in the same dependency order as the
    # existing cloud pipeline. Desk data, market fetches, and Room stages are
    # intentionally absent.
    ("financial-model-inputs", "build_financial_model_inputs.py", "state/company_intel/financial_model_inputs.json"),
    ("financial-coverage", "build_financial_coverage.py", "state/company_intel/financial_coverage.json"),
    ("financial-statement-candidates", "build_financial_statement_v2_candidate_queue.py", "state/company_intel/financial_statement_v2_candidate_queue.json"),
    ("forecast-readiness", "build_forecast_readiness.py", "state/company_intel/forecast_readiness.json"),
    ("financial-reprocess-blockers", "build_financial_reprocess_blockers.py", "state/company_intel/financial_reprocess_blockers.json"),
    # Server-only owner handoff. Without the CI Supabase secrets this is an
    # explicit no-op, but it must precede the assumptions consumer.
    ("owner-financial-assumptions", "import_owner_financial_assumptions.py", "state/company_intel/financial_engine_assumptions.json"),
    ("financial-engine-assumptions", "build_financial_engine_assumptions.py", "state/company_intel/financial_engine_assumptions.json"),
    ("official-share-capital-approvals", "build_official_share_capital_approvals.py", "state/company_intel/official_share_capital_approvals.json"),
    ("financial-evidence-reconciliation", "build_financial_evidence_reconciliation.py", "state/company_intel/financial_evidence_reconciliation.json"),
    ("earnings-bridges", "build_earnings_bridges.py", "state/company_intel/earnings_bridges.json"),
    ("cement-operating-series", "build_cement_operating_series.py", "state/company_intel/cement_operating_series.json"),
    ("cement-historical-reconciliation", "cement_historical_reconciliation.py", "state/company_intel/cement_historical_reconciliation.json"),
    ("financial-truth-qualification", "build_financial_truth_qualification.py", "state/company_intel/financial_truth_qualification.json"),
    ("formal-financial-engines", "build_formal_financial_engines.py", "state/company_intel/financial_forecasts.json"),
    ("source-qa", "build_source_qa.py", "state/company_source_qa.json"),
    ("company-graph", "build_company_graph.py", "state/company_intel/company_graph.json"),
    ("change-intelligence", "build_change_intelligence.py", "state/company_intel/change_intelligence.json"),
    ("operating-events", "build_operating_events.py", "state/company_intel/operating_events.json"),
    ("driver-graphs", "build_driver_graphs.py", "state/company_intel/driver_graphs.json"),
    ("impact-engine", "impact_engine.py", "state/company_intel/impact_scenarios.json"),
    ("signal-clusters", "build_signal_clusters.py", "state/company_intel/signal_clusters.json"),
    ("thesis-monitoring", "build_thesis_monitoring.py", "state/company_intel/thesis_monitoring.json"),
    ("intelligence-confidence", "build_intelligence_confidence.py", "state/company_intel/intelligence_confidence.json"),
    ("intelligence-cases", "build_intelligence_cases.py", "state/company_intel/intelligence_cases.json"),
    ("mlcf-pioc-readiness", "build_mlcf_pioc_readiness_manifest.py", "state/company_intel/mlcf_pioc_readiness_manifest.json"),
    ("guidance-contradictions", "build_guidance_contradictions.py", "state/company_intel/guidance_contradictions.json"),
    ("management-delivery", "build_management_delivery.py", "state/company_intel/management_delivery.json"),
    ("evidence-watchlist", "build_evidence_watchlist.py", "state/company_intel/evidence_watchlist.json"),
    ("ci-monitoring", "build_ci_monitoring.py", "state/company_intel/monitoring.json"),
    ("peer-registry", "build_peer_registry.py", "state/company_intel/peer_registry.json"),
    ("event-studies", "build_event_studies.py", "state/company_intel/event_studies.json"),
    ("conditional-benchmarks", "build_conditional_benchmarks.py", "state/company_intel/conditional_benchmarks.json"),
    ("historical-state-map", "build_historical_state_map.py", "state/company_intel/historical_state_map.json"),
    ("causal-foundations", "build_causal_foundations.py", "state/company_intel/causal_foundations.json"),
    ("company-scenario-lab", "build_company_scenario_lab.py", "state/company_intel/scenario_lab.json"),
    ("company-brains", "build_company_brains.py", "state/company_intel/company_brains.json"),
    ("event-review-windows", "build_event_review_windows.py", "state/company_intel/event_review_windows.json"),
    ("ci-work-routing", "build_ci_work_routing_policy.py", "state/company_intel/work_routing_policy.json"),
    ("ownership-source-manifest", "build_ownership_source_manifest.py", "config/ownership_source_review_manifest.json"),
    ("ci-completion-matrix", "build_ci_completion_matrix.py", "state/company_intel/completion_matrix.json"),
    ("ci-slice", "build_ci_slice.py", "Henneth Desk 2.CI.0/data/company_intelligence.json"),
    ("ci-artifact-integrity", "build_ci_artifact_integrity.py", "state/company_intel/artifact_integrity.json"),
    # The archive sink is explicitly advisory in the established pipeline. It
    # is a CI-only append path and has no effect when its server credentials are
    # absent.
    ("ci-archive", "supabase_ci_store.py", None),
)

CI_CHECKS: tuple[str, ...] = (
    "check_ci_artifact_integrity.py",
    "check_ci_completion_matrix.py",
    "check_financial_model_inputs.py",
    "check_financial_coverage.py",
    "check_financial_evidence_reconciliation.py",
    "check_financial_truth_qualification.py",
    "check_formal_financial_engines.py",
    "check_intelligence_cases.py",
    "check_event_studies.py",
    "check_ci_work_routing_policy.py",
)


def _diagnostic_has_failure(text: str) -> bool:
    """Recognize the existing producers' exit-0 degraded convention."""
    lowered = text.lower()
    if "last-good retained" in lowered or "degraded" in lowered:
        return True
    for match in re.finditer(r"(\d+)\s+(?:ticker\s+)?(?:errors?|failures?)", lowered):
        if int(match.group(1)) > 0:
            return True
    return False


def _diagnostic_has_change(text: str) -> bool:
    """Recognize a producer's explicit changed-work counters.

    The source inventory is authoritative for retained-source identity. These
    counters cover a successful retry that stages bytes for an already-known
    document, where the metadata hash itself does not change yet.
    """
    lowered = text.lower()
    patterns = (
        r"(\d+)\s+metadata changes?",
        r"(\d+)\s+new/changed page hashes?",
        r"(\d+)\s+pdfs staged",
        r"(\d+)\s+documents? staged",
    )
    return any(int(match.group(1)) > 0 for pattern in patterns for match in re.finditer(pattern, lowered))


def _run_poll(name: str, args: list[str], cadence: str, *, changed: bool = False) -> dict:
    started = utc_now()
    try:
        proc = subprocess.run(
            [sys.executable, *args], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900,
        )
        status = "degraded" if proc.returncode != 0 or _diagnostic_has_failure(proc.stdout) else "ok"
        return {
            "name": name, "cadence": cadence, "status": status,
            "returncode": proc.returncode, "started_at": started,
            "finished_at": utc_now(), "changed": bool(changed or _diagnostic_has_change(proc.stdout)),
            "diagnostic": proc.stdout[-1200:],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": name, "cadence": cadence, "status": "degraded",
            "returncode": 1, "started_at": started, "finished_at": utc_now(),
            "changed": False, "diagnostic": f"{type(exc).__name__}:{exc}",
        }


def _poll_due(force: bool, now: datetime | None = None) -> bool:
    return force or (now or datetime.now(timezone.utc)).weekday() == 0


def _run_producer(name: str, args: list[str], cadence: str) -> dict:
    """Run a source producer and bind its changed bit to retained state."""
    before = source_inventory()
    result = _run_poll(name, args, cadence)
    after = source_inventory()
    result["changed"] = bool(result.get("changed") or before != after)
    return result


def _run_ci_step(name: str, script: str, output: str | None) -> dict:
    result = _run_poll(
        name,
        [str(ROOT / "scripts" / script)],
        "daily",
    )
    result["output"] = output
    return result


def _run_extraction_chain(polls: list[dict], outputs: list[str]) -> bool:
    """Consume the current-run handoff before another producer can replace it."""
    for name, script, output in CI_PIPELINE[:2]:
        result = _run_ci_step(name, script, output)
        polls.append(result)
        if output:
            outputs.append(output)
        if result.get("status") == "degraded":
            return False
    return True


def _run_ci_checks(polls: list[dict]) -> bool:
    for script in CI_CHECKS:
        result = _run_poll(
            script.removesuffix(".py"),
            [str(ROOT / "scripts" / script)],
            "daily",
        )
        polls.append(result)
        if result.get("status") == "degraded":
            return False
    return True


def _run_derived_chain(polls: list[dict], outputs: list[str]) -> bool:
    """Build the small deterministic CI projection after evidence extraction."""
    for name, script, output in CI_PIPELINE[2:]:
        result = _run_ci_step(name, script, output)
        polls.append(result)
        if output:
            outputs.append(output)
        if result.get("status") == "degraded":
            # The archive sink is advisory in the established cloud pipeline;
            # a transient archive outage must not prevent local CI checks from
            # proving the deterministic outputs.
            if name != "ci-archive":
                return False
    return True


def run(*, force: bool = False, skip_network: bool = False) -> int:
    before = source_inventory()
    polls: list[dict] = []
    outputs = [
        "state/research_index.json",
        "state/company_intel/cursors.json",
        "state/company_intel/source_registry.json",
    ]
    producer_failed = False
    evidence_changed = False
    if skip_network:
        polls.append({
            "name": "dry-run", "cadence": "none", "status": "ok", "returncode": 0,
            "started_at": utc_now(), "finished_at": utc_now(),
            "changed": False, "diagnostic": "network polling skipped",
        })
    else:
        # The official producer owns conditional requests, bounded PDF staging,
        # and last-good retention. Do not use --metadata-only: a changed official
        # filing must reach document_intelligence in this same run.
        psx = _run_producer(
            "psx-official-index",
            [str(ROOT / "scripts" / "fetch_company_documents.py"), "--force"],
            "daily",
        )
        polls.append(psx)
        evidence_changed = bool(psx.get("changed"))
        producer_failed = psx.get("status") == "degraded"
        if not producer_failed and (evidence_changed or force):
            if not _run_extraction_chain(polls, outputs):
                producer_failed = True

        if not producer_failed and _poll_due(force):
            # Existing issuer producer owns ETag/Last-Modified and its retained cache.
            issuer = _run_producer(
                "issuer-source-index",
                [str(ROOT / "scripts" / "fetch_issuer_sources.py"), "--force"],
                "weekly",
            )
            polls.append(issuer)
            producer_failed = issuer.get("status") == "degraded"
            evidence_changed = bool(evidence_changed or issuer.get("changed"))
            if not producer_failed and (issuer.get("changed") or force):
                staged = _run_producer(
                    "issuer-document-stage",
                    [str(ROOT / "scripts" / "stage_issuer_documents.py"), "--force"],
                    "weekly",
                )
                polls.append(staged)
                producer_failed = staged.get("status") == "degraded"
                evidence_changed = bool(evidence_changed or staged.get("changed"))
                if not producer_failed and staged.get("changed"):
                    if not _run_extraction_chain(polls, outputs):
                        producer_failed = True
        elif not producer_failed:
            polls.append({
                "name": "issuer-source-index", "cadence": "weekly", "status": "skipped",
                "returncode": 0, "started_at": utc_now(), "finished_at": utc_now(),
                "changed": False, "diagnostic": "outside Monday UTC weekly window",
            })

        # Source failures leave the investor-facing CI projection untouched.
        # A successful source delta is the only condition that may rebuild it.
        if not producer_failed and (evidence_changed or force):
            if not _run_derived_chain(polls, outputs):
                producer_failed = True
            elif not _run_ci_checks(polls):
                producer_failed = True
    after = source_inventory()
    failures = [
        {"name": item["name"], "error": item.get("diagnostic")}
        for item in polls if item.get("status") == "degraded"
    ]
    prior = load_json(RECEIPT, {})
    receipt, should_write = build_receipt(
        before=before, after=after, polls=polls, outputs_attempted=outputs,
        failures=failures, prior=prior, run_id=str(uuid4()), started_at=None,
    )
    if should_write and receipt:
        validate_receipt(receipt)
        save_json(RECEIPT, receipt)
        print(f"ci_refresh: receipt written; status={receipt['run_status']} review_required={receipt['review_required']}")
    else:
        print("ci_refresh: no meaningful source/failure delta; last receipt preserved")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="run weekly issuer discovery outside Monday")
    parser.add_argument("--recovery", action="store_true", help="force source retry and consume retained handoffs")
    parser.add_argument("--self-check", action="store_true", help="run offline receipt checks; no network/state writes")
    args = parser.parse_args(argv)
    if args.self_check:
        # Self-test is strictly offline and must not rewrite the durable receipt
        # or any production/source state.
        from check_ci_refresh_receipt import self_check
        return self_check()
    return run(force=bool(args.force or args.recovery))


if __name__ == "__main__":
    raise SystemExit(main())
