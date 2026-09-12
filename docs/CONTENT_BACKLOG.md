# Content backlog — the publishing queue

The scheduled routines read this file to decide what to write next. **Order matters**: always take
the topmost eligible blog item whose file is not published. Resume the earliest `draft: true` file
first; it is resumable work, not a published item. For the historical inventory, remote git
`draft: false` plus a live canonical URL and sitemap entry is sufficient; no historical Vercel or
deployment SHA is required. A new current-run publication must record its exact publication/deployment
identifier, and pending current-run evidence must be verified before any retry.

Do not trust a handwritten status column. For blogs, inspect the actual file, draft flag and
publication evidence described above. Landing-page selection retains its existing file-existence
rule at `site/src/pages/solutions/<slug>.astro`; blog authorization does not activate that routine.

Process: [CONTENT_ROUTINE.md](CONTENT_ROUTINE.md) · Strategy: [BLOG_PLAN.md](BLOG_PLAN.md)
· Comparison pages: [COMPARISON_PAGES_PLAN.md](COMPARISON_PAGES_PLAN.md)

---

## Blog queue — historical completed clusters

Historical sourcing for the first three is recorded in
[PSX_MECHANICS_VERIFIED.md](PSX_MECHANICS_VERIFIED.md). They already exist; this is not an open
writing queue. Re-verify facts before any future substantive update.

| # | Slug | Working title | Cluster | Sources |
|---|---|---|---|---|
| 1 | `psx-book-closure-ex-date` | Book closure and the ex-date, after T+1 | Market structure | MECHANICS §A |
| 2 | `psx-market-types-explained` | Ready, futures and what "spot" actually means on the PSX | Market structure | MECHANICS §B |
| 3 | `kse-100-index-explained` | How the KSE-100 is actually built | Market structure | MECHANICS §C |

Then Cluster 2 (Getting started) — **these need research first**, so a run that reaches them must
verify before drafting:

| # | Slug | Working title | Cluster |
|---|---|---|---|
| 4 | `how-to-start-investing-psx` | How to start investing in the PSX | Method |
| 5 | `cdc-sub-account-vs-investor-account` | CDC sub-account vs investor account | Method |

The 2026-09-12 content inventory shows these five queue items plus the other five existing blog
posts are already published. Preserve this historical queue and its sourcing notes as the record of
what was completed; do not delete or reorder it to manufacture a fresh queue.

## Blog queue — bounded next planning briefs

The initial Market structure, Method, and Valuation clusters are complete in the current inventory.
An exhausted eligible list is therefore a **planning trigger**, not a no-op: only when there is no
resumable draft **and** no eligible missing post may the next blog run append at most three candidate
briefs. These are planning records only. Every item below is `requires-research`, has not
been drafted or published, and must pass the source, cannibalisation, quality, build, render, and
publication-evidence gates. No search-volume or traffic number is asserted.

| Order | Slug | Audience / query | Differentiation | Required primary sources | Internal links | Status |
|---|---|---|---|---|---|---|
| 1 | `how-to-compare-psx-sectors` | Individual investor; “how to compare PSX sectors” | A source-led way to compare sector structure and operating context without turning a sector view into a named-stock call. | PSX sector classification and index methodology; current PSX notices or rulebook passages used for any market-structure claim; desk sector output only where its date and provenance are available. | `/psx/`; `/solutions/psx-screener-and-strategies/`; `/blog/how-to-value-a-psx-company/` | `requires-research`, not drafted, not published |
| 2 | `what-moves-the-psx-market` | Individual investor; “what moves the PSX market” | Explain the mechanism between macro releases and market context, with dated source evidence and no forecast or investment instruction. | SBP monetary-policy material; PBS releases for any inflation claim; PSX/NCCPL market or settlement material for any market-mechanics claim; source dates recorded in the run. | `/psx/`; `/blog/how-to-value-a-psx-company/`; `/solutions/psx-market-today/` | `requires-research`, not drafted, not published |
| 3 | `psx-astro-market-lens-methodology` | Pro reader; “PSX astrology market analysis” | Describe the desk’s tested, scored, falsifiable lens and its limits, not astrology as prediction; must be distinct from the existing astro landing page. | The desk’s dated scored results and methodology in the data layer; primary astronomical/ephemeris inputs used by that methodology; no unsupported finance or performance claim. | `/solutions/psx-astrology-market-lens/`; `/psx/`; `/blog/how-to-value-a-psx-company/` | `requires-research`, cannibalisation review required, not drafted, not published |

