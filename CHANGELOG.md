# Henneth — Changelog

Newest first. Every entry = what changed, why, and (for bugs) how it's prevented from recurring.
The desk is a **live website** — nothing ships unless `python scripts/preflight.py` exits 0.

## How to write an entry

**Heading:** `## YYYY-MM-DD — vYYYY.MM.DD — Short title`

Versions are **CalVer**: the release date, plus `.2`, `.3`… for a second release the same day.
Chosen over semver because releases here are date-driven, and because the version should answer
the question a reader actually has — *how current is my desk?* — which `v1.14.2` does not.

**This file is the ENGINEERING record and stays that way.** It names migrations, internals and, in
at least one entry, a security hole that was found and closed. None of that goes in front of a
subscriber.

What subscribers see comes from a `public` block you add per release:

```
## 2026-07-22 — v2026.07.22 — Mobile tables

<!--public
Tables fit your phone screen now instead of scrolling sideways.
A free position-size calculator is on the website.
-->

### Everything else — the engineering detail, unpublished.
```

`scripts/build_changelog.py` extracts only those blocks into `state/changelog.json`, which the
terminal reads to show the version and a "what's new" note. It **fails closed**: no block means
nothing is published for that release. Forgetting the marker costs a shrug; an opt-out design
would leak an internal detail the first time someone forgot. It also refuses to build if a public
note contains an obviously internal term.

Write the public lines for a user: what they can now do, or what stopped being annoying. Not
which file changed.

---

## 2026-09-25 — v2026.09.25 — Ask the desk answers again

<!--public
Ask the desk answers everyday questions again, on its own page and in the side panel. Ask about the
market, a sector, or a stock by ticker or company name. A simple "hi" gets an instant reply, and if
the assistant is busy it tells you how many seconds to wait instead of failing.
-->

### What was wrong

Ask-the-desk (`api/ask.js`) failed on most questions, in the `/ask` page and the context rail alike.
Three causes, stacked:

1. **Context too big for the budget.** Groq's free tier allows 8K tokens per minute per model,
   shared org-wide. The context sent per question was large enough that one or two questions spent
   the whole minute, so most requests came back 429.
2. **The fact-check rejected correct answers.** `validateAnswer` rejects the whole answer on any
   figure not present in the slice. It compared signed values, so "down 1.2%" against a stored
   `-1.2` failed, and it treated label numbers (KSE-100, KMI-30, RSI14) as figures to verify.
3. **Greetings went to the model.** "Hi" spent a data fetch and a model call, then usually failed
   the gate because there was nothing to ground.

### What changed

- `buildContext` builds one small slice per question, a **ticker** slice (matched by ticker or
  company name), a **sector** slice, or a **market** slice, roughly 0.2–1.8K tokens. It fetches 17
  light state files with the caller's token (adds `indices`, `macro`, `daily_read`, `health`).
- Model `openai/gpt-oss-120b` at low reasoning effort, 1,200-token completion budget. On a 429 it
  retries once on `openai/gpt-oss-20b` (a separate per-model limit). If both are limited it returns
  429 `provider_busy` with Groq's `retry_after`, and `askFriendlyError` in `dashboard/app.js` shows
  the wait in seconds.
- Greetings and "what can you do" get a fixed local reply. No fetch, no model call.
- `validateAnswer` compares figures as magnitudes (the sign is prose), accepts million/billion
  renderings, and exempts label numbers. It still rejects any ungrounded figure or date, advice
  phrase, URL or prompt leak. Rule 2 stays enforced by the gate, not only by the prompt.

### Decision

The owner has chosen to stay on Groq's free tier. A 429 problem is fixed by shrinking context, not
by upgrading the plan. Recorded in `docs/GOTCHAS.md`.

### Prevention

`scripts/check_root_ask_hardening.mjs` (38 assertions, Groq mocked) covers the slice routing, the
fallback model, the busy response and the magnitude/label rules. `check_root_ask_ui.mjs` covers the
thread's busy state and retry control.

---

## 2026-09-07 — v2026.09.07 — Prices stay current: whole-universe refresh

<!--public
Prices across the whole desk now stay current — every close is refreshed daily, not just a rotating
handful. If you saw a stock stuck on an old price, that's fixed: the desk reprices its entire universe
on every update.
-->

### What changed

Three stacked bugs had let 263 of 456 symbols drift weeks stale while `health.json` stayed green — a
July close was still live in September. All three shared the same shape: a refresh design that needed
the cron to fire *many* times to finish one lap.

1. **Board-counter starvation.** ~103 KSE All Share entries are PSX board artifacts (`…NC`, `…XD`,
   `…XB`, rights counters), not companies; DPS returns zero bars for them forever. Their count was
   subtracted from the per-run rotation slice, driving it to `max(0, 90 − 103) = 0` — no listed symbol
   with an existing series was refreshed for 47 sessions.
2. **mtime ordering in the cloud.** `actions/checkout` rewrites the repo alphabetically each run, so the
   "stalest first" queue ordered by `st_mtime` degenerated to alphabetical — everything past ~letter H
   (TATM among them) was never reached. The refresh clock now lives in persisted state
   (`state/history_meta.json` `last_attempt`), committed with `state/`, not in file mtimes.
3. **The cron is a wish.** `desk-data.yml` declares ~18 runs/weekday but GitHub load-sheds scheduled
   ticks; since 2026-08-27 it fired 1–2/day. Any design needing several runs per lap never completes.

**Fix:** `fetch_history.py` now reprices the ENTIRE universe in a SINGLE run — concurrently via a
`ThreadPoolExecutor` (`WORKERS`), ~6 min for ~490 symbols, well inside the 25-min Actions cap. One
honoured tick a day keeps every price ≤ 1 day old. `DEADLINE_S` bounds wall time as a guard; symbols
not reached lead the next run, and `preflight.py` WARNs on any non-zero `skipped_deadline` or on a large
share of covered symbols not attempted in 3 days — a check that would have caught all three bugs. The
per-run slice (`LISTED_PER_RUN`) is gone; do not reintroduce it — it silently reinstates this bug the
moment the cron degrades. Full detail in [`docs/GOTCHAS.md`](docs/GOTCHAS.md).

---

## 2026-08-18 — v2026.08.18 — Desk clean URLs

<!--public
Desk links are now clean paths such as `/today`, `/watchlist`, and `/ticker/HBL`, so shared links
open directly and remain reliable after refresh. Existing old links are upgraded automatically.
-->

### What changed

The dashboard now uses the History API and path-based dispatch instead of hash navigation. Vercel
routes clean dashboard paths back to the shell, while `/state/*` authentication, signed-out open
routes, OAuth callback fragments, extension links, email links, and browser back/forward behavior
remain unchanged. The marketing site was already path-based; its links into the desk now use the
same clean paths.

---

## 2026-08-17 — v2026.08.17 — Ask the Desk: model swap + truncation/markdown fix

<!--public
Ask the Desk stopped cutting off mid-answer, and replies now render as real headings and bullet
lists instead of showing literal asterisks. Earlier the same day, a Groq model retirement had
started silently breaking every Ask the Desk answer — that's fixed too.
-->

### What changed

**1. Retired-model outage.** Groq retired `llama-3.3-70b-versatile` on 2026-08-16, which broke every
Ask the Desk call with no visible warning beyond an API error. `api/ask.js` now points `GROQ_MODEL`
at `openai/gpt-oss-120b`. One line (`f72c4f43`).

**2. Mid-answer truncation.** `max_tokens` in the same file was `500`, tight enough that longer
answers cut off before the thought finished. Raised to `1000`.

**3. Literal `**markdown**` instead of structure.** The model's replies followed the prompt's
`**Bold Label**` / `- ` bullet convention, but the dashboard printed that convention as raw
asterisks and dashes rather than rendering it. `dashboard/app.js` gained `mdLite()`/`inlineMd()` to
turn the same convention into real `<h4>`/`<ul>`/`<strong>` markup; `dashboard/themes.css` tunes the
resulting heading/bold weight onto `--ink1` (darker) while body text stays `--ink2`, so the new
structure reads as hierarchy rather than just heavier text. (`f19ae352`)

---

## 2026-08-16 — v2026.08.16 — Desk UI overhaul: app shell, context rail, dark theme

<!--public
The desk got a proper rebuild. There's a permanent app shell now — a left nav that remembers where
you were, a top bar with search, and a page-info strip that always tells you which page you're on
and how fresh the data is.

A new panel on the right stays with you across pages: ask a question, keep notes, watch tickers,
see your alerts, and read the day's news — without losing the page you were reading. The news pane
lists today's PSX headlines from Profit, Dawn and the rest, each linking out to the full article,
stamped with when it was last refreshed.

Dark mode. The light/dark control sits next to the search box in the top bar, one click, and it
follows your system setting until you tell it otherwise. Your choice is remembered on this device.

The live index ticker now runs edge to edge across the whole desk, passing behind the two side
panels and blurring softly as it goes.
-->

