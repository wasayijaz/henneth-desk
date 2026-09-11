# Henneth

**A multi-agent research & analytics publication covering the Pakistan Stock Exchange in depth, and the global tape for context.**
It researches, values, backtests, debates, and monitors — then puts every call on the record and grades it.
It **never places orders**; execution is manual on your broker.

It is shaped as a **publication**, not an advisory service: output is scheduled, impersonal, and
identical for every subscriber. It does not know the reader, does not tailor output to them, and
does not tell anyone what to buy. See [`docs/PUBLICATION_RESTRUCTURE.md`](docs/PUBLICATION_RESTRUCTURE.md).
The one deliberate exception is the personal astrology lens, which is disclaimed on every surface.

> ⚠️ **This is a research & analytics tool, not an investment adviser.** Everything here is educational
> information — never personalized advice, a recommendation, or a promise of returns. Past performance
> does not predict future results. Investing in PSX carries risk, including the loss of capital. You make
> your own decisions. (A platform-wide footer + a "Research · not advice" badge repeat this on every page.)

**Live:** https://desk.henneth.app/  ·  private repo, hosted on Vercel
Docs: [`CLAUDE.md`](CLAUDE.md) (desk rules) · [`docs/SYSTEM-REGISTRY.md`](docs/SYSTEM-REGISTRY.md) (system map)
· [`docs/PRODUCT-ROADMAP.md`](docs/PRODUCT-ROADMAP.md) (path to a subscription product)

> **Reviewing this repo?** Start with [`CHANGELOG.md`](CHANGELOG.md) — newest first, and every entry states
> what changed, why, and for bugs how recurrence is prevented (including bugs introduced during a build and
> caught before shipping). Then read **Entitlements & security posture** and **Known gaps** below; both are
> written for audit rather than for marketing. Nothing is billed yet, and `state/legal.json` has not been
> reviewed by a lawyer.

---

## What it does

A single-page terminal (collapsible sidebar, hard-cornered mono "Bloomberg-lite" design) over the whole PSX universe.
Dense sections render as **horizontal scroll-tile lanes at every viewport width**, not just on phones — a 1,400px
list buries what sits under it exactly as a 375px one does:

- **Today** — the desk's plain-English daily read: tone, favoured/avoided sectors, a short watchlist.
- **Board** — live universe heatmap, backtest-proven signals, predictability ranks, positions, news + agent wire.
- **Insider & off-market** — every ticker page's Data flags, Signal Stack, and "at a glance" explainer now
  surface insider/substantial-shareholder filings and off-market trade prints (`state/insider_activity.json`,
  `state/offmarket_activity.json`), retained ≥3 months and refreshed weekly. Metadata only — filing counts and
  off-market share/value totals, never a buy/sell read; kept out of the Signal Stack confluence tally for the
  same reason as Astro.
- **Value** — every stock valued four ways (peer P/E, earnings-power vs bond yield, Graham, DDM); the
  median is the model fair value, with the full working expandable per row.
- **Strategies** — 52 transparent, rule-based strategies, each backtested on every stock's ~19-year history
  (win rate, expectancy after costs, out-of-sample) — you see what *actually* worked, not theory. The
  Board itself no longer publishes entry/stop/target on a named ticker (same regulatory line as the
  Desk Room, above); a **free strategy-level calculator** on the website lets a reader pick a
  strategy and their own price and derive their own levels — the desk states the rule, the reader
  supplies the stock and the price.
- **The Desk Room** (on every ticker) — named AI analyst personas research and **debate** the stock:
  a technical desk and a fundamental desk (kept separate), then a bull case vs a bear case. No Chair
  verdict — under SECP's amended research-analyst rules (S.R.O.7(I)/2026), a house view or a dated
  call on a named stock is a licensed research service, so the Room ends at the debate: commentary,
  not a direction. A **"watch the desk analyse" replay** plays the whole debate back as a staged,
  animated walkthrough (it animates the *saved* session — no agents run per view, so it's free and
  always available).
- **Scores** — track records, scoped to what the desk is allowed to call: sector, macro and astro
  reads (never a named-stock verdict, since the Room no longer issues one) plus the brokers, ranked
  overall and per sector on their own public calls.
- **Sectors** — a weekly sector debate, opened TLDR-first: the house view, the case for and the case
  against as three tiles readable in about three minutes, with the full argument behind a
  read-the-transcript modal. Sectors the desk has argued carry a run dot; the rest carry a real empty
  state rather than a blank panel.
