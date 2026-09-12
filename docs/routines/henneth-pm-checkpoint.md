<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-pm-checkpoint

Weekday 17:00 PKT checkpoint. This is the second daily firing of the light market-event checkpoint;
the morning checkpoint behavior is defined by the same gate and evidence contract. Work in the
assigned routine worktree for `wasayijaz/henneth-desk`, never in the owner's checkout.

Read [the shared reporting contract](REPORTING.md), `AGENTS.md`, `docs/ROUTINES_AFTER_SPLIT.md`,
and the checkpoint sections of `docs/OPERATIONS.md` before running. Keep this long-only, daily-
timeframe research desk free of advice language. The cloud data pipeline owns deterministic market
refreshes; this routine owns the checkpoint's judgment and acknowledgement.

## Run

1. Synchronize the assigned worktree with the canonical remote. Record the starting PKT timestamp.
2. Run `python scripts/post_close_integrity.py` against the dated snapshot before treating any
   checkpoint as a no-op. If the gate fails, use the approved single `desk-data.yml` catch-up
   dispatch, wait for it, synchronize again, and recheck. Never run the full cloud data pipeline
   locally; if the gate remains failed, block publication and report the exact problems.
3. Read `state/calendar.json`. On a weekend or listed holiday, record a `no-op`, with no commit,
   publish, or judgment work.
4. Read `state/checkpoint_trigger.json`. If it is missing or unreadable, treat the checkpoint as
   required and record the evidence problem. If `checkpoint_required` is false, record the summary
   and pending list, acknowledge this PM firing with `python scripts/build_checkpoint_trigger.py
   --ack checkpoint-pm`, append the required runlog entry, and stop as a verified `no-op`.
5. If required, run the News Sentinel role once. Use a `gpt-5.6-luna` high subagent when callable;
   otherwise execute the role inline from this card. It scans the PSX announcements page plus a
   small set of Pakistani business sources since the last checkpoint, deduplicates against the tail,
   tags only universe tickers (or `MACRO`), scores impact 1–5, and appends only sourced items through
   `scripts/newslog_append.py`. It must preserve the append-only news log and stop at 40 tool calls.
6. If `state/positions.json` has open positions, run the Monitor role once with the same Luna-high
   or inline fallback. It compares only `state/live.json` with each stored plan and writes the
   prescribed status (`HOLD`, `NEAR_TARGET`, `TAKE_PROFIT`, `STOP_OUT`, `THESIS_BROKEN`, or
   `TIME_EXIT`) and timestamps. Missing or stale live data is reported, never guessed.
7. If this run appended an impact-4-or-5 item, run Macro and Market Analyst roles once, using Luna
   high when callable or their inline cards from the committed role descriptions. Macro writes
   sourced domestic facts and a regime to `state/macro.json`; Market Analyst writes a sourced,
   non-advisory `state/daily_read.json` using state data only for prices.
8. Run `python scripts/build_dashboard.py`. A non-zero result is a hard stop: do not publish.
9. When the gate passes, run `python scripts/publish.py "Checkpoint PM <PKT time>"`. Treat an
   unchanged state as a verified publication no-op. Record the exact resulting SHA and live URL
   only when actually known.
10. Always acknowledge the PM gate, even after a safe upstream error:
   `python scripts/build_checkpoint_trigger.py --ack checkpoint-pm`.
11. Append one object to `state/runlog.json` with `started`, `mode` (`light`, `light-escalated`, or
    `light-skipped`), `ended`, and a one-line `outcome` covering health, news, monitor alerts,
    escalation, open positions, and publication. Preserve prior entries.

## Required result fields

`checkpoint: PM`; `date` and start/end PKT timestamps; `holiday_or_weekend`; `gate_required`;
`gate_summary`; `pending[]`; `news_items_found`; `high_impact_items`; `open_positions`;
`monitor_statuses[]`; `escalated`; `preflight_or_build`; `acknowledgement`; `runlog_written`;
`publication.status`; `publication.sha`; `publication.url`; `problems[]`; `next_action`.

## Outcomes

- `success`: required checkpoint completed, build/preflight passed, acknowledgement and runlog were
  written, and publication was confirmed or was an honest unchanged-state no-op.
- `no-op`: holiday/weekend or a readable false gate; record the gate and still write the PM ack and
  runlog. No publication is expected.
- `blocked`: a required external/human dependency prevents safe continuation, such as a missing
  required source or unresolved predecessor; do not claim a push. A missing trigger file is not a
  silent no-op: run the required path and report the evidence problem.
- `fail`: a script, role output, build/preflight, acknowledgement, or runlog write failed. Preserve
  the last-good site and report the exact failed step.

Report with [REPORTING.md](REPORTING.md), including monitor alerts and exact publication identifiers.
