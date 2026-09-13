# Case C — Sales-Led Expansion Candidate Audit

**Decision:** Select Pakistan State Oil Company Limited (`PSO`) and its FY2025 retail-network and convenience-channel expansion as the Case C golden candidate.

**Selection state:** `selected_candidate_pending_evidence_ingestion`

**Do not mark the case Active or Published yet.** The official event evidence is strong enough to choose the company and define the model, but the decisive FY2025 source is not yet retained and hash-bound in this integration checkout. Selection and evidence activation are separate gates.

## 1. Scope and qualification standard

This is an architectural-candidacy ranking, not an equity recommendation or a ranking of company quality. A candidate ranks highly only when it satisfies all of the following:

1. It is in the exact 20-company pilot, unless an out-of-pilot exception is explicitly justified.
2. It has a real sales-organisation, geography, branch, channel, outlet, dealership, or product-sales-infrastructure expansion.
3. The event is dated and supported by an official PSX filing or a retained, hash-bound official issuer document.
4. The event can be translated into attributable operating drivers rather than inferred from aggregate sales growth or market-share outcomes.
5. The financial architecture can produce quarterly revenue, gross profit, SG&A, EBITDA, EPS, cash conversion, ROIC, and fair-value impact without using sector-inappropriate concepts.
6. Reported facts, deterministic derivations, analyst assumptions, and scenario outputs remain separate.

The exact pilot in `state/company_profiles.json` is:

`MLCF, OGDC, PPL, DGKC, PSO, UBL, FFC, LUCK, HUBC, PRL, BOP, NBP, MEBL, ATRL, HBL, MARI, ENGROH, GAL, NRL, CNERGY`.

`SYS` and `TRG` are not in this pilot or in the retained company-profile universe in this checkout. `PTC` and `FCCL` have profile rows but are outside the exact pilot. They therefore cannot be promoted to Case C without an explicit universe change.

## 2. Exact candidate ranking

| Rank | Company | Case C fit | Evidence position | Qualification decision |
|---:|---|---|---|---|
| 1 | **PSO** | Direct fit: nationwide fuel-retail outlets, convenience stores, named concept stores, digital journey channel, LPG e-commerce and last-mile delivery | Strong dated official FY2025 issuer disclosure and corresponding PSX annual-report filing; decisive document not yet retained in this checkout | **Winner — select pending ingestion** |
| 2 | NBP | Direct branch-network expansion | Strongest already hash-bound branch evidence: Islamic branches and windows grew materially in 2025 | Reject for this golden slot: banking requires NII, fee income, credit cost, RWA/capital and ROE/P/B outputs, not gross margin, EBITDA, conventional working capital and ROIC |
| 3 | BOP | Branch and digital-customer-acquisition pathway | Hash-bound issuer briefing gives current footprint and digital strategy, but not a clean dated opening cohort or attributable expansion delta | Reject: strategy/footprint is not a qualified expansion event |
| 4 | GAL | Automotive distribution/dealership economics would fit the requested output chain | Correct company type, but retained documents contain no qualifying dated sales-channel or dealership event | Reject: evidence absent |
| 5 | MEBL | Branch-led customer acquisition is conceptually valid | No retained, dated, canonical branch-expansion event that clears the case gate | Reject: evidence insufficient and bank model mismatch |
| 6 | UBL | Branch/digital distribution is conceptually valid | Retained evidence does not isolate a dated expansion cohort with incremental economics | Reject |
| 7 | HBL | Domestic/overseas branch and digital channel are conceptually valid | No qualified expansion event in retained state | Reject |
| 8 | FFC | Fertiliser marketing/distribution could support a dealer-channel case | No retained dated dealer, depot, geography, or sales-infrastructure expansion event | Reject |
| 9 | CNERGY | Has a petroleum-marketing segment and therefore surface-level distribution fit | Audited records are throughput, supply share and sales-mix outcomes rather than an attributable organisation/channel/network expansion | **Previously rejected; retain rejection** |
| 10 | ENGROH | Portfolio companies may contain consumer/distribution exposure | Listed entity is a holding company; no direct retained operating sales-expansion event attributable to the parent | Reject |
| 11 | PRL | Product sales exist | Evidence and economics are refinery throughput/product-mix led, not sales-network led | Reject |
| 12 | ATRL | Product sales exist | Refining economics dominate; no dated channel/network expansion | Reject |
| 13 | NRL | Product sales exist | Refining, plant and product-mix economics; no dated sales-infrastructure event | Reject |
| 14 | HUBC | New customer/product channels are theoretically possible | Retained events are power/infrastructure led; no qualifying sales expansion | Reject |
| 15 | LUCK | Marketing exists, but the operating model is capacity/dispatch led | No qualifying sales-team/channel event; also overlaps the industrial case family | Reject |
| 16 | DGKC | Marketing exists, but the operating model is capacity/dispatch led | No qualifying sales-led expansion; industrial evidence belongs in Case B archetype | Reject |
| 17 | MLCF | Sales and distribution expenses exist | Already the industrial/cement golden case; using it again would defeat cross-archetype proof | Ineligible for Case C |
| 18 | MARI | Has technology ventures as well as E&P | Already the E&P golden case; retained expansion evidence is not a sales-organisation cohort | Ineligible for Case C |
| 19 | OGDC | Hydrocarbon sales | Exploration/production, not sales-led distribution | Reject |
| 20 | PPL | Hydrocarbon sales | Exploration/production, not sales-led distribution | Reject |

