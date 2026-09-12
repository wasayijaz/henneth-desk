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

1. Synchronize the assigned worktree and record the PKT start time. Do not run the full cloud data
   pipeline or a second liveness watchdog here.
2. Read `state/calendar.json` first. A weekend or listed holiday is a deliberate `no-op`: do not
   edit state, dispatch catch-up, run judgment roles, commit, or publish.
3. Require the same-session PM checkpoint's verified publication and acknowledgement, or its
   verified no-op result. Run `python scripts/post_close_integrity.py`; if it fails, use the
   approved single `desk-data.yml` catch-up dispatch, wait, synchronize, and recheck. A failed
   predecessor or still-failed post-close gate blocks this routine; never publish over it.
4. Run exactly three judgment roles, in order. For each, use a `gpt-5.6-luna` high subagent when
   callable; otherwise execute the role inline from the committed role description in this runbook.
   - News Sentinel: scan PSX announcements and Pakistani business press for the last two trading
     days, tag universe tickers, score impact 1–5, and append sourced items to `state/newslog.json`.
   - Macro Analyst: read `state/global.json` and `state/georisk.json`, web-verify domestic facts
     (SBP, CPI, IMF, debt/yields, reserves and fiscal events), and write `state/macro.json`; use
     `null` when a number cannot be verified.
   - Market Analyst: read the current state bundle and write `state/daily_read.json` with a concise
     headline, regime-aware sectors, up to five watchlist names with proven strategy/fundamental/
     catalyst evidence, and risks. Never invent a price or make a named-security call.
5. Run `python scripts/build_dashboard.py`. A failed build/preflight is a hard stop and must not
   reach the public site.
6. Run `python scripts/publish.py "Daily desk refresh <YYYY-MM-DD>"`. A clean unchanged-state
   result is a verified no-op; otherwise capture the exact commit and deployed URL only if proven.
7. Follow [FINALIZATION.md](FINALIZATION.md) using `scripts/finalize_routine.py`, the verified
   research SHA, start time, `--routine daily` and mode `full`. Include regime, geo-risk and headline in
   its outcome. The helper appends and publishes run history, verifies the receipt on origin/main,
   and never rewrites prior entries. Report research and receipt SHAs separately; Room must not
   proceed while receipt publication is outstanding. Daily does not write a checkpoint ack.

## Required result fields

`date`; `market_day`; `roles_run[]`; `news_items_found`; `macro.regime`; `macro.sources[]`;
`geo_risk`; `daily_read.headline`; `daily_read.watchlist_count`; `preflight_or_build`;
`runlog_written`; `publication.status`; `publication.sha`; `publication.url`; `problems[]`;
`next_action`.

## Outcomes

- `success`: all three roles completed with sourced outputs, build/preflight passed, runlog was
  appended, and publication was confirmed or verified unchanged.
- `no-op`: non-market day or holiday was detected before judgment work; record the calendar evidence
  and no publication.
- `blocked`: a required source, role output, or owner gate is unavailable and safe continuation
  would require guessing or changing scope. Keep the last-good state live.
- `fail`: role, build/preflight, publication, or runlog persistence failed; report the exact step and
  whether any partial state was left for review.

Every final report must follow [the shared reporting contract](REPORTING.md).
