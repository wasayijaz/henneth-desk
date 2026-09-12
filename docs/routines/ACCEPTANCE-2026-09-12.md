# Routine acceptance — 2026-09-12

Interim evidence, not a completion certificate. Production baseline verified remotely:
`930a2f4b93e15d5edd7b8a7a0c8e810ed8fdfe3b`. Integration changes are not yet published.

| Existing scheduled task | Actual evidence | Remaining acceptance |
|---|---|---|
| PM checkpoint | Saturday calendar no-op; clean synchronized checkout; post-close self-test passed | Trading-day roles, publication, remote receipt and deployment |
| Daily refresh | Saturday calendar no-op; clean synchronized checkout; post-close self-test passed | Same-session PM dependency, three roles, publication and receipt |
| Desk Room loop | Saturday no-write branch; stale checkout safely fast-forwarded; task confirmed clean synchronized baseline and runbooks | Trading-day debate/QA/publication |
| Weekly harvest | Two dated broker calls and one Commercial Banks debate; source/dossier QA passed | Integrate new gates, review final diff, authorized publication and receipt |
| Weekly code review | Actual code/config review; integrated strict TS check and 59-page build passed; independent review identified legacy-ack and Friday-data blockers | Final integrated release verification after price-data repair |
| Product scout | Four new proposals, three existing open items retained; synchronized with byte-identical draft preserved | Report training hold rather than success; approved publication still pending |
| GitHub cadence check | API covered Sep 8–11: two scheduled runs each day; degraded | Catch-up coordination/approval hold; no dispatch yet |
| Blog publish | Five queued slugs already exist; build and desktop/mobile checks passed; clean synchronized queue confirmed in task | No-op confirmed; a future new post still needs full release validation |
| Landing page publish | Four queued pages already exist; synchronized baseline; build passed | No new page eligible; queue no-op does not prove a future new-page release |

## Interpretation safeguards

- Older tasks' summary API omitted messages that exist in their saved transcripts. Inspect actual
  transcript/tool evidence before treating an empty summary as a failed run or scheduling a retry.
- Permission-denied linked Git metadata was resolved with scoped escalation for ordinary Git
  operations. No global trust weakening, replacement tasks or worktree deletion was needed.
- Three clean checkouts were fast-forwarded in place; Product scout was fast-forwarded after
  proving its draft did not overlap incoming files, with an identical before/after SHA-256 hash.
- All nine saved prompts now require scoped permission handling and clear separated result bullets;
  schedules, target tasks and activation states were preserved. Only PM acknowledges checkpoints.
- Harvest's four high QA findings concern pre-existing historical price jumps (LSEVL, MDTL,
  CLCPS, USVIX), not today's authored broker calls/sector dossier. Three older rooms have stale
  views (PAEL, PIOC, JSML). These are not evidence that every live ticker is current.
- No weekend no-op, exhausted queue, mocked test, or draft validation is counted as an end-to-end
  production release. Research commit, receipt commit, and deployed revision require separate proof.

## Release gate

Replaying the stored snapshot against Friday 2026-09-11 23:59 PKT (diagnostic only, no state
changes) returns FAIL: index capture lacks a timezone-aware timestamp and 451/487 traded
counters have that session's EOD bar (92.61%, below the existing 99% threshold). Saturday's
`not_required` result does not establish Friday freshness. Investigate missing-counter identity
and producer evidence; do not fabricate a timestamp or exclude real traded symbols to pass.

Independent live inspection of https://dps.psx.com.pk/indices/ALLSHR confirms the symbol cell
declares `data-order="HASCOL"`, links `/company/HASCOL`, and carries `NC` in a separate badge.
The generic table parser removes tags without preserving boundaries, producing `HASCOLNC`.
Therefore a blanket NC history alias is not the correct repair: source symbol extraction must
respect the actual symbol field and retain compliance metadata separately. Preference/security
identities must not be collapsed. This changes the earlier identity assumption and needs the
targeted implementation checkpoint before editing the price-data schema/intake.

Desk preflight and the marketing build pass on the integration checkout. The publication lock,
publisher destination, deadline handling and receipt helper have targeted checks; independent
review and a final stable test pass remain mandatory before shipping. No claim of completion.

