#!/usr/bin/env python3
"""Verify the deterministic Company Intelligence premium-motion contract."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "Henneth Desk 2.CI.0" / "styles.css"
APP = ROOT / "Henneth Desk 2.CI.0" / "app.js"


def _check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _keyframe_body(source: str) -> tuple[str, str] | None:
    match = re.search(
        r"@keyframes ciProcessingSettle\{from\{([^}]*)\}to\{([^}]*)\}\}",
        source,
    )
    return (match.group(1), match.group(2)) if match else None


def main() -> int:
    errors: list[str] = []
    try:
        source = CSS.read_text(encoding="utf-8")
        app_source = APP.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"CI premium motion check: FAIL — {exc}")
        return 1

    tokens = {
        "--dur-press": "120ms",
        "--dur-enter": "240ms",
        "--dur-drawer": "280ms",
        "--ease-in-out": "cubic-bezier(.77,0,.175,1)",
        "--ease-drawer": "cubic-bezier(.32,.72,0,1)",
    }
    for name, value in tokens.items():
        _check(errors, f"{name}:{value}" in source, f"missing motion token {name}:{value}")

    expected_entrance = (
        ".workspace.is-entering .detail>.hero,"
        ".workspace.is-entering .detail>.grid4,"
        ".workspace.is-entering .detail>.panel,"
        ".workspace.is-entering .detail>.company-route-stack"
        "{animation:ciProcessingSettle var(--dur-enter) var(--ease-out) both}"
    )
    _check(errors, expected_entrance in source, "entrance must target direct content sections only")
    _check(
        errors,
        ".workspace.is-entering .detail .metric" not in source
        and '[class*="-card"]' not in source
        and '[class*="-tile"]' not in source,
        "nested card/tile entrance selectors must not remain",
    )
    for index, delay in enumerate((0, 35, 55, 75, 95), 1):
        _check(
            errors,
            f".workspace.is-entering .detail>*:nth-child({index}){{animation-delay:{delay}ms}}" in source,
            f"missing direct-section stagger {delay}ms",
        )
    _check(errors, 95 + 240 <= 335, "staggered entrance exceeds the 335 ms visible-sequence budget")

    keyframe = _keyframe_body(source)
    _check(errors, keyframe is not None, "ciProcessingSettle keyframe is missing")
    if keyframe is not None:
        start, end = keyframe
        _check(errors, start == "opacity:0;transform:translate3d(0,7px,0)", "entrance start must use opacity and transform only")
        _check(errors, end == "opacity:1;transform:none", "entrance end must use opacity and transform only")
        _check(errors, "filter" not in start and "filter" not in end, "entrance keyframe must not animate filter")

    _check(
        errors,
        "transition:transform var(--dur-drawer) var(--ease-drawer)" in source,
        "mobile drawers must use the drawer duration and easing",
    )
    for mobile_rule, message in (
        ("html{scrollbar-gutter:auto}", "mobile must not reserve desktop scrollbar gutter"),
        (".detail>*{min-width:0;max-width:100%}", "mobile detail children must shrink to the viewport"),
        (".detail :where(section,article,div){min-width:0}", "nested mobile grid items must release intrinsic table width"),
        (".baseline-table,.fact-table,.oi-benchmark-table{width:100%;max-width:100%;min-width:0}", "wide data tables must scroll inside a viewport-bounded wrapper"),
    ):
        _check(errors, mobile_rule in source, message)
    _check(
        errors,
        "animation:ciChartDraw 600ms var(--ease-out) forwards" in source,
        "charts must draw in 600 ms using the shared ease-out curve",
    )
    _check(
        errors,
        "@media (hover:hover){button:active,a[href]:active{transform:scale(.98);transition:transform var(--dur-press) var(--ease-in-out)}}" in source,
        "hover-capable controls must provide the 120 ms scale press response",
    )
    _check(
        errors,
        "enhanceMotion({ animate: !searchState || Boolean(searchState.focusView) });" in app_source,
        "page-route changes must animate while search and form rerenders remain still",
    )

    reduced_motion = re.search(
        r"@media \(prefers-reduced-motion:reduce\)\{\*,\*::before,\*::after\{([^}]*)\}button:active,a\[href\]:active\{([^}]*)\}\}",
        source,
    )
    _check(errors, reduced_motion is not None, "reduced-motion global override is missing")
    if reduced_motion is not None:
        global_body, active_body = reduced_motion.groups()
        _check(errors, "animation:none!important" in global_body, "reduced motion must remove animations")
        _check(errors, "transition-property:color,background-color,border-color,opacity!important" in global_body, "reduced motion must retain color/opacity feedback properties")
        _check(errors, "transition-duration:var(--dur-press)!important" in global_body, "reduced motion feedback must use the press duration")
        _check(errors, "transform:none!important" in active_body, "reduced motion must remove press movement")

    if errors:
        print("CI premium motion check: FAIL")
        for error in errors:
            print(f"  x {error}")
        return 1
    print("CI premium motion check: OK (motion, mobile containment, charts, press, reduced motion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
