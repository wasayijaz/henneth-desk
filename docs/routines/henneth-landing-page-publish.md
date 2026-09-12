<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-landing-page-publish

Friday marketing-site landing-page routine. Build one distinct commercial-intent page from the
queue, with no doorway variants or topic cannibalisation. Read [REPORTING.md](REPORTING.md),
`docs/CONTENT_BACKLOG.md`, `docs/CONTENT_ROUTINE.md`, `docs/SEO_PLAN.md`,
`docs/PSX_MECHANICS_VERIFIED.md`, `docs/PSX_COSTS_VERIFIED.md`, and `AGENTS.md`.

## Run

1. Synchronize the assigned `wasayijaz/henneth-desk` worktree and record the start time. Select the
   topmost landing item whose `site/src/pages/solutions/<slug>.astro` file does not exist. If none
   qualifies, finish as `no-op`.
2. Check the target query against existing blog posts, tools, and solutions. If it competes with an
   existing page, do not create a duplicate; report the skipped item and the stronger existing path.
   Otherwise run one Content Researcher/Writer judgment pass with a `gpt-5.6-luna` high subagent
   when callable, or execute the role inline from the committed content routine. Copy an existing
   solution shell, use `SolutionPage.astro` props, and provide a specific audience, real problem,
   three useful features, real FAQs, sourced facts, and no advice language. Add the page to both the
   solutions hub `jump` array and the Footer Use cases list.
3. Run `npm run build` in `site/`. Render and inspect at 1280px and 375px: confirm no horizontal
   overflow, mobile desk-panel order, and that content remains visible when animation does not run.
   Keep the work unpublished if any gate fails.
4. Stop for explicit human approval before the one-way publication action. If this routine is marked
   training-only, stop before any externally visible action even if a draft is approved. Without
   approval or after a training-mode hold, report `blocked` and leave the page in its safe review state.
5. After approval, rerun build/render checks and publish only authored page/link paths. Probe the live
   URL for HTTP 200 and sitemap inclusion when available. Record exact commit/deploy SHA and every
   URL; use `unknown` instead of guessing.

## Required result fields

`date`; `activation_mode`; `queue_slug`; `source_file`; `target_query`; `audience`; `cannibalisation_check`;
`features_count`; `faq_count`; `sourced_facts[]`; `hub_link`; `footer_link`; `build`;
`render_1280`; `render_375`; `mobile_panel_check`; `animation_fallback_check`; `human_approval`;
`publication.status`; `publication.sha`; `publication.url`; `sitemap_url`; `next_queue_item`;
`problems[]`; `next_action`.

## Outcomes

- `success`: one distinct landing page passed source, link-wiring, build, visual, human approval,
  publication, and live verification gates; exact identifiers are reported.
- `no-op`: no eligible page remained, or deterministic duplicate checking correctly found no new
  page to build. A skipped cannibalising item records the existing page and is not a failure.
- `blocked`: duplicate review requires an owner choice, a source or visual gate is incomplete, or
  human publication approval is missing. Do not publish.
- `fail`: build, wiring, render, staging, publication, live probe, or report persistence failed;
  leave the last-good site live and report the exact failed gate.

Final reporting follows [REPORTING.md](REPORTING.md), including target query, audience, links, and
exact publication evidence.
