# Content routine — blogs and landing pages

The repeatable process. Read [BLOG_PLAN.md](BLOG_PLAN.md) for *what* to write and
[SEO_PLAN.md](SEO_PLAN.md) for why; this is *how*, and it exists to make each new page cheap.

**The economics.** The machinery is built. A new page should be a small data file plus prose, not
a design exercise — if you find yourself writing CSS for a content page, the component is missing
and should be added to `explain/` instead of inlined.

## Standing authorization — blog only

Effective **2026-09-12**, the owner authorizes this routine to plan, research, draft, independently
fact-check, build, and render **one blog post per run** during the first execution's coordinator
integration/release hold; only publication is blocked until the shared-pipeline repairs have shipped
and been independently verified. Once that hold clears, it also authorizes publication and verification
without fresh per-post approval. This does not authorize landing-page, tool, desk, GSC, unrelated
code, or state changes. Source, quality, cannibalisation, build, render, and publication evidence
remain hard stops.

Use Luna High for the writer when callable and a separate independent fact-check pass for every
factual claim. A draft is resumable and unpublished; a `draft: false` flag alone is not proof of
publication. For historical inventory, remote git `draft: false` plus a live canonical URL and
sitemap entry is sufficient; no historical Vercel/deployment SHA is required. For a new current run,
the exact publication/deployment identifier is required. Before any retry or repeat, verify pending
current-run evidence and the idempotency record for that slug; existing evidence means do not publish
again.

---

## 1. Two page types, split by intent — never duplicate a topic across both

| | Blog post | Landing page |
|---|---|---|
| Lives at | `/blog/<slug>/` | `/solutions/<slug>/` |
| Source file | `src/content/blog/<slug>.mdx` | `src/pages/solutions/<slug>.astro` |
| Intent | Informational — "how does settlement work" | Commercial — "PSX screener" |
| Query shape | a question | a product |
| Job | earn trust, get cited | convert |
| Shell | automatic via `[...slug].astro` | `SolutionPage.astro` |

**The one rule that matters: one topic, one page.** A blog post and a landing page targeting the
same query compete with each other and split the signal. If a topic is already covered by a tool
page or a post, extend that page rather than adding a second one.

⚠️ **Landing pages do not create backlinks.** A link from henneth.app to desk.henneth.app is an
*internal* link on the same root domain. Only another domain linking here creates a backlink, and
no page we build can produce one. Landing pages catch commercial-intent queries and concentrate
internal link equity — that is the whole of their SEO job.

---

## 2. Publishing a blog post

1. **Pick the top eligible blog item** from the inventory and backlog. Resume the earliest `draft: true`
   file before selecting another item. A missing file is eligible only after duplicate/cannibalisation
   checks. Only when there is no resumable draft **and** no eligible missing item may the routine append
   at most three research-required blog briefs based on actual content/query gaps, then select at most
   one; an exhausted list is a planning trigger, not a silent no-op. Source or quality blocks stop the
   run rather than refill it.
2. **Verify every fact first.** Rates from PSX_COSTS_VERIFIED.md, mechanics from
   PSX_MECHANICS_VERIFIED.md. Anything else needs a primary source *in hand before drafting*.
   Rule 2 applies to published content.
3. Create `src/content/blog/<slug>.mdx` with `draft: true`:

```yaml
---
title: Under 60 chars, contains the target query
description: One sentence under 155 chars. This is the search snippet.
pubDate: 2026-07-21
cluster: Market structure     # must be one of CLUSTERS in content.config.ts
draft: true
---
```

4. **Import only the components the piece needs:**

```jsx
import Snapshot from '../../components/explain/Snapshot.astro';
import Timeline from '../../components/explain/Timeline.astro';
import Ledger   from '../../components/explain/Ledger.astro';
import Matrix   from '../../components/explain/Matrix.astro';
```

5. **Structure that works** — answer first, argue second:
   - One paragraph stating the answer plainly
   - `<Snapshot>` with the four facts that matter
   - The argument, with `<Timeline>` / `<Ledger>` / `<Matrix>` carrying the numbers
   - A sources list linking the primary documents
