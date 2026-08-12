#!/usr/bin/env python3
"""Fail closed when an iOS acceptance result hides unexpected skipped tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_TESTS = frozenset(
    {
        "testInstalledBuildLaunchesExpectedEntrySurface()",
        "test00AuthenticatedSessionPersistsAcrossTwoColdLaunches()",
        "testConversationOpensAtLatestSeededMessage()",
        "testTodayContextCanOpenAndDismiss()",
        "testDraftSurvivesBackgroundWithoutSending()",
        "testPrivacyAndAccountDeletionEntriesAreReachable()",
        "testGPSAutoRefreshPublishesCityAndReadyState()",
        "testProductionSettingsEntriesOpenAndReturn()",
    }
)
GPS_TEST = "testGPSAutoRefreshPublishesCityAndReadyState()"


def _test_cases(node: Any) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    cases = [node] if node.get("nodeType") == "Test Case" else []
    for child in node.get("children", []):
        cases.extend(_test_cases(child))
    return cases


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify(
    summary: dict[str, Any],
    tests: dict[str, Any],
    *,
    platform: str,
    expected_city: str,
) -> tuple[int, int]:
    cases: list[dict[str, Any]] = []
    for node in tests.get("testNodes", []):
        cases.extend(_test_cases(node))

    if not cases:
        raise ValueError("iOS acceptance contains zero tests")

    names = [str(case.get("name", "<unnamed>")) for case in cases]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    observed = set(names)
    missing = sorted(EXPECTED_TESTS - observed)
    unexpected = sorted(observed - EXPECTED_TESTS)
    if missing or unexpected or duplicates:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected))
        if duplicates:
            details.append("duplicate: " + ", ".join(duplicates))
        raise ValueError("iOS acceptance test set mismatch (" + "; ".join(details) + ")")

    invalid_results = [
        f"{case.get('name', '<unnamed>')}={case.get('result', '<missing>')}"
        for case in cases
        if case.get("result") not in {"Passed", "Skipped", "Failed"}
    ]
    if invalid_results:
        raise ValueError(
            "iOS acceptance contains invalid test results: "
            + ", ".join(invalid_results)
        )

    failed = [case for case in cases if case.get("result") == "Failed"]
    skipped = [case for case in cases if case.get("result") == "Skipped"]
    allowed_skips = {GPS_TEST} if platform == "iOS" and not expected_city else set()
    unexpected_skips = [
        str(case.get("name", "<unnamed>"))
        for case in skipped
        if case.get("name") not in allowed_skips
    ]

    if summary.get("result") != "Passed" or summary.get("failedTests", 0) or failed:
        raise ValueError("iOS acceptance contains failed tests")
    if unexpected_skips:
        raise ValueError(
            "unexpected skipped iOS acceptance tests: " + ", ".join(unexpected_skips)
        )

    reported_total = int(summary.get("totalTestCount", -1))
    if reported_total != len(cases):
        raise ValueError(
            f"iOS acceptance test count mismatch: summary={reported_total}, cases={len(cases)}"
        )
    passed = sum(case.get("result") == "Passed" for case in cases)
    reported_passed = int(summary.get("passedTests", -1))
    reported_skipped = int(summary.get("skippedTests", -1))
    if reported_passed != passed or reported_skipped != len(skipped):
        raise ValueError(
            "iOS acceptance result count mismatch: "
            f"summary passed/skipped={reported_passed}/{reported_skipped}, "
            f"cases={passed}/{len(skipped)}"
        )
    return passed, len(skipped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--platform", choices=("iOS", "iOS Simulator"), required=True)
    parser.add_argument("--expected-city", default="")
    args = parser.parse_args()

    try:
        passed, skipped = verify(
            _load_object(args.summary),
            _load_object(args.tests),
            platform=args.platform,
            expected_city=args.expected_city.strip(),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"iOS acceptance verification failed: {exc}", file=sys.stderr)
        return 1

    suffix = "skip" if skipped == 1 else "skips"
    print(f"iOS acceptance verified: {passed} passed, {skipped} allowed {suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
