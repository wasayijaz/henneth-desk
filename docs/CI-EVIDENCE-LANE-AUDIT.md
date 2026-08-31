# CI evidence-lane audit (retained sources only)

**Audit date:** 2026-08-31 (PKT)
**Scope:** the retained official archive in `state/research_index.json`,
`state/company_documents.json`, and `state/company_event_ledger.json`. This is a
documentation-only audit; it does not fetch, parse, restage, or promote any
document, and it does not alter a gate or readiness state.

## E&P: MARI remains the strongest observed-only seed

`MARI` is the only E&P name in this comparison with a date- and page-bound
retained filing that identifies both the target and the operating role:

| Field | Retained value |
|---|---|
| Event | `evt_eddfcc381018cb0dff43` (`acquisition`) |
| Document | `psx:260446`, PSX DPS **Material Information** |
| Official URL | <https://dps.psx.com.pk/download/document/260446.pdf> |
| Content hash | `c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42` |
| Evidence page | 1 |
| Publication/availability | `2025-09-30T10:46:00+05:00` (PSX publication; retained in the index) |
| Reported text | “Acquisition of Working Interest in Peshawar Block (as an Operator) from Hycarbex-American Energy …” |

The filing reports a MARI acquisition and operator designation. It does **not**
report a working-interest percentage, consideration, approval/effective status,
partner split, production response, capex, or ramp. Those are genuinely absent
from the retained evidence, not parser fields that can be inferred. The event is
single-origin PSX evidence; no independent second source is retained.

The other retained MARI event, `evt_ddf99590afb6dacddbde` / `psx:265594`
(`cdc3f69157f5e5803238ba347ecb4e96f7297479df87d345739896913de8aae4`, page 3,
published `2025-11-13T10:10:00+05:00`), only states that offshore-block
acquisition is part of long-term strategy. It is not a substitute for the
operator-bound Peshawar filing.

MARI is not financially model-ready. `state/company_intel/financial_coverage.json`
marks it `queued_for_qualification` (nine indexed official financial documents,
most without retained hashes), and the readiness/watchlist products retain the
`insufficient_three_year_consolidated_v2_history` limitation. Thus this is an
**observed event seed only**, not a forecast, valuation, or quantified impact
case; 5Y/8Q history and qualified cash-flow/share-count tie-outs remain absent.

### Executed MARI filing pilot — zero financial-truth delta

The owner-approved, exact-ID official-PSX tranche was tested under the existing
transport and parser caps. `psx:264550` (FY26 Q1, 59 pages), `psx:271327`
(FY26 Q2, 66 pages), and `psx:275583` (FY26 Q3, 64 pages) are now bound to
their transport hashes and current parser receipts. The first is
`processed_unsupported`; the latter two have successful transport/parser
receipts. Their candidate statement geometry did not establish the required
consolidated, direct three-month full-statement schedule, so the authoritative
financial-truth counters remain annual Revenue/PAT/EPS **0/5**, annual OCF
**0/5**, direct reported-quarter sets **0/8**, and official share-count tie-out
**missing**. No *financial* fact was promoted merely because a receipt
succeeded. The Q2 filing separately supplies source-bound event mechanics:
65% Peshawar Block working interest with operatorship; that strengthens the
Observed E&P case only and does not corroborate, model, or value it.

The FY26 annual `psx:280901` is an official exact-ID lead but was rejected at
the existing 12 MiB transport cap before bytes could be hash-bound. It was not
split, retried as a different source, or used to infer FY25/26 values. A future
annual path must use an independently approved compliant transport decision or
an exact approved smaller official counterpart; neither exists in this wave.

## Industrial / cement: MLCF FY26 annual is image-only

The selected industrial case's exact official FY26 annual `psx:280589`
(`c9c7771eaa6a7fc75f6468318218ec85dd7d947637294e6dab9b19c3067ef696`;
10 pages; published 2026-07-31) passed its source-identity and byte checks.
Its text layer is below the parser's minimum threshold, so the diagnostic
returned `unsupported_image_only`. It adds **zero** annual Revenue/PAT/EPS,
annual OCF, share-count, or qualified-quarter coverage. OCR, a parser-cap
change, and a substitute provider were not introduced.

### Why OGDC and PPL do not replace MARI

The research index contains compelling *headline metadata* for OGDC and PPL,
but none of these documents has a corresponding hash- and page-bound object in
`state/company_documents.json`:

- OGDC: `psx:278795` (Qadirpur D/PL farm-in completion,
  `2026-06-19T08:01:00+05:00`), `psx:279127` (Bobi Deep-1 production,
  `2026-06-29T10:07:00+05:00`), and `psx:278969` (Sahito-1 gas production,
  `2026-06-23T08:07:00+05:00`). Canonical DPS URLs and official IDs are retained;
  `content_sha256`, page evidence, and extracted text are not.
- PPL: `psx:280578` (Rahi X-1 discovery in **PPL Operated** Shah Bandar,
  `2026-07-30T15:12:00+05:00`) and `psx:281187` (Dolphin X-1 discovery,
  `2026-08-17T10:22:00+05:00`) are similarly metadata-only. The earlier
  `psx:280562` Rahi item is explicitly marked **REVOKED** and is excluded.

These records are useful intake leads, not Observed evidence. They cannot
establish source identity, page geometry, operator/WI details, or technical
operands until the exact PDFs are owner-approved, hash-bound, and extracted.
Both OGDC and PPL also remain `queued_for_qualification` with insufficient
three-year consolidated v2 history.

## Sales-led lane: no eligible retained candidate

No retained official document for the 20-company pilot reports a dated
sales-led expansion (sales hiring, new geography/channel/branch, or
product-sales infrastructure) with an effective/rollout date. The nearest
records are not eligible:

- **BOP:** `evt_a51de635bed77b8329cc`, `psx:272102`, PSX DPS annual report,
  <https://dps.psx.com.pk/download/document/272102.pdf>, hash
  `b2ae42c6a0bc8032863d3df5a86b23b7d22c00f0581db6ec6bbed2ec64575617`, page 25,
  published `2026-03-05T12:29:00+05:00`. The retained passage is generic
  digital/customer-acquisition strategy; it gives no dated launch, geography,
  channel, branch, staffing, or operating milestone.
- **PSO:** `evt_2f3bfdf4a586999e66b6` (`issuer:61d85f4626413576b676aed8`,
  *Stations Accepting Corporate Cards*,
  <https://psopk.com/source/fuelcards/list_of_enabled_outlets.pdf>, hash
  `2bd076fae2202d45aac45bdd142e28f004a4254fff96cf02bac82caa0d892662`, page 4)
  and `evt_30027cd832df431a70a9` (`issuer:ca78a4beec7f30b38e790a5e`,
  *PSO Cards SMS & Email Alerts Service*,
  <https://psopk.com/source/fuelcards/corporate-cards/02.pdf>, hash
  `0b66c3bbd717ed36b51c91918c5e85dbc86c26b67c438c2c1796d4f97ce18604`, page 1).
  Both have null publication/event dates and are same-issuer product material;
  neither records a rollout or expansion date.
- **GAL:** the retained issuer home source (`issuer` registry hash
  `9fed93ec98418218bc7449c51856fa3e79c8c9edccb0443189778495bc0200e7`) has no
  corresponding sales event in `company_event_ledger.json`.

This is a **NO-GO** for a sales-led observed seed. Strategy language, a static
outlet list, or an undated service description cannot be converted into an
effective expansion event by re-parsing.

## Minimum legal intake if the owner wants to qualify one lane

The smallest compliant tranche is one owner-reviewed, exact official PSX/issuer
document (or a tightly related two-document pair) that is already in the
retained index and states:

1. the named company and operating target (block, well, branch, channel, or
   product infrastructure);
2. the action (acquisition, discovery, commissioning, launch, opening, or
   deployment) and an explicit event/effective date; and
3. the attributable operand needed for the lane (operator/WI/partner for E&P;
   capacity/commissioning/dispatch for industrial; geography/channel/staffing
   for sales).

The document must then pass the existing intake controls: canonical URL and
exact `psx:<digits>` ID, owner-reviewed metadata, transport SHA-256 binding,
page-level extractable text/geometry, and the existing 12 MiB/120-page limits.
`document_intelligence.py` may append evidence/events only after that scoped
review; OCR, cap relaxation, inferred dates, and unapproved provider changes
are not permitted. The current review manifest/allowlist is limited to its
existing financial tranche, so adding an OGDC/PPL event or a sales document
would require a new owner approval. Until that approval and extraction occur,
the E&P MARI event remains the least-bad observed-only seed and the sales lane
remains NO-GO.