### What changed

**1. The dashboard was one file. Now it is a shell plus modules.** `dashboard/index.html` +
`app.js` carried the whole desk. Eighteen new files split it along real seams:

| Area | Files |
| --- | --- |
| App shell (nav, layout, routing chrome) | `shell.css`, `shell.js` |
| Top bar (search, scheme, plan, account) | `topbar.css`, `topbar.js` |
| Right context rail | `rail.css`, `rail.js` |
| Board page | `board.css`, `board.js` |
| Page styles per section | `pages.css`, `pages-markets.css`, `pages-research.css`, `pages-tools.css`, `pages-workspace.css` |
| Design primitives | `palette.css`, `motion.css`, `icons.css`, `icons.js` |
| Auth surface override | `auth-bridge.css` |

`auth-bridge.css` exists because `auth-terminal.css` is generated and must never be hand-edited —
all auth-surface overrides land in the bridge file instead.

**No deploy-config change was needed.** Root `vercel.json` copies the whole `dashboard/` directory
into `public/`, so new files ship automatically. The one deliberate exclusion (`dashboard/app.html`,
a stale duplicate shell, deleted after the copy) is unchanged.

**2. Right context rail — five tabs, persistent across navigation.** `rail.js` renders Ask, Notes,
Watchlist, Alerts and News. Data Health folded into the persistent page-info strip rather than
occupying a tab of its own; the old "Related" pane was deleted outright — Watchlist replaces it
(per the repo rule against keeping a superseded path alive alongside its replacement).

The fifth tab started as an Outline pane (a table of contents for the current page) and was replaced
by News before release — an outline of a page you are already looking at carries almost no
information, whereas the news the desk already scrapes had no persistent home. It reads the existing
news state, lists the day's articles with outbound links, and carries a last-refreshed stamp. The
Outline path was removed rather than left behind a flag.

Every pane writes through a compare-before-write guard (`setWatchHTML`, `setAlertsHTML`,
`setOutlineHTML`, `lastNotesHTML`). This is not an optimisation. `app.js` runs an enhancement
`MutationObserver` on `document.body`; an unconditional `innerHTML =` re-entered that observer on
every 30-second refresh and made the rail flicker. Writing only on change breaks the loop at the
source.

**3. Colour scheme moved out of the account menu and into the top bar.** It previously lived inside
`renderAccountButton()`'s signed-in branch — two clicks deep behind the avatar, and completely
absent for signed-out visitors, who see the auth terminal and had no way to change it at all. It is
now `#schemeBtn` in `index.html`, sitting between the search button and the language chip, cycling
System → Light → Dark and stating both current and next state in its `title`/`aria-label`.

The account-menu control was **removed**, not kept as a second path to the same setting.

Scheme contract: `localStorage["deskScheme"]` is `"light"`, `"dark"`, or **absent** (= follow OS).
`applyDeskScheme()` writes `data-scheme` on `<html>`, never on `document.body` — writing it on the
body would trip the enhancement observer above. A guard script at `index.html:21` applies the stored
value before first paint so there is no light flash on a dark-mode load.

**4. Two-scheme cascade.** `body[data-theme=gemini]` is the theme root; there is no bare `:root`
palette selector in this codebase. Order is: complete light palette on the theme root → then
`@media (prefers-color-scheme: dark) { html:not([data-scheme="light"]) body[data-theme=gemini] {…} }`
→ then `html[data-scheme="dark"] body[data-theme=gemini] {…}`. That order is what makes an explicit
user choice win in *both* directions; reversing the last two blocks would leave a user who picks
Light on a dark-mode OS stuck in dark.

Alias tokens (`--bg`, `--panel`, `--ink1/2/3`, `--line`, `--surf`, `--hair`, `--up`, `--dn`,
`--accent`) are `var()` indirections defined once in the light block, so they follow the scheme with
no per-scheme duplication. Boot-screen tokens are deliberately scheme-*invariant* — the boot screen
paints before any scheme decision is knowable.

`icons.css` uses `mask-image` + `background-color: currentColor`, so glyphs inherit text colour and
are scheme-correct for free.

