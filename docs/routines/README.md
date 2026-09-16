# Henneth routine runbooks

These are the repository-owned runbooks for the nine scheduled Henneth routines. They replace retired
desktop-scheduler instructions outside this repository. Automation prompts point here rather than
to a user-profile scheduler folder or a provider-specific command-line tool.

Every run reads, in order:

1. `AGENTS.md` for engineering and research governance.
2. `docs/OPERATIONS.md` and `docs/ROUTINES_AFTER_SPLIT.md` for publication boundaries.
3. `docs/routines/REPORTING.md` for the mandatory result format.
4. The matching routine section below.

## Shared execution rules

- **Initial release hold cleared (2026-09-12):** coordinator release
  `8c5a5dfc1681f5cb006c0ab93265d83ed4e52c97` reached remote `main`; Desk and marketing
  production deployments were READY at that commit, and authenticated Today/Board showed the
  verified official index change and exchange timestamp. Earlier instructions to await this
  initial clearance are superseded. This clears only that hold, not source, predecessor,
  preflight, serialization, deployment, receipt or cost gates. See
  [the acceptance ledger](ACCEPTANCE-2026-09-12.md#production-repair-verified--2026-09-12).
- **Takeover release authorization (2026-09-12):** the owner explicitly approved the remaining
  repairs, code pushes and normal scoped routine publications/dispatches. Former training-only
  routines retain the coordinator's initial shared-pipeline release hold, then may execute their
  normal verified path without asking for the same approval again. No schedule, task identity,
  model, product scope or cost boundary changes implicitly. A failed gate still blocks release.
- **Cost approval (owner instruction, 2026-09-12):** no new paid service, subscription,
  upgrade, credit purchase, or additional billable usage without explicit owner approval
  for that cost. Existing task/publication authorization is not spending authorization.
  Verify both provider and connector pricing before use; unknown pricing blocks that action.
  Do not enable overages, billing, or paid fallbacks. Continue unaffected free/local work.
  Google Search Console API itself is free; that does not establish that a connector or
  model call is free. Report any cost-related hold separately from a technical failure.
- Work only in the routine's existing isolated checkout (worktree or private clone). Never use the owner's checkout.
- Synchronize with `wasayijaz/henneth-desk` before work and again before publication.
- **Synchronization proof:** after a fresh fetch, compare the assigned checkout's `HEAD` with
  `origin/main` before research. A fetch updates the remote reference, not the working files.
  Do not read a runbook or state file before proving equality. Fast-forward a clean checkout; block
  on dirty or divergent state. A Git-metadata permission error requires scoped escalation of the
  same safe command, not skipping synchronization.
  If they differ, preserve the draft and synchronize the working branch through normal Git;
  stop on conflicts. Report both full SHAs. Do not run old local checks and label them as
  validation of the remote release. Revalidate affected findings after synchronization.
- If a linked checkout's Git metadata is outside the sandbox, request scoped escalation for the
  normal Git operation. Do not treat a permission error as a successful synchronization, change
  global Git trust, or create a replacement task. Preserve dirty work and stop on a real conflict.
- Desk and marketing routines never rebuild, stage, publish, or gate on Henneth CI.
- Resolve `load_workspace_dependencies` once at the start of every run and retain the returned
  absolute executable paths. On Windows, invoke the exact bundled Python executable for every
  Python command; never call bare `python` or `py`. A missing shell alias is an execution error to
  correct immediately, not evidence that a predecessor is absent or that the routine should stop.
- Use Luna High subagents when judgment roles are required and callable. Otherwise perform the
  role inline from its repository definition. Never search for another provider's CLI.
- A spawned role receives an execution brief that explicitly limits its files and states that the
  parent routine is already authorized. The role must execute that scoped research directly; a
  redundant subagent planning checkpoint is handled by the parent and is not a new owner gate.
  New costs, broader scope, destructive recovery, or a failed safety gate still stop normally.
- A required judgment role that neither ran nor was performed inline blocks that routine; it is
  not a successful training result.
- The weekday judgment chain is dependency-serialized: PM checkpoint, then Daily refresh, then Desk
  Room. Daily and Room use `scripts/wait_for_routine_receipt.py` against `origin/main`; clock time
  alone is never predecessor evidence. They do not dispatch data while a predecessor receipt is
  missing, and a successful catch-up resumes the current routine instead of ending it. Start one
  receipt-waiting command and let it finish; do not surround it with browser refreshes, narrated
  checks, or another polling loop.
- Judgment work has one owner per weekday chain: PM owns the bounded news scan, Daily owns Macro and
  Market Analyst, and Room owns selected debates. A downstream routine consumes verified upstream
  state instead of repeating the same role.
- Normal activated routines may publish their own verified outputs without asking again. Routines
  marked training-only stop before their first externally visible action.
- **Standing publication approval (2026-09-13):** after the owner directly approved the Blog and
  Harvest publication/finalization boundaries, routine-scoped commits, pushes and required
  completion receipts must not ask for the same approval again. This covers only the routine's
  documented path after every gate passes. New costs, schedule/model changes, CI actions,
  destructive recovery, widened scope or a failed gate still require their own handling.
- End with the Markdown result required by `docs/routines/REPORTING.md`.
- Published PM, Daily, Room and Harvest runs finish with the remotely verified receipt described
  in `FINALIZATION.md`. A failed publish or local-only acknowledgement is not completion.
- When assessing prices, follow `REPORTING.md`: identify the session and traded/current counts,
  cached coverage and fetch outcomes; separate source as-of dates from capture/completion times.
  Dated older last trades, failed fetches and research eligibility are distinct findings.
- A Saturday/holiday hold or `not_required` result is a calendar no-op, not a certificate of live
  price freshness. Record `not checked` for price evidence that this run did not assess.
- Progress through the routine's existing stages using actual evidence. Report the completed
  checkpoint and next unverified step; a training or no-op result does not activate a routine
  or prove a later publication/deployment stage.

## PM checkpoint

- Publication slot 1 on trading weekdays.
- Run `scripts/post_close_integrity.py` before treating the checkpoint trigger as a no-op.
- If deterministic data is stale, dispatch `desk-data.yml` once, wait, synchronize, and recheck.
  Check the authenticated GitHub CLI first and never run the full cloud data pipeline locally. A
  browser is a fallback only after the CLI is proven unavailable. Failure of one dispatch transport
  is not permission to abandon the approved recovery.
- Read `state/checkpoint_trigger.json`. A false trigger is a valid no-op only after integrity passes.
- Run News Sentinel once, with at most 10 external source retrievals. Run Monitor only with open
  positions. Hand high-impact news to Daily; PM never runs Macro or Market Analyst.
- Rebuild the dashboard, run preflight, publish verified state, then publish and verify the acknowledgement receipt.
- Preserve append-only research and run history. Report the final remote SHA.

## Daily refresh

- Publication slot 2 on trading weekdays.
- Wait up to 90 minutes for the same-session PM receipt and verify its publication, runlog,
  research SHA and acknowledgement from `origin/main`.
- Run `scripts/post_close_integrity.py`; use the one-dispatch recovery path when needed.
- Consume PM's verified news scan. Run exactly Macro and Market Analyst, in that order, with at most
  16 combined external source retrievals.
- Each watchlist name needs a proven strategy, fundamental rating, and dated catalyst.
- Rebuild the dashboard, rerun preflight after final synchronization, then publish.

## Desk Room

- Publication slot 3 on trading weekdays.
- Wait up to 90 minutes for the same-session Daily receipt and verify it from `origin/main` before
  any Room work or data dispatch.
- Read `docs/DESK-ROOM-PLAN.md`; debate only `room_plan._meta.run_full_now` within its budget.
- The freshly generated `state/room_plan.json` is authoritative for ticker scope. Scheduler or
  coordinator ticker names are hints only and must never override the live plan. A direct owner
  override is accepted only when it explicitly references the freshly generated plan; otherwise
  discard unselected scratch outputs before assembly.
- Run independent chartist and fundamentalist roles in parallel when callable, then bull/bear debate,
  deterministic assembly, verifier QA, translation, scoring, dashboard build, and preflight.
- If required roles are unavailable, perform them inline or stop as blocked; do not seek another CLI.

## Weekly broker harvest and sector debate

- Synchronize first and keep the run token-frugal.
- Scan recent public broker research; file only calls with named house, ticker, date, and source URL.
- Refresh the deterministic sector dossier. If fewer than three sectors are valid, skip the debate.
- Select one sector by the persisted rotation. Run one combined sector-debate role and one chair role.
- Both roles use only the sector dossier; substantial dissent is mandatory.
- Run room QA, dashboard build, and preflight before any activated publication.

## Weekly code review

- Review code commits since the previous weekly checkpoint; exclude generated state.
- Prioritize correctness, security, dead code, duplicated rules, stale paths, and material inefficiency.
- Fix only low-risk, well-understood issues and add a check that would have caught each meaningful bug.
- Flag judgment calls without changing them. Run relevant syntax, regression, preflight, and build checks.
- Use pull-request review and scoped staging; never sweep unrelated files into a commit.

## Weekly product scout

- Propose and rank improvements; do not implement product changes.
- Inspect current product evidence and deduplicate against the existing backlog.
- Add only specific items with problem, evidence, impact, effort, risk, and acceptance test.
- Cover existing-product improvements, useful new features and efficiency opportunities.
- Explain each proposal's build level (small fix, enhancement, larger feature), scope and first
  working stage. Report the top three. A justified “nothing new” result is valid.

## GitHub Actions cadence check

- Inspect scheduled `desk-data.yml` runs and bucket the last four full weekdays.
- A weekday with fewer than five scheduled runs is degraded.
- If degradation affects the latest one or two weekdays, dispatch two or three catch-up runs a few
  seconds apart, then run preflight informationally.
- Do not edit files or publish state in this routine.

## Blog publishing

- Owner-authorized autonomous blog workflow (2026-09-12), subject to the coordinator's initial
  shared-pipeline release hold in `henneth-blog-publish.md`; no new per-post approval after clearance.
- Follow `docs/CONTENT_BACKLOG.md`, `docs/BLOG_PLAN.md` and `docs/CONTENT_ROUTINE.md`. Resume
  unfinished drafts or reconcile pending publication first; refill an exhausted queue with at most
  three distinct topic briefs, then write at most one post per run.
- Use verified Desk documents and primary sources only. No advice language.
- Require relevant tool/blog links, a clean site build, desktop/mobile visual checks, and no mobile overflow.
- Require a separate independent fact-checker. Stage only authored files; leave the post as draft
  while a release hold or any content/build/visual gate remains unresolved. Return its verified
  production URL for owner submission to GSC, never claim indexing from HTTP or sitemap alone.

## Landing-page publishing

- Owner-authorized after the shared-pipeline release hold clears, as recorded in the automation.
- Build exactly one topmost missing solution page after checking search-intent cannibalisation.
- Reuse `SolutionPage.astro`; wire the solutions hub and footer.
- Require verified figures, no advice language, a clean build, desktop/mobile visual checks, no overflow,
  correct mobile ordering, and content that remains visible without animation.
- Stage only authored files. In training mode leave the page unpublished and report the exact diff.
