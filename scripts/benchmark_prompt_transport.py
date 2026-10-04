#!/usr/bin/env python3
"""Offline CPU benchmark of byte-equivalent tool-result transport.

Uses synthetic records and, optionally, synthetic Pi captures. No model/API/DB
calls, no captured contents in reports, and no API-token or end-to-end claims.
The reference fixture is the unmodified module from branch base 7d934b3c6.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import time

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "backend/tests/fixtures/prompt_transport_7d934b3.py"
REFERENCE_SHA256 = "a09fe0203c2748d76a82ad0cccae4ebf03db69d5edd5c86d251d0d087ee9d206"
CURRENT = ROOT / "backend/app/services/llm/prompt_transport.py"


def load_projection(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compact_tool_json


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workloads() -> dict[str, list[dict]]:
    cases = {}
    for size in (10, 100, 1000):
        data = {"records": [
            {"id": i, "label": '合成记录  保留空格\\n与\\"引号',
             "value": 1.23e-12, "missing": None}
            for i in range(size)
        ]}
        for layout in ("pretty", "compact"):
            text = json.dumps(data, ensure_ascii=False, indent=2) if layout == "pretty" else json.dumps(
                data, ensure_ascii=False, separators=(",", ":")
            )
            cases[f"records_{size}_{layout}"] = [{"role": "tool", "content": text}]
    for label, text in {
        "long_string": json.dumps({"text": "合成报告 保留  空格。\n" * 10000}, ensure_ascii=False, indent=2),
        "escape_dense": json.dumps({"text": '\\"\n\t' * 10000}, indent=2),
        "outside_whitespace": '{' + " \n\t\r" * 25000 + '"ok":true}',
        "numeric_lexemes": '[ 1.23000e-19, -0.0, ' + '9' * 6000 + ' ]',
        "invalid_constant": '{ "value": NaN }',
        "invalid_long_string": '{ "text": "' + '\\\\' * 20000,
    }.items():
        cases[label] = [{"role": "tool", "content": text}]
    cases["ordinary_prose"] = [{"role": "user", "content": '{ "keep": "my  words" }'},
                               {"role": "tool", "content": "Error: synthetic failure"}]
    return cases


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"p50_ms": statistics.median(ordered),
            "p95_ms": ordered[math.ceil(len(ordered) * .95) - 1],
            "p99_ms": ordered[math.ceil(len(ordered) * .99) - 1]}


def benchmark(cases, *, samples: int, iterations: int) -> list[dict]:
    if digest(REFERENCE) != REFERENCE_SHA256:
        raise ValueError("Frozen baseline differs from branch base")
    baseline, candidate = load_projection(REFERENCE), load_projection(CURRENT)
    rows = []
    for label, messages in cases.items():
        before = copy.deepcopy(messages)
        expected = baseline(messages)
        actual = candidate(messages)
        if expected != actual or messages != before:
            raise AssertionError(f"Non-equivalent or mutated input: {label}")
        for _ in range(10):
            baseline(messages)
            candidate(messages)
        elapsed = {"baseline": [], "candidate": []}
        for sample in range(samples):
            pair = [("baseline", baseline), ("candidate", candidate)]
            if sample % 2:
                pair.reverse()
            for name, project in pair:
                started = time.perf_counter_ns()
                for _ in range(iterations):
                    result = project(messages)
                elapsed[name].append((time.perf_counter_ns() - started) / iterations / 1e6)
                if result != expected or messages != before:
                    raise AssertionError(f"Unstable projection: {label}")
        row = {"case": label, "input_utf8_bytes": len(json.dumps(messages, ensure_ascii=False).encode()),
               "tool_messages": sum(message.get("role") == "tool" for message in messages),
               "output_identical": True, "input_unchanged": True,
               "samples_ms": elapsed,
               **{name: quantiles(values) for name, values in elapsed.items()}}
        row["p50_reduction_pct"] = round(100 * (1 - row["candidate"]["p50_ms"] / row["baseline"]["p50_ms"]), 2)
        row["p95_reduction_pct"] = round(100 * (1 - row["candidate"]["p95_ms"] / row["baseline"]["p95_ms"]), 2)
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=101)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--capture", action="append", default=[], metavar="NAME=PATH",
                        help="Only synthetic Pi captures in [{enabled,calls},...] format")
    args = parser.parse_args()
    if not 21 <= args.samples <= 1001 or not 1 <= args.iterations <= 100:
        parser.error("samples must be 21..1001; iterations must be 1..100")
    cases = workloads()
    captures = []
    for capture in args.capture:
        label, path = capture.split("=", 1)
        path = Path(path)
        for arm_index, arm in enumerate(json.loads(path.read_text())):
            for call_index, call in enumerate(arm["calls"]):
                cases[f"{label}_arm{arm_index}_call{call_index}"] = call["messages"]
        captures.append({"name": label, "sha256": digest(path)})
    rows = benchmark(cases, samples=args.samples, iterations=args.iterations)
    # Diagnostic microbenchmark thresholds, NOT a production or live quality gate.
    material = [row for row in rows if row["input_utf8_bytes"] >= 10000
                and row["case"].startswith("records_")]
    target_met = all(row["p50_reduction_pct"] >= 15 for row in material)
    # Sub-microsecond noise on passthrough paths should not dominate this check.
    no_tail_regression = all(row["candidate"]["p95_ms"] <= row["baseline"]["p95_ms"] * 1.1 + .02
                             for row in rows)
    report = {"status": "local_target_met" if target_met and no_tail_regression else "local_target_not_met",
              "baseline_ref": "7d934b3c6", "source_sha256": {
                  str(path.relative_to(ROOT)): digest(path) for path in (REFERENCE, CURRENT, Path(__file__))},
              "environment": {"python": platform.python_version(), "platform": platform.system(),
                              "machine": platform.machine(), "clock": "perf_counter_ns"},
              "samples": args.samples, "iterations_per_sample": args.iterations,
              "pair_order": "alternating baseline/candidate then candidate/baseline",
              "captures": captures, "rows": rows,
              "local_target": {"material_records_p50_at_least_15_percent_faster": target_met,
                               "p95_within_10_percent_plus_0_02_ms": no_tail_regression},
              "limits": ["Synthetic local CPU microbenchmark; real traffic baseline unavailable.",
                         "Output bytes unchanged: no additional input token reduction.",
                         "Batch-mean percentiles, not individual request or end-to-end latency.",
                         "No live model quality, API usage, CI or deployment conclusion."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(rows), "output": str(args.output)}))
    return 0 if target_met and no_tail_regression else 2


if __name__ == "__main__":
    raise SystemExit(main())
