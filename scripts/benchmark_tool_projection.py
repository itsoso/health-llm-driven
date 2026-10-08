#!/usr/bin/env python3
"""Synthetic local CPU benchmark of public tool-guide reuse; no model calls."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.agent_kernel.read_task_scope import OwnedReadScope

CURRENT = ROOT / "backend/app/services/agent_tool_prompt_projection.py"
BASELINE = ROOT / "backend/tests/fixtures/tool_projection_7d934b3.py"
BASELINE_HASH = "054fd897fd4c3964dbe1154f5ae0c6fb8ee813a220f755b741e63f4be6df43d1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset(module):
    for helper in (module._query_description, module._batch_description):
        if hasattr(helper, "cache_clear"):
            helper.cache_clear()


def quantiles(values):
    ordered = sorted(values)
    return {"p50_ms": statistics.median(ordered),
            "p95_ms": ordered[math.ceil(len(ordered) * .95) - 1],
            "p99_ms": ordered[math.ceil(len(ordered) * .99) - 1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=101)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    if not 21 <= args.samples <= 1001 or not 1 <= args.iterations <= 1000:
        parser.error("samples must be 21..1001; iterations must be 1..1000")
    assert digest(BASELINE) == BASELINE_HASH, "Frozen baseline changed"
    original, current = load(BASELINE), load(CURRENT)
    rows = []
    for dimensions in [("sleep",), ("diet",), ("sleep", "diet"), ("sleep", "spo2"),
                       ("sleep", "spo2", "diet", "workout", "supplements"), ("unknown",)]:
        tools = deepcopy(original.HEALTH_TOOLS)
        before = deepcopy(tools)
        scope = OwnedReadScope(tuple({"dimension": dimension, "days": 7} for dimension in dimensions))
        expected = original.project_owned_read_tool_descriptions(tools, scope)
        reset(current)
        assert current.project_owned_read_tool_descriptions(tools, scope) == expected
        elapsed = {key: [] for key in ("baseline", "warm", "cold")}
        for sample in range(args.samples):
            pair = [("baseline", original), ("warm", current)]
            if sample % 2:
                pair.reverse()
            for label, module in pair:
                # Each block starts warm; cold insertion is measured separately.
                module.project_owned_read_tool_descriptions(tools, scope)
                started = time.perf_counter_ns()
                for _ in range(args.iterations):
                    actual = module.project_owned_read_tool_descriptions(tools, scope)
                elapsed[label].append((time.perf_counter_ns() - started) / args.iterations / 1e6)
                assert actual == expected and tools == before
            reset(current)
            started = time.perf_counter_ns()
            actual = current.project_owned_read_tool_descriptions(tools, scope)
            elapsed["cold"].append((time.perf_counter_ns() - started) / 1e6)
            assert actual == expected and tools == before
        row = {"dimensions": dimensions, "samples_ms": elapsed, "provider_payload_identical": True,
               **{key: quantiles(values) for key, values in elapsed.items()}}
        row["warm_p50_reduction_pct"] = round(100 * (1 - row["warm"]["p50_ms"] / row["baseline"]["p50_ms"]), 2)
        rows.append(row)
    warm_pass = all(row["warm_p50_reduction_pct"] >= 25 for row in rows[:-1])
    tail_pass = all(row["warm"]["p95_ms"] <= row["baseline"]["p95_ms"] * 1.1 + .01 for row in rows)
    cold_pass = all(row["cold"]["p95_ms"] <= row["baseline"]["p95_ms"] * 1.2 + .02 for row in rows)
    report = {"status": "local_target_met" if warm_pass and tail_pass and cold_pass else "local_target_not_met",
              "baseline_ref": "7d934b3c6", "source_sha256": {
                  str(path.relative_to(ROOT)): digest(path) for path in (BASELINE, CURRENT, Path(__file__),
                      ROOT / "backend/app/services/tool_schema_registry.py")},
              "environment": {"python": platform.python_version(), "platform": platform.system(), "machine": platform.machine()},
              "samples": args.samples, "iterations_per_warm_sample": args.iterations,
              "pair_order": "alternating baseline/warm and warm/baseline; cold one call after each pair",
              "local_target": {"warm_p50_at_least_25_percent_faster": warm_pass,
                               "warm_p95_within_10_percent_plus_0_01_ms": tail_pass,
                               "cold_p95_within_20_percent_plus_0_02_ms": cold_pass},
              "rows": rows,
              "limits": ["Synthetic local function CPU; no real traffic baseline or end-to-end latency.",
                         "Warm quantiles are batch means; cold quantiles are single calls excluding cache_clear.",
                         "Identical provider input; no new token savings or model noninferiority claim."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(rows)}))
    return 0 if report["status"] == "local_target_met" else 2


if __name__ == "__main__":
    raise SystemExit(main())
