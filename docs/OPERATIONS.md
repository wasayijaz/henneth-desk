# Henneth — Operations Runbook

**Read this before touching anything that reaches the live site.** It is the single source of truth
for how the desk runs, who does what, and how to publish without breaking the live website. Governance
rules (position sizing, circuit breaker, no-lookahead, etc.) live in [`CLAUDE.md`](../CLAUDE.md); this
doc is about *operations*.

Live site: https://desk.henneth.app/ · Repo: private, hosted on Vercel · Auth/DB: Supabase.

---

## 1. The hybrid architecture (who runs what, where)

Two halves, on purpose. The split is what gives 24/7 freshness at controlled token cost.

```
COMPUTER OFF — GitHub Actions cloud cron  (.github/workflows/desk-data.yml)   FREE, no tokens, no agents
  every 30 min off-peak, market hours →  python scripts/run_cloud.py
  = prices · quant · backtests · fair value · health · dashboard
    + Desk Room DETERMINISTIC scaffolding (dossiers · queue · gate · scoring)
  → publish.py → push → Vercel deploy → watchdog

COMPUTER ON — app scheduled tasks (Claude app, ~/.claude/scheduled-tasks/)     tokens, owner present
  the JUDGEMENT/agent work: news-sentinel · monitor · macro · daily read
  · the Desk Room DEBATES (chartist/fundamentalist/bull/bear/chair) · weekly broker harvest
  → publish.py → push → Vercel deploy → watchdog

ALWAYS — every visitor sees the full SAVED analysis 24/7 (debates, TA/FA, 52 backtests, scores),
  because agent output is persisted in state/ and served statically. Agents REFRESH it; they are
  not needed for a user to READ it. Nothing goes dark when the computer is off.
```

**Rule of thumb:** deterministic/data work can run in the cloud; anything that needs Claude (an agent)
runs on the owner's machine. The cloud never runs an agent (no API key by design).

### 1a. Company Intelligence surface (2.CI.0 — owner-only live surface)

`Henneth Desk 2.CI.0/` is a third static surface in this repository, not a copied desk. The root
pipeline remains authoritative. Its ordered company-intelligence segment is:

The CI Ask endpoint is a separate owner-only edge function (`POST /api/ask`). It performs the
owner JWT check before any data/provider request, forwards the bearer only to the same-origin
`/data/company_intelligence.json` route, and never publishes model prose or client-supplied context
directly. Its offline contract, endpoint, and Ask UI checks are part of `scripts/preflight.py`.
The Ask tab keeps pending state per symbol, retries one expired bearer, discards stale responses,
and renders the nine deterministic answer sections with explicit blocked/unknown states. It is
safe to switch companies while a request is in flight; no client-side provider secret or raw
backend error is rendered.

1. `fetch_company_profiles.py` — monthly/failed-row retry DPS issuer profiles for the 20-company pilot.
2. `fetch_company_documents.py` — daily official PSX/PUCARS metadata plus at most 24 verified 12 MB PDFs in ignored current-run cache.
   Historical annual-report metadata can be seeded only by an explicit operator-reviewed JSON
   manifest passed to `fetch_company_documents.py --historical-metadata-manifest <path>`. The
   manifest is capped at five documents and is metadata-only: exact `psx:<digits>` id, matching
   numeric `official_document_id`, exact pilot `ticker`, current universe `company_name`, canonical
   `https://dps.psx.com.pk/download/document/<id>.pdf` URL, `title`, snake_case `type`, ISO
   `published_at` with `+05:00`, and `period: { "period_type": "annual|interim", "period_end":
   "YYYY-MM-DD" }`. It rejects raw text, facts, availability or download fields, and a dry run is
   available with `--dry-run`. Do not commit a production seed manifest unless the exact PSX title
   and company metadata have been source-reviewed first.
3. `document_intelligence.py` — immediate local extraction, page evidence, append-only events/changes and training-mode queue.
4. `build_financial_series.py` — evidence-linked, period-aware financial facts. Unknown period/unit/basis stays flagged, never guessed.
5. `fetch_issuer_sources.py` — weekly same-domain issuer page hashes and report-link index.
6. `stage_issuer_documents.py` — weekly, bounded same-domain issuer PDFs (maximum 16 per run), followed immediately by a second extraction/financial pass.
7. `build_source_qa.py` — compact source-health flags and URL index.
8. `build_company_graph.py` — deterministic company/document/fact/event/source graph with source URL/page provenance.
9. `build_change_intelligence.py` — source-backed digest of official filings, issuer-page changes, comparable financial movements and classified events.
10. `build_operating_events.py`, `build_driver_graphs.py`, `impact_engine.py` — offline,
    deterministic, evidence-gated event/driver/scenario products. Driver graphs cover all 20 pilot
    companies through nine declarative sector models; ENGROH has an explicit holding-company model.
    Event routing is filtered through each company's graph and never creates numeric impacts without
    sourced operands.
11. `build_peer_registry.py` — after `fetch_sectors.py` refreshes the retained PSX sector map,
    this emits the formal peer registry for the exact 20-company CI pilot. The only grouping
    rule is retained official sector label/code. Missing or duplicate pilot/sector state fails
    closed; singleton sectors publish an explicit empty `formal_peers` list; international peers
    remain unavailable.
12. `build_ci_slice.py` — the one bounded JSON file the CI app reads.
13. `build_event_studies.py` runs after indices/sectors and before the slice; it uses only retained
    oldest-first price history, strict pre-event baselines, calendar horizons, and ex-ante analogue
    cutoffs. KSE100-relative values mean stock raw return minus KSE100 raw return; unsupported
    financial outcomes stay null with named missing inputs.
14. `build_financial_model_inputs.py` builds offline v2 historical model inputs. Sector-driver
    registry coverage is qualitative routing coverage only; executable numerical adapters are tracked
    separately from that registry. The CEMENT adapter maps qualified reported actuals to the formal
    engine input seam for input-ready companies; other sectors remain adapter-unavailable, and all
    formal forecasts, valuations and market expectations still require explicit owner-approved
    assumptions before computing.
15. Document restaging is an explicit, owner-triggered two-batch workflow. The first batch is an
    allowlisted set of `psx:<digits>` IDs resolved from `research_index.json` and the exact pilot;
    transport uses a scoped run directory and metadata-only receipts. The owner-review manifest is
    generated separately from retained `financial_coverage.json` metadata only, and preflight fails
    if the manual execution allowlist drifts from that current review manifest. Shared extraction
    queues, cursors and source registries are untouched. Normal `run_cloud.py` is offline with respect
    to restaging; raw PDFs remain transient and preflight rejects them from served roots.
15a. `build_financial_reprocess_blockers.py` records the results of that approved first tranche
    without retrying it. It is an exact-ID metadata ledger for documents rejected by the existing
    size, page-count or text/geometry gates. It must never become a second transport path: it does
    not download PDFs, change caps/allowlists, extract values, write receipts, or activate a model.
    A future parser or source-policy change requires separate owner review before any new restage.
16. `build_company_scenario_lab.py` runs after fundamentals and quant, then before the CI slice. It
    publishes only dated snapshot operands, formula metadata and readiness. The browser supplies all
    revenue-growth, net-margin and P/E assumptions; generated state contains no selected case. The
    tool is sensitivity/reverse-solving arithmetic, not a forecast, valuation verdict or advice.
    EBITDA, FCF, DCF and forecast outputs remain blocked until qualified history exists.
17. `build_company_brains.py` runs immediately before the CI slice. The Brain is a compact reference
    index, not another fact store: producer IDs remain authoritative, every one of the 21 business
    domains has an explicit available/partial/unknown/blocked status, and the timeline carries typed
    references only. Forecast and valuation domains remain blocked and empty in v1.
18. `build_thesis_monitoring.py` converts retained signal clusters into deterministic read-only
    monitoring records before the Brain/slice build. Each record links back to its cluster and
    official evidence, exposes explicit prove/kill/watch checks, and uses only the canonical
    Strengthening/Stable/Weakening/Broken vocabulary. Single-source evidence is Stable, never
    promoted to Strengthening. This v1 does not store user-authored theses or calculate prices.
19. `build_intelligence_confidence.py` scores retained signal clusters through seven fixed,
    inspectable components whose weights sum to 100. Single-originator evidence cannot receive
    corroboration credit; historical and peer inputs come only from strict no-lookahead event
    studies. The UI displays producer scores without recalculating them, and Ask receives only a
    capped component summary without evidence payloads or URLs.
20. `build_guidance_contradictions.py` emits first-class qualitative management-priority,
    delivery-promise, project/capacity-action, stated-risk and operating-constraint objects only
    when retained same-company official document evidence has a strict assertion shape. Companies
    without qualifying objects publish explicit `no_guidance_objects`; contradictions are exact
    normalized-key conflicts among eligible objects only. The CI app displays the emitted rows and
    does not infer guidance, risks, contradictions, forecasts, valuation or advice in the browser.
21. `build_ci_monitoring.py` composes retained source QA, observed changes, events, exact-ID
    watchlist records and guidance contradictions into a 20-company monitoring pulse. It emits only
    categorical healthy/degraded/stale/unknown status and source-linked alerts. A page needs a prior
    retained hash before it is called changed; degraded sources are never treated as fresh; missing
    change activity does not turn an old source healthy.
21a. `build_event_review_windows.py` adds a read-only priority layer to that monitoring path. It
    retains known calendar rows with their supplied confirmation status, derives an expected results
    window only from a stable, retained past earnings cadence, and emits a five-day review range.
    It never schedules an agent, fetches a provider, predicts a filing, or creates an investment
    conclusion. Forward calendar dates are explicitly prospective review metadata rather than
    observed facts, and remain distinguishable from dated source evidence.
