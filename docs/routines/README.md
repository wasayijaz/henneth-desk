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

- Work only in the routine's existing isolated worktree. Never use the owner's checkout.
- Synchronize with `wasayijaz/henneth-desk` before work and again before publication.
- Desk and marketing routines never rebuild, stage, publish, or gate on Henneth CI.
- Use the bundled runtime paths returned by `load_workspace_dependencies`.
- Use Luna High subagents when judgment roles are required and callable. Otherwise perform the
  role inline from its repository definition. Never search for another provider's CLI.
- A required judgment role that neither ran nor was performed inline blocks that routine; it is
  not a successful training result.
- Research may overlap, but Desk publication is serialized: PM checkpoint, Daily refresh, Desk Room.
- Normal activated routines may publish their own verified outputs without asking again. Routines
  marked training-only stop before their first externally visible action.
- End with the Markdown result required by `docs/routines/REPORTING.md`.

## PM checkpoint

- Publication slot 1 on trading weekdays.
- Run `scripts/post_close_integrity.py` before treating the checkpoint trigger as a no-op.
- If deterministic data is stale, dispatch `desk-data.yml` once, wait, synchronize, and recheck.
  Never run the full cloud data pipeline locally.
- Read `state/checkpoint_trigger.json`. A false trigger is a valid no-op only after integrity passes.
- Run news sentinel. Run monitor only with open positions. Run macro and market analyst only when
  fresh news has impact 4 or higher.
- Rebuild the dashboard, run preflight, publish verified state, then acknowledge the checkpoint.
- Preserve append-only research and run history. Report the final remote SHA.

## Daily refresh

- Publication slot 2 on trading weekdays.
- Require the same-session PM publication and acknowledgement, or its verified no-op result.
- Run `scripts/post_close_integrity.py`; use the one-dispatch recovery path when needed.
- Run exactly news sentinel, macro agent, and market analyst, in that order.
- Each watchlist name needs a proven strategy, fundamental rating, and dated catalyst.
- Rebuild the dashboard, rerun preflight after final synchronization, then publish.

## Desk Room

- Publication slot 3 on trading weekdays.
- Require the same-session Daily publication or verified no-op and coherent post-close evidence.
- Read `docs/DESK-ROOM-PLAN.md`; debate only `room_plan._meta.run_full_now` within its budget.
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
- Report the top three. A justified “nothing new” result is valid.

## GitHub Actions cadence check

- Inspect scheduled `desk-data.yml` runs and bucket the last four full weekdays.
- A weekday with fewer than five scheduled runs is degraded.
- If degradation affects the latest one or two weekdays, dispatch two or three catch-up runs a few
  seconds apart, then run preflight informationally.
- Do not edit files or publish state in this routine.

## Blog publishing

- Training-only unless the automation explicitly records activation.
- Follow `docs/CONTENT_BACKLOG.md` and `docs/CONTENT_ROUTINE.md`; write exactly one topmost missing post.
- Use verified Desk documents and primary sources only. No advice language.
- Require relevant tool/blog links, a clean site build, desktop/mobile visual checks, and no mobile overflow.
- Stage only authored files. In training mode leave the post as draft and report the exact diff.

## Landing-page publishing

- Training-only unless the automation explicitly records activation.
- Build exactly one topmost missing solution page after checking search-intent cannibalisation.
- Reuse `SolutionPage.astro`; wire the solutions hub and footer.
- Require verified figures, no advice language, a clean build, desktop/mobile visual checks, no overflow,
  correct mobile ordering, and content that remains visible without animation.
- Stage only authored files. In training mode leave the page unpublished and report the exact diff.