Review caught an additional first-run blocker: the real PM acknowledgement has only `acked_at`
and `by`, while the new helper initially required receipt-era fields. The local correction now
accepts the exact valid legacy shape only as a historical clock; a later verified PM may replace
it with a fully identified acknowledgement. Older/equal starts and malformed shapes are blocked.
The coordinator reran finalization checks: 13 mocked scenarios and one temporary bare-Git
transport fixture passed. The nine-runbook contract check passed. These are local checks, not
proof of production publication or deployment.

The sidebar inventory confirms exactly nine canonical tasks in Henneth Routines. Current
work remains uncommitted and unpushed in the isolated integration checkout. The price-data
identity repair remains at its targeted owner checkpoint; no additional access is missing.

Final local verification pass before that checkpoint: publisher lock, publisher safety, fetch
deadline, research publication policy, nine-runbook contract, and routine finalization checks all
passed; `git diff --check` passed. Desk preflight also passed but warned of 102 uncovered
universe entries, including synthetic NC tickers. Its weekend result does not override the
failed Friday replay above. Archived-task inventory confirms the redundant Weekly harvest task
`01a09614-7980-7de0-80db-e745e0a2c8de` is already archived; no additional task or worktree was
deleted. Completed in-task workers were closed after their changes and evidence were retained.

## Subsequent verification — 2026-09-12 22:40 PKT

- Real corrected snapshot: 491 securities; September 11 exchange source time is preserved.
  Post-close replay at the actual current time reported 491/491 traded counters current.
  The preceding complete intake fetched 581/581 configured identities (558 PSX, 23 foreign).
- Health and Desk preflight passed after rebuilding the corrected snapshot. The 61 older PSX
  last-trade series remain explicitly dated, not relabelled as current trades or called suspended.
- Independent review then found UTC-host attempt timestamps, snapshot/OHLC denominator omissions,
  date-only history acceptance, and mixed-date watchlist labelling. These are release blockers;
  the earlier green test does not overrule them. Repairs and additional negative tests are ongoing.
- Genuine full history refresh is running again with explicit offset-aware attempt timestamps.
  Do not convert old timestamps by hand or claim this second fetch is complete until it exits.
- Marketing build passed (59 pages). Homepage desktop screenshot inspected; mobile layout width
  check passed, but the thumbnail-like mobile capture is insufficient for a complete visual sign-off.
  Local Desk sign-in gate remains intact; signed-in Today rendering is not yet verified.
- Blog schedule prompt now records owner-authorized autonomous queue refill, draft resumption,
  independent fact-checking, one post per run, and GSC URL reporting. Schedule and task identity
  were preserved. Its existing task has been dispatched for reversible research/drafting while
  the initial shared-pipeline publication hold remains. No new post has been claimed published.
- Existing GSC connection was verified read-only for sc-domain:henneth.app; a hostname-filtered
  finalized Web Search summary for 2026-08-13 through 2026-09-09 returned 18 clicks and 1,457
  impressions. No SEO schedule or permission change was made.
- Integrated repair is still uncommitted/unpublished. All nine-routine acceptance requirements
  remain in scope; production publication, applicable research receipts and deployments are pending.

## Subsequent verification — completed refresh and independent release review

- Real full sweep completed at `2026-09-12T17:50:00.881401Z`: 581 attempted, processed,
  successful and cached identities; zero failures and deadline skips. New attempt timestamps
  carry explicit UTC offsets. The strengthened actual-time post-close gate passes 491/491
  September 11 traded counters; this is local source-data verification, not deployment proof.
- After that sweep, data health, dashboard rebuild, Desk preflight and the nine-runbook contract
  all passed. Intake identity/deadline/storage, capture (17), freshness (5), signal health (10),
  research publication and publication-lock regression checks passed.
- Independent publication review found two additional blockers: ignored unstage failure in
  data-only publication, and finalizer state writes outside finalizer serialization. The first
  is now repaired and its negative regression passes; concurrent-finalizer repair is ongoing.
  These findings override earlier readiness language. No production release is certified.
- Owner-authenticated live Desk inspection succeeded without changing authentication. The live
  Today page still shows KSE100 170511.85 with -0.06% against its stored prior snapshot. Integration
  also retains that prior-history calculation; an exact exchange daily-change audit is open.
  Do not claim ticker coverage alone proves the index return correct.
