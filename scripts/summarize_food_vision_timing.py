#!/usr/bin/env python3
"""Aggregate fixed passive timing records; never emit source log payloads."""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROW = re.compile(
    r"food_vision_stage input_kind=(base64|url) "
    r"stage=(provider|decode_sanitize) outcome=(returned|failed|cancelled) "
    r"elapsed_ms=(\d+)$"
)


def summarize(lines, *, max_events=100_000):
    groups = defaultdict(list)
    events = 0
    for line in lines:
        match = ROW.search(line.rstrip("\r\n"))
        if match is None:
            continue
        events += 1
        if events > max_events:
            raise ValueError("timing event limit exceeded; narrow the log window")
        kind, stage, outcome, elapsed = match.groups()
        groups[(kind, stage, outcome)].append(int(elapsed))
    rows = []
    for (kind, stage, outcome), values in sorted(groups.items()):
        values.sort()

        def percentile(p):
            position = (len(values) - 1) * p
            lo = int(position)
            return round(values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (position - lo))

        rows.append({
            "input_kind": kind, "stage": stage, "outcome": outcome,
            "samples": len(values), "p50_ms": percentile(.5),
            "sample_p95_ms": percentile(.95), "sample_p99_ms": percentile(.99),
        })
    return {"events": events, "stages": rows, "limits": [
        "Stage aggregates are not paired requests or end-to-end latency.",
        "Provider time includes transport, SDK retries and model waiting.",
        "Returned means the operation returned, not successful recognition or persistence.",
        "Missing events and non-matching lines are not zero-duration samples.",
    ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-events", type=int, default=100_000)
    args = parser.parse_args()
    if not 1 <= args.max_events <= 1_000_000:
        parser.error("max-events must be between 1 and 1000000")
    with args.log.open(encoding="utf-8") as source:
        result = summarize(source, max_events=args.max_events)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
