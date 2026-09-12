# Routine contract after the Desk / CI split

This contract overrides legacy mixed-repository instructions. Read it alongside the named
routine runbook; retain that runbook's sourcing, research, translation and publication gates.

The active runbooks are repository-owned at `docs/routines/README.md`. All scheduled results
must follow `docs/routines/REPORTING.md`. User-profile scheduler files are historical references,
not runtime dependencies.

## Product ownership

- The nine existing Henneth Routines tasks operate on `wasayijaz/henneth-desk` only.
  Desk owns `dashboard/`, its deterministic `state/`, Desk Room and market commentary.
  Marketing owns `site/` in the same repository.
- Company Intelligence lives in `wasayijaz/henneth-ci`, with app root `ci-app/`, separate
  state, preflight and a controlled release workflow. No Desk gate may require CI rebuilds.
  Never recreate, stage or publish CI-owned files from a Desk routine.
- Use each task's existing isolated worktree and persistent task. Do not move to the owner's
  checkout. Fetch and synchronize from the canonical remote before research and again before
  publication. An old branch must incorporate the split before it can publish.
- Keep existing parent model settings: PM and Daily retain the owner's GPT-5.5 High setting.
  Judgment sub-agents use Luna High. A model named in a prompt is not a parent-model change.
- Keep each task in Henneth Routines and preserve its schedule, notification preference and
  activation/training status. This split does not create a CI schedule.

## Refresh and publication

The production deterministic entrypoint is `scripts/run_desk_cloud.py` through
`desk-data.yml`. Local commentary tasks do not run the full data pipeline. PM and Daily retain
their already-approved single cloud catch-up dispatch if the post-close data gate fails.

Run `scripts/post_close_integrity.py` to assess the dated snapshot; do not reimplement its
coverage thresholds in prose. Never insert or infer a completion timestamp to pass this gate.
Missing evidence means unknown/stale. Record the check's covered/traded counts.

Research may overlap. Publish in order: PM, Daily, Desk Room. Before a successor publishes,
check the predecessor's persistent task and final remote SHA. A predecessor is complete when
its publication and required acknowledgement are on origin/main, or when its current-session
report confirms a verified no-op with no pending publish/acknowledgement and a passing data
gate. A genuinely failed, running or unverified predecessor cannot be treated as a no-op.
Do not demand a new commit solely to prove a legitimate no-op.

On synchronization, preserve append-only news, claims and run history from preceding runs.
Regenerate derived files on the synchronized baseline and repeat preflight. Use the repository
publication lock and `scripts/publish.py`; any rebase conflict aborts with no automatic side
selection, and a clean rebase is preflighted again before push. Content tasks stage only their own
pages and required links. The default state staging continues to exclude `state/company_intel/**`
as defense against stale CI writers.

The private-state build/middleware deny-list stays in Desk as defense against stale writers.
The root Ask UI and response checks remain mandatory.

## Verification and reporting

For Desk, require preflight success, the correct remote commit, a READY production deployment
where provider metadata is available, and the public probe. Private `/state/` returns 401 to
anonymous requests; that is not evidence of a broken publish. If exact deployed-commit proof
is unavailable, report that limitation rather than claiming it.

CI deploys only through its own controlled workflow: checks, immutable preview, owner/non-owner
access verification, promotion of that same preview, and production verification. A Desk push
does not release CI. A CI failure cannot block Desk prices or commentary.
