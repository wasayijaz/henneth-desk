# Event-to-Value Alpha — Continuation Handoff

## AUTHORITATIVE PAUSE CHECKPOINT — 2026-09-13 23:15 PKT

This section supersedes older checkpoints below for continuation purposes. Older
entries are retained as history, not as current state.

### Objective and definition of done

Complete Event-to-Value Alpha with three source-grounded, model-ready and
Published Intelligence Cases: one E&P, one industrial/cement expansion and one
sales-led expansion. Each must have five qualified annual years, eight qualified
reported quarters, statement/share tie-outs, a real dated event, competing
hypotheses, sector-specific drivers, cutoff-safe analogues, deterministic
eight-quarter bear/base/bull forecasts, valuation, price-implied expectations,
Ask Henneth answers, Scenario Lab, thesis monitoring, provenance and the final
production/authentication gates. No case is Published yet.

### Git and release state

- Authoritative worktree: `D:\PSX Trader X Claude\.codex-alpha-readiness-integration`
- Branch: `codex/alpha-readiness-integration`
- Last product-code HEAD before this documentation checkpoint: `0280f29c` —
  `ci: align financial contracts with current parser and share tie-out`.
- Upstream: use the tip of `origin/codex/alpha-readiness-integration`; the
  documentation-only pause checkpoint follows `0280f29c` and is pushed.
- Never push `main`, merge, publish or deploy without fresh owner authorization.
- Part 0 live release proof remains deferred. GitHub validation/preview work is
  preserved; production remains unchanged and no Vercel work is authorized.
- The dirty parent `D:\PSX Trader X Claude` must not be reset, cleaned, stashed or
  used as the CI implementation worktree. A paused UI worker accidentally wrote
  CI UI edits there; preserve them until they can be compared safely.

### Last completed, verified and pushed milestones

- `809b66ef`: cement-expansion analogue distribution engine now requires explicit
  publication availability, exact source/hash/page/URL binding, pre-event
  baselines, mature endpoints, data cutoffs, independent episodes and N >= 3 per
  horizon. Current retained result is honestly 0 qualified episodes from 43 rows;
  all distributions remain suppressed and three evidence slots are explicit.
- `e37a42a8`: removed decorative CI and sign-in background-image requests while
  retaining company logos and lightweight section/chart motion. CI navigation,
  no-background and motion checks passed. The Desk is a separate product.
- `05a2844c`: Company Brain, source index, MLCF readiness and evidence watchlist
  rebuild deterministically and preserve integrity metadata; five focused checks
  passed. Current authoritative MLCF counters remain 3 annual triplets, 0 direct
  reported quarters, 2 annual OCF and 1 official share-count tie-out.
- `0280f29c`: financial graph fixtures follow parser revision v6 and the MLCF gap
  contract accepts the official share-count tie-out while formal outputs remain
  blocked. Both focused checks passed.

### Work in progress when paused — do not commit as-is

Intentional but incomplete code in the feature worktree:

- `scripts/financial_statement_facts.py`,
  `scripts/mlcf_fy25_full_schedule_audit.py`,
  `scripts/check_mlcf_fy25_full_schedule_audit.py`: interrupted MLCF `psx:260032`
  parser/audit work for PBT, tax, capex and depreciation. It has not received a
  final GLM report or clean integration review.
- `config/owner_financial_assumption_handoff.json` and
  `scripts/check_owner_financial_assumption_handoff.py`: interrupted fail-closed
  handoff repair. The checker still failed before pause because DGKC is partial,
  not input-ready.
- `Henneth Desk 2.CI.0/app.js`, `Henneth Desk 2.CI.0/api/ask_contract.js` and
  `scripts/check_causal_foundations_ui.mjs`: partial UI/API repair copied into the
  correct worktree. Causal and Ask checks pass; Company Brain, financial coverage
  and monitoring UI checks still fail.

Generated/restage churn remains across `state/company_intel/*.json`,
`state/company_financial_series.json` and
`Henneth Desk 2.CI.0/data/company_intelligence.json`. Do not stage it broadly.
Untracked `.cache/`, `.agents/skills/lieflat-charts/`, MARI receipt scripts/artifact
and `_patch_mari_enp_readiness.py` also remain unreviewed. Never use `git add -A`.

### Verified checks and known failures

Passed during the final wave:

- cement analogue engine plus historical analogue/state-map/event-study,
  conditional benchmark, global no-lookahead and Rule 4 checks;
- Company Brain, Brain source index, Brain formal links, MLCF/PIOC readiness and
  evidence watchlist checks;
- financial graph and MLCF financial-truth gap checks;
- CI JavaScript syntax, causal-foundations UI, Ask Henneth, navigation,
  no-background-image and premium-motion checks.

