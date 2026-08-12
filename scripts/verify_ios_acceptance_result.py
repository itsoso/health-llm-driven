#!/usr/bin/env python3
"""Fail closed when an iOS acceptance result hides unexpected skipped tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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
    allowed_skips: set[str],
) -> tuple[int, int]:
    cases: list[dict[str, Any]] = []
    for node in tests.get("testNodes", []):
        cases.extend(_test_cases(node))

    failed = [case for case in cases if case.get("result") == "Failed"]
    skipped = [case for case in cases if case.get("result") == "Skipped"]
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

    reported_total = int(summary.get("totalTestCount", 0))
    if reported_total != len(cases):
        raise ValueError(
            f"iOS acceptance test count mismatch: summary={reported_total}, cases={len(cases)}"
        )
    return int(summary.get("passedTests", 0)), len(skipped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--allow-skip", action="append", default=[])
    args = parser.parse_args()

    try:
        passed, skipped = verify(
            _load_object(args.summary),
            _load_object(args.tests),
            set(args.allow_skip),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"iOS acceptance verification failed: {exc}", file=sys.stderr)
        return 1

    suffix = "skip" if skipped == 1 else "skips"
    print(f"iOS acceptance verified: {passed} passed, {skipped} allowed {suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