### Out-of-pilot names raised during triage

| Company | Status | Treatment |
|---|---|---|
| SYS | Not in the exact pilot/profile state | Do not widen the universe. It would need a new official-source packet, profile registration, financial-history coverage and a separately evidenced geography/salesforce event. |
| TRG | Not in the exact pilot/profile state | Do not widen the universe. Parent/associate attribution would add another evidential and consolidation boundary. |
| PTC | Profile exists but is outside the active pilot | Current retained evidence is acquisition/licence/spectrum oriented rather than a quantified sales-expansion cohort. |
| FCCL | Profile exists but is outside the active pilot | Cement/industrial economics do not improve Case C diversity. |

## 3. Winning event and official evidence

### Canonical event

`PSO_FY2025_RETAIL_NETWORK_AND_CHANNEL_EXPANSION`

Proposed classification:

```yaml
event_type: distribution_network_expansion
event_subtype: fuel_retail_and_convenience_channel
company: PSO
event_period_end: 2025-06-30
status: selected_candidate_pending_evidence_ingestion
model_adapter: omc_distribution_network_expansion_v1
```

### Primary sources

1. **Official PSO FY2025 results release, dated 19 August 2025**  
   `https://psopk.com/index.php/en/media/press-releases/pso-shows-resilience-in-a-challenging-market-posts-profit-after-tax-of-pkr-209-billion-in-fy25`

   Reported statements include:
   - 107 new retail outlets and 3,649 total outlets.
   - More than 310 convenience stores.
   - VIBE concept stores in Karachi, Lahore and Islamabad.
   - Asaan Safar phase I through Fuelink and upgraded station amenities.
   - LPG Blue e-commerce/pre-ordering and last-mile delivery in Gilgit-Baltistan.
   - 498 dispensing controllers installed across 137 outlets.

2. **Official PSO Summary Annual Report 2025**  
   `https://psopk.com/files/financial-reports/annual/2025/Summary-of-Annual-Report-2025.pdf`

   The Statement of Corporate Intent records the same 107-outlet expansion, 3,649 ending network, VIBE locations, Asaan Safar outlets, LPG/lubricant customer channels and dispensing-controller deployment.

3. **Official PSX annual-report filing**  
   Document ID: `psx:260771`  
   Published: `2025-10-02T08:48:00+05:00`  
   URL: `https://dps.psx.com.pk/download/document/260771.pdf`

   This exact filing is present in `state/research_index.json`. Its local download failed because it exceeded the legacy 12 MiB PSX-document limit, so it does not currently supply hash-bound page evidence.

4. **Official PSO FY2024 comparator**  
   Release: `https://psopk.com/index.php/en/media/press-releases/pso-continues-to-dominate-the-energy-market-reports-profit-pkr-159-billion-in-fy24`  
   Annual report: `https://psopk.com/files/financial-reports/annual/2024/PSO-Annual-Report-2024.pdf`

   FY2024 reported 101 new outlets and a 3,580-outlet ending network. This comparator creates a necessary reconciliation check for the FY2025 cohort.

### Evidence state in this integration checkout