21b. `build_ci_work_routing_policy.py` makes the token boundary explicit. The roster-wide CI source
    scan is deterministic: official PSX disclosure metadata (`fetch_company_documents.py`), issuer
    freshness hashes (`fetch_issuer_sources.py`) and retained monitoring composition run across the
    exact pilot without AI. Targeted owner/AI review is only eligible from retained material changes,
    retained post-baseline source-change alerts or active event-review windows. One-time historical
    issuer link-index imports remain deterministic review metadata: `first_seen_at` is not treated
    as a document publication date or targeted-work trigger. The policy checker forbids 20-company
    daily per-ticker AI schedules, roster-wide AI sweeps and prompt payloads in generated state.
22. `build_financial_evidence_reconciliation.py` creates a separate financial evidence ledger from
    retained series, coverage, model-input and readiness state. It does not parse or fetch a filing,
    promote audit-only facts, choose through conflicts, or activate a forecast. Eligibility requires
    exact official PSX document/page provenance and availability after the reported period; unsafe or
    conflicting rows stay quarantined and missing annual slots remain explicit.
23. `build_ci_completion_matrix.py` emits the read-only completion audit after the current CI
    producers have run and before the private slice is built. It maps active product requirements to
    retained repo/state evidence, status, blockers and next required evidence; it never fetches,
    reprocesses, calls a model, applies SQL, publishes or claims unsupported blocked features are
    complete. The CI slice includes only a compact non-rendered summary, and
    `check_ci_completion_matrix.py` is wired into preflight.
24. `check_ci_global_no_lookahead.py` runs in preflight after the CI completion matrix. It compares
    parseable consumer-facing dates in emitted CI state and the private slice only when an explicit
    cutoff exists; a value after that cutoff fails, while opaque or no-cutoff fields are linted rather
    than inferred.
25. `build_financial_engine_assumptions.py` runs after forecast readiness and before the formal
    engines. It emits deterministic market operands (`current_price`, `shares_out`) from retained
    dated state and preserves any owner-approved records already in the assumptions file. For a
    company with three qualified annual observations it also emits explicitly typed historical
    reference cases for revenue growth and net margin. Those records carry `derived_value`, exact
    source facts and a `not_owner_approved_forecast_input` status; they never expose the formal
    engine's accepted `value` field. Net debt and P/E assumptions remain owner-approved inputs, so
    formal forecast, valuation and market-expectations products stay blocked until all required
    approvals exist. Private CI assumption drafts are approved only through the manual server-side
    `approve_owner_financial_assumptions.py` append-copy handoff; it is not part of the cloud run.
26. `build_financial_truth_qualification.py` runs after reconciliation and before
    `build_formal_financial_engines.py`. Financial truth is the authoritative fail-closed activation
    gate: the legacy three-period forecast-readiness status remains descriptive and cannot activate
    an output. The formal engines run before the CI completion matrix and private slice, emitting
    deterministic forecast, valuation and market-expectations products only when current qualified
    financial truth and approved, source-labelled, dated operands are both present; otherwise each
    product remains explicitly blocked with no numeric result. Its focused checker
    is both part of the cloud sequence and preflight.
27. `build_ownership_source_manifest.py` emits a review-only candidate list from retained issuer
    and PSX metadata for the exact 20-company pilot. It never downloads or parses a document and
    cannot activate ownership; page-level official evidence and owner approval remain required.

The scripts exit 0 and retain last-good durable state on provider failures. Raw pages and PDFs remain
under ignored `.cache/company_intel/`; no cloud agent, model key, paid browser, hosted database or new
Vercel feature is used. The approval queue does not invoke an agent: training mode requires the owner
to approve synthesis first. Local synthesis training uses `prepare_synthesis_batch.py`, the
`company-intelligence-librarian` and `company-intelligence-verifier` agents, and the deterministic
`company_brief_review.py` approval gate; durable briefs are written only after explicit owner approval.
CI slice shows a receipt-backed document as approved and complete only when its document ID and
content hash exactly match an append-only owner approval receipt; it never rewrites queue history or
receipts, and a stale hash remains pending.
Manual historical expansion uses `ci_backfill.py` in batches of at most five companies and at most five
batches per invocation. A durable cursor advances only after a completed batch; a failed provider keeps
last-good data and leaves the unfinished batch due for a later retry.

Wave 1 builders are safe on empty or partial inputs. Events require action-language evidence and a
source URL. Driver edges are labelled `declarative_assumption` until measured sector evidence is
available. Bear/Base/Bull probabilities are deterministic (25/50/25); revenue, EBITDA, EPS, FCF and
valuation impacts remain `null` with `insufficient_data` when sourced period/unit/currency inputs
are absent.

Hosting is a separate Vercel project rooted at `Henneth Desk 2.CI.0/`, with `ci.henneth.app` attached.
`/data/*` fails closed unless a verified Supabase
ES256 JWT carries the exact `sub` configured as `CI_OWNER_USER_ID`; a valid non-owner receives 403.
There is no CI signup, service-role key, schema change or order path. Presentation changes must not
alter `middleware.js`, the owner environment value, the project root, or the private no-store header.

### 1b. Company Intelligence production release (Event-to-Value Alpha)

`ci.henneth.app` must not receive a production deployment merely because a
commit reaches `main`. The release path is
`.github/workflows/ci-production-release.yml`: validate the repository,
restamp the CI artifact envelope to the release commit, deploy one preview,
run the public and protected smoke checks, then promote that exact preview
without rebuilding. The `ci-production` GitHub Environment scopes deployment
credentials to the two jobs that use them: the first Vercel preview action and
the later promotion. If required reviewers are available for the repository,
configure them there; GitHub environment secrets are unavailable to a job that
does not name that environment.

Required one-time Vercel/GitHub configuration (external to this repository):

1. Disable automatic Vercel Git production deployments for the CI project, or
   configure deployment protection so they cannot reach `ci.henneth.app`
   before the protected release workflow completes. This setting is not
   expressible in `vercel.json`; do not claim the policy is active until it is
   inspected in the Vercel project.
2. Create the protected GitHub Environment `ci-production`, with owner
   approval required, and add `VERCEL_TOKEN`, `VERCEL_ORG_ID`,
   `VERCEL_CI_PROJECT_ID` as environment secrets. The Vercel credentials are
   supplied only to the environment-scoped preview and promotion jobs and must
   never be copied into repository files, logs, or receipts. Add four more
   environment secrets for the authenticated smoke: `HENNETH_CI_OWNER_SMOKE_EMAIL`,
   `HENNETH_CI_OWNER_SMOKE_PASSWORD`, `HENNETH_CI_NON_OWNER_SMOKE_EMAIL`, and
   `HENNETH_CI_NON_OWNER_SMOKE_PASSWORD`. These are ordinary Supabase Auth
   accounts (the owner account must match `CI_OWNER_USER_ID`; the second must
   be a different account). The release job exchanges each pair at runtime
   through Supabase's password grant using only the existing public project URL
   and publishable key. Short-lived bearer tokens remain in process memory,
   are never printed or persisted, and must not be replaced with static token
   secrets.
3. Run **Henneth CI controlled production release** from `main`. It uploads an
   immutable, secret-free release receipt tied to the promoted commit. Retain
   that Actions artifact as the production proof; the checked-in
   `release_integrity_receipt.json` template is deliberately not a release
   approval.

The release receipt is green only with one matching commit across GitHub CI,
preview, production, the public login shell, owner private-data `200`, and
non-owner private-data `403`. The release HTTP smoke script never prints a
token, authorization header, or response body.

The root desk deployment also strips CI-owner-only source artifacts from `public/state/`:
`company_documents.json`, `company_briefs.json`, `company_brief_receipts.json`,
`document_synthesis_queue.json`, and the full `company_intel/` directory. Root `middleware.js`
returns a generic 404 for those paths before token validation as defense-in-depth, while ordinary
desk `/state/*` authorization stays unchanged. `scripts/check_root_state_publication.py` is wired
into preflight and must be updated with any future change to that boundary.

---

## 2. The ONE publish path — never hand-push state

**Always publish with `python scripts/publish.py "<message>"`. Never `git push` state files by hand.**

`publish.py` is the shared choke point every loop and the cloud use. It:
1. runs `preflight.py` (the pre-deploy gate) — **if it fails, nothing publishes**, last-good site stays live;
2. stages **`state/` only**, and commits only if something actually changed (a no-op otherwise);
3. pushes **race-safely** — the cloud cron and app loops both push to `main`, so on a rejected
   (non-fast-forward) push it rebases onto latest preferring our fresh state (`-X theirs`) and retries.
   Whatever the other side raced in regenerates next cycle, so nothing is lost.
4. A push to `main` is the entire deploy — Vercel auto-builds in ~60s. There is no separate deploy step.

### 2a. Shipping CODE — the `--code` flag (added 2026-07-19)

Staging is scoped on purpose. `publish.py` used to run a blanket `git add -A`, which staged the
whole working tree. The cloud cron and any number of interactive sessions share ONE checkout, so a
routine data refresh would sweep up whatever anyone else had open. On 2026-07-19 three commits
carried work their message never mentioned — a Desk Room coverage commit shipped another session's
in-progress `dashboard/app.js` and `scripts/push_send.py`.

The misleading history was the smaller problem: **committing a file nobody has finished editing can
publish broken code**, with nothing in the message to hint it happened. The same reasoning was
already in the file, applied to the wrong step — the rebase handler has always refused to
auto-resolve outside `state/` because that "could permanently discard someone's actual code edit."

| you are… | run |
|---|---|
| a data/agent loop (all but one task) | `python scripts/publish.py "<msg>"` |
| deliberately shipping code or docs | `python scripts/publish.py "<msg>" --code` |

Behaviour worth knowing:
- files outside `state/` are **listed, never silently included or silently dropped**;
- if only code changed and `--code` was absent, it prints **NOTHING PUBLISHED** rather than the
  misleading "nothing changed" — a skipped code fix is loud, not silent;
- the message argument is positional-only, so `publish.py --code` cannot commit with the literal
  message `--code`.

