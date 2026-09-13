#!/usr/bin/env python3
"""Keep the Company Intelligence shell separate from the Henneth Desk UI."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "Henneth Desk 2.CI.0"
FILES = (SHELL / "index.html", SHELL / "app.js", SHELL / "styles.css")

# These are inherited Desk product landmarks, not generic words such as
# "research" that are valid inside Company Intelligence routes.
FORBIDDEN = (
    "desk.henneth.app",
    "Desk sections",
    "Primary desk navigation",
    "Desk status",
    "Henneth research terminal",
    "Desk classification",
    "The desk has",
    "the desk will",
)
REQUIRED = (
    "Company Intelligence",
    'aria-label="Company directory"',
    'aria-label="Company intelligence directory tree"',
    "Intelligence cases",
)


def main() -> int:
    source = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    failures = [f"forbidden inherited Desk UI: {marker!r}" for marker in FORBIDDEN if marker in source]
    failures.extend(f"required CI landmark missing: {marker!r}" for marker in REQUIRED if marker not in source)
    result = "FAIL" if failures else "PASS"
    print(f"ci_product_identity: {result}")
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