- **Research** — broker notes and company filings (results / AGM / corporate-briefing), digested and tagged.
- **Macro / Dividends / Earnings / News** — the global tape that moves PSX, a geo-risk radar, dividend
  timing (buy-by / ex-date), the earnings calendar, and a permanent news log.
- **Global coverage** — 23 US and global symbols (S&P 500, Nasdaq 100, Dow, Russell, VIX, all eleven
  SPDR sectors, EEM/EFA/ACWI, TLT/HYG/GLD/USO), defined in [`config/markets.json`](config/markets.json).
  Index and sector level only, for the context they give PSX: **no US single stocks and no US signals**
  (`signals_enabled: false`). Data is the same free Yahoo endpoint the desk already used —
  `fetch_deep_history.py` differed only by a `.KA` suffix, so a second market cost no new vendor.

### Versioning and release notes

Versions are **CalVer** — `vYYYY.MM.DD`, plus `.2` for a second release the same day. Chosen over
semver because releases here are date-driven, and because the version should answer the question a
reader actually has (*how current is my desk?*), which `v1.14.2` does not.

The terminal shows the current version at the foot of the sidebar, with a dot when it has moved
since that browser last acknowledged one. Clicking it opens **What's new**. The same release history
also lives at all times on **`/shipped`** (linked from the sidebar, open to signed-out visitors) —
so a completed backlog item is visible on the site itself, not only in this repo.

Those notes come from `<!--public ... -->` blocks inside [`CHANGELOG.md`](CHANGELOG.md), extracted by
`scripts/build_changelog.py` into `state/changelog.json`. **CHANGELOG.md itself is the engineering
record and is never published** — it names migrations, internals, and a security hole that was found
and closed. The extractor **fails closed**: a release with no public block publishes nothing, and the
build aborts outright if a public note contains an obviously internal term. Forgetting a marker costs
a shrug; an opt-out design would leak the first time someone forgot.

Each ticker page also carries a **risk profile** (volatility, real max-drawdown with era context, liquidity,
valuation, dividend reliability), a **"questions before buying"** checklist, and **"what the brokers say."**

- **Accounts** — sign-up / sign-in (Supabase Auth), a short onboarding quiz + guided wizard, and a personal
  **watchlist** that overlays the shared research. Per-user data is row-level-secured; the research layer is
  shared and read-only to users.
  Signed out, a gated route lands you **straight on the sign-in / create-account research terminal**
  (`dashboard/auth-terminal.js` + `.css`) — a full-screen animated terminal, not an interstitial card
  asking you to pick a door first. Onboarding runs inside that same surface once the account exists, so
  the visitor never changes screens between "create account" and "answer four questions". On a phone the
  form sits at the **top** and the terminal scene below it, because the first thing on screen has to be
  the thing you came to do.

### The personal astrology pillar (`/astro`, `/mychart`, `/cast`)

A Vedic (sidereal) financial-astrology layer, shipped as **exploration and cultural interest — explicitly
not an edge claim.** It exists because it is engaging and differentiated; it is framed honestly because
the desk tested it and it failed.

- **The desk's own test result, stated plainly:** `astro_backtest.py` ran **2,589 hypotheses across 101
  subjects** (99 stocks + KSE100 + KMI30) over ~19 years, and `astro_natal_test.py` ran **379** natal-method
  hypotheses across **27** verified company birth charts. **Zero survivors** in both after Bonferroni and
  Benjamini-Hochberg correction, on market-adjusted returns (`r − β·r_mkt`, so beta isn't mistaken for
  signal). At p<0.05 you would expect ~129.5 false positives from 2,589 tests by luck; 143 came back.
  The same machinery pointed at ordinary macro factors (`sector_macro.py`) *did* find real effects —
  **17 Bonferroni / 34 FDR survivors of 98**, e.g. oil→E&P at p=2e-5, joint R² ≤2.6%. That contrast is the
  point, and it is published in `state/astro_backtest.json` rather than summarised away.
  **The natal test carries an explicit power caveat:** with company charts this young it is weakly powered,
  so the result is *"not demonstrated"* — **not** *"disproved."* The desk keeps that distinction because
  claiming disproof would be a verdict it has not earned.