6. **Link out and across.** At least one link to a relevant `/tools/` page, one to `/blog/`, and
   every primary source cited. Outbound links to regulators are the strongest E-E-A-T signal a
   YMYL page has — the T+1 pillar shipped without them and was weaker for it.
   ⚠️ **Also link down, into `/psx/`.** The first four posts in this cluster shipped with zero
   links into the ticker layer — an island next to another island (the `/psx/` hub itself had the
   same problem until its footer link was added). Every post names a company or the board
   generically at some point; don't skip the link:
   - **Names a specific company** ("Bank Alfalah", "OGDC") → link it to `/psx/<symbol lowercase>/`
     if that symbol exists in `tickers.json`. If it doesn't (not yet covered), don't force it.
   - **Names PSX companies generically** ("every listed company", "the wider board", "the desk
     covers") → link that phrase to `/psx/`, the hub.
   - One of the two is a hard minimum per post, same tier as the `/tools/` link above.
7. `npm run build`, then **render it** — temporarily flip `draft: false` only for local validation,
   serve `dist/`, and look at 1280px and 375px. Restore `draft: true` immediately after validation,
   including on failure. The build passes on layouts that are visibly broken; two real defects in the
   first post were invisible to it.
8. After all gates pass and the coordinator hold clears, the standing blog authorization permits
   flipping `draft: false`, committing, and publishing one post. During the hold, leave the validated
   work as a draft and report publication as blocked by the hold. For historical inventory, remote
   git `draft: false` plus live canonical and sitemap evidence is sufficient; for this current run,
   record the exact publication/deployment identifier. If a run is retried, verify any pending
   current-run evidence before repeating; actual evidence means already published and must not be
   republished.
9. **GSC is owner-only.** Report the exact production URL and observed live evidence, but never submit
   an indexing request automatically. The owner may use GSC URL Inspection separately.

---

## 3. Publishing a landing page

Copy an existing page in `src/pages/solutions/` and change the props. Everything visual —
breadcrumbs, schema, ticker tape, desk panel, FAQ, CTA band — comes from `SolutionPage.astro`.

```astro
---
import SolutionPage from '../../components/SolutionPage.astro';
---
<SolutionPage
  title="…"            {/* browser tab + search result */}
  h1="…"               {/* the on-page headline; may differ from title */}
  description="…"      {/* search snippet, under 155 chars */}
  path="/solutions/<slug>/"
  kicker="For …"
  icon="learn"         {/* any id in IconSprite */}
  lead="One sentence."
  problem="The problem this audience actually has, in their words."
  appPlan="investor"   {/* investor | pro | null → contact CTA */}
  features={[{ icon, title, body }, …]}   {/* three reads best */}
  faqs={[{ q, a }, …]}                    {/* real questions only */}
>
  {/* Free-form middle section. Put the internal links here. */}
</SolutionPage>
```

**Then wire it up — a page nothing links to will not rank:**
- Add to the `jump` array in `src/pages/solutions.astro` (the hub)
- Add to the `Use cases` column in `src/components/Footer.astro`

Both, deliberately. A page built to rank but reachable only from a footer is the doorway pattern
Google targets. If it is worth ranking it is worth navigating to.

---

## 4. The desk visuals

Two components, both reading the committed public slice
(`site/src/data/public/context.json`, regenerated by `scripts/build_public_slice.py`):

| Component | Shows | Default |
|---|---|---|
| `TickerTape` | 15 real symbols and day moves, scrolling | on |
| `DeskPeek` | 4 real signals with closes, plus macro strip | on |

Turn off per page with `showTape={false}` / `showPeek={false}`.

**They use REAL data, and that is not optional.** Rule 2 forbids a price from memory, and an
invented move printed beside a real listed company is a false claim about that company. The slice
already carries the board, so honest costs the same as faked. Both components carry the `as_of`
date — that stamp is what keeps a stale build from implying a live feed.

### Animation rules — learned the hard way

- **Never animate opacity from 0 for an entrance.** Every fill mode that makes the delay look
  right (`both`, `backwards`) paints that zero before the animation starts, so anything rendering
  without advancing the animation — a paused compositor, a crawler, a social scraper — sees an
  empty panel containing your real content. `DeskPeek` originally did this and rendered a blank
  white box. **Animate transform only.** Worst case is content sitting in its final position.
- **Add motion inside `@media (prefers-reduced-motion: no-preference)`**, rather than removing it
  in a `reduce` branch. Then "reduced motion" and "animation never ran" land on the same
  fully-visible default.
- **Mobile leads.** Most PSX traffic is on a phone. `SolutionPage` gives the desk panel `order: -1`
  below 900px so the visual, not the prose, stops the scroll.

---

## 5. Before publishing anything

- [ ] Every figure traces to a verified doc or a primary source you read
- [ ] No advice language (Rule 5) — pages explain, they never say what to buy
- [ ] Internal links: at least one tool, one related page
- [ ] Internal link into `/psx/` — a named company to its ticker page, or generic coverage to the hub
- [ ] Primary sources linked where cited
- [ ] `npm run build` clean
- [ ] **Rendered and looked at**, at 1280px and 375px
- [ ] No horizontal overflow at 375px
- [ ] Linked from the hub and the footer (landing pages only)
- [ ] Blog posts: production URL and live publication evidence recorded; GSC request remains owner-only
- [ ] Landing pages: follow the existing landing-page routine and its separately governed GSC step

---

## 6. Cadence

**One genuinely good page per week.** Not five thin ones — Google's helpful content system targets
scaled production and a new domain has no buffer.

From week 4 the compounding work is not new pages, it is the GSC loop: filter to positions 5–20,
sort by impressions, improve *those* pages. A page at position 11 already has the ranking signal;
moving it to 6 beats writing a new post from zero.

**Judge month 3 on impressions and average position, not sessions.**
