<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-product-scout

Sunday product-improvement scout. Its purpose is a practical roadmap: improve existing features,
suggest useful new features, and improve usability, speed, reliability and operating efficiency.
Explain the build level so the owner can choose the next work. It proposes and ranks; it never builds, edits source, or changes
anything except `state/product_backlog.json` during an actual routine run. Read [REPORTING.md](REPORTING.md),
`AGENTS.md`, `docs/ROUTINES_AFTER_SPLIT.md`, `docs/OPERATIONS.md`, and the existing backlog.

## Run

1. Synchronize the assigned worktree and record the PKT start time.
2. Inventory the shipped UI before forming ideas: list every `page[A-Z]...` function in
   `dashboard/app.js`, inspect navigation routes and subfeatures, and read the named function for
   every related candidate. Check `state/dashboard.json`, one ticker's room/explainer/fair-value
   slices, the current backlog, and the known-gap operations sections.
3. Run `python scripts/provenance_lint.py` and inspect Room QA caveats. Then run one Product Scout
   judgment pass with a `gpt-5.6-luna` high subagent when callable; otherwise perform the role inline
   from this card. Propose at most ten new items using the existing `accuracy`, `clarity`, and
   `feature` categories. Efficiency improvements belong in the matching existing category:
   accuracy for reliability/data integrity, clarity for reducing user effort, feature for useful
   new capability. Do not force an idea into every category without evidence.
4. Every item must cite a concrete observation, include an `existing_check` naming the page function
   examined, carry impact/effort/score/status, and avoid proposing a rebuild of an existing feature.
   Carry forward open items without duplicating or truncating them and sort the full list by score.
   For each new proposal explain: user problem, expected benefit, concrete proposed change,
   `build_level` (`small_fix`, `enhancement`, or `larger_feature`), `build_scope` (what gets built
   and its dependencies), `acceptance_test`, and tradeoffs. Distinguish a measured efficiency
   issue from a hypothesis requiring measurement; never invent performance gains or precise
   delivery estimates. Surface larger work in useful stages, starting with a working first version.
5. Update only `state/product_backlog.json` with `updated`, the existing note, categories, and ranked
   items. Run the applicable deterministic validation. If this automation is activated, publish with
   the state-only default `python scripts/publish.py "Weekly product scout <YYYY-MM-DD>: <N> items ranked"`;
   in training mode stop with the verified backlog delta for approval. Do not use a code-publication
   path. Record the exact SHA/URL only when proven.

## Required result fields

`date`; `page_inventory[]`; `routes_checked[]`; `backlog_before_ids[]`; `provenance_result`;
`qa_observations[]`; `new_items[]` (≤10); `carried_items[]`; `categories`; `item_count`;
`top_three[]`; `backlog_written`; `publication.status`; `publication.sha`; `publication.url`;
`problems[]`; `next_action`.

## Outcomes

- `success`: inventory and accuracy evidence were checked, ranked backlog was written, and the
  state-only publication was verified.
- `no-op`: no new improvement survived duplicate and evidence checks; refresh only the date if that
  is the repository's established behavior and report why the existing backlog covers the field.
- `blocked`: product inventory or provenance evidence was unavailable, or a candidate would require
  an owner decision before it could be stated safely; do not write speculative backlog items.
- `fail`: an unauthorized file changed, backlog validation/publication failed, or report persistence
  failed. Restore no files automatically; report the exact boundary for the owner.

Report using [the shared contract](REPORTING.md), with the top three items easy to scan.
For each top item, show improvement, benefit, build level and recommended first step. Label the
recommendation `suggested`, `approved`, `in progress`, or `shipped` according to evidence; creating
a backlog entry never means the feature was built. Put detailed proposals in the backlog and
keep the reply readable. The scout does not implement features during its routine.