Latest measured aggregate before these repairs: 56/69 checks passed. Known
remaining failures included owner assumption handoff, Company Brain UI,
financial-coverage UI, monitoring UI and PSO Ask leakage; the latter Ask failure
is now fixed locally but not committed. Do not claim the aggregate is green until
it is rerun after the incomplete lanes are reconciled.

MLCF canonical restage remains unsafe now. The verified v6 parser previously
emitted 40 loadable FY2024/FY2025 facts, but that added no qualification periods
because PBT, tax, capex and depreciation/EBITDA lineage were missing. No v6
canonical receipt exists. Retry only if the interrupted parser work proves a real
fact-level delta and the ordered aggregate is green.

### Source-path corrections retained

- DGKC FY2025 issuer annual is already qualified; the PSX distributor copy is the
  same report and must never be double-counted.
- Preferred retained DGKC FY26 tranche remains issuer Q1
  `issuer:e2aaab14b5e3e2cd59997280`, issuer Q2
  `issuer:a1b59989dc0600cfdfe4870c`, and PSX Q3 `psx:275962`.
- `psx:264230` and `psx:271381` remain metadata leads unless freshly fetched,
  hash-bound and geometry-verified under owner-approved intake.
- The cement analogue lane has no source-bound target case and no qualified
  historical episodes yet; it must not calibrate scenarios or forecasts.

### Execution order on resume

1. Inspect and reconcile the interrupted MLCF parser/audit diff. Prove exact
   page-bound PBT/tax/capex/depreciation facts or record zero delta; do not guess.
2. Finish the fail-closed owner handoff and the three remaining CI UI contracts in
   the feature worktree. Compare but do not alter accidental parent-main edits.
3. Run focused checks, inspect each diff, then make and push separate narrow
   feature-branch commits for verified milestones only.
4. Rebuild the ordered CI state and rerun the aggregate/completion gate. Attempt
   canonical `psx:260032` restage once only if the parser delta is real and the
   baseline is green.
5. Continue the vertical order: complete one cement investor slice, then implement
   E&P and sales-led cases independently. Share only the case/evidence/provenance/
   run/confidence/monitoring/UI envelope, never one universal sector model.

### Coordination guardrails

GLM task `01a053cc-1d39-7fb1-a432-78c20edef4cc`, analogue task
`01a09b94-5828-7673-8730-fb9e6833a1ec`, UI task
`01a04910-f949-73f3-9cbe-5a143bcc00c4`, and local agents were told to pause.
On resume, GLM should receive most implementation work; Luna High/GPT-5.5 handle
parallel execution and focused review. The UI task must use only
`Henneth Desk 2.CI.0` / `ci.henneth.app`; it must not open or modify the separate
Henneth Desk/dashboard. No provider expansion, OCR, qualification relaxation,
invented facts, release work, main push or deployment without fresh approval.

### CONTINUE FROM HERE

Resume only in `D:\PSX Trader X Claude\.codex-alpha-readiness-integration` at
the pushed tip of `origin/codex/alpha-readiness-integration` (whose last product
code milestone is `0280f29c`). First inspect the uncommitted MLCF parser/audit
diff and obtain or reproduce its exact fact-level result. In parallel, finish the
owner-handoff and remaining three UI contracts. Commit and push only independently
verified files, then rerun the aggregate gate. All three cases remain unpublished
and all formal forecasts, valuations and market-expectations outputs remain
fail-closed.

## Objective

Deliver three source-grounded, published Intelligence Cases: one industrial/cement,
one E&P, and one sales-led. Each Published case needs five annual years, eight
direct reported quarters, source-qualified/tied-out financial truth, its own
sector-specific deterministic model, scenarios, valuation, price-implied
expectations, provenance, monitoring, and final production/auth gates. No case
may be Published early.

## Current checkpoint

- Worktree: `D:\PSX Trader X Claude\.codex-alpha-readiness-integration`
- Branch: `codex/alpha-readiness-integration`
- HEAD: `aa6cdcee` — `ci: record bounded MARI and sales evidence gaps`
- Upstream: `origin/codex/alpha-readiness-integration`; that HEAD is pushed.
- `main`, production, deployment, publishing, and Vercel were not touched.

## Last verified milestones

- `3cd12445` — MLCF FY22 schedule evidence audit; zero qualified promotion.
- `7d6b27b8` — MLCF FY25 local-cache evidence-gap receipt.
- `836c3cdf` — fail-closed parser support for a unique, nearby, column-aligned
  numeric band when PyMuPDF separates statement values by block. The focused
  geometry check and existing financial-statement parser self-check passed.