- **Your chart.** A user enters birth date/time/place; the browser casts their sidereal (Lahiri) natal
  chart from a committed 552 KB packed ephemeris (`state/natal_ephem.bin`, 1950–2035, daily, `<9H`
  tenths-of-a-degree) and scores every PSX name against it with classical techniques (Tara koota, Moon-lord
  friendship, benefic placement, dasha resonance). Ascendant is computed live from LST + latitude, and is
  **never invented** when birth time is unknown — the reading falls back to Chandra lagna, a real Vedic
  technique.
- **The daily layer.** The natal chart is static, so the product is the *moving* sky: gochara placed from
  the natal Moon and recomputed every day, a transit ring on the orrery, and dated "worth another look"
  shifts (ingresses, dasha/antardasha turnovers) — computed client-side from data already shipped, so it
  costs nothing per user.
- **The per-stock reading is a join, not a printout.** Placements alone are worthless, so every
  stock's reading carries four blocks, each built only from `state/`: the **Vimshottari ladder**
  (maha/antar with real dates and the next three turns, each labelled the way the tradition labels
  it — stamped *the tradition's claim, untested*); the **falsification receipt for that name** (its
  own rows out of `astro_backtest.json`: conditions tested, days in/out, effect %/day, p-value,
  survived or not); the **Pakistan (1947) and KSE-100 (1991) comparison**; and **today's live sky
  joined to what each active condition actually measured**. A stock with no birth chart falls back
  to its sector's peers and then to the KSE-100 proxy, and **says which it used** — a peer's numbers
  are never presented as the stock's. Nothing in any block is a direction, target or level.
- **`scripts/astro_context.py`** makes that join possible: it names today's conditions in
  `astro_backtest.py`'s exact vocabulary and **asserts its own output against the backtest's test
  list every run**, so the two cannot silently drift apart into a lie. It also publishes the
  Pakistan and KSE-100 charts — cast at **both** disputed birth times, publishing only the slow
  grahas (Saturn, Jupiter, Rahu, Ketu) whose placement agrees under both; the Moon and ascendant are
  refused outright, enforcing `astro_map.json`'s `usage_rule` in code rather than in a footnote.
- **Visuals.** An isometric-feel natal orrery (foreshortened orbits, native SVG pixel glyphs — *not*
  `foreignObject`, which breaks in Safari), a Vimshottari dasha ribbon with an antardasha sub-period strip,
  per-stock timing windows, and 8 commodities read through their traditional rulers.
- **Scored like anything else.** `astro_claims.py` files dated, **market-relative** astro claims with a
  stamped benchmark level, graded on the same public scorecard as every broker call.

### Three plans, one data layer (`/plans`)

**Free → Investor → Pro → Broker.** The tier above Free is named **Investor** deliberately — a paid tier
named for what the customer *lacks* ("Learner") reads as a label on the customer.

| Plan | For | Adds |
|---|---|---|
| **Free** | anyone with an account | Cast your chart, the daily desk note, the track record |
| **Investor** | people new to investing | The guided path, full astro reading, dividends, earnings |
| **Pro** | TA/FA-literate investors | Model fair value, running the strategy library, research library |
| **Broker** | research houses | *Not built.* Plan defined internally; **the site claims nothing** |

**"Free" means free, not open.** Since the account gate (2026-07-21) every one of these tiers,
Free included, needs a signed-in account — the research data is no longer fetchable without one.
The single exception is casting a birth chart at `/cast`, which stays open as the acquisition
funnel. And the **Broker** row is an internal plan only: the public site deliberately makes no
feature claims for it, because promising multi-seat admin, an API and white-label exports before
any of it is built dates the page and creates an expectation the desk would owe.

- **The Investor desk** (`/learn`) — 4 levels that unlock in order, 17 lessons, played **one card per
  screen** in a focused player rather than as a long scroller. Card kinds are visually unmistakable:
  lesson · watch out · the point · interactive · check yourself. Progress persists per user.
  Level 2 ("The documents") covers every document a Pakistani listed company publishes — annual report,
  the three financial statements, auditor's report, pattern of shareholding, related-party transactions,
  AGM notices, material information — with **tap-to-learn labelled statements**, a 12-document map, and a
  dividend-date timeline.
- **Rule 2 inside the teaching.** `fundamentals.json` holds revenue, net income and EPS but **not** gross
  profit, opex or finance cost. So the labelled income statement shows real reported figures **only on the
  lines the desk actually holds** (anchored to a real, named company), and every other line reads
  *"in the filing"* — teaching the reader to go find it. No statement line is ever fabricated.
