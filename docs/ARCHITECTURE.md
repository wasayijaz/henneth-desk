# Henneth — Desk architecture

This is the architecture of the Pakistan Stock Exchange research desk as it exists today. It is
written for an agent joining with no previous context. Governance is in [`CLAUDE.md`](../CLAUDE.md),
operations are in [`OPERATIONS.md`](OPERATIONS.md), and sharp edges are in [`GOTCHAS.md`](GOTCHAS.md).

## 1. System overview

Henneth researches, scores and monitors PSX signals. It never places orders; execution is manual.

| Surface | URL | Source | Deployment |
|---|---|---|---|
| Marketing site | https://henneth.app | `site/` (Astro, static) | Vercel project rooted at `site/` |
| Research terminal | https://desk.henneth.app | `dashboard/` + committed `state/` | Vercel project rooted at the repo |
| Henneth CI | https://ci.henneth.app | external repository | `github.com/wasayijaz/henneth-ci` |

CI split: on 2026-09-11 the CI product moved to `github.com/wasayijaz/henneth-ci`. Its app folder,
release workflows, CI-owned state and CI-specific checks are no longer present in this repository.

The desk has four layers:

1. Deterministic Python in `scripts/` fetches, measures, scores, backtests and writes JSON to `state/`.
2. Local judgement agents in `.claude/agents/` and `prompts/` read compact state and write analysis back.
3. The static terminal in `dashboard/` reads `state/*.json` and writes nothing to that seam.
4. `publish.py` stages the approved desk state/public extract, then the desk and marketing Vercel
   projects deploy from Git.

```text
PSX DPS / Yahoo / TradingView
             |
             v
scripts/ --writes--> state/*.json <--writes-- local agents
             |                         |
             +--> dashboard/ ----------+
             +--> site/src/data/public/
                         |
                  publish.py -> Git -> Vercel
```

## 2. Major modules and ownership

| Concern | Authoritative module | Primary consumers |
|---|---|---|
| Prices, calendars, dividends and history | `scripts/psx_data.py` plus fetchers | every later script and the terminal |
| Universe and market mapping | `update_universe.py`, `config/markets.json`, `psx_data.py` | per-ticker scripts |
| Research eligibility | `liquidity.py` -> `state/liquidity.json` and `psx_data.research_symbols()` | fundamentals, backtests, signals |
| Indicators | `indicators.py` | `quant.py`, `strategy_engine.py`, backtests |
| Strategy rules | `strategies/*.json` | `strategy_engine.py`, `backtest.py`, `build_signals.py` |
| Rule 4 sizing | `CLAUDE.md`, `build_signals.py`, dashboard/site calculators | research UI and practice tools |
| Health gate | `data_health.py` -> `state/health.json` | signal generation and publish gate |
| Desk publish gate | `preflight.py` | `publish.py`, cloud workflow |
| Account/data gate | `middleware.js` | every `/state/*` request |
| Desk Ask endpoint | `api/ask.js` | dashboard Ask surface |
| Company profiles | `fetch_company_profiles.py` -> `state/company_profiles.json` | Desk Room, explainer and ticker overview |
| Astrology company charts | `astro_charts.py` -> `state/company_charts.json` | astrology dashboard surfaces |
| Desk Room scaffolding | `room_*.py` | Room agents and terminal Room views |
| Public marketing extract | `build_public_slice.py`, `build_astro_lite.py` | Astro pages under `site/` |

`state/` is the seam between producers and consumers. Python writes it through `psx_data.save_json`;
the dashboard and marketing build read it. Consumers do not reach around the seam to call providers.

Security identity comes from DPS company/ETF links checked against `data-order`; display badges
are stored separately as `source_badges`. History storage accepts valid short series but research
eligibility remains owned by its existing consumers. Every universe ticker is attempted per sweep;
partial/invalid responses retain last-good history and produce explicit failures.

Price session date and collection time are different fields. `snapshot.py` and `fetch_indices.py`
use the exchange's timestamped KSE100 tick to identify the session; intraday files use their own
last tick. Weekend collections do not create weekend trading bars. The UI labels prices by source
time, not the time a report was rebuilt. Post-close integrity checks the latest completed session
on weekends/holidays, keeping them from bypassing a failed Friday close.

## 3. Data and execution flow