- Exact read-only diagnostic for official `psx:260032` verified 401 pages and
  pinned SHA-256 `4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1`.
  It now recognizes aligned annual OCF geometry on page 295, but does not prove
  all annual Revenue/PAT/EPS/share operands.
- `1c0d60f5` — MLCF's case envelope now projects its counters from authoritative
  financial-truth state rather than freezing its current blocked counts. The
  contract remains strict (5 annual years / 8 direct quarters / 5 annual OCF),
  permits a future qualified transition, and still blocks formal engines until
  financial truth and owner-approved forward inputs both pass.
- `aa6cdcee` — records the completed retained MARI Q1–Q3 geometry review and
  distinct sales-led candidate review. Both were zero-delta outcomes; neither
  weak evidence nor a duplicate MARI case was promoted.

## What happened immediately before pause

1. The approved canonical restage of `psx:260032` was attempted once after the
   counter-contract checkpoint. It produced no durable v6 receipt or canonical
   fact change; do not retry it merely because it was silent. Any future retry
   needs a new, evidence-based parser reason and must report its exact delta.
2. The completed MARI mapping established a zero financial-truth delta. Q1
   `psx:264550` is unsupported under current strict statement geometry; Q2
   `psx:271327` p38 and Q3 `psx:275583` p18 have mixed direct/cumulative income
   columns whose direct-three-month roles are not safely bound. Q2/Q3 OCF is
   cumulative 6M/9M only. MARI remains 0/5 annual, 0/8 direct-quarter and has
   no official share-count tie-out.
3. Sales-led candidate selection was bounded and remains unresolved. CNERGY's
   strongest verified retained source is only an observed `sales_mix_expansion`
   event (`issuer:439f94b15635143d5d16b663`, page 1, pinned hash); its primary
   sales-record document is unavailable (404/no bytes/hash), and its financial
   truth is zero across all load-bearing gates. PSO/GAL/BOP are weaker. Do not
   promote a sales-led case without a new owner-approved intake path.
4. The retained MLCF FY2022 annual `psx:194111` remains audit-only: pages
   271/273/275 provide 16/25 consolidated candidates, but nine load-bearing
   rows are absent/ambiguous and the exact source has no immutable
   `published_at` or `available_on` binding. No promotion or code change is
   safe from this review.

## Working-tree warning

Do **not** commit or clean/reset/stash the working tree as-is.

- Unrelated owner/other-session files: `Henneth Desk 2.CI.0/data/company_intelligence.json`
  and `scripts/check_reprocess_company_documents.py`.
- This handoff file is newly updated and uncommitted. It was intentionally not
  committed/pushed because the owner requested an immediate pause. Do not stage
  it together with the two unrelated files.

## Checks run this session

- PASS: `python -m py_compile scripts/financial_statement_facts.py
  scripts/check_mlcf_fy25_parser_geometry.py`.
- PASS: `scripts/check_mlcf_fy25_parser_geometry.py`.
- PASS: `scripts/check_financial_statement_facts.py`.
- PASS: `scripts/check_financial_truth_qualification.py` before the interrupted
  counter lane, and after the committed counter-contract milestone (20 retained
  companies; DGKC remains the leader).
- PASS: `scripts/check_intelligence_cases.py`,
  `scripts/check_formal_financial_engines.py`,
  `scripts/build_ci_artifact_integrity.py`, and
  `scripts/check_ci_artifact_integrity.py` for `1c0d60f5`.
- PASS: `scripts/check_mlcf_fy22_table_audit.py` and
  `scripts/check_mlcf_fy22_full_schedule_audit.py` (both remain intentionally
  fail-closed); the integrity finalizer/checker was rerun at the existing
  committed envelope to restore checker-side metadata removal.
- FAIL, pre-existing-state check: `scripts/check_financial_model_inputs.py` at
  `legacy model load`; parser checks before that assertion did not fail. Treat
  as a baseline/reconciliation issue until compared to a clean baseline.
- SAFE ROLLBACK: canonical `psx:260032` restage, for the frozen-counter reason
  above. No facts or receipt were written.

## Active execution order

1. Keep the local safety floor active. Live release proof remains deferred to
   the final release gate; no Vercel work is authorized.
2. Finish one industrial/cement vertical slice (MLCF) only through factual
   qualification and deterministic investor workflow; it remains non-Published
   until all five-year/eight-quarter/tie-out gates actually pass.
3. Complete E&P (MARI) and sales-led lanes independently. Share only the case,
   evidence/provenance, run, confidence, monitoring and UI envelope—not a
   universal sector-economic model.

## Resume guardrails

