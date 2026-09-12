"""Golden-case checks for high-consequence deterministic maths.

Not a test framework. A small script the publish gate can run. It encodes CLAUDE.md
Rule 4 and the payout-ratio sign guard (the class of bug that already shipped once)
as expected numbers. Production calculators are not imported and not rewritten.

If this fails, preflight fails, publish.py does not push, last-good site stays live.

Usage: python scripts/check_rule4.py
"""
from __future__ import annotations

import math
import sys

from psx_data import canonical_symbol, split_board_state


def rule4_shares(capital: float, entry: float, stop: float,
                 risk_per_trade_pct: float = 1.0, max_pct_per_trade: float = 8.0):
    """CLAUDE.md Rule 4. Returns None when the setup is invalid."""
    if not (capital > 0 and entry > 0 and stop >= 0) or entry <= stop:
        return None
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None
    risk_budget = capital * risk_per_trade_pct / 100
    shares = math.floor(min(risk_budget / risk_per_share, (capital * max_pct_per_trade / 100) / entry))
    return shares if shares > 0 else None


def payout_ratio(dps, eps):
    """Same guard as scripts/fetch_fundamentals.py: only defined for positive EPS."""
    if dps is None or eps is None or not (eps > 0):
        return None
    return dps / eps * 100


# (capital, entry, stop, expected_shares_or_None, note)
# Hand-computed from the Rule 4 formula. Change a production calculator without
# updating these only if the *rule* changed — and then update CLAUDE.md in the
# same change.
RULE4_CASES = [
    (1_000_000, 100.0, 90.0, 800, "value cap binds: 8% of 1e6 is 800 shares at 100"),
    (1_000_000, 100.0, 50.0, 200, "stop distance binds: 1% of 1e6 / 50 = 200"),
    (1_000_000, 100.0, 100.0, None, "entry == stop is invalid"),
    (1_000_000, 100.0, 110.0, None, "stop above entry is invalid (long-only)"),
    (0, 100.0, 90.0, None, "zero capital is invalid"),
    (1_000_000, 0, 0, None, "zero entry is invalid"),
    (100_000, 200.0, 199.0, 40, "tight stop: risk would allow 1000, cap holds to 40"),
]

PAYOUT_CASES = [
    (5.0, 17.59, 28.425241614553723, "AKBL-shaped: positive DPS/EPS"),
    (2.0, -1.18, None, "lossmaking: must not produce a negative payout"),
    (0.0, 10.0, 0.0, "zero dividend on positive earnings is 0, not missing"),
    (1.0, 0.0, None, "zero EPS is not a payout ratio"),
    (None, 10.0, None, "missing DPS"),
]


# Corporate-action board suffixes. Golden cases from the 2026-08-17 universe.
# Only XD/XB/XR collapse here. Compliance badges are parsed separately from HTML;
# an arbitrary NC suffix is never sufficient evidence to rewrite a security identity.
SYMBOL_CASES = [
    ("FFCXD", "FFC", "XD", "Fauji Fertilizer ex-dividend counter"),
    ("HBLXD", "HBL", "XD", "Habib Bank ex-dividend counter"),
    ("BAFLXD", "BAFL", "XD", "Bank Alfalah ex-dividend counter"),
    ("NESTLEXD", "NESTLE", "XD", "Nestle Pakistan ex-dividend counter"),
    ("PAKTXD", "PAKT", "XD", "Pakistan Tobacco ex-dividend counter"),
    ("EFERTXD", "EFERT", "XD", "Engro Fertilizers ex-dividend counter — not ENGRO/ENGROH"),
    ("IPAKXB", "IPAK", "XB", "ex-bonus counter"),
    ("FPRMXR", "FPRM", "XR", "ex-right counter"),
    ("FFC", "FFC", None, "already canonical"),
    ("ENGROH", "ENGROH", None, "Engro Holdings is its own company, not a suffix of ENGRO"),
    ("HASCOLNC", "HASCOLNC", None, "never infer identity from an unstructured NC suffix"),
    ("EPCLPS", "EPCLPS", None, "preference share is a different security"),
    ("US500", "US500", None, "non-PSX symbols are untouched"),
    ("ffcxd", "FFC", "XD", "source case does not matter"),
]


def main():
    fails = []
    for capital, entry, stop, expected, note in RULE4_CASES:
        got = rule4_shares(capital, entry, stop)
        if got != expected:
            fails.append(f"Rule 4 {note}: expected {expected}, got {got} "
                         f"(capital={capital} entry={entry} stop={stop})")
    for dps, eps, expected, note in PAYOUT_CASES:
        got = payout_ratio(dps, eps)
        if expected is None:
            if got is not None:
                fails.append(f"payout {note}: expected None, got {got}")
        elif got is None or abs(got - expected) > 1e-9:
            fails.append(f"payout {note}: expected {expected}, got {got}")
    for src, canon, state, note in SYMBOL_CASES:
        got_c, got_s = split_board_state(src)
        if got_c != canon or got_s != state or canonical_symbol(src) != canon:
            fails.append(f"symbol {note}: {src!r} -> {(got_c, got_s)} "
                         f"(want {(canon, state)})")

    if fails:
        print("Henneth - check_rule4")
        print(f"\n  FAIL ({len(fails)}):")
        for f in fails:
            print(f"    x {f}")
        print("\n  RESULT: DO NOT DEPLOY — a golden case no longer matches the published rule.")
        sys.exit(1)
    print("Henneth - check_rule4")
    print(f"\n  RESULT: OK — {len(RULE4_CASES)} Rule 4 cases, {len(PAYOUT_CASES)} payout cases.")
    print(f"  RESULT: OK — {len(SYMBOL_CASES)} symbol-identity cases.")
    sys.exit(0)


if __name__ == "__main__":
    main()
