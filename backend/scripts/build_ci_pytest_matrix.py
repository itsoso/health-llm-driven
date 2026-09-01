#!/usr/bin/env python3
"""Build a deterministic, timing-balanced GitHub Actions pytest matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / ".github" / "ci" / "backend-pytest-shards.json"


def load_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    shards = payload.get("shards")
    if not isinstance(shards, list) or not shards:
        raise ValueError("pytest shard catalog must contain a non-empty shards list")
    return shards


def balance_shards(
    shards: Sequence[dict[str, Any]], *, worker_count: int
) -> list[dict[str, Any]]:
    """Assign isolated pytest processes using deterministic LPT bin packing."""
    if worker_count < 1:
        raise ValueError("worker_count must be at least 1")

    labels = [str(shard.get("label") or "") for shard in shards]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate shard label")
    if not all(labels):
        raise ValueError("every shard requires a label")

    worker_count = min(worker_count, len(shards))
    bins: list[dict[str, Any]] = [
        {"labels": [], "seconds": 0.0} for _ in range(worker_count)
    ]
    ordered = sorted(
        shards,
        key=lambda shard: (
            -float(shard.get("estimated_seconds", 1.0)),
            str(shard["label"]),
        ),
    )
    for shard in ordered:
        target = min(
            enumerate(bins),
            key=lambda item: (item[1]["seconds"], item[0]),
        )[1]
        target["labels"].append(str(shard["label"]))
        target["seconds"] += float(shard.get("estimated_seconds", 1.0))

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
