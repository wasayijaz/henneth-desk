#!/usr/bin/env python3
"""Offline boundary checks for the independent CI refresh runner.

This checker deliberately does not invoke the runner or touch state. It keeps
the autonomy contract small and reviewable: official-source polling, bounded
CI evidence consumers, no Desk/LLM path, and an explicit manual recovery flag.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_ci_refresh import CI_CHECKS, CI_PIPELINE, _diagnostic_has_change, _diagnostic_has_failure, _poll_due


EXPECTED_PIPELINE = (
    "document_intelligence.py",
    "build_financial_series.py",
    "build_financial_model_inputs.py",
    "build_financial_coverage.py",
    "build_financial_statement_v2_candidate_queue.py",
    "build_forecast_readiness.py",
    "build_financial_reprocess_blockers.py",
    "import_owner_financial_assumptions.py",
    "build_financial_engine_assumptions.py",
    "build_official_share_capital_approvals.py",
    "build_financial_evidence_reconciliation.py",
    "build_earnings_bridges.py",
    "build_cement_operating_series.py",
    "cement_historical_reconciliation.py",
    "build_financial_truth_qualification.py",
    "build_formal_financial_engines.py",
    "build_source_qa.py",
    "build_company_graph.py",
    "build_change_intelligence.py",
    "build_operating_events.py",
    "build_driver_graphs.py",
    "impact_engine.py",
    "build_signal_clusters.py",
    "build_thesis_monitoring.py",
    "build_intelligence_confidence.py",
    "build_intelligence_cases.py",
    "build_mlcf_pioc_readiness_manifest.py",
    "build_guidance_contradictions.py",
    "build_management_delivery.py",
    "build_evidence_watchlist.py",
    "build_ci_monitoring.py",
    "build_peer_registry.py",
    "build_event_studies.py",
    "build_conditional_benchmarks.py",
    "build_historical_state_map.py",
    "build_causal_foundations.py",
    "build_company_scenario_lab.py",
    "build_company_brains.py",
    "build_event_review_windows.py",
    "build_ci_work_routing_policy.py",
    "build_ownership_source_manifest.py",
    "build_ci_completion_matrix.py",
    "build_ci_slice.py",
    "build_ci_artifact_integrity.py",
    "supabase_ci_store.py",
)

EXPECTED_CHECKS = (
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

FORBIDDEN_SCRIPT_NAMES = (
    "run_cloud.py",
    "fetch_history.py",
    "quant.py",
    "backtest.py",
    "claude",
    "room_",
)


def self_check() -> int:
    if tuple(script for _, script, _ in CI_PIPELINE) != EXPECTED_PIPELINE:
        print("ci_refresh_runner: FAIL (CI pipeline order changed)")
        return 1
    if tuple(CI_CHECKS) != EXPECTED_CHECKS:
        print("ci_refresh_runner: FAIL (CI check order changed)")
        return 1
    if any(any(marker in script.lower() for marker in FORBIDDEN_SCRIPT_NAMES)
           for _, script, _ in CI_PIPELINE):
        print("ci_refresh_runner: FAIL (Desk or model path entered CI pipeline)")
        return 1
    if any(any(marker in script.lower() for marker in FORBIDDEN_SCRIPT_NAMES)
           for script in CI_CHECKS):
        print("ci_refresh_runner: FAIL (Desk or model path entered CI checks)")
        return 1
    if not _diagnostic_has_change("company_documents: 1 metadata changes, 1 PDFs staged"):
        print("ci_refresh_runner: FAIL (producer change diagnostic not detected)")
        return 1
    if not _diagnostic_has_change("issuer_sources: 2 new/changed page hashes"):
        print("ci_refresh_runner: FAIL (issuer change diagnostic not detected)")
        return 1
    if _diagnostic_has_change("company_documents: 0 metadata changes, 0 PDFs staged"):
        print("ci_refresh_runner: FAIL (zero change diagnostic marked changed)")
        return 1
    if not _diagnostic_has_failure("issuer_sources: 1 source errors (last-good retained)"):
        print("ci_refresh_runner: FAIL (degraded producer diagnostic not detected)")
        return 1
    monday = datetime(2026, 9, 21, 3, 7, tzinfo=timezone.utc)
    tuesday = datetime(2026, 9, 22, 3, 7, tzinfo=timezone.utc)
    if not _poll_due(False, monday) or _poll_due(False, tuesday) or not _poll_due(True, tuesday):
        print("ci_refresh_runner: FAIL (weekly/manual cadence boundary)")
        return 1
    source = (ROOT / "scripts" / "run_ci_refresh.py").read_text(encoding="utf-8")
    if '"fetch_company_documents.py"), "--metadata-only"' in source:
        print("ci_refresh_runner: FAIL (metadata-only PSX poll cannot progress evidence)")
        return 1
    if '"on-change"' in source:
        print("ci_refresh_runner: FAIL (receipt-incompatible on-change cadence)")
        return 1
    if "if not producer_failed and (evidence_changed or force):" not in source:
        print("ci_refresh_runner: FAIL (delta/recovery gate missing)")
        return 1
    if "producer_failed = True" not in source:
        print("ci_refresh_runner: FAIL (derived failure is not propagated)")
        return 1
    if 'parser.add_argument("--recovery"' not in source:
        print("ci_refresh_runner: FAIL (manual recovery flag missing)")
        return 1
    print("ci_refresh_runner: PASS (bounded, delta-aware, offline)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    return self_check()


if __name__ == "__main__":
    raise SystemExit(main())
