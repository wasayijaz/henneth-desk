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

## Evidence discipline

- A readiness reply or copied result from another task is not a routine execution.
- Distinguish validation passed, publication pending, and live deployment verified. A training
  run awaiting publication is `blocked` with validation results, not end-to-end `success`.
- For two-stage finalization report research SHA and receipt SHA separately. A failed receipt
  leaves the routine incomplete even if the earlier research push succeeded.
- Use actual Markdown with blank lines before lists. Never collapse headings and bullets into
  one paragraph, or claim unavailable visual/build/deployment checks passed.

## Price evidence when assessed

- Price check: report the exact session date, gate result, same-session EOD count / traded-symbol
  denominator, and cached-history coverage / universe total. Label these distinct populations;
  also report history fetch successes, failures and deadline skips from the assessed run.
- Source as-of: give the provider's session or last-trade date separately from the timezone-aware
  capture/completion time. A recent capture does not make an old source price current.
- Older last trades: name affected tickers and dates; distinguish a successful fetch returning an
  older last trade from a failed fetch retaining cached prices. If the cause is unverified, say
  `unknown`; do not infer inactivity from missing history or research eligibility from coverage.
- Saturday/holiday holds and `not_required` checks establish only the calendar no-op. They do not
  certify live-price freshness or the preceding session's completeness. If prices were not
  assessed, report `not checked` rather than carrying forward another run's passing counts.
- Keep these as short bullets under Data or Findings and Verification. Report only stages actually
  completed: validation, publication and deployment each need their own evidence; state the next
  unverified stage. Training evidence does not change an automation's activation status.
