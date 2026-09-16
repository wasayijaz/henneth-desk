"""Validate the repository-owned contract for Henneth's nine routine runbooks."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTINES = ROOT / "docs" / "routines"
RUNBOOK_IDS = (
    "henneth-pm-checkpoint",
    "henneth-daily-refresh",
    "henneth-desk-room-loop",
    "henneth-weekly-harvest",
    "henneth-weekly-code-review",
    "henneth-product-scout",
    "henneth-github-cadence-check",
    "henneth-blog-publish",
    "henneth-landing-page-publish",
)

REQUIRED_MARKERS = (
    "<!-- REPOSITORY-OWNED-RUNBOOK -->",
    "<!-- REPORTING-INCLUDE: REPORTING.md -->",
    "<!-- PROVIDER-NEUTRAL-RUNTIME -->",
)
REQUIRED_REPORTING_HEADINGS = (
    "Status / Result",
    "Data or Findings",
    "Actions / Publication",
    "Verification",
    "Problems / Next action",
)

# These identify runtime/provider instructions that must not return in a Codex runbook. The
# no-runtime marker is intentionally not treated as a violation.
PROHIBITED_LEGACY_STRINGS = (
    ".claude/",
    ".claude\\",
    "scheduled-tasks",
    "claude -p",
    "Task tool",
    "Skill tool",
    "Co-Authored-By",
    "anthropic.com",
    "noreply@anthropic",
    "AUTOMATION-PLAN.md",
)


def check() -> list[str]:
    errors: list[str] = []
    shared = ROUTINES / "README.md"
    shared_text = shared.read_text(encoding="utf-8") if shared.is_file() else ""
    for phrase in ("Synchronization proof", "`HEAD`", "`origin/main`",
                   "fetch updates the remote reference, not the working files"):
        if phrase not in shared_text:
            errors.append(f"shared synchronization contract missing: {phrase}")
    for phrase in ("Cost approval", "explicit owner approval", "connector pricing",
                   "unknown pricing blocks", "additional billable usage"):
        if phrase not in shared_text:
            errors.append(f"shared cost-approval contract missing: {phrase}")
    for phrase in ("Standing publication approval", "must not ask for the same approval again",
                   "New costs", "failed gate"):
        if phrase not in shared_text:
            errors.append(f"shared standing-publication contract missing: {phrase}")
    reporting = ROUTINES / "REPORTING.md"
    if not reporting.is_file():
        errors.append("missing docs/routines/REPORTING.md")
    else:
        reporting_text = reporting.read_text(encoding="utf-8")
        for heading in REQUIRED_REPORTING_HEADINGS:
            if heading not in reporting_text:
                errors.append(f"REPORTING.md missing required heading: {heading}")

    for routine_id in RUNBOOK_IDS:
        path = ROUTINES / f"{routine_id}.md"
        if not path.is_file():
            errors.append(f"missing runbook: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in REQUIRED_MARKERS:
            if marker not in text:
                errors.append(f"{routine_id}: missing marker {marker}")
        if "REPORTING.md" not in text:
            errors.append(f"{routine_id}: missing shared reporting include")
        for heading in ("Required result fields", "Outcomes"):
            if heading not in text:
                errors.append(f"{routine_id}: missing section {heading}")
        for legacy in PROHIBITED_LEGACY_STRINGS:
            if legacy.casefold() in text.casefold():
                errors.append(f"{routine_id}: prohibited legacy string: {legacy}")

    finalizer_calls = {
        "henneth-pm-checkpoint": ("pm", "light"),
        "henneth-daily-refresh": ("daily", "full"),
        "henneth-desk-room-loop": ("room", "room"),
        "henneth-weekly-harvest": ("harvest", "harvest"),
    }
    for routine_id, (cli_id, mode) in finalizer_calls.items():
        path = ROUTINES / f"{routine_id}.md"
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if "scripts/finalize_routine.py" not in text or "FINALIZATION.md" not in text:
                errors.append(f"{routine_id}: missing remote completion receipt procedure")
            if "Always acknowledge" in text:
                errors.append(f"{routine_id}: unconditional acknowledgement can hide failed work")
            if f"--routine {cli_id}" not in text or f"`{mode}`" not in text:
                errors.append(f"{routine_id}: finalizer CLI identity/mode is not explicit")
    if not (ROUTINES / "FINALIZATION.md").is_file():
        errors.append("missing FINALIZATION.md")

    pm_path = ROUTINES / "henneth-pm-checkpoint.md"
    daily_path = ROUTINES / "henneth-daily-refresh.md"
    room_path = ROUTINES / "henneth-desk-room-loop.md"
    if pm_path.is_file():
        pm = pm_path.read_text(encoding="utf-8")
        for phrase in ("only news scan", "10 external", "Do not run Macro or Market Analyst",
                       "Before reading any runbook or state file", "git rev-parse HEAD",
                       "Check `gh auth status` first", "do not open a browser"):
            if phrase not in pm:
                errors.append(f"PM efficiency contract missing: {phrase}")
    if daily_path.is_file():
        daily = daily_path.read_text(encoding="utf-8")
        for phrase in ("do not run News Sentinel again", "exactly two judgment roles",
                       "16 external", "--poll-seconds 180"):
            if phrase not in daily:
                errors.append(f"Daily efficiency contract missing: {phrase}")
    if room_path.is_file():
        room = room_path.read_text(encoding="utf-8")
        if "--poll-seconds 180" not in room:
            errors.append("Room efficiency contract missing: --poll-seconds 180")

    blog_path = ROUTINES / "henneth-blog-publish.md"
    if blog_path.is_file():
        blog = blog_path.read_text(encoding="utf-8").casefold()
        for phrase in ("standing blog-only authorization", "independent", "three", "draft: true",
                       "google search console", "idempotency", "release hold",
                       "staged publication proof", "git show :site/src/content/blog/<slug>.mdx"):
            if phrase not in blog:
                errors.append(f"blog autonomous publication contract missing: {phrase}")
        for obsolete in ("if no item qualifies, finish as `no-op`", "must explicitly approve the reviewed"):
            if obsolete in blog:
                errors.append("blog contract restores retired empty-queue/per-post approval stop")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("routine contract: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"routine contract: PASS ({len(RUNBOOK_IDS)} runbooks + REPORTING.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
