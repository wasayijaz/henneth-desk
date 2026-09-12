"""Offline regression for the official index-change preflight boundary."""
from unittest.mock import patch

import preflight


def main():
    cases = [
        (None, "missing", True, False),
        ({"live": {}}, None, False, True),
        ({"daily_change": {}}, None, False, True),
        ({"daily_change": []}, None, True, True),
        ({"daily_change": {"KSE100": {"percent": 0.98}}}, None, True, False),
    ]
    for data, error, fails, warns in cases:
        with patch.object(preflight, "load", return_value=(data, error)), \
                patch.object(preflight, "fails", []), patch.object(preflight, "warns", []):
            preflight.check_index_daily_change()
            assert bool(preflight.fails) == fails, preflight.fails
            assert bool(preflight.warns) == warns, preflight.warns
    print("index daily-change preflight boundary: PASS (5 cases)")


if __name__ == "__main__":
    main()
