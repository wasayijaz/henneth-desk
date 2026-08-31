# Henneth Company Intelligence — Event-to-Value Alpha

## Mission and scope

Event-to-Value Alpha is the active delivery milestone for `ci.henneth.app`.
The broader 68-section Company Intelligence specification remains the long-term
roadmap. This milestone proves the complete, source-grounded investor workflow
for three companies before expanding the universe, generic interface breadth,
or monitoring volume.

Each completed Intelligence Case must establish a traceable path:

`observed evidence -> operating event -> competing hypotheses -> drivers -> analogues -> quarterly financial impact -> scenarios -> valuation -> price-implied expectations -> investor conclusion -> monitoring`.

No case is marked product-complete until it is `Published` and has usable,
source-qualified financial, valuation, and current-price-expectations outputs.

## Execution rules

- The golden scope is exactly three companies: one E&P exploration case, one
  industrial/cement expansion case, and one sales-led expansion case.
- Existing 20-company CI products remain searchable but do not receive new
  formal Event-to-Value work unless they are a selected golden company.
- A source fact, derived fact, inference, analyst assumption, scenario output,
  forecast, and market-implied value remain visibly distinct.
- Numerical accounting, quarterly models, EPS, cash flow, debt, valuation,
  probability, and reverse-expectations calculations are deterministic.
- Historical outcomes are labels, never inputs available before their historical
  cutoff. Small samples remain visible but do not produce misleading averages.
- Every part is committed separately only after its relevant checks are green.
  The execution log below records the investor behaviour, data coverage, and
  unresolved blocker before the next part begins.

## Active execution order — vertical case lanes

The numbered Parts below remain the completeness checklist and final acceptance
standard. Development proceeds vertically by case rather than horizontally by
shared layer: prove a bounded case lane end to end, then reuse only contracts
that were actually proven.

1. Keep Part 0's local safety floor active: timestamp meanings, no-lookahead,
   artifact integrity, and secrets/auth invariants. Live release proof remains
   deferred until the final release gate.
2. Establish the selected industrial first-case viability quickly: a dated,
   authoritative observation, credible mechanism, competing hypotheses, and a
   bounded official-filing availability audit. DGKC's retained expansion lead
   did not clear this test, so MLCF / Pioneer Cement is the current `Observed`
   industrial alternative; do not expand research indefinitely.
3. Take the viable MLCF lane through financial facts, corroboration, cutoff-safe
   analogues, calibrated scenarios, deterministic eight-quarter modelling,
   valuation, price-implied expectations, and the minimum real case interface.
   A provisional case may progress only through `Observed`, `Corroborated`,
   `Modelled`, and `Validated` until every Part 1 publication gate is met.
4. Backfill the complete five annual years, eight reported quarters,
   share-count history, and tie-outs before `Published`; a source receipt is
   never progress on its own. Non-load-bearing unavailable disclosure may be
   marked unknown, but load-bearing gaps remain blocking.
5. Repeat the proven lane for E&P, then sales-led expansion. Extract a shared
   abstraction only after the first case demonstrates it is shared.

### Sector-model boundary

The shared case envelope is deliberately narrow: identity and lifecycle,
epistemic typing, provenance, point-in-time controls, assumption/run lineage,
scenario labels, confidence, monitoring, and the case-page sections. Economic
models remain sector-specific.

- **Cement / industrial:** capacity, utilization, dispatch or production,
  selling price, fuel/power/freight, maintenance and expansion capex,
  commissioning ramp, working capital, and financing.
- **E&P:** working interest/operator status, geological and commercial
  probabilities, resources/reserves, well and development costs, drilling and
  first-production timing, hydrocarbon mix/decline, royalty/tax, commodity
  price/FX, and circular-debt exposure.
- **Sales-led:** sales/support headcount, compensation and marketing,
  productivity ramp, channel/geography/customer mix, gross margin, acquisition
  and retention, and working capital.

No universal driver schema or formula engine is introduced. The selected MLCF
industrial lane establishes the concrete cement/acquisition model; E&P and sales-led economics are independently
implemented, with reuse limited to workflow contracts proven across sectors.

## Current baseline — 2026-08-31

| Area | Retained evidence | Status | Implication for Alpha |
|---|---|---|---|
| Architecture coverage | `state/company_intel/completion_matrix.json` | 61 complete, 4 partial, 4 blocked of 69 | Useful foundations exist; this is not proof of investor-ready cases. |
| Financial model readiness | `state/company_intel/forecast_readiness.json` | MLCF and DGKC input-ready; all formal outputs non-computed | No company currently clears Alpha’s financial-output gate. |
| Formal engines | `financial_forecasts.json`, `formal_valuations.json`, `market_expectations.json` | Deterministic code exists; 0 computed / 20 | Alpha must prove live outputs for three cases, not merely engine code. |
| Historical analogue state | `state/company_intel/conditional_benchmarks.json` | 21 dated benchmarks; thin samples remain suppressed | Golden cases need case-specific, cutoff-safe analogue evidence. |
| Private thesis storage | `private_thesis_storage_receipt.json` | Schema configured; live CRUD/cross-user RLS proof absent | Persisted owner scenarios/theses stay disabled until verified. |
| CI release integrity | Generated CI state carries a reproducible build envelope; live preview/production proof has not been run | Deferred by owner | Part 0 remains preserved and does not block current Alpha product development. |
| Financial truth qualification | `financial_truth_qualification.json`; `financial_reprocess_blockers.json` | DGKC leads on retained annual-income coverage but is not golden; MLCF is the selected industrial case | MLCF remains at 3/5 annual income triplets, 2/5 consolidated annual OCF periods and 3/8 qualified direct consolidated quarters; its official share-count/capital-note tie-out is now passed. The authoritative gate is stricter: 0/5 annual and 0/8 quarterly full-statement schedules, each requiring source-bound income, balance-sheet and cash-flow facts plus deterministic EBITDA/FCF operand lineage. Formal outputs remain fail-closed. |

