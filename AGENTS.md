# Henneth — Agent Entry Point

Harness-neutral brief. Codex, Claude Code, and any other agent working in this repo start here.

Henneth is a personal trading-intelligence desk for the Pakistan Stock Exchange. It researches,
scores, and monitors signals. **It never places orders.** Execution is manual by the owner.

## Read in this order

| File | What it governs |
|---|---|
| [`docs/ORIENTATION.md`](docs/ORIENTATION.md) | **Start here.** Current Desk/marketing versus CI ownership, cloud data and Codex routines, retired Claude schedules, approval boundaries. |
| [`CLAUDE.md`](CLAUDE.md) | **Governance.** The hard rules — risk limits, position sizing, veto authority, data provenance. Binding on every agent and every cycle. |
| [`docs/GIT_MODEL.md`](docs/GIT_MODEL.md) | **Read before Git operations.** Assigned isolated checkout, dirty owner work, scoped staging, and the limits of the local publication lock. |
| [`docs/ROUTINES.md`](docs/ROUTINES.md) | **Automation map.** Nine Codex routine cards, cloud workflow, cost approval and the acceptance ledger; scheduling is not proof of successful release. |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | **Operations.** The hybrid cloud/app model, the one publish path, safety gates, how to run each flow without breaking the live site. |
| [`docs/GOTCHAS.md`](docs/GOTCHAS.md) | **Sharp edges.** Traps that already cost debugging time — the auth gate, the CSS at-rule trap, encoding, frozen breakpoints. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **The system as it is today.** Modules, data flows, ownership, seams. Read this before adding anything — it exists to stop you building a second implementation of something that already exists. |
| [`docs/TECH-DEBT.md`](docs/TECH-DEBT.md) | **Known debt, with evidence.** Each entry names its trigger. Check it before "fixing" something that is already logged, and add to it when you knowingly leave debt behind. |

`CLAUDE.md` is auto-loaded by Claude Code but **not** by other harnesses. If you are not Claude Code,
read it explicitly before doing anything that touches signals, sizing, or published output.

## Non-negotiables (full text in `CLAUDE.md`)

1. **Long only.** No shorts, no leverage, no derivatives. Daily timeframe only.
2. **All prices, dates and dividends come from the data layer** (`state/` JSON produced by
   `scripts/`). Never quote one from model memory. Missing data is answered "unknown", never guessed.
3. **No advice language.** Output is research — "the setup", "the desk's read" — never "you should
   buy". No performance promises.
4. **Risk limits:** max 4 concurrent positions · max 20% total exposure · no two positions in the
   same sector. One sizing formula only:
   `shares = floor(min(risk_budget / (entry − stop), (capital × 8%) / entry))`, where
   `risk_budget = capital × risk_per_trade_pct` (default 1%). `entry ≤ stop` or `shares = 0` is invalid.
5. **Data health gates everything.** `state/health.json` `status != "ok"` → no new signals this cycle.
6. **The Auditor has veto.** Any mismatch against its independent re-derivation kills the setup.
7. **Live strategy files are immutable.** Add a new versioned file; never edit one in place.
8. **No lookahead in backtests.** A signal at bar *t* may use only data available at *t*'s close.
9. **`config/desk.json` must never be served.** It holds the owner's real trading capital and the
   Telegram bot token.

## Layout

```
scripts/         deterministic Python — fetch, indicators, quant, predictability, backtests,
                 health, publish, preflight, Desk Room + astro + sector pipelines
.claude/agents/  judgment agents (strategist, risk-officer, auditor, monitor, reviewer,
                 news-sentinel, macro-agent, market-analyst, room-* debate cast, sector-*)
prompts/         reference prompts; current scheduled execution follows docs/routines/
strategies/      JSON rule templates; every setup must reference one
state/           all desk state, JSON only — the single source of truth
dashboard/       static visual layer; reads state/, writes nothing
site/ public/    marketing site; api/ask.js is the Groq-backed "ask the desk" endpoint
config/          desk.json — capital, risk params, alerts. Never served.
docs/            runbook and plans
logs/            one transcript per cycle run
```

## Engineering conventions

