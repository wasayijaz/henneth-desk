# Event-to-Value Alpha — Part 1 retained-evidence gap map

**Audit date:** 2026-08-31 (PKT)  
**Coordination base:** `b6fee018`  
**Scope:** retained state only. This map does not fetch, parse, restage, approve,
promote, or infer a fact. It records what the current gates accept and what they
still reject.

## How to read this map

The publication proof is shared across sectors: five qualified annual income
triplets, five qualified annual operating-cash-flow periods, eight qualified
direct reported quarters, an official share-count/capital-note tie-out, no
unresolved conflicts, and source-qualified event economics. The economic
operands are not shared. Cement/acquisition, E&P, and sales-led cases keep
separate models; only identity, lifecycle, provenance, cutoff, scenario/run
lineage, monitoring, and case-page contracts may be reused.

Current lifecycle truth is two `Observed` cases and zero `Corroborated`,
`Modelled`, `Validated`, or `Published` cases. The sales-led slot is unselected.

## Industrial lane — MLCF / Pioneer Cement

Authoritative sources:

- `state/company_intel/financial_truth_qualification.json`
- `state/company_intel/mlcf_pioc_readiness_manifest.json`
- `state/company_intel/official_share_capital_candidates.json`
- `state/company_intel/intelligence_cases.json`

### Company financial-truth gate

| Requirement | Qualified now | Exact retained status | Remaining gate |
|---|---:|---|---|
| Annual Revenue / attributable PAT / basic EPS triplets | 3 / 5 | 2026-06-30, 2025-06-30, 2024-06-30 | Two additional distinct eligible annual periods. The gate does not nominate dates, so this map does not invent them. |
| Direct consolidated three-month Revenue / attributable PAT / basic EPS sets | 3 / 8 | 2026-03-31, 2025-12-31, 2025-09-30 | Five additional qualified direct-quarter periods. Retained metadata or cumulative interim figures do not count. |
| Annual consolidated operating cash flow | 2 / 5 | 2025-06-30, 2024-06-30 | Three additional eligible annual OCF periods. |
| Official share-count/capital-note tie-out | 0 / 1 | `psx:271712` p.31 has a source/hash/page-bound, arithmetically tied candidate, but it is `approved: false`, has no `available_on`, and is candidate-only. | Verified restage plus explicit owner approval through the existing gate. The candidate cannot activate financial truth. |

The current financial-tie-out status is `blocked`. Forecast, valuation, and
market-expectations output must remain blocked even though the historical MLCF
model-input adapter reports ready under its narrower legacy scope.

### Acquisition/cement event bridge

The observed case proves the MLCF control transaction and later inclusion of
PIOC dispatches. It does not prove a standalone PIOC earnings contribution or
capacity impact. The exact missing event-model inputs are:

- source-qualified PIOC contribution and MLCF consolidation bridge by retained
  period;
- transaction-chain debt and cash position plus post-transaction share-capital
  tie-out;
- incremental revenue, margin, EPS, operating cash flow, debt, and share count;
- cement capacity, commissioning/ramp, capex, and fuel/power/freight schedules.

PIOC is not in the current CI pilot and has no retained official financial
document, financial-truth row, or formal model-input row. These are blockers,
not zero values. MLCF's historical actuals cannot stand in for PIOC or the
transaction bridge.

## E&P lane — MARI / Peshawar Block

Authoritative sources:

- `state/company_intel/mari_enp_evidence_readiness.json`
- `state/company_intel/intelligence_cases.json`
- `docs/CI-EVIDENCE-LANE-AUDIT.md`

The active case is `case_mari_working_interest_observed_v1`, sourced to
`psx:260446` p.1. It reports acquisition of working interest in Peshawar Block
as operator. The older offshore disclosure is retained evidence but is not an
alias for, or substitute for, the active case.

### Financial-history slots

| Slot | Retained status | Why it does not qualify |
|---|---|---|
| Annual 2026-06-30 | Metadata lead: `psx:280901` | Indexed title/date only; no retained content hash or parsed Revenue/PAT/EPS triplet. |
| Annual 2025-06-30 | Metadata lead: `psx:258895` | Indexed title/date only; no retained content hash or parsed triplet. |
| Annual 2024-06-30 | Audit-only/quarantined issuer facts | Page/hash evidence exists, but statement identity, eligibility, and complete triplet are not model-ready. |
| Annual 2023-06-30 | Audit-only | Retained evidence is not a complete eligible income triplet. |
| Annual 2022-06-30 | Unavailable | No retained annual-period evidence. |
| Quarter 2024-09-30 | Unavailable | No retained quarterly-period evidence. |
| Quarter 2024-12-31 | Unavailable | No retained quarterly-period evidence. |
| Quarter 2025-03-31 | Unavailable | No retained quarterly-period evidence. |
| Quarter 2025-06-30 | Unavailable | No retained quarterly-period evidence. |
| Quarter 2025-09-30 | Metadata lead | Indexed result title; no model-ready direct-quarter facts. |
| Quarter 2025-12-31 | Metadata leads: `psx:269182`, `psx:271327` | Indexed official documents; values are not parsed or qualified as a direct three-month triplet. |
| Quarter 2026-03-31 | Metadata lead: `psx:275583` | Indexed official document; values are not parsed or qualified. |
| Quarter 2026-06-30 | Unavailable | No retained quarterly-period evidence. |

Result: 0 / 5 model-ready annuals and 0 / 8 model-ready quarters. The retained
shares-out value is a market-operand metadata lead without an official filing
page/hash and cannot satisfy the share-count gate.

### E&P event-model operands

Operator status and Peshawar Block identity are observed text only. The retained
record does not provide a qualified working-interest percentage, consideration,
resources/reserves, exploration or development timing, production/decline,
well/development cost, opex, royalty/tax, hydrocarbon mix, commodity price, FX,
or project cash-flow schedule. No numeric E&P run may activate from these
absences.

## Sales-led lane — no selected company

Authoritative retained audit: `docs/CI-EVIDENCE-LANE-AUDIT.md`.

There is no eligible dated, attributable, discrete sales-expansion event in the
retained 20-company pilot:

- BOP `psx:272102` is generic strategy language, not a dated rollout;
- PSO's outlet/card/service records are undated same-issuer product material;
- GAL has no corresponding sales event in the event ledger.

Therefore no company-specific Part 1 financial slot map is authoritative for
the sales lane yet. Selecting a company because its accounts are convenient
would reverse the evidence-led order. The event gate must clear first; only
then should that company's five-year/eight-quarter/share-count gaps and its
sales-specific operands—channel/geography, sales/support capacity, productivity
ramp, acquisition/retention, gross margin, marketing/compensation, and working
capital—be mapped.

## Safe conclusions and next boundaries

1. MLCF is the only lane with partial qualified financial truth, but remains
   blocked by 2 annual triplets, 3 annual OCF periods, 5 direct quarters, the
   unapproved share-count tie-out, and the PIOC/acquisition bridge.
2. MARI is a valid observed E&P seed but has 0/5 annuals, 0/8 quarters, no
   filing-bound share count, and no numeric event-economics operands.
3. The sales-led lane remains a no-go for case selection under retained evidence.
4. A metadata lead, candidate, audit-only value, receipt, or generic strategy
   statement is not progress through a publication gate.
5. Any new restage, source intake, candidate approval, OCR/provider change, or
   case selection is outside this read-only map and needs its existing owner
   checkpoint. Until then, missing load-bearing fields remain `unknown` and all
   formal outputs fail closed.