- `state/research_index.json` knows `psx:260771` and its official publication timestamp.
- `state/company_documents.json` does not contain a ready/hash-bound `psx:260771` record.
- `state/company_intel/source_registry.json` in this checkout contains PSO corporate-card documents but does not yet contain the FY2025 annual-report links present in the newer source-registry state.
- `state/company_intel/operating_events.json` correctly contains no canonical PSO operating event.
- The retained corporate-card station list is hash-bound but undated; it is a current footprint list, not expansion evidence.

Accordingly, the case cannot become Active until the official FY2025 report or dated issuer release is retained with content hash, page/excerpt evidence and a conservative `available_on` date.

## 4. Epistemic boundaries and required reconciliation

### Gross openings are not net additions

Reported facts:

- FY2024 ending network: 3,580 outlets.
- FY2025 gross new outlets: 107.
- FY2025 ending network: 3,649 outlets.

Deterministic derivation:

- Net FY2025 network change: `3,649 - 3,580 = 69`.
- Unreconciled difference: `107 - 69 = 38` outlets.

The difference may represent closures, replacements, reclassification or a changed counting basis. That explanation is an inference until PSO supplies a reconciliation. The model must therefore retain separate fields for `gross_openings`, `closures_or_reclassifications`, and `net_active_change`; it must not treat all 107 openings as permanent incremental outlets.

### Do not double-count channel layers

Fuel outlets, Shop Stop/convenience stores, VIBE stores, Asaan Safar locations and digitally integrated outlets can overlap. They are nested attributes/cohorts, not automatically additive sites. A location may be one fuel outlet, one convenience store and one VIBE location simultaneously.

### Do not back-solve causality from reported outcomes

FY2025 market share, lubricant volumes, LPG growth, consolidated PAT or total EBITDA cannot be attributed to the outlet expansion merely because they appear in the same release. The Case C model must estimate the counterfactual incremental contribution from explicitly approved unit-economics assumptions.

### Availability and no-lookahead

- `event_period_end` records the economic period, not information availability.
- `available_on` must be the earliest retained, dated official source available to the model.
- If only an issuer PDF with no reliable publication timestamp is retained, use its conservative first-seen date.
- Historical outcomes after the cutoff may be labels for evaluation, never model inputs.

## 5. Event model architecture

Do not build one universal “sales-led” formula that forces every company to use sales representatives and revenue per rep. Case C proves a **distribution-network expansion** archetype. A later software/services case can use a separate `salesforce_expansion_v1` adapter.

Architecture:

```text
Event-to-Value common contract
    -> distribution_network_expansion_v1
        -> omc_distribution_network_expansion_v1
```

The common contract standardises provenance, quarterly outputs, scenarios and valuation. The sector adapter owns economically meaningful drivers.

### Common case object

```yaml
case_id: PSO_FY2025_RETAIL_NETWORK_AND_CHANNEL_EXPANSION
company_id: PSO
event_id: <stable canonical event id>
event_type: distribution_network_expansion
event_subtype: fuel_retail_and_convenience_channel
event_period_end: 2025-06-30
available_on: <retained source availability>
source_cutoff: <scenario cutoff>
status: selected_candidate_pending_evidence_ingestion
reported_facts: []
derived_facts: []
assumptions: []
quarterly_schedule: []
scenario_outputs: []
valuation_outputs: null
provenance: []
quality_flags: []
policy:
  research_only: true
  no_advice: true
```

Every reported fact requires `document_id`, `source_url`, `content_sha256`, one-based `page`, bounded `text`, `available_on`, unit and period. Every assumption requires an owner/approval state, value, unit, scenario, effective period, rationale and source label. Derived facts and outputs name their formula IDs.

## 6. Exact eight-quarter driver schedule

The model horizon is eight consecutive fiscal quarters from the chosen cutoff. Store one row per quarter and scenario. Source-reported history remains outside the assumption fields.

### Quarter-row schema