**5. Two IACVT bugs found and fixed.** `color: var(--undefined-token)` does not fall back — it
computes to `unset` and the whole declaration silently vanishes (CSS "invalid at computed-value
time"). Two such references existed and produced text that was invisible in one scheme only, which
is exactly the failure mode that survives a light-mode-only review. Both fixed; the verification
pass confirms zero undefined `var()` references remain.

**6. Hard-corner law preserved.** `themes.css:5` sets a global `border-radius: 0 !important`. None
of the new files reintroduce a radius.

**7. The workspace is one continuous canvas; the side panels float on it.** `.shell` previously
painted `--paper` behind everything, which read as an outline colour framing the two side panels.
It now paints `--paper-3` — the same value the centre column uses — so the canvas runs unbroken from
edge to edge and the panels sit *on* it rather than being cut out of it.

**8. The global index tape is full-bleed and runs behind the panels.** `#gstripHost` used to live
inside `.main-col`, which is `overflow: auto` and clipped to grid column 2 — so no negative-margin
trick could ever widen it past the centre column. The fix is structural, not cosmetic: the host is
now a direct child of `.shell` (still outside `#view`, so a page render never re-creates it and the
marquee never snaps back to the start), taken out of grid flow with `position: absolute` under a new
`--tape: 31px` token, with `.main-col` reserving that height as top padding so the first card cannot
slide under it.

Both panels became glass — `color-mix(in srgb, var(--rpanel) 86%, transparent)` plus
`backdrop-filter: blur(12px) saturate(1.4)` — because an opaque panel would simply chop the tape off
at the column edge. The tape stays visible as it travels behind each panel and reads out of focus,
which is what makes the band feel continuous across the whole workspace. `--rpanel` still supplies
the tint, so light and dark need no separate values.

Stacking order is deliberate and minimal: tape at `z-index: 1`, panels at `z-index: 2`, and
`.main-col` given **no** `position`/`z-index` at all. Giving the column a stacking context would
have trapped every sticky or modal descendant underneath the panels; `z-index: 1` on the tape
already beats the column's `z-index: auto` content in the root stacking context. `pointer-events` is
off on the host and back on for `.gstrip` itself, so the hover-pause and the click through to
`#/macro` still work while the transparent gutter beside the strip does not eat clicks meant for the
column underneath.

**9. The `HENNETH DESK` lockup.** `.nav-brand` is a flex row (`img` · `HENNETH` · `<small>DESK</small>`),
so the gap between the two words is the flex `gap`, **not** a text space — and the markup was
carrying an `&nbsp;` *on top of* the 8px gap, double-spacing it. The `&nbsp;` is gone and one value
owns the spacing: `.hn-auth .nav-brand { gap: .5em }` in `auth-bridge.css` (never in the generated
`auth-terminal.css`). Against the `.06em` tracking that reads as a word break without splitting the
lockup into two separate words.

**10. Urdu coverage extended to the new surfaces.** `translateTree()` swaps text nodes by exact
dictionary hit, so a brand-new file is translated only if its strings are already in
`dashboard/i18n-ur.js` — a miss is silent and simply leaves English on screen. The new rail tabs and
Board tile headers were exactly that kind of silent miss, and `board.js` emitted `"News Wire"`
against a `"News wire"` key (matching is case-sensitive). Keys added, casing reconciled at the
emitter, and the Nastaliq selector list at `themes.css:1089` extended to the new prose-bearing
classes — Urdu was otherwise falling back to JetBrains Mono, a Latin monospace that does not shape
the script. Numeric cells are deliberately excluded from Nastaliq and added instead to the existing
`direction: ltr; unicode-bidi: isolate` rule, so digits do not reorder under RTL.

### Verification

The scheme control was exercised by scripted clicks rather than asserted: three clicks walked
System → Light → Dark → System, with `data-scheme` on `<html>`, the `localStorage` value, and the
computed `body` background agreeing at each step — including the key being *removed* (not set to
`"system"`) on the third click. Console clean, zero errors.

The full-bleed tape was measured, not eyeballed: `#gstripHost` spans `0 → 1269.6px` against a shell
width of `1269.6px` at `top: 58px` (the topbar height), height `31.6px`; it overlaps the sidebar,
which sits above it at `z-index: 2` with `blur(12px) saturate(1.4)` computed on both panels;
`.main-col` reserves `43px` of top padding; the marquee animation is still running
(`marquee 60s`); and `window.__shellFail` is `null`. The brand gap measures `7.5px` — the single
`.5em` value, with no residual `&nbsp;`.

An earlier probe read as a total failure (zero-height host, null strip, no padding) purely because
the page was signed out: the auth terminal was mounted and `body[data-strip=off]` had legitimately
collapsed the band. Worth recording, because the same false alarm will recur for anyone verifying
this signed out.

## 2026-08-15 — v2026.08.15.3 — Auth nav: dead language chip removed, Back to site points at the marketing site

<!--public
The "EN / اردو" button on the sign in screen is gone — it never did anything — and "← Back to site"
now actually takes you back to henneth.app.
-->

### What changed

**1. The language chip was decoration.** `HN_MARKUP` in `dashboard/auth-terminal.js` rendered
`<button class="nav-chip lang">EN / اردو</button>`, but nothing in the file (or anywhere else) bound a
listener to `.lang`. Clicking it did nothing. The desk's real language toggle lives in the signed-in
topbar (`.lang-btn` in `themes.css`, driven by `i18n-ur.js`) and is untouched — those selectors were
checked before deleting, so the removal is scoped to the auth surface only.

Removed with it: the `.hn-auth .nav-chip.lang` rule and its `:hover` in `auth-terminal.css`, plus the
`.lang` fragment of the shared `:focus-visible` ring. The rest of that ring (`.nav-back`, `.odo-btn`,
tabs, inputs, `.switch-link`, `.module`) is unchanged — keyboard focus is still visible everywhere.

Why delete rather than wire it up: the auth terminal is three fields and a button. Urdu on the login
form buys nothing an Urdu speaker needs before they have an account, and a control that lies about
what it does is worse than no control.

**2. `← Back to site` was `href="#"`.** It swallowed the click and left the visitor on the login page.
Now `https://henneth.app/` — absolute, because the auth terminal is served from `desk.henneth.app` and
a relative path would loop back into the desk.

## 2026-08-15 — v2026.08.15.2 — auth-terminal.css: stale generator header removed

No behaviour change. `dashboard/auth-terminal.css` still carried a "Do not hand-edit — generated by
scratchpad/gen_auth_css.py" banner from when it was first generated out of
`henneth-login-terminal-wake6-v4.html`. That stopped being true many releases ago: the file has been
hand-maintained since, the generator is stale, and re-running it would silently revert the mobile
block, the short-viewport block and the onboarding styles.

The header now says what is actually true — hand-maintained, generator stale, do not re-run — and
documents that the file covers three surfaces, not one: the sign-in / create-account terminal, the
post-login onboarding flow, and the first-view "today" panel.

Care needed when editing comments in this file: `.hn-auth /* c */ .foo{}` parses fine (a comment is
whitespace, so it reads as a descendant combinator), but the same shape in front of an at-rule kills
the remainder of the stylesheet silently. Verified after the edit by reading
`document.styleSheets[…].cssRules.length` in the browser — 303 rules, same as before.

## 2026-08-15 — v2026.08.15 — Auth terminal: no scrolling on short screens, form-only on mobile

<!--public
The sign in / create account screen now fits on a laptop screen without scrolling, and on a phone it
shows just the form — centred, no animation — instead of the desktop layout squeezed sideways.
-->

### What changed

**1. Short-viewport rhythm, without touching the signed-off desktop proportions.** On a ~700px-tall
laptop the Create Account state (name + email + password + strength meter + legal) overflowed `.left`
by 22px and scrolled. The fix is a dedicated `@media (min-width: 881px) and (max-height: 820px)` block
in `dashboard/auth-terminal.css` that trims padding, headline size and the field/tab/legal margins.
The base desktop rules are unchanged: at 2000×963 the SIGN IN button and legal block sit within 2px of
the endorsed reference render.

Why a media query rather than smaller base margins: the tall-desktop proportions were signed off
visually. Trimming them globally to solve a short-screen overflow silently changes the layout everyone
else sees. The block is guarded with `min-width: 881px` so it never collides with the mobile rules.
Measured after the change: 1440×694 → both tab states 617/617, zero overflow.

**2. Mobile is the transaction only.** Under `max-width: 880px` the animated terminal scene (`.right`)
and every nav item except the brand (`.nav-right`) are `display:none`. `.left` takes `flex:1` inside
the flex-column `.split` — without it `.left` only grew to content height (516px in an 812px viewport)
and `.form-wrap{margin:auto}` had no free space to centre into. The form is now vertically centred and
neither state scrolls at 375×812.

This reverses the previous release's form-above-scene ordering: on a phone the scene is decoration that
pushes the actual task off-screen, and the nav chips wrapped onto a second row. The comment explaining
the old ordering was rewritten, not left stale.

**3. Dead scene CSS deleted.** With `.right` gone from mobile, three blocks of scene-tuning rules
(`.modules-dock`, `.board`, `.path-status`, `.grid5`, `.calibration-orbit` at `max-width:880px` and
`561–880px`) had no element to style — including a `561–880px` block that was duplicated verbatim.
Removed rather than left in place; a comment in the surviving mobile block says not to re-add them
without re-adding the scene.

### Note

`dashboard/auth-terminal.css` still carries a header saying *"Do not hand-edit — regenerate from the
design file instead."* That has not been true for several releases; the generator
(`scratchpad/gen_auth_css.py`) no longer reflects the file. The header should be dropped or the
generator retired — flagged here so it is not treated as live guidance.

---

## 2026-08-14 — v2026.08.14 — Sign-in goes straight to the terminal; desk mark in the header

<!--public
Signing in is one step shorter: you land on the sign in / create account screen directly instead of
a page that just asks which one you want. On a phone the form is now at the top of that screen, with
the animated terminal below it. The desk mark now sits in the header on every page.
-->

### What changed

**1. The members-only interstitial is gone.** `renderGate()` in `dashboard/app.js` used to paint a card
reading *"The terminal is members-only."* with **Create your account** / **I already have one** buttons,
and only then open the auth surface. It now clears `#view`, sets `data-gated="1"`, and calls
`openAuth(planIntent() ? "signup" : "signin")` — nothing else. The card's `.gate-*` rules and its Urdu
strings were deleted with it rather than left orphaned.

Why: the card carried no information the login screen doesn't carry by being the only thing on screen,
and it spent a click at the most expensive step of the funnel. The `gate_viewed` event is unchanged, so
the funnel comparison across the change stays valid.

`renderGate()` returns early when `_authTerm` is already set. Moving between two gated routes re-runs
`route()`, and remounting would replay the terminal's four-second boot sequence each time.

**2. Mobile order on the auth terminal: form first, scene second.** `dashboard/auth-terminal.css` carried
two competing `@media (max-width: 880px)` blocks. The first (a faithful port of the wake6-v4 source) set
`.right { order: -1 }`, putting the animated terminal above the form. The second — the one that sets
`.left{order:1}` / `.right{order:2}` and shrinks the board, dock and seal for a phone — was **dead code**:
a stray `.hn-auth` token sat between the preceding rule and its `@media`, so the browser parsed
`.hn-auth @media (max-width: 880px)` as one invalid selector prelude and discarded the entire block. Every
declaration inside it was also unscoped (`body`, `.page`, `.split`, `.left`, `.right`, …) and would have
leaked into the desk had it ever parsed.

Fixed by deleting the stray token, scoping all 24 selectors with `.hn-auth`, and dropping `order:-1` from
the first block so the two no longer contradict each other. `body{overflow-x:hidden}` was dropped rather
than scoped — measured `documentElement.scrollWidth === clientWidth === 375` at the mobile preset, so it
was suppressing an overflow that does not exist.

This **departs from the reference HTML on purpose.** wake6-v4 itself stacks the scene above the form on
mobile; the desk stacks the form above the scene. The animation is context, not the task.

Note on the class of bug: `.hn-auth /* comment */ .foo{}` is valid CSS (a comment is whitespace, so it
reads as a descendant combinator) and that pattern appears seven more times in this file, all legitimate.
The same pattern in front of an at-rule is silently fatal. The remaining seven were checked individually.

**3. Desk mark in the top bar.** `dashboard/index.html` swaps the header's text-only brand for
`logo-terminal.svg` (already in `dashboard/`, byte-identical to the branding master) plus the wordmark:

```html
<a class="brand brand-top" href="#/today" aria-label="Henneth Desk"><img class="brand-top-mark" src="logo-terminal.svg" alt="" width="535" height="472" decoding="async"><span class="brand-mobile">Henneth <em>Desk</em></span></a>
```

`aria-label` on the link with `alt=""` on the image, so the brand is announced once — on mobile the
wordmark span is visible too, and an `alt` of "Henneth Desk" would make a screen reader say it twice.
The span keeps `.brand-mobile`, so the existing desktop-hide / mobile-show / gated-show rules apply
unchanged: on desktop the sidebar already spells the name out and only the mark rides in the header;
on a phone the sidebar is a drawer, so the words come back beside it.

Sized at 30px in `themes.css` — the tallest the mark stands in a 48px bar with the bar's 7px padding
intact. **Watch this one:** `logo-mark.svg` exists precisely because the "HENNETH DESK" label plate, its
LED and the button housing occupy a 39px band of a 472px artboard and stop reading below ~40px. At 30px
that band renders about 2.5px. If it reads as mush on a real screen, the fix is a one-word swap of the
`src` to `logo-mark.svg`.

**4. The Vercel build shipped an allow-list, and it broke the site. `scripts/vercel_build.sh` copied
eighteen files out of `dashboard/` by name. `auth-terminal.js` and `auth-terminal.css` are new in this
release and were not on that list, so production served the new `app.js` — which now opens the terminal
as the gate — with no terminal module to open. Both files 404'd and every signed-out visitor got a blank
page. `index.html`, `app.js`, `themes.css` and `logo-terminal.svg` all deployed correctly; only the two
files the release was actually about were missing.

An allow-list of filenames fails silently and fails **closed**, and it fails hardest on exactly the file
a release is about — an existing file is never the one you forget. Replaced with copy-everything then
deny:

```sh
cp -r dashboard/. public/
rm -f public/app.html
```

`app.html` is a stale duplicate shell predating the sign-in gate and is deliberately not served. A
deny-list fails **open** and fails loudly: the worst outcome is a stray file being reachable, which is
visible, rather than a required file being absent, which is not. Vercel builds from the git checkout, so
untracked scratch files in `dashboard/` never reach the build. This also matches what `README.md` already
claimed the build did.

**5. The build fix could not deploy itself.** Shipping §4 changed nothing live. The Vercel project
carried an Ignored Build Step — `git diff --quiet HEAD^ HEAD -- dashboard/ state/ vercel.json` — set to
skip rebuilds on data-free commits. A commit touching only `scripts/vercel_build.sh` matches none of
those paths, so Vercel skipped the deploy and the broken build stayed in production. The list also
omitted `api/` and `middleware.js`, meaning a change to the edge auth gate or the Ask endpoint would
have shipped nothing, silently.

The condition is now declared in `vercel.json` as `ignoreCommand`, where it lives beside the
`buildCommand` it guards and is reviewable in the diff, rather than in dashboard settings no one reads:

```
git diff --quiet HEAD^ HEAD -- dashboard/ state/ api/ middleware.js scripts/vercel_build.sh vercel.json
```

Adding anything the deploy depends on to this list is now part of adding it to the build.

Diagnostic note worth keeping: `vercel.json` sets `cleanUrls: true`, so `GET /index.html` returns a
15-byte `Redirecting...` stub, not the page. Grepping that stub for a marker returns 0 for **any**
marker and reads as "the deploy didn't land". Verify against `/`, or curl with `-L`. That cost a false
alarm on the header logo, which had shipped fine.

### Verified

On live (`https://desk.henneth.app/`, not localhost): `brand-top-mark` present in the served HTML,
`logo-terminal.svg` 200. Before the build fix, `auth-terminal.js` and `auth-terminal.css` returned 404
while `app.js` and `themes.css` returned 200 — the exact asymmetry the allow-list predicts.

Fresh load past the cache at `localhost:8878`: `.brand-top` present, mark 30px, auth terminal mounted,
no "members-only" text in the document, console clean. At the 375×812 mobile preset: `.left` order 1 at
y=107, `.right` order 2 at y=647, `.split` `display:flex` / `column`, no horizontal overflow.

### Still open

- `#/cast` — "cast your birth chart without an account" was a line on the deleted card. The route works
  and the funnel still depends on it, but it no longer has an entry point for a signed-out visitor who
  hasn't been given the link. Needs a home or an explicit decision to drop it.
- Onboarding answers persist to `localStorage` only. Cross-device requires a `desk_profile` jsonb column
  on Supabase `profiles`. Proposed, not applied.

## 2026-08-10 — v2026.08.10 — Premium polish round 5: tape stability, modal/scroll-lock cleanup, sidebar restore

<!--public
The price tape no longer jitters as numbers update, and closing a lesson or note popup now always
restores normal scrolling — no more stuck screens. The sidebar remembers its width without a flash
on load.
-->

### What changed

Fifth polish round on `dashboard/`, closing out the loop from rounds 1-4 (see prior entries). Fixed
12 findings from a 3-agent parallel audit, applied as one batch, verified in-browser, then confirmed
clean by an independent final audit re-deriving each fix from the shipped files.

- **Tape number jitter** — `globalStripData` now formats price with a fixed 2-decimal formatter
  (`toLocaleString`, `minimumFractionDigits/maximumFractionDigits: 2`) instead of the variable-width
  general formatter; `.gstrip .gitem b/i` got wider `min-width` floors (9ch/7ch) so the marquee track
  width stops drifting as digit counts change.
- **Modal/overlay teardown on navigation** — route changes now close any `.pl-overlay` /
  `.replay-overlay` via each modal's own `_close()` (added to the lesson player, security modal, and
  "what's new" modal) instead of a blind `.remove()`, and always reset `body.style.overflow`. Previously
  a modal open during a route change could leave the page scroll-locked or leak its keydown listener.
