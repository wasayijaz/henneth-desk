"""Global no-lookahead lint for emitted Company Intelligence JSON.

This checker is intentionally source-independent: it does not rebuild any CI
product or call upstream providers. It only compares explicit dates already
emitted in consumer-facing CI state against explicit product cutoffs.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CI_STATE_DIR = ROOT / "state" / "company_intel"
CI_SLICE = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
# The release receipt is an operator-verification record, not a generated
# investor-facing data artifact. Its timestamps describe verification activity,
# never economic source timing; its dedicated checker owns its schema.
NON_CONSUMER_ARTIFACT_NAMES = {"release_integrity_receipt.json"}

DATE_FIELD_NAMES = {
    "approved_at",
    "as_of",
    "available_at",
    "available_on",
    "baseline_date",
    "built",
    "completed_at",
    "data_cutoff",
    "date",
    "detected_at",
    "document_published_at",
    "document_retrieved_at",
    "effective_date",
    "endpoint_date",
    "fetched",
    "first_seen_at",
    "fundamentals_as_of",
    "last_changed_at",
    "last_completed_at",
    "latest_change_at",
    "latest_detected_at",
    "latest_event_at",
    "latest_price_as_of",
    "latest_source_at",
    "max_published_at",
    "observed_at",
    "period_end",
    "price_as_of",
    "profile_updated",
    "published_at",
    "published_on",
    "retrieved_at",
    "selected_date",
    "source_as_of",
    "updated",
}

CUTOFF_FIELD_NAMES = {
    "as_of",
    "build_cutoff_at",
    "built",
    "data_cutoff",
    "last_completed_at",
    "profile_updated",
    "source_as_of",
    "updated",
}

ROOT_METADATA_FIELD_NAMES = {"_meta", "meta"}

IGNORED_DATE_FIELD_NAMES = {
    # Finalizer timestamps describe when the generated artifact was built. They
    # are deliberately not source-effective, source-published, or observed
    # facts, so they must never become economic event timing or a local cutoff.
    "build_cutoff_at",
    "generated_at",
    "candidate_date",
    "date_basis",
    "expected_completion",
    "expected_lag",
    "matched_text",
    "next_monitor_date",
    "precision",
    "required_date",
    "target_date",
}

# Event-review metadata deliberately carries dates in the future: these are
# retained calendar entries or a cadence-derived review window, not observed
# facts. Keep the exemption artifact-aware and path-specific so every other
# date (including source/provenance timestamps in the same artifact) remains
# subject to the normal cutoff check.
PROSPECTIVE_CALENDAR_CONTAINERS = {
    "known_events",
    "review_windows",
    "expected_reporting_window",
    "expected_reporting_windows",
    "targeted_triggers",
}
PROSPECTIVE_CALENDAR_DATE_KEYS = {"date"}

OPAQUE_EXAMPLE_LIMIT = 12


@dataclass(frozen=True)
class DatePoint:
    raw: str
    parsed_date: date
    parsed_datetime: datetime | None


@dataclass
class ScanStats:
    artifacts: int = 0
    compared: int = 0
    skipped_no_cutoff: int = 0
    skipped_opaque: int = 0
    skipped_ignored: int = 0
    failures: list[str] | None = None
    no_cutoff_examples: list[str] | None = None
    opaque_examples: list[str] | None = None

    def __post_init__(self) -> None:
        self.failures = []
        self.no_cutoff_examples = []
        self.opaque_examples = []

    def fail(self, message: str) -> None:
        assert self.failures is not None
        self.failures.append(message)

    def note_no_cutoff(self, path: str) -> None:
        self.skipped_no_cutoff += 1
        assert self.no_cutoff_examples is not None
        if len(self.no_cutoff_examples) < OPAQUE_EXAMPLE_LIMIT:
            self.no_cutoff_examples.append(path)

    def note_opaque(self, path: str, value: Any) -> None:
        self.skipped_opaque += 1
        assert self.opaque_examples is not None
        if len(self.opaque_examples) < OPAQUE_EXAMPLE_LIMIT:
            self.opaque_examples.append(f"{path}={value!r}")


def parse_date_point(value: Any) -> DatePoint | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            return DatePoint(text, date.fromisoformat(text), None)
        except ValueError:
            return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return DatePoint(text, parsed.date(), parsed)


def is_after(left: DatePoint, right: DatePoint) -> bool:
    if left.parsed_date != right.parsed_date:
        return left.parsed_date > right.parsed_date
    if left.parsed_datetime is None or right.parsed_datetime is None:
        return False
    left_dt = comparable_datetime(left.parsed_datetime)
    right_dt = comparable_datetime(right.parsed_datetime)
    return left_dt > right_dt


def comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def latest_date(points: Iterable[DatePoint]) -> DatePoint | None:
    latest: DatePoint | None = None
    for point in points:
        if latest is None or is_after(point, latest):
            latest = point
    return latest


def dotted(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def date_key_kind(key: str) -> str | None:
    lowered = key.lower()
    if lowered in IGNORED_DATE_FIELD_NAMES:
        return "ignored"
    if lowered in DATE_FIELD_NAMES:
        return "date"
    if lowered.endswith("_as_of"):
        return "date"
    if lowered.endswith("_at") or lowered.endswith("_on") or lowered.endswith("_date"):
        return "date"
    return None


def is_prospective_calendar_date(artifact: str, path: str, key: str, container: dict[str, Any] | None = None) -> bool:
    """Return whether *key* is an explicitly forward-looking calendar date.

    The deterministic event-review artifact and the generated CI slice both
    expose retained/derived future event dates. Their availability cutoff,
    source timestamps, and all unrelated fields must still be checked.
    """
    if key.lower() not in PROSPECTIVE_CALENDAR_DATE_KEYS:
        return False
    normalized_artifact = artifact.replace("\\", "/")
    normalized_path = path.replace("\\", "/")
    is_state_artifact = normalized_artifact.endswith(
        "state/company_intel/event_review_windows.json"
    )
    is_ci_slice_artifact = normalized_artifact.endswith(
        "Henneth Desk 2.CI.0/data/company_intelligence.json"
    )
    is_ci_slice_field = (
        is_ci_slice_artifact and ".event_review_windows." in f".{normalized_path}."
    )
    is_work_routing_trigger = (
        normalized_artifact.endswith("state/company_intel/work_routing_policy.json")
        and ".targeted_triggers[" in f".{normalized_path}"
        and isinstance(container, dict)
        and container.get("trigger_type") == "active_event_review_window"
    )
    if not (is_state_artifact or is_ci_slice_field or is_work_routing_trigger):
        return False
    # A date is prospective only when it belongs to one of the declared
    # event-review containers. This excludes arbitrary nested future dates.
    segments = normalized_path.replace("]", "").replace("[", ".").split(".")
    return any(segment in PROSPECTIVE_CALENDAR_CONTAINERS for segment in segments)


def cutoff_points_from(value: Any) -> list[DatePoint]:
    points: list[DatePoint] = []
    if isinstance(value, dict):
        for item in value.values():
            points.extend(cutoff_points_from(item))
    elif isinstance(value, list):
        for item in value:
            points.extend(cutoff_points_from(item))
    else:
        point = parse_date_point(value)
        if point is not None:
            points.append(point)
    return points


def node_cutoff(node: dict[str, Any]) -> DatePoint | None:
    points: list[DatePoint] = []
    for key, value in node.items():
        if key.lower() in CUTOFF_FIELD_NAMES or key.lower().endswith("_as_of"):
            points.extend(cutoff_points_from(value))
    return latest_date(points)


def artifact_cutoff(data: Any) -> DatePoint | None:
    if not isinstance(data, dict):
        return None
    points = cutoff_points_from({key: data[key] for key in CUTOFF_FIELD_NAMES if key in data})
    for key in ROOT_METADATA_FIELD_NAMES:
        if key in data:
            points.extend(cutoff_points_from(data[key]))
    return latest_date(points)


def identifier_for(node: dict[str, Any]) -> str | None:
    for key in (
        "event_id",
        "scenario_id",
        "fact_id",
        "alert_id",
        "watch_id",
        "delivery_id",
        "guidance_id",
        "guidance_record_id",
        "confidence_id",
        "thesis_id",
        "doc_id",
        "document_id",
        "symbol",
    ):
        value = node.get(key)
        if isinstance(value, str) and value:
            return f"{key}={value}"
    return None


def compare_against_cutoff(
    *,
    artifact: str,
    path: str,
    key: str,
    value: Any,
    cutoff: DatePoint | None,
    container: dict[str, Any] | None,
    stats: ScanStats,
) -> None:
    kind = date_key_kind(key)
    if kind is None:
        return
    field_path = dotted(path, key)
    if kind == "ignored":
        stats.skipped_ignored += 1
        return
    if is_prospective_calendar_date(artifact, path, key, container):
        # Forward-looking event dates are valid by contract; sibling
        # availability/provenance fields continue through this checker.
        return
    point = parse_date_point(value)
    if point is None:
        if value is not None:
            stats.note_opaque(f"{artifact}:{field_path}", value)
        return
    if cutoff is None:
        stats.note_no_cutoff(f"{artifact}:{field_path}")
        return
    stats.compared += 1
    if is_after(point, cutoff):
        stats.fail(
            f"{artifact}:{field_path} has {point.raw} after cutoff {cutoff.raw}"
        )


def check_local_ordering(artifact: str, path: str, node: dict[str, Any], stats: ScanStats) -> None:
    data_cutoff = parse_date_point(node.get("data_cutoff"))
    for key in ("selected_date", "endpoint_date", "effective_date", "detected_at", "published_at", "information_available_at"):
        point = parse_date_point(node.get(key))
        if data_cutoff is not None and point is not None:
            stats.compared += 1
            if is_after(point, data_cutoff):
                ident = identifier_for(node)
                suffix = f" ({ident})" if ident else ""
                stats.fail(
                    f"{artifact}:{path}.{key}{suffix} has {point.raw} after local data_cutoff {data_cutoff.raw}"
                )
    effective = parse_date_point(node.get("effective_date"))
    baseline = None
    baseline_node = node.get("baseline")
    if isinstance(baseline_node, dict):
        baseline = parse_date_point(baseline_node.get("selected_date"))
    info_cutoff = (
        parse_date_point(node.get("information_available_at"))
        or parse_date_point(node.get("detected_at"))
        or parse_date_point(node.get("published_at"))
        or effective
    )
    if info_cutoff is not None and baseline is not None:
        stats.compared += 1
        if not is_after(info_cutoff, baseline):
            ident = identifier_for(node)
            suffix = f" ({ident})" if ident else ""
            cutoff_name = (
                "information_available_at" if node.get("information_available_at")
                else ("detected_at" if node.get("detected_at")
                else ("published_at" if node.get("published_at")
                else "effective_date"))
            )
            stats.fail(
                f"{artifact}:{path}.baseline.selected_date{suffix} has {baseline.raw}; expected strictly before {cutoff_name} {info_cutoff.raw}"
            )


def scan_node(
    artifact: str,
    value: Any,
    path: str,
    inherited_cutoff: DatePoint | None,
    stats: ScanStats,
) -> None:
    if isinstance(value, dict):
        local_cutoff = node_cutoff(value) or inherited_cutoff
        check_local_ordering(artifact, path, value, stats)
        for key, item in value.items():
            comparison_cutoff = inherited_cutoff if key.lower() in CUTOFF_FIELD_NAMES else local_cutoff
            if not isinstance(item, (dict, list)):
                compare_against_cutoff(
                    artifact=artifact,
                    path=path,
                    key=key,
                    value=item,
                    cutoff=comparison_cutoff,
                    container=value,
                    stats=stats,
                )
            scan_node(artifact, item, dotted(path, key), local_cutoff, stats)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_node(artifact, item, f"{path}[{index}]", inherited_cutoff, stats)


def artifact_paths() -> list[Path]:
    if not CI_STATE_DIR.exists():
        raise FileNotFoundError(f"missing CI state directory: {CI_STATE_DIR}")
    paths = [
        path for path in sorted(CI_STATE_DIR.glob("*.json"))
        if path.name not in NON_CONSUMER_ARTIFACT_NAMES
    ]
    if CI_SLICE.exists():
        paths.append(CI_SLICE)
    else:
        raise FileNotFoundError(f"missing CI slice: {CI_SLICE}")
    return paths


def scan_artifact(path: Path, stats: ScanStats) -> None:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    stats.artifacts += 1
    artifact = str(path.relative_to(ROOT)).replace("\\", "/")
    root_cutoff = artifact_cutoff(data)
    scan_node(artifact, data, "", root_cutoff, stats)


def run_scan(paths: Iterable[Path] | None = None) -> ScanStats:
    stats = ScanStats()
    for path in paths or artifact_paths():
        scan_artifact(path, stats)
    return stats


def run_self_tests() -> None:
    passing = {
        "as_of": "2026-01-10T18:00:00+05:00",
        "events": [
            {
                "event_id": "evt_pass",
                "detected_at": "2026-01-10T12:00:00+05:00",
                "effective_date": "2026-01-09",
                "baseline": {"selected_date": "2026-01-08"},
            },
            {
                "event_id": "evt_published_later_pass",
                "effective_date": "2025-06-30",
                "information_available_at": "2025-10-02",
                "baseline": {"selected_date": "2025-10-01"},
            },
        ],
        "studies": {
            "evt_pass": {
                "event_id": "evt_pass",
                "data_cutoff": "2026-01-10",
                "selected_date": "2026-01-10",
            }
        },
    }
    stats = ScanStats()
    scan_node("fixture/pass.json", passing, "", node_cutoff(passing), stats)
    if stats.failures:
        raise AssertionError(f"passing fixture failed: {stats.failures}")
    if stats.compared < 5:
        raise AssertionError("passing fixture did not exercise date comparisons")

    # Regression test: baseline equal to or after information availability must fail
    failing_info_baseline = {
        "as_of": "2026-01-10",
        "events": [
            {
                "event_id": "evt_info_leak",
                "effective_date": "2025-06-30",
                "information_available_at": "2025-10-02",
                "baseline": {"selected_date": "2025-10-02"},
            }
        ],
    }
    stats_fail = ScanStats()
    scan_node("fixture/fail_info.json", failing_info_baseline, "", node_cutoff(failing_info_baseline), stats_fail)
    if not stats_fail.failures:
        raise AssertionError("baseline equal to information availability date must fail")

    prospective_calendar = {
        "as_of": "2026-01-10",
        "event_review_windows": {
            "known_events": [{"event_id": "evt_future", "date": "2026-02-10"}],
            "expected_reporting_window": {"date": "2026-02-20"},
            "review_windows": [{"event_type": "results", "date": "2026-02-10"}],
        },
    }
    stats = ScanStats()
    scan_node(
        "state/company_intel/event_review_windows.json",
        prospective_calendar,
        "",
        node_cutoff(prospective_calendar),
        stats,
    )
    if stats.failures:
        raise AssertionError(f"prospective calendar fixture failed: {stats.failures}")

    ci_slice_calendar = {
        "as_of": "2026-01-10",
        "tickers": [
            {
                "event_review_windows": {
                    "known_events": [{"event_id": "evt_slice_future", "date": "2026-02-10"}],
                    "expected_reporting_window": {"date": "2026-02-20"},
                    "review_windows": [{"event_type": "results", "date": "2026-02-10"}],
                }
            }
        ],
    }
    stats = ScanStats()
    scan_node(
        "Henneth Desk 2.CI.0/data/company_intelligence.json",
        ci_slice_calendar,
        "",
        node_cutoff(ci_slice_calendar),
        stats,
    )
    if stats.failures:
        raise AssertionError(f"CI slice prospective calendar fixture failed: {stats.failures}")

    # The exemption is not a blanket allowance for dates in this artifact:
    # source/provenance timestamps and undeclared date fields must still fail.
    prospective_with_bad_provenance = {
        "as_of": "2026-01-10",
        "event_review_windows": {
            "known_events": [
                {
                    "event_id": "evt_bad_source",
                    "date": "2026-02-10",
                    "source_as_of": "2026-01-11",
                }
            ],
            "audit": {"date": "2026-02-11"},
        },
    }
    stats = ScanStats()
    scan_node(
        "state/company_intel/event_review_windows.json",
        prospective_with_bad_provenance,
        "",
        node_cutoff(prospective_with_bad_provenance),
        stats,
    )
    if len(stats.failures) != 2:
        raise AssertionError(
            "prospective calendar exemption weakened provenance/un-declared date checks"
        )

    failing = {"as_of": "2026-01-10", "alerts": [{"alert_id": "alert_fail", "date": "2026-01-11"}]}
    stats = ScanStats()
    scan_node("fixture/fail.json", failing, "", node_cutoff(failing), stats)
    if not stats.failures:
        raise AssertionError("failing fixture did not report future alert date")

    no_date = {
        "events": [{"event_id": "evt_no_cutoff", "date": "2026-01-11"}],
        "schedule": {"target_date": "2030-01-01"},
        "notes": [{"available_at": "not a date"}],
    }
    stats = ScanStats()
    scan_node("fixture/no-date.json", no_date, "", node_cutoff(no_date), stats)
    if stats.failures:
        raise AssertionError(f"no-date fixture should lint-only, got: {stats.failures}")
    if stats.skipped_no_cutoff != 1 or stats.skipped_opaque != 1 or stats.skipped_ignored != 1:
        raise AssertionError(
            "no-date fixture did not exercise no-cutoff, opaque, and ignored-date paths"
        )


def print_summary(stats: ScanStats) -> None:
    print(
        "ci_global_no_lookahead: "
        f"{'FAIL' if stats.failures else 'PASS'} "
        f"({stats.artifacts} artifacts, {stats.compared} date comparisons, "
        f"{stats.skipped_no_cutoff} no-cutoff skips, "
        f"{stats.skipped_opaque} opaque skips, {stats.skipped_ignored} ignored-date skips)"
    )
    if stats.no_cutoff_examples:
        print("  no-cutoff examples:")
        for example in stats.no_cutoff_examples:
            print(f"    - {example}")
    if stats.opaque_examples:
        print("  opaque examples:")
        for example in stats.opaque_examples:
            print(f"    - {example}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run only isolated fixture checks")
    args = parser.parse_args()

    try:
        run_self_tests()
        if args.self_test:
            print("ci_global_no_lookahead self-test: PASS")
            return 0
        stats = run_scan()
    except Exception as exc:
        print(f"ci_global_no_lookahead: FAIL ({exc})", file=sys.stderr)
        return 1
    print_summary(stats)
    if stats.failures:
        for failure in stats.failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
