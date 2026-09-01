#!/usr/bin/env python3
"""Replay the sanitized interaction-quality release corpus."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "backend/tests/fixtures/agent_interaction_quality/corpus.json"
FORBIDDEN_KEYS = {"prompt", "content", "image", "user_id", "token", "secret", "database_dump"}


def percentile(values: list[int], ratio: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * ratio) - 1)]


def main() -> int:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    turns = payload.get("turns", [])
    failures: list[str] = []
    if payload.get("synthetic") is not True or len(turns) != 20:
        failures.append("corpus must contain exactly 20 synthetic turns")
    for turn in turns:
        leaked_keys = FORBIDDEN_KEYS.intersection(turn)
        if leaked_keys:
            failures.append(f"forbidden fixture fields: {sorted(leaked_keys)}")

    surfaces = sum(int(turn.get("surfaces", 0)) for turn in turns)
    literal_br = sum(turn["surfaces"] for turn in turns if turn.get("literal_br"))
    placeholder_flood = sum(turn["surfaces"] for turn in turns if turn.get("placeholder_flood"))
    protocol_leak = sum(turn["surfaces"] for turn in turns if turn.get("protocol_leak"))
    terminal_mismatch = sum(1 for turn in turns if not turn.get("terminal_match"))
    unverified_write_claim = sum(
        1 for turn in turns if turn.get("write_claim") and not turn.get("verified_receipt")
    )
    read_requests = sum(int(turn.get("read_requests", 0)) for turn in turns)
    read_executions = sum(int(turn.get("read_executions", 0)) for turn in turns)
    duplicate_ratio = max(0, read_executions - read_requests) / max(1, read_requests)
    unsafe_medication_paths = sum(1 for turn in turns if turn.get("unsafe_medication_path"))
    oversized_outputs = sum(1 for turn in turns if int(turn.get("output_chars", 0)) > 50_000)

    timing: dict[str, dict[str, int]] = {}
    for timing_class in ("simple_read", "routine_health", "complex_report"):
        rows = [turn for turn in turns if turn.get("timing_class") == timing_class]
        timing[timing_class] = {
            "p95_ttft_ms": percentile([int(row["ttft_ms"]) for row in rows], 0.95),
            "p95_total_ms": percentile([int(row["total_ms"]) for row in rows], 0.95),
        }

    checks = {
        "surface_count_100": surfaces == 100,
        "literal_br_0": literal_br == 0,
        "placeholder_flood_0": placeholder_flood == 0,
        "protocol_leak_0": protocol_leak == 0,
        "terminal_mismatch_0": terminal_mismatch == 0,
        "unverified_write_claim_0": unverified_write_claim == 0,
        "duplicate_ratio_lt_1pct": duplicate_ratio < 0.01,
        "simple_read_p95_ttft_le_5s": timing["simple_read"]["p95_ttft_ms"] <= 5_000,
        "routine_health_p95_ttft_le_10s": timing["routine_health"]["p95_ttft_ms"] <= 10_000,
        "complex_report_p95_total_le_30s": timing["complex_report"]["p95_total_ms"] <= 30_000,
        "bounded_outputs": oversized_outputs == 0,
        "unsafe_medication_paths_0": unsafe_medication_paths == 0,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    report = {
        "synthetic_contract_fixture": True,
        "turns": len(turns),
        "surfaces": surfaces,
        "duplicate_ratio": round(duplicate_ratio, 4),
        "timing": timing,
        "checks": checks,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
