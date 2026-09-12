# Git model for Henneth work

Read before Git operations. This map reflects the integration checkout inspected on
2026-09-12; inspect the assigned checkout again before any mutation.

## Checkout and repository identity

The authorized integration checkout is `D:/PSX Trader X Claude/.codex-routine-hardening`,
on `codex/routine-hardening`. Its Git common directory is `D:/PSX Trader X Claude/.git`;
its origin is `https://github.com/wasayijaz/henneth-desk.git`. It is a linked worktree,
not the owner-root working tree. Other routine tasks may have their own existing worktrees
or private clones; keep each task in its assigned checkout.

The owner checkout at `D:/PSX Trader X Claude` contains unrelated dirty work and uncommitted
handover originals. Preserve them. Do not clean, reset, relocate, or publish that checkout
as part of integration. Old instructions banning all `.codex-*` paths do not apply to an
explicitly assigned routine worktree. Conversely, a plausible sibling path is not permission
to edit it. Scope searches to `scripts/`, `docs/`, `dashboard/` or `site/` inside the assignment;
avoid recursively searching the owner root and every nested checkout.

Useful read-only checks, run from the assigned directory:

```text
git rev-parse --show-toplevel
git rev-parse --git-common-dir
git branch --show-current
git status --short
git diff --cached --name-only
```

Branch, worktree and dirty-file counts drift; there is no fixed expected count. Cloud commits
advance the remote, but do not themselves rewrite every local working tree. Diagnose local
changes before attributing or removing them.

## Preserve ownership when synchronizing and publishing

Follow [OPERATIONS.md](OPERATIONS.md) and [ROUTINES_AFTER_SPLIT.md](ROUTINES_AFTER_SPLIT.md).
Synchronize with the canonical remote before research and again before publication. Inspect
dirty/index state and preserve append-only records. A permission error is not a successful
sync: use scoped escalation for the ordinary Git operation, without global trust changes.
Stop on real conflicts; do not choose `ours`/`theirs` or discard another worker's edits.

Fetching is not synchronization of working files. Before research, compare `git rev-parse HEAD`
with the freshly fetched `git rev-parse origin/main`; if different, preserve the draft and
update the working branch normally before validating current production code/data. Quote both
full IDs as evidence. A check run on an older HEAD is not acceptance of a newer remote release.

Never run blanket `git add -A`. When staging is authorized, name only authored paths and
inspect the staged diff. If unrelated work is already staged, coordinate with its owner;
do not reset the whole index. Do not delete branches/worktrees or rewrite history to tidy up.

Use [publish.py](../scripts/publish.py) for authorized publication. Its data-only path stages
eligible Desk state and generated marketing extracts; `--code` includes explicitly pre-staged
authored files. CI-private exclusions remain mandatory. The current publisher pushes the
verified `HEAD` to remote `main`; local `main` may name a different commit. Never substitute
a hand-written push or assume a no-change publisher result transported an earlier local commit.

[publish_lock.py](../scripts/publish_lock.py) coordinates participating publishers for the
same user, host and canonical origin, including separate local clones. **This lock is not
distributed:** cloud jobs and other hosts rely on Git fast-forward rejection, conflict-safe
rebase handling and fresh preflight. It also does not serialize every research/data writer.

A remote commit is publication evidence, not deployment proof. PM/Daily/Room/Harvest use
[FINALIZATION.md](routines/FINALIZATION.md) for separate research and completion receipts.
Respect release holds and the [cost approval boundary](routines/README.md#shared-execution-rules).