**Before passing `--code`, run `git status --porcelain`** and confirm every non-`state/` file is
yours this run. If something else is dirty it belongs to a concurrent session — stage your own paths
by name instead.

`psx-desk-code-review` is the **only** scheduled task that needs `--code`; it is the only one that
edits hand-authored files. Every other task is state-only and unaffected.

---

## 3. The safety gates (why the live site doesn't break)

Layered, so a bad cycle can't reach users and a transient glitch can't blank a page:

- **`preflight.py`** (before publish): re-reads every file the UI joins on; asserts shape, non-empty,
  no NaN/Infinity, and **per-ticker history completeness** (the "No data for XXX" class). Also runs
  free Tier-1 gates on every publish: **code syntax** (`check_code_syntax` — `ast.parse` all scripts +
  `node -c app.js`), the **root state publication boundary** (`check_root_state_publication.py` —
  root builds exclude CI-owner-only artifacts and middleware denies their request paths), and
  **accuracy/provenance** (`provenance_lint.py` — see §3b). Exits non-zero
  → `publish.py` aborts.
- **`watchdog.py`** (after publish): fetches the LIVE Vercel URLs a browser hits and checks they are
  reachable, fresh, non-empty, health not degraded, and sampled ticker histories serve. Wired into every
  publishing loop; if it fails, the loop re-publishes once then reports loudly. Run ad hoc:
  `python scripts/watchdog.py`.
- **`data_health.py`** (Rule 6): if `health.json.status != ok`, NO new signals generate that cycle
  (monitoring continues). `tv_crosscheck` feeds it but only a **genuine glitch** (close off >20% =
  decimal/split/wrong-symbol; widened 2026-07-15 to safely clear real corporate-action adjustment gaps)
  degrades health; TV lag/adjustment **drift** is advisory and never freezes the desk (a TV-vs-DPS
  mismatch is not an error — CLAUDE.md).
- **Client resilience** (in `app.js`): `j()` retries + XHR fallback + last-known-good; a router try/catch
  never leaves a blank screen; a 30-second auto-refresh self-corrects transient misses; the ticker page
  self-heals with retry.

---

## 3a. Code QA — the layer that was missing until 2026-07-15

The three gates above watch **data**, **build shape**, and **design** — none of them read the actual
**code** for correctness or security bugs. The repo has no tests and no linter (Python or JS), and pushes
directly to `main` with no PR/CI review, so nothing was catching real defects before they went live.
Two tiers now close this gap, deliberately NOT a `.github/workflows/*` CI file — see §5's gotcha on why
adding those needs the GitHub web UI; both tiers below avoid that entirely and need no owner action.

**Tier 1 — instant, free, every publish.** `check_code_syntax()` inside `preflight.py` (added 2026-07-15)
`ast.parse`s every `scripts/*.py` and runs `node -c dashboard/app.js`, and FAILS the gate (blocks publish)
on a real syntax error. Since `preflight.py` is the one gate every surface already runs through — the
cloud cron (`desk-data.yml` → `run_cloud.py` → `preflight.py`), every app-scheduled task, and any manual
`publish.py` call — this runs on literally every publish, everywhere, for zero added cost and no new
infrastructure. It catches "the build is broken" the moment it happens, not up to a week later.

**Tier 2 — weekly deep review.** `psx-desk-code-review` (Sat ~12:00 PKT) runs the `/code-review` skill
(8 finder angles — line-by-line, removed-behavior, cross-file, reuse, simplification, efficiency, altitude,
CLAUDE.md conventions — each candidate independently verified CONFIRMED/PLAUSIBLE/REFUTED before it's
reported) against the week's code diff. This is the one that catches things a syntax check can't: logic
bugs, security holes, silently-swallowed errors, dead code. Clear-cut, low-risk fixes are applied directly
and published through the normal gated path; genuine judgment calls (thresholds, design tradeoffs,
anything behavior-changing) are reported, not auto-fixed. Effort is `medium` for the routine weekly pass —
request a `high`/`ultra` pass explicitly before anything high-stakes (e.g. before turning on billing).
Weekly (not daily/per-push) by design: each pass spends real tokens (multiple agent calls), and a syntax
break is already caught instantly by Tier 1 — the deep pass exists to catch what only careful reading
catches, which doesn't need same-day turnaround the way a broken build does.

