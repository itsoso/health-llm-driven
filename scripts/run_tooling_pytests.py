#!/usr/bin/env python3
"""Run a supplemental fast lane for repository tooling tests."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TESTS = (
    "backend/tests/test_agent_skill_governance.py",
    "backend/tests/test_agent_skill_manifests.py",
    "backend/tests/test_doc_drift_narrative_counts.py",
    "backend/tests/test_doc_drift_skill_contract.py",
    "backend/tests/test_dossier_consistency.py",
    "backend/tests/test_reva_health_harness_plugin_package.py",
    "backend/tests/test_system_map_agent_context.py",
    "backend/tests/test_system_map_generator.py",
)
BENCHMARK_TEST = "backend/tests/test_agent_skill_benchmark.py"
SUPPLEMENTAL_SCOPE = (
    "This supplemental runner skips coverage and does not replace regular project "
    "tests or CI gates."
)

PYTEST_OPTIONS = (
    "--noconftest",
    "-c",
    os.devnull,
    "--rootdir",
    str(ROOT),
    "-o",
    "addopts=",
    "-q",
    "--strict-markers",
    "--tb=short",
    "-p",
    "no:cacheprovider",
    "-p",
    "scripts.tooling_pytest_guard",
)


def build_command(*, include_benchmark: bool) -> list[str]:
    tests = [*DEFAULT_TESTS]
    if include_benchmark:
        tests.append(BENCHMARK_TEST)
    return [sys.executable, "-m", "pytest", *PYTEST_OPTIONS, *tests]


def sanitized_environment(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ if environ is None else environ)
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTEST_PLUGINS", None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, epilog=SUPPLEMENTAL_SCOPE)
    parser.add_argument(
        "--include-benchmark",
        action="store_true",
        help="include the agent Skill benchmark contract tests",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    completed = subprocess.run(
        build_command(include_benchmark=args.include_benchmark),
        cwd=ROOT,
        env=sanitized_environment(),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