`run_desk_cloud.py` is the ordered Desk cloud list. `run_cloud.py` is the desk-only development entry
point with the same product boundary. Both keep `fetch_company_profiles.py`, `build_calendar.py`, the
astro pipeline, market data, Desk Room scaffolding, the public extract and the desk dashboard.

The normal cloud flow is:

1. Refresh universe, history, liquidity, profiles, dividends, fundamentals and market context.
2. Build quant, predictability, backtests, live snapshot, fundamental scores and fair value.
3. Build signals, checkpoint state, Desk Room state, astro/public extracts and dashboard state.
4. Run the desk preflight gate and publish only when the gate is green.

Network or provider failures retain last-good data where the producer supports it, write degraded
health and exit 0. The pipeline never fabricates a number to keep going.

## 4. Authentication and publication

The root middleware matches `/state/:path*`. `natal_ephem.bin`, `natal_ephem.json` and
`public_probe.json` remain public; all other desk state requires a valid Supabase ES256 bearer token.
The shell remains public so a signed-out visitor can see the sign-in UI. The UI gate and data gate are
independent.

The CI-private state deny-list covers all seven CI-owned root files plus `state/company_intel/**`
in the Desk publisher, middleware and build, with its own preflight check. This is a Desk security boundary even after the repository split:
an old checkout or accidental file recreation must never expose CI research to Desk accounts.

`publish.py` runs `preflight.py --desk`, stages `state/` and the generated marketing extract, and
ships hand-authored code only when the caller pre-staged it with `--code`. It never uses a blanket
stage for code. The push/rebase lock is shared across same-user, same-host worktrees and independent
clones by canonical origin identity. Other hosts retain Git fast-forward/rebase protection.

`finalize_routine.py` verifies the research commit on the remote before writing a routine receipt,
then publishes and verifies the runlog/PM acknowledgement through the normal publisher.
It holds the shared per-origin `finalization` lane from baseline reads through remote receipt
verification. Its publisher independently takes the `publish` lane; waiting clones fail closed
on a stale baseline. Both lanes reuse `PublishLock`, with no publication-lock bypass.
`check_research_publication.py` is the hard preflight boundary for prohibited signal execution
fields and named-ticker Room chair fields. This enforces the existing internal publication policy;
it does not claim to classify every possible prose recommendation.

## 5. Integrations and storage

| Provider | Desk use | Boundary | Failure mode |
|---|---|---|---|
| PSX DPS | live watch, EOD, sectors and off-market data | `psx_data.py` | degrade, keep prior, exit 0 |
| Yahoo Finance | deep history, dividends and global context | fetchers + `psx_data.yahoo_symbol` | same |
| TradingView | delayed EOD cross-check | `tv_crosscheck.py` | advisory |
| Supabase | auth and per-user rows | client SDK/REST + RLS | signed-out or explicit fallback |
| Groq | desk Ask | `api/ask.js` | 502/429, no fabricated answer |
| Vercel | terminal/marketing hosting | `vercel.json`, `middleware.js`, `api/ask.js` | last-good deploy remains if blocked |

Git is the research database. Committed `state/` makes the terminal self-contained. `config/desk.json`
and `.env` are private and never enter a served directory. The marketing site receives only the
allow-listed output under `site/src/data/public/`.

## 6. Invariants

1. Producers write state; renderers do not fetch providers.
2. A failed preflight never publishes a structurally broken cycle.
3. A provider failure never crashes the cycle or invents a value.
4. All published prices, dates and dividends come from `state/`.
5. Strategy files that have produced a published backtest are immutable.
6. Desk data remains account-gated except for the three explicit public files.

## 7. Official index daily-change seam

`fetch_indices.py` owns `indices.json.daily_change`: each index records the board's current
level, point change, percent change, derived previous close, exchange source timestamp and
session date. The numeric `live` map remains available to existing level consumers. Historical
captures are not silently rewritten to manufacture official daily returns.

Named board headers, finite values, arithmetic and source/session coherence are checked at
intake. An older session or older same-session source clock preserves every stored byte.
Preflight imports the producer's validator; missing metadata permits an explicit unavailable
daily move, but malformed metadata blocks publication. Today and both Board rendering paths
use the official metadata, never a historical-snapshot subtraction as a daily-change fallback.
Historical capture/scoring quality remains a separate audit in TECH-DEBT.md.
