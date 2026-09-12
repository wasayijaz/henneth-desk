# Routine reporting contract

Every routine report is an audit note, not a heartbeat. Use this exact shape so a reader can scan
the result without reconstructing the run from tool output.

## Required report shape

```markdown
# <routine ID> — <YYYY-MM-DD>

## Status / Result
- Status: `success` | `no-op` | `blocked` | `fail`
- Result: <one sentence stating what happened>
- Run time: <start and end in PKT, or `unknown`>

## Data or Findings
- Inputs: <state files, source documents, commit range, or schedule evidence>
- Findings: <facts, counts, decisions, and confidence limits>

## Actions / Publication
- Actions: <deterministic work and judgment work completed>
- Publication: `published` | `not-published` | `no-op`; SHA: `<exact SHA or n/a>`; URL: `<exact URL or n/a>`

## Verification
- Checks: <commands, build/render checks, QA gates, or external probes and their results>

## Problems / Next action
- Problems: <none, or each concrete blocker/failure>
- Next action: <owner or next routine action; never imply completion when blocked>
```

The headings are mandatory: `Status / Result`, `Data or Findings`, `Actions / Publication`,
`Verification`, and `Problems / Next action`. Keep bullets short and use a table when several
counts or dates are easier to compare. Do not make an XML heartbeat block the only report, and do
not replace the report with one long paragraph.

Keep the whole report under 220 words unless a required findings table genuinely needs more room.
Put each separate result, problem, or next action in its own bullet. Do not mention model names,
agent tools, retired schedulers, provider-specific commands, or internal orchestration in the
user-facing report; report the work and evidence instead.

When a run publishes or inspects an external artifact, record the exact commit SHA, deployment
SHA, URL, or source URL. If it is unavailable, write `unknown` or `n/a`; never shorten, invent, or
infer it. A no-op still records the gate and why no work was needed. A blocked or failed run records
the last safe checkpoint and the precise next action.

## Status meanings

- `success`: all required work and verification completed; publication may be `published` or a
  verified no-op.
- `no-op`: a deliberate gate, holiday, empty queue, or unchanged state meant no work was required;
  the gate itself was readable and recorded.
- `blocked`: work could not safely proceed because a human gate, predecessor, required evidence, or
  provider action is outstanding; do not claim publication.
- `fail`: an unexpected error or failed verification stopped the run; preserve the last-good output.