- **Layout-thrash cleanup** — `tileRuns`, `tileify`, and `wireTiles` were read/write-interleaved
  (measure, mutate, measure, mutate...), forcing a reflow per element. Rewritten as two-pass:
  collect all measurements first, then apply all DOM writes.
- **Sidebar restore flash** — restoring the saved sidebar width on load now happens before its
  transition is armed (`.shell:not(.side-ready) .sidebar{transition:none}`, class added via `rAF` +
  a 300ms timer fallback since `rAF` doesn't reliably fire in a backgrounded tab). Toggling the
  sidebar afterward still animates normally.
- **Font metric shift** — added a `local("Consolas")` `@font-face` fallback with `size-adjust`/
  `ascent-override`/`descent-override` tuned to JetBrains Mono's metrics, so body text doesn't
  reflow when the real font finishes loading.
- **Reduced-motion tape** — under `prefers-reduced-motion: reduce`, the tape now also hides items
  past the 9th, shortening the (now static) list instead of just freezing a long scrolling one.
- **Small leaks** — removed a duplicate `#searchbtn` click binding, guarded the ticker-note
  save-confirmation timeout with `isConnected` (was writing to a possibly-removed node), and
  dropped a `transition` from `.rp-prog-fill` that fought its `transform`-based animation.
- One finding from the audit (`--topbar-h` variable) was hallucinated — grep-confirmed it doesn't
  exist anywhere in `dashboard/` — and skipped.

Commit: `aa150983`.

---

## 2026-08-09 — v2026.08.09 — SEO: orphaned /psx/ hub fixed, blog posts linked into it, canonicalization

<!--public
Company pages under /psx/ are easier for Google to find now, and the blog links through to the
company/ticker data it's talking about instead of dead-ending.
-->

### What changed

Three commits, one root cause: the marketing site (`site/`) had pages with no inbound links
pointing at them, which starves Google of crawl authority regardless of content quality.

- **`c5c0d55e`** — `/psx/` hub had zero site-wide inbound links (nav stays capped at 7 items by
  design; nothing else pointed down to it). The 19 `/psx/[ticker]` pages hang off it via
  breadcrumb, but a hub with no inbound links passes nothing to its children — this is exactly why
  GSC Page Indexing showed all 19 as "Discovered - currently not indexed." Fixed by adding `/psx/`
  to `Footer.astro`'s Product column, same pattern already used for `/global-markets`.
- **`c3602d13`** — the 4 existing blog posts had zero internal links into the `/psx/` layer (same
  orphaned-island pattern, one level down). Added one contextual link per post: a named company to
  its own ticker page where one exists (Bank Alfalah → `/psx/bafl/`), generic mentions to the
  `/psx/` hub otherwise. `docs/CONTENT_ROUTINE.md` now bakes this in as a hard minimum for every
  future post, alongside the existing `/tools/` link requirement, plus a step to request indexing
  in GSC right after push instead of waiting on Google's own crawl schedule.
- **`2bd6d4bb`** — `trailingSlash: true` in `site/vercel.json` forces a 301 from the non-slash form
  to the slash form, matching the sitemap/canonical already in use (both `/features` and
  `/features/` were serving 200, duplicate-URL crawl-budget waste). `Header.astro`/`Footer.astro`
  nav hrefs now carry the trailing slash directly so site-wide nav stops generating an avoidable
  redirect hop on every internal click. Also tightened 3 title/description tags (`solutions.astro`
  meta description 158→151 chars; `psx-market-types-explained.mdx` title shortened to cut mobile
  SERP truncation risk; `/psx/` hub title rewritten from generic "PSX companies" to keyword-rich
  "PSX companies by sector, dividends and fair value").

All three verified deployed (`READY`) on the `henneth-site` Vercel project. No GA4 traffic pull
this round — no GA4 MCP tool connected this session; numbers TBD next check.

### Not done this batch (tracked, not forgotten)

- Unique OG images per blog post and per `/psx/{ticker}/` page — bigger lift (image generation),
  deferred.
- 8 remaining GSC "Request Indexing" manual submissions (bafl, dgkc, engroh, indu, luck, mlcf,
  pakt, trg).
- Cluster-2 blog posts in `docs/CONTENT_BACKLOG.md` (`how-to-start-investing-psx`,
  `cdc-sub-account-vs-investor-account`).
- 5 backlink/outreach messages drafted (KSEStocks links page, Profit editor, Mettis Global,
  Sarmaaya.pk FB community, Stockiest91 Telegram) — draft only, none sent; sending any is
  outward-facing and needs separate go-ahead per contact.

---

## 2026-08-05 — v2026.08.05 — Insider & off-market data wired into the ticker page

<!--public
Insider/substantial-shareholder filings and off-market trade prints now show up on every ticker
page — Data flags, Signal Stack, and the plain-English "at a glance" summary. Metadata only: what's
on file, never a buy/sell read.
-->

### What changed

`state/insider_activity.json` and `state/offmarket_activity.json` (retained ≥3 months, refreshed
weekly by `scripts/fetch_insider_offmarket.py`) now feed three surfaces per desk hard-rule #2 —
facts only, no direction ever inferred from a filing or an off-market print alone:

- **Data flags** (`dashboard/app.js`) — a neutral info-flag row: recent filing count + off-market
  aggregate for the trailing retention window, no pro/con framing.
- **Signal Stack** — new `insiderLens`, permanently non-directional (`k: ""`), excluded from the
  confluence tally the same way `astroLens` is (it makes no edge claim, just states what's on file).
- **At a glance** (`scripts/build_explainer.py`, deterministic Python) — folds filing/off-market
  facts into `what_changed`, computed once per cycle, zero LLM tokens.

### Backend (prior session, retained/accumulating history)

`fetch_insider_offmarket.py` replaces the old fully-overwritten trailing-7-day snapshot: off-market
days ACCUMULATE and prune to a 90-day trailing window; insider filings ACCUMULATE and are never
pruned. One-time backfill/seed scripts (`backfill_offmarket_90d.py`, `seed_insider_history.py`,
`build_insider_batches.py`, `consolidate_insider_batches.py`, `fetch_insider_pdfs.py`,
`render_insider_pdf_images.py`, `filter_insider_backfill.py`) got the desk from a 7-day snapshot to
≥3 months of retained history in one pass; the weekly fetch takes over from there.

---

## 2026-08-01 — v2026.08.01 — Urdu translations, made sustainable

<!--public
Urdu translations run leaner now, so the language stays in the product for good instead of
risking getting dropped later.
-->

### The problem

The Urdu translator agent was reading and rewriting whole state files (`rooms.json` alone is
~380KB) every call — English content paid for twice (in and out), and Urdu script tokenizes
~2-3x per word vs Latin script, so re-emitting existing Urdu on every call multiplied the cost
further. The Desk Room loop made this worst: one translator call per persona per ticker.

### Three changes, stacked

1. **Model swap.** `state-translator` agent: `sonnet` → `haiku` (~70% cheaper per token).
2. **Deterministic extract/merge, so the LLM never sees a whole state file.**
   `scripts/translate_extract.py` walks a state file against dotted field-path patterns
   (`[]` = every array element, `*` = every dict key), hash-skips anything already translated
   (first 12 hex chars of sha256 over the exact English string, `h12()`), and writes only the
   untranslated strings to `state/translate_batch.json`. The translator agent (Read/Write only,
   fact-blind by design) reads that tiny batch and writes Urdu-only to
   `state/translate_batch_ur.json` — it never opens the source file. `scripts/translate_merge.py`
   folds `_ur` + `_ur_hash` siblings back into the source file and deletes both temp files. If
   extract reports 0 fields, the translator is never spawned — zero tokens, zero LLM call.
   Wired into all four call sites: `prompts/cycle-light.md` (newslog.json), `prompts/cycle-full.md`
   (macro.json, daily_read.json), `prompts/sector-week.md` (sector_debates/<slug>.json), and the
   `psx-desk-room-loop` scheduled task (rooms.json).
3. **Room loop batches per session, not per persona.** The scheduled task's translate step now
   issues one extract command covering every ticker in the batch (13 field patterns × N tickers,
   concrete `<SYM>.field` paths — deliberately not the `*` wildcard, so it never backfills the
   entire rooms.json history in one run) and spawns the translator agent once for the whole batch.

### Bug found and fixed during build: partial-array hash

If only some elements of a plain string array were translated (e.g. `risks[0]`/`risks[1]` but not
`risks[2]`), `translate_merge.py` was unconditionally stamping `risks_ur_hash` over the FULL joined
English array. The next extract's hash-skip check then wrongly treated the whole array — including
the untranslated element — as done, permanently hiding it from future translation passes.

Fixed in both scripts: `translate_merge.py` only writes `_ur_hash` when every element with
non-empty English also has a non-empty Urdu counterpart in `_ur` (otherwise it removes any stale
hash key); `translate_extract.py`'s array-skip condition also requires every element of the
existing `_ur` array to be a non-empty string, as a second guard. Verified with a 2-of-3
translated test array: post-merge, no `_ur_hash` is written, and a re-extract on that array
correctly returns all 3 elements rather than skipping the whole thing.

### Legacy data migration

`state/rooms.json` had 96 pre-existing `_ur` translations (written before this hash-check system
existed) with no `_ur_hash` sibling — without backfilling, the new hash-skip extract would have
treated them as untranslated and burned tokens re-translating already-good Urdu. One-off script
stamped `_ur_hash = h12(current_english)` for every such field, assuming the existing translation
matches the current English (it was written from it). Ran once against rooms.json, newslog.json,
macro.json, daily_read.json and every sector_debates/*.json — only rooms.json needed it (+96
hashes).

### Also

`scripts/merge_translations.py` (the old per-ticker dotted-key merge script, no hash support)
marked LEGACY in its docstring — superseded by the generic extract/merge pair, kept only in case
an old `room_tmp_*_fields_ur.json` still needs merging by hand.

## 2026-07-26 — v2026.07.26.2 — Stale calendar dates, a misleading confidence label, and the fair-value spread

<!--public
Six fixes from the backlog:

A ticker's "next earnings" date could show one that had already passed, if the calendar had a
stale entry ahead of the real one. It now only ever shows the nearest date that hasn't happened yet.

The P/E ratio and dividend payout percentage are now derived from today's live price, not whatever
price was on the page the last time the underlying data was scraped — the two can disagree, and
the live-price version is the one that's actually current.

A signal's "confidence" label now requires enough closed trades behind it, not just a good score.
Ten trades can't earn "high confidence" regardless of how good they looked.

The fair-value card no longer hides disagreement between its four valuation methods behind one
composite number — it now shows the full spread, so "undervalued by 20%" and "the four methods
range from Rs 381 to Rs 1,542" are both visible at once.

A new "Shipped" page lists every completed item from this backlog, so it's visible on the site
and not just in this file.
-->

### Earnings/ex-div date filter (item 3)

`dashboard/app.js` `pageTicker()` — `nextEarn`/`nextXdiv` used a bare `.find()` over
`earnings_calendar.json` events with no date check and no sort: the first matching event in the
array won even if it was in the past, or a later one existed earlier in the array. Replaced with a
`nextOfType(t)` helper that filters to `date >= today` and sorts ascending, taking the earliest.
Two commits: the first (`72824af`) shipped everything else in this entry but the actual filter was
missed; caught in review and fixed in `6fc72c2`.

### Live-price P/E and derived payout ratio (items 6, 8)

`scripts/score_fundamentals.py` — added `live_pe(v, sym)` and `derived_payout(v)`. Both prefer
`state/live.json`'s current price combined with EPS/yield from `fundamentals.json`, falling back to
the vendor's own scraped ratio only when a live price or EPS/yield isn't available. Output
(`state/fundamental_scores.json`) is read by the ticker page in preference to the raw scrape.

### Sample-gated confidence (item 4)

`scripts/build_signals.py` — `confidence` now requires `p["n"] >= 30` for "high" and `p["n"] >= 15`
for "medium", on top of the existing score thresholds. `min_trades` (8) stays the bare eligibility
floor for a strategy to be considered at all; it was never meant to double as the bar for calling
something highly confident.

### Fair-value method spread (item 7)

`dashboard/app.js` value screener + ticker fair-value card — now render the four methods' individual
values (peer P/E, earnings-power, Graham, DDM) alongside the median, so a wide split between them
(one stock ranged Rs 381–Rs 1,542) is visible instead of collapsed into a single "undervalued by X%"
number.

### Recently shipped page (item 5)

`dashboard/app.js` — new `pageShipped()`, reusing `state/changelog.json` (same source as the
"What's new" modal, but rendering every cached release as a card instead of capping at 5).
Registered in `PAGES` and added to `OPEN_ROUTES` (signed-out visible, same as `glossary`/`legal`).
`dashboard/index.html` — "Shipped" link added to the `.side-legal` sidebar block.

## 2026-07-26 — v2026.07.26.3 — Astro calc audit: dignity scoring, a consistent conjunction orb

<!--public
Your Chart's resonance scores (the stock and commodity matches) now read exaltation and
debilitation, not just whether a planet sits in its own sign. A planet in its strongest placement
lifts a match; in its weakest, it pulls the score down.

The "crossing your natal X today" flag now uses the same 2.5-degree closeness on both stock charts
and personal charts — one consistent standard for what counts as a conjunction, everywhere it's
shown.
-->

### Dignity scoring in `resonanceWithGraha` (audit item)

`dashboard/app.js` — was own-sign only. Added exaltation (+12, overrides the own-sign +8) and
debilitation (-10) against `state/astro_map.json`'s `grahas.<name>.exalted`/`debilitated`. Rahu and
Ketu have both fields null there (the data itself flags their dignity as disputed) — the code skips
the claim for them rather than guessing. Threaded `amap` through as a 4th param, matching the
existing pattern (`gocharaRead`, `dashaTimeline`, `synastry`, `stockTiming` all take it explicitly,
never a module global); updated both call sites (`synastry`'s chartless-stock fallback, the
commodities grid on `/mychart`). Verified live: a synthetic exalted-Sun chart scored 48 with an
"exalted" reason, debilitated-Sun scored 26 with "debilitated", Rahu scored 50 with no dignity
claim attached.

### Conjunction-orb standardized (audit item)

Three separate orb checks exist in the codebase asking two different questions. `astro_engine.py`'s
`find_events()` (1.0°) detects the single day two transiting bodies pass closest to each other —
a genuinely different question, left as-is and commented so it isn't "fixed" into alignment later.
`astro_natal.py`'s `transits_to_natal()` (was 3.0°) and `app.js`'s `gocharaRead()` (already 2.5°)
both ask "is anything conjunct this natal point today" and had drifted apart. Tightened the Python
side to 2.5° to match — tighter orb, harder to claim a false hit, and it matches what was already
live on the JS side. `transits_to_natal` feeds the "transiting X conjunct natal Y" line on the stock
chart page (`app.js:1633`), so this is a real, live scoring change, not internal-only.
`state/astro_natal.json` regenerated.



<!--public
Long lists no longer bury what is under them. Every dense section — the universe, macro, news,
signals, research — now sits in a horizontal tile lane you swipe through, on a phone and on a
desktop alike, so nothing costs you a screen of scrolling to reach.

Sector debates open short: the house view, the case for and the case against, as three tiles you can
read in about three minutes. The full argument is still there behind "read the transcript". Sectors
the desk has already argued carry a dot, and the ones it has not say so plainly instead of looking
broken.

Macro reads as tiles too — rates, currency, commodities and the global tape at a glance rather than
as rows to scan.

The astrology reading now answers four questions instead of printing a chart. Where you are in the
Vimshottari dasha ladder, with dates and the next three turns, each labelled the way the tradition
labels it. What nineteen years of PSX history actually measured for that same stock — the conditions
tested, the effect per day, the p-value, and whether it survived correction. How the stock's sky
compares to Pakistan's own 1947 chart and the KSE-100's 1991 chart, using only the slow planets that
a disputed birth time cannot move. And what the sky is doing today, joined to what that exact
condition was worth when tested.

None of it is a call. Every claim from the tradition is stamped untested; every number the desk
measured carries its p-value.
-->

### Astro: the four blocks, and why the old reading was worthless

The complaint was exact — the reading printed placements and stopped, which is "basic info that
nobody will care about." The fix is not more astrology; it is *joining* the astrology to the
falsification work the desk already did and never surfaced per stock. Four blocks in
`composeAstroReading` (`dashboard/app.js`), each built ONLY from `state/`:

- `arDashaBlock` — the tradition's dated claim. Maha/antar with real dates from
  `astro_natal.json:dasha`, coloured by `astro_map.json:grahas[b].natural_nature`.
- `arReceiptBlock` — the falsification receipt for THAT name: its own rows out of
  `astro_backtest.json:all_tests`, five lowest p, with survivor counts and the honesty note.
- `arLiveBlock` — today's live conditions from `astro_context.json`, each joined to its measured
  effect. This is the whole point of the release: "live now → tradition claims → desk measured X,
  p=Y, did not survive correction."
- `arCompareBlock` — Pakistan and KSE-100 slow grahas plus Saturn returns.

**Fallback discipline.** ENGROH has no birth chart — the screenshot that started this was ENGROH.
The receipt scopes `subject == sym`, then the sector (naming the peers it borrowed), then
`KSE100 (proxy)`, and the dasha block falls back to the market's own chart. It never silently
presents a peer's numbers as the stock's.

**Non-directive by construction (SECP Reg 2(ha), S.R.O.7(I)/2026).** No block states a direction,
target or level. Tradition claims carry the untested stamp; measurements carry the p-value and the
correction result. Both branch caveats end "Nothing here is a buy, sell or hold, a target or a stop."

### `scripts/astro_context.py` — new, and the reason the join is possible

The dashboard could show what the sky is doing OR what the desk measured, but could not join them,
because nothing in `state/` named today's conditions in the backtest's vocabulary. The new script
mirrors `astro_backtest.py`'s masks exactly and **asserts its output against
`astro_backtest.json:all_tests` at the end of every run** — if the two drift, the join becomes a
lie, so it prints a warning naming the orphan condition. That guard already earned its keep: it
caught `Rahu retrograde` / `Ketu retrograde`, which are true every day and were never tested.

It also publishes the Pakistan (1947-08-14) and KSE-100 (1991-11-01) charts, which `astro_map.json`
records as events with no positions because neither has a known time. Each is cast at BOTH argued
times and **only placements that agree are published**; the Moon and ascendant are refused outright.
`astro_map`'s `usage_rule` is now enforced in code rather than in a footnote.

Wired into `run_cloud.py` after `astro_natal.py`.

### `astro_natal.py` — the ladder the reading needed

`antar_ladder()` (9 sub-periods under the running maha) and `upcoming_changes(n=3)` added, so the
dasha block has dated turns instead of one current period. `astro_map.json` gained per-graha
`natural_nature` + `nature_note`, with `_note_nature` stating explicitly that the label is the
tradition's own and not a measured effect.

### Tiles at every width, and the sector page

The scroll-tile lane was phone-only; it now applies at every viewport (`5472da0`), because a 1,400px
desktop list buries what is under it exactly as a 375px one does. The sector page was rebuilt
(`3c52e87`): TLDR-first house/for/against tiles, a left rail of sectors, full-transcript modals, run
dots for argued sectors and a real empty state for the rest. Macro instrument rows became tiles in
this release.

### One-line CSS bug found during verification

`.topbar>*{flex:none}` froze the timestamp span at its 190px max-width, so at ~1280px the header
overflowed and the whole page gained a horizontal scrollbar. `flex:0 1 auto;min-width:0` — it
ellipsises instead. Verified: `document.body.scrollWidth === clientWidth` at 375 and at 1280, zero
console errors, 3 cards × 4 blocks rendering real data for ENGROH (sector fallback), ABL and AGP.

## 2026-07-22 — v2026.07.22 — The publication restructure, global coverage, mobile tables

<!--public
Tables fit your phone screen now. The widest one needed 4,393px before — twelve screen-widths of
sideways dragging to finish one sentence. Wide tables restack as readable cards instead.

The Desk Room shows when a debate was published, and says "Read" rather than "Run". Nothing was
ever run on request: the analysts work to the desk's own rotation, and the wording now says so.

Signals show risk per share instead of a share count. The desk does not know your capital, so
sizing is yours — there is a free position-size calculator on the website using the desk's own rule.

The desk now covers 23 global symbols: the S&P 500, Nasdaq, Dow, Russell, VIX, all eleven US
sector ETFs, EM and developed baskets, rates, gold and oil. Index and sector level, for the context
they give PSX — no US stock picks, and no signals on them.

A free financial-astrology lens is on the website — your Moon sign, its element, and the sectors
and commodities tradition attaches to it, plus what nineteen years of testing actually found.
-->

Implements `docs/PUBLICATION_RESTRUCTURE.md` §2a, §3, §4, §5 step 1, §6b and §7. Five of the doc's
own instructions were wrong when checked against the code and are corrected in place there.

### §4 — the Desk Room was already compliant; the copy was the violation
`runDeskBar` renders only when `hvRoom` exists, and `playDeskReplay()` replays a pre-computed
debate. No user action ever triggered an agent or spent a token. The copy ("Run the desk on FFC",
"Once it finishes…") claimed on-demand personal analysis — the advisory framing the restructure
exists to remove, for something the product does not do. Reframed to reveal-as-reveal.

### §5 step 1 — repointing the watchdog probe
`watchdog.py` used `natal_ephem.json` as its public-access probe: the one file that must serve 200
while everything else 401s. Flagging natal off would have left that check passing meaninglessly.
`build_dashboard.py` now emits a purpose-built `public_probe.json`; because it carries the cycle
stamp, deploy staleness is detectable without a credential for the first time.

### §3 — sizing out of published output
`size_shares`/`size_pkr` removed from the signal payload; `risk_per_share` added. The computation
stays because `shares <= 0` is the Rule 4 validity guard. `prompts/cycle-full.md` also instructed
the auditor step to write sizes into `signals.json`, so the script change alone would have been
undone by the next full cycle.

### §7 — US coverage, and the seam held
`quant.py` computed close, RSI and 20-day returns for US500, XLE and GLD with **no code change**:
`state/history/{SYM}.json` is a market-agnostic seam and only `liquidity.py` was currency-bound.
Yahoo spells the S&P 500 `^GSPC`; a symbol here becomes a filename and then a URL path, so the desk
calls it `US500` and maps it. Never let a vendor's punctuation become a filename.

### Routines
Adding a second market silently widened every script that iterates the universe, including those
whose source is PSX-specific. No crashes — the harm was bounded per-run fetch budgets being spent
on symbols that can never return, starving real PSX names in the rotation. `market_symbols()`
applied to the five PSX-source fetchers; the market-agnostic maths deliberately left alone.

---

## 2026-07-19 — Three-plan product, the Investor desk, and entitlement enforcement

Turned the single-tenant desk into a three-audience product. **Nothing here is billed** — card
processing via international providers is unavailable in Pakistan, so a local gateway comes later.

### Plans
- `Free → Investor → Pro → Broker` (`PLANS` / `PLAN_ORDER` in app.js). The paid entry tier is
  **Investor**, not "Learner" — a tier named for what the customer lacks is a label on the customer.
  DB migration `rename_learner_plan_to_investor` moved the stored value and the CHECK constraint.
- Broker renders **"coming soon"** (disabled CTA) — the plan is defined, the product is not built.
- Plan cards show an **Upgrade CTA** for any tier above yours. `on` is evaluated before `soon`, so
  your own plan never reads "Coming soon". `notifyUpgrade()` records interest instead of faking a
  checkout that does not exist.
- `#/plans` carries an **owner-only preview-as-plan** switch: re-renders the entire product as any
  tier without touching the stored plan (in-memory, reload resets). `hasFeature`/`isSubscribed`
  honour the preview even though `BILLING_LIVE` is false, or preview would be meaningless.

### Entitlement security — a self-promotion hole found and closed
`profiles.plan` is guarded by a CHECK constraint plus **two** triggers. The first migration added a
`BEFORE UPDATE` trigger only. That was insufficient: the client writes profiles via **upsert**, so a
crafted INSERT could have set `plan='pro'` and self-granted a paid tier. Migration
`freeze_plan_on_insert_too` adds a `BEFORE INSERT` trigger forcing `plan='free'` for role
`authenticated`. Plan changes are now a service-role-only path.
`ui_mode` is intentionally left client-writable — it is a view preference, not an entitlement.
`BILLING_LIVE = false` remains the single switch; while false any signed-in account reads as
subscribed, so shipping paywalls could not strip access from accounts that already had it.

### The Investor desk (`#/learn`)
- 4 levels that **unlock in order**, 17 lessons, played **one card per screen** in a focused player.
  A long scroller with quizzes was the first attempt and was rejected as a poor experience.
- Card kinds are visually unmistakable and namespaced `k-*`: lesson · watch out · the point ·
  interactive · check yourself.
- New **Level 2, "The documents"**: the full map of what a Pakistani listed company publishes, the
  annual report, all three financial statements, the auditor's report + pattern of shareholding +
  related-party transactions, and announcements/AGM/material information.
- **Interactive labelled statements** (`anatomies` in `state/curriculum.json`): tap any line for what
  it is and what to watch. **Rule 2 compliance:** `fundamentals.json` holds revenue/net income/EPS but
  not gross profit, opex or finance cost — so real figures appear **only** on the lines the desk
  actually holds (anchored to a real named company), and every other line reads *"in the filing"*.
  No statement line is fabricated to make the lesson look complete.
- Plus a 12-document tap-to-learn map and a dividend-date timeline highlighting the ex-date.

### Two bugs introduced during this build, caught before/at verification
1. **Async render race.** `renderPlayer()` awaited the anchor fetch mid-render, letting a second
   render interleave and leaving 3 stale `.anatomy` nodes; clicks bound to a detached copy silently
   did nothing. Fix: fetch the anchor once in `openLesson`, keep `renderPlayer` synchronous.
   *Prevention:* never await inside a function that fully rewrites its own container.
2. **Class-name collision.** The card wrapper took `class="pl-card ${c.type}"`, so a card of type
   `anatomy` matched the `.anatomy` **component** selector and inherited its border. Card kinds are
   now namespaced `k-*`. *Prevention:* never use a raw data-driven type string as a CSS class.

Also: the sidebar was regrouped (Today/Board · You · Edge · Market), the account menu rebuilt to show
the plan you are on, and search widened from a 34 px icon to a labelled 230 px field (collapses back
to an icon under 1100 px; palette behaviour unchanged).

---

## 2026-07-18 — Personal astrology pillar, its funnel, and the daily sky

A Vedic (sidereal) astrology layer shipped as **exploration, never an edge claim** — because the desk
tested it and it failed.

### The test result that frames the whole pillar
- `astro_backtest.py`: 2,589 hypotheses across 101 subjects (99 stocks + KSE100 + KMI30) → **0 survivors**
  after Bonferroni and FDR. Expected ~129.5 false positives at p<0.05; 143 came back.
- `astro_natal_test.py`: 379 natal-method hypotheses, 27 verified company birth charts → **0 survivors**.
  Published with an explicit power caveat: young charts make this test weakly powered, so the finding is
  **"not demonstrated", not "disproved"** — the desk does not claim a verdict it has not earned.
- The honest foil: `sector_macro.py` ran the *same* machinery on ordinary macro factors and found
  **17 Bonferroni / 34 FDR survivors of 98** (oil→E&P at p=2e-5, joint R² ≤2.6%). Same bar, real result.

Two methodology bugs were found and fixed **in our own test harness** before trusting any of it:
- **A self-rigging backtest.** A 2,000-shift permutation can never produce a p below 1/(N+1), so it
  could not reach a ~1.4e-4 Bonferroni bar — "zero survivors" was guaranteed by the method rather than
  by the data. Fixed with two-stage resampling (2,000 screen → 50,000/200,000 fine).
- **A false discovery.** Raw returns surfaced 2 survivors at p=5e-6 on PIOC. Both were **beta**:
  market −0.119%/day, cement −0.238%, PIOC β=1.243 → −0.430%. Market-adjusting returns
  (`r − β·r_mkt`) moved p from 5.0e-6 to 1.29e-3. Two further bugs inside the replication check were
  fixed at the same time.

### The feature
- Browser-side natal chart from a committed 552 KB packed ephemeris (1950–2035, daily, `<9H`).
  Ascendant computed live from LST + latitude, validated against the sunrise anchor.
- Classical synastry against every PSX name (Tara koota, Moon-lord friendship, benefic placement,
  dasha resonance); chartless names (pre-2000 listings) read through the sector significator.
- Vimshottari dasha + antardasha, an isometric-feel natal orrery, per-stock timing windows,
  8 commodities read through traditional rulers, and goal-tailored *language* (never maths).
- **The daily layer** (the actual subscription rationale, since a natal chart never changes): gochara
  placed from the natal Moon and recomputed daily, a transit ring on the orrery, and dated
  "worth another look" shifts. All client-side over data already shipped — zero marginal cost per user.
- `astro_claims.py` files dated **market-relative** claims with a stamped benchmark level and grades
  them on the public scorecard. `fetch_indices.py` was added because grading market-relative claims
  against an absolute price would have scored a stock falling 2% in an 8%-down market as a **hit**.

### The funnel
Casting a chart requires **no account** — it is client-side maths over an ephemeris the browser
already fetches, so the prior sign-in wall was artificial. Guests cast free into `localStorage`;
`migrateGuestChart()` lifts the chart into the profile on sign-in so birth details are never entered
twice. Free tier sees the real chart plus the 3 strongest matches, then one shared `planWall()`.

### A silent bug this uncovered (was live, affected every user)
`computeNatal()` read `timeKnown` while the wizard and the Supabase column both use `time_known`.
The value was therefore always `undefined`, so **no user ever received a rising sign** — every chart
silently fell back to Chandra lagna however exact the birth time given, and the ascendant ray in the
orrery was dead code. Fixed by normalising `bd.timeKnown ?? bd.time_known ?? false`.
*Prevention:* the snake_case DB column is the source of truth; accept both spellings at the boundary.

### Editorial: the 4th wall
On owner instruction, all readings stopped narrating the platform's own mechanics and limits
("so it isn't invented", "the desk tested astrology and found no edge", source citations). Readings
now lead with the Moon (Chandra lagna is a real technique, presented confidently). The null result is
**not hidden** — it remains in this changelog, in the README, and in the Investor desk's astrology
lesson, which teaches the tradition and the test result together. It is simply no longer narrated
inside an individual reading.

---

## 2026-07-12 — Ticker pages blank in real Chrome (extension breaking fetch)

Wasay reported "no data" on every individual ticker, on both live and preview, in his actual
Chrome (not reproducible in the sandboxed browser pane). Diagnosed directly in his real Chrome
session via console + network inspection.

**Root cause:** a Chrome extension (id `hoklmmgfnpapgjgcpechhaamimifchmp`, script `frame_ant.js` —
an ad/anti-fraud blocker) monkey-patches `window.fetch` and intermittently throws
`TypeError: Failed to fetch` on the dashboard's own same-origin `state/*.json` requests. Not a
code bug — same behavior on preview and live because it's the same browser.

**Fix:** `j()` in app.js now retries with backoff, and its **last attempt uses `XMLHttpRequest`**
instead of `fetch` — extensions that patch `fetch` don't intercept XHR the same way. Verified
live in Wasay's actual Chrome with the extension still active: `#/ticker/FFC` and `#/ticker/HUBC`
both went from "No data" to fully rendering on reload.

Also: user-facing fix is to disable/allowlist that extension for localhost + the live domain —
recommended to Wasay directly, not something code can fully route around if the extension also
blocks XHR on a given page (it didn't here, but could).

---

## 2026-07-12 — Educational + compliance layer on ticker & value pages

Reworked the company (ticker) page toward investor education and away from anything that
reads like advice — aligns with desk hard-rule #5 (no advice language) and reduces trust/
compliance risk for inexperienced users. All new content is derived from the data layer;
nothing is fabricated.

### Added (ticker page)
- **Prominent disclaimer banner** at the top (not hidden in a footer): educational/informational
  only, not personalized advice, past performance ≠ future results, PSX carries risk of capital loss.
- **Data-provenance line** under the header: currency (PKR), source + whether intraday (DPS) or
  end-of-day close, quant/fundamentals timestamps, and that the long chart is split/bonus-adjusted
  (Yahoo) while the DPS close is unadjusted. Inline `low liquidity` / `earnings negative` flags.
- **"What the data flags"** — auto-derived pros/cons ("what could go right / wrong") from real
  signals only (proven strategies, fair-value gap, forward vs trailing P/E, covered yield, beta,
  payout stretch, volatility rank, liquidity, peer valuation, max drawdown, lossmaking). Framed as
  factual observations, explicitly "not predictions, not advice; absence of a flag is not a green light."
- **"Questions to ask before buying"** — 7-item checklist answered from data where the desk has it
  (profit/growth via forward-vs-trailing P/E, cash-generation proxy with caveat, valuation vs peers,
  dividend sustainability via payout ratio + history, "can you tolerate a 30–50% fall" via real max
  drawdown, time horizon) and **honest where it doesn't** (debt: "not in feed — open the balance sheet").
- **Risk profile panel** — risk beyond volatility: price volatility, maximum historical decline,
  liquidity, market sensitivity (beta), valuation, dividend reliability — each with a plain-language
  read and a low/moderate/high chip. Debt & earnings-stability shown as **"not scored"** (no data) —
  honest, not faked. Header teaches "a low rupee price does not mean a stock is cheap."

### Changed — softened advice-flavored language (ticker + value pages)
- Fair-value verdict `undervalued/overvalued` → **"below / above model fair value"** everywhere
  (ticker section heading "Fair value model", pills, value-screen headings + row pills + expand note).
- Business scorecard rating `attractive/caution/neutral` → **"stronger / weaker / mixed scorecard"**.
- Value screen: removed "looks cheap / looks rich"; added the disclaimer banner; headings now
  "Priced below/above model fair value". Verified: **no advice words** (`undervalued`, `looks cheap`,
  `strong buy`, `guaranteed`, etc.) anywhere on either page.

### Fixed — misleading edge cases
- **Negative earnings → P/E** now shows **"n/a · earnings negative"** instead of a misleading `0`/`n/a`
  string (verified on TRG, EPS −8.82: P/E cell reads "n/a · earnings negative", cons list "fallen 93%
  peak-to-trough" + "currently lossmaking", checklist Q1 flags the loss).
- **Illiquid names** flagged in provenance + risk panel (verified PSEL 0.4M/day → low liquidity).

### Not built (no data — deliberately not faked)
- Company description ("what does this company do") and revenue/earnings/debt/cash-flow **trend charts**
  need data not in the feed (fundamentals is a single current snapshot; sector is stored as a numeric
  code, not a name). Flagged for a future scraper add rather than fabricated.

---

## 2026-07-12 — Value working, contrast, empty-state honesty, deploy guard

### Fixed
- **Board RSI / 20d columns went blank ("—") intermittently.**
  Root cause: `j()` (data fetcher in `app.js`) cached `null` on *any* transient fetch
  miss for 25s, so one hiccup loading `quant.json` blanked every RSI/20d/heat cell that
  reads from it. Fix: retry once, **never cache a failure**, fall back to last-known-good.
  Prevented by: `preflight.py` asserts `quant.json` has ≥20 tickers each carrying
  `rsi14`/`ret_20d`/`close` before any deploy.
- **Value tab hid its working.** The four valuation models existed in `fairvalue.json`
  (`relative_pe`, `earnings_power`, `graham`, `ddm`, median → `composite_fair`) but the
  screen only showed price/fair/verdict. Now each row expands inline to show all four
  models, price-vs-each %, the median derivation, the inputs (EPS, P/E, growth), and a
  plain-English why. Prevented from regressing: `preflight.py` requires every fair-value
  ticker to carry a non-empty `methods` object.
- **Light-grey text unreadable.** The `gemini` theme's `.sub` never set `opacity`, so the
  base `.sub{opacity:.55}` washed `--ink2` out. Fix: `.sub{opacity:1}`, darkened
  `--ink2` (#565650→#4a4a44) and `--ink3` (#8a8a80→#6b6b63) for real contrast.
- **Macro "Pakistan macro" showed a big empty grey block + four "—" cells.**
  Two causes: (1) `.facts` used CSS grid `auto-fill`, which reserves phantom empty tracks
  (the grey block) → changed to `auto-fit` which collapses them; (2) FX reserves / 6m
  T-bill / 10y PIB / remittances aren't in `macro.json` yet → now we render only populated
  facts and print an honest "pending this cycle" note instead of dead "—" cells.
- **Dividends "Upcoming" looked broken when empty.** It's legitimately empty off-season
  (PSX payouts cluster Jul–Aug; the desk never guesses a date). Rewrote the empty state to
  say so and point at the trailing payouts already listed below.

### Added
- **`scripts/preflight.py`** — deterministic pre-deploy guard. Re-reads every state file
  the dashboard consumes and asserts the exact shape the UI joins on (tickers present,
  fields non-null, no NaN/Infinity that would break `JSON.parse`). Exit 1 = do not deploy.
  Wired as the **last step of `build_dashboard.py`** (which the GitHub Actions workflow
  runs under `set -e`), so a structurally broken cycle aborts the job and the last-good
  live site stays up. Also the final step of `run_cloud.py`. Verified: empty `quant.json`
  → exit 1; healthy state → exit 0.

### Earlier this session (UI reskin — see git log)
- Option A light-terminal theme across all tabs; ticker-tape marquee autoscroll (pauses on
  hover); board regrouped into 3 filled columns (killed right-side dead space); search
  overlay close bug; mobile header horizontal-scroll fix; local preview loop
  (`preview.bat` → `scripts/serve.py`, serves local `state/`, nothing hits the cloud).

---

## How to not break the live site
1. Iterate locally: `preview.bat` (or `python scripts/serve.py`) → http://localhost:8877/dashboard/
2. Before any push: `python scripts/run_cloud.py` (or at minimum `python scripts/preflight.py`) must exit 0.
3. Push a batch, not every edit. CI re-runs the pipeline + preflight; a bad data cycle can no longer publish.

## 2026-08-17 — v2026.08.17.2 — 13 new tickers added to coverage

<!--public
The desk now also tracks: AKBL, BAFL, EFERT, EPQL, FFC, FPRM, HBL, HGFA, HIFA, IPAK, NESTLE, PAKT, STL. History is backfilling, so charts fill in over the next few sessions.
-->

### Universe expansion

Auto-recorded by scripts/changelog_tickers.py: AKBL, BAFL, EFERT, EPQL, FFC, FPRM, HBL, HGFA, HIFA, IPAK, NESTLE, PAKT, STL added to state/universe.json this cycle.

## 2026-08-19 — v2026.08.19 — 2 new tickers added to coverage

<!--public
The desk now also tracks: FPRMR2, STLR. History is backfilling, so charts fill in over the next few sessions.
-->

### Universe expansion

Auto-recorded by scripts/changelog_tickers.py: FPRMR2, STLR added to state/universe.json this cycle.

## 2026-08-24 — v2026.08.24 — 3 new tickers added to coverage

<!--public
The desk now also tracks: GCWLPRS, SGPLR, TISL. History is backfilling, so charts fill in over the next few sessions.
-->

### Universe expansion

Auto-recorded by scripts/changelog_tickers.py: GCWLPRS, SGPLR, TISL added to state/universe.json this cycle.
