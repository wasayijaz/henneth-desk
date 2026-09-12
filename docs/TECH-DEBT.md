# Desk technical debt

This file covers the current Desk repository only. Record evidence and a concrete retirement trigger.

## Routine acceptance evidence

The 2026-09-12 tests produced actual runs in the canonical tasks. The task-summary API omitted
messages from older tasks; their saved transcripts contain tool execution and Markdown reports.
An empty summary therefore is not proof of a failed run. Some checkouts could not synchronize
because sandbox access to linked Git metadata was denied; use the normal scoped permission
escalation rather than changing global Git trust or creating replacement tasks.
Copied reports are historical context only. Close this item when each canonical
scheduled task has an actual run with required checks and truthful publication/deployment evidence.
Trading-day procedures require a trading-day acceptance run; a weekend skip is insufficient.

## Historical coverage labels

Preflight reports never-covered universe symbols as backfilling. Live provider evidence on
2026-09-12 disproved the existing explanation that the affected NC entries were independent
board counters without company history: the parser concatenates a separate compliance badge
onto the declared ticker. See `docs/routines/PRICE-HISTORY-2026-09-12.md`. Three other traded
securities have genuine short histories rejected by the ingestion minimum. Correct structured
identity extraction and price storage without weakening downstream research eligibility.
Close when source identities and coverage are verified and the latest completed trading session
passes its freshness gate; a weekend preflight pass is not sufficient evidence.

## Index daily change versus captured history — release blocker

Read-only public DPS `/indices` verification on 2026-09-12 returned columns Index, High,
Low, Current, Change, % Change. KSE100 was 170511.85, change +1646.81, +0.98%.
The retained September 10 history value is 170610.7, which yields -0.06% when compared
to September 11. The exchange-implied previous close is 168865.04; capture history
therefore cannot be assumed to be official close history. Both Today `indexRead()`
and Board `indexBoard()` currently derive daily moves from the retained snapshots.
Independent review also identified `dashboard/board.js` as a consumer requiring the same
repair. The primary DPS `/timeseries/eod/KSE100` endpoint was independently reported to
contain the official September 10 close; historical source availability must not be assumed
absent from old documentation. This report is not permission to rewrite retained records.

Proposed bounded repair: preserve exchange daily-change fields with source/session
provenance in `fetch_indices.py`; consume that evidence in Today and Board, with an
explicit unknown daily move when absent or inconsistent. Do not silently edit old
history or imply that this corrects every historic benchmark/scoring claim. Tests
must cover conflicting captured history, absent/malformed change, source coherence,
and the real counterexample. The owner approved this schema checkpoint and code publication
on 2026-09-12; implementation is underway, not yet released.
Close this blocker only after exact-source intake, both renderers, preflight and
live deployed daily change are independently verified. Historical index capture
quality remains a separate documented audit, not repaired by this field addition.
