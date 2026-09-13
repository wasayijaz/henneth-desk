#!/usr/bin/env python3
"""Verify the Company Intelligence mobile readability and containment contract."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "Henneth Desk 2.CI.0" / "styles.css"


def _check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []
    try:
        source = CSS.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"CI mobile readability check: FAIL - {exc}")
        return 1

    containment_rules = (
        ("html{scrollbar-gutter:auto}", "mobile must remove the desktop scrollbar gutter"),
        ("body,.shell,#app,.workspace,.detail{width:100%;max-width:100%}", "mobile app shell must be viewport bounded"),
        (".detail{overflow-x:hidden;scrollbar-width:none}", "mobile detail pane must suppress page-level horizontal overflow"),
        (".detail>*{min-width:0;max-width:100%}", "direct detail children must shrink inside the viewport"),
        (".detail :where(section,article,div){min-width:0}", "nested cards and grids must release intrinsic width"),
        (".baseline-table,.fact-table,.oi-benchmark-table{width:100%;max-width:100%;min-width:0}", "wide table wrappers must be bounded before they scroll internally"),
    )
    for needle, message in containment_rules:
        _check(errors, needle in source, message)

    readable_rules = (
        ("@media (max-width:560px){.topbar{min-height:44px}", "mobile readability block must be emitted at the phone breakpoint"),
        (".drawer-open{width:40px;min-height:40px}", "mobile drawer controls must meet a 40 px touch target"),
        (".tree-folder-row,.tree-folder-label,.tree-leaf,.tree-expander,.past-context-tabs button,.strategy-flow-step,.ownership-flow-step,.intelligence-lifecycle-step{min-height:40px}", "mobile navigation and route controls must meet a 40 px touch target"),
        (".ci-chart{min-height:168px}", "mobile chart blocks need enough vertical room for labels"),
        (".metric .ci-chart{min-height:70px}", "metric charts need a separate compact mobile floor"),
        (".ci-svg-source{font-size:8.5px}", "legacy chart source labels must stay readable on phones"),
        (".ci-viz-inspector,.ci-viz-record-legend{font-size:12px;line-height:1.55}", "Lieflat inspector text must stay comfortably readable on phones"),
        (".evidence blockquote,.change-card blockquote,.oi-evidence-row blockquote{max-width:100%;overflow-wrap:anywhere;word-break:break-word}", "long retained evidence text must wrap instead of widening the mobile page"),
        ("scrollbar-color:var(--focus) transparent", "wide mobile tables must expose an internal scroll affordance"),
        ("box-shadow:inset -16px 0 0 color-mix(in srgb,var(--focus) 10%,transparent)", "wide mobile tables must show a right-edge scroll cue"),
        (".baseline-table::-webkit-scrollbar,.fact-table::-webkit-scrollbar,.oi-benchmark-table::-webkit-scrollbar{height:8px}", "wide mobile tables must keep a visible touch-scroll bar"),
        (".baseline-table table,.fact-table-head,.fact-table-row,.oi-benchmark-row{min-width:min(760px,210vw)}", "wide table contents must scroll inside their bounded wrappers"),
    )
    for needle, message in readable_rules:
        _check(errors, needle in source, message)

    _check(
        errors,
        "@media(prefers-reduced-motion:reduce){.ci-viz-svg *{animation:none!important;transition:none!important}" in source,
        "mobile chart hardening must preserve reduced-motion behavior",
    )

    if errors:
        print("CI mobile readability check: FAIL")
        for error in errors:
            print(f"  x {error}")
        return 1
    print("CI mobile readability check: OK (viewport containment, readable charts, scroll affordance, touch targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