- **The acquisition funnel.** Casting a chart requires **no account** (it is client-side maths over an
  ephemeris the browser already fetches). A guest casts free, the chart is held in `localStorage`, and
  `migrateGuestChart()` lifts it into their profile on sign-in — birth details are never entered twice.
  Free users see their real chart plus their strongest 3 matches; the rest sits behind one shared
  `planWall()` component with fixed, honest language.

## Principles (locked — see `CLAUDE.md`)

- **Long-only, daily timeframe.** No shorts, no leverage, no intraday scalping.
- **All numbers come from the data layer.** No agent quotes a price from memory; unknown ≠ guessed.
- **Research, never advice.** No "buy/strong buy/guaranteed" language anywhere. Losses are expected.
- **Brokers are audited, never trusted** — every broker call is scored on the leaderboard.
- **The Auditor keeps veto**; the Room only informs the strategist.

## Repo layout — one repo, two sites, two domains

Both the marketing site and the terminal live in **this single repo**. They are two *separate
Vercel projects* pointed at the same GitHub repository but different root directories, so one
`git push` can deploy either or both depending on what changed.

| surface | source | build config | domain |
|---|---|---|---|
| **Marketing site** | `site/` (Astro) | `site/vercel.json` | **henneth.app** — the root domain |
| **The terminal** | `dashboard/` + `state/` | `vercel.json` (repo root) | **desk.henneth.app** |

The root `vercel.json` copies the **whole** `dashboard/` directory plus the `state/` tree into
`public/` — that is the entire terminal build (no bundler, no framework). It used to copy a
hand-listed three files, which meant `sw.js` and `push.js` had silently never shipped and every
asset added later 404'd in production while working perfectly in local dev. The one deliberate
exclusion is `dashboard/app.html`, a stale duplicate shell that predates the sign-in gate; it is
deleted after the copy so the wholesale rule stays self-maintaining.

`site/` is a normal Astro project with its own `package.json`; its `node_modules` is gitignored,
so only ~30 source files of it are tracked.

**The marketing build is hermetic** — it never reads `state/`. Where it needs desk data, the
pipeline hands it a generated slice under `site/src/data/public/` (`tickers.json`, `context.json`,
`astro_lite.json`, `coverage.json`) plus `site/public/moon_ephem.bin`. Those are regenerated
deterministic output, so `scripts/publish.py` stages them by default alongside `state/` rather than
behind `--code`. Before that they were rewritten by every cycle and committed by none, which meant
the public astro page would have kept serving whatever sky was current the day it shipped.

**Why the split.** The terminal used to own the root domain. Marketing needs the root (that is
what people type and what a link preview shows), so the terminal moved to a subdomain. Anything
pointed at the apex expecting `/state/*.json` will now 404 — the marketing site has no `state/`.
`watchdog.py` therefore targets `desk.henneth.app` explicitly, and says so in a comment, because
a watchdog silently checking the wrong surface is worse than no watchdog.

**Naming convention** (the single source of truth is `site/src/site.config.ts`): the product is
**Henneth** everywhere public — the brand, the domain, this README. It is **Henneth Desk** only
*inside* the app, where the distinction between the company and the tool actually matters.

### Inside the terminal — a shell, not a page

`dashboard/` is vanilla: no framework, no bundler, classic `<script>` tags, and it **reads
`state/` and writes nothing**. It is still split along real seams rather than living in one file:

| layer | files | what it owns |
|---|---|---|
| shell | `shell.css`, `shell.js` | left nav, layout, routing chrome |
| top bar | `topbar.css`, `topbar.js` | search, colour scheme, plan badge, account |
| context rail | `rail.css`, `rail.js` | Ask · Notes · Watchlist · Alerts · Outline |
| board | `board.css`, `board.js` | the landing board |
| pages | `pages.css` + `pages-markets/research/tools/workspace.css` | per-section styling |
| primitives | `palette.css`, `motion.css`, `icons.css`, `icons.js`, `themes.css` | tokens, motion, glyphs |
| auth override | `auth-bridge.css` | overrides for the **generated** `auth-terminal.css` |

Two rules that are easy to break by accident:

- **`auth-terminal.css` is generated — never hand-edit it.** Overrides go in `auth-bridge.css`.
- **`body[data-theme=gemini]` is the theme root.** There is no bare `:root` palette selector.
  Dark mode layers `html[data-scheme]` *combined with* that root, in this order: light palette →
  `@media (prefers-color-scheme: dark)` scoped to `html:not([data-scheme="light"])` →
  `html[data-scheme="dark"]`. That order is what lets an explicit choice win in both directions.

The colour scheme lives in the top bar next to search (`#schemeBtn`), cycling System → Light →
Dark, so it is reachable **signed-out** too. `localStorage["deskScheme"]` is `"light"`, `"dark"`,
or absent (= follow the OS); the attribute is written on `<html>`, never on `document.body` —
`app.js` runs an enhancement `MutationObserver` on the body, and writing there would re-enter it.
For the same reason every rail pane compares before it writes.

The context rail persists across navigation, so asking a question or taking a note does not cost
you the page you were reading. Data health folded into the page-info strip instead of taking a tab.

No `vercel.json` change is needed when files are added here — the root config copies the whole
directory (see above).

## Architecture — free layer does the heavy lifting; agents only judge

```
DETERMINISTIC PYTHON (free, no tokens)                 AGENTS (tokens, right-sized model)
  data fetch  → quant/predictability/backtest            news · macro · market-analyst (commentary)
  fair value  → signals → dossiers → coverage gate        Desk Room: chartist · fundamentalist ·
  scoring     → leaderboards → QA (verify + design lint)   debate(bull+bear) · chair · librarian · verifier
  build_dashboard → preflight gate → deploy               broker-harvester · design-reviewer
```

**The efficiency engine.** A per-ticker *material hash* (valuation verdict, scorecard, new documents,
high-impact news, earnings proximity — **not** price) drives a coverage gate that tiers every ticker each
cycle: **reaffirm** (unchanged → last view stands, 0 tokens) · **delta** (price moved → cheap refresh) ·
**full** (material change or never covered → a budget-capped debate). So the whole universe stays current at a
small fraction of naive cost, and new AGM/broker/news data *targets* exactly the ticker that changed.

**Two liquidity gates, deliberately separate** (`scripts/liquidity.py` → `state/liquidity.json`).
Coverage reaches the whole KSE All Share (554 symbols), which made ~350 thin names visible, so
"is this worth analysing" and "would the desk ever trade it" became different questions:

| gate | threshold | decides | count |
|---|---|---|---|
| **research** | ≥ Rs 5M ADTV + ≥ 500 bars | what gets backtests, fundamentals, predictability | 208 |
| **signal** | ≥ Rs 30M ADTV | what can ever produce a published setup | 100 |

A name can be fully researched and still never produce a setup — the ticker page says so out loud
rather than showing an empty signal section.

**Translation is deterministic-first too.** Urdu output uses the same free-layer-does-the-heavy-lifting
shape as everything else: `scripts/translate_extract.py` hash-skips anything already translated and
hands the translator agent (Haiku, Read/Write only) a tiny batch of only the untranslated English
strings — it never opens a full state file, and if nothing changed the agent is never even spawned.
`scripts/translate_merge.py` folds the Urdu back in. Cut translation cost roughly 90%. Liquidity is measured with the published estimators, not
a turnover rule of thumb: **Amihud (2002)** price impact, **Corwin-Schultz (2012)** high-low spread
(with the overnight adjustment and per-observation zero floor), **Fong-Holden-Trzcinka (2017)** for
cost magnitude where no quote data exists, **Roll (1984)**, and **SEC Rule 22e-4** days-to-liquidate
classified at the *stressed* participation rate.

**Backtests pay a per-symbol spread, not a flat fee.** Each name is charged
`max(config floor, estimated round-trip cost)`. Lesmond, Schill & Zhou (2004) showed the stocks
producing the largest momentum returns are the same stocks that cost the most to trade — and most of
this 70-strategy library is breakout/momentum, so a constant cost assumption flatters exactly the names
it should penalise. Switching it on removed 64 of 591 previously "eligible" strategy-ticker pairs.
Those were artefacts of an unrealistic cost assumption, not edges.

