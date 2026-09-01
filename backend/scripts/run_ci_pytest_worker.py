#!/usr/bin/env python3
"""Run several timing-balanced pytest shards while preserving process isolation."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from glob import glob, has_magic
import json
import math
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.build_ci_pytest_matrix import DEFAULT_CATALOG, load_catalog
    from scripts.run_ci_pytest_shard import instrument_pytest_args, run_shard
except ModuleNotFoundError:  # Direct execution from backend/scripts.
    from build_ci_pytest_matrix import DEFAULT_CATALOG, load_catalog
    from run_ci_pytest_shard import instrument_pytest_args, run_shard


MIN_SHARD_TIMEOUT_SECONDS = 180
MAX_SHARD_TIMEOUT_SECONDS = 600
SHARD_TIMEOUT_MULTIPLIER = 3.0


BASE_PYTEST_ARGS = [
    "-q",
    "--no-cov",
    "--tb=short",
    "--maxfail=5",
    "--timeout=120",
    "--timeout-method=signal",
]


def expand_path_inputs(
    path_inputs: Sequence[str],
    *,
    cwd: Path,
    exclude_paths: Sequence[str] = (),
) -> list[str]:
    """Expand shell-style file globs without interpreting pytest node IDs."""
    expanded: list[str] = []
    for path_input in path_inputs:
        if "::" in path_input or not has_magic(path_input):
            expanded.append(path_input)
            continue
        matches = sorted(glob(str(cwd / path_input)))
        if not matches:
            raise ValueError(f"pytest path pattern matched no files: {path_input}")
        expanded.extend(str(Path(match).relative_to(cwd)) for match in matches)
    excluded = set(expand_path_inputs(exclude_paths, cwd=cwd)) if exclude_paths else set()
    return [path for path in expanded if path not in excluded]


def shard_timeout_seconds(shard: dict[str, Any]) -> int:
    """Derive a bounded process deadline from historical shard wall time."""

    explicit = shard.get("timeout_seconds")
    if explicit is not None:
        timeout_seconds = int(explicit)
    else:
        estimated_seconds = float(shard.get("estimated_seconds", 1.0))
        if estimated_seconds < 0:
            raise ValueError("estimated_seconds must not be negative")
        timeout_seconds = math.ceil(estimated_seconds * SHARD_TIMEOUT_MULTIPLIER)
        timeout_seconds = max(MIN_SHARD_TIMEOUT_SECONDS, timeout_seconds)
        timeout_seconds = min(MAX_SHARD_TIMEOUT_SECONDS, timeout_seconds)
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1")
    return timeout_seconds


def run_worker(
    labels: Sequence[str],
    catalog: Sequence[dict[str, Any]],
    *,
    cwd: Path,
    junit_dir: Path,
    shard_runner: Callable[..., int] = run_shard,
) -> int:
    by_label = {str(shard["label"]): shard for shard in catalog}
    unknown = [label for label in labels if label not in by_label]
    if unknown:
        raise ValueError(f"unknown pytest shard labels: {', '.join(unknown)}")

    junit_dir.mkdir(parents=True, exist_ok=True)
    for label in labels:
        shard = by_label[label]
        paths = expand_path_inputs(
            shard["paths"],
            cwd=cwd,
            exclude_paths=shard.get("exclude_paths", []),
        )
        pytest_args = [*BASE_PYTEST_ARGS, *shard.get("extra_args", [])]
        pytest_args = instrument_pytest_args(
            pytest_args,
            junit_path=str(junit_dir / f"{label}.xml"),
        )
        try:
            timeout_seconds = shard_timeout_seconds(shard)
        except ValueError as exc:
            raise ValueError(f"{label} {exc}") from exc
        print(
            "[ci-worker] "
            + json.dumps(
                {
                    "shard": label,
                    "paths": len(paths),
                    "deadline_seconds": timeout_seconds,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        return_code = shard_runner(
            paths,
            pytest_args,
            timeout_seconds=timeout_seconds,
        )
        if return_code != 0:
            return return_code
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--junit-dir", type=Path, default=Path("test-results"))
    args = parser.parse_args(argv)
    labels = [label.strip() for label in args.shards.split(",") if label.strip()]
    if not labels:
        parser.error("--shards must contain at least one label")
    try:
        return run_worker(
            labels,
            load_catalog(args.catalog),
            cwd=Path.cwd(),
            junit_dir=args.junit_dir,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
