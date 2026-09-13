"""Single entrypoint for the deterministic desk pipeline (NO agents, no tokens).
Runs every data script in order and rebuilds signals + dashboard. Used by the
update-live-desk skill locally, and mirrors what GitHub Actions runs in the cloud.

Idempotent and safe to re-run. Deep history is skipped for tickers already cached
(fetch_deep_history only pulls missing ones), so re-runs are fast.
Usage: python scripts/run_cloud.py"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
STEPS = [
    "update_universe.py", "fetch_history.py", "fetch_deep_history.py",
    # Must run AFTER both history fetches and BEFORE fetch_fundamentals / predictability /
    # backtest: it writes the research gate those three read (psx_data.research_symbols), and
    # the per-symbol trading friction the backtest charges. Out of order, the gate falls back
    # to core-only and the backtest silently reverts to a flat friction assumption.
    "liquidity.py",
    # DPS company pages for the top research-eligible liquid PSX names. Needs liquidity.py for
    # the pilot list; consumers only read the retained state/company_profiles.json seam.
    "fetch_company_profiles.py",
    # Official PSX announcement metadata for the same 20-company pilot. In scheduled cloud
    # runs this age-gates itself to the first 08:xx PKT cycle; PDFs are a bounded, ignored
    # current-run handoff to the deterministic extractor and are never published or committed.
    "fetch_company_documents.py",
    # Must immediately consume the ignored current-run PDF handoff before any later producer
    # can replace it. Writes bounded, source-linked page evidence for Company Intelligence.
    "document_intelligence.py",
    # Period-aware, evidence-linked financial fact series from the retained document evidence.
    # Pure local transform; no network, no model, no paid provider.
    "build_financial_series.py",
    # Official issuer roots discovered only from DPS profiles; weekly requests-only hash monitor
    # for bounded investor/report/governance/news index pages. No browser or paid provider.
    "fetch_issuer_sources.py",
    # Bounded same-domain issuer PDFs from the source registry. Must be consumed immediately.
    "stage_issuer_documents.py",
    "document_intelligence.py",
    "build_financial_series.py",
    "build_financial_model_inputs.py",
    "build_financial_coverage.py",
    # Review-only audit of retained annual documents that are inside existing transport and
    # provenance limits but have not reached the v2 financial parser. It never downloads,
    # restages or changes an execution allowlist.
    "build_financial_statement_v2_candidate_queue.py",
    "build_forecast_readiness.py",
    "build_financial_reprocess_blockers.py",
    # Server-only owner-approved formal engine assumptions from the private Henneth CI
    # Supabase table. Inert without CI Supabase secrets; generated/historical inputs below
    # preserve these imported rows but never approve them themselves.
    "import_owner_financial_assumptions.py",
    # Deterministic market operands for the formal engines. Emits only objective current_price
    # and shares_out records from retained dated state; forward assumptions remain owner-approved.
    "build_financial_engine_assumptions.py",
    # Empty-by-default, owner-approved conversion of receipt-bound official
    # share-capital candidates; it never imports an unapproved candidate.
    "build_official_share_capital_approvals.py",
    "build_financial_evidence_reconciliation.py",
    # Historical reported deltas only; this does not enter the formal-engine path.
    "build_earnings_bridges.py",
    # Audit-only retained cement operating observations. This is evidence for review only:
    # it never activates financial_model_inputs, forecasts, valuations, or market expectations.
    "build_cement_operating_series.py",
    "cement_historical_reconciliation.py",
    # Strict retained-evidence qualification is the authoritative formal-engine
    # activation gate. It must precede engine output so a stale prior-cycle
    # qualification result cannot activate forecasts, valuations, or expectations.
    "build_financial_truth_qualification.py",
    # Source-gated algebra only: stays blocked until current financial truth and
    # approved, dated assumptions exist.
    "build_formal_financial_engines.py",
    # Compact issuer-source health index and relationship graph for the private CI surface.
    "build_source_qa.py",
    # Compact CI knowledge graph over official documents, events, facts and issuer sources.
    # Pure local transform; the browser reads the generated CI slice, not this raw state file.
    "build_company_graph.py",
    # Deterministic "what changed" digest over official filings, issuer-site changes,
    # source-linked financial movements and event classifications. Free local transform.
    "build_change_intelligence.py",
    # Wave 1 Company Intelligence: evidence-backed events, declarative sector drivers,
    # and null-safe Bear/Base/Bull scenarios before the bounded app slice.
    "build_operating_events.py", "build_driver_graphs.py", "impact_engine.py", "build_signal_clusters.py",
    "build_thesis_monitoring.py", "build_intelligence_confidence.py", "build_intelligence_cases.py", "build_mlcf_pioc_readiness_manifest.py", "build_guidance_contradictions.py",
    "build_management_delivery.py",
    "build_evidence_watchlist.py",
    "build_ci_monitoring.py",
    # Needs the history fetches for closes and liquidity.py for the research gate it iterates
    # (psx_data.research_symbols). Earlier than this it would correlate core-only; it has no
    # other dependency and nothing downstream blocks on it. Pure local math, no network.
    "correlation.py",
    "fetch_dividends.py",
    "fetch_dividends_deep.py",  # 18y payout history (Yahoo events) — DPS only gives ~18 months
    "fetch_fundamentals.py",
    # Insider/off-market activity — same family as fetch_fundamentals.py (no cadence gate here
    # either; the script itself is cheap/idempotent and degrades to the prior file on failure).
    "fetch_insider_offmarket.py",
    "build_calendar.py", "quant.py", "predictability.py", "backtest.py",
    "snapshot.py",
    # score_fundamentals.py's live_pe() reads state/live.json for TODAY's price. It must run
    # AFTER snapshot.py writes that file this cycle, not back-to-back with fetch_fundamentals.py
    # (which pairing left live_pe() reading the PRIOR cycle's live.json all cycle — the root
    # cause of the P/E-off-a-stale-print mismatches room-verifier flagged on ENGROH/MEBL).
    "score_fundamentals.py",
    "fetch_indices.py",  # append-only KSE100/KMI30 levels — the index history nobody else has
    "fetch_sectors.py",  # PSX code->name map (needs live.json); feeds Rule 4's sector limit + CI sector labels
    "build_peer_registry.py",  # exact CI pilot grouped only by the retained official PSX sector label
    "fetch_intraday.py", "fetch_global.py", "fetch_georisk.py",
    "astro_engine.py",   # sidereal ephemeris: positions + dated events. Pure math, no network.
    "astro_history.py",  # extends the cached daily sky (bounded per run; ~70ms/day once caught up)
    "astro_charts.py",   # verified birth dates only (Exchange workbooks first, then careful Yahoo)
    "astro_natal.py",    # natal + Vimshottari + transits-to-natal, bracketed for the unknown time
    # Joins today's sky to the backtest's own condition vocabulary, and publishes the Pakistan /
    # KSE-100 slow-graha placements. Must run AFTER astro_engine (current sky) and is checked
    # against astro_backtest.json — a live condition the backtest never tested prints a warning
    # rather than silently becoming an unmeasured claim on the astro page.
    "astro_context.py",
    "astro_claims.py",   # files the astro readings as dated, market-relative, scoreable claims
    "fetch_macro_history.py",  # oil/gold/PKR/S&P/EM/10y/dollar daily history (full refetch each run)
    "sector_macro.py",   # which macro drivers actually move each sector — measured, weekly cadence
    "sector_dossier.py", # deterministic evidence pack the weekly sector debate argues from
    "tv_crosscheck.py", "data_health.py", "compute_fairvalue.py", "build_signals.py",
    # Decides whether the token-spending local AI checkpoint has anything material to do.
    # Runs after its two inputs are current this cycle: build_ci_monitoring.py (the CI alerts)
    # and data_health.py (state/health.json). Reads state only, writes
    # state/checkpoint_trigger.json, never networks.
    "build_checkpoint_trigger.py",
    # Desk Room deterministic layer (free): compile dossiers, rank the coverage queue,
    # resolve/score any due persona+broker calls. Agents read these; they never fetch.
    "fetch_research.py", "build_explainer.py",  # explainability layer (plain-English "at a glance")
    "room_dossier.py", "room_queue.py", "room_gate.py", "room_score.py",
    "room_verify.py",   # deterministic QA: flags glitch-derived / inconsistent numbers before publish
    "design_lint.py",   # deterministic UI QA: flags rounded corners / padding-contract / raw-hex drift
    # The marketing site's public astro slice. Must run AFTER astro_engine (it reads the current
    # sky). Writes only into site/, never state/, so it cannot affect the desk's own data layer.
    "build_astro_lite.py",
    # Allow-listed public ticker extract for henneth.app. Must run AFTER quant / fairvalue /
    # dividends_deep / liquidity / sectors / changelog. Writes only into site/src/data/public/,
    # never state/. publish.py already commits that folder as generated data. Not running this
    # left public /psx/ pages on whatever extract last happened to be committed.
    "build_public_slice.py",
    # Private Company Intelligence app slice. Reads only retained state files and writes the
    # one JSON file the static CI app consumes.
    "build_event_studies.py",
    "build_conditional_benchmarks.py",
    "build_historical_state_map.py",
    # Causal evidence must resolve against event studies rebuilt in this same cycle.
    "build_causal_foundations.py",
    "build_company_scenario_lab.py",
    "build_company_brains.py",
    # Deterministic low-token event metadata: known calendar items plus conservative
    # reporting windows derived only from retained past cadence.
    "build_event_review_windows.py",
    # Policy route for CI work: deterministic roster-wide scans feed retained triggers;
    # targeted owner/AI work may only be requested from material changes, post-baseline
    # source changes or event review windows.
    "build_ci_work_routing_policy.py",
    "build_ownership_source_manifest.py",  # review metadata only; never activates ownership facts
    "build_ci_completion_matrix.py",
    "build_ci_slice.py",
    # Finalize the complete private CI release as one reproducible UTC-cutoff
    # artifact set. This runs only after every CI producer and the slice.
    "build_ci_artifact_integrity.py",
    # Server-only, append-only CI archive. It is intentionally a no-op until cloud secrets are
    # installed; archive failure must not interrupt the deterministic public research release.
    "supabase_ci_store.py",
    "check_ci_completion_matrix.py",
    "check_causal_foundations.py",
    "check_conditional_benchmarks.py",
    "check_financial_coverage.py",
    "check_financial_truth_qualification.py",
    "check_financial_statement_v2_candidate_queue.py",
    "check_ci_reprocess_manifest.py",
    "check_intelligence_cases.py",
    "check_mlcf_pioc_readiness_manifest.py",
    "check_financial_reprocess_blockers.py",
    "check_ownership_source_manifest.py",
    "check_forecast_contract.py",
    "check_owner_financial_assumptions.py",
    "check_financial_engine_assumptions.py",
    "check_formal_financial_engines.py",
    "check_financial_evidence_reconciliation.py",
    "check_earnings_bridges.py",
    "check_cement_operating_series.py",
    "check_cement_historical_reconciliation.py",
    "check_intelligence_confidence.py",
    "check_thesis_monitoring.py",
    "check_management_delivery.py",
    "check_guidance_contradictions.py",
    "check_evidence_watchlist.py",
    "check_ci_monitoring.py",
    "check_peer_registry.py",
    "check_company_scenario_lab.py",
    "check_company_brains.py",
    "check_event_review_windows.py",
    "check_historical_state_map.py",
    "check_ci_work_routing_policy.py",
    "check_ci_artifact_integrity.py",
    "check_financial_model_inputs.py",
    "check_event_studies.py",
    "check_operating_intelligence.py",
    # Diffs universe.json against the last-seen ticker set and auto-appends a templated
    # CHANGELOG.md entry when the universe grew (symbols only — nothing to leak). Must run
    # AFTER update_universe.py and BEFORE build_changelog.py so the new entry gets picked up
    # the same cycle it's written.
    "changelog_tickers.py",
    # Public release notes for the terminal's version badge. Extracts ONLY the `public` blocks
    # from CHANGELOG.md and refuses to build if one contains an internal term — so a bad note
    # fails the step rather than shipping. Cheap, no network.
    "build_changelog.py",
    "build_dashboard.py", "preflight.py",
]
# steps allowed to exit non-zero without aborting the run
ADVISORY = {"tv_crosscheck.py", "supabase_ci_store.py"}


def main():
    failed = []
    for s in STEPS:
        print(f"\n=== {s} ===")
        r = subprocess.run([sys.executable, str(SCRIPTS / s)])
        if r.returncode != 0 and s not in ADVISORY:
            failed.append(s)
            print(f"  ! {s} exited {r.returncode}")
    print("\n" + ("ALL OK" if not failed else f"FAILED: {', '.join(failed)}"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
