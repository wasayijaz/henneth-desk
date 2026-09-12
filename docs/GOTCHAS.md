# Henneth — Gotchas & Conventions

Things that cost real debugging time at least once. Every entry is a trap that looks fine until it
isn't. Read before touching the area named in the heading.

Governance rules live in [`CLAUDE.md`](../CLAUDE.md). Operations (who runs what, where, the publish
path) live in [`OPERATIONS.md`](OPERATIONS.md). This file is the third layer: *the sharp edges*.

---

## Verifying a deploy

**`/state/*` is auth-gated. You cannot verify a state-file push with unauthenticated curl.**
`middleware.js` (matcher `/state/:path*`) verifies Supabase ES256 JWTs and fails closed.
The only exceptions are `PUBLIC_FILES = {natal_ephem.bin, natal_ephem.json, public_probe.json}`.
Everything else returns 401 to a client without a session.

Consequence: a polling loop like `until curl -s .../state/changelog.json | grep -q vX; do sleep 10; done`
can never succeed. It will run forever. Verify instead via the Vercel deployments API — match
`githubCommitSha` against your commit, and require `state: "READY"` and `target: "production"`.

**A signed-out live page emits ~50 console 401s from `/state/*`.** That is the gate working. Not a bug.

**`vercel.json` sets `cleanUrls: true`.** `GET /index.html` returns a 15-byte `Redirecting...` stub,
not the page. Grep against `/`, or use `curl -L`.

## CSS in `dashboard/auth-terminal.css`

**A comment before an at-rule silently kills the rest of the stylesheet.**
`.hn-auth /* note */ .foo{}` is valid — a comment counts as whitespace, so it parses as a descendant
combinator. The same shape in front of `@media` is fatal, and fails quietly: no console error, the
remaining rules just stop existing.

Verify after any comment edit by reading `document.styleSheets[i].cssRules.length` in the browser.
Current count: **303**.

**Centered flex is not linear.** `.left` is `display:flex; align-items:center`. Adding N px of margin
to a child does not move it N px — in one measured case 8px of `.sub` margin moved the sign-in button
11px. Tune empirically and re-measure after every change. Do not compute the delta and trust it.

**Desktop base proportions are frozen** to the owner-endorsed reference. Every anti-scroll trim lives
in `@media (min-width:881px) and (max-height:820px)`, never in base rules. Breakpoints:

| Query | Effect |
|---|---|
| `max-width: 880px` | mobile — hides `.right` (animation panel) and `.nav-right` |
| `max-width: 560px` | also hides `.legal` |
| `min-width:881px and max-height:820px` | desktop short-viewport trim (the no-scroll fix) |

**The file covers three surfaces**, not one: the sign-in / create-account terminal, the post-login
onboarding flow, and the first-view "today" panel. All rules are scoped `.hn-auth …`.

**Its generator is stale.** `scratchpad/gen_auth_css.py` produced the first version out of
`henneth-login-terminal-wake6-v4.html`. The file has been hand-maintained since. Re-running the
generator would silently revert the mobile block, the short-viewport block, and the onboarding styles.
Do not re-run it.

## `dashboard/auth-terminal.js`

Mountable IIFE exposing `window.HennethAuthTerminal` (`mount(tab)`, `unmount`, …). Markup lives in the
`HN_MARKUP` template literal starting around line 14.

`switchTab` is **not** on the live build's exposed object. To drive tabs from a browser probe, click
the `.tab` element instead of calling the API.

`data-gated="1"` on `<body>` strips the desk sidebar and topbar while gated. That is why the logo
lives inside the auth terminal's own `.nav` rather than the shared topbar.

## Browser automation probes

- `javascript_tool` rejects top-level `await`. Wrap probes in `(async()=>{ … })()`.
- Never call `location.reload()` inside a probe — it kills the inspected target mid-execution
  ("Inspected target navigated or closed"). Reload and measure in two separate calls.
- Screenshots at mobile viewport render at devicePixelRatio scaling and can *look* horizontally
  cropped when nothing overflows. Trust `documentElement.scrollWidth` vs `clientWidth`, not the image.

## Concept D marketing homepage

The shared marketing canvas is `--maxw: 1180px`. Below the homepage hero, direct post-hero chapters
use 24 px desktop/tablet and 18 px mobile gutters while their section backgrounds remain full width.
Do not target arbitrary inline values such as `[style*="44px"]` to create those gutters: that also
matches visualization heights, offsets and SVG transform origins. Target direct padded `.hn-rv`
chapters instead.

`Header.astro` owns navigation on every marketing route, and `Base.astro` mounts the same shared glass
bar on the homepage and every interior page. The mobile drawer breakpoint is 760 px, while compact
post-hero rails start at 920 px and reach
their smallest cards at 620 px. Keep the fixed drawer overlay as a sibling outside the transformed or
filtered header so it can cover and blur the full viewport.

The Astro markup's `data-*` hooks and the selectors in `home-concept-d-posthero.ts` are one
interface; changing either side without the other silently disables a chapter. Do not rearrange
chapters with CSS `order`: source/DOM order must match visual order so keyboard and assistive
technology encounter the same sequence. The two WebGL fields use a 120 px visibility margin and cap
DPR at 1.5. Verify `prefers-reduced-motion` and `scripting: none` before release. The hero video
remains enabled at 620 px and below; keep it muted and `playsinline`, and preserve readable foreground
content because mobile autoplay may still be refused. Illustrative ticker, case and scorecard panels
must retain a persistent sample label; do not reintroduce dates or returns that could be mistaken for
a live record.

## Windows / encoding

