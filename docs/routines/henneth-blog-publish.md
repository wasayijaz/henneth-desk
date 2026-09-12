<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-blog-publish

Tuesday marketing-site blog routine. Create at most one post from the top eligible backlog item;
drafting and publication are separate checkpoints. Read [REPORTING.md](REPORTING.md),
`docs/CONTENT_BACKLOG.md`, `docs/CONTENT_ROUTINE.md`, `docs/BLOG_PLAN.md`, `docs/SEO_PLAN.md`,
`docs/PSX_MECHANICS_VERIFIED.md`, `docs/PSX_COSTS_VERIFIED.md`, and `AGENTS.md`.

## Run

1. Synchronize the assigned worktree for `wasayijaz/henneth-desk` and record the start time. Select
   the topmost blog queue item whose `site/src/content/blog/<slug>.mdx` file does not exist. File
   existence, not a status label, is the queue truth. If no item qualifies, finish as `no-op`.
2. Check for topic cannibalisation against existing blog, tool, and landing pages. Items already
   fully sourced may be drafted directly; any item needing research must be verified against a
   primary source in this run. Use one Content Researcher/Writer judgment pass with a
   `gpt-5.6-luna` high subagent when callable, otherwise execute the role inline from the committed
   content routine. Draft exactly one `draft: true` MDX file with sourced facts, the required answer-
   first structure, appropriate explain components, links to a tool and related blog content, and a
   link into `/psx/` or the named ticker page. Never invent a number or use advice language.
3. Run `npm run build` in `site/`. Render the draft at 1280px and 375px and inspect both; confirm
   no horizontal overflow. Keep `draft: true` if any build/render/source/voice gate fails.
4. Stop for the one-way publication checkpoint. A human owner must explicitly approve the reviewed
   draft before changing `draft: false`, staging it, or publishing it. If this routine is marked
   training-only, stop before any externally visible action even if a draft is approved. No approval
   or training-mode hold means `blocked`, not success.
5. After approval, flip `draft: false`, rerun the build and render checks, and publish only the
   authored content paths through the repository's safe publication path. Confirm the live URL returns
   HTTP 200 and appears in the sitemap when those probes are available. Record exact commit/deploy
   SHA and URLs; write `unknown` when proof is unavailable.

## Required result fields

`date`; `activation_mode`; `queue_slug`; `source_file`; `topic_cluster`; `cannibalisation_check`; `sources[]`;
`differentiated_claim`; `omitted_claims[]`; `internal_links[]`; `draft_path`; `draft_status`;
`build`; `render_1280`; `render_375`; `human_approval`; `publication.status`; `publication.sha`;
`publication.url`; `sitemap_url`; `next_queue_item`; `problems[]`; `next_action`.

## Outcomes

- `success`: one sourced post passed build, render, voice, human approval, publication, and live URL/
  sitemap verification; exact identifiers are reported.
- `no-op`: no eligible queue item existed, or a deliberate queue gate found no work before drafting.
- `blocked`: source verification, cannibalisation review, visual review, or human publication approval
  is outstanding. Keep the file as draft and report the precise gate.
- `fail`: drafting, build, render, staging, publication, live probe, or reporting persistence failed;
  never flip a failed draft live and preserve the last-good site.

Use [the shared reporting contract](REPORTING.md); report the differentiated claim, omissions, and
next queue item even when publication does not occur.