Terra orchestrates; Luna High and GPT-5.5 do most execution; use Codex Spark
for focused deterministic tests when available. Commit and push only small,
verified feature-branch milestones. Never push `main`, merge, publish, deploy,
perform Vercel work, add a provider, OCR, relax qualification, or manufacture
facts without fresh owner authorization.

## Immediate next actions

1. Inspect the interrupted, no-diff MARI mixed-duration parser investigation;
   resume only if a deterministic page-local header/column-role proof can bind
   direct 3M Revenue/PAT/EPS without weakening statement, unit or basis rules.
2. If that cannot be proven, leave MARI at zero delta and return to the next
   non-duplicative MLCF retained-report gap; never retry FY25 merely because it
   is available.
3. Keep the sales-led slot unselected until an owner-approved exact-source
   intake can establish both a distinct dated sales event and real financial
   coverage.
4. Before a new focused milestone, regenerate/check the complete artifact
   envelope and stage only files owned by that milestone.

## CONTINUE FROM HERE

Resume in `D:\PSX Trader X Claude\.codex-alpha-readiness-integration` on
`codex/alpha-readiness-integration` at pushed commit `aa6cdcee`. First inspect
the interrupted MARI mixed-duration parser lane and either prove a strict
page-local direct-quarter mapping or close it as zero delta. MLCF, MARI and
every sales candidate remain not qualified; all formal outputs stay blocked.
ZLM and every worker remain paused until the owner explicitly asks to resume
them.

## Pause checkpoint — 2026-09-01

- Current branch/HEAD: `codex/alpha-readiness-integration` at `cb864bff`
  (`ci: add CNERGY sales vertical slice`), three commits ahead of
  `origin/codex/alpha-readiness-integration`. The remote push of private CI
  state was rejected by the safety gate; no workaround was attempted.
- Local verified milestones after the prior handoff: `b7452551` adds the
  read-only Event-to-Value Product Readiness surface; `6ad157bf` adds the
  fail-closed MLCF/PIOC industrial vertical-slice contract; `cb864bff` adds
  the fail-closed CNERGY sales-led vertical-slice contract. Each keeps formal
  outputs blocked while financial truth is red.
- MLCF checker passes but is blocked at canonical event/source binding and
  financial truth. CNERGY checker passes but proves that retained sales
  performance/sales-mix records are not a case-eligible sales-infrastructure
  expansion. MARI's GLM vertical-slice artifact was not emitted and must be
  rerouted only after resume.
- Luna was interrupted while adding MLCF/CNERGY artifacts to the canonical
  artifact-integrity list. The working tree is intentionally dirty, including
  `scripts/check_ci_artifact_integrity.py`, `artifact_integrity.json`, both
  new vertical-slice artifacts, the readiness artifact, the CI slice, and a
  broad set of pre-existing generated CI state. Do not reset, clean, stash, or
  force-commit it. First action on resume: inspect this dirty diff, finish the
  narrow artifact-integrity coverage repair, and run the documented
  deterministic rebuild sequence before any new case work.


## Milestone Checkpoint — 2026-09-13

- Current branch/HEAD: `codex/alpha-readiness-integration` at `b6d5dbe1` (`ci: implement deterministic event, valuation, analogue, and scenario engines across three golden cases`).
- Local verified milestones committed:
  * Case A (MARI E&P): `mari_enp_valuation_engine.py` (90 checks passed), `mari_enp_scenario_lab.py` (65 checks passed), `mari_enp_analogue_engine.py` (721 checks passed), `mari_enp_ask_engine.py` (794 checks passed), and `build_mari_enp_vertical_slice.py` (121 checks passed).
  * Case B (MLCF Cement): `mlcf_cement_expansion_model.py` (556 checks passed), `mlcf_cement_scenario_lab.py` (1154 checks passed), `mlcf_cement_analogue_engine.py` (470 checks passed), and `build_mlcf_industrial_vertical_slice.py` (passed).
  * Case C (PSO Sales): Candidate audit completed in `docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md` (selecting PSO), `pso_sales_expansion_model.py` (19 checks passed), and `check_cnergy_sales_vertical_slice.py` (passed).
  * Gate Hardening: Single authoritative fail-closed financial-truth activation gate in `scripts/formal_financial_engines.py` and `scripts/build_ci_slice.py` (`check_formal_financial_engines.py` passes with synthetic computed & real state blocked).
  * Financial Truth Progress: MLCF consolidated annual OCF promoted to 2/5 (FY24 & FY25 from official report `psx:260032` p.295); share count tied out.
  * Artifact Integrity: All 64 CI artifacts sealed in `state/company_intel/artifact_integrity.json` with reproducible UTC cutoff; `check_ci_artifact_integrity.py` and `check_event_to_value_product_readiness.py` pass cleanly.
