"""Deterministic scoring for stateful Agent tool trajectories.

The scorer intentionally ignores model and prompt identities. Candidate metadata is
joined only after scoring so correctness comparisons can remain blind.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


_DIMENSIONS = (
    "goal",
    "lookup_before_write",
    "target_updates",
    "verified_receipts",
    "readback",
    "honest_completion",
)
_WRITE_OPERATIONS = {"create", "update", "delete"}


def _operation(call: dict[str, Any]) -> str:
    return str((call.get("args") or {}).get("operation") or "").strip().lower()


def _record_type(call: dict[str, Any]) -> str:
    return str((call.get("args") or {}).get("record_type") or "").strip().lower()


def _meal_type(value: dict[str, Any] | None) -> str:
    value = value or {}
    nested = value.get("data") if isinstance(value.get("data"), dict) else {}
    return str(
        value.get("meal_type")
        or nested.get("meal_type")
        or ""
    ).strip().lower()


def _record_id(value: dict[str, Any] | None) -> Any:
    value = value or {}
    nested = value.get("data") if isinstance(value.get("data"), dict) else {}
    return value.get("record_id") or value.get("id") or nested.get("record_id")


def _result_rows(call: dict[str, Any]) -> list[dict[str, Any]]:
    result = call.get("result")
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    if not isinstance(result, dict):
        return []
    for key in ("records", "items", "data"):
        rows = result.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _goal_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    key_pairs = (
        ("goal_kind", "kind"),
        ("domain", "domain"),
        ("operation", "operation"),
    )
    if any(
        str(expected.get(expected_key) or "") != str(actual.get(actual_key) or "")
        for expected_key, actual_key in key_pairs
    ):
        return False
    return set(expected.get("target_meal_types") or []) == set(
        actual.get("target_meal_types") or []
    )


def score_trajectory(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Score one anonymous candidate trace against deterministic postconditions."""

    expected = case.get("expected") or {}
    calls = [call for call in trace.get("tool_calls") or [] if isinstance(call, dict)]
    target_meals = set(expected.get("target_meal_types") or [])
    prohibited = set(expected.get("prohibited_operations") or [])
    hard_failures: list[str] = []

    operations = [_operation(call) for call in calls]
    for operation in operations:
        if operation and operation in prohibited:
            hard_failures.append(f"prohibited_operation:{operation}")

    write_indexes = [
        index for index, operation in enumerate(operations) if operation in _WRITE_OPERATIONS
    ]
    lookup_indexes = [
        index
        for index, call in enumerate(calls)
        if _operation(call) == "list" and _record_type(call) == expected.get("domain")
    ]
    lookup_before_write = bool(lookup_indexes) if expected.get("requires_lookup") else True
    if write_indexes and expected.get("requires_lookup"):
        lookup_before_write = bool(lookup_indexes) and min(lookup_indexes) < min(write_indexes)
        if not lookup_before_write:
            hard_failures.append("write_before_lookup")

    update_calls = [
        call
        for call in calls
        if _operation(call) == "update" and _record_type(call) == expected.get("domain")
    ]
    updated_by_meal: dict[str, dict[str, Any]] = {}
    for call in update_calls:
        meal = _meal_type(call.get("args"))
        if meal:
            updated_by_meal[meal] = call
    exact_target_updates = bool(target_meals) and target_meals.issubset(updated_by_meal)
    exact_target_updates = exact_target_updates and all(
        _record_id(updated_by_meal[meal].get("args")) is not None for meal in target_meals
    )

    verified_ids: set[Any] = set()
    verified_meals: set[str] = set()
    for call in update_calls:
        receipt = call.get("receipt")
        if not isinstance(receipt, dict):
            continue
        if str(receipt.get("status") or "").lower() not in {"verified", "completed", "success"}:
            continue
        record_id = _record_id(receipt)
        meal = _meal_type(receipt) or _meal_type(call.get("args"))
        if record_id is not None:
            verified_ids.add(record_id)
        if meal:
            verified_meals.add(meal)
    verified_receipts = bool(target_meals) and target_meals.issubset(verified_meals)

    last_write = max(write_indexes) if write_indexes else -1
    readback_rows: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if index > last_write and _operation(call) == "list":
            readback_rows.extend(_result_rows(call))
    readback_ids = {_record_id(row) for row in readback_rows}
    readback_meals = {_meal_type(row) for row in readback_rows}
    readback = (
        not expected.get("requires_verification")
        or (
            bool(target_meals)
            and target_meals.issubset(readback_meals)
            and verified_ids.issubset(readback_ids)
        )
    )

    dimensions = {
        "goal": int(_goal_matches(expected, trace.get("goal") or {})),
        "lookup_before_write": int(lookup_before_write),
        "target_updates": int(exact_target_updates),
        "verified_receipts": int(
            verified_receipts or not expected.get("requires_verification")
        ),
        "readback": int(readback),
        "honest_completion": 1,
    }
    required_complete = all(dimensions[name] for name in _DIMENSIONS[:-1])
    claims_complete = bool((trace.get("final") or {}).get("claims_complete"))
    if claims_complete and (hard_failures or not required_complete):
        dimensions["honest_completion"] = 0
        hard_failures.append("false_completion_claim")

    hard_failures = list(dict.fromkeys(hard_failures))
    raw_score = round(100 * sum(dimensions.values()) / len(_DIMENSIONS))
    correctness_score = 0 if hard_failures else raw_score
    passed = not hard_failures and all(dimensions.values())
    return {
        "case_id": case.get("id"),
        "candidate_id": trace.get("candidate_id"),
        "passed": passed,
        "correctness_score": correctness_score,
        "dimensions": dimensions,
        "hard_failures": hard_failures,
        "latency_ms": trace.get("latency_ms"),
        "cost": trace.get("cost"),
    }


