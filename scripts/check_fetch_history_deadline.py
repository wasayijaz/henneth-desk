"""Deterministic regression checks for fetch_history's request/intake deadline."""
import time

import requests

import fetch_history
import psx_data


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def check_request_timeout_is_bounded():
    observed = []

    class SlowSession:
        def get(self, _url, timeout):
            observed.append(timeout)
            time.sleep(timeout + 0.01)
            raise requests.Timeout("simulated slow provider")

    original_session = psx_data._sess
    original_slot = psx_data._next_slot[0]
    psx_data._sess = lambda: SlowSession()
    psx_data._next_slot[0] = 0
    try:
        budget = 0.1
        deadline = time.monotonic() + budget
        started = time.monotonic()
        try:
            psx_data.eod_history("SLOW", deadline=deadline)
        except psx_data.DeadlineExceeded:
            pass
        else:
            raise AssertionError("slow request was not classified as deadline-skipped")
        elapsed = time.monotonic() - started
    finally:
        psx_data._sess = original_session
        psx_data._next_slot[0] = original_slot

    _assert(observed and 0 < observed[0] <= budget + 0.01,
            "request did not receive the remaining deadline")
    _assert(elapsed < 0.3, f"slow request exceeded bounded test budget: {elapsed:.3f}s")


def check_default_and_long_deadline_keep_20_second_cap():
    observed = []

    class ImmediateFailureSession:
        def get(self, _url, timeout):
            observed.append(timeout)
            raise requests.ConnectionError("simulated provider outage")

    original_session = psx_data._sess
    original_slot = psx_data._next_slot[0]
    original_sleep_until = psx_data._sleep_until
    psx_data._sess = lambda: ImmediateFailureSession()
    psx_data._next_slot[0] = 0
    psx_data._sleep_until = lambda _deadline, _seconds: None
    try:
        try:
            psx_data.eod_history("DEFAULT")
        except requests.ConnectionError:
            pass
        else:
            raise AssertionError("default caller did not preserve provider failure")
        try:
            psx_data.eod_history("LONG", deadline=time.monotonic() + 1200)
        except requests.ConnectionError:
            pass
        else:
            raise AssertionError("deadline caller did not preserve provider failure")
    finally:
        psx_data._sess = original_session
        psx_data._next_slot[0] = original_slot
        psx_data._sleep_until = original_sleep_until

    _assert(observed == [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20],
            f"default/long-deadline requests changed the 20-second cap: {observed}")


def check_near_deadline_passes_remaining_budget():
    observed = []

    class SlowSession:
        def get(self, _url, timeout):
            observed.append(timeout)
            raise requests.Timeout("simulated near-deadline timeout")

    original_session = psx_data._sess
    original_slot = psx_data._next_slot[0]
    psx_data._sess = lambda: SlowSession()
    psx_data._next_slot[0] = 0
    try:
        deadline = time.monotonic() + 0.05
        try:
            psx_data.eod_history("NEAR", deadline=deadline)
        except psx_data.DeadlineExceeded:
            pass
        else:
            raise AssertionError("near-deadline call was not classified as skipped")
    finally:
        psx_data._sess = original_session
        psx_data._next_slot[0] = original_slot

    # Subtracting two monotonic floats can round a few ulps above the original budget.
    _assert(observed and 0 < observed[0] <= 0.05 + 1e-9,
            f"near-deadline request did not receive remaining budget: {observed}")


def check_throttle_and_backoff_are_shared():
    calls = []

    class RetrySession:
        def get(self, _url, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                return type("Response", (), {
                    "status_code": 429,
                    "headers": {},
                })()
            return type("Response", (), {
                "status_code": 200,
                "json": lambda self: {"data": [[172800, 12, 3, 11], [86400, 10, 2, 9]]},
            })()

    original_session = psx_data._sess
    original_slot = psx_data._next_slot[0]
    original_interval = psx_data._MIN_INTERVAL
    original_sleep = psx_data.time.sleep
    sleeps = []
    psx_data._sess = lambda: RetrySession()
    psx_data._next_slot[0] = 0
    psx_data._MIN_INTERVAL = 0.25
    psx_data.time.sleep = lambda seconds: sleeps.append(seconds)
    try:
        rows = psx_data.eod_history("RETRY", deadline=time.monotonic() + 10)
    finally:
        psx_data._sess = original_session
        psx_data._next_slot[0] = original_slot
        psx_data._MIN_INTERVAL = original_interval
        psx_data.time.sleep = original_sleep

    _assert(len(calls) == 2, f"shared provider retry path did not retry once: {calls}")
    _assert(len(rows) == 2 and rows[0]["date"] < rows[1]["date"],
            f"shared provider parser did not preserve oldest-first rows: {rows}")
    _assert(any(seconds >= 2 for seconds in sleeps),
            f"429 backoff was not applied: {sleeps}")
    _assert(any(abs(seconds - 0.25) < 0.01 for seconds in sleeps),
            f"shared throttle was not applied: {sleeps}")


def check_unfinished_future_is_not_accepted():
    deadline = time.monotonic() + 0.2

    def simulated_request(symbol):
        if symbol == "SLOW":
            time.sleep(0.4)
            return ("ok", None)
        return ("ok", None)

    started = time.monotonic()
    results = fetch_history._collect_results(["FAST", "SLOW"], simulated_request, deadline)
    elapsed = time.monotonic() - started
    accepted = {symbol for symbol, _result in results}

    _assert("FAST" in accepted, "completed result was not accepted before deadline")
    _assert("SLOW" not in accepted, "unfinished result was accepted as completed")
    _assert(elapsed < 0.5, f"unfinished request blocked beyond its budget: {elapsed:.3f}s")


if __name__ == "__main__":
    check_request_timeout_is_bounded()
    check_default_and_long_deadline_keep_20_second_cap()
    check_near_deadline_passes_remaining_budget()
    check_throttle_and_backoff_are_shared()
    check_unfinished_future_is_not_accepted()
    print("fetch_history deadline checks passed (cap, deadline, throttle/backoff, intake, failure)")
