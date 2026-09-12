<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-weekly-code-review

Saturday code-quality checkpoint. Review only the eight-day overlap window of code changes; do not
run the data pipeline or mutate `state/`. Read [REPORTING.md](REPORTING.md), `AGENTS.md`,
`docs/ROUTINES_AFTER_SPLIT.md`, and `docs/TECH-DEBT.md`.

## Run

1. Synchronize the assigned checkout and record exact `base` and `head` SHAs. Select commits
   since eight days ago and review hand-authored code, templates, and build/release configuration
   (including Python, JS/TS, Astro/MDX, HTML/CSS and `.github/`). Exclude generated `state/`,
   generated public data and dependency lockfile contents. Never silently omit a deployed code
   language from the review merely because it was absent from a legacy pathspec.
2. Run one medium-scope Reviewer judgment pass using a `gpt-5.6-luna` high subagent when callable;
   otherwise perform the role inline from this card. Inspect correctness, security, auth/RLS,
   injection/XSS, unsafe process use, dead code, duplicated logic, concrete technical debt, and
   material inefficiency. Do not flag intentional health-degradation fallbacks, idempotency guards,
   or frozen strategy versions as debt.
3. Classify every finding as confirmed/plausible low-risk mechanical fix or owner judgment call.
   Apply only the former, in narrow patches. Do not silently change user-visible behavior or make a
   speculative abstraction. Re-check every edit with the smallest relevant syntax/functional check.
4. If there are fixes, run `python scripts/preflight.py` and stage only the files authored by this
   run. Publish through `python scripts/publish.py "Weekly code review <YYYY-MM-DD>: <N> fixes, <M> flagged" --code`
   only when this automation is activated; in training mode stop with the verified staged diff for
   approval. If there are no fixes, report a clean pass and do not publish. Record exact commit SHA
   and URL only when known. Do not edit unrelated files in this routine.

## Required result fields

`date`; `base_sha`; `head_sha`; `commit_count`; `pathspec`; `findings_total`; `fixed[]`;
`flagged_for_owner[]`; `clean_pass`; `checks[]`; `staged_paths[]`; `publication.status`;
`publication.sha`; `publication.url`; `problems[]`; `next_action`.

## Outcomes

- `success`: the selected range was reviewed, all fixes were verified, and any publication was
  scoped to this run's files; a verified clean pass also qualifies.
- `no-op`: no commits fell in the review window or there were no findings/fixes; report the exact
  range and why no publication was needed.
- `blocked`: a concurrent dirty path, unclear ownership, or a judgment call prevents safe editing;
  leave it flagged with evidence and do not stage or publish it.
- `fail`: review, syntax/preflight, staging, publication, or report persistence failed. Report any
  partial edits and the recovery action; never claim a clean pass.

Use [REPORTING.md](REPORTING.md) and include exact SHAs for the review range.
