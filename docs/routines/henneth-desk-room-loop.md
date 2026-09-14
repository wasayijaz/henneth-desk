<!-- REPOSITORY-OWNED-RUNBOOK -->
<!-- REPORTING-INCLUDE: REPORTING.md -->
<!-- PROVIDER-NEUTRAL-RUNTIME -->

# henneth-desk-room-loop

Weekday evening Desk Room loop. It spends tokens only on the deterministic gate's selected names,
ends at a neutral bull/bear debate, and never publishes a named-security house call. Work in the
assigned `wasayijaz/henneth-desk` routine worktree. Read [REPORTING.md](REPORTING.md), `AGENTS.md`,
`docs/ROUTINES_AFTER_SPLIT.md`, `docs/DESK-ROOM-PLAN.md`, and `docs/PUBLICATION_RESTRUCTURE_V2.md`.

## Run

1. Synchronize the worktree and record PKT start time. Check `state/calendar.json`; a holiday or
   weekend is a `no-op` with no state or publication changes.
2. Wait for and verify the same-session Daily receipt with
   `python scripts/wait_for_routine_receipt.py --routine daily --date <YYYY-MM-DD> --timeout-seconds 5400`.
   Do not dispatch data while waiting for Daily. After the receipt verifies, synchronize and run
   `python scripts/post_close_integrity.py`. Dispatch one cloud catch-up only when this integrity
   check itself fails; never dispatch merely because the Daily receipt is absent. Wait for that
   exact run, synchronize, and recheck. A timed-out predecessor or still-failed integrity gate
   blocks Room publication.
3. Refresh the free Room layer in order: `python scripts/fetch_research.py`,
   `python scripts/room_dossier.py`, `python scripts/room_queue.py`, and
   `python scripts/room_gate.py`. Read `state/room_plan.json` and record `_meta.counts` and the
   exact `run_full_now[]` list. Never exceed the live `state/budget.json` deep-dive cap.
4. If `state/research_staging/` contains text documents, run one Librarian role per document. Use
   a Luna-high subagent when callable, otherwise inline the committed role: digest the document by
   content hash, extract only sourced broker/filing claims, merge through the deterministic state
   path, and remove the staged text after a successful merge. Empty staging is a no-op for this step.
5. Apply each `reaffirm[]` item with `python scripts/room_apply.py <SYM> --reaffirm`. For each
   `delta[]` item, run one Luna-high-or-inline Chartist role from its technical dossier, write the
   prescribed temporary memo, then apply `--delta`.
6. For the whole `run_full_now[]` batch, run `python scripts/room_batch.py`. Stage 1 runs Chartist
   and Fundamentalist roles in parallel per ticker; Stage 2 runs one Debate role per ticker after
   every Stage 1 file exists. Each role uses Luna high when callable or its committed inline card.
   Personas must read only the supplied dossier lane, use no memory numbers, and write the prescribed
   JSON. There is no Chair stage and no per-ticker claims file.
7. Run `python scripts/room_assemble.py`; missing debate output skips that ticker rather than
   creating a partial room. Run `python scripts/room_verify.py`, then the Verifier role for each
   assembled ticker, using Luna high when callable or the committed inline QA card. A blocked or
   high-severity finding must be corrected or explicitly left unpublished. Record QA in each room.
8. After QA, run one scoped translation extraction/merge for this batch. Translation is non-blocking
   and must never broaden to old sessions; an English session remains valid if translation fails.
9. Run `python scripts/room_score.py`, then `python scripts/build_dashboard.py`. A preflight failure
   stops publication.
10. Publish with `python scripts/publish.py "Desk Room loop <YYYY-MM-DD>: <full> full, <delta> delta, <reaffirm> reaffirm"`.
   Record exact SHA/URL only when verified. Then follow [FINALIZATION.md](FINALIZATION.md) using
   `scripts/finalize_routine.py` with the research SHA, start time, `--routine room`, mode `room` and Room
   counts. Report the separately verified receipt SHA. Never mark an unpublished local log as filed.

## Required result fields

`date`; `market_day`; `room_plan.counts`; `reaffirm[]`; `delta[]`; `full[]`; `budget_cap`;
`librarian_documents`; `stage_completion`; `assembled[]`; `skipped_incomplete[]`; `qa_by_ticker[]`;
`translation.status`; `resolved_claims`; `preflight`; `runlog_written`; `publication.status`;
`publication.sha`; `publication.url`; `problems[]`; `next_action`.

## Outcomes

- `success`: every selected stage completed or an explicitly recorded incomplete ticker was omitted,
  QA/preflight passed, runlog was written, and publication was verified or was an unchanged no-op.
- `no-op`: holiday/weekend, no eligible Room work, or only reaffirmation with no state change; record
  the readable gate and counts. Do not manufacture a debate.
- `blocked`: budget, data health, missing predecessor, missing required staged output, or unresolved
  QA finding prevents a safe publish. Leave the last-good public state intact.
- `fail`: a deterministic stage, role, assembly, translation boundary, QA persistence, preflight,
  publication, or runlog write failed unexpectedly. Report the exact ticker/stage and recovery step.

Use [REPORTING.md](REPORTING.md); debate notes must remain neutral research, never advice.
