# Routine finalization

`scripts/finalize_routine.py` is the last, deterministic step for four manual
research routines:

| CLI routine | Existing routine | Mode |
|---|---|---|
| `pm` | PM checkpoint | `light`, `light-escalated`, or `light-skipped` |
| `daily` | daily refresh | `full` |
| `room` | Desk Room loop | `room` |
| `harvest` | weekly broker harvest | `harvest` |

The caller supplies the routine identity, its original PKT start time, the full
research commit SHA, the routine mode, and a short research-only outcome:

```text
python scripts/finalize_routine.py \
  --routine pm \
  --started 2026-09-12T17:20:00+05:00 \
  --research-sha 0123456789abcdef0123456789abcdef01234567 \
  --mode light \
  --outcome "checkpoint completed; no material escalation"
```

The SHA must be a full git object ID reachable from a freshly fetched
`origin/main`. That covers both a newly published research result and an
unchanged, already-published baseline: the baseline is accepted only when the
caller names the exact remote research commit. Before any state write, the
checkout must also be clean and exactly synchronized with `origin/main` (no
local-ahead or stale/behind commits). The script then runs the current
`scripts/preflight.py --desk`. Only after both checks pass does it append the
receipt and run log. PM additionally writes the existing checkpoint
acknowledgment; daily, Room, and harvest never write that acknowledgment.

The optional `--status` is structural and currently accepts only `success`.
Holiday, weekend, blocked, failure, and training results must not call this
finalizer. Research prose may contain words such as “failed” when they are not
the outcome's status prefix (for example, a company failed a target review).

The append-only receipt is `state/routine_finalization.json`. Each entry has:

```json
{
 "routine": "pm",
 "started": "2026-09-12T17:20:00+05:00",
 "research_sha": "...",
 "mode": "light",
 "outcome": "checkpoint completed",
 "ended": "2026-09-12T18:00:00+05:00",
 "ack_proof": {
  "acked_at": "2026-09-12T18:00:00+05:00",
  "by": "checkpoint-pm",
  "routine": "pm",
  "started": "2026-09-12T17:20:00+05:00",
  "research_sha": "..."
 }
}
```

PM receipts include this immutable acknowledgment proof. On retry, a PM
receipt is finalized only when the proof is valid and the remote
`state/checkpoint_ack.json` matches it, or when that acknowledgment is backed
by a strictly later PM receipt with its own matching proof. A missing or
corrupt same-session acknowledgment cannot be mistaken for completion, and an
older PM run cannot overwrite a newer current acknowledgment. Receipt `ended`
must be at or after `started`.

One pre-finalizer state is supported explicitly: an existing acknowledgment
whose exact shape is only `{"acked_at": "<PKT>", "by": "checkpoint-pm"}` is
treated as a legacy clock, not as proof for any routine, start, or research
SHA. A later PM start may replace it through the normal verified receipt path;
a PM start at or before that clock is blocked. The finalizer never fabricates
identity for the legacy object. Any partially expanded or malformed
acknowledgment is rejected.

`state/runlog.json` receives the normal `started`, `mode`, `ended`, and
`outcome` fields plus `routine` and `research_sha`. The receipt and run log do
not claim that transport succeeded. Before writing, the finalizer takes the
freshly fetched remote receipt and run-log arrays as the append-only base, so
newer remote rows are not overwritten by an older local checkout. After
writing, it invokes the existing `scripts/publish.py` path. It fetches
`origin/main` again and reports success only when the matching receipt entry,
matching run-log entry, and required PM acknowledgment (when applicable) are
present in the remote tree. For PM, the acknowledgment must also satisfy the
immutable-proof rule above. Unrelated newer entries do not need to make the
whole files byte-for-byte equal. The containing remote commit is reported
separately. A historic PM receipt remains finalized even if the current PM
acknowledgment later supersedes it; retry validation matches the historic
receipt/run-log identity instead of treating the current ack as a historic
snapshot.

Outcomes must describe research only; do not put push, publish, remote, commit,
deploy, or receipt claims in the outcome.

## Recovery

Finalizers acquire a separate, per-origin `finalization` lane before reading or checking
their baseline, and hold it through receipt publication and remote verification. The same
OS-lock implementation owns both lanes; the nested publisher still acquires the ordinary
`publish` lane. No environment variable or command-line flag bypasses publication locking.
This serializes local finalizers across both worktrees and independent clones without
deadlocking their nested publisher. A waiting clone may become stale while another run
finishes; it must stop before writing, synchronize normally, and retry the same inputs.
Canonical routines must retain separate checkouts: this is not authorization for another
routine to edit or publish files in the finalizer's checkout. Other machines and cloud
writers remain governed by clean rebase and fail-closed conflict handling.

- **Research SHA blocked:** publish the research through its owning routine and
  rerun with the full SHA of the resulting commit. No receipt, run-log entry,
  or PM acknowledgment is written by the failed finalization.
- **Preflight blocked:** repair the preflight failure, then rerun with the same
  inputs. The acknowledgment is written only after preflight passes.
- **Publisher or push blocked:** success is not reported. The local receipt,
  run log, and PM acknowledgment may already exist because they are the bytes
  the publisher was asked to transport. Do not create a new start time or
  delete those append-only entries. Inspect `origin/main` versus the local
  containing commit and reconcile the existing commit under the normal
  repository publishing ownership. Restore a clean, synchronized baseline
  before retrying; an existing local-ahead commit is explicitly blocked. Then
  rerun the exact same command; if the matching entries are on `origin/main`,
  the retry is an idempotent verification and adds no duplicate.
- **Publisher no-op after a failed push:** this is still blocked unless the
  second remote verification finds the matching receipt and log entries, plus
  the current PM acknowledgment for a new PM finalization. A local commit ahead
  of `origin/main` is not evidence of publication.

Run the mocked contract checks without touching live state:

```text
python scripts/check_routine_finalization.py
```

The check covers an unverified SHA, failed preflight, stale and local-ahead
baselines, failed receipt push, remote append-only history, superseded PM ack
idempotency, successful remote verification, and a real temporary bare-Git
transport proof.