**Four self-checking systems** watch different failure classes:
1. **Data QA** — flags glitchy/inconsistent numbers (e.g. a bad "-83% drop") → verifier web-checks, can block.
2. **Deploy QA** — `preflight.py` gates the build; a structurally broken cycle can never publish.
3. **Design QA** — flags corner/padding/token/typography drift → design-reviewer fixes surgically.
4. **Code QA** — two tiers: an instant free syntax gate inside `preflight.py` on *every* publish, plus a
   weekly `/code-review` deep pass (8-angle finder + verify) that fixes clear-cut correctness/security bugs
   and flags judgment calls. The repo has no tests or linter, so this is the only check on the CODE itself.

## Automation (loops)

Loops run locally (while the Claude app is open) and `push` to `main`; each push auto-deploys on Vercel.

| Loop | When | Cost | Does |
|---|---|---|---|
| Market checkpoints | weekdays 11:00 & 17:00 PKT | cheap | data + news sentinel + position monitor → push |
| Daily | weekdays 17:20 PKT | ~3 agents | macro + analyst read → push |
| Room-loop | weekdays 17:47 PKT | budget-capped debates | Desk Room debates + QA + scoring → push |
| Weekly-harvest | Sat 11:00 PKT | 1 haiku agent | broker calls (Profit/Dawn/Mettis) + filings → push |
| Code review | Sat 12:00 PKT | 1 review pass | `/code-review` on the week's diff; fixes clear-cut bugs → push |
| Product scout | Sun 12:10 PKT | 1 lean agent | ranks a product backlog. **Proposes only, never builds.** |

The Room loop is staged, not hand-orchestrated: `room_batch.py` splits the gate's plan into per-ticker
files, the persona agents **write their own output**, and `room_assemble.py` is the single writer of
`rooms.json`. Routing agent output back through the orchestrator's context was what previously capped
a batch at 3; agents writing directly cost ~10 orchestrator tokens each instead of ~800.

Every push runs the same gate (`preflight.py`) before it publishes, so a broken cycle never reaches the live site. `scripts/publish.py "<msg>"` is the one push helper all loops use.

**`publish.py` stages Desk state and generated public data only.** It used to `git add -A`, which staged the whole working tree —
and since the cloud cron and every interactive session share one checkout, a routine data refresh could
sweep up another session's half-finished edits and ship them under an unrelated commit message. Shipping
code is now a deliberate `--code` opt-in; anything left unstaged is listed, never silently included or
silently dropped. The weekly code review is the only loop that needs the flag.

## Run it locally

```bash
python scripts/serve.py           # → http://localhost:8877/dashboard/
python scripts/run_desk_cloud.py  # Desk-only free pipeline (fetch → quant → … → Desk preflight)
python scripts/preflight.py --desk # Desk deploy gate; exits non-zero if the Desk data is unsafe
```

The dashboard uses clean paths: `/today`, `/ticker/HBL`, `/legal/privacy`, and the other routes
listed in `vercel.json`. The local server maps those paths to `dashboard/index.html`, matching the
Vercel rewrites, so refreshing or sharing a deep link exercises the same shell. In-app navigation
uses the History API and browser back/forward uses `popstate`. Supabase sign-in callbacks are the
one deliberate exception: their protocol fragments (`#access_token=…`, `#error_code=…`) are handled
separately and are not dashboard routes.

Hosted on **Vercel** (private repo, auto-deploys on every `push` to `main`; `vercel.json` assembles the
static site + committed `state/` data). The refresh loops push fresh data → Vercel redeploys.

## Data & stack

- **Prices:** PSX DPS portal (EOD `[ts, close, volume, open]` — no high/low, so ATR is a close-to-close
  proxy); **Yahoo Finance `.KA`** for ~19-year adjusted history (auto de-glitched) used on charts + long-run stats.
  `fetch_history.py` reprices the **entire universe in one run** (concurrent, ~6 min for ~490 symbols), so a
  single honoured cron tick keeps every close ≤ 1 day old — refresh no longer depends on how *many* times the
  cron fires. GitHub's scheduled queue is best-effort and had degraded to 1–2 runs/day; the old design needed
  ~4 runs to finish a lap, which is how a July close reached the live site in September. `preflight.py` WARNs
  if a large share of covered symbols has not been attempted in 3 days — the shape every stale-price bug had.
- **Fundamentals:** stockanalysis.com (P/E, EPS, margins, dividends, earnings dates).
- **Sectors:** parsed from PSX's own screener (`fetch_sectors.py`), verified against 19 anchor tickers and
  kept at last-good on mismatch. This fixed two live bugs: Rule 4's same-sector limit and peer P/E, which
  had been comparing against the **whole-market** median while labelled "priced like its peers" (8 tickers
  changed verdict when corrected).
