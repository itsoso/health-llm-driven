#!/usr/bin/env python3
"""Build a deterministic, timing-balanced GitHub Actions pytest matrix."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / ".github" / "ci" / "backend-pytest-shards.json"


def scheduling_seconds(shard: dict[str, Any]) -> float:
    """Measured process time affects placement, never the worker's deadline."""
    value = shard.get("scheduling_seconds", shard.get("estimated_seconds", 1.0))
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("scheduling seconds must be a positive finite number")
    return float(value)


def _validate_shards(shards: Sequence[dict[str, Any]]) -> None:
    if not shards or any(not isinstance(shard, dict) for shard in shards):
        raise ValueError("pytest shard catalog requires shard objects")
    labels = [shard.get("label") for shard in shards]
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError("every shard requires a non-empty string label")
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate shard label")
    for shard in shards:
        scheduling_seconds(shard)


def load_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pytest shard catalog must be an object")
    shards = payload.get("shards")
    if not isinstance(shards, list) or not shards:
        raise ValueError("pytest shard catalog must contain a non-empty shards list")
    _validate_shards(shards)
    if "timing_source" in payload or any("scheduling_seconds" in shard for shard in shards):
        source = payload.get("timing_source")
        if not isinstance(source, dict):
            raise ValueError("measured scheduling requires timing_source provenance")
        if (
            any("scheduling_seconds" not in shard for shard in shards)
            or type(source.get("sample_count")) is not int
            or source["sample_count"] != len(shards)
        ):
            raise ValueError("timing source must cover every shard exactly once")
        if type(source.get("run_id")) is not int or source["run_id"] <= 0:
            raise ValueError("timing source requires a positive run_id")
        if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("head_sha", ""))):
            raise ValueError("timing source requires a full head_sha")
        if source.get("measurement") != "successful_attempt_process_wall_seconds":
            raise ValueError("timing source must measure successful attempt process wall time")
        excluded = source.get("excluded_timeout_seconds")
        if (
            isinstance(excluded, bool)
            or not isinstance(excluded, (int, float))
            or not math.isfinite(excluded)
            or excluded < 0
        ):
            raise ValueError("excluded timeout seconds must be non-negative and finite")
    return shards


def balance_shards(
    shards: Sequence[dict[str, Any]], *, worker_count: int
) -> list[dict[str, Any]]:
    """Assign isolated pytest processes using deterministic LPT bin packing."""
    if worker_count < 1:
        raise ValueError("worker_count must be at least 1")

    _validate_shards(shards)

    worker_count = min(worker_count, len(shards))
    bins: list[dict[str, Any]] = [
        {"labels": [], "seconds": 0.0} for _ in range(worker_count)
    ]
    ordered = sorted(
        shards,
        key=lambda shard: (
            -scheduling_seconds(shard),
            str(shard["label"]),
        ),
    )
    for shard in ordered:
        target = min(
            enumerate(bins),
            key=lambda item: (item[1]["seconds"], item[0]),
        )[1]
        target["labels"].append(str(shard["label"]))
        target["seconds"] += scheduling_seconds(shard)

    return [
        {
            "label": f"balanced-{index:02d}",
            "shards": ",".join(worker["labels"]),
            "estimated_seconds": round(worker["seconds"], 3),
        }
        for index, worker in enumerate(bins, start=1)
    ]


def build_matrix(catalog: Path, worker_count: int) -> dict[str, Any]:
    return {"include": balance_shards(load_catalog(catalog), worker_count=worker_count)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)

    matrix = json.dumps(
        build_matrix(args.catalog, args.workers),
        sort_keys=True,
        separators=(",", ":"),
    )
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"matrix={matrix}\n")
    else:
        print(matrix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
