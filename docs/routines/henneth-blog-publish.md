<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-blog-publish

Tuesday marketing-site blog routine. Under the standing blog-only authorization dated 2026-09-12,
plan, create, verify, and publish at most one post per run; drafting and publication remain separate
states. Read [REPORTING.md](REPORTING.md),
`docs/CONTENT_BACKLOG.md`, `docs/CONTENT_ROUTINE.md`, `docs/BLOG_PLAN.md`, `docs/SEO_PLAN.md`,
`docs/PSX_MECHANICS_VERIFIED.md`, `docs/PSX_COSTS_VERIFIED.md`, and `AGENTS.md`.

## Run

1. Synchronize the assigned worktree for `wasayijaz/henneth-desk` and record the start time. The
   first execution is under coordinator integration/release hold for **publication only** until the
   shared-pipeline repairs have shipped and been independently verified. Continue inventory, planning,
   research, fact-checking, drafting, and validation during the hold; leave any result unpublished.
   Resume the earliest existing `draft: true` blog before selecting a new item. For historical
   inventory, remote git `draft: false` plus live canonical and sitemap evidence is sufficient; do not
   require a historical Vercel/deployment SHA. For a new current-run publication, require the exact
   publication/deployment identifier and verify any pending current-run evidence before retrying.
2. Select the top eligible blog item after cannibalisation review against existing blog, tool, and
   landing pages. Resume the earliest existing draft first. Only when no resumable draft exists **and**
   no eligible missing item exists may the planner append at most three `requires-research` candidate
   briefs to `docs/CONTENT_BACKLOG.md` based on an actual content/query gap. Briefs must record
   audience, query, differentiated claim, required primary sources, internal links, and `not
   published`; they are not article bodies and never change the landing queue. Source or quality
   blockage stops the run; it does not justify inventing a brief or a finance fact. Work on at most one
   post in this run.
3. Check every factual claim against the required primary source in the same run. Use Luna High for
   the writer when callable, otherwise the committed inline role; then run a separate independent
   fact-check pass. Draft or resume exactly one `draft: true` MDX file with sourced facts, the required
   answer-first structure, appropriate explain components, links to a tool and related blog content,
   and a link into `/psx/` or the named ticker page. Never invent a number or use advice language.
4. For local visual validation only, temporarily set this draft to `draft: false`, run `npm run build`
   in `site/`, and serve the local build. Render its actual URL at 1280px and 375px and inspect both;
   confirm no horizontal overflow. Restore `draft: true` immediately after local validation, including
   on failure. Do not commit or push the temporary preview state.
5. Once source, cannibalisation, quality, build, voice, and render gates pass, no fresh per-post owner
   approval is required. If the coordinator hold is still active, leave the validated work as
   `draft: true` and report `publication.status=blocked` for that hold; do not stall research or
   drafting. Once the hold clears, flip `draft: false` and publish only the authored content paths
   through the repository's safe publication path. Publish one post maximum. If any gate fails, leave
   the work unpublished and report the precise block.
6. Verify publication before treating a new current-run item as complete or selecting it again: confirm
   the live canonical URL, HTTP status, noindex/robots result, exact sitemap entry, and exact
   publication/deployment identifier. On retry, verify pending current-run evidence first; actual
   evidence means already published and must not be republished, while missing or ambiguous evidence is
   `blocked` pending reconciliation. Historical inventory uses remote git `draft: false` plus live
   canonical and sitemap evidence and does not require a retroactive deployment SHA. Record exact
   identifiers and URLs for the current run; write `unknown` when proof is unavailable.

## Required result fields

After verified publication, include a separate **Google Search Console** section with short bullets:
- **URL to inspect/request indexing:** the exact clickable production canonical URL (not preview).
- **Live checks:** HTTP status, canonical target, noindex/robots result, and exact sitemap containing it.
- **Google indexing:** `not checked` unless actual Search Console evidence was inspected; HTTP 200
  and sitemap inclusion do not prove indexing. Never claim an indexing request was submitted unless done.
- **Owner action:** paste that URL into Search Console URL Inspection and request indexing if needed.
For no-op, draft, failed or blocked publication, say **No new URL published; nothing new to submit**.
Existing live pages may be listed separately and must not be described as published by this run.

`date`; `activation_mode`; `authorization_basis`; `queue_slug`; `source_file`; `topic_cluster`;
`cannibalisation_check`; `sources[]`; `differentiated_claim`; `omitted_claims[]`; `internal_links[]`;
`writer_model`; `fact_check`; `queue_refill[]`; `draft_path`; `draft_status`; `build`; `render_1280`;
`render_375`; `human_approval` (must say `not required` after the hold clears); `publication.status`;
`publication.sha`; `publication.url`; `publication_evidence`; `idempotency_check`; `sitemap_url`;
`next_queue_item`; `problems[]`; `next_action`.

## Outcomes

- `success`: one sourced post passed the independent fact-check, build, render, standing authorization,
  publication, idempotency, and live URL/sitemap verification; exact identifiers are reported.
- `no-op`: a retry verifies the same current-run post already published, with no new work or
  publication. Not used for an exhausted blog queue: exhaustion triggers bounded planning.
  A lack of defensible, sourceable candidates is `blocked`, never permission to publish filler.
- `blocked`: coordinator release hold, source verification, cannibalisation review, quality, visual
  review, ambiguous publication evidence, or another hard gate is outstanding. Keep the file as draft
  and report the precise gate.
- `fail`: drafting, build, render, staging, publication, live probe, or reporting persistence failed;
  never flip a failed draft live and preserve the last-good site.

Use [the shared reporting contract](REPORTING.md); report the differentiated claim, omissions, and
next queue item even when publication does not occur.
