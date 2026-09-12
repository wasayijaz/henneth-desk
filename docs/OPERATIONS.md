# Henneth — Desk operations runbook

This runbook covers the PSX research desk only. Governance rules live in [`CLAUDE.md`](../CLAUDE.md);
architecture is in [`ARCHITECTURE.md`](ARCHITECTURE.md); sharp edges are in [`GOTCHAS.md`](GOTCHAS.md).

## 1. Product boundary

| Product | Repository | Deployment |
|---|---|---|
| Henneth Desk | this repository | `https://desk.henneth.app` |
| Henneth marketing | `site/` in this repository | `https://henneth.app` |
| Henneth CI | `github.com/wasayijaz/henneth-ci` | `https://ci.henneth.app` |

CI split: on 2026-09-11 the CI product moved to `github.com/wasayijaz/henneth-ci`. The CI app folder,
CI release flows, CI-owned state and CI-specific checks are no longer in this repository.

The Desk pipeline is deterministic and read-only with respect to trading execution. It may research,
score and monitor; it never places orders.

## 2. Desk refresh flow

When the computer is off, GitHub Actions runs `.github/workflows/desk-data.yml` and invokes the Desk
cloud path. When the computer is on, local scheduled tasks run the judgement agents. Both paths use
the same committed `state/` seam and the same publication gate.

The ordered deterministic flow is:

1. `update_universe.py`, history, liquidity, company profiles and market context.
2. Dividends, fundamentals, quant, predictability, backtests and the live snapshot.
3. Scores, sectors, macro context, astro state, fair value and signals.
4. Checkpoint state, Desk Room dossiers/queue/gate/score/verification, public extracts and dashboard.
5. `preflight.py`, followed by the normal Desk publish path.

`run_desk_cloud.py` is the production-oriented ordered list. `run_cloud.py` is the desk-only local/cloud
entry point for the same product boundary. Both keep `fetch_company_profiles.py`, `build_calendar.py`,
`build_checkpoint_trigger.py --desk`, Desk Room scripts and the astro/public/dashboard builders.

Provider failures must retain last-good data where possible, write degraded health and exit 0. No step
may invent a price, date, dividend or financial value to keep the cycle moving.

## 3. Publication path

Always use:

```text
python scripts/publish.py "Desk refresh or change description"
```

`publish.py` runs `python scripts/preflight.py --desk` first. A failure leaves the last-good site live.
The normal path stages only regenerated `state/` and the generated marketing extract. Hand-authored
files must be staged explicitly and then shipped with `--code`.

The path is intentionally race-safe: local worktrees and private clones of the same origin share
a same-user, same-host repository push lock, and a rejected
push retries only after a clean rebase. Any rebase conflict— including a conflict under `state/`—
aborts and stops for human resolution; the publisher never chooses `ours` or `theirs`. A clean
rebase reruns Desk preflight before the retry push. The default state staging excludes all seven
CI-private root files and the `state/company_intel/**` subtree, and those exclusions must remain in
place for stale local writers. Cloud/other machines rely on Git fast-forward rejection and rebase
verification; the local lock is not a distributed mutex.

PM, Daily, Room and Harvest finish through `scripts/finalize_routine.py` as documented in
`routines/FINALIZATION.md`. It verifies published research before writing a completion receipt,
then publishes and verifies the runlog and (PM only) acknowledgement. A failed receipt remains
incomplete; a local acknowledgement alone must not release the next routine.

Do not run `git add -A`, hand-push state, or publish from an unreviewed worktree. Never run
`scripts/publish.py` from a cleanup worker.

## 4. Verification gate

Run the checks that match the change. The full desk gate is:

```text
python -m compileall -q scripts
python scripts/check_rule4.py
node -c dashboard/app.js
python scripts/preflight.py
```

The gate checks Python/served JavaScript syntax, provenance, Rule 4, generated URL safety, root Ask,
Today UI, raw-artifact safety, core state shape, history completeness/rotation, post-close integrity,
Desk Room shape and data-health status.

