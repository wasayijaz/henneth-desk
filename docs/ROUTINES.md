# Henneth automation map

Current takeover map, 2026-09-12. The approved configuration has nine active Codex schedules
in **Henneth Routines**, alongside the cloud data workflow. The
[acceptance ledger](routines/ACCEPTANCE-2026-09-12.md) records the coordinator's inventory and
run evidence. Active scheduling is not proof that every applicable research/publication path
has passed acceptance.

## Cloud data

[desk-data.yml](../.github/workflows/desk-data.yml) declares weekday schedule
`7,37 3-11 * * 1-5` (UTC) and manual dispatch. It installs Python 3.12, runs
[run_desk_cloud.py](../scripts/run_desk_cloud.py), then
[post_close_recovery.py](../scripts/post_close_recovery.py), gated
[publish.py](../scripts/publish.py), and a non-fatal watchdog. It refreshes deterministic
Desk data; it does not run the local judgment roles. Workflow configuration is not evidence
that every scheduled execution actually ran; use the cadence routine's run-history checks.

This checkout has no push/PR-triggered validation workflow. Company Intelligence's workflows
belong to its separate repository; do not restore old CI contract/release YAML into Desk.

## Existing Codex tasks

The linked cards own the exact scripts, state reads/writes, gates and result fields. The
existing scheduler owns firing times, target tasks and model settings; preserve them rather
than recreating schedules from historical handover times.

| Routine card | Responsibility and publication boundary |
|---|---|
| [henneth-pm-checkpoint](routines/henneth-pm-checkpoint.md) | Calendar/trigger, checkpoint judgment; verified research then PM acknowledgment/receipt. |
| [henneth-daily-refresh](routines/henneth-daily-refresh.md) | Same-session PM dependency, news/macro/daily read; research and runlog receipt, no PM ack. |
| [henneth-desk-room-loop](routines/henneth-desk-room-loop.md) | Daily dependency, selected debates and QA; research and runlog receipt. |
| [henneth-weekly-harvest](routines/henneth-weekly-harvest.md) | Broker evidence and one rotating sector debate; verified research and receipt. |
| [henneth-weekly-code-review](routines/henneth-weekly-code-review.md) | Code/config review, scoped permitted fixes and regression checks. |
| [henneth-product-scout](routines/henneth-product-scout.md) | Evidence-backed improvement proposals/backlog; no unapproved feature implementation. |
| [henneth-github-cadence-check](routines/henneth-github-cadence-check.md) | Workflow history and bounded authorized catch-up dispatch; no state edits/publication. |
| [henneth-blog-publish](routines/henneth-blog-publish.md) | One sourced post, separate fact-checker, build/render gates, scoped release after clearance. |
| [henneth-landing-page-publish](routines/henneth-landing-page-publish.md) | One distinct queued page, build/render gates and scoped release after clearance. |

All tasks follow [the shared contract](routines/README.md),
[REPORTING.md](routines/REPORTING.md), [OPERATIONS.md](OPERATIONS.md), and
[ROUTINES_AFTER_SPLIT.md](ROUTINES_AFTER_SPLIT.md). Desk/marketing use `henneth-desk`;
none of these nine schedules is a Company Intelligence release task.

## Holds, cost and completion

Retain the coordinator's initial shared-pipeline release hold. The owner-approved normal
scoped publications/dispatches may proceed after clearance without repeating the same
approval; failed technical gates still block. **New/additional costs require explicit owner
approval**, including provider and connector charges. Unknown pricing blocks that action;
do not enable subscriptions, credits, overages or paid fallbacks under routine authorization.

Research can overlap; publish in PM → Daily → Room order with the predecessor evidence required
by each card. [FINALIZATION.md](routines/FINALIZATION.md) owns completion receipts. Only PM
writes checkpoint acknowledgment. Calendar skips follow the card's no-write path, and a
Saturday harvest follows its own maintenance rules. Source-session freshness is checked by
[post_close_integrity.py](../scripts/post_close_integrity.py), including off-market publication.

Use the [acceptance ledger](routines/ACCEPTANCE-2026-09-12.md) to identify remaining applicable
stages. Keep research commit, receipt commit, deployed revision and live checks distinct.
Do not count local fixtures, drafts, calendar skips or exhausted queues as proof of a future
production run. Do not mark all routines proven from a green preflight.

## Retired procedures

Legacy Claude app schedules and their user-profile task files are historical references,
not active runtime dependencies. Do not re-enable them, copy their old schedules into Codex,
or interpret their retirement as a cloud-only operating model. Current cards replace their
mixed-repository and provider-specific execution instructions.