The routine must resume the earliest draft before selecting a missing item. It may refill this
section by appending no more than three new briefs only when there is no resumable draft **and** no
eligible missing item. A source or quality block is not a planning trigger: stop and report the block.
The routine must not create landing pages, alter the landing queue, or treat these briefs as approval
to write unsupported facts.

### Angles that are already sourced and must not be lost

- **Book closure (#1).** The rule changed *in the regulation text*: the 2023 rulebook headed clause
  10.6 "…– 2 SETTLEMENT DAY"; the Feb 2026 edition drops the suffix and reads "one settlement day".
  NCCPL's circular says "ex-price shall be computed w.e.f. BC-1". ⚠️ "Last day to buy" appears in
  **no** primary source — present it as a consequence of the ex-entitlement basis, never as a
  quoted rule. ⚠️ Splits are the exception (BAFL, PSX/N-403).
- **Market types (#2).** *"Spot market" does not exist as a defined PSX market type.* The word
  appears twice in the rulebook — a contract-note field, and a punitive T+0 mode for
  non-compliant issuers. The SERP vacuum exists because the thing does not exist. That IS the
  piece. Also: NDM is **T+0 to T+60**, not T+0.
- **KSE-100 (#3).** It is a **total-return** index (base Nov 1991 = 1,000) — most sources get this
  wrong. Selection is **36 sectors + 64 largest by free float**, not the "35 + 65" in circulation.
  ⚠️ No weight cap is published: write "the methodology does not specify a cap", never "there is
  no cap".

---

## Landing page queue

| # | Slug | Targets | Plan |
|---|---|---|---|
| 1 | `psx-dividend-calendar-and-yields` | dividend dates, yields, book closure | investor |
| 2 | `psx-company-fair-value` | "is X overvalued", intrinsic value | pro |
| 3 | `psx-market-today` | daily read, what moved and why | investor |
| 4 | `psx-astrology-market-lens` | the astro pillar (differentiated) | pro |

Each needs a distinct audience and a real problem statement. **If a proposed page would compete
with an existing blog post or tool page for the same query, skip it and extend that page instead** —
cannibalisation is the failure mode these are most likely to hit.

⚠️ #4 needs care: the astro lens is scored and falsifiable per the desk's rules. The page must
present it as a *tested, scored* lens with published results, never as prediction.

---

## Comparison queue

Highest-value gap on the site: comparison articles are the largest single category of AI-answer
citations and there are currently none. **Full spec, competitor set and extra gates:
[COMPARISON_PAGES_PLAN.md](COMPARISON_PAGES_PLAN.md) — read it before drafting any of these.**
Build in order; #1 is the hub the other two hang off.

| # | Slug | Targets | Notes |
|---|---|---|---|
| 1 | `compare/psx-research-tools` | "best PSX stock screener", "PSX research tools" | Hub. Needs the `/compare/` index + footer link shipped with it. |
| 2 | `compare/sarmaaya-alternatives` | "Sarmaaya alternatives" | Must open with the honest case for staying on Sarmaaya. |
| 3 | `compare/free-vs-paid-psx-research` | "is PSX research worth paying for" | Links `/pricing.md` and `/plans/`. |

⚠️ These name real competitors, which makes them the highest-liability pages on the site. Every
feature or price claim needs a same-run observation of that competitor's own site, recorded with a
date — never memory, never a third-party listicle. No disparagement, and concede honestly where a
competitor is better; a comparison that wins on every row is read as marketing and cited by nobody.

---

## Standing rules for every run

1. **No unverified number.** Rates from PSX_COSTS_VERIFIED.md, mechanics from
   PSX_MECHANICS_VERIFIED.md. Anything else needs a primary source read in that run.
2. **No advice language** (CLAUDE.md Rule 5).
3. **Build must pass, and the page must be rendered and looked at** before publishing. The build
   passes on layouts that are visibly broken — this has already happened twice.
4. **Scope `git add` to the files you touched.** Multiple sessions share this checkout and a
   blanket add has twice swept in someone else's in-flight work.
5. If a source, cannibalisation, quality, build, render, or publication-evidence gate fails, **stop
   and report — do not publish**. A missed week costs nothing; a wrong published number costs the
   domain's credibility.
6. The blog-only standing authorization dated 2026-09-12 permits planning, research, drafting,
   fact-checking, build, and render during the coordinator integration/release hold; publication is
   blocked until that hold clears. It then permits one autonomous blog publication per run. It does
   not authorize landing-page changes, tools, desk output, or automatic GSC requests.