- The Blog task produced `how-to-compare-psx-sectors.mdx`, confirmed locally `draft: true`.
  Its transcript reports a 60-page build and 1280/375 rendering without overflow. Its wording
  "independent inline fact-check" is not sufficient proof of a separate checker; the same task
  has been asked to reconcile checker identity and the failed methodology-PDF fetch. No new URL
  is published and the integration release hold remains.
- Cost approval is saved in all nine automation prompts. Read-back verified unchanged names,
  kinds, schedules, activation statuses and target task IDs. No model override was requested.
  Shared README and its contract check also require explicit approval for new/additional costs,
  with unknown provider or connector pricing blocking that action. No paid service was enabled.

## Exchange daily-change source verification

- A read-only real PSX `/indices` request returned KSE100 current 170511.85, change
  +1646.81 and +0.98%, with the named table headers verified. The local September 10
  snapshot is 170610.7; neither Today nor Board may call the resulting -0.06% an
  official daily return. This is a confirmed consumer/source-contract defect.
- The proposed source-owned daily-change field addition and two-renderer change is
  recorded in TECH-DEBT.md for the required schema checkpoint. No past index row
  was rewritten. The current price gate proves coverage, not official return accuracy.
- Today article/provenance and chart-data regression suites pass, but they lack this
  daily-change counterexample and therefore cannot establish the affected feature's
  correctness. Index repair, finalizer concurrency review and release remain open.

## Owner release approval and blog correction

- The owner explicitly approved remaining repairs and code pushes, including the index
  data-field checkpoint. Index implementation is now authorized and underway; this does not
  waive any test, provenance, deployment or explicit cost-approval gate.
- Five formerly training-only automation prompts now record normal scoped publication/dispatch
  authorization after the initial integration release clearance. Existing schedules, IDs, task
  targets and status fields were retained. Blog/PM/Daily/Room already had their scoped authority.
- Blog follow-up completed in its existing task. The task corrected its earlier self-review
  claim, used a separate checker, removed an unread methodology citation and an unsupported
  sector example, and reports the corrected 60-page build plus both viewport checks passed.
  Draft remains unpublished under the shared release hold; no GSC submission URL exists yet.
- Finalizer lock implementation now reuses the existing PublishLock with a named finalization
  lane; main review requested actual overlapping finalize-process coverage. A first test run
  exposed a fixture's unset bare-repository HEAD, which is being corrected, not counted as a
  passing concurrency test. No production push or completion receipt has been claimed.

## Release-candidate verification — 2026-09-12

- Main reran the finalization suite: mocked failures, actual temporary Git transport, two
  overlapping finalizer processes, cross-clone contention and stale-clone retry all passed.
  Publisher safety/lock and nine-runbook contract checks also passed. These are test fixtures,
  not production routine receipts.
- Genuine official index fetch returned KSE100 current 170511.85, change +1646.81, +0.98%,
  derived previous close 168865.04, source `2026-09-11T16:50:00+05:00`. Older stored sessions
  were not corrected or fabricated. Independent review's stale-source overwrite finding was
  fixed; 21 market-capture tests now include full byte preservation for older sessions and
  older same-session timestamps. Reviewer closed that specific blocker.
- Health and dashboard rebuild passed. Final Desk preflight passed with no warnings and
  491/491 traded counters current. The new preflight-boundary regression passed all five cases.
- Local authenticated Today was visually checked at desktop and 375px mobile; the official
  index move and exchange timestamp are visible. Source dates appear per watchlist name.
  Mobile page width did not overflow. Local onboarding was dismissed through its normal UI;
  no authentication gate was changed. Production UI verification is still pending release.
- Marketing Astro build passed with 59 pages; desktop and mobile homepage screenshots were
  inspected with no measured page-width overflow. The global npm shim was broken, so the same
  installed Astro build entry point ran directly with the bundled Node runtime; no dependency
  installation or spending was needed.
- New current ORIENTATION/GIT_MODEL/ROUTINES docs and AGENTS links distinguish nine active
  Codex schedules from retired Claude schedules. Root handover originals and owner edits remain
  untouched. Exact approved Vercel Desk/marketing projects were verified against henneth-desk;
  the local .vercel mapping points to CI and was not used to deploy.
- This section certifies local release-candidate checks only. Push, live deployment and
  remaining applicable routine publications still need their own evidence below.