- **Canonical Python for published numbers is 3.12** — that is what
  `.github/workflows/desk-data.yml` installs. The owner's machine may be 3.14. Do not use a
  3.13+ language feature, and do not bump the workflow as a drive-by. Deps: `requests`,
  `pandas`, `numpy`, plus the two specialised pins in `requirements.txt` (`pymeeus`,
  `pymupdf`). Scripts must be idempotent and safe to re-run. A network failure writes a
  degraded health status and **exits 0** — never crash the cycle.
- No backward-compatibility layers. Remove obsolete paths rather than adding fallbacks or migrations.
- Simplest implementation that fully meets the current requirement. No speculative abstraction.
- Grow in layers: never trade a working product for unfinished complexity.
- Prefer existing dependencies over new ones or hand-rolled equivalents.

## Shared vocabulary

These seven words are used throughout this repo's docs with exact meanings. Use them the same way.

| Term | Meaning here |
|---|---|
| **Module** | Anything with an interface and an implementation. A Python script, a JS function, a state file, an agent definition, an HTTP endpoint. |
| **Interface** | Everything a caller must understand to use the module correctly — its behaviour, its invariants, the errors it can raise, its configuration, and the performance characteristics that matter. Not just the signature. |
| **Implementation** | The behaviour hidden behind the interface. Callers must not need to know it. |
| **Seam** | A location where behaviour can change without forcing calling code to change. `state/*.json` is the desk's biggest seam: Python writes, JS reads, neither knows the other. |
| **Depth** | The amount of useful behaviour available through a small interface. `psx_data.save_json(path, obj)` is deep — one call buys atomic write, NaN scrubbing, and UTF-8 correctness. |
| **Locality** | Related knowledge, bugs and changes concentrated in one place. When a rule lives in five files, a fix in one is a bug in four. |
| **Leverage** | Giving many callers a useful capability through a small interface. Centralising the Yahoo endpoint would give six fetchers retry and error handling for free. |

## Engineering guardrails

Binding on every agent working in this repo. `CLAUDE.md`'s desk rules govern *what the desk may say*;
these govern *how the code gets changed*.

**Before you change anything**

1. Understand the existing behaviour first. Read both sides of an interaction — the writer and the
   reader, the Python and the JS — before concluding what something does.
2. Search for an existing implementation before adding a new one. This repo has been built by many
   agent sessions; the most common failure mode is a second implementation of something that
   already works. `graft ask` and `docs/ARCHITECTURE.md` exist for exactly this.
3. Prefer small, coherent changes over sweeping ones. One concern per change.
4. Protect production behaviour. The live desk publishes itself on a cron; a broken change reaches
   the public site without a human in the loop. Assume no one will catch it for you.

**Structure**

5. Do not duplicate business logic. If a rule already exists in Python, do not re-derive it in JS,
   TypeScript, or an agent prompt. If it must exist in two places (the position-size calculator is
   a deliberate case), say so in a comment at both sites and name the other one.
6. Keep authoritative business rules centralised. Risk limits, sizing, health gating and publication
   scope each have exactly one owner. Change the owner, not a copy.
7. Keep modules deep where the evidence supports it: a small interface hiding real behaviour. Do not
   manufacture depth by wrapping one call in another.
8. Maintain clear seams. `state/` is the seam between the deterministic layer and every consumer.
   Do not let a consumer reach around it, and do not let a producer render.
9. Improve locality. When you touch a rule that is scattered, either consolidate it or log it in
   `docs/TECH-DEBT.md` with a concrete trigger. Do not scatter it further.
10. Prefer simple interfaces. Fewer arguments, fewer modes, fewer flags.
11. Do not implement speculative architecture. Build the smallest thing that fully meets the current
    requirement. No config option for a case that does not exist yet.

**Correctness**

12. Test important behaviour through stable interfaces, not internals. Use the relevant
    `scripts/check_*` regressions, self-tests, and publication gates; distinguish fixture results
    from verified runs against actual source data and deployed output.
13. When you fix a meaningful bug, add a check that would have caught it — a lint rule, a preflight
    assertion, a guard — not just the fix.
14. Treat schema and migration work conservatively. Additive first. Every SQL file in `docs/` is
    applied by hand by the owner; never assume one has been applied.
15. Treat authentication and permissions as high-risk. `middleware.js` and the Supabase RLS policies
    are the only things standing between a signed-out visitor and the desk's research. Never weaken
    them to make something work. If a change requires relaxing a gate, stop and ask the owner.