- **Indices:** `fetch_indices.py` appends KSE100/KMI30 levels daily — the index history needed to grade
  market-relative claims honestly (a stock falling 2% while the market fell 8% must not score as a hit for
  "underperforms").
- **Ephemeris:** `pymeeus`-derived sidereal positions (Lahiri ayanamsa from precessing Spica), pre-baked
  into a committed binary table for the browser. Chosen over `pyswisseph` (won't build on 3.14) and
  `skyfield` (needs a 17 MB kernel).
- **Cross-check:** `tradingview-ta` (screener=pakistan) verifies the quant layer; a mismatch blocks signals.
- **Stack:** Python 3.14 (requests/pandas/numpy) · vanilla JS SPA (History API path router, canvas charts, no framework)
  · JetBrains Mono + Pixelify Sans · **Supabase** (auth + per-user profiles/watchlist/plan) · **Vercel** hosting.

## Entitlements & security posture

Billing is **not wired**. Card processing through international providers is unavailable in Pakistan, so
payment will run through a local gateway (PayFast or similar) later. Until then plans are set manually and
the product says so on `/plans` rather than showing a dead checkout.

- **`BILLING_LIVE = false` is the single switch.** While false, any signed-in account reads as subscribed,
  so shipping paywalls could not strip access from accounts that already had it. Flipping it moves access
  entirely onto the plan's feature list.
- **A user cannot promote their own plan.** `profiles.plan` is guarded at the database by a CHECK
  constraint plus two triggers: a `BEFORE UPDATE` trigger reverts `plan`/`plan_since` for role
  `authenticated`, and a `BEFORE INSERT` trigger forces `plan='free'`. **The INSERT trigger is
  load-bearing** — the client writes profiles via `upsert`, so an UPDATE-only guard would have left a
  crafted insert able to self-grant `pro`. This was caught and closed during the build. Plan changes are a
  service-role-only path.
- `ui_mode` (which desk shell you see) is deliberately client-writable — it is a view preference, not an
  entitlement.
- **Owner preview.** `/plans` carries an owner-only "preview as plan" switch that re-renders the whole
  product as any tier without changing the stored plan (in-memory; a reload resets it).
- Per-user rows (watchlist, notes, birth data, learn progress) are RLS-scoped to their owner.
- **The research layer requires an account (2026-07-21).** It is shared and read-only *to signed-in
  users* — not to the public. Until this date the sign-in screen gated the interface but not the
  data: every file under `/state/` was a plain static asset, so `curl .../state/backtests.json`
  returned 4.7 MB to anyone. The whole product — Room debates, dossiers, fair values, claims,
  strategy map — was one `wget` away.

  `middleware.js` at the repo root closes it. Vercel Edge Middleware on `/state/:path*` verifies
  the Supabase access token before the CDN serves anything. Verification is a local Web Crypto
  check against Supabase's published **ES256** JWKS, so there is no shared secret to store and no
  auth round trip per request; if the project is ever moved back to legacy HS256 keys, `alg` stops
  matching and every request fails **closed**.

  **One deliberate exception:** `natal_ephem.bin` / `.json` stay public. `/cast` is the top of the
  acquisition funnel, and those two files are an astronomical ephemeris — public-domain physics
  anyone can compute, containing zero desk output.

  Tested against 12 forgeries including `alg:none`, HS256 alg-confusion, expired tokens and a
  self-signed token carrying the real `kid`. Full reasoning in `docs/OPERATIONS.md` §9b.
  **Regression check — this must stay 401 forever:**
  `curl -s -o /dev/null -w "%{http_code}" https://desk.henneth.app/state/rooms.json`
- **Bot protection is live (2026-07-21).** Cloudflare Turnstile on signup, sign-in and password
  reset — the last one included because it sends mail, so it is the same spam vector. Without it a
  bot could POST thousands of addresses at signup, each triggering a confirmation email, burning
  the Supabase quota and getting the sending domain flagged as a spam source, which then silently
  kills delivery to real users. Verified server-side: a signup with no token returns
  `400 captcha_failed`. The site key is public and lives in `app.js`; the secret exists only in the
  Supabase dashboard.
- **Password floor is 10 characters**, enforced server-side (Supabase) and mirrored client-side.
  Length rather than composition rules, per NIST SP 800-63B — forcing a symbol and a digit
  reliably produces `P@ssw0rd1`, while length is what actually resists cracking.
- **Google sign-in was removed (2026-07-21, owner)** — email and password only. Worth knowing if it
  returns: Supabase's captcha does **not** apply to the OAuth redirect flow, so a Google button is
  an unprotected path to account creation.

### Known gaps, stated for audit

- **`state/legal.json` is `review_status: DRAFT`.** Terms/Privacy/Risk are drafted but **not reviewed by a
  Pakistani lawyer**. This is a hard gate before charging anyone.
- **Supabase key hygiene — DONE (verified 2026-07-21).** JWT-based legacy keys are disabled: the
  legacy `anon` key is rejected at the API gateway (401), and legacy `anon`/`service_role` are
  disabled as a pair. The client uses the publishable key, which is safe to ship. Any future
  server-side job needs a new-style `sb_secret_...` key, never the old service_role JWT.
- **Leaked-password protection is OFF and cannot be switched on — it is a Pro-plan feature and the
  org is on Free.** Not an oversight. The mitigation is the 10-character floor above, which blocks
  the entire bottom tier of guessable passwords that HaveIBeenPwned would otherwise catch. Revisit
  only if the project moves to Pro for other reasons.
- **The track record is young.** **547 dated claims are filed; 121 have resolved** (70 miss, 51 hit)
  **and 426 are still pending** (verified against `state/claims.json`, updated 2026-08-11) — early
  numbers, not a proven record, and the product displays the real counts rather than implying
  otherwise.
- **The Broker plan is defined, not built.** No leaderboard API, white-label, or broker-side scoring exists.
- **The astrology layer has no demonstrated edge** (see above). It is excluded from signal confluence and
  never feeds a setup.
- The repo has **no test suite or linter**; correctness rests on `preflight.py`, `room_verify.py`,
  `design_lint.py`, and the weekly `/code-review` pass.

## Governance (the desk can't quietly disagree with itself)
`CLAUDE.md` is enforced, not aspirational: one **position-sizing formula** (risk by stop distance,
capped at 8% position value — Strategist and Auditor compute it identically), a **circuit breaker**
that won't auto-resume into a bad regime, **stale-position time-stops**, **immutable live strategy
files** (edits create a new version + fresh backtest), an explicit **no-lookahead** rule the Auditor
can veto on, a fixed **news impact 1–5 scale**, and a **calendar-freshness guard** (`data_health.py`
degrades if session times go 60 days unverified, halting new signals). The **Auditor keeps veto**.

## Docs
- [`AGENTS.md`](AGENTS.md) — **entry point for any agent or harness** (Codex, Claude Code, anything else). Harness-neutral brief: what the desk is, what to read in which order, the non-negotiables restated for tools that do not auto-load `CLAUDE.md`.
- [`CLAUDE.md`](CLAUDE.md) — the desk rules every agent obeys.
- [`docs/GOTCHAS.md`](docs/GOTCHAS.md) — the sharp edges: traps that have already cost debugging time (the `/state/*` auth gate that makes curl verification impossible, the CSS at-rule comment trap, cp1252 encoding, frozen dashboard breakpoints).
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — **operations runbook**: the hybrid cloud/app model, the one publish path, safety gates, and how to run every flow without breaking live. Read this first when operating the desk.
- [`docs/SYSTEM-REGISTRY.md`](docs/SYSTEM-REGISTRY.md) — index of every agent, loop, script, and state file.
- [`docs/DESK-ROOM-PLAN.md`](docs/DESK-ROOM-PLAN.md) — the multi-agent analyst design.
- [`docs/AUTOMATION-PLAN.md`](docs/AUTOMATION-PLAN.md) — the whole-product loop map.
- [`docs/PRODUCT-ROADMAP.md`](docs/PRODUCT-ROADMAP.md) — single-tenant → subscription product (auth, delivery, billing, compliance).
- [`docs/SEO_PLAN.md`](docs/SEO_PLAN.md) — the only user-acquisition channel (zero paid spend, by decision): verified SERP constraints, content routine, and the backlink/outreach plan.
- [`CHANGELOG.md`](CHANGELOG.md) — what changed and why.

---
*Educational and informational research only — not personalized investment advice. Past performance does
not guarantee future results. Investing in PSX carries risk, including the possible loss of capital.*