Share-capital candidates now have an explicit fail-closed approval bridge: the empty owner manifest cannot add a fact, change a number, or activate an engine. A future approval must name the exact tied-out source candidate and date; the builder then requires its bound successful official reprocess receipt and retains the official source/hash and availability date in the eligible fact. This removes a workflow gap without treating the current candidate as approved.

The DGKC FY2025 PSX distributor annual (`psx:260947`) is no longer an executable restage path: the retained issuer annual is the canonical qualified source for the same FY2024/FY2025 income facts, so the distributor copy cannot add coverage and must not be double-counted. The unverified DGKC Q1 metadata lead (`psx:264230`) is also removed from the execution path. The retained verified Q3 source remains a geometry-blocked evidence gap; none of these corrections promotes a fact or output.
| Intelligence Case lifecycle | `state/company_intel/intelligence_cases.json` | 3 `Observed`, 0 `Corroborated`, 0 `Modelled`, 0 `Validated`, 0 `Published`, 0 `Monitoring`, 0 `Closed` | MLCF/PIOC plus two MARI seeds are source-bound observations only. The two MARI cases do **not** satisfy the final three-company standard, so a distinct sales-led company remains unselected. None may activate forecast, valuation, expectations, recommendation, or publication. |

## Golden-company selection register

Selection is evidence-led, not based on a preferred ticker. A company is chosen
only once its retained official source coverage can support five fiscal years,
eight reported quarters, load-bearing share-count data, and a real dated event.

| Case | Required event family | Current shortlist | Selection status | Reason / next evidence |
|---|---|---|---|---|
| A — E&P | exploration, appraisal, development, or production | OGDC, PPL, MARI | Observed | Mari Energies is selected for an observed-only E&P seed because official PSX filing `psx:260446` (2025-09-30, p.1) reports acquisition of working interest in Peshawar Block as operator. It is not Corroborated, Modelled, Validated or Published: the notice does not establish working-interest percentage, reserves/resources, costs, timing, production, project economics, or qualified financial history. OGDC remains a source observation only; PPL has no qualifying retained E&P event. |
| B — industrial/cement | expansion, hiring, procurement, maintenance, commissioning, or capacity | MLCF, LUCK, DGKC | Observed | MLCF's dated, official acquisition/control of Pioneer Cement is the strongest retained lane: PSX `psx:267429` (2025-12-18) describes control mechanics, and `psx:275425` (2026-04-28) confirms PIOC dispatches joined local-market totals after acquisition in February 2026. Treat the February date as month-only; dispatch percentage remains audit-only. DGKC and LUCK remain unselected. |
| C — sales-led | sales hiring, geography, branch/channel, product-sales infrastructure | CNERGY; MARI Sky47; PSO, GAL, BOP reviewed | Unselected | MARI Sky47 remains a useful supplemental `Observed` product-launch seed, but it cannot count because the Alpha requires three companies. CNERGY’s verified issuer-hosted 2018 gasoline-supply-share document is dated and hash/page-bound but remains evidence-only; its primary sales-record PDF is unavailable at the exact official URL. No distinct sales-led company has model-ready financial truth. |

## Ordered execution log

| Part | Gate | Status | Visible investor behaviour delivered | Data coverage / unresolved blocker |
|---|---|---|---|---|
| 0 | Release integrity | Deferred by owner | Every generated private CI artifact is now sealed with a common UTC cutoff, source commit, generator version, and hash manifest; stale or mismatched envelopes fail closed. | Preserve the release work for Alpha readiness; do not run live preview/production proof while Part 1 product work continues. |
| 1 | Model-ready financial truth | In progress | Financial truth is the authoritative fail-closed gate for formal forecast, valuation, and market-expectations output; legacy three-period readiness is descriptive only. | Selected MLCF case: 3/5 annual income triplets, 2/5 consolidated annual OCF, 3/8 direct consolidated quarters and a passed official share-count tie-out. Its full-statement schedule gate remains 0/5 annual and 0/8 quarterly. |
| 2 | Three real operating events | In progress | MLCF has an `Observed` Pioneer Cement control/acquisition case; MARI has separate `Observed` Peshawar E&P and Sky47/Karakoram-01 product-launch cases. | Exactly 3 case objects are `Observed`, but they cover only two companies. The final sales-led company remains unselected; none has independent corroboration, source-qualified incremental financial impact, or complete financial truth. |
| 3 | Sector event models | In progress | Deterministic, provenance-gated cement/capacity, E&P, and sales-led kernels exist with explicit bear/base/bull contracts and fail-closed blocked envelopes. The MLCF/PIOC adapter binds the real observed case only to a no-output path until its event and financial inputs qualify. | All three engines are implemented but unproven on a real source-qualified case: no current case may emit a numerical run, valuation, or expectation result from absent inputs. |
| 4 | Eight-quarter event-to-financial models | Not started | None | Requires complete actuals and source-labelled analyst assumptions. |
| 5 | Historical analogues | In progress | The MLCF/PIOC and MARI/Peshawar observed-case routes show cutoff-safe same-event raw-price context: MLCF -34.54% at 1Q and -19.40% at 2Q; MARI -2.71% at 1Q and -16.80% at 2Q. | These are deterministic descriptive derived facts, not causal attribution, adjusted/total return, analogue benchmarks, forecasts, or valuation inputs. Same-company/peer aggregates remain suppressed at n < 3; 4Q and 8Q outcomes are immature. |
| 6 | Valuation and expectations | Not started | None | Requires computed model outputs and appropriate valuation schedules. |
| 7 | Intelligence Case interface | In progress | The private route renders all three `Observed` source-grounded seeds. The distinct MARI Sky47 route exposes its reported launch, alternatives and three watch items without rendering its null model-input kernel. Owner-gated Ask Henneth receives bounded observed-case evidence, alternatives and watch conditions. | This is a read-only evidence context, not a model output. Ask and the case route remain blocked from formal financial impact, scenarios, valuation, expectations, or publication until financial truth qualifies. |
| 8 | Private thesis monitoring | Not started | None | Requires owner-session CRUD and cross-user RLS verification before writes are enabled. |
| 9 | Golden fixtures and release | Not started | None | Requires all case, product, runtime, and deployment gates green. |

