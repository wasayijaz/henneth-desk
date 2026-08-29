# CI MLCF/PIOC Observed Case Seed

Status: Observed, reported-fact case seed only.

This memo records the smallest source-grounded observed seed for the Maple Leaf
Cement Factory Limited (MLCF) / Pioneer Cement Limited (PIOC) acquisition-control
case. It is not a forecast, valuation, recommendation, probability assessment,
or formal model input. It preserves only retained official-source facts and the
missing evidence gates that must stay closed before any model, valuation, or
market-expectations output can activate.

## Evidence Conclusion

The retained evidence supports one defensible dated acquisition/control event:
MLCF reported a public offer to acquire PIOC shares and control of Pioneer
Cement Limited through PSX DPS document `psx:267429`, published on
2025-12-18 at 12:52 PKT. The retained case remains Observed because the event
is supported by a single official issuer/PSX source chain, not independent
originator corroboration or a complete financial bridge.

A later MLCF quarterly filing, `psx:275425`, published on 2026-04-28 at
10:25 PKT, supports operating follow-through only: it says Pioneer Cement
Limited dispatches were included in MLCF local-market totals due to acquisition
during February 2026. Treat that as month-only timing and operating inclusion,
not as standalone PIOC financial impact.

## Case Seed

| Field | Retained value |
|---|---|
| Case id | `case_mlcf_pioc_control_observed_v1` |
| Acquirer symbol | `MLCF` |
| Target symbol | `PIOC` |
| Case family | `industrial_cement` |
| Case type | `acquisition_control` |
| Status | `Observed` |
| Epistemic type | `reported_fact` |
| Case as-of | `2026-08-22T21:48:11+05:00` |
| Source state | `state/company_intel/intelligence_cases.json` |

## Dated Event

| Field | Retained value |
|---|---|
| Source event id | `evt_cb44dc32c91b0c5712a5` |
| Cluster id | `cluster_82b31911757fd2f836e1eaea` |
| Assertion key | `acquisition:pioneer cement limited:public_offer:2025-12-18` |
| Conflict key | `acquisition:pioneer cement limited:2025-12-18` |
| Proposition | Acquisition, public-offer stage, target `PIONEER CEMENT LIMITED` |
| Originator | `issuer:MLCF` |
| Distributor | `psx` |
| Event date / detected at | `2025-12-18T12:52:00+05:00` |
| Assessment | `single_source` |
| Quality flags | none retained |
| Source state | `state/company_intel/signal_clusters.json` |

Known transaction mechanics retained from the source are limited to control and
share-count mechanics: public offer for up to `26,623,096` PIOC shares,
`11.72%` through the public offer, and `58.03%` through Share Purchase
Agreement(s). Offer price, consideration, synergies, fair value, and any
forward financial claim are deliberately excluded from this memo.

## Official Source Citations

| Role | Document id | Citation | Availability | Hash |
|---|---|---|---|---|
| Control event | `psx:267429` | PSX DPS, `MLCF-Material Information to PSX`, page 3, `https://dps.psx.com.pk/download/document/267429.pdf` | Published `2025-12-18T12:52:00+05:00`; retrieved `2026-08-18T01:54:00+05:00` | `98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54` |
| Operating follow-through | `psx:275425` | PSX DPS, `Transmission of Quarterly Financial Statements for the Period Ended 31.03.2026`, page 4, `https://dps.psx.com.pk/download/document/275425.pdf` | Published `2026-04-28T10:25:00+05:00`; retrieved `2026-08-22T21:48:11+05:00` | `744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f` |

Retained source snippets:

- `psx:267429`, page 3: public announcement of public offer to acquire up to
  `26,623,096` shares and control of Pioneer Cement Limited by MLCF.
- `psx:275425`, page 4: inclusion of Pioneer Cement Limited dispatches in
  local-market totals due to acquisition during February 2026.

## Fact vs Unknown

Facts retained:

- MLCF is the observed acquirer symbol in the current CI pilot.
- PIOC is the named target company, but it is not inside the current CI pilot.
- The control/acquisition event is dated by PSX publication to
  2025-12-18 at 12:52 PKT.
- The later operating-inclusion filing is dated by PSX publication to
  2026-04-28 at 10:25 PKT.
- The later filing supports only month-level acquisition timing for
  February 2026 and dispatch inclusion in MLCF local-market totals.

Unknown or not activated:

- No retained target-company PIOC financial truth row exists inside the current
  CI pilot.
- No source-qualified standalone PIOC revenue, margin, EPS, cash-flow, debt, or
  share-count contribution is attached to the observed case.
- No source-qualified MLCF/PIOC incremental financial bridge is attached to the
  observed case.
- No owner-reviewed formal forward assumptions are attached to this case.
- No independent-originator corroboration is attached to this case.
- No model, valuation, market-expectations output, probability, or conclusion is
  activated.

## Competing Hypotheses as Research Questions

These are no-output research questions. They do not produce a forecast,
valuation, recommendation, or probability.

- Consolidation mechanism: did the February 2026 acquisition change MLCF's
  reported local dispatch scale through PIOC operating inclusion, and can that
  be separated from ordinary cement demand, pricing, and mix changes?
- Control mechanism: did the public-offer plus Share Purchase Agreement chain
  transfer effective control in a way that changed MLCF's operating footprint,
  or is the retained evidence only sufficient for a legal/control observation?
- Financial bridge mechanism: can official subsequent filings isolate the
  target contribution, financing structure, debt/cash movement, and share-count
  effect without using inferred or model-generated inputs?
- Alternative reading: is the December 2025 document only an offer/control
  disclosure, with April 2026 dispatch inclusion still insufficient to quantify
  impact?

## Evidence Gates Before Promotion

The case must remain Observed until all relevant gates are source-qualified and
owner-reviewed through existing CI paths.

- Corroborated gate: requires independent-originator corroboration or another
  official source that preserves the same acquisition/control chain without
  contradiction.
- Modelled gate: requires source-qualified incremental financial bridge inputs
  for the transaction chain, including target contribution, acquirer
  consolidation bridge, debt/cash position, and official share-capital tie-out.
- Financial truth gate: MLCF currently has `3/5` annual income triplets,
  `0/8` qualified reported-quarter fact sets, `0/5` annual operating-cash-flow
  periods, and no official share-count capital-note tie-out in
  `state/company_intel/financial_truth_qualification.json`.
- Target-company gate: PIOC must enter the CI evidence boundary with retained
  official financial documents, a financial truth row, and model-input row
  before target-company contribution can be used.
- Formal-output gate: forecasts, valuations, reverse expectations, market gaps,
  and any investor-facing conclusion remain blocked until all required actuals,
  market operands, and owner-approved assumptions are present.

## Hard Boundaries

- Do not infer completion terms beyond retained official text.
- Do not infer PIOC financial contribution from MLCF consolidated movement.
- Do not use offer price or consideration as a valuation input from this memo.
- Do not promote month-only February 2026 timing into a specific completion
  date.
- Do not use this seed as an advice or trade signal.
