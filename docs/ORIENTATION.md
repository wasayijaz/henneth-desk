# Henneth orientation

Entry map for the approved Codex takeover, integrated 2026-09-12. Runtime status and release
evidence can change; consult the existing tasks and acceptance ledger before acting.

## Products and execution

Henneth researches the Pakistan Stock Exchange; it never places orders. Desk rules in
[CLAUDE.md](../CLAUDE.md) and engineering rules in [AGENTS.md](../AGENTS.md) bind every harness.
Read CLAUDE.md explicitly; do not assume another harness loaded it.

| Product | Repository and surface |
|---|---|
| Desk | `wasayijaz/henneth-desk`: `dashboard/` and `state/`, served at `desk.henneth.app` |
| Marketing | Same Desk repository: `site/`, served at `henneth.app` |
| Company Intelligence (CI) | Separate `wasayijaz/henneth-ci` repository, served at `ci.henneth.app` |

Cloud deterministic refresh and local Codex routines coexist. The cloud workflow
[desk-data.yml](../.github/workflows/desk-data.yml) runs Python data processing independently
of a desktop session. The nine existing Codex schedules in **Henneth Routines** own the
judgment, content and maintenance work listed in [ROUTINES.md](ROUTINES.md).

Legacy Claude app schedules were deliberately retired. Do not re-enable them or interpret
their retirement as retirement of the active Codex schedules. `.claude/agents/` and `prompts/`
remain reference material used by current runbooks; their names do not mandate a Claude CLI.
Old owner-root handovers describing one repository, cloud-only operation or manual-only
judgment are historical, not the current execution contract.

## First reads and boundaries

Follow the [AGENTS read order](../AGENTS.md#read-in-this-order), then the relevant routine card.
[GIT_MODEL.md](GIT_MODEL.md) explains why the assigned checkout matters. Preserve the dirty
owner checkout at `D:/PSX Trader X Claude`; do work only in the isolated checkout assigned to
the task. Never blanket-stage, sweep unrelated edits, or recreate CI inside Desk.

[OPERATIONS.md](OPERATIONS.md) owns the publication path and source-data gates;
[ROUTINES_AFTER_SPLIT.md](ROUTINES_AFTER_SPLIT.md) owns the product split. Prices and dates
come from their deterministic producers. Capture/completion time is not an exchange session
timestamp. A calendar no-op is not a freshness certificate.

## Approval and acceptance

The takeover approval permits the scoped work recorded in the
[shared routine contract](routines/README.md#shared-execution-rules); it does not change
schedules, models or product scope. Preserve the coordinator's initial shared-pipeline
release hold until explicitly cleared. Do not ask again for already-approved scoped actions.

**Cost is a hard approval boundary:** no new paid service, subscription, upgrade, credit
purchase or additional billable usage without explicit owner approval for that cost. Verify
provider and connector pricing; unknown pricing blocks that action. Do not enable overages
or paid fallbacks. Existing execution/publication approval is not spending approval.

The [acceptance ledger](routines/ACCEPTANCE-2026-09-12.md) records actual evidence and remaining
work; [TECH-DEBT.md](TECH-DEBT.md) records unresolved defects. Nine active schedules do not
mean nine proven routines. Drafts, local tests and weekend/empty-queue no-ops do not prove
research publication, completion receipts, deployment or live verification.
