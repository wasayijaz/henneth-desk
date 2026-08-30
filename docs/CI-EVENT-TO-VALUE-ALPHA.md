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

## Current baseline — 2026-08-29

| Area | Retained evidence | Status | Implication for Alpha |
|---|---|---|---|
| Architecture coverage | `state/company_intel/completion_matrix.json` | 61 complete, 4 partial, 4 blocked of 69 | Useful foundations exist; this is not proof of investor-ready cases. |
| Financial model readiness | `state/company_intel/forecast_readiness.json` | MLCF and DGKC input-ready; all formal outputs non-computed | No company currently clears Alpha’s financial-output gate. |
| Formal engines | `financial_forecasts.json`, `formal_valuations.json`, `market_expectations.json` | Deterministic code exists; 0 computed / 20 | Alpha must prove live outputs for three cases, not merely engine code. |
| Historical analogue state | `state/company_intel/conditional_benchmarks.json` | 21 dated benchmarks; thin samples remain suppressed | Golden cases need case-specific, cutoff-safe analogue evidence. |
| Private thesis storage | `private_thesis_storage_receipt.json` | Schema configured; live CRUD/cross-user RLS proof absent | Persisted owner scenarios/theses stay disabled until verified. |
| CI release integrity | Generated CI state carries a reproducible build envelope; live preview/production proof has not been run | Deferred by owner | Part 0 remains preserved and does not block current Alpha product development. |
| Financial truth qualification | `financial_truth_qualification.json`; `financial_reprocess_blockers.json` | DGKC leads on retained coverage but is not golden; MLCF is the selected industrial case | MLCF has 3/5 annual income triplets, 2/5 consolidated annual OCF periods, and 3/8 qualified direct consolidated quarters (FY26 Q1–Q3); no owner-approved official share-count tie-out exists. Formal outputs remain fail-closed. |

## Golden-company selection register

Selection is evidence-led, not based on a preferred ticker. A company is chosen
only once its retained official source coverage can support five fiscal years,
eight reported quarters, load-bearing share-count data, and a real dated event.

| Case | Required event family | Current shortlist | Selection status | Reason / next evidence |
|---|---|---|---|---|
| A — E&P | exploration, appraisal, development, or production | OGDC, PPL, MARI | Observed | Mari Energies is selected for an observed-only E&P seed because its retained official PSX filing `psx:265594` is dated, hash-bound and page-cited for offshore exploration-block acquisition (2025-11-13). It is not Corroborated, Modelled, Validated or Published: working interest, operator status, economics, technical outcomes and qualified financial history remain absent. OGDC remains a source observation only; PPL has no qualifying retained E&P event. |
| B — industrial/cement | expansion, hiring, procurement, maintenance, commissioning, or capacity | MLCF, LUCK, DGKC | Observed | MLCF's dated, official acquisition/control of Pioneer Cement is the strongest retained lane: PSX `psx:267429` (2025-12-18) describes control mechanics, and `psx:275425` (2026-04-28) confirms PIOC dispatches joined local-market totals after acquisition in February 2026. Treat the February date as month-only; dispatch percentage remains audit-only. DGKC and LUCK remain unselected. |
| C — sales-led | sales hiring, geography, branch/channel, product-sales infrastructure | PSO, GAL, BOP reviewed | Unselected | No retained dated, canonical sales-led operating event. BOP `psx:272102` (2026-03-05) is a dated generic digital/customer-acquisition strategy narrative, not a discrete rollout; PSO corporate-card/network clues have null event dates and 0 qualified periods; GAL has no event and 0 qualified periods. No sales-led case is selected. |

## Ordered execution log

| Part | Gate | Status | Visible investor behaviour delivered | Data coverage / unresolved blocker |
|---|---|---|---|---|
| 0 | Release integrity | Deferred by owner | Every generated private CI artifact is now sealed with a common UTC cutoff, source commit, generator version, and hash manifest; stale or mismatched envelopes fail closed. | Preserve the release work for Alpha readiness; do not run live preview/production proof while Part 1 product work continues. |
| 1 | Model-ready financial truth | In progress | Financial truth is the authoritative fail-closed gate for formal forecast, valuation, and market-expectations output; legacy three-period readiness is descriptive only. | Selected MLCF case: 3/5 annual income triplets, 2/5 consolidated annual OCF, 3/8 direct consolidated quarters, and no owner-approved official share-count tie-out. Official FY25 `psx:260032` is hash-bound and v2-qualified; its capital note now has a source-bound, unapproved candidate path. |
| 2 | Three real operating events | In progress | MLCF has an `Observed` IntelligenceCase seed for the Pioneer Cement control/acquisition chain, and Mari Energies has an `Observed` E&P seed for its official offshore exploration-block acquisition disclosure. | Both cases are deliberately not Corroborated, Modelled, Validated, or Published: neither has independent corroboration, source-qualified incremental financial impact or a complete financial-truth gate. |
| 3 | Sector event models | Not started | None | Requires one deterministic E&P, capacity/hiring, and sales-ramp model contract. |
| 4 | Eight-quarter event-to-financial models | Not started | None | Requires complete actuals and source-labelled analyst assumptions. |
| 5 | Historical analogues | Not started | None | Requires case-specific domestic/peer search with historical cutoffs. |
| 6 | Valuation and expectations | Not started | None | Requires computed model outputs and appropriate valuation schedules. |
| 7 | Intelligence Case interface | Not started | None | Requires published case objects and a deterministic rendering contract. |
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