16. Protect secrets. Never print, log, commit, or echo a key value. `config/desk.json` and `.env`
    stay out of every served directory and every diff.
17. Handle external service failure deliberately. PSX, Yahoo, TradingView, Groq, Supabase and Resend
    all fail. A failure writes a degraded status and exits 0; it never crashes the cycle and never
    fabricates a value to keep going.

**Dependencies and providers**

18. Minimise dependencies. Prefer the four already installed. A new package needs a reason that
    survives "could this be twenty lines of stdlib?".
19. Isolate third-party provider logic. Supabase, Groq, Resend and Vercel specifics belong behind
    one module each, not sprinkled through callers.

**Finishing**

20. Run the verification commands below after any meaningful change. State what you ran and what it
    said — do not claim a check passed that you did not run.
21. Inspect the final diff before you finish. Unstaged noise, stray debug output and half-finished
    edits from another session are a real, documented hazard here.
22. Preserve backwards compatibility only where a real consumer depends on it. This desk has one
    owner and no external API clients — obsolete paths get deleted, not wrapped.
23. Document meaningful technical debt in `docs/TECH-DEBT.md`, with a concrete trigger for when it
    must be paid. "Clean this up eventually" is not a trigger.
24. Document architectural changes in `docs/ARCHITECTURE.md` in the same change that makes them.
25. Keep temporary workarounds identifiable and removable. Mark them, name the condition that
    retires them, and log them in `docs/TECH-DEBT.md`.
26. Preserve Git history and unrelated work. Never rewrite history, never `git add -A`, never stage
    a file you did not author this session. Publishing is the owner's action.
27. Explain important changes to the owner in plain English. The owner does not read code. A change
    is not delivered until it has been described in terms of what the product now does.

## Verification

The repository has standalone regression scripts, Python stdlib mocks and temporary Git
integration fixtures, including `check_publish_safety.py` and `check_routine_finalization.py`.
High-consequence maths is checked by `python scripts/check_rule4.py`, which `preflight.py`
runs on every publish. Run the checks your change touches; fixture success alone does not
prove routine acceptance or a production release.

```bash
python -m compileall -q scripts          # syntax-checks every Python file
node -c dashboard/app.js                 # one file; preflight now checks every shipped *.js
python scripts/check_rule4.py            # Rule 4 + payout-ratio golden cases
python scripts/preflight.py              # THE gate: shape, freshness, syntax, provenance
python scripts/provenance_lint.py        # provenance subset, standalone
python scripts/design_lint.py            # UI conventions — advisory, never fails
cd site && npm run build                 # the marketing site actually builds
```

Setup, if a fresh checkout: `pip install -r requirements.txt` then `cd site && npm install`.
`requirements.txt` is the only Python dependency source of truth (cloud and local).

`preflight.py` is the only hard gate — `publish.py` runs it first and refuses to publish on FAIL,
so the last-good site stays live. `--strict` promotes WARNs to failures.

Not side-effect-free, do not run casually: `scripts/run_desk_cloud.py` (writes Desk `state/`, needs network),
`scripts/publish.py` (**pushes to `main` on success**).

Workflow evidence in this checkout: `.github/workflows/desk-data.yml` runs on a weekday
schedule and manual dispatch, using Python 3.12 and gated publication. It has no push or
pull-request trigger; no separate Desk push/PR validation workflow is present. Do not confuse
Company Intelligence's separate repository/workflows with this checkout's continuous integration.
`site/package.json` builds with `astro build`; it does not wire `astro check` into that build.
Inspect current manifests and checks before claiming additional lint/type-check coverage.

## Publishing

```bash
python scripts/publish.py "message"          # data only
python scripts/publish.py "message" --code   # plus pre-staged hand-authored files
```

Race-safe and preflight-gated. `--code` ships only what is already staged; it never runs `git add -A`.
Files under `state/` are committed automatically. Full detail in `docs/OPERATIONS.md`; the failure
modes are in `docs/GOTCHAS.md`.

Desk typography (all current and future redesigned pages): Latin UI text, chart labels/values,
and tooltips use JetBrains Mono; retain existing Urdu glyph-font and icon-font exceptions.