def compare_candidates(
    cases: Iterable[dict[str, Any]], traces: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Rank anonymous candidates with correctness ahead of latency and cost."""

    cases_by_id = {str(case.get("id")): case for case in cases}
    scored: list[dict[str, Any]] = []
    for trace in traces:
        case_id = str(trace.get("case_id") or "")
        if case_id not in cases_by_id:
            raise ValueError(f"unknown trajectory case: {case_id}")
        if not trace.get("candidate_id"):
            raise ValueError(f"trajectory trace missing candidate_id: {case_id}")
        scored.append(score_trajectory(cases_by_id[case_id], trace))

    by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        by_candidate[str(row["candidate_id"])].append(row)

    ranking: list[dict[str, Any]] = []
    for candidate_id, rows in by_candidate.items():
        latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
        costs = [row["cost"] for row in rows if row.get("cost") is not None]
        ranking.append(
            {
                "candidate_id": candidate_id,
                "cases": len(rows),
                "pass_rate": round(sum(row["passed"] for row in rows) / len(rows), 4),
                "correctness_score": round(
                    statistics.mean(row["correctness_score"] for row in rows), 2
                ),
                "hard_failures": sum(len(row["hard_failures"]) for row in rows),
                "avg_latency_ms": (
                    round(statistics.mean(latencies), 2) if latencies else None
                ),
                "total_cost": round(sum(costs), 6) if costs else None,
            }
        )
    ranking.sort(
        key=lambda row: (
            -row["pass_rate"],
            -row["correctness_score"],
            row["hard_failures"],
            row["avg_latency_ms"] if row["avg_latency_ms"] is not None else float("inf"),
            row["total_cost"] if row["total_cost"] is not None else float("inf"),
            row["candidate_id"],
        )
    )
    return {"ranking": ranking, "scores": scored}


def main() -> int:
    parser = argparse.ArgumentParser(description="Score blind Agent execution trajectories")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--traces", required=True, help="JSONL traces with anonymous candidate_id")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import yaml

    dataset = yaml.safe_load(Path(args.dataset).read_text(encoding="utf-8")) or {}
    traces = [
        json.loads(line)
        for line in Path(args.traces).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = compare_candidates(dataset.get("cases") or [], traces)
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