**First pass (2026-07-15, `high` effort, ~800-line session diff, first review this repo has ever had)**
found and fixed 10 real, verified issues, including: an XSS vector (a broker name could break out of an
`onclick` attribute — `esc()` didn't escape quotes; fixed globally + the call site converted to the same
safe `data-*` + delegated-listener pattern already used for the watchlist star), silent financial-data loss
(the portfolio "add holding" and private-note save paths discarded the real error and showed a false
"Saved ✓"), a governance gap (`tv_crosscheck.py`'s error/drift escalation only ever looked at the `close`
field — a genuine indicator-only glitch was invisible to both health-gating and the advisory log; and
`auditor.md` still instructed a literal `"FAIL"` string match against a status vocabulary that had moved to
PASS/DRIFT/ERROR, silently defeating the Auditor's veto per CLAUDE.md Rule 7), and an architecture fix to
`publish.py` itself (the race-safe conflict auto-resolve used to apply to the WHOLE working tree via
`git add -A` — a rebase conflict on any hand-authored file, not just regenerated `state/` data, could be
silently resolved by discarding the other side's edit with zero visibility; now conflict auto-resolve is
scoped to `state/` files only, and any conflict outside that aborts and fails loudly for a human to
resolve by hand instead of guessing).

---

## 3b. Accuracy QA — "are we presenting fact, not assumption?" (2026-07-15)

The desk's credibility is that it never shows an assumed/placeholder/stale number as fact. Two tiers:
- **Tier 1 (free, every publish):** `scripts/provenance_lint.py`, wired into `preflight.py`. Hard-FAILs
  (blocks publish) on: **stub markers** (TODO/PLACEHOLDER/TBD/lorem/`<INSERT` in any rendered state
  field), **hollow analysis** (a Desk Room `house_view` present but its summary/conviction empty), and
  **grossly stale analysis** (a house view computed at `price_at_session` now >30% from the live close).
  WARNs (surfaces, doesn't block) on 15–30% staleness. Deliberately unambiguous checks only — it never
  guesses whether a *target* price is "wrong" (that's a legit forward call, not an assumption).
- **Tier 2 (judgment):** the existing `room-verifier` agent already cross-examines each ticker's numbers
  against the data + web before a Room session publishes, and records its verdict in `rooms.json[SYM].qa`.
  The desk is already partly self-aware here — house views caveat their own soft spots (e.g. "leans on an
  unverified 30% growth assumption"). The weekly `psx-desk-product-scout` (§3c) reads those `qa` caveats to
  propose accuracy improvements.

Root Ask-the-desk (`api/ask.js`) has its own deterministic response gate in the same publish path:
`scripts/check_root_ask_hardening.mjs` verifies that client input is bounded and that model output cannot
publish advice language, URLs, prompt leakage, or number/date-looking claims absent from the exact
context slice supplied to the model. This is a per-request safety and spend bound; durable cross-request
quota/rate limiting still belongs in the deployment/provider layer (for example Vercel/Groq quota
controls or a real storage-backed limiter). Do not add an in-memory counter to the Edge function and call
it a rate limit — stateless instances will not share it.

## 3c. Self-improvement loop — the desk proposing its own upgrades (2026-07-15)

`psx-desk-product-scout` (weekly, Sun ~12:00 PKT, one cheap agent session) reads the live product + the
accuracy signals above and writes a **ranked backlog** to `state/product_backlog.json` across three
categories — **accuracy** (grounded in provenance-lint/qa findings), **clarity** (presentation), and
**feature** (new capability). It **proposes and ranks only — it never builds.** The owner picks items to
implement; implementation runs on demand through the normal gated path. This split (cheap looped ideation,
human-gated build) is the guardrail: it keeps the "improve ourselves" loop from becoming a token bonfire or
shipping machine-written features with no human in the loop. `score = impact(3/2/1) / effort(3/2/1)`, higher
first. Out of scope by rule: live per-visitor agent runs (impossible on static hosting) and any recurring
heavy-token feature.

---

## 3d. The astro pillar — how a differentiator stays honest (2026-07-17)

The desk runs a **Vedic (sidereal) astrology lens**. It exists only because it is **falsifiable**, and it
is built so it cannot quietly become a horoscope. Four layers, and the order matters:

| Layer | File | What it is | Cost |
|---|---|---|---|
| 1. Sky | `scripts/astro_engine.py` → `state/astro.json` | Where the nine grahas ARE + 90 days of dated events (ingress / station / conjunction / lunation / eclipse), each with a fixed 1–5 importance | free, pure math |
| 1b. Past sky | `scripts/astro_history.py` → `state/astro_history.json` | Daily sidereal positions 2007→today, **cached** | free, incremental |
| 2. Claims | `state/astro_map.json` | What tradition CLAIMS (sector significators, dignities). **Hypotheses, not evidence** | one-off |
| 2b. Falsification | `scripts/astro_backtest.py` → `state/astro_backtest.json` | Does any of it hold on 19y of PSX? | free |
| 3. Lens | `.claude/agents/room-astro.md` | Writes the read — **may only assert what survived** | ~1 cheap agent/week |

**The rules that keep it honest — do not soften these:**

1. **Dates are computed, never recalled.** CLAUDE.md Rule 2 with teeth. During the build, the model's own
   memory placed Rahu in the wrong sign, PSX's sector codes in the wrong sectors, and would have
   hardcoded a wrong ayanamsa. The computation was right every time. **No agent may state a transit date.**
2. **The ayanamsa is derived, not hardcoded** — Spica precessed from J2000 (Chitrapaksha definition),
   published in the JSON so it can be audited. `provenance_lint.py` fails the publish if it leaves the
   sane Lahiri band, if a graha goes missing, or if Rahu and Ketu stop being 180° apart.
3. **No natal charts for companies, ever.** PSX publishes no listing dates. A birth chart from a guessed
   date is invented input. Per-ticker astro = its sector's significators tested on its own history.
4. **`astro_map.json` is frozen on approval** (Rule 8 discipline). Changing a mapping = a v2 file with
   fresh tests, never an in-place edit — or every past astro score silently changes meaning.
5. **Astro never touches a trade.** No setups, no sizing, no gating. Strategist / Risk / Auditor never
   read it. It is a lens the desk reports and scores.
6. **Every read is a dated claim in `claims.json`** (`source_type: "astro"`), resolved against real prices
   and published on the Scores board — hits *and* misses, with the reason each worked or failed.
7. **"Nothing survived" is a publishable result**, not a failure. If the backtest kills a claim, the lens
   says the transit is happening and has no demonstrated effect, and stops there.

**Statistics (the integrity of the whole pillar — read before touching `astro_backtest.py`):**
- **Circular-shift permutation**, not day shuffling: returns are autocorrelated and astro windows are
  contiguous blocks. Shuffling days would manufacture significance.
- **Two-stage resampling.** A permutation p can't go below 1/(N+1). With ~350 hypotheses the Bonferroni
  bar is ~1.4e-4, so a 2,000-shift test could **never** reach it — "zero survivors" would have been an
  artefact of the method. Screen at 2,000; re-test anything at p≤0.01 with 50,000 (floor 2e-5).
- **Every graha is tested against every sector** — the only fair way to let the data pick a significator
  rather than the author. That means hundreds of hypotheses, so the Bonferroni bar is computed from the
  real test count and published alongside the expected number of false positives.
- **Known conservatism:** periodic masks re-align under rotation, so the test is biased *against* finding
  astro effects (verified: a planted +0.40%/day scored p=7.6e-4, not the 2e-5 floor). A null result is
  **"not demonstrated", never "disproved"**. Read effect sizes, not just p-values.

---

## 4. The seven app scheduled tasks (`~/.claude/scheduled-tasks/`)

Only run while the Claude app is open; catch up on next open. The 5 data/agent tasks each end with
`publish.py` + watchdog. The cloud cron now keeps DATA fresh 24/7, so these are primarily about the
**agent** work — but they still run `run_cloud.py` first (cheap, idempotent) as a local-freshness prereq
and a cloud-outage fallback.

| Task | When (PKT) | Does |
|---|---|---|
| `psx-desk-checkpoint-am` | **weekday 11:00** | data + **news-sentinel** + position **monitor**; escalates to full commentary only on impact ≥ 4 news |
| `psx-desk-checkpoint-pm` | **weekday 17:00** | same flow as above — see §4a |
| `psx-desk-daily-refresh` | weekday ~17:20 | macro + market-analyst **daily read** (≤120 words) |
| `psx-desk-room-loop` | weekday ~17:47 | the **Desk Room debates** — ≤3 full/day (budget gate), rest reaffirm free; QA + scoring |
| `psx-desk-weekly-harvest` | Sat ~11:00 | broker **calls** from the business press (Profit/Dawn/Mettis) + filings refresh |
| `psx-desk-code-review` | Sat ~12:00 | **Code QA** — see §3a. Not a data task; touches code only, never `state/`. |
| `psx-desk-product-scout` | Sun ~12:00 | **Self-improvement** — see §3c. Writes the ranked backlog; proposes only, never builds. |

Manual refresh (any session, no waiting for a task): the **`update-live-desk`** skill, or directly
`python scripts/run_cloud.py` (free data) then `python scripts/publish.py "..."`.

### 4a. Two fixed daily checkpoints, not hourly (changed 2026-07-14, simplified same day)

The intraday task no longer runs hourly — it fires exactly **twice a day, every weekday: 11:00 and 17:00
PKT**, for token efficiency (cut from ~8 runs/day to 2). An earlier version tried to align these to Mon–Thu
vs Friday's different market hours (open/break/close), which needed 3 separate tasks since one cron
expression can't hold multiple distinct (hour, minute) pairs — the owner simplified this to one uniform
time pair across all weekdays, which collapses cleanly to **2 tasks**: `psx-desk-checkpoint-am` (cron
`0 11 * * 1-5`) is the single source of truth for the whole flow; `psx-desk-checkpoint-pm` (cron
`0 17 * * 1-5`) is a thin pointer whose prompt just says "read and execute psx-desk-checkpoint-am/SKILL.md
verbatim". **To change checkpoint behavior, edit only `psx-desk-checkpoint-am/SKILL.md`.** Note: the
scheduler's human-readable `schedule` summary string has shown bugs on multi-value hour fields in the past
— trust `cronExpression` and `nextRunAt` from `list_scheduled_tasks`, not the summary text.

### 4a. Every agent pins its own model — task model is now a free choice (2026-07-20)

**Rule: every file in `.claude/agents/` MUST declare `model:` in its frontmatter. Never leave it
to inherit.**

Until 2026-07-20, eleven agents declared no model, so they silently ran on whatever model the
*calling task* happened to be set to. That list was not the harmless half — it was
`auditor` (which holds veto under Rule 7), `risk-officer` (Rule 4 limits), `strategist`
(position sizing), `monitor` (stop-outs), `news-sentinel` (impact 1-5, which gates escalation
under Rule 10), `market-analyst`, `macro-agent`, `reviewer`, `sector-debate`, `sector-chair` and
`fundamentals-agent`.

So switching a scheduled task to a cheaper model would have quietly downgraded the entire
governance layer — the parts specifically built to stop bad output reaching a user — with no
warning and no visible diff. The Room personas were unaffected only because they happened to pin
`sonnet` already.

All 22 agents now pin explicitly. Consequence: **the task's model only affects orchestration**,
so you can set any scheduled task to Haiku without touching analysis quality.

Worth knowing before you do: for the expensive task (the Room loop) the orchestrator is only
about **4% of spend** — 56 agents at ~15k each vs ~35k for the orchestrator — because the agents
write their own files rather than returning JSON through it. The tasks where a cheap orchestrator
would actually save real money are `psx-desk-daily-refresh` (it writes the daily prose) and
`psx-desk-code-review` (it reads the diff and edits source), and those are precisely the two
where the orchestrator's own judgment is the product. Cheap where it matters least, expensive
where it matters most.

To check nothing has regressed:
```
rg -L "^model:" .claude/agents/*.md      # any file listed here inherits — fix it
```

---

## 5. The cloud workflow — editing gotcha

`.github/workflows/desk-data.yml` runs the deterministic pipeline in the cloud.
**You cannot push changes to `.github/workflows/*` from this environment** — the git credential and `gh`
here lack GitHub's `workflow` OAuth scope. To add/edit it, use the **GitHub web UI** (repo → Actions →
edit the workflow → commit), or have the owner grant the scope. After a web edit, `git pull` to sync local.
Also ensure repo **Settings → Actions → General → Workflow permissions = Read and write** (so the job can
push refreshed data).

---

## 6. Hosting & data ownership

- **Vercel** serves the static site from committed files (`vercel.json` copies `dashboard/*` + `state/`
  into `public/`). Push to `main` = deploy. `Cache-Control: must-revalidate` is set, so users get fresh
  JS/CSS after each deploy (no stale-cache class on live; the local `serve.py` preview DOES cache — hard-
  reload it when testing).
- **Supabase** = auth + per-user data, plus a dedicated server-only CI archive; it never serves
  research data to a browser. Per-user, row-level-secured on
  the `profiles` table: `watchlist`, `notes`, `portfolio`, `followed_brokers`, `digest_prefs` (all jsonb).
  The client uses the publishable key (safe); the legacy service_role/anon keys are disabled.
  Lifecycle-email columns (added by `docs/lifecycle_email.sql`, not yet applied — see §8/§10):
  `activated_at`, `activation_type`, `signup_at`, `email_optout`, `unsub_token`. The first three are
  write-once/service-role-only (`activated_at`/`activation_type` via the `mark_activated` RPC,
  never a direct client upsert — `saveProfile()` cannot touch them). New table
  `lifecycle_email_log` (service-role only, RLS on with zero policies) tracks per-user/per-key sends
  and is the idempotency guard for the cron.
- **Dedicated CI archive, private theses and formal-owner inputs.** The Henneth CI Supabase project is provisioned with
  `company_theses`, `company_financial_assumptions`, five append-only archive tables, and a nonpublic PDF bucket; the archive receipt is
  `state/company_intel/supabase_archive_receipt.json`, the private-thesis schema receipt is
  `state/company_intel/private_thesis_storage_receipt.json`, and the reviewable archive contract is
  `docs/henneth_ci_archive.sql`. Archive tables have RLS enabled with no browser grants or policies;
  only the cloud-held service credential may write. The private-thesis receipt proves schema
  configuration only; it does not complete live storage until owner-token create/read/update/archive/
  restore/delete and cross-user RLS smoke tests are appended through
  `scripts/record_private_thesis_storage_verification.py` without secrets. The
  browser uses only a publishable key plus its bearer token. Archive/restore is normal; permanent
  deletion requires confirmation. The free cloud pipeline runs `supabase_ci_store.py` after the
  private CI slice, retaining metadata, facts, snapshots for every generated per-company CI research
  product, and ready current-run official PDFs. It
  dry-runs without its two cloud secrets and treats unavailable transient PDF bytes as a safe skip.
  A fully successful archive cycle appends a public, secret-free receipt (run key, payload hash,
  row counts and HTTP status classes) to `supabase_archive_receipt.json`; failed or partial runs
  record a secret-free failed latest attempt and never claim current archive health. An owner may run
  `python scripts/supabase_ci_store.py --verify-receipt` in the cloud environment after a successful
  sync: it makes one bounded, read-only lookup of that receipt's `ci_sync_runs` row and fails if its
  run key, completion time, payload hash, or row counts differ. It neither writes a new receipt nor
  runs as a publication gate, so a transient verification failure cannot disturb research publication.
  Any fair value is private user input, never Henneth output. The formal-assumption table is an
  append-only owner input ledger for growth, margin, exit P/E, and net debt. Its server-only
  importer reads only approved rows for `HENNETH_CI_OWNER_USER_ID`, uses approval date as the
  earliest eligible date, and does nothing until that ID plus the CI URL and service-key secrets
  are configured in the cloud. Draft approval is a separate manual server-only action:
  `approve_owner_financial_assumptions.py --row-id <uuid>` validates the owner, metric bounds,
  source label, optional HTTPS URL and rationale, then appends a new approved copy with the current
  timestamp. Missing secrets, failed fetches or invalid drafts are safe no-ops/degraded outcomes
  and must not print key material. The hardening contract in
  `docs/company_financial_assumptions_insert_hardening.sql` is applied to the dedicated CI project as migration `harden_owner_financial_assumption_drafts`
  (2026-08-27); it narrows authenticated inserts to unapproved drafts while leaving backend approval
  to the private credential path. It must not be applied to the legacy desk project as part of CI work.
- **Management Delivery is deterministic and conservative.** `build_management_delivery.py` runs
  after guidance, thesis and confidence state and before the CI slice. Its original thesis records
  remain limited to retained same-symbol official events that are strictly later than the latest
  source observation and exactly match an assertion/conflict key. A separate guidance record set
  compares first-class same-company guidance objects only; it requires strictly later availability,
  exact keys and incompatible modalities for a contradiction, while same evidence is excluded.
  Companies without qualifying guidance publish an explicit blocked state. The two record sets are
  never loosely merged or matched in the browser.
- **The Evidence Watchlist is an exact-link monitoring view.** `build_evidence_watchlist.py` joins
  active deterministic theses to their management-delivery, confidence and financial-readiness rows
  by source IDs within the same company. It shows confirm, break and next-evidence checks from retained
  state only. It never reads private user theses, performs loose text matching, or emits forecasts,
  probabilities, numeric impacts, valuation or advice.
- **Market Expectations Gap is caller-only algebra.** The Scenario Lab stores no selected case or
  gap. After the owner enters growth, margin and P/E, the browser subtracts caller growth from the
  reverse-solved growth required at the current price. It is not a forecast, probability or verdict.
- **Financial qualification is metadata-only.** `build_financial_coverage.py` maps official PSX
  document IDs and explicit annual-period wording for the exact pilot. Unknown periods stay unknown;
  half-year notices never become annual history; audit-only facts stay quarantined. Its candidate
  queue requires a later owner-approved bounded restage and does not authorize parsing or publishing.
- **Retained v2-candidate queue is review-only.**
  `build_financial_statement_v2_candidate_queue.py` lists only already retained annual PDFs whose
  source, content hash, file/page limits and pilot binding are intact but which lack v2 parsing.
  It cannot download, restage, parse, OCR, alter an allowlist, emit facts or activate a model.
- **Forecast readiness fails closed.** `build_forecast_readiness.py` accepts a financial period only
  when revenue, attributable PAT and basic EPS are aligned annual consolidated PKR facts from the
  current parser, have exact official provenance, no quality flags, and a publication date strictly
  after period end. Three such periods plus the CEMENT adapter can mark the formal-engine input seam
  ready; they do not approve revenue growth, net margin, exit P/E, net debt, forecasts, valuations or
  market expectations. The nine sector driver registries are qualitative routing coverage, not
  implemented numeric models.
- **Causal foundations are an evidence resolver, not a causal model.**
  `build_causal_foundations.py` creates one categorical row for every existing driver edge and may
  attach only retained same-company official events and strict baseline-before-event study records.
  Every row names its next data requirement; numeric impact, forecast and valuation stay blocked.
  Macro evidence remains excluded until the source layer exposes stable per-test identifiers.
- **Conditional benchmarks never recompute returns.** `build_conditional_benchmarks.py` resolves only
  exact event-type/subtype analogues already retained inside the target event study, requires every
  candidate to predate the target, and separates same-company from same-current-sector history.
  Horizon statistics remain null until at least three mature prior outcomes exist. Peer, international,
  financial-outcome and causal interpretations stay explicitly blocked without their registries/data.
- **Repo is private.** State data (incl. `history/`, `history_deep/`, `intraday/`) is committed so Vercel
  is self-contained.

---

## 7. Universe coverage — what tickers the desk tracks

`config/desk.json.universe` controls this. **As of 2026-07-19 the desk covers the WHOLE listed market
in two tiers — 554 symbols total.** `state/universe.json` writes a `tier` onto every symbol:

| tier | who | count | gets |
|---|---|---|---|
| `core` | KSE100 (top-N by weight) + full KMI30 | ~103 | the full pipeline — deep history, backtests, fundamentals, model fair value, signals, Desk Room debates |
| `listed` | every remaining **KSE All Share (ALLSHR)** constituent | ~451 | prices, quant measures, sector, dividends, a real searchable page — but *not* the expensive per-ticker analysis |

**Why two tiers:** covering only KSE100+KMI30 meant a genuine listed company (BBFL was the reported
case) did not exist in the product at all — search found nothing and there was no page to land on.
For a product users expect to be complete, an unsearchable listed company is a bug. But running 70
strategies × 19 years, plus a Yahoo deep-history pull and a fundamentals scrape, across 554 names is
not affordable per cycle. So: everything is *visible*, the core is *researched*, and the ticker page
says which it is (`coverageNote` in `pageTicker`) rather than letting empty sections imply the desk
looked and found nothing.

### 7a. The two gates — research vs signal (do not conflate them)

Tier is no longer what decides who gets analysed. **`state/liquidity.json` is**, via two
deliberately separate gates:

| gate | config | what it decides | count today |
|---|---|---|---|
| **research** | `liquidity.research_min_adtv_pkr` (5M) + `research_min_bars` (500) | what the desk *analyses* — backtests, fundamentals, predictability | 208 (core ∪ promoted listed) |
| **signal** | `risk.min_avg_daily_traded_value_pkr` (30M) | what the desk will ever *publish a setup on* | 100 |

They are different questions and must stay separate. A name can be fully researched and still
never produce a setup — that is the intended outcome for a thin stock, and the ticker page says
so out loud ("No setups will be published on this name") instead of showing an empty signal
section that reads as "the desk looked and found nothing".

Note the signal gate already excludes **38 of the ~103 core names** — index membership is not
liquidity. IBFL is the worked example: a core-tier constituent with a **median turnover of
~98,000 PKR/day**, where a single full position would be 82% of a normal day's entire volume.

**Per-symbol friction is the reason this matters.** `backtest.py` charges each name
`max(config friction floor, estimated round-trip spread)` from `liquidity.json`, not a flat
0.6%. A constant cost assumption flatters exactly the wrong names — Lesmond, Schill & Zhou
(2004) showed the stocks producing the largest momentum returns are the same stocks that cost
the most to trade, and most of this library is breakout/momentum. Switching this on removed
**64 of 591** previously "eligible" strategy-ticker pairs. Those were artefacts, not edges.

**If you add a per-ticker script, decide its gate explicitly.** Cheap pure-math scripts
(`quant.py`, `snapshot.py`, `compute_fairvalue.py`, `build_signals.py`, `data_health.py`,
`liquidity.py`) run across ALL symbols. Anything that hits the network per ticker, or is heavy
compute, MUST call the ONE shared helper — `psx_data.research_symbols()`. Do not hand-roll a
`tier == "core"` filter: three scripts each carried their own copy, so the rule could not be
changed in one place and a missed copy would silently analyse a different set than its peers.
`research_symbols()` fails CLOSED to core-only if `liquidity.json` is missing.

Already gated: `backtest`, `fetch_fundamentals`, `predictability`. Still core-only by tier
(genuinely core-specific, not liquidity questions): `fetch_deep_history`, `fetch_intraday`,
`astro_charts`. Rotation-bounded: `fetch_history` (`LISTED_PER_RUN=90`) and `fetch_dividends`
(`LISTED_DIV_PER_RUN=60`) — core refreshes every run and the long tail rotates stalest-first,
so a 554-symbol universe cannot outrun the 30-minute cron.

**Ordering constraint:** `liquidity.py` MUST run after both history fetches and before
`fetch_fundamentals` / `predictability` / `backtest` (it is placed accordingly in
`run_cloud.py`). Out of order, the gate silently falls back to core-only and the backtest
reverts to flat friction — no error, just quietly worse numbers.

`fetch_fundamentals` is threaded (6 workers): it is latency-bound, and serial it took ~10 min
at this universe size, which alone would blow the Actions budget. 208 names now take ~29s.

**Insider/off-market (`fetch_insider_offmarket.py`, weekly, same family as `fetch_fundamentals`).**
Writes `state/insider_activity.json` (filings, never pruned) and `state/offmarket_activity.json`
(off-market days, pruned to a 90-day trailing window) — both ACCUMULATE across runs rather than
being fully overwritten, so ≥3 months of history is retained even though PSX's own pages only show
a trailing window. Off-market pulls a plain static CSV (`dps.psx.com.pk/download/omts`, no
rendering needed); insider filings need the Firecrawl CLI (JS-hydrated announcements page) and
degrade to `stale: true` (keep prior file, exit 0) if Firecrawl isn't available that run. As of
2026-08-05 both files feed three ticker-page surfaces — Data flags, Signal Stack (`insiderLens`,
non-directional, excluded from confluence), and `build_explainer.py`'s "at a glance" — all
metadata-only per Rule 2, no direction ever inferred from a filing or an off-market print alone.

If a ticker a user searches for still doesn't appear, check `state/universe.json.symbols` first (is
it there?), then `config/desk.json.universe` (`cover_all_listed` still true? `kse100_top_n` capped?)
— don't assume it's a search bug.

**Cost note:** the deterministic layer (prices/quant/backtests) is free regardless of universe size —
more tickers just means more (free) compute time. Only the Desk Room **debates** are token-budgeted
(`deep_dives_per_day` in the Room config), and that budget is independent of universe size — a bigger
universe means the coverage queue is longer, not that any single cycle spends more tokens.

**Backfill note:** widening the universe requires a one-time full run of `run_cloud.py` (fetches history/
deep-history/fundamentals for the newly-added tickers — subsequent runs are fast again since
`fetch_deep_history.py` only pulls missing tickers). If done via the cloud cron, the first run may run
long; the 15-min timeout in `desk-data.yml` may need raising to ~25 min for that one run (web-UI edit
required — see §5). Preflight/publish gating means a timeout never publishes broken state either way —
worst case the backfill just continues on the next scheduled run.

---

## 8. Known gaps / honest notes

- **Sector concentration** in the portfolio tracker is by POSITION, not sector — the feed only has numeric
  sector codes (e.g. `0809`), no names. Building a code→name map would enable true sector grouping.
- **Lifecycle email (welcome/nudges/activated/digest)** is built — `scripts/lifecycle_email.py` +
  `scripts/email_templates.py` + `scripts/email_copy.py`, schema in `docs/lifecycle_email.sql` — but
  NOT yet live: the SQL hasn't been applied in Supabase, and the cron step can't be pushed from this
  environment (§5 — no `workflow` OAuth scope). Owner must: (1) apply `lifecycle_email.sql` by hand
  in the Supabase SQL editor, (2) add the three secrets (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
  `RESEND_API_KEY`) + the workflow step via the GitHub web UI. See §10 for the runbook once live.
- **Private CI thesis storage** has a configured-schema receipt in
  `state/company_intel/private_thesis_storage_receipt.json`, but live completion remains blocked until
  an owner browser session proves CRUD/archive/restore/delete and a separate authenticated identity
  proves the row cannot be read, changed, archived, restored or deleted across users. Record only the
  pass/fail outcome with `scripts/record_private_thesis_storage_verification.py`; do not record account
  identifiers, credentials, endpoints or thesis contents.
- **Legal pages** (`state/legal.json`, `/legal/*`) are DRAFTS — a Pakistani lawyer must review before
  charging (flagged in the file's `review_status`). Discoverable from: page footer, the sidebar bottom
  (`.side-legal`), the sign-in/sign-up modal (`.auth-legal`), and the Settings page.
- **Track record** is young (see the clock on the Scores page). Do not switch on paid billing until it
  matures — that clock is the honest gate.

---

## 9. Fixed bug class — `hidden` attribute silently overridden by CSS

The account-menu dropdown never actually closed (2026-07-14): `menu.hidden = true` was set correctly in
JS, but `.acct-menu{display:flex}` (an author-stylesheet class rule) unconditionally overrode the
browser's native `[hidden]{display:none}` default — author-origin CSS always wins over the UA default,
regardless of selector specificity. The element was visually always-open from the moment it was first
rendered; the JS toggle was a no-op the whole time. Proven with `getComputedStyle(el).display` while
`el.hidden = true`. Fixed with an explicit `.acct-menu[hidden]{display:none!important}` override — the
same pattern already used for `.searchbox[hidden]`.

**Rule going forward: any element toggled via the `hidden` DOM property MUST have a matching
`.class[hidden]{display:none!important}` CSS rule**, or the toggle silently does nothing. Checked
2026-07-14: only two such elements exist (`#searchbox`, `#acctMenu`), both now correctly overridden.
Re-checked 2026-07-26: a third had appeared — `#sideVer` (the sidebar version badge), added with
`display:flex` and no `[hidden]` rule, so the "no changelog yet" early-return left an empty bordered
bar pinned to the sidebar. Now overridden too. The class recurs; re-check whenever new UI lands.

---

## 9a. Fixed bug class — `vercel.json` takes NO comment keys (2026-07-20)

Three consecutive desk deploys went straight to **ERROR with zero build logs**. No logs at all is the
tell: the build never started, because Vercel validates `vercel.json` against its schema when the
deployment is *created*, and rejects unknown properties. The cause was `"_comment"` /
`"_comment_buildCommand"` keys added to explain the config — a habit that is correct in every other
file in this repo and silently fatal in this one.

**Rule: `vercel.json` and `site/vercel.json` carry no explanatory keys.** JSON has no comments, and
this particular JSON is schema-validated. Config reasoning goes here, in the runbook, instead.

Meanwhile the marketing site kept deploying fine, so `henneth.app` picked up the new branding while
`desk.henneth.app` sat on a commit from hours earlier. **A green marketing site is not evidence the
desk shipped** — the two are separate Vercel projects (`henneth-site`, `psx-trade-desk`) off one repo.
Verify the desk by fetching something only the new build would contain, not by loading the site.

### What the current desk config does, and why

- **`buildCommand` copies the whole `dashboard/` directory**, not a hand-listed subset. The old list
  was `index.html app.js themes.css` only — which meant `sw.js` and `push.js` had *never shipped*, and
  every icon/manifest/OG asset would have 404'd in production while working perfectly in local dev.
  Wholesale copy is self-maintaining for future assets.
- **`rm -f public/app.html`** is the one deliberate exclusion. `dashboard/app.html` is a stale
  duplicate shell predating the sign-in gate; serving it would expose an ungated-looking copy of the
  terminal at `/app.html`. Removed *after* the copy so the wholesale rule stays intact.
- **`/state/*.json` gets `max-age=60, stale-while-revalidate=900`.** `max-age=0` forced a full
  revalidation round-trip for every state file on every navigation, and a ticker page opens ~23 of
  them — the main reason mobile navigation felt broken. The data itself is rewritten on a 30-minute
  cycle, so a 60s browser-fresh window cannot show anything the cycle would not have shown anyway.
  Genuinely intraday files (`live.json`, `health.json`, `runlog.json`, news) are fetched with a
  per-request cache-buster in `app.js` and bypass this entirely, so they are never served stale.
- **Images/manifest get 1 day + SWR.** Not `immutable`: the filenames are unhashed, so a real logo
  change must still be able to propagate.

---

## 10. Lifecycle email runbook (`scripts/lifecycle_email.py`)

Not live yet — see §8. Once the owner applies `docs/lifecycle_email.sql` in Supabase and adds the
three secrets + workflow step, this is how to run and check it.

**CLI:**
- `python scripts/lifecycle_email.py` — dry run (default). Prints who's due for what, sends nothing.
- `python scripts/lifecycle_email.py --send` — dry run + actually calls Resend.
- `python scripts/lifecycle_email.py --test <user_id>` — force one user through the due-window
  logic regardless of timing, for template/rendering checks. Combine with `--send` to actually
  deliver it.
- `python scripts/lifecycle_email.py --only <key>` — restrict to one email key (`welcome`,
  `nudge_24h`, `activated`, `digest_<ISOyear>-W<week>`, `nudge_7d`).
- `python scripts/lifecycle_email.py --requeue-stale` — re-check `lifecycle_email_log` rows stuck
  in a non-terminal status (e.g. Resend call failed after the log-insert step).

**Due windows** (a user qualifies for exactly one key per run, first match wins):

| key | condition |
|---|---|
| `welcome` | immediate on first run after signup |
| `nudge_24h` | ≥24h, ≤72h since signup, not activated |
| `activated` | fires once on `activated_at` |
| `digest_<ISOyear>-W<week>` | activated, digest pref on, ≥7d since signup, user's sharded weekday |
| `nudge_7d` | ≥7d, ≤14d since signup, not activated |

**Caps:** `DAILY_CAP = 90`, `MONTHLY_CAP = 2800` (Resend free tier is 100/day, 3,000/month — capped
below the ceiling on purpose). `time.sleep(0.6)` between sends. Digest sends are sharded by
`hash(user_id) % 5` across weekdays so the whole activated base doesn't queue on one day.

**Idempotency:** every send inserts into `lifecycle_email_log(user_id, email_key)` (unique
constraint) *before* calling Resend. A retry that hits the same `(user_id, email_key)` gets a 409
on the insert and is skipped — this is what makes double-running the cron safe, not app-level
dedup logic.

**Checks before flipping `--send` on for real:**
1. Dry run must show **zero** existing users due on first run — if it doesn't, `LIFECYCLE_EPOCH`
   in the script is wrong (would blast the whole existing user base with "welcome"). Stop and fix
   before sending anything.
2. `--test <own user_id> --send` → open the result in Gmail and Outlook. Confirm square corners,
   monospace fallback, the "Research · not advice" footer, and a working unsubscribe link.
3. Run the CLI twice in a row with `--send` — second run must skip every email it just sent (the
   409-on-insert path above), not re-send.
4. Set `DAILY_CAP = 2` temporarily and confirm the script actually stops after 2 sends in a run.

**Unsubscribe:** `/unsubscribe?t=<uuid>` (dashboard route, ungated) calls the anonymous
`email_unsubscribe(p_token, p_scope)` RPC, which flips `email_optout` and returns a boolean. Test
it from a signed-out browser — the whole point is it must not require a session.

**Rollback:** delete the workflow step in `.github/workflows/desk-data.yml`. Nothing else in the
desk depends on this script running — it only reads `profiles`/`state/*.json` and writes to
`lifecycle_email_log`.

---

## 9b. THE ACCOUNT GATE — `/state/` is no longer public (2026-07-21)

Until this date the sign-in screen gated the INTERFACE but not the DATA. Every file under
`/state/` was a plain static asset, so this returned 4.7 MB to anyone, with no account:

```
curl https://desk.henneth.app/state/backtests.json
```

The whole research product — `rooms.json`, `dossiers.json`, `fairvalue.json`, `claims.json`,
`strategy_map.json`, `quant.json` — was one `wget` away. **`middleware.js` at the repo root now
closes that.**

### How it works
- Vercel **Edge Middleware**, matcher `/state/:path*`. It runs BEFORE the static asset is served,
  so files stay on the CDN and only gain an auth check. A serverless proxy was rejected: `state/`
  is ~92 MB across 729 files, which would blow the function bundle and add a cold start to each of
  the ~23 fetches a ticker page makes.
- Verification is **local Web Crypto against Supabase's published JWKS**. This project signs
  access tokens with **ES256** (asymmetric P-256) and publishes the public half at
  `/auth/v1/.well-known/jwks.json`, so there is **no shared secret to store** and no auth round
  trip per request. If the project is ever switched back to legacy HS256 symmetric keys, `alg`
  stops matching and every request fails CLOSED — the correct direction to fail.
- `dashboard/app.js` attaches `Authorization: Bearer <access_token>` on every `state/` fetch.
  On a 401 it refreshes the session once and retries, so an hour-old tab recovers instead of
  appearing broken.
- CI-owner-only source artifacts are not ordinary desk state. The root build removes
  `company_documents.json`, `company_briefs.json`, `company_brief_receipts.json`,
  `document_synthesis_queue.json`, and `company_intel/`, and middleware returns a generic 404 for
  the same paths before checking a bearer.

### The one deliberate exception
`natal_ephem.bin` and `natal_ephem.json` stay public (`PUBLIC_FILES` in `middleware.js`).
`/cast` is the top of the acquisition funnel — a stranger casts a birth chart, gets value, and it
follows them into the account they create. Those two files are an astronomical ephemeris: public-
domain physics anyone can compute, containing zero desk output. **Add to that set only if the same
test passes** — is it public knowledge that happens to be cached here, rather than something the
desk produced?

### Do not "simplify" this
The token read in `app.js` uses **localStorage first and the `sb` client only as a fallback**.
That is not redundancy: `sb` is a `const` declared ~5,400 lines below `j()`, and touching a const
in its temporal dead zone throws ReferenceError — `typeof` does not save you, it throws too. This
file has hit that exact bug three times. The fallback is wrapped in try/catch for the same reason.

`SB_STORAGE_KEY` in `app.js` must track `SB_URL` and the boot script in `index.html`. If the
Supabase project ref changes and that string does not, every request silently loses its token and
the desk 401s on everything.

### Verified (2026-07-21)
12 adversarial cases pass, including `alg:none`, HS256 alg-confusion, unsigned tokens, missing
`exp`, expired tokens, and a self-signed token carrying the real `kid`. Live: all research files
401, ephemeris 200, app shell 200.

**Regression check** — this must stay 401 forever:
```
curl -s -o /dev/null -w "%{http_code}" https://desk.henneth.app/state/rooms.json   # expect 401
```

---

## 9c. ANALYTICS — two tags, two properties, and one failure mode that is silent (2026-07-22)

Both properties carry **GA4** (`G-5PLLEK6RYC`, deliberately the same measurement ID on both, so a
visitor who reads a blog post and then signs up stays one session) and **PostHog** (US cloud,
project 522643).

| surface | GA4 | PostHog token comes from |
|---|---|---|
| `site/` → henneth.app | `Base.astro`, PROD **+ hostname guard** | `PUBLIC_POSTHOG_PROJECT_TOKEN` at **build time** |
| `dashboard/` → desk.henneth.app | `index.html`, hostname guard | **hardcoded** in `index.html` — the desk has no build step |

**The silent failure.** `site/.env` is gitignored, so the marketing build's token can only come
from Vercel. If `PUBLIC_POSTHOG_PROJECT_TOKEN` is missing or scoped to the wrong environment, the
build **succeeds**, the page **loads**, every `capture()` call **returns normally**, and nothing is
ever recorded. There is no error anywhere. `posthog.astro` now refuses to initialise without a
token specifically so the failure is "no data" rather than a phantom install, but you still have to
know to look.

- Both variables live in Vercel → **henneth-site** → Settings → Environment Variables.
- **Scope them to Production.** Every Vercel preview builds in production mode, so a
  Preview-scoped token pours preview traffic into the same project as real visitors — the
  identical mistake GA4 made here once (see the comment above the gtag block in `Base.astro`).
- Neither needs the "Sensitive" flag. Both are public keys that ship in page HTML; marking them
  sensitive only stops *you* reading them back.

**Check it's alive** (expects the token in the built HTML — empty means the env var did not reach
the build):
```
curl -s https://henneth.app/ | grep -c "phc_"      # expect 1, not 0
```

**The desk's funnel events** are in `dashboard/app.js` via one `track()` helper that fires to GA4
and PostHog together: `gate_viewed`, `auth_validation_failed`, `signup_started` / `signin_started`,
`signup_pending_confirmation`, `signup_completed` / `signin_completed`, `signup_failed` /
`signin_failed` (carrying the raw Supabase reason). `identifyUser()` binds the PostHog session to
the Supabase **user id — never the email**, and calls `posthog.reset()` on sign-out.

`signup_pending_confirmation` and `signup_completed` are deliberately separate. With email
confirmation on, a successful `signUp()` returns no session: the account exists but the person is
not in yet. Merging the two would report a conversion rate the desk does not have.

---

## 9d. Fixed bug class — the orphaned marker field (2026-07-26)

The Chair stage was removed from the Desk Room for regulatory reasons (SECP Reg 2(ha) — see the
`room-chair` agent header). Nothing writes `house_view` any more. But `room_gate.py` still keyed its
"has this ticker ever been covered?" test off `house_view`, so every Room session written *after* the
removal would be re-planned as `full` — "never covered" — on every subsequent cycle, forever. The
REAFFIRM (0 tokens) / DELTA (~5k) / FULL (~25k) tiering the module exists to provide would have
quietly stopped tiering, at ~25k tokens per name per cycle. It did not show up in testing because all
42 sessions already in `state/rooms.json` were written *before* the removal and still carry the field:
the bug is invisible until the first new session lands. `room_apply.py` had already been switched to
`ta_memo` for exactly this reason; the gate was simply missed.

**Rule: when a pipeline stage is removed, grep for every field it was the sole writer of, and fix
every consumer in the same commit.** `grep -rn "<field>" scripts/` — a field with readers and no
writer is a live bug, not dead code. As of 2026-07-26 `house_view` still has three remaining readers
(`build_explainer.py`, `provenance_lint.py`, `room_verify.py`); those degrade gracefully today
(absent field → section omitted) but they are the same trap and should go when convenient.

Related, same week and same shape: `.side-ver` was added with a `hidden` attribute and a
`display:flex` class rule, re-introducing §9's bug class in a third element — so §9's "only two such
elements exist" line is now stale. Rotation-based fetchers are a third instance of "correct sibling,
wrong copy": `fetch_dividends_deep.py` merges prior output before writing, `fetch_dividends.py` did
not and was deleting every symbol outside the current batch. **When a module has a sibling that
already solves the same problem, copy the sibling.**

---

## 9e. Fixed bug class — a UTC date compared against a PKT trading date (2026-07-26)

`new Date().toISOString().slice(0,10)` returns the **UTC** calendar date. Every date in `state/` is a
**PKT** trading date (CLAUDE.md, "all timestamps are PKT"), and PKT is UTC+5 — so between 00:00 and
04:59 PKT that expression names *yesterday*. For a display stamp that is cosmetic. For a
**comparison** it is a real off-by-one for five hours every day: the new `date >= today` filter on the
earnings / ex-dividend rails kept a results date that had already passed listed as "next", with a
negative countdown beside it.

`dashboard/app.js` now exports a `todayPKT()` helper (defined next to `fmt`); **any date comparison
against `state/` data must use it.** Detection: `grep -n "toISOString().slice(0, *10)" dashboard/app.js`
and ask of each hit — is this value *compared* to a state date, or only *printed*? Compared → must be
`todayPKT()`. Printed → leave it. As of 2026-07-26 the two comparison sites are fixed and ~14 display
sites are intentionally untouched, so the grep is noisy by design; the question, not the count, is the
test. One deliberate exception: `paperCreditDividends` — under UTC lag it *delays* a dividend credit,
and crediting late is safer than crediting early.

Same review, adjacent shape worth naming: `scripts/score_fundamentals.py` ranked a **live-priced** P/E
against a peer array built from the vendor's **weekly scrape-time** ratio. Both numbers were correct;
they were just not the same vintage. **When a value is re-derived from fresh data, re-derive the
comparison set the same way** — otherwise the two agree the day after a refresh and drift apart all
week, skewing every cheap/fair/expensive verdict in the same direction.

---

## 9f. Fixed — root `vercel.json` build command reverted to an allow-list (2026-07-26)

Went from an explicit `cp` list to `cp -r dashboard/. public/ && rm -f public/app.html` at some point —
a deny-list. Harmless while `dashboard/` held only public assets, but the day anything gets dropped in
there for local testing, it ships. `build_public_slice.py` states the opposite principle for `state/`
data: "if it is not explicitly allowed out, it does not go out." Same principle applies to code.

Reverted to an explicit `cp` of each of the 18 tracked files in `dashboard/`, **except `app.html`** —
that file is a stale pre-rebrand duplicate of `index.html`, still tracked in git, deliberately never
shipped. Adding a new file to `dashboard/` that should reach the live site now requires adding it to
the `cp` list in `vercel.json` by name — that's the intended friction, not an oversight if the deploy
doesn't pick it up.

---

## 9g. Fixed bug class — a compliance gate keyed on MUTABLE state, not on the frozen record (2026-08-01)

`room_score.py` keeps the desk's own per-named-stock calls off the published leaderboard — a hard SECP
Reg 2(ha) requirement (§4 of `docs/PUBLICATION_RESTRUCTURE_V2.md`). It implemented that as
`if styp == "persona" and c.get("ticker") in uni_syms` — i.e. "is this ticker in `universe.json`
*right now*". But a claim's `ticker` is **frozen when the claim is written**; the universe is not. PSX
renames and delists constantly (this quarter: `UBL`→`UBLXD`, `DCR`→`DCRXD`, `LOTCHEM`→`LOTCHEMXD`, and
106 newly-added tickers in one preflight warning). So **24 pending named-stock persona claims had
already aged out of the universe** and were queued to resolve straight onto the public leaderboard with
no human gate — two of them dated to resolve the very day this was found. Nothing failed loudly; the
filter *looked* correct and the leaderboard was empty only because nothing had resolved yet.

**Rule: a gate must test the compliance-relevant FACT recorded on the record, not a lookup into
state that can drift out from under it.** Here the fact is "does this claim name a security" —
`c.get("ticker")` — which cannot change after the claim is written. Ask of any filter guarding a
publishing or safety boundary: *if the reference data changes tomorrow, does this quietly start
letting things through?* If yes, it is keyed on the wrong thing. Detection: grep for membership tests
against `universe.json` / `sectors.json` / any regenerated map inside a gate —
`grep -rn "in uni_syms\|in .*_syms\|universe.json" scripts/` — and check each is a *lookup* (fine) not
a *gate* (suspect).

Adjacent shape from the same review, and it inverts §9e's lesson: `score_fundamentals.py` had started
"deriving" the payout ratio as `div_yield × LIVE price / EPS`, on the stated reasoning that the
vendor's scraped figure was computed off a stale price snapshot. But payout is **DPS/EPS — both terms
are rupees per share and neither depends on price at all**. Since `div_yield` was scraped against the
vendor's *own* price, the reconstruction returned `DPS × (live price / scrape price)` and scaled payout
by pure price drift: a name that doubles with no change to its dividend or earnings reads as paying out
twice as much of its profit, flipping the `≤75%` "generous & covered" test and tripping the `>90%`
"stretched" warning on nothing but a rally. §9e correctly says *re-derive the comparison set the same
way you re-derived the value*; the prior question is **does this quantity depend on price at all?**
`live_pe` genuinely does (P/E is price ÷ earnings) and is correct. Payout does not. Before "freshening"
a ratio with a live price, write out its algebra and check the price term is actually there.

**Follow-on, found 2026-08-08 in the fix itself.** `abbb1627` replaced the above with the correct
`DPS / EPS`, but guarded it on `if dps is not None and eps:` — truthiness, which only rejects zero.
For a lossmaking company the division runs anyway and yields a *negative* payout ratio: live state had
`PKGS -169.67%` and `SSGC -17.42%`. Downstream, `score_fundamentals.py` tests `payout <= 75` for
"sustainable" — which a negative number passes — so the site was ready to tell a subscriber that a
loss-making company pays "-170% of profit — sustainable." **When a ratio is only meaningful over a
positive denominator, guard on the sign, not on truthiness.** `if x:` and `if x > 0:` differ on exactly
the inputs that make the ratio nonsense.

---

## 9h. Fixed bug class — a shared-helper refactor silently defeated by a local shadow (2026-08-08)

`f0eab9f6` ("Dedupe indicator math + JSON I/O across scripts") added
`from indicators import rolling_max as _roll_max, rsi as _rsi, sma as _sma` to the top of
`strategy_engine.py` — and the file's own `def _rsi(...)` and `def _roll_max(...)` further down
**re-bound both names at import time**, so every call site kept using the local copies. The
consolidation was real in the diff and inert in the runtime; two of the three "deduped" helpers had
simply been re-shadowed by the code they were meant to replace. Nothing errored, nothing warned, and
the duplicate bodies stayed live and free to drift apart from the shared ones.

**Rule: after moving a helper into a shared module, delete the local definition in the same commit —
an import alone does not win.** In Python the last binding at module scope wins regardless of order of
appearance, so an import at line 25 loses to a `def` at line 40 every time. Detection, run over any
"dedupe"/"consolidate"/"extract helper" commit:

```bash
python - <<'PY'
import ast, pathlib
for p in pathlib.Path("scripts").glob("*.py"):
    t = ast.parse(p.read_text(encoding="utf-8"))
    imported = {a.asname or a.name for n in ast.walk(t) if isinstance(n, ast.ImportFrom) for a in n.names}
    for n in t.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in imported:
            print(f"{p}:{n.lineno}: local def {n.name}() shadows the import of the same name")
PY
```

Before deleting a shadow, prove the two are equivalent rather than assuming it — here both were checked
numerically against the shared versions over a 300-bar random series (`np.array_equal(..., equal_nan=True)`
→ identical for `rsi` and `rolling_max`) so the removal was a provable no-op, not a hopeful one.

---

## 10. If the live site looks wrong — triage order

1. `python scripts/watchdog.py` — is it stale, degraded, or serving empty? It tells you which.
2. If **degraded**: read `state/health.json.problems`. A `tv_crosscheck ERROR` = a real data glitch;
   `drift` in `advisories` = benign TV lag (ignore).
3. If **stale** (`updated` old): a deploy didn't propagate or no cycle ran — run `run_cloud.py` +
   `publish.py`, or trigger the cloud workflow (Actions → Run workflow).
4. If a **single ticker** is blank: check `state/history/<SYM>.json` exists and is non-empty; preflight
   should have caught a broad gap. The client self-heals transient misses (retry button/auto-retry) — a
   one-off "couldn't load" that clears on retry is normal transient behavior, not a data bug.
4b. If a user reports **every ticker / all pages** blank at once, but `curl`ing the live state files and
   `watchdog.py` both show healthy 200s with real data: this is almost always CLIENT-side — either (a) a
   browser extension (ad/anti-fraud blocker) monkey-patching `window.fetch` and throwing on same-origin
   requests (the reason `j()` in app.js has an XHR fallback), or (b) the user was on the page during the
   ~60s Vercel deploy-propagation window right after a publish. Verify server-side health FIRST (curl the
   state files + `watchdog.py`) before assuming a data bug — don't guess from a screenshot alone. Ask the
   user to hard-refresh or try a different browser/incognito if it's reproducible.
5. If a ticker can't be **found in search**: see §7 — check it's actually a tracked constituent before
   assuming a search bug.
6. Never fix by hand-pushing — fix the data, run `publish.py`, let the gates pass.
7. **Whenever you change something structural** (universe size, a config default, a new per-user table, a
   new loop) — update this file (`docs/OPERATIONS.md`) and, if it affects a scheduled task's behavior, that
   task's `SKILL.md` in the same turn. Docs going stale is how future sessions break things they don't
   know changed.

---

## 11. Web Push (watchlist alerts) — **BUILT, INERT, NOT ACTIVATED** (2026-07-19)

Browser push notifications for watchlist events. **Fully written and currently doing nothing.** It
cannot activate on its own: it needs VAPID keys only the owner can generate, and absent keys are the
designed off-state — no registration, no permission prompt, no network call, no UI. Every existing
visitor's experience is byte-identical to before this landed.

### The pieces

| file | role | live today? |
|---|---|---|
| `dashboard/sw.js` | service worker: `push` → notification, `notificationclick` → `/ticker/SYM` | no — nothing registers it, and it is **not copied by `vercel.json`'s buildCommand** |
| `dashboard/push.js` | client helper, global `window.PSXPush` | no — not in `vercel.json`, not in `index.html` |
| `docs/push_subscriptions.sql` | the per-user table + RLS | **not applied** to Supabase |
| `scripts/push_send.py` | the sender (cron/manual; a static host can't push) | runs, prints "not configured", exits 0 |
| `state/push_queue.json` | alerts awaiting delivery | does not exist; absent = nothing to send |

`sw.js` deliberately has **no fetch handler and no caching** — the site's freshness guarantee
(`must-revalidate`, §6) is the product, and a caching worker would be a route to serving stale prices.

### The client API (`window.PSXPush`)

`configure({vapidPublicKey, sb, userId})` → returns `available()`; call on sign-in and sign-out ·
`available()` → bool, **false until keyed** · `status()` → `"unavailable" | "denied" | "on" | "off"` ·
`subscribe()` / `unsubscribe()` → `{ok:true}` or `{ok:false, error}` with stable reasons
(`unavailable`, `not_signed_in`, `denied`, `dismissed`, `save_failed`) · `renderToggle(hostEl)` →
paints a toggle, or writes an **empty string and attaches nothing** when unavailable, so it is safe
to call unconditionally. Nothing throws.

### Owner action required to activate (nothing happens until all five)

1. **Generate the VAPID keypair** yourself — e.g. `npx web-push generate-vapid-keys`, or
   `python -c "from py_vapid import Vapid01 as V; v=V(); v.generate_keys(); print(v.public_key, v.private_key)"`.
   The private key is a credential: it never enters the repo, a state file, or a log.
2. **Add repo secrets** (GitHub → Settings → Secrets and variables → Actions):
   `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (`mailto:you@…`), `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY` (service-role — server-side only; it bypasses RLS, so it must never
   reach the client bundle). Then expose them as `env:` on the push step of the workflow.
3. **Apply the table**: run `docs/push_subscriptions.sql` in the Supabase SQL editor. It adds
   `push_subscriptions` to the per-user layer described in §6 (owner-only RLS, four explicit
   policies, `on delete cascade` from `auth.users`).
4. **Ship the files**: add `dashboard/sw.js dashboard/push.js` to `vercel.json`'s `buildCommand`
   copy list (it currently copies only `index.html app.js themes.css`), load `push.js` from
   `index.html`, and set `window.PSX_VAPID_PUBLIC_KEY` (the *public* key only) before it — or pass
   it via `PSXPush.configure()`. **`sw.js` must be served from the site root** for `scope:"/"`.
5. **Install the dependency deliberately**: `push_send.py` needs `pywebpush`. It detects the absence
   and reports it rather than installing anything — adding a package to the cron that publishes the
   live site is a reviewed decision, not a side effect.

Until step 4 the site cannot even see these files. Reverting is deleting the same five things.
`push_send.py` is safe to schedule *now*: with no env keys it prints one line and exits 0 (Rule:
never crash the cycle).

