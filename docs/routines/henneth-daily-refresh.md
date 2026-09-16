<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-daily-refresh

Weekday end-of-day commentary refresh after the close defined by `post_close_integrity.py`
(including Friday). Operate in the assigned routine
worktree for `wasayijaz/henneth-desk`; the cloud workflow owns deterministic data and its watchdog.
Read [REPORTING.md](REPORTING.md), `AGENTS.md`, `docs/ROUTINES_AFTER_SPLIT.md`, and the current
operations refresh guidance first.

## Run

1. Synchronize the assigned worktree and record the PKT start time. Resolve
   `load_workspace_dependencies` once and use the exact bundled Python executable for every Python
   command; never call bare `python` or `py`. Do not run the full cloud data pipeline or a second
   liveness watchdog here.
2. Read `state/calendar.json` first. A weekend or listed holiday is a deliberate `no-op`: do not
   edit state, dispatch catch-up, run judgment roles, commit, or publish.
3. Wait for and verify the same-session PM checkpoint receipt with one long-running command:
   `python scripts/wait_for_routine_receipt.py --routine pm --date <YYYY-MM-DD> --timeout-seconds 5400 --poll-seconds 180`.
   This command fetches `origin/main` and proves the receipt, matching runlog, research SHA, and PM
   acknowledgement. Let that command wait; do not add browser refreshes, narrated status checks, or
   a second polling loop around it. Do not dispatch data while waiting for PM. After PM verifies, synchronize and
   run `python scripts/post_close_integrity.py`. Only if that integrity gate fails may this routine
   use one authenticated `desk-data.yml` catch-up dispatch, wait for that exact run, synchronize,
   and recheck. A timed-out predecessor or still-failed post-close gate blocks this routine; never
   publish over it.
4. The verified PM receipt proves that the day's News Sentinel scan completed. Read the new PM
   news from `state/newslog.json`; do not run News Sentinel again. Run exactly two judgment roles,
   in order. For each, use a `gpt-5.6-luna` high subagent when
   callable; otherwise execute the role inline from the committed role description in this runbook.
   Tell each spawned role that the parent routine is already authorized and give it an exact file
   boundary; the role performs that scoped state update without asking the owner for another plan
   approval. The parent may answer a redundant role checkpoint and continue.
   - Macro Analyst: read `state/global.json` and `state/georisk.json`, web-verify domestic facts
     (SBP, CPI, IMF, debt/yields, reserves and fiscal events), and write `state/macro.json`; use
     `null` when a number cannot be verified. Use no more than eight external source retrievals and
     reuse official source responses obtained in this run.
   - Market Analyst: read the current state bundle and write `state/daily_read.json` with a concise
     headline, regime-aware sectors, up to five watchlist names with proven strategy/fundamental/
     catalyst evidence, and risks. Never invent a price or make a named-security call.
   The two roles together may use no more than 16 external source retrievals. Crossing the limit is
   `blocked`, not permission to continue. Deterministic file reads, builds and Git verification do
   not count toward this research-source limit.
5. Run `python scripts/build_dashboard.py`. A failed build/preflight is a hard stop and must not
   reach the public site.
6. Run `python scripts/publish.py "Daily desk refresh <YYYY-MM-DD>"`. A clean unchanged-state
   result is a verified no-op; otherwise capture the exact commit and deployed URL only if proven.
7. Follow [FINALIZATION.md](FINALIZATION.md) using `scripts/finalize_routine.py`, the verified
   research SHA, start time, `--routine daily` and mode `full`. Include regime, geo-risk and headline in
   its outcome. The helper appends and publishes run history, verifies the receipt on origin/main,
   and never rewrites prior entries. Report research and receipt SHAs separately; Room must not
   proceed while receipt publication is outstanding. Daily does not write a checkpoint ack.
8. A successful catch-up is not completion. After every catch-up, resume at the failed gate and
   continue through roles, build, research publication, and finalization in the same run. Do not
   answer a data-freshness question as though it were the routine's completion report.

## Required result fields

`date`; `market_day`; `roles_run[]`; `pm_news_consumed`; `news_items_found`; `macro.regime`; `macro.sources[]`;
`geo_risk`; `daily_read.headline`; `daily_read.watchlist_count`; `preflight_or_build`;
`runlog_written`; `publication.status`; `publication.sha`; `publication.url`; `problems[]`;
`next_action`; `efficiency.external_source_retrievals`.

## Outcomes

- `success`: both roles completed with sourced outputs after a verified PM news scan, build/preflight passed, runlog was
  appended, and publication was confirmed or verified unchanged.
- `no-op`: non-market day or holiday was detected before judgment work; record the calendar evidence
  and no publication.
- `blocked`: a required source, role output, or owner gate is unavailable and safe continuation
  would require guessing or changing scope. Keep the last-good state live.
- `fail`: role, build/preflight, publication, or runlog persistence failed; report the exact step and
  whether any partial state was left for review.

Every final report must follow [the shared reporting contract](REPORTING.md).