```yaml
quarter_index: 1                       # integer 1..8
period_start: YYYY-MM-DD
period_end: YYYY-MM-DD
scenario: Bear|Base|Bull
source_cutoff: YYYY-MM-DD

network:
  opening_active_outlets: number
  gross_outlets_opened: number
  closures_or_reclassifications: number
  closing_active_outlets: number
  cohort_active_equivalent_outlets: number
  outlet_retention_rate: decimal
  ramp_factor_by_cohort: decimal

fuel_channel:
  mature_litres_per_outlet_quarter: number
  incremental_litres: number
  realized_price_per_litre: PKR
  marketing_margin_per_litre: PKR
  incremental_fuel_revenue: PKR
  incremental_fuel_gross_contribution: PKR

nonfuel_channel:
  convenience_store_count: number
  vibe_store_count: number
  mature_sales_per_store_quarter: PKR
  store_ramp_factor: decimal
  company_economic_share: decimal
  gross_margin_rate: decimal
  incremental_nonfuel_revenue: PKR
  incremental_nonfuel_gross_profit: PKR

digital_and_geography:
  asaan_safar_active_sites: number|null
  lpg_blue_active_geographies: number|null
  digital_orders_or_customers: number|null
  revenue_per_order_or_customer: PKR|null
  geographic_mix: object
  channel_mix: object

operating_costs:
  incremental_sales_hires: number
  incremental_support_hires: number
  compensation_per_fte_quarter: PKR
  outlet_support_cost: PKR
  marketing_spend: PKR
  central_technology_cost: PKR
  dealer_commission_or_revenue_share: PKR
  other_incremental_opex: PKR
  incremental_sga: PKR

capital_and_working_capital:
  owned_capex: PKR
  dealer_funded_capex: PKR
  capitalized_central_infrastructure: PKR
  depreciation: PKR
  receivable_days: number
  inventory_days: number
  payable_days: number
  incremental_receivables: PKR
  incremental_inventory: PKR
  incremental_payables: PKR
  incremental_nwc: PKR
  change_in_incremental_nwc: PKR

tax_and_equity:
  tax_rate: decimal
  shares_outstanding: number
  discount_rate_quarterly: decimal

outputs:
  incremental_revenue: PKR
  incremental_gross_profit: PKR
  incremental_ebitda: PKR
  incremental_ebit: PKR
  incremental_nopat: PKR
  incremental_pat: PKR
  incremental_eps: PKR_per_share
  incremental_fcff: PKR
  cash_conversion_ratio: decimal|null
  incremental_invested_capital: PKR
  roic_annualized: decimal|null
  discounted_fcff: PKR
```

### Required assumption records

| Assumption | PSO interpretation | Required treatment |
|---|---|---|
| Sales hires | Territory/channel managers attributable to expansion | Explicit number and start quarter; zero is permitted only if approved |
| Compensation | Fully loaded quarterly cost per incremental sales/support FTE | Scenario input |
| Support cost | Outlet supervision, training, maintenance, technology and central support | Separate fixed and per-site components |
| Marketing spend | Launch and ongoing local/channel marketing | Separate launch pulse from recurring spend |
| Ramp period | Quarters from opening to mature throughput/store sales | Explicit cohort ramp vector, e.g. eight values |
| Revenue per mature rep | Not economically primary for PSO | Mark `not_applicable`; replace with mature volume/contribution per outlet |
| Gross margin | Fuel uses regulated/realised marketing contribution per litre; stores use gross-margin rate | Never apply one blended margin without mix support |
| Customer acquisition cost | Use for digitally acquired LPG/app customers when customer counts exist | Otherwise unavailable, not fabricated |
| Working capital | Incremental receivables + inventory - payables attributable to the expansion | Exclude legacy circular debt unless causally attributable |
| Retention | Outlet survival/continued operation and, where supported, digital-customer retention | Scenario input |
| Geography/channel mix | Fuel, convenience, VIBE, digital LPG and region weights | Weights must sum to one within each relevant dimension |
| Tax | Incremental effective cash tax rate | Approved scenario input |
| Capex ownership | Company-funded versus dealer-funded site investment | Required for cash flow and ROIC |
| Shares | Period-correct diluted shares outstanding | Source-gated market operand |
| Valuation | WACC/discount rate, terminal method and any multiple | Owner-approved; never generated by the case engine |

### Core deterministic formulas

For quarter `q` and opening cohort `c`:

