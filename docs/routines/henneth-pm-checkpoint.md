<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-pm-checkpoint

Weekday post-close checkpoint; the scheduler owns its exact firing time. Work in the
assigned routine worktree for `wasayijaz/henneth-desk`, never in the owner's checkout.

Read [the shared reporting contract](REPORTING.md), `AGENTS.md`, `docs/ROUTINES_AFTER_SPLIT.md`,
and the checkpoint sections of `docs/OPERATIONS.md` before running. Keep this long-only, daily-
timeframe research desk free of advice language. The cloud data pipeline owns deterministic market
refreshes; this routine owns the checkpoint's judgment and acknowledgement.

## Run

1. Before reading any runbook or state file, synchronize the assigned worktree with the canonical
   remote. Run a fresh `git fetch --prune origin main`, fast-forward the clean checkout to
   `origin/main`, and prove `git rev-parse HEAD` equals `git rev-parse origin/main`. If Git metadata
   needs scoped filesystem escalation, retry that same safe operation with escalation. A dirty,
   divergent, or still-stale checkout is `blocked`; never assess today's data from it. Record the
   starting PKT timestamp only after equality is proven. Resolve `load_workspace_dependencies`
   once and use the exact bundled Python executable for every Python command; never call bare
   `python` or `py`.
2. Read `state/calendar.json` first. On a weekend or listed holiday, report a `no-op` with no
   judgement work, acknowledgement, runlog change, catch-up dispatch, or publication.
3. Run `python scripts/post_close_integrity.py` against the dated snapshot before treating any
   checkpoint as a no-op. If the gate fails, use exactly one authenticated GitHub Actions dispatch
   for `desk-data.yml` on `wasayijaz/henneth-desk` `main`. Check `gh auth status` first and use the
   authenticated `gh workflow run` command when available; do not open a browser before testing the
   CLI. GitHub API or Actions UI are fallbacks only when the CLI is unavailable. Wait for that exact run, synchronize again,
   and recheck. This approved zero-cost recovery is part of the routine and must not be abandoned
   merely because one transport is unavailable. Never run the full cloud data pipeline locally;
   if the dispatched run or the recheck fails, block publication and report the exact problems.
4. Read `state/checkpoint_trigger.json`. If it is missing or unreadable, treat the checkpoint as
   required and record the evidence problem. Its embedded `acked_at` is a build-time snapshot;
   `state/checkpoint_ack.json` is the acknowledgement authority. If `checkpoint_required` is false,
   record the summary and pending list, skip roles/build, verify preflight and the unchanged baseline
   on origin/main, then complete step 10. This is a research no-op with a published receipt.
5. If required, run the News Sentinel role once. Use a `gpt-5.6-luna` high subagent when callable;
   otherwise execute the role inline from this card. It scans the PSX announcements page plus a
   small set of Pakistani business sources since the last checkpoint, deduplicates against the tail,
   tags only universe tickers (or `MACRO`), scores impact 1–5, and appends only sourced items through
   `scripts/newslog_append.py`. It must preserve the append-only news log and stop after 10 external
   source retrievals. Reuse a source response already obtained in this run; do not reopen it through
   another transport. PM is the weekday chain's only news scan.
6. If `state/positions.json` has open positions, run the Monitor role once with the same Luna-high
   or inline fallback. It compares only `state/live.json` with each stored plan and writes the
   prescribed status (`HOLD`, `NEAR_TARGET`, `TAKE_PROFIT`, `STOP_OUT`, `THESIS_BROKEN`, or
   `TIME_EXIT`) and timestamps. Missing or stale live data is reported, never guessed.
7. Do not run Macro or Market Analyst in PM. Record the count and identifiers of new impact-4-or-5
   items for Daily, which owns those two roles once after the verified PM receipt. This prevents the
   same high-reasoning research from running twice within one publication chain.
8. Run `python scripts/build_dashboard.py`. A non-zero result is a hard stop: do not publish.
9. When the gate passes, run `python scripts/publish.py "Checkpoint PM <PKT time>"`. Treat an
   unchanged state as a verified publication no-op. Record the exact resulting SHA and live URL
   only when actually known.
10. Follow [FINALIZATION.md](FINALIZATION.md): use `scripts/finalize_routine.py` with the verified
    research SHA, start time, `--routine pm` and mode (`light`, `light-escalated`, or `light-skipped`).
    It acknowledges only verified work, appends run history and publishes/verifies the receipt.
    Never acknowledge a failed or incomplete checkpoint. A local-only acknowledgement is not completion.
11. Report the research SHA and final receipt SHA separately. Daily may proceed only after the
    receipt is remotely verified; receipt publication failure leaves this checkpoint blocked.

## Required result fields

`checkpoint: PM`; `date` and start/end PKT timestamps; `holiday_or_weekend`; `gate_required`;
`gate_summary`; `pending[]`; `news_items_found`; `high_impact_items`; `open_positions`;
`monitor_statuses[]`; `high_impact_handoff[]`; `escalated`; `preflight_or_build`;
`acknowledgement`; `runlog_written`; `efficiency.external_source_retrievals`;
`publication.status`; `publication.sha`; `publication.url`; `problems[]`; `next_action`.

## Outcomes

- `success`: required checkpoint completed, build/preflight passed, acknowledgement and runlog were
  written, and publication was confirmed or was an honest unchanged-state no-op.
- `no-op`: holiday/weekend with no writes. A trading-day false trigger skips research but requires
  the remotely verified acknowledgement/runlog receipt; state its publication separately.
- `blocked`: a required external/human dependency prevents safe continuation, such as a missing
  required source or unresolved predecessor; do not claim a push. A missing trigger file is not a
  silent no-op: run the required path and report the evidence problem.
- `fail`: a script, role output, build/preflight, acknowledgement, or runlog write failed. Preserve
  the last-good site and report the exact failed step.

Report with [REPORTING.md](REPORTING.md), including monitor alerts and exact publication identifiers.