Retain the root CI-private publication deny-list (the seven CI-owned root files plus
`state/company_intel/**`) and its preflight check after separation.
Never fabricate or backfill a refresh completion timestamp to pass a gate. Only the deterministic
producer can establish that a refresh completed; missing evidence blocks publication until a verified run.

Off-market publication checks the latest completed trading session, not an automatic weekend pass.
Routine calendar skips still perform no writes. Source timestamps identify the exchange session;
capture/build timestamps indicate processing only and must not be presented as new trading activity.

The marketing site has its own build:

```text
cd site && npm run build
```

Do not run `scripts/run_cloud.py` casually: it writes state and may call external providers. Do not
run `scripts/publish.py` during review or cleanup work.

## 5. State and access boundaries

`state/` is the single source of truth. The dashboard reads state; it does not write it. The marketing
site reads only `site/src/data/public/`, which is generated by `build_public_slice.py`.

Root `middleware.js` matches `/state/:path*`. Only `natal_ephem.bin`, `natal_ephem.json` and
`public_probe.json` are public. Every other desk state file requires a valid Supabase ES256 bearer.
Keep this behavior unchanged when touching auth or `/state/`.

`config/desk.json` contains real capital and alert secrets. It must never be served, printed, logged,
or copied into `state/`, `public/` or a diff. `.env` is likewise private.

## 6. Desk Room and local judgement

The cloud builds deterministic Desk Room scaffolding (`room_dossier.py`, `room_queue.py`, `room_gate.py`,
`room_score.py`, `room_verify.py`). Local agents read those compact artifacts and write judgment state
such as `rooms.json`, `daily_read.json`, `macro.json` and `claims.json`. Agents never fetch providers
directly and never bypass the state seam.

The checkpoint trigger guarantees the first daily checkpoint, keeps monitoring unconditional while
positions are open, and wakes the local judgement loop when news or health requires it. It no longer
depends on Company Intelligence monitoring.

## 7. Hosting

The root `vercel.json` builds `public/` through `scripts/vercel_build.sh`. The build copies the
dashboard and committed state, keeps `config/` private, and serves the terminal SPA fallback only for
clean dashboard routes. The marketing `site/vercel.json` is separate and must not inherit the root
terminal configuration.

HTML/JS must revalidate. State files use short caching with stale-while-revalidate. A caching service
worker must not intercept state requests because freshness is part of the product contract.

## 8. External failure and recovery

If a provider is down, inspect `state/health.json`, the cycle transcript under `logs/`, and the last
producer output. Preserve last-good state; do not guess. If preflight fails, fix the producer or state
shape at its owner, rerun the relevant check, then rerun the full gate. If post-close integrity fails,
allow the recovery path to refetch before attempting publication.

## 9. Change discipline

Read both producer and consumer before changing a state seam. Keep authoritative rules in one owner.
Add a preflight assertion when fixing a meaningful publication bug. Inspect the final diff and status
before handing work to the owner. Never edit a live strategy in place, weaken authentication, expose
private config, or add a compatibility layer for a removed product.

## 10. Gradual automation acceptance

1. Prove deterministic intake, source dates, full-sweep coverage and safe publication on actual
   data. Failed inputs retain last-good output; never promote an offline test to a live result.
2. Prove each routine in its existing scheduled task. Calendar/empty-queue no-ops are valid but
   do not substitute for an applicable research-and-publication run. Keep its source evidence,
   research SHA, completion receipt and deployed revision distinguishable.
3. Promote a training routine to unattended publication only after owner approval of its actual
   evidence. Preserve approved model, schedule, task identity and product boundary. No blanket
   activation follows from repairing the data pipeline.
4. Automate bounded recoveries at their deterministic owner, with an observable failure outcome.
   Repeated failure escalates; it must not cause duplicate research, overlapping writers, relaxed
   gates or an unlimited retry loop. Product scout proposes improvements and build levels, not
   unapproved feature implementation.

Deploy via the repository's gated Git publication path. A legacy local `.vercel/project.json`
may still name CI; do not infer a Desk deployment target from it. Verify the Vercel project's
repository and domain explicitly. Desk and marketing link to `henneth-desk`; CI releases remain
independent and must not be triggered by this checkout.
