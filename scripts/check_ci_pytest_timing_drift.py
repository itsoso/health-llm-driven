#!/usr/bin/env python3
"""Assess backend pytest placement drift from one exact successful CI run.

This tool is deliberately read-only. It consumes reviewed local metadata and
writes a diagnostic report; it cannot update the catalog or authorize release.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys


WORKER_NAME = re.compile(r"backend-test-balanced-([0-9]{2})")


def _read_json(path: Path):
    with path.open("rb") as stream:
        raw = stream.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError("input exceeds size bound")
    return json.loads(raw)


def _positive_int(value) -> bool:
    return type(value) is int and value > 0


def _positive_seconds(value) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("scheduling seconds must be positive and finite")
    return float(value)


def _policy(catalog: dict) -> dict:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("shards"), list):
        raise ValueError("invalid catalog")
    value = copy.deepcopy({key: item for key, item in catalog.items() if key != "timing_source"})
    labels = []
    for shard in value["shards"]:
        if not isinstance(shard, dict):
            raise ValueError("invalid shard")
        labels.append(shard.get("label"))
        shard.pop("scheduling_seconds", None)
    if any(not isinstance(label, str) or not label for label in labels) or len(labels) != len(set(labels)):
        raise ValueError("invalid shard labels")
    return value


def _timings(catalog: dict) -> dict[str, float]:
    values = {}
    for shard in catalog.get("shards", []):
        label = shard.get("label")
        if not isinstance(label, str) or label in values:
            raise ValueError("invalid timing labels")
        values[label] = _positive_seconds(shard.get("scheduling_seconds"))
    if not values:
        raise ValueError("empty timing catalog")
    return values


def _source_run_ids(catalog: dict) -> set[int]:
    source = catalog.get("timing_source")
    if not isinstance(source, dict):
        raise ValueError("timing source required")
    rows = source.get("runs")
    if rows is None:
        rows = [source]
    if not isinstance(rows, list) or not rows:
        raise ValueError("timing source runs required")
    run_ids = [row.get("run_id") for row in rows if isinstance(row, dict)]
    if len(run_ids) != len(rows) or any(not _positive_int(run_id) for run_id in run_ids):
        raise ValueError("invalid timing source run")
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("duplicate timing source run")
    return set(run_ids)


def _assign(labels: dict[str, float], worker_count: int) -> list[list[str]]:
    if not _positive_int(worker_count):
        raise ValueError("worker count must be positive")
    bins = [{"labels": [], "seconds": 0.0} for _ in range(min(worker_count, len(labels)))]
    for label, seconds in sorted(labels.items(), key=lambda row: (-row[1], row[0])):
        target = min(enumerate(bins), key=lambda row: (row[1]["seconds"], row[0]))[1]
        target["labels"].append(label)
        target["seconds"] += seconds
    return [row["labels"] for row in bins]


def successful_full_run_ids(runs: list, jobs_by_run: dict[int, dict]) -> list[int]:
    if not isinstance(runs, list) or not 0 < len(runs) <= 100:
        raise ValueError("bounded run inventory required")
    accepted = []
    seen = set()
    expected = {f"backend-test-balanced-{index:02d}" for index in range(1, 17)}
    for run in runs:
        if not isinstance(run, dict) or not _positive_int(run.get("databaseId")):
            raise ValueError("invalid run inventory")
        run_id = run["databaseId"]
        if run_id in seen:
            raise ValueError("duplicate run inventory")
        seen.add(run_id)
        sha = run.get("headSha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("invalid run sha")
        if not (
            run.get("workflowName") == "CI"
            and run.get("headBranch") == "main"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and run.get("attempt") == 1
        ):
            continue
        inventory = jobs_by_run.get(run_id)
        if not isinstance(inventory, dict) or not isinstance(inventory.get("jobs"), list):
            raise ValueError("missing job inventory")
        if inventory.get("total_count") != len(inventory["jobs"]):
            raise ValueError("incomplete job inventory")
        workers = [job for job in inventory["jobs"] if job.get("name") in expected]
        if {job.get("name") for job in workers} != expected or len(workers) != len(expected):
            continue
        if not all(
            job.get("conclusion") == "success"
            and job.get("run_attempt") == 1
            and job.get("run_id") == run_id
            and job.get("head_sha") == sha
            for job in workers
        ):
            continue
        accepted.append(run_id)
    return sorted(accepted, reverse=True)


def assess(
    catalog: dict,
    observed: dict,
    *,
    successful_full_run_ids: list[int],
    current_run_id: int,
    current_head_sha: str,
    worker_count: int,
    max_slower_ratio: float,
    max_runs_since_source: int,
) -> dict:
    if _policy(catalog) != _policy(observed):
        raise ValueError("execution policy changed")
    if not _positive_int(current_run_id):
        raise ValueError("invalid current run")
    if catalog.get("worker_count") != worker_count or observed.get("worker_count") != worker_count:
        raise ValueError("worker count does not match catalog policy")
    if not isinstance(current_head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", current_head_sha):
        raise ValueError("invalid current run sha")
    observed_source = observed.get("timing_source")
    if (
        not isinstance(observed_source, dict)
        or _source_run_ids(observed) != {current_run_id}
        or observed_source.get("run_id") != current_run_id
        or observed_source.get("head_sha") != current_head_sha
    ):
        raise ValueError("observed timing source is not bound to current run")
    if (
        isinstance(max_slower_ratio, bool)
        or not isinstance(max_slower_ratio, (int, float))
        or not math.isfinite(max_slower_ratio)
        or max_slower_ratio < 0
    ):
        raise ValueError("invalid drift threshold")
    if not _positive_int(max_runs_since_source):
        raise ValueError("invalid staleness threshold")
    run_ids = successful_full_run_ids
    if (
        not isinstance(run_ids, list)
        or current_run_id not in run_ids
        or any(not _positive_int(run_id) for run_id in run_ids)
        or len(run_ids) != len(set(run_ids))
    ):
        raise ValueError("current run missing from successful full run inventory")
    run_ids = sorted(run_ids, reverse=True)
    bounded = run_ids[run_ids.index(current_run_id) :]
    source_run_ids = _source_run_ids(catalog)
    source_positions = [index for index, run_id in enumerate(bounded) if run_id in source_run_ids]
    runs_since_source = min(source_positions) if source_positions else len(bounded)

    predicted = _timings(catalog)
    actual = _timings(observed)
    if predicted.keys() != actual.keys():
        raise ValueError("timing labels changed")
    assignments = _assign(predicted, worker_count)
    predicted_loads = [sum(predicted[label] for label in labels) for labels in assignments]
    observed_loads = [sum(actual[label] for label in labels) for labels in assignments]
    predicted_critical = max(predicted_loads)
    observed_critical = max(observed_loads)
    slower_ratio = observed_critical / predicted_critical - 1.0
    shard_ratios = [actual[label] / predicted[label] - 1.0 for label in predicted]
    drift_exceeded = slower_ratio > float(max_slower_ratio)
    catalog_stale = not source_positions or runs_since_source >= max_runs_since_source
    return {
        "schema_version": "ci_pytest_timing_drift.v1",
        "release_authority": False,
        "current_run_id": current_run_id,
        "current_head_sha": current_head_sha,
        "catalog_source_run_ids": sorted(source_run_ids),
        "successful_full_run_ids": bounded,
        "worker_count": worker_count,
        "predicted_critical_seconds": round(predicted_critical, 3),
        "observed_critical_seconds": round(observed_critical, 3),
        "slower_ratio": round(slower_ratio, 6),
        "largest_shard_slower_ratio": round(max(shard_ratios), 6),
        "runs_since_source": runs_since_source,
        "max_slower_ratio": float(max_slower_ratio),
        "max_runs_since_source": max_runs_since_source,
        "drift_exceeded": drift_exceeded,
        "catalog_stale": catalog_stale,
        "status": "REVIEW_REQUIRED" if drift_exceeded or catalog_stale else "CURRENT",
        "limitations": [
            "single observed run is not a stable latency percentile",
            "start delay, dependency installation and runner overhead are excluded",
            "the report cannot update the catalog, push code or authorize release",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--current-run-id", type=int, required=True)
    parser.add_argument("--recent-runs", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--max-slower-ratio", type=float, default=0.20)
    parser.add_argument("--max-runs-since-source", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        runs = _read_json(args.recent_runs)
        jobs = {
            run["databaseId"]: _read_json(args.jobs_dir / f"{run['databaseId']}.json")
            for run in runs
        }
        full_run_ids = successful_full_run_ids(runs, jobs)
        current_rows = [run for run in runs if run.get("databaseId") == args.current_run_id]
        if len(current_rows) != 1:
            raise ValueError("current run metadata missing")
        report = assess(
            _read_json(args.catalog),
            _read_json(args.observed),
            successful_full_run_ids=full_run_ids,
            current_run_id=args.current_run_id,
            current_head_sha=current_rows[0].get("headSha"),
            worker_count=args.workers,
            max_slower_ratio=args.max_slower_ratio,
            max_runs_since_source=args.max_runs_since_source,
        )
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        print("Timing evidence rejected; supply complete exact-run metadata.", file=sys.stderr)
        return 1
    if report["status"] != "CURRENT":
        print("Timing catalog review required; inspect the uploaded report.", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