## Part 0 acceptance record

Part 0 is complete only when all of the following are evidenced against the
same commit:

- every generated CI artifact has UTC `build_cutoff_at`, `generated_at`,
  generator version, and source commit metadata;
- no-lookahead distinguishes source-effective/published/observed timestamps
  from generated metadata;
- the aggregate CI contract, artifact-integrity, and authentication smoke tests
  pass;
- a preview deployment and production deployment identify the same green
  commit; and
- the CI private JSON endpoint remains owner-gated while the public login
  surface remains functional.

### Part 0 implementation evidence — 2026-08-28

- `scripts/build_ci_artifact_integrity.py` stamps all generated CI state and
  the private app slice with `source_commit_sha`, `generator_version`,
  `build_cutoff_at`, and `generated_at`, then writes a hash-backed manifest.
  Invalid or unknown commit identities fail closed.
- `scripts/check_ci_artifact_integrity.py` verifies every artifact hash and
  validates the stored source commit. Static checkout checks accept an older
  generated run because a committed file cannot name its own containing commit;
  CI and release jobs fail closed by supplying `GITHUB_SHA` /
  `HENNETH_CI_SOURCE_COMMIT_SHA` immediately after finalization.
- `scripts/check_ci_global_no_lookahead.py` treats the generated envelope as
  metadata rather than economic timing, while continuing to check source and
  provenance dates. It passed locally over 43 artifacts / 16,368 date
  comparisons.
- The aggregate and preflight gates finalize the artifact set only after
  ordinary rebuild checks, so metadata is not mistaken for a business-output
  difference and cannot be erased before validation. The focused artefact
  checker passed over 37 sealed artifacts after a stable finalizer run.
- `scripts/check_ci_release_integrity_receipt.py` now fails closed unless one
  secret-free receipt ties the GitHub contract, preview, production, public
  login, owner `200`, and non-owner `403` checks to the same full commit SHA.
  Its current receipt is deliberately `not_verified`; it is release evidence,
  not an investor-facing generated artifact.
- `.github/workflows/ci-production-release.yml` supplies the controlled
  preview-to-promotion route, with deployment credentials scoped through the
  `ci-production` environment on both Vercel-consuming jobs. The
  preview job restamps the private CI slice to the release `github.sha`, deploys
  that source tree directly as the Vercel preview, stamps the Vercel preview
  with `githubCommitSha`, verifies that metadata through the Vercel deployment
  API, and after promotion verifies the production domain resolves to that same
  deployment id and commit without a rebuild. The workflow intentionally avoids
  `vercel pull`/prebuilt deployment because the CLI project-settings fetch can
  fail under tightly scoped CI deployment tokens. The workflow is code-complete
  but its Vercel Git-deploy setting, protected environment secrets, and first
  live receipt remain external evidence. The CI Vercel project and team IDs are
  non-secret, versioned release bindings; only the deployment token remains a
  protected environment secret.
- **Production-path change applied (2026-08-28):** the `henneth-ci` Vercel
  project was on the Hobby plan with Git-triggered deployments enabled, while
  its Standard Protection excluded production custom domains. The owner
  approved disconnecting `wasayijaz/henneth-desk` from that Vercel project;
  Vercel now confirms the project is not connected to a Git repository, so a
  push cannot bypass the protected release workflow. The workflow's Vercel
  CLI deployment path remains available through its protected credentials.