```text
closing_active_outlets[q]
  = opening_active_outlets[q]
  + gross_outlets_opened[q]
  - closures_or_reclassifications[q]

active_equivalent_outlets[q]
  = sum_c(gross_openings[c] * retention[c,q] * ramp_factor[c,q])

incremental_litres[q]
  = active_equivalent_outlets[q] * mature_litres_per_outlet_quarter[q]

incremental_fuel_revenue[q]
  = incremental_litres[q] * realized_price_per_litre[q]

incremental_fuel_gross_contribution[q]
  = incremental_litres[q] * marketing_margin_per_litre[q]

incremental_nonfuel_revenue[q]
  = active_equivalent_stores[q]
  * mature_sales_per_store_quarter[q]
  * company_economic_share[q]

incremental_nonfuel_gross_profit[q]
  = incremental_nonfuel_revenue[q] * store_gross_margin_rate[q]

incremental_sga[q]
  = sales_compensation[q]
  + support_compensation[q]
  + outlet_support_cost[q]
  + marketing_spend[q]
  + central_technology_cost[q]
  + other_incremental_opex[q]

incremental_ebitda[q]
  = incremental_fuel_gross_contribution[q]
  + incremental_nonfuel_gross_profit[q]
  + incremental_digital_gross_profit[q]
  - incremental_sga[q]

incremental_ebit[q] = incremental_ebitda[q] - depreciation[q]
incremental_nopat[q] = incremental_ebit[q] * (1 - tax_rate[q])
incremental_pat[q] = incremental_nopat[q] - incremental_after_tax_interest[q]
incremental_eps[q] = incremental_pat[q] / shares_outstanding[q]

incremental_fcff[q]
  = incremental_nopat[q]
  + depreciation[q]
  - owned_capex[q]
  - change_in_incremental_nwc[q]

incremental_invested_capital[q]
  = cumulative_owned_capex_net_of_depreciation[q]
  + capitalized_central_infrastructure_net[q]
  + incremental_nwc[q]

roic_annualized[q]
  = annualized_incremental_nopat[q]
  / average_incremental_invested_capital[q]

cash_conversion_ratio[q]
  = cumulative_incremental_fcff[q] / cumulative_incremental_ebitda[q]

fair_value_impact
  = sum_q(discounted_incremental_fcff[q])
  + discounted_terminal_or_residual_value
```

Return both:

- `ebitda_break_even_quarter`: first quarter in which quarterly incremental EBITDA is non-negative after launch costs.
- `cash_payback_quarter`: first quarter in which cumulative incremental FCFF is non-negative.

They must not be conflated.

## 7. Clean implementation sequence

1. Refresh the PSO issuer financial-report page into this worktree's source registry.
2. Stage the exact FY2025 summary/full annual report through the bounded same-domain issuer-document path and record its SHA-256.
3. Retain page-level evidence for the 107 openings, 3,649 ending network, convenience-store count and named channel launches.
4. Add a canonical `distribution_network_expansion` event type. Do not misclassify the disclosure as acquisition, capacity expansion, generic product launch or earnings.
5. Add a strict extraction pattern requiring explicit expansion language plus a unit such as outlets, branches, stores, dealerships, geographies or channels.
6. Preserve `event_period_end`, `published_at`, `available_on` and `detected_at` as distinct dates.
7. Reconcile gross openings versus net network change, or emit `unreconciled_opening_closure_delta=38` as a visible quality flag.
8. Implement `distribution_network_expansion_v1`, then the PSO/OMC adapter specified above.
9. Backfill source-qualified PSO annual and quarterly financial history and approved shares/current-price/valuation operands.
10. Register Bear/Base/Bull eight-quarter schedules only after assumption approval.
11. Publish the case only when evidence, scenario, valuation, no-lookahead and provenance checks are green.

## 8. Final recommendation

PSO is the only current-pilot candidate combining a clearly disclosed distribution expansion with an economically compatible path to all required Case C outputs. NBP has stronger already-retained branch proof but is architecturally unsuitable for this particular golden-case output contract. GAL is economically suitable but evidentially empty. SYS/TRG would widen the universe and create more source and attribution work without improving on PSO's official evidence.

The correct decision is therefore:

```text
Case C company: PSO
Event: FY2025 retail-network and convenience/digital-channel expansion
Current state: selected_candidate_pending_evidence_ingestion
Activation blocker: retain and hash-bind the decisive official FY2025 disclosure,
                    reconcile gross openings versus net network movement,
                    and implement the OMC distribution-network adapter.
```
