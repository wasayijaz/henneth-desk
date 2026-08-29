# Henneth — Architecture as it exists today

Written for a coding agent joining with zero previous context. Read this before adding a module. The most common failure in this repo is a second implementation of something that already works.

This describes the live product, not a target design. Operations live in [OPERATIONS.md](OPERATIONS.md). Governance lives in [CLAUDE.md](../CLAUDE.md). Sharp edges live in [GOTCHAS.md](GOTCHAS.md). Known debt lives in [TECH-DEBT.md](TECH-DEBT.md).

---

## 1. System overview

Henneth is a research publication and research terminal for the Pakistan Stock Exchange, with a thin global-markets layer for context. It never places orders. Execution is manual.

There are two public surfaces, one owner-only surface, three Vercel projects, and one private Git repo:

| Surface | URL | Source | Vercel project |
|---|---|---|---|
| Marketing site | https://henneth.app | `site/` (Astro, static) | `henneth-site`, root directory `site/` |
| Research terminal | https://desk.henneth.app | `dashboard/` + committed `state/` | `psx-trade-desk`, repo root |
| Company Intelligence | https://ci.henneth.app | `Henneth Desk 2.CI.0/` + generated private slice | separate CI project, root directory `Henneth Desk 2.CI.0/` |

The product is a hybrid of five parts:

1. Deterministic Python (`scripts/`) fetches, measures, scores, backtests, and writes JSON into `state/`. This runs in GitHub Actions even when the owner's computer is off. No LLM. No tokens.
2. Judgement agents (`.claude/agents/` + `prompts/`) run on the owner's machine. They write analysis back into `state/`. Visitors read the saved analysis 24/7; agents refresh it, they are not needed to serve it.
3. The terminal (`dashboard/`) is a static path-routed SPA. It reads `state/*.json` over HTTPS. It writes nothing to `state/`.
4. Supabase holds auth, per-user rows, and the dedicated Henneth CI append-only archive. It never serves research to browsers: current research is still rendered from the private generated CI slice.
5. Vercel serves static files. Edge middleware gates `/state/*` and CI `/data/*`. The CI project also exposes a separate owner-only `Henneth Desk 2.CI.0/api/ask.js`: it verifies the Supabase ES256 owner claim, loads only the requested company row, projects it through `api/ask_contract.js`, and builds the final answer/citations server-side around qualitative model output.

    PSX DPS / Yahoo / Firecrawl / TV
                    |
                    v
     scripts/  --writes-->  state/*.json  <--writes--  local agents
                    |
          +---------+------------------+
          |                            |
          v                            v
     gated copy on                allow-listed extract
     desk.henneth.app/state/*     site/src/data/public/*
     (account required)                    |
          |                                v
          +---- publish.py --> git push --> Vercel --> henneth.app

---

## 2. Major modules and who owns what

| Concern | Owner (change this, not a copy) | Consumers |
|---|---|---|
| Prices, calendars, dividends, history | `scripts/psx_data.py` + the fetchers | every later script, the terminal |
| Canonical PSX identity | `psx_data.canonical_symbol` / `split_board_state` — temporary XD/XB/XR board suffixes collapse to the ordinary ticker at universe intake | `update_universe.py`, `snapshot.py`, public extract |
| Universe + market mapping | `scripts/update_universe.py`, `config/markets.json`, `psx_data.yahoo_symbol` / `market_symbols` / `research_symbols` | every per-ticker script |
| Research vs signal eligibility | `scripts/liquidity.py` -> `state/liquidity.json`; `psx_data.research_symbols()` | backtest, fundamentals, predictability, fair value, signals |
| Indicators | `scripts/indicators.py` | `quant.py`, `strategy_engine.py`, backtests |
| Strategy rules | `strategies/*.json` + `strategies/library.json` | `strategy_engine.py`, `backtest.py`, `build_signals.py` |
| Position sizing (Rule 4) | `CLAUDE.md` is the rule. Computed in `scripts/build_signals.py`. Shown in `dashboard/app.js` `deskSize()` and `site/src/scripts/calculators.ts` `sizePosition()` | practice book, marketing calculators |
| Risk limits published to the client | `scripts/build_dashboard.py` writes `state/desk_rules.json` (allow-list of rule constants only) | `app.js` `loadDeskRules()` |
| Health gate (Rule 6) | `scripts/data_health.py` -> `state/health.json` | signal generation, terminal banners, watchdog |
| Publish gate | `scripts/preflight.py` | `publish.py`, `build_dashboard.py`, the cloud workflow |
| CI contract gate | `.github/workflows/ci-contract.yml` | rebuilds deterministic CI artifacts from retained state in a clean checkout, then runs preflight; never fetches, publishes, or accepts stale generated state |
| Live-site gate | `scripts/watchdog.py` | after every publish |
| Account gate (data) | `middleware.js` | every `/state/*` request on the terminal |
| Root state publication boundary | `scripts/root_state_publication.py`, `scripts/check_root_state_publication.py`, `scripts/vercel_build.sh`, `middleware.js` | excludes CI-owner-only artifacts from root `/state/*` and fails closed on matching request paths |
| Account gate (UI) | `dashboard/app.js` `OPEN_ROUTES` / `gateAllows()` | clean dashboard paths |
| Per-user data | Supabase `profiles` + RLS | `app.js`, the Chrome extension |
| Public marketing extract | `scripts/build_public_slice.py`, `scripts/build_astro_lite.py` | Astro pages under `site/` |
| Ask-the-desk | `api/ask.js` (Groq) | `/ask` and the context rail |
| Company profile source | `scripts/fetch_company_profiles.py` -> `state/company_profiles.json` | CI slice, Room dossiers, explainer, ticker overview |
| Official company documents | `scripts/fetch_company_documents.py` -> existing `state/research_index.json` + transient ignored PDF handoff | deterministic document extraction |
| Page evidence, facts and events | `scripts/document_intelligence.py` -> `state/company_documents.json`, `state/company_event_ledger.json` | CI slice, approval queue |
| Issuer source registry | `scripts/fetch_issuer_sources.py` -> `state/company_intel/source_registry.json` | CI Sources view |
| Company financial series | `scripts/build_financial_series.py` -> `state/company_financial_series.json` | CI Financials view, graph, synthesis handoff; owner-approved manual claims enter only through `scripts/manual_financial_claims.py` after manifest, dual-review and provenance checks |
| Company source QA | `scripts/build_source_qa.py` -> `state/company_source_qa.json` | CI source-health badges and graph |
| Company knowledge graph | `scripts/build_company_graph.py` -> `state/company_intel/company_graph.json` | CI Graph view |
| Company change intelligence | `scripts/build_change_intelligence.py` -> `state/company_intel/change_intelligence.json` | CI Changes view and overview metrics |
| Judgment handoff | `scripts/document_queue.py` -> `state/document_synthesis_queue.json` | owner-approved local synthesis only |
| Synthesis training batch | `scripts/prepare_synthesis_batch.py` -> ignored `.cache/company_intel/training_batch.json` | local librarian/verifier agents |
| Approved CI briefs | `scripts/company_brief_review.py` -> `state/company_briefs.json`, `state/company_brief_receipts.json` | CI Brief view |
| Company Intelligence slice | `scripts/build_ci_slice.py` -> `Henneth Desk 2.CI.0/data/company_intelligence.json` | private CI app only |
| Operating events | `scripts/build_operating_events.py` -> `state/company_intel/operating_events.json` | evidence-backed Wave 1 index derived from canonical documents/events; v1 closed registry declares the five genuinely supported event classes, source systems and no-lookahead rules |
| Signal clusters | `scripts/build_signal_clusters.py` -> `state/company_intel/signal_clusters.json` | versioned closed registry for source-qualified acquisition and management-change propositions; unsupported or future/unsafe evidence is rejected rather than clustered |
| Sector driver graphs | `scripts/build_driver_graphs.py` + `sector_driver_models.py` -> `state/company_intel/driver_graphs.json` | full 20-company pilot across BANKS/CEMENT/E&P/REFINERY/FERTILIZER/AUTO_ASSEMBLER/POWER/OMC/HOLDING_COMPANY; declarative routing only, no company values |
| Impact scenarios | `scripts/impact_engine.py` -> `state/company_intel/impact_scenarios.json` | graph-filtered event-to-driver Bear/Base/Bull scaffolding; numeric impacts remain null without sourced inputs |
| Historical event studies | `scripts/build_event_studies.py` -> `state/company_intel/event_studies.json` | one raw-price benchmark per canonical event; strict pre-event baselines and calendar horizons |
| Conditional historical benchmarks | `scripts/build_conditional_benchmarks.py` + `conditional_benchmarks.py` -> `state/company_intel/conditional_benchmarks.json` | exact event-type/subtype same-company and same-sector analogue resolver over existing event-study outcomes; source-derived candidate-evidence summaries expose thin history while statistics remain suppressed below three mature prior observations |
| Causal driver evidence map | `scripts/build_causal_foundations.py` -> `state/company_intel/causal_foundations.json` | one categorical evidence row per driver-graph edge, resolving only same-company official events and strict event studies; no causal estimate or numeric impact |
| Financial statement v2 facts | `scripts/financial_statement_facts.py` -> retained financial series/model inputs | conservative geometry-backed income, balance-sheet and cash-flow facts; every line is restricted to its local statement heading, text fallback stays audit-only, and manual claims retain a distinct source method/revision |
| Cement operating evidence | `scripts/build_cement_operating_series.py` -> `state/company_intel/cement_operating_series.json` | audit-only retained official cement operating observations; current seed emits DGKC company series and explicit MLCF/LUCK insufficiency/missing gates, with no forecast, valuation or model-input activation |
| Cement historical reconciliation | `scripts/cement_historical_reconciliation.py` -> `state/company_intel/cement_historical_reconciliation.json` | joins only upstream-qualified annual Revenue/PAT/EPS actuals to an independently fail-closed operating-driver lane audit; audit-only observations, missing publication dates and unqualified issuer bindings remain excluded, and the product cannot register an adapter or emit a forecast |
| Financial model inputs | `scripts/build_financial_model_inputs.py` -> `state/company_intel/financial_model_inputs.json` | exact pilot, provenance-gated reported history and null-safe derivations; qualitative sector registries and executable numerical adapters are separate seams |
| Financial qualification coverage | `scripts/build_financial_coverage.py` -> `state/company_intel/financial_coverage.json` | metadata-only official PSX document map, evidenced annual slots, quarantined audit-only coverage and bounded-restage candidates; never infers values |
| Financial-truth qualification | `scripts/build_financial_truth_qualification.py` + `financial_truth_qualification.py` -> `state/company_intel/financial_truth_qualification.json` | strict retained-evidence scorecard ranks a leading candidate without making it golden; requires five annual income triplets, eight qualified reported-quarter fact sets, five annual operating-cash-flow periods, an official share-count tie-out and no unresolved canonical conflicts before a financial-truth claim. It is the authoritative fail-closed activation gate for formal engines; document metadata remains separately labelled as non-qualifying coverage |
| Retained v2 financial-statement review queue | `scripts/build_financial_statement_v2_candidate_queue.py` -> `state/company_intel/financial_statement_v2_candidate_queue.json` | exact-pilot metadata-only queue of already retained annual PDFs inside the existing source, file and page limits that lack v2 parsing; owner review required, never downloads, restages, parses or activates facts |
| CI restage review manifest | `scripts/build_ci_reprocess_manifest.py` -> `config/ci_reprocess_review_manifest.json`; `scripts/check_ci_reprocess_manifest.py` | owner-reviewable metadata-only filing restage manifest derived only from retained financial coverage; preflight locks the separate execution allowlist to this current manifest |
| Forecast/valuation readiness | `scripts/build_forecast_readiness.py` + `forecast_contract.py` -> `state/company_intel/forecast_readiness.json` | exact input-qualification contract over annual consolidated official facts; sector-driver registry coverage is tracked separately, the current CEMENT adapter marks only the formal-engine input seam ready, and formal numeric outputs remain blocked without owner-approved assumptions |
| Financial engine assumptions | `scripts/build_financial_engine_assumptions.py` -> `state/company_intel/financial_engine_assumptions.json`; `config/owner_financial_assumption_handoff.json`; `scripts/import_owner_financial_assumptions.py`; manual `scripts/approve_owner_financial_assumptions.py` | deterministic source-labelled market operands (`current_price`, `shares_out`) plus explicitly non-forecast historical reference cases for revenue growth and net margin from three qualified annual facts; the local handoff lists missing owner-reviewed records without values or activation, and private Supabase drafts remain approved only by an explicit server-side append-copy handoff |
| Formal financial engines | `scripts/build_formal_financial_engines.py` + `formal_financial_engines.py` -> `financial_forecasts.json`, `formal_valuations.json`, `market_expectations.json` | deterministic forecast, valuation and reverse-expectations algebra; all products remain blocked until qualified actuals plus approved, source-labelled, dated market operands and owner-approved forward/valuation assumptions exist |
| Snapshot Scenario Lab | `scripts/build_company_scenario_lab.py` -> `state/company_intel/scenario_lab.json` | caller-supplied sensitivity, reverse-expectations and market-gap algebra over dated fundamentals/prices; generated state never selects a forecast or house case |
| Persistent Company Brain | `scripts/build_company_brains.py` -> `state/company_intel/company_brains.json` | compact 21-domain, five-type reference index over authoritative profiles, approved briefs, operating events, resolvable event studies and an exact per-company pointer index into retained CI source products; it never re-derives their facts |
| Thesis monitoring | `scripts/build_thesis_monitoring.py` + `thesis_monitoring.py` -> `state/company_intel/thesis_monitoring.json` | source-cluster-linked inference records with canonical Strengthening/Stable/Weakening/Broken states and explicit prove/kill/watch checks; no user thesis storage in v1 |
| Private user theses | Supabase `company_theses` + owner-only RLS | authenticated CI create/edit/archive/restore/delete; separate from deterministic thesis monitoring; schema-configured receipt lives at `state/company_intel/private_thesis_storage_receipt.json`, while live completion still requires owner-token CRUD and cross-user RLS proof recorded by `scripts/record_private_thesis_storage_verification.py` |
| Intelligence confidence | `scripts/build_intelligence_confidence.py` + `intelligence_confidence.py` -> `state/company_intel/intelligence_confidence.json` | transparent seven-component scores over retained signal clusters using source quality, independence, strict analogues, financial readiness, completeness and recency |
| Management delivery | `scripts/build_management_delivery.py` + `management_delivery.py` -> `state/company_intel/management_delivery.json` | preserves categorical event-based follow-through for active theses and adds a separate first-class guidance record set; both require same-company, exact normalized keys, strictly later availability and self-source exclusion |
| MLCF/PIOC event-model readiness manifest | `scripts/build_mlcf_pioc_readiness_manifest.py` -> `state/company_intel/mlcf_pioc_readiness_manifest.json` | compact read-only blocker/input checklist for the retained MLCF acquisition-control case; preserves official refs and known deal fields, records PIOC outside the CI pilot, and hard-blocks formal output without a generic economic engine |
| Guidance & contradictions | `scripts/build_guidance_contradictions.py` + `guidance_contradictions.py` -> `state/company_intel/guidance_contradictions.json` | strict qualitative management-priority, delivery-promise, project/capacity-action, stated-risk and operating-constraint objects from retained same-company official evidence only; exact normalized-key contradictions only, no numeric forecasts, valuation, advice or browser inference |
| Financial evidence reconciliation | `scripts/build_financial_evidence_reconciliation.py` + `financial_evidence_reconciliation.py` -> `state/company_intel/financial_evidence_reconciliation.json` | source/page/availability-ledger for retained financial facts and earnings-bridge readiness; preserves audit-only records, quarantines conflicts and lookahead/provenance failures, and cannot activate forecasts, valuation or market expectations |
| Approved restage blocker ledger | `scripts/build_financial_reprocess_blockers.py` -> `state/company_intel/financial_reprocess_blockers.json` | exact-ID, metadata-only record of why the owner-reviewed first tranche could not be restaged within current PSX file/page/parser gates; it never downloads, parses, changes allowlists, writes receipts, emits values, or activates a financial engine |
| Historical earnings bridges | `scripts/build_earnings_bridges.py` + `earnings_bridges.py` -> `state/company_intel/earnings_bridges.json` | consecutive, conflict-free annual Revenue/PAT/EPS deltas from eligible retained facts; source-linked descriptive history only, never a forward input or formal-engine activator |
| Owner-approved training receipt view | `scripts/build_ci_slice.py` + `check_training_receipt_reconciliation.py` | read-only effective synthesis status in the CI slice reconciled by exact document ID and content hash against append-only owner approval receipts; queue history and receipt records remain unchanged |
| CI continuous monitoring | `scripts/build_ci_monitoring.py` + `ci_monitoring.py` -> `state/company_intel/monitoring.json` | deterministic per-company source freshness and retained-change pulse composed from existing source QA, change, event, watchlist and guidance state; statuses are healthy/degraded/stale/unknown and every emitted alert has retained source provenance |
| CI event review windows | `scripts/build_event_review_windows.py` -> `state/company_intel/event_review_windows.json` | exact 20-company retained calendar plus conservative historical-cadence review windows; five-day priority windows are deterministic metadata only, never scheduled agent work, an inferred filing, a forecast, or an action |
| CI work routing policy | `scripts/build_ci_work_routing_policy.py` -> `state/company_intel/work_routing_policy.json` | deterministic route contract that keeps roster-wide official disclosure and issuer freshness scans non-AI, and allows targeted owner/AI review only from retained material changes, retained post-baseline source-change alerts or active event windows; historical issuer `first_seen_at` link imports stay review metadata, never targeted-work triggers |
| CI release integrity | `scripts/build_ci_artifact_integrity.py`, `scripts/check_ci_artifact_integrity.py`, `.github/workflows/ci-production-release.yml`, `scripts/check_ci_vercel_deployment_commit.py` | seals generated CI artifacts to one build cutoff and, during CI/release, to the exact deployed source commit; checked-in generated artifacts validate their own hashes without pretending to contain their containing commit SHA. Production is permitted only through a protected, tested-preview promotion whose live Vercel metadata resolves to that exact commit and deployment id; external Vercel/GitHub configuration remains a required owner-controlled boundary |
| CI completion matrix | `scripts/build_ci_completion_matrix.py` -> `state/company_intel/completion_matrix.json`; `scripts/check_ci_completion_matrix.py`; `scripts/check_ci_product_contracts.py` | source-independent audit map from active Company Intelligence requirements to retained repo/state evidence, current status, blockers and next required evidence; the aggregate gate executes every matrix-referenced product/UI/security checker outside preflight recursion, while the CI slice carries only a compact non-rendered summary |
| CI global no-lookahead lint | `scripts/check_ci_global_no_lookahead.py` | scans emitted CI state and the private slice against explicit local/product cutoffs; opaque dates are reported but never guessed, while a provable future consumer-facing date fails preflight |
| Evidence watchlist | `scripts/build_evidence_watchlist.py` + `evidence_watchlist.py` -> `state/company_intel/evidence_watchlist.json` | exact-ID monitoring index over deterministic theses, delivery, confidence and financial readiness; exposes what would confirm or break a signal without forecasting or loose matching |
| Formal peer registry | `scripts/build_peer_registry.py` -> `state/company_intel/peer_registry.json` | exact 20-company CI pilot grouped only by retained PSX official sector label/code; formal peers are explicit pilot-sector cohorts, singleton sectors emit empty peer groups, and international registry stays unavailable |
| Ownership source review | `scripts/build_ownership_source_manifest.py` -> `config/ownership_source_review_manifest.json` | metadata-only 20-company official-source review queue for annual-report schedules and PSX substantial-holder/free-float candidates; cannot fetch, extract or activate ownership facts |
| Bounded document restage | `reprocess_company_documents.py` + metadata receipts under `state/company_intel/` | explicit first-batch IDs, scoped transient run directories, no shared queue mutation |
| Company Intelligence data gate | `Henneth Desk 2.CI.0/middleware.js` | `/data/*` on the CI Vercel project |
| Company Intelligence Ask UI | `Henneth Desk 2.CI.0/app.js` + `styles.css` | owner-only Ask tab; per-symbol request state and nine server-owned answer sections |
| Company Intelligence Ask UI gate | `scripts/check_ask_henneth_ui.mjs` via `scripts/preflight.py` | 20-row static UI/auth/citation/section/responsive verification |
| Company Intelligence navigation | `Henneth Desk 2.CI.0/app.js` + `styles.css` | exact 17-tab primary company navigation plus separate read-only research-tools row; domain views consume the CI slice only, while formal peers render the emitted registry and unavailable ownership, earnings and formal-valuation products stay explicit |
| Company Intelligence navigation gate | `scripts/check_company_navigation_ui.mjs` via `scripts/preflight.py` | exact tab order/routing, tab-row keyboard isolation, 20-row rendering, emitted peer-registry rendering, blocked-state and no-browser-peer-derivation contract |
| Brand / plan copy on the marketing site | `site/src/site.config.ts` | every Astro page |
| Desk Room scaffolding | `scripts/room_*.py` | Room agents; terminal Room surfaces |
| Astro pillar | `scripts/astro_*.py` | `/astro`, `/cast`, `/mychart`, `/financial-astrology` |

If you are about to add a helper, search this table first.

---

## 3. Frontend / backend relationship

There is no application server for the research product.

**Terminal (`dashboard/`)**

- `index.html` is the shell. It loads `auth-terminal.js`, `app.js`, `rail.js`, `topbar.js`, `board.js`, `shell.js`, `icons.js`, `i18n-ur.js`.
- Routing uses clean URL paths (`/today`, `/ticker/LUCK`). `route()` in `app.js` is the sole
  dispatcher; in-app navigation uses the History API and browser back/forward arrives through
  `popstate`. Supabase auth callbacks still arrive in the URL hash and are handled separately —
  those callback fragments are not dashboard routes.
- Data access is `j(filename)` in `app.js`. Locally it reads `../state/`; live it reads `state/` and attaches the Supabase bearer token. Middleware verifies that token. There is an XHR fallback because some browser extensions break `fetch`.
- `app.js` is about 7,300 lines and owns almost every page. Adjacent files own chrome, not product rules.
- `app.html` is a stale pre-gate shell. `scripts/vercel_build.sh` copies the whole `dashboard/` then deletes `app.html` so it is not served.

**Marketing site (`site/`)**

- Astro 5, static output, no server adapter.
- Hermetic on purpose: the marketing build must not import `../state/`. It reads only `site/src/data/public/*`, which Python writes.
- Waitlist / plan-interest posts from the browser to Supabase (`site.config.ts` points at table `waitlist`).
- Calculators are client-side TypeScript. The position-size tool is a deliberate second copy of Rule 4 — both copies name each other in comments.

**Chrome extension (`extension/`)**

- Read-only companion. Detects a ticker on TradingView or PSX DPS, reuses the desk session token, shows the same public-safe research. Not on the publish path.

---

## 4. Important data flows

### 4a. Cloud refresh (free, no agents)

`.github/workflows/desk-data.yml` runs `python scripts/run_cloud.py` then `python scripts/publish.py`.

`run_cloud.py` is the ordered list. Do not reorder casually. Two order invariants:

1. `liquidity.py` must run after both history fetches and before `fetch_fundamentals` / `predictability` / `backtest`. Out of order, `research_symbols()` falls back to core-only and backtests silently charge flat friction.
2. `build_astro_lite.py` must run after `astro_engine.py`. It writes into `site/`, never `state/`.

`build_public_slice.py` runs in `run_cloud.py` after the research it reads (and after `build_astro_lite.py`). It writes only the allow-listed extract into `site/src/data/public/`. `publish.py` commits that folder as generated data, same as `state/`. Adding a field to `state/` still does not publish it. If a pilot name is temporarily missing from the universe (for example an ex-dividend suffix like `FFCXD`), the extractor keeps the last published public row and marks it `stale` rather than deleting the marketing page.

### 4b. Local judgement cycle

`prompts/cycle-full.md` (pre-market / escalation) and `prompts/cycle-light.md` (intraday). Agents read `state/`, write `state/`, then the same `publish.py`. The cloud never holds an Anthropic key.

Deterministic `build_signals.py` already publishes candidate setups labelled `basis: "backtest-proven, unaudited"`. The Auditor can later upgrade a setup. Those are different objects. Do not collapse them.

### 4c. What a signed-in visitor sees

Browser loads `index.html` / `app.js` (public) -> `sb.auth.getSession()` -> `Authorization: Bearer ...` -> `middleware.js` -> CDN `state/*.json`.

A signed-out visitor can load the shell and a short open-route list (`cast`, `mychart`, `legal`, `plans`, `glossary`, `shipped`, `unsubscribe`). Almost every research file still returns 401. The UI gate and the data gate are independent; do not assume one covers the other.

### 4d. What a marketing-site visitor sees

Astro pages rendered from `site/src/data/public/tickers.json` (pilot names), `astro_lite.json`, `coverage.json`, `strategy_levels.json`, `context.json`. No fair-value method values, no verdicts, no backtest stats, no Desk Room, no predictability. That allow-list is the product boundary. Adding a field to `state/` does not publish it.

### 4e. What the private Company Intelligence app sees

`fetch_company_profiles.py` retains sourced DPS issuer profiles. `fetch_company_documents.py`
incrementally indexes official PSX/PUCARS announcements in the existing research index, can merge an
explicit metadata-only historical seed manifest for at most five exact `psx:<digits>` official IDs,
and makes a bounded, ignored current-run PDF handoff. `document_intelligence.py` immediately extracts page-linked
evidence, conservative facts/events, append-only changes, a training-mode approval queue, and transient
full-page financial normalization; it makes no model call. `build_financial_series.py`,
`build_source_qa.py`, `build_company_graph.py`, and `build_change_intelligence.py` turn retained
evidence into period-aware financial rows, source-health flags, an evidence-linked graph, and a
deterministic "what changed" digest. `fetch_issuer_sources.py` weekly discovers same-domain issuer
pages and report links from the official DPS profile. `stage_issuer_documents.py` safely downloads a
bounded same-domain PDF set into the existing transient extraction handoff; the same document
intelligence and financial-series modules consume it immediately. Raw HTML/PDF bodies are not committed.

Model synthesis is training-mode only. `prepare_synthesis_batch.py` writes a compact ignored handoff for
the librarian/verifier agents. `company_brief_review.py` is the deterministic approval gate: it validates
document/page citations, blocks advice language, requires a clean verifier receipt, and writes durable
briefs only after explicit owner approval.

`build_ci_slice.py` joins the bounded private view into one generated file under
`Henneth Desk 2.CI.0/data/`. The app reads no other state file and never calls a market provider.
Its separate Vercel project uses `Henneth Desk 2.CI.0/` as the project root. The shell and sign-in form load publicly, but
middleware verifies the existing Supabase ES256 access token and serves `/data/*` only when the
signed `sub` equals `CI_OWNER_USER_ID`. No owner UUID, service-role key or signup path lives in the
repository. Private user theses use the separately reviewed `company_theses` RLS contract. The
dedicated CI project has a secret-free schema receipt at
`state/company_intel/private_thesis_storage_receipt.json`, but the browser surface is not considered
live until owner-token CRUD and cross-user RLS smoke tests are recorded by the secret-free,
append-only local recorder; the UI still treats an absent or inaccessible table as an explicit
not-activated state.

Wave 1 Company Intelligence runs after the second `document_intelligence.py` /
`build_financial_series.py` pass. It derives operating events from the append-only event ledger
and retained evidence, builds only the three declared sector driver models, then emits scenarios
before the slice. The pilot boundary is exact equality with `company_profiles.pilot.symbols`.

---

## 5. Database ownership

The live desk remains on Supabase project `qteoncckohuoatbjjykb` for Auth and per-user data.
Dedicated project `wexonytulckejkynncvv` (**Henneth CI**) is the server-only, append-only archive
for retained company source documents, source-linked facts, and deterministic CI snapshots. It has
RLS enabled, no browser grants, and a private `ci-documents` PDF bucket. It is configured but not
yet receiving writes until the cloud-only sync credential is installed; see
[`henneth_ci_archive.sql`](henneth_ci_archive.sql) and
`state/company_intel/supabase_archive_receipt.json`. The archive selection covers every generated
per-company CI research product, including operating evidence, historical bridges, scenarios and
future formal-engine states; cursors, transient review artifacts and receipts stay out. After a fully successful archive cycle, the
adapter appends a public, secret-free sync receipt keyed to the remote `ci_sync_runs` row; a failed
or partial response records a failed latest attempt and never claims current sync health. The optional
`supabase_ci_store.py --verify-receipt` path makes a single server-only, read-only lookup of the known
remote `ci_sync_runs` record and checks its stable key, completion time, payload hash, and row counts
against the local receipt; it is deliberately not a publication gate and does not mutate receipt state.

Live today, as described in [OPERATIONS.md](OPERATIONS.md) section 6 (there is no checked-in migration of the live schema):

- `auth.users` — Supabase Auth.
- `profiles` — one row per user, RLS owner-only. Client-writable fields include `watchlist`, `notes`, `portfolio`, `followed_brokers`, `digest_prefs`. `plan` is not client-writable (`freeze_plan` / `force_free_plan` triggers). Also holds onboarding / astro-board / strategy-board / language / theme.
- `waitlist` — marketing-site inserts.

Applied to the dedicated Henneth CI project:

- `docs/company_theses.sql` — private per-user company theses for the exact 20-company CI pilot.
  It grants authenticated CRUD only behind four owner predicates, revokes public/anonymous access,
  bounds every input and labels any fair-value assumption as private user input. Its secret-free
  schema receipt is `state/company_intel/private_thesis_storage_receipt.json`; the completion matrix
  credits only schema configuration until an owner browser session proves create/read/update/archive/
  restore/delete and a second authenticated identity proves cross-user isolation, then the outcome is
  appended locally through `scripts/record_private_thesis_storage_verification.py` without identifiers,
  credentials, endpoints or thesis contents.
- `docs/company_financial_assumptions.sql` — append-only private owner input for the four explicit
  formal financial-engine operands. The server-only importer filters to the configured CI owner,
  accepts only approved/source-labelled/dated rows, and makes approval date the first eligible
  date; reference cases and browser entries cannot activate a formal engine by themselves.
- `docs/henneth_ci_archive.sql` — durable document, fact, snapshot and PDF-object archive. Archive
  tables have no anon/authenticated grants and no RLS policies; a server-only sync credential is the
  sole writer. This preserves the `state/` seam as the publish source of truth while retaining a
  tamper-resistant historical archive. `scripts/supabase_ci_store.py` runs after the private CI
  slice: it archives source-linked records every cloud cycle and uploads only ready, current-run
  official PDF bytes from the bounded extraction handoff. Missing or invalid transient bytes are
  skipped; they never block publication.

Written, not applied in the live desk project (SQL lives in `docs/`, owner runs it by hand):
- `docs/push_subscriptions.sql` — Web Push endpoints. Feature is inert until VAPID keys, this table, and a shipping change all exist.
- `docs/lifecycle_email.sql` — activation columns, `mark_activated` RPC, unsubscribe RPC, `lifecycle_email_log`, `lifecycle_queue` view. `scripts/lifecycle_email.py` exists; it cannot run until this is applied and Resend + service-role secrets exist.
- `docs/company_financial_assumptions_insert_hardening.sql` — applied hardening for the dedicated CI assumptions table (migration `harden_owner_financial_assumption_drafts`, 2026-08-27). It narrows authenticated inserts to inert drafts (`approved=false`, `approved_at null`) so server-side approval remains an append-copy operation. It does not alter the legacy desk project.

Never assume a SQL file in `docs/` has been applied. Additive first. There is no migration runner.

---

## 6. Authentication flow

1. `dashboard/index.html` does a synchronous first-paint guess from `localStorage` key `sb-qteoncckohuoatbjjykb-auth-token` (must track the project ref). This only decides whether the chrome is collapsed.
2. `initAuth()` in `app.js` calls `sb.auth.getSession()`, loads `profiles`, migrates a guest birth chart, then `route()`.
3. Sign-in / sign-up UI is `dashboard/auth-terminal.js` (`window.HennethAuthTerminal`). Passwords never touch our code.
4. Cloudflare Turnstile is wired but off (`CAPTCHA_SITE_KEY = ""`). Do not enable one side without the other — see the comment above that constant.
5. Access tokens are ES256. `middleware.js` and `api/ask.js` each verify against the project's JWKS. Fail closed. If the project is switched back to HS256, every gated request 401s. That is the correct direction.
6. The publishable key in `app.js` / `site.config.ts` is safe to ship. The service role must never enter the client bundle, a state file, or a commit.

---

## 7. Authorization model

| Layer | What it protects | Bypassable from the client? |
|---|---|---|
| `middleware.js` | research files under `/state/` | no |
| `gateAllows()` / `OPEN_ROUTES` | which clean dashboard paths render | yes — it is UX |
| `hasFeature()` / `PLANS` / `BILLING_LIVE` | which screens are teaser-walled | yes, and while `BILLING_LIVE === false` every signed-in account is treated as Pro |
| Supabase RLS | a user's own `profiles` row | no, if RLS stays on |
| Supabase RLS | a user's own `company_theses` rows | schema configured in the dedicated CI project; browser completion still needs owner-account CRUD and cross-user RLS verification |
| `isOwner()` | plan-preview chrome | yes — it is an email string compare |

`plan` is frozen in the database against client writes. There is no payment gateway. Do not flip `BILLING_LIVE` or `site.earlyAccess` until a local gateway, reviewed legal pages, and a service-role trial path exist.

---

## 8. Important business rules and where they live

| Rule | Authoritative text | Enforced by |
|---|---|---|
| Long only, daily timeframe, no advice language | `CLAUDE.md` | agents, `api/ask.js` system prompt, copy review, `provenance_lint.py` |
| Numbers come from `state/`, else "unknown" | `CLAUDE.md` Rule 2 | agents; Ask-the-desk now relies on instruction-following around a pre-filtered slice, not templates |
| Position sizing | `CLAUDE.md` Rule 4 | `build_signals.py` (validity guard), `app.js` `deskSize()`, `calculators.ts` `sizePosition()` |
| Max 4 names, 20% exposure, one per sector | `CLAUDE.md` Rule 4 + `config/desk.json` `risk` | `build_signals.py`; practice checker in `app.js` |
| Health gates new signals | `CLAUDE.md` Rule 6 | `data_health.py`; consumers must honour `health.json` |
| Auditor veto | `CLAUDE.md` Rule 7 | `.claude/agents/auditor.md` on the local cycle |
| Strategy files immutable once live | `CLAUDE.md` Rule 8 | convention + Auditor; no file-system lock |
| No lookahead | `CLAUDE.md` Rule 9 | `backtest.py` / `strategy_engine.py` |
| News impact 4+ retriggers the full cycle | `CLAUDE.md` Rule 10 | news-sentinel + orchestrator prompt |
| Named-security levels are not published | `docs/PUBLICATION_RESTRUCTURE.md` + V2 | `build_signals.py` computes then discards entry/stop/target/shares; public tools take the reader's own numbers |
| `config/desk.json` is never served | `CLAUDE.md` | `vercel_build.sh` copies `dashboard/` + root-servable `state/` only; `desk_rules.json` is an allow-list export |

---

## 9. AI / LLM architecture

Three separate uses. Do not mix their jobs.

**Local desk agents** (Claude Code). Orchestrated by `prompts/cycle-full.md` and `cycle-light.md`. Each agent is a markdown file in `.claude/agents/`. They read compact dossiers (`state/dossiers.json`), never scrape. Output is JSON in `state/` (`rooms.json`, `daily_read.json`, `macro.json`, `claims.json`). Token cost stays on the owner. The cloud workflow has no API key on purpose.

**Ask-the-desk** (`api/ask.js`). Vercel Edge. Auth required. Fetches about 13 light state files with the caller's token, builds a symbol/sector-scoped slice, calls Groq (`llama-3.3-70b-versatile`). Rule 2 here is a system prompt, not an architecture guarantee. If `GROQ_API_KEY` is missing on the terminal Vercel project, the endpoint returns a configured error and the UI says chat is not configured. That is the current live state noted in `GOTCHAS.md`.

**State translator** (`state-translator` agent + `translate_extract.py` / `translate_merge.py`). Optional Urdu layer. Failure must leave English in place.

There is no in-product RAG store, no embeddings pipeline, and no per-visitor agent on the static host.

---

## 10. Integrations and external providers

| Provider | Used for | Isolated behind | Failure mode |
|---|---|---|---|
| PSX DPS | live watch, EOD, sectors, off-market CSV | `psx_data.py` | degrade, keep prior file, exit 0 |
| Yahoo Finance chart API | deep history, non-PSX names, some dividends | several fetchers; ticker via `psx_data.yahoo_symbol` | same |
| TradingView | EOD cross-check only, 15-min delayed | `tv_crosscheck.py` | advisory unless a genuine glitch; never compare TV live to DPS live |
| Firecrawl CLI | insider filings page | `fetch_insider_offmarket.py` | `stale: true`, keep prior |
| Supabase Auth + DB | accounts, profiles, private company theses, waitlist | client SDK/REST + RLS | signed-out or explicit feature-not-activated fallback |
| Groq | Ask-the-desk | `api/ask.js` | 502/429, no fabricated answer |
| Resend | lifecycle email | `lifecycle_email.py` | not live |
| PostHog + GA4 | analytics | `index.html` snippet; `site/src/components/posthog.astro` + `Base.astro` | silent if env missing |
| Vercel | hosting, edge middleware, one edge function | `vercel.json`, `middleware.js`, `api/ask.js` | last-good deploy stays if publish is blocked |
| Telegram | owner-only alerts | `config/desk.json` `alerts`, `scripts/alert.py` | empty token -> log only |
| Cloudflare Turnstile | signup bot protection | `app.js` `CAPTCHA_SITE_KEY` | currently disabled |

---

## 11. Storage

- Git is the research database. `state/` is committed, including `history/`, `history_deep/`, `intraday/`, so Vercel is self-contained.
- Writes go through `psx_data.save_json`: atomic temp replace, NaN/Inf scrubbed, UTF-8. Callers should not invent a second writer.
- `config/desk.json` is local/private. Never copy it into `public/` or `state/`.
- Root `/public/` is the terminal Vercel output directory and is gitignored. `site/public/` is the marketing site's static assets and is not gitignored — the root ignore rule is anchored on purpose.

---

## 12. Background processes

| Process | Where | What |
|---|---|---|
| `desk-data.yml` | GitHub Actions, weekdays 07/37 minutes past 03:00-11:00 UTC | `run_cloud.py` + `publish.py` + `watchdog.py` |
| App scheduled tasks | owner's Claude app (OPERATIONS.md section 4, SYSTEM-REGISTRY.md) | news, monitor, macro, daily read, Desk Room debates, weekly harvest, weekly code review |
| `lifecycle_email.py` | not scheduled live | welcome / nudge / digest |
| `push_send.py` | runnable, inert without VAPID | web push |
| Content tweet tasks | separate content system | not the desk |

`SYSTEM-REGISTRY.md` is a cheap index and was last dated 2026-07-14. Prefer `run_cloud.py` and `OPERATIONS.md` when the registry disagrees.

The cloud workflow installs Python 3.12 (`.github/workflows/desk-data.yml`). That is the canonical runtime for published numbers. The owner's machine may be 3.14. `requirements.txt` is the only dependency list.

---

## 13. Deployment architecture

One repo, two Vercel projects, one publish choke point.

**Terminal**

- Root `vercel.json`: `installCommand` is a no-op, `buildCommand` is `sh scripts/vercel_build.sh`, `outputDirectory` is `public`.
- `vercel_build.sh` copies all of `dashboard/` into `public/`, deletes `app.html`, copies `state/` to `public/state/`, then removes the CI-owner-only artifacts (`company_documents.json`, `company_briefs.json`, `company_brief_receipts.json`, `document_synthesis_queue.json`, and `company_intel/`). The dashboard copy remains a deny-list because an allow-list already 404'd `auth-terminal.js` in production; the CI state exclusion is the opposite boundary and is checked by `scripts/check_root_state_publication.py`.
- The terminal's Vercel configuration falls back only clean dashboard paths to the SPA shell, so a
  refresh or shared link such as `/today`, `/ticker/LUCK`, or `/legal/privacy/` reaches the same
  dispatcher. Static assets, `/state/*`, and `/api/*` retain their normal handling and are not
  swallowed by the SPA fallback.
- `ignoreCommand` skips a deploy when the commit did not touch `dashboard/`, `state/`, `api/`, `middleware.js`, the build script, or `vercel.json`.
- Cache: HTML/JS `must-revalidate`; `state/*.json` 60s + SWR 900s. A caching service worker would violate the freshness guarantee; `dashboard/sw.js` has no fetch handler and is not shipped until push is activated.

**Marketing**

- `site/vercel.json` pins Astro. Do not let Vercel import the root `vercel.json` into this project — that is the terminal build and it breaks the site.
- Ignored-build-step gotcha for merge commits is documented in `site/README.md`.

**Publish**

- Always `python scripts/publish.py "message"`. Never hand-push `state/`.
- Default: stage `state/` + generated marketing extracts only.
- `--code`: ships only files already staged by you. It never runs `git add -A`.
- Rebase auto-resolve is allowed only for regenerable data. A conflict on a hand-authored file aborts.

---

## 14. Invariants

1. Producers write `state/` (or the public extract). Renderers do not fetch upstream vendors.
2. Consumers do not reach around `state/` into `config/`, Yahoo, or DPS.
3. A structurally broken cycle must not publish. `preflight.py` fail -> last-good site stays.
4. A vendor failure must not crash the cycle and must not invent a number.
5. `config/desk.json` and `.env` never enter a served directory.
6. Named-security entry/stop/target/share-count against the desk's capital do not appear on subscriber surfaces.
7. Strategy JSON that has produced a published backtest is frozen. New version = new file.
8. SQL in `docs/` is not live until the owner applies it.
9. `BILLING_LIVE` false means do not take money and do not lock members out.
10. The two Vercel projects stay separate. The marketing build stays hermetic.

---

## 15. Behaviour that must stay synchronized

| If you change... | also change... |
|---|---|
| Rule 4 | `CLAUDE.md`, `build_signals.py`, `app.js` `deskSize()`, `site/src/scripts/calculators.ts` `sizePosition()`, and the comments that name the siblings |
| Risk constants in `config/desk.json` | they flow through `desk_rules.json` automatically; do not hardcode a second set in `app.js` except as the documented fallback |
| Supabase project ref | `SB_URL` / `SB_STORAGE_KEY` in `app.js`, the first-paint script in `index.html`, `middleware.js` / `api/ask.js` JWKS URL, `site.config.ts` |
| `PUBLIC_FILES` in middleware | `watchdog.py` (it uses `public_probe.json` as the unauthenticated content check) |
| Plan ladder / feature names | `PLANS` in `app.js` and `site.plans` in `site.config.ts`. `app.js` wins for entitlement |
| `earlyAccess` / `BILLING_LIVE` | both, plus legal review and a trial grant path |
| Universe / liquidity gates | `psx_data.research_symbols()` only — do not add a local `tier == "core"` filter |
| Indicator math | `scripts/indicators.py` only; delete any local shadow in the same commit |
| JWT verify logic | `middleware.js` and `api/ask.js` (deliberate duplicate; keep them equivalent in behaviour) |
| CI-private root state list | `scripts/root_state_publication.py`, `middleware.js`, `scripts/vercel_build.sh`, and `scripts/check_root_state_publication.py` |
| Dashboard filename added | nothing — `vercel_build.sh` copies the folder. Do not revive an allow-list |
| Public page data | `build_public_slice.py` allow-list. Never read `state/` from Astro |

---

## 16. Unusual technical decisions

Leave these alone unless the reason died.

- JSON files in git instead of a research database. Lets a static host serve the product and lets `publish.py` be the only write path.
- Two gates, UI and data. The sign-in screen was never enough; `/state/` used to be wget-able.
- JWKS on the edge, no shared secret. Verification is Web Crypto against a public key.
- Ask-the-desk duplicates `verify()` rather than importing middleware. A chat change must not regress the file gate.
- Public extract is an allow-list. New `state/` fields stay private by default.
- Disagreement shape, not verdict, on public ticker pages. Legal + Rule 5.
- Signals compute size and levels, then throw them away. Validity still needs the maths; publication must not look like advice.
- Deny-list dashboard copy. An allow-list already caused a live blank sign-in page.
- `research_symbols()` fails closed to core. A missing liquidity file must not fan the expensive pipeline out across the whole market.
- Health ignores foreign-symbol freshness. A Yahoo miss on XLE must not halt PSX signals.
- No test framework. The real gates are `preflight.py`, `provenance_lint.py`, `watchdog.py`, and a production publish. Do not drop in Jest/pytest as part of an unrelated change.

---

## 17. Important seams

| Seam | Why it is a seam | Do not |
|---|---|---|
| `state/*.json` | Python writes, JS/agents/extension read | let the dashboard call Yahoo; let a fetcher render HTML |
| `state/desk_rules.json` | exports rule constants without exporting secrets | serve `config/desk.json` |
| `site/src/data/public/` | only desk data the marketing site may see | import `../../state` from Astro |
| `psx_data.save_json` / `load_json` | atomic UTF-8 NaN-safe I/O | add a third JSON helper |
| `psx_data.research_symbols()` | one definition of who gets the expensive pipeline | copy a `tier == "core"` filter |
| `psx_data.yahoo_symbol()` | one place that knows `.KA` vs a US ticker vs `US500` -> `^GSPC` | concatenate `.KA` at a call site |
| `middleware.js` | data gate | move research serving through a serverless proxy (`state/` is about 92MB) |
| `publish.py` | the only push path | `git add -A` or a raw `git push` of state |
| `hasFeature()` / `BILLING_LIVE` | future entitlement | scatter `if (plan === "pro")` through pages |
| `strategies/library.json` | live rule templates | edit a live strategy in place |

---

## 18. Where to make a change

| You want to... | Start here, not somewhere else |
|---|---|
| Add a ticker field the UI needs | write it in the Python producer, assert it in `preflight.py`, then read it in `app.js` |
| Add a public marketing fact | add it to the allow-list in `build_public_slice.py`, then the Astro page |
| Change risk limits | `config/desk.json` + `CLAUDE.md` if the rule text changes |
| Change how Yahoo is called | put retry/error handling in one helper and migrate fetchers to it (see TECH-DEBT) |
| Add a dashboard page | `PAGES` + a `pageX()` in `app.js`, nav in `index.html`. Do not start a second router |
| Add a marketing page | `site/src/pages/...` + `site.config.ts` if it is brand-shaped |
| Add an agent | `.claude/agents/`, one line in `SYSTEM-REGISTRY.md`, persist into `state/` |
| Add a cron step | `run_cloud.py` if it is free/deterministic; owner's scheduled tasks if it needs Claude |
| Touch auth or `/state/` | stop and read `middleware.js`, `GOTCHAS.md`, OPERATIONS.md section 9b |
| Activate push or email | owner applies SQL + secrets; do not turn it on from code alone |

If this file does not name the place, search `graft/` or run `graft ask` before writing a new module.