- **Not evidenced yet:** the `ci-production` GitHub environment has been
  created and the owner has added the three Vercel deployment credentials.
  Before the first protected release, add the four Supabase email/password
  smoke secrets documented in the release runbook. The release smoke now
  obtains short-lived access tokens at runtime through the existing public
  Supabase URL/publishable key; raw tokens are neither logged nor persisted.
  The remaining prerequisite is the first GitHub Actions green run, matching
  preview/production deployment, public-login runtime smoke, and live owner
  `200` / non-owner `403` checks against `ci.henneth.app`.

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-08-27 | Alpha execution record created; no case selected or promoted. | This document and the retained baseline files named above. |
| 2026-08-27 | Completed retained-state candidate audit without promoting weak evidence. | E&P: `company_event_ledger.json` OGDC `evt_2564e46943e475e1c5dd`; industrial: DGKC `evt_c66c444c35780cf5951e`; sales-led: PSO `evt_2f3bfdf4a586999e66b6` / `evt_30027cd832df431a70a9`. All three case slots remain unselected until the strict financial/event gates are met. |
| 2026-08-28 | Implemented and locally verified the Part 0 integrity envelope and finalizer ordering. | 37 sealed artifacts; source-commit binding; workflow structural check; 43-artifact no-lookahead scan; focused metadata-safe deterministic checks. Live deployment/auth evidence remains open. |
| 2026-08-28 | Repaired the artifact source-commit model so static checked-in JSON does not falsely fail after commit, while CI and release jobs restamp and verify against the exact `GITHUB_SHA`. | `check_ci_artifact_integrity.py --self-test`; CI contract exact-commit verification step; release preview restamp before Vercel build. |
| 2026-08-28 | Created the `ci-production` GitHub Environment and disconnected the Vercel CI project from Git to prevent automatic production deployments. | Owner-approved live Vercel/GitHub configuration; workflow remains blocked only on its protected secrets and first release receipt. |
| 2026-08-28 | Scoped the preview job to `ci-production` too, so GitHub can supply the Vercel credentials at the first provider action without making them repository-wide. | Release workflow structural self-test rejects both an unprotected preview and an unprotected promotion. |
| 2026-08-28 | Replaced expiring static smoke-token inputs with protected owner/non-owner Supabase email/password secrets. The release smoke exchanges each pair for an in-memory password-grant access token using only the existing public URL and publishable key; no token is emitted or stored. | Offline smoke self-test covers the grant request and private-data gate; workflow checker requires all four credential names and rejects obsolete token inputs. |
| 2026-08-28 | Removed the local `vercel pull` / prebuilt deploy leg from the protected release workflow after the first controlled preview failed on Vercel project-settings retrieval. The workflow now deploys the restamped source tree directly as the immutable preview and still promotes only that verified deployment. | Release workflow checker fails if `vercel pull` or `--prebuilt` returns to this path. |
| 2026-08-28 | Began Part 1 Wave 1A and made financial truth the authoritative fail-closed gate for formal forecasts, valuations, and market expectations. Legacy forecast readiness cannot activate an output. | Synthetic positive/negative boundary checks, reconciliation checks, preflight, and artifact-integrity verification. |
| 2026-08-28 | Retried the owner-approved DGKC filings `psx:260947`, `psx:264120`, and `psx:275807` without widening provider, parser, or source policy. | FY25 annual exceeds the 120-page gate; Q1 FY26 and Q3 FY26 are image-only under the current parser. No receipt, fact, or coverage delta was written; blockers are retained in `financial_reprocess_blockers.json`. |
| 2026-08-29 | Added a fail-closed transport path for the verified 333-page DGKC FY2025 annual report, preserving its original hash and one-based citations across three temporary 111-page parser units. Replaced the image-only quarterly notices with the owner-directed retained full-report counterparts `psx:264230` and `psx:275962`. | Chunk coverage/hash/page-mapping checks pass; formal engines rebuild after financial truth inside a restoreable transaction. The actual restage was not accepted because the mandatory full repository gate found unrelated generated-state consistency failures. No receipt or model-ready financial-truth delta is claimed. |
| 2026-08-29 | Audited DGKC first-case viability under the vertical-lane rule. | No Observed seed: `evt_c66c444c35780cf5951e` lacks a trusted event date, full context, and resolved subsidiary attribution. Its PP-bag reference stays evidence-only; no inferred date or cement model is permitted. |
| 2026-08-29 | Added the first narrow IntelligenceCase output: MLCF / Pioneer Cement acquisition-control is `Observed` only. | `psx:267429` p.3 records the dated MLCF offer/control mechanics; `psx:275425` p.4 records PIOC dispatch inclusion after February 2026 acquisition. The case preserves both sources, alternatives, and explicit promotion blocks; it emits no forecast, valuation, expectations, or recommendation. |
| 2026-08-29 | Completed retained-state financial availability audit for the selected MLCF lane. | No executable filing tranche: PIOC has no retained CI financial document, while MLCF has 3/5 annual income facts and no qualified OCF, quarter, or share-capital coverage. Existing MLCF quarterly transmissions are hash-bound but have unconsolidated/mixed geometry and cannot be promoted. `psx:260032` is the smallest future official annual candidate, subject to owner approval and exact intake gates. |
| 2026-08-29 | Restaged the verified MLCF FY25 annual and qualified its consolidated annual OCF facts; added a fail-closed capital-note candidate path. | `psx:260032` remains one official source, never double-counted. MLCF now has 3/5 annual income triplets and 2/5 annual consolidated OCF. Its page-317 capital-note candidate carries the source URL, hash, original page, and arithmetic tie-out but remains unapproved and cannot activate financial truth or any formal output. |
| 2026-08-29 | Restaged the owner-approved MLCF Q1 FY26 official quarterly filing `psx:263397` through the atomic intake path. | The 43-page PDF is hash-bound (`a05eeee2...b9cdcc7e`) and has a durable success receipt. It adds 33 source/page-bound v2 facts, including direct three-month income-statement evidence, but no qualifying consolidated Revenue/PAT/EPS triplet. MLCF remains fail-closed at 0/8 qualified quarters; no formal output was activated. |
| 2026-08-30 | Audited the remaining owner-approved MLCF Q2/Q3 FY26 filings `psx:271712` and `psx:275425` without adding any source or OCR. | Both exact hash-bound PDFs contain later-page, direct consolidated three-month Revenue/PAT/EPS statements (Q2 page 33; Q3 page 28). Q2 has since been receipt-backed and reclassified below; Q3 remains a targeted parser/transaction work item. |
| 2026-08-30 | Restaged owner-approved MLCF Q2 FY26 filing `psx:271712` and corrected financial-series conflict identity so direct three-month facts are not confused with cumulative interim facts. | The success receipt is hash-bound to `f4f9d671...cf9e5f69`; direct consolidated Revenue PKR 18,935,494,000, attributable PAT PKR 3,118,059,000, and EPS 2.98 are source-bound to original page 33. Qualified direct-quarter coverage moved 0/8 to 1/8. Same-slot value conflicts still fail closed; annual income (3/5), annual OCF (2/5), and share-count tie-out (missing) keep formal forecasts, valuation, and expectations blocked. Commit `b0be7862`. |
| 2026-08-30 | Restaged owner-approved MLCF Q3 FY26 filing `psx:275425` through the same atomic path. | The exact retained official PDF is hash-bound to `744a0c71...eae11f`; a changed live URL is rejected by hash and may use only that explicit retained original. Direct consolidated Revenue PKR 21,545,015,000, attributable PAT PKR 1,770,955,000, and EPS 1.86 are source-bound to PDF page 29 (printed page 28). Qualified direct-quarter coverage moved 1/8 to 2/8. Transaction rebuild order now includes the observed IntelligenceCase and MLCF/PIOC readiness manifest, preventing stale derived state from passing preflight. Annual income (3/5), annual OCF (2/5), and share-count tie-out (missing) continue to block formal outputs. |
| 2026-08-30 | Replayed owner-approved MLCF Q1 FY26 filing `psx:263397` after a geometry-parser repair. | The official 43-page PDF remains hash-bound to `a05eeee2...b9cdcc7e`. Its consolidated page 29 now yields direct three-month Revenue PKR 16,483,361,000, attributable PAT PKR 2,728,256,000, and EPS 2.60. A code-fingerprinted receipt makes this bounded parser replay repeatable without invalidating previously qualified v5 facts. Qualified direct-quarter coverage moved 2/8 to 3/8. Annual income (3/5), annual OCF (2/5), and share-count tie-out (missing) still block formal outputs. |
| 2026-08-30 | Completed a read-only retained-evidence audit for MLCF's remaining financial-truth gaps. | No additional retained source already carries qualified, load-bearing annual, OCF, quarter, or share-count evidence. Older hash-bound PSX result notices are metadata/evidence leads with no reparse receipt; issuer road-show and AGM summaries remain audit-only. The next financial wave requires an explicit, bounded owner-approved reparse of exact retained full reports and the capital-note source; no formal output was activated. |
| 2026-08-30 | Diagnosed the exact hash-pinned MLCF FY24 Q1–Q3 PSX results tranche without consuming state. | Official PSX documents psx:219092, psx:225623, and psx:229941 each passed the exact-source transport checks but are image-only under the existing parser policy. No fact, receipt, or coverage delta was written; direct-quarter coverage remains 3/8. OCR, parser-cap relaxation, or a substitute provider was not introduced. |
| 2026-08-30 | Added a second, dedicated observed-only E&P case seed for Mari Energies. | Official PSX filing `psx:265594`, published 2025-11-13 and hash-bound to `cdc3f691...e8aae4`, reports the acquisition of offshore exploration blocks (p.3). It is a source-grounded observation only: no operator/working-interest/economic/technical outcome or qualified financial history is supplied, so forecasts, valuation, expectations and publication remain blocked. |
| 2026-08-30 | Closed the retained-state sales-led selection audit without forcing a case. | No 20-company-pilot candidate supplies a dated, attributable, discrete sales expansion event. BOP `psx:272102` is a generic strategy narrative; PSO's network/card records are undated; GAL has no event. The sales-led lane remains unselected pending qualified retained evidence or separately approved source intake. |
| 2026-08-30 | Added deterministic, provenance-gated E&P event economics and a MARI evidence-readiness audit. | The pure E&P kernel computes only from explicit source- or analyst-labelled inputs and is not wired to formal outputs. MARI has two exact hash/page-backed event excerpts (`psx:265594` p.3 and `psx:260446` p.1), but 0/5 model-ready annuals, 0/8 model-ready quarters, no filing-bound share count, and no numeric E&P operands. It remains Observed and blocked. |
| 2026-08-30 | Added the read-only Intelligence Case route and connected it to existing observed-case projections. | `/company/{ticker}/intelligence/{case_id}` renders the MLCF/PIOC and MARI observed seeds with evidence and explicit promotion blocks. Unmodelled financial impact, scenarios, valuation, and expectations fail closed instead of displaying invented values. The UI checker passes 71 assertions; the CI product contract passes 64 checks. |
| 2026-08-30 | Completed the bounded local-retention audit for MARI's two official event filings. | `psx:265594` and `psx:260446` remain hash-verified official metadata, but neither original PDF nor a reprocess receipt is retained locally and neither is allowlisted for exact-ID restage. No parsing, OCR, facts, or model outputs were added. The next safe action is explicit retained-byte staging under the existing official-source path. |
| 2026-08-30 | Added and independently hardened the sales-led expansion economics kernel. | The pure eight-quarter model requires provenance-labelled inputs, computes revenue, SG&A, gross profit, EBITDA, operating EPS proxy, FCF, ROIC, NPV, per-share value and break-even timing for isolated bear/base/bull cases. Independent Luna review closed unknown-input, pre-valuation-quarter, and non-finite/overflow boundaries; it remains unconnected until a source-grounded sales-led case qualifies. |
| 2026-08-31 | Executed the owner-approved, hash-pinned seven-document MLCF financial-filing tranche through the existing exact-ID PSX parser path. | FY25 annual `psx:260032` was hash-verified and processed as four temporary original-page-preserving units (1–120, 121–240, 241–360, 361–401). FY26 Q1–Q3 full reports `psx:263397`, `psx:271712`, and `psx:275425` received durable success receipts. FY24 notices `psx:219092`, `psx:225623`, and `psx:229941` were rejected as image-only; no OCR, substitute source, or promotion occurred. Financial truth remains 3/5 annual income triplets, 2/5 annual OCF periods, 3/8 direct quarters, and no official share-count tie-out; formal outputs remain blocked. |
| 2026-08-31 | Corrected the CI-slice preflight projection contract exposed by the approved restage transaction. | The slice enriches an Intelligence Case with independently-produced confidence and watch-next context. Preflight now validates that same canonical projection rather than comparing it to the un-enriched source case. Aggregate preflight, artifact integrity, financial-truth, formal-engine, and Intelligence Case payload checks pass; the only aggregate warning is the pre-existing non-gating history backfill. |
| 2026-08-31 | Corrected the active MARI observed case to the authoritative Peshawar Block working-interest/operator disclosure and recorded the lifecycle count explicitly. | `state/company_intel/intelligence_cases.json` contains `case_mari_working_interest_observed_v1` from `psx:260446` p.1 and `case_mlcf_pioc_control_observed_v1`; lifecycle truth is 2 Observed and 0 Corroborated/Modelled/Validated/Published. The older offshore seed is not an alias or active case. |
| 2026-08-31 | Audited the source-authority boundary for MLCF's image-only annual fact citations. | Existing eligible annual manual facts cite `psx:236626` p.1 and `psx:280589` p.3, but their retained document entries have no canonical page count or page-evidence record. A parser receipt cannot be fabricated for image-only filings. Any future authority repair must be append-only, owner- and independently-reviewed, geometry-only, and exact-match existing approved manual claims; it cannot introduce values, OCR, a provider, or activate formal outputs. |
| 2026-08-31 | Canonicalized the owner-approved MLCF image-only document geometry as a separate, append-only authority ledger. | `manual_document_authority.json` binds the approved `psx:236626` p.1 and `psx:280589` p.3 render hashes, geometry, official URLs, document hashes, publication dates, and research-index dates. Its checker rejects numeric facts, parser-like records, hash/page/date drift, and insufficient review. The existing nine approved annual income claims retain exactly the same values and coverage; annual OCF, share-count, five-year/eight-quarter gates, and every formal output remain blocked. |
| 2026-08-31 | Made financial-truth qualification authoritative for Intelligence Confidence's financial-model component. | A legacy `financial_model_inputs.status: ready` can no longer add financial-model confidence while financial truth is `not_qualified`; the legacy status remains visible only as provenance. The deterministic checker covers both the red-gate block and qualified positive boundary. No financial fact, coverage, forecast, valuation, or expectation output changed. |
| 2026-08-31 | Projected MLCF's retained confidence and evidence watch checks into its observed-case route under an exact source-chain join. | The UI requires one matching ticker, document/hash/page, confidence ID, assertion key, and source-cluster chain; mismatched or ambiguous context is omitted. MLCF renders the current low (42/100) derived confidence and four official-source watch checks, while financial-truth red continues to block every formal output. |
| 2026-08-31 | Rebuilt the evidence watchlist from the financial-truth-gated confidence state. | Four existing watch items had stale `medium` bands after the confidence gate reduced their source-bound assessments to `low`. The deterministic rebuild now agrees with the pure builder and the private slice; no financial fact, model input, forecast, valuation, expectation, or lifecycle state changed. |
| 2026-08-31 | Added bounded observed-case context to owner-gated Ask Henneth and closed an Ask readiness leak. | Ask can now answer qualitative evidence, alternative-reading, and confirmation/break questions against one exact source-cited case; it does not receive reported values or promote an `Observed` case. The Ask projection now suppresses legacy snapshot/model-input readiness, observations, and derived values whenever financial truth is red; synthetic positive coverage proves an actually qualified company may proceed. |
| 2026-08-31 | Aligned the IntelligenceCase lifecycle vocabulary with the Alpha domain contract. | The deterministic state builder, route validator, case UI, and Ask Henneth now recognise `Monitoring` and `Closed` after `Published`. Existing cases remain exactly two `Observed` seeds; no lifecycle was promoted. |
| 2026-08-31 | Re-audited the sector-model implementation against the active Alpha goal and corrected the execution record. | The cement expansion engine passes 312 deterministic checks; the MLCF/PIOC real-case adapter passes 893 source/contract boundaries; E&P and sales-led engines pass 97 and 566 checks. These are implemented, unproven kernels: their real-case paths remain blocked until source-qualified financial and event operands exist. |
| 2026-08-31 | Removed stale DGKC distributor/metadata execution paths from the financial-restage tranche. | The FY2025 PSX distributor annual cannot be reprocessed or chunked because it duplicates the canonical retained issuer annual; the unverified Q1 metadata lead is also non-executable. The verified Q3 geometry blocker remains visible. No financial fact, coverage, or formal output changed. |
| 2026-08-31 | Extended the single financial-truth activation predicate through Scenario Lab and its browser interaction. | Legacy snapshot labels cannot produce scenario arithmetic, reverse expectations, valuation sensitivity, or implied-price output while financial truth is red. The state builder, Company Brain, CI slice, Ask projection, and navigation checks share the current qualification result; synthetic positive coverage preserves activation for a fully qualified company. |
| 2026-08-31 | Added MLCF's retained cutoff-safe historical market context to its observed IntelligenceCase. | The exact control event now renders raw-price outcomes of -34.54% at 1Q and -19.40% at 2Q from the retained 2025-12-17 baseline; 4Q/8Q remain immature and all analogue aggregates remain suppressed at n < 3. This is source-bound deterministic context only—not causal attribution, adjusted/total return, a benchmark, a forecast, valuation input, or a case promotion. |
| 2026-08-31 | Extended the source-bound historical-market envelope to MARI's active Peshawar observed case. | The canonical operating-event record and `psx:260446` p.1 evidence bind MARI's same-event raw-price outcomes of -2.71% at 1Q and -16.80% at 2Q from the retained 2025-09-29 baseline. The result is descriptive only; 4Q/8Q and all analogue aggregates stay suppressed/immature, and no E&P economic, forecast, valuation, expectation, or lifecycle output is activated. |
| 2026-08-31 | Replaced the legacy three-line financial readiness shortcut with the Alpha’s full-statement financial-truth activation gate. | Formal forecasts, valuation and market expectations now require five annual and eight direct reported-quarter schedules spanning source-bound income, balance-sheet and cash-flow facts, deterministic EBITDA/FCF operand lineage, an official share-count tie-out, and no canonical conflict. A stale `status: qualified` record without that schedule is blocked; the legacy Revenue/PAT/EPS/OCF counters remain visible only. All 20 real companies remain blocked at 0 computed outputs. Commit `835fb96e`. |
| 2026-08-31 | First inspected the already-approved local-only MLCF annual/Q3 parser sources without network fallback. | `psx:260032` and `psx:275425` are still hash-bound in retained metadata, but both named local raw-PDF paths are absent. That sandboxed fallback wrote no fact or receipt. The subsequent exact-ID, hash-verified PSX annual fetch succeeded; missing local bytes are an offline-recovery concern, not the current evidence-path blocker. |
| 2026-08-31 | Added a bounded, read-only original-page diagnostic to the exact-ID filing transport and inspected the approved MLCF FY2025 annual report. | `psx:260032` remains hash-valid at 401 pages. Pages 197–205 are the unconsolidated statements and correctly remain non-load-bearing for the consolidated financial-truth gate. The diagnostic then located the actual consolidated pages 291/293/295, whose existing block-geometry parser output was revalidated without relaxing any rule. |
| 2026-08-31 | Restaged the owner-approved, pinned MLCF FY2025 annual through the existing four-chunk canonical transaction. | The 401-page PSX original matched hash `4fdf…ba6d1`; its consolidated statement pages 291/293/295 revalidated FY2025/FY2024 income and OCF facts. The run committed a success receipt but added **zero** new qualified financial periods: those facts were already retained. MLCF therefore remains at 3/5 annual income, 2/5 annual OCF, 3/8 direct quarterly fact sets, and no official share-count tie-out; formal outputs remain blocked. |
| 2026-08-31 | Audited the remaining owner-approved MLCF FY2024 direct-quarter leads (`psx:219092`, `psx:225623`, `psx:229941`) through exact-ID, hash-bound read-only diagnostics. | Each is a two-page image-only PSX notice. No OCR, parser relaxation, substitute source, receipt, fact, or coverage change was used. Under the current approved intake policy these documents cannot close the five-quarter gap; MLCF stays Observed, never Published. |
| 2026-08-31 | Executed the owner-approved MARI FY26 quarterly filing pilot and recorded the oversized FY26 annual limit. | `psx:264550` (59 pages) is hash-bound but `processed_unsupported`; `psx:271327` (66 pages) and `psx:275583` (64 pages) have hash-bound success receipts. None supplies a qualified consolidated direct-quarter schedule, so MARI remains 0/5 annual Revenue/PAT/EPS, 0/5 annual OCF, 0/8 direct quarters, and missing an official share-count tie-out. FY26 annual `psx:280901` exceeded the 12 MiB transport cap; no split, OCR, substitute source, fact promotion, or formal output was used. |
| 2026-08-31 | Enriched the MARI/Peshawar Observed E&P case from its successful FY26 Q2 source receipt. | `psx:271327` p.6 reports a 65% Peshawar Block working interest with operatorship. The case now displays that reported operating mechanic alongside the original 2025-09-30 disclosure. It remains `Observed`: two MARI/PSX filings are not independent-originator corroboration, and no financial truth, model, valuation, or expectation output was activated. |
| 2026-08-31 | Diagnosed the exact, hash-pinned MLCF FY26 annual as the next selected-industrial filing path. | Official PSX `psx:280589` matches its retained hash and has 10 pages, but is image-only under the existing text/geometry parser. It therefore adds zero qualified annual or share-count evidence; OCR, cap changes, and substitute sources remain disallowed. |
| 2026-08-31 | Promoted the explicitly owner-approved, source-bound MLCF FY25 capital-note candidate into the official share-count tie-out gate. | The approval manifest references only `share_candidate_bac81251d3ce82eb8ccffbec`; it is bound to official PSX filing `psx:260032`, its canonical hash, availability date, and original page 291. MLCF's share-count gate is now satisfied, but full financial truth remains red at 3/5 annual income, 2/5 annual OCF, and 3/8 direct quarters, so formal forecasts, valuation, expectations, Scenario Lab arithmetic, and lifecycle promotion remain blocked. |
| 2026-08-31 | Audited the only three retained-registry MLCF FY25 quarter notices that could add direct standalone periods: `psx:240505`, `psx:247754`, and `psx:251879`. | Their official PSX IDs, titles, periods, and pinned SHA-256 values remain internally consistent, but no matching PDF bytes exist anywhere in the repository's transient raw caches or worktrees. The current owner-review manifest forbids PDF fetches and does not allowlist these IDs; therefore page geometry, consolidated direct-quarter columns, and fact eligibility are unknown, no receipt/fact/coverage change is allowed, and any exact-ID refetch requires an explicit approved manifest change. |
| 2026-08-31 | Completed a retained-state selection audit for the required sales-led case. | No dated, attributable, hash/page-bound sales expansion event exists in the 20-company pilot, so no Observed case was forced. MARI's official PSX AI-ready data-centre campus headline (`psx:280337`) is the closest lead, but it has no retained content hash, byte record, page binding, or event record; it remains a non-load-bearing lead. The cheapest future evidence path is bounded exact-ID intake of that filing and companion clarification `psx:280161`, subject to explicit approval. |
| 2026-08-31 | Tested LUCK as a replacement for the first industrial/cement case and retained MLCF as the selected lane. | LUCK has one FY25 income triplet but no dated, attributable, hash/page-bound capacity or commissioning event; its four hash-pinned annual reports and material-information notices have no local bytes, no qualified OCF/direct-quarter/share-count machinery, and no shorter path than MLCF. MLCF remains the only selected industrial case with an observed, dated, source-bound event and a partial financial-truth path. |
| 2026-08-31 | Compared OGDC and PPL with MARI for the first E&P case and retained MARI as the selected lane. | MARI alone has two dated official PSX exploration/acquisition events bound to hashes and pages (`psx:260446` p.1 and `psx:265594` p.3), plus explicit FY25/FY26 annual leads and a hash-pinned FY24 annual anchor. OGDC and PPL have no qualifying extracted E&P event, no local document bytes, and no comparable annual anchor; none is a shorter source-qualified path. |
| 2026-08-31 | Diagnosed the owner-approved exact MLCF FY25 direct-quarter tranche: `psx:240505`, `psx:247754`, and `psx:251879`. | All three PSX PDF downloads matched their pre-existing pinned SHA-256 identities, but each is image-only under the existing text/geometry parser. The diagnostic wrote no receipt, fact, or canonical state, and direct-quarter coverage remains 3/8. OCR, parser relaxation, and substitute sources remain prohibited. |
| 2026-08-31 | Diagnosed MARI's owner-approved FY26 annual `psx:280901` through an exact, document-specific bounded transport path. | The 21,734,153-byte official PDF hash-bound to `2cd5056a…5131ba09` and has 14 pages; the normal 12 MiB cap remains unchanged for every other source. The current text/geometry parser found no qualified consolidated statement columns: most pages are image-only and readable candidates lack a current header/local scale. No receipt, fact, or coverage delta was written; the newly verified hash is pinned for any future retry. |
| 2026-08-31 | Diagnosed the owner-approved MARI sales-event pair through a dedicated material-information intake boundary. | Official PSX `psx:280337` is a one-page text-readable filing, hash-bound to `acdfaac317a7f2650a9ac11f2e98b69ebf37ce30a3134b51b61c084531286996`. Its page 1 reports that Sky47, a majority-owned MARI subsidiary, officially launched the Karakoram-01 AI-ready data-centre campus on 2026-07-24. Companion clarification `psx:280161` is image-only. Diagnosis wrote no receipt, canonical state, financial fact, financial-truth coverage, forecast, valuation, expectation, or lifecycle change. |
| 2026-08-31 | Consumed the verified MARI launch source through the restored transaction after rebuilding all event-derived artifacts. | `psx:280337` now has an `event_success` receipt and one `product_launch` reported fact: MARI's majority-owned Sky47 subsidiary officially launched Karakoram-01 on 2026-07-24. The event retains exact PSX URL, source hash, original page 1, evidence hash, level-1 source quality, and an 82/100 evidence confidence. `psx:280161` remained image-only with zero delta. MARI's financial truth remains `not_qualified`; all formal forecasts, valuation, market expectations, and case promotion remain blocked. |
| 2026-08-31 | Added the distinct MARI Sky47/Karakoram-01 sales-led IntelligenceCase seed. | The case is `Observed` only and binds to canonical event `evt_e9068dbe4b6b8493a0cb`, exact PSX filing `psx:280337`, its source/evidence hashes, page 1 and filing date. It explicitly separates the data-centre launch from MARI's E&P case, records only the reported launch, competing unknowns and monitoring needs, and contains null source-labelled model operands. MARI financial truth remains red, so forecast, valuation and market-expectations outputs stay blocked; no revenue, capacity, pricing, utilisation, timing or valuation was inferred. |
| 2026-08-31 | Bound the first official-source recovery tranche for selected MLCF and independently audited the distinct sales-led lane. | Five official MLCF PDFs are locally retained with exact hashes and zero promoted facts: the FY2022 annual and three FY2022 interim reports await deterministic native-text statement/tie-out review, while image-only FY2021 remains quarantined. CNERGY’s requested sales-record PDF is unavailable at its exact issuer URL; an alternative issuer-hosted, page-dated 2018 gasoline-supply-share document is retained as observed-only evidence with zero case or financial promotion. This does not select CNERGY or change any financial-truth count. |
| 2026-08-31 | Completed the first deterministic native-text fact-candidate pass on four retained MLCF filings. | The review bound native-text statement pages, then rejected every candidate under consolidated statement, visible unit/period/header, full-row geometry and ambiguity rules. It produced zero audit candidates, facts, coverage deltas, case changes or output activation. The first candidate pass therefore closes a false-positive risk rather than claiming financial-truth progress; the remaining path requires a tighter table-aware extractor and independent tie-out. |
| 2026-08-31 | Isolated four FY2022 MLCF annual table cells with current-period header and cell geometry. | Official PSX Financials annual `psx:194111` provides source-bound, consolidated FY2022 audit candidates for Sales-net, profit after taxation, basic EPS and net cash generated from operating activities. They retain units, original pages 273/275, current-column geometry and exact source hash, but remain promotion-blocked pending independent full-statement extraction and annual tie-out. No financial-truth count, case lifecycle or formal output changed. |
| 2026-08-31 | Expanded the retained MLCF FY2022 annual review into a fail-closed statement-schedule audit. | The exact-hash PSX annual now yields 16 local-geometry, audit-only consolidated candidates across pages 271, 273 and 275, plus 2021 comparative cells where the same table binds them. Nine required rows remain explicit omissions rather than inferred: seven balance-sheet rows without page-local consolidated basis, reported EBITDA, and depreciation/amortisation. The receipt cannot write canonical facts, alter financial truth, or activate outputs; independent statement extraction, period tie-out, conflict review and the existing financial-truth acceptance path remain mandatory. |
| 2026-08-31 | Made the FY2022 annual schedule’s point-in-time gap explicit. | The retained official document has no bound publication or availability date. Every audit candidate is therefore marked not model-ready; no date is inferred, and an official availability-date binding is now an explicit prerequisite to any canonical promotion. |
