<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-github-cadence-check

Every four days, inspect the deterministic `desk-data.yml` schedule and dispatch safe catch-up runs
only when recent scheduled delivery is under-firing. This routine does not edit workflow files,
publish, or change repository data. Read [REPORTING.md](REPORTING.md), `AGENTS.md`, and
`docs/ROUTINES_AFTER_SPLIT.md`.

## Run

1. Synchronize the assigned worktree and query the last 80 scheduled workflow runs for
   `.github/workflows/desk-data.yml`. Use the workflow's committed cron as the authority: UTC
   weekdays at `:07` and `:37` during the configured window. Bucket scheduled events by UTC date and
   select the last four full UTC calendar weekdays, including zero-run days. Paginate until the
   entire window is covered; 80 results is an initial page, not proof of completeness. Missing
   evidence is `unknown`; a verified day with no runs counts as zero.
2. Record a runs/day table. Treat a day with fewer than five scheduled runs as degraded. If the most
   recent one or two full weekdays are degraded, prepare two or three manual catch-ups through the
   workflow's existing manual trigger. Dispatch them only when this automation is activated; in
   training mode stop for approval. Space them safely and record each returned run identifier.
   Use the connected repository control when a local command is unavailable; never dispatch for an
   old blip that has recovered, and never mark a missing local launcher as a cadence failure.
3. If the cadence is healthy, make no external change. If dispatches were fired, run
   `python scripts/preflight.py` for informational verification only; it does not authorize a
   publication. Record the exact workflow URLs/run IDs where available.

## Required result fields

`checked_at`; `workflow`; `cron_source`; `full_weekdays[]`; `runs_per_day[]`; `threshold`; `degraded_days[]`;
`dispatch_decision`; `dispatch_count`; `dispatch_run_ids[]`; `dispatch_urls[]`; `preflight_status`;
`publication.status: not-applicable`; `problems[]`; `next_action`.

## Outcomes

- `success`: four-day cadence evidence was collected and the correct healthy/degraded decision was
  made; any catch-up dispatches and their identifiers were recorded.
- `no-op`: all four full weekdays met the threshold, so no dispatch was needed.
- `blocked`: workflow run evidence or manual-dispatch authorization is unavailable; do not infer
  health and do not fire a substitute command.
- `fail`: the query, bucketing, dispatch, or informational preflight produced an unexpected error;
  report the exact evidence gap and next check.

Final reporting must follow [REPORTING.md](REPORTING.md); this routine has no publication SHA.
