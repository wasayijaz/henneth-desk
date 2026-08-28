# Event-to-Value Alpha — Continuation Handoff

## Objective

Deliver three source-grounded, published Intelligence Cases: one cement/industrial,
one E&P, and one sales-led. Each must have five annual years, eight reported
quarters, source-qualified/tied-out financial truth, sector-specific deterministic
models, scenarios, valuation, price-implied expectations, provenance, monitoring,
and the final production/auth gates. No case is Published early.

## Checkpoint

- Worktree: `D:\PSX Trader X Claude\.codex-release-push`
- Branch: `codex/financial-truth-part1`
- HEAD before this handoff commit: `9b2193d077d23056bb92bd95667b3aa5031c0c14`
- Upstream: `origin/codex/financial-truth-part1`; current HEAD is pushed.
- `main` was not changed, merged, deployed, published, or promoted. Vercel work
  remains forbidden.

## Last focused milestones

- `c439ddb8` — bounded PSX annual-restage transport.
- `edf53e5a` — OCF-label extraction support.
- `6df28e9c` — fail-closed share-capital candidate checker.
- `7294289b`, `a300f7bc`, `db993bb2` — rebuild ordering and explicit rollback
  diagnostics for restage transactions.
- `6f19e74e` — exact-hash retained PSX annual fallback. **Do not extend or use it
  as product evidence now:** `psx:260947` is a distributor duplicate of the
  canonical issuer FY25 annual.
- `543abfd9`, `ee91fbfa`, `9b2193d0` — vertical-case execution order, independent
  sector economics, and DGKC PP-bag-event no-go.

## What was in progress at pause

The first DGKC vertical lane was being tested. The PP-bag commissioning record
`evt_c66c444c35780cf5951e` was rejected as an `Observed` seed: it has null dates,
truncated evidence, unresolved NPL/NPPCL attribution, and no event-study/causal
support. No case was created. Separately, the canonical issuer FY25 annual was
identified as the only legitimate source path for FY25 OCF and share-capital
operands; a read-only availability check returned HTTP 200 for its existing URL.

## Source-path correction

- FY25 canonical annual: `issuer:39fe974f6ef82bbeadf83938`, hash
  `96ca1120b238541d4916fb1c777614ee6045f30ab130d2f18e8a1fd5c62bdf73`.
  It is already v2-qualified for FY24/FY25 income facts and must **not** be
  double-counted with PSX distributor variant `psx:260947`.
- Preferred retained FY26 quarter tranche: Q1
  `issuer:e2aaab14b5e3e2cd59997280`, Q2
  `issuer:a1b59989dc0600cfdfe4870c`, Q3 `psx:275962`.
- `psx:264230` and `psx:271381` are metadata leads only unless freshly fetched,
  hash-bound, and geometry-qualified. Do not treat them as verified inputs.

## Current evidence and blockers

- DGKC financial truth remains `not_qualified`: 4/5 annual income triplets,
  0/5 annual OCF, 0/8 direct reported quarters, and no official share-count
  capital-note tie-out. Formal forecast, valuation, and expectations remain
  fail-closed.
- The canonical issuer FY25 record retains capped income facts but no retained
  page text for OCF/capital-note pages. Retrieval must verify the existing exact
  issuer URL/hash before targeted extraction; never use the PSX duplicate as a
  proxy.
- A single-document PSX duplicate transaction rolled back at
  `checker:preflight.py`: `check_company_brain_source_index.py` reported stale
  thesis-monitoring metadata and the CI no-lookahead tail also failed. A normal
  non-transaction `preflight.py` passed. Treat this as a branch transaction
  consistency blocker pending a clean-baseline comparison; it is not financial
  fact evidence and must not be bypassed.
- No retained industrial alternative is Observed-ready. The best lead,
  `evt_7f4ca5a74010800d1a88` (30MW CFPP), is also undated/audit-only.

## Working-tree warning

Do not commit the current dirty state as-is. It contains failed-restage/generated
churn in `Henneth Desk 2.CI.0/data/company_intelligence.json` and many
`state/company_intel/*.json` artifacts (including integrity, financial truth,
formal-engine, monitoring, and case surfaces). It also has untracked root
`_manifest_old.json` and `_manifest_new.json`; these are temporary release
comparison residue and must stay excluded. No uncommitted intentional source
code change is known at pause; this handoff file is the only intentional pending
file.

## Verified checks already run

- PASS: `scripts/check_pdf_chunking.py`.
- PASS: `scripts/check_reprocess_company_documents.py` (including rollback-stage
  assertions).
- PASS: focused Python compile of the reprocess files.
- PASS: `scripts/check_financial_truth_qualification.py`.
- PASS: `scripts/check_formal_financial_engines.py` (synthetic qualified case;
  real state correctly remains blocked).
- PASS: normal `scripts/preflight.py` with one non-gating warning: 102 newly
  added universe tickers are still backfilling history.
- BLOCKED by that same warning: `scripts/preflight.py --strict`.
- FAILED transaction: exact PSX duplicate restage, safely rolled back with no
  receipt and no qualified-fact delta; diagnostic stage above.

## Active execution order

1. Keep the local safety floor active; defer live deployment proof to final
   release.
2. Prove one defensible DGKC vertical investor slice before broad backfill. If
   no dated industrial event is available quickly, do not hunt indefinitely.
3. Build cement economics concretely for its case only; then implement E&P and
   sales-led economics independently. Share only the narrow IntelligenceCase,
   evidence/provenance, deterministic-run, confidence, monitoring, and UI
   envelope—never a universal economic-driver/formula model.
4. Finish the full five-year/eight-quarter/share/tie-out publication gate before
   Published status, then repeat for E&P and sales-led.

## Resume guardrails

Terra orchestrates; Luna High and GPT-5.5 execute most work; use Codex Spark for
routine focused tests when available. After each small verified milestone, make
a focused commit and push this feature branch only. Never push `main`, merge,
publish, deploy, perform Vercel work, or alter production without fresh owner
authorization.

## Immediate next actions

1. Compare the transaction-only preflight failure with a clean baseline and
   isolate the stale metadata writer without changing financial qualification.
2. Retrieve the exact canonical issuer FY25 annual only after pinning its
   existing hash, then extract/qualify OCF and share-capital operands from its
   original pages; record zero delta honestly if unsupported.
3. Audit the three preferred retained FY26 issuer/PSX quarter documents for
   direct three-month columns, identity, text geometry, and availability dates.
4. Make a bounded retained-state search for a dated, attributable industrial
   event; if none exists, record DGKC as financial-only/unselected and move to
   the strongest evidence-backed industrial lane.

## CONTINUE FROM HERE

Resume in `D:\PSX Trader X Claude\.codex-release-push` on
`codex/financial-truth-part1`. First isolate the transaction-only stale-metadata
failure against the clean baseline. Then use only the canonical issuer FY25
annual (`issuer:39fe974f6ef82bbeadf83938`, pinned hash above) for OCF/share
evidence, never the PSX duplicate. Keep DGKC unselected until a dated,
attributable industrial event is proven; do not manufacture a case or relax any
financial-truth, provenance, or point-in-time gate.
