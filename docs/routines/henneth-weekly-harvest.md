<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-weekly-harvest

Saturday broker-call harvest plus exactly one rotating sector debate. Read [REPORTING.md](REPORTING.md),
`AGENTS.md`, `docs/ROUTINES_AFTER_SPLIT.md`, `docs/AUTOMATION-PLAN.md`, and `prompts/sector-week.md`.
Operate only in the assigned `wasayijaz/henneth-desk` routine worktree. Brokers are evidence to be
graded, never an endorsement; all output is research, not advice.

## Run

1. Synchronize the assigned worktree and record the PKT start time. On a weekend this routine is
   normally scheduled Saturday for maintenance, so do not apply the market holiday gate unless the
   calendar explicitly marks the run as unavailable.
2. Run `python scripts/fetch_broker_calls.py` to create the deterministic candidate queue.
3. Run one Broker Harvester judgment role. Prefer a `gpt-5.6-luna` high subagent when callable;
   otherwise execute the committed role inline. Give it the queue, broker registry, universe, and
   eight oldest broker-note tickers. It may use roughly 5–7 targeted searches and returns only dated,
   named-house, ticker, claim, and source-URL records. An empty call list is valid.
4. Write the bounded result to `state/room_tmp/broker_calls.json`, then run
   `python scripts/room_broker_apply.py`. Drop any call lacking broker, ticker, date, or URL.
   Refresh filings with `python scripts/fetch_research.py`, then run `python scripts/room_dossier.py`
   and `python scripts/room_score.py`.
5. Rebuild `state/sector_dossiers.json` with `python scripts/sector_dossier.py`. If fewer than three
   sectors are available, record a blocked Part B and do not invent a debate.
6. Read/create `state/sector_debates/_rotation.json`; refill deterministically by member count when
   empty. Take the first sector, except a real impact-4-or-5 item in the last seven days may jump the
   queue if the report records the reason. Run exactly one Sector Debate role, then exactly one Sector
   Chair role, each with Luna high when callable or their committed inline role cards. Both may cite
   only `state/sector_dossiers.json`; the Chair must include substantial dissent and dated,
   market-relative claims with the current KSE-100 benchmark.
7. Run the scoped translation path if needed, file the sector claims, update rotation and rebuild
   `_index.json`. Run `python scripts/room_verify.py`, then `python scripts/build_dashboard.py`.
8. If preflight passes and this automation is activated, publish with
   `python scripts/publish.py "Weekly harvest <YYYY-MM-DD>: <N> broker calls; sector <Sector>"`.
   In training mode, stop with the verified state diff for approval. Capture exact SHA/URL only when
   proven. Preserve append-only state and append the runlog entry only when the run is filed.

## Required result fields

`date`; `broker_candidates`; `broker_calls_found`; `broker_calls_recorded`; `broker_houses[]`;
`unsourced_dropped`; `resolved_calls`; `health_status`; `sector_dossier_count`; `sector`;
`rotation_action`; `queue_jumped`; `debate_completed`; `chair.stance`; `chair.conviction`;
`chair.dissent`; `claims_filed`; `preflight`; `runlog_written`; `publication.status`;
`publication.sha`; `publication.url`; `problems[]`; `next_action`.

## Outcomes

- `success`: broker evidence was recorded or honestly empty, one complete sector debate/chair passed
  QA and preflight, rotation/runlog were updated, and publication was verified or unchanged.
- `no-op`: the candidate queue was empty and the sector evidence was already complete only when no
  state changed; report the evidence and no publication. Do not call an empty or incomplete debate a
  success.
- `blocked`: fewer than three sectors, missing required dossier/benchmark, incomplete Chair dissent,
  or an unresolved QA/preflight gate prevents publication. Keep broker records only if their own
  deterministic validation passed and name the next recovery step.
- `fail`: a fetch, role, state merge, rotation, QA, preflight, publication, or runlog write failed;
  report the exact boundary and preserve the last-good public output.

Final output follows [the shared reporting contract](REPORTING.md).