The console is cp1252. Any script that reads or prints state JSON containing Urdu or em-dashes will
crash with `UnicodeDecodeError` / `UnicodeEncodeError` unless it uses
`io.open(path, encoding='utf-8')` for reads and `json.dumps(..., ensure_ascii=True)` for prints.

## Publishing

`scripts/publish.py --code` ships **only files already staged in git**. It never runs `git add -A`.
Unstaged hand-authored files are left behind on purpose — they may belong to a concurrent session.
That is correct behaviour, not a failure.

Preflight emits a standing benign WARN: newly-added universe tickers still backfilling history
(103 at last count). It never gates publish.

## The ~103 permanently-empty board counters

The KSE All Share constituent list carries PSX board artifacts that are **not companies** — `…NC`
(non-compliant), `…XD` (ex-dividend), `…XB` (ex-bonus), and rights counters. DPS returns zero bars
for them forever. They never gain a `state/history/{SYM}.json`, so they never leave
`fetch_history._pick()`'s never-fetched set, and they are excluded from `coverage.json` (so the
dashboard does not surface them and `data_health.py` does not count them as missing history).

This is inert as long as they stay off the refresh budget. It was **not** inert once: their count
used to be subtracted from `LISTED_PER_RUN`, driving the rotation slice to `max(0, 90 - 103) = 0`.
No listed symbol with an existing series was refreshed on any run for 47 sessions, and
`health.json` stayed green throughout because its freshness test was a `max()` over all symbols.
That is how a July close reached the live site in September.

**Trigger to revisit:** the full-universe sweep now attempts ~every covered symbol every run, so
`attempted` near the whole universe is normal, not a warning sign. Revisit only if wall time creeps
toward the 25-minute Actions cap (persistent non-zero `skipped_deadline`) — raise `WORKERS` a little
or move the never-fetched probe to a separate weekly job before widening anything else.

## File mtimes are meaningless in the cloud

`actions/checkout` writes the entire repo fresh at the start of every workflow run, in git index
order — **alphabetical**. Every `state/` file therefore has an mtime that says nothing about when
its contents were produced, and mtime *ordering* degenerates to alphabetical ordering.

This cost a second month of stale prices. After the board-counter starvation above was fixed, the
long-tail rotation still ordered its queue by `st_mtime` ("stalest first"). In the cloud that meant
"alphabetically first", so the same 90 symbols were repriced on every run forever and everything
past roughly the letter H — TATM among them — was never reached at all. Locally the ordering looked
fine, because a local checkout preserves the mtimes of files you didn't touch.

**Rule:** any clock that must survive a run is persisted state, committed with `state/`. The refresh
clock is `state/history_meta.json` `last_attempt`. `preflight.py` WARNs when a large share
of covered symbols has not been attempted in 3 days, which is the shape all three stale-price bugs had.

The post-close gate also requires `history_meta.json` to describe a finalized refresh, not merely carry
a recent `completed_at`: `processed` must equal `attempted`, `ok` plus the finalized `failed` list must
account for every processed symbol, `skipped_deadline` must be zero, and `with_history` must match
`coverage.json`. Completion and capture timestamps must include an explicit timezone offset; naive
timestamps are invalid and are never interpreted as PKT.

## The cron is a wish, not a schedule

The third and deepest stale-price bug. `desk-data.yml` **declares** ~18 runs a weekday
(`"7,37 3-11 * * 1-5"`). GitHub's scheduled-workflow queue is best-effort and load-sheds ticks under
load: since 2026-08-27 the schedule actually fired **1–2 times a day**, not 18. Any refresh design
that needs several runs to cover the universe — as the old least-recently-attempted rotation did
(`LISTED_PER_RUN` symbols per run, ~4 runs to sweep the tail) — simply never completes when only one
run honours per day. 263 of 456 symbols drifted weeks stale while `health.json` stayed green, because
the rotation was "working" — it just wasn't being run often enough to finish a lap.

**Rule:** never depend on how MANY times the cron fires. `fetch_history.py` now reprices the ENTIRE
universe in a SINGLE run — concurrently, with a `ThreadPoolExecutor` (`WORKERS`), ~6 minutes for
~490 symbols, well inside the 25-minute job cap. One honoured tick a day keeps every price ≤1 day
old. `DEADLINE_S` bounds the wall clock as a guard; result intake stops with a bounded drain
allowance for the at-most-six requests already in flight. Symbols not reached before it are left unstamped
so they lead the next run, and `preflight.py` WARNs on any non-zero `skipped_deadline`. `last_attempt`
survives only as the ORDERING key for that rare cut-short case — it is no longer a rotation ration.
Do not reintroduce a per-run slice; it silently reinstates this bug the moment the cron degrades.

`CHANGELOG.md` uses CalVer: `## YYYY-MM-DD — vYYYY.MM.DD — Title`, with `.2` / `.3` suffixes for extra
same-day releases. `scripts/build_changelog.py` extracts **only** the `<!--public … -->` blocks into
`state/changelog.json` and fails closed — an entry with no public block publishes nothing. That is
intended for internal-only changes.

## Secrets

`config/desk.json` must **never** be served. It holds `capital_pkr` (the owner's actual trading
capital) and the Telegram bot token.

## Known open threads

- `GROQ_API_KEY` is missing on the Vercel deployment — Ask-the-desk returns
  "Chat isn't configured yet — GROQ_API_KEY is missing on the deployment."
- `/cast` (cast a birth chart without an account) is the deliberate signed-out acquisition entry
  point. Do not add it to the members-only route list or remove the public ephemeris exception.
- Proposed, not built: a `desk_profile` jsonb column on the Supabase `profiles` table for
  cross-device onboarding persistence.
