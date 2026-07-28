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
_VERIFIED_RECEIPT_STATUSES = {"verified", "completed", "success"}
_UNCERTAIN_RECEIPT_STATUSES = {
    "uncertain",
    "in_flight",
    "processing",
    "queued",
    "reconciliation_required",
}


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


def _trace_tool_calls(trace: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = trace.get("attempts")
    if isinstance(attempts, list):
        return [
            call
            for attempt in attempts
            if isinstance(attempt, dict)
            for call in (attempt.get("tool_calls") or [])
            if isinstance(call, dict)
        ]
    return [
        call
        for call in (trace.get("tool_calls") or [])
        if isinstance(call, dict)
    ]


def _arg_value(call: dict[str, Any], key: str) -> Any:
    args = call.get("args") or {}
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    return args.get(key) if args.get(key) is not None else data.get(key)


def _receipt_status(call: dict[str, Any]) -> str:
    receipt = call.get("receipt")
    if not isinstance(receipt, dict):
        return ""
    return str(receipt.get("status") or "").strip().lower()


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
    if expected.get("target_date") and str(expected["target_date"]) != str(
        actual.get("target_date") or ""
    ):
        return False
    return set(expected.get("target_meal_types") or []) == set(
        actual.get("target_meal_types") or []
    )


def score_trajectory(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Score one anonymous candidate trace against deterministic postconditions."""

    expected = case.get("expected") or {}
    calls = _trace_tool_calls(trace)
    target_meals = set(expected.get("target_meal_types") or [])
    prohibited = set(expected.get("prohibited_operations") or [])
    hard_failures: list[str] = []
    expected_record_type = str(
        expected.get("target_record_type") or expected.get("domain") or ""
    ).strip().lower()

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

    authoritative_ids_by_meal: dict[str, set[Any]] = defaultdict(set)
    if target_meals and lookup_indexes:
        for row in _result_rows(calls[lookup_indexes[0]]):
            meal = _meal_type(row)
            record_id = _record_id(row)
            if meal in target_meals and record_id is not None:
                authoritative_ids_by_meal[meal].add(record_id)
        for meal in sorted(target_meals):
            count = len(authoritative_ids_by_meal[meal])
            if count == 0:
                hard_failures.append(f"missing_lookup_target:{meal}")
            elif count > 1:
                hard_failures.append(f"ambiguous_lookup_target:{meal}")

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
    if expected.get("requires_lookup") and exact_target_updates:
        exact_target_updates = all(
            _record_id(updated_by_meal[meal].get("args"))
            in authoritative_ids_by_meal[meal]
            for meal in target_meals
        )
        if not exact_target_updates:
            hard_failures.append("update_target_not_from_lookup")

    relevant_write_calls = [
        call
        for call in calls
        if _operation(call) in _WRITE_OPERATIONS
        and (not expected_record_type or _record_type(call) == expected_record_type)
    ]
    expected_operation = str(expected.get("operation") or "").strip().lower()
    expected_values = expected.get("target_values") or {}
    if target_meals:
        target_effects = exact_target_updates
    elif expected_operation in _WRITE_OPERATIONS:
        matching_writes = [
            call
            for call in relevant_write_calls
            if _operation(call) == expected_operation
            and all(
                str(_arg_value(call, key)) == str(value)
                for key, value in expected_values.items()
            )
        ]
        target_effects = len(matching_writes) == 1
    else:
        target_effects = True

    verified_ids: set[Any] = set()
    verified_meals: set[str] = set()
    for call in relevant_write_calls:
        receipt = call.get("receipt")
        if not isinstance(receipt, dict):
            continue
        if _receipt_status(call) not in _VERIFIED_RECEIPT_STATUSES:
            continue
        record_id = _record_id(receipt)
        meal = _meal_type(receipt) or _meal_type(call.get("args"))
        if record_id is not None:
            verified_ids.add(record_id)
        if meal:
            verified_meals.add(meal)
    if target_meals:
        verified_receipts = target_meals.issubset(verified_meals)
    elif expected_operation in _WRITE_OPERATIONS:
        verified_receipts = bool(verified_ids)
    else:
        verified_receipts = True

    successful_effect_ids = {
        _record_id(call.get("receipt"))
        for call in relevant_write_calls
        if _receipt_status(call) in _VERIFIED_RECEIPT_STATUSES
        and _record_id(call.get("receipt")) is not None
    }
    attempt_turn_ids = {
        str(attempt.get("client_turn_id"))
        for attempt in (trace.get("attempts") or [])
        if isinstance(attempt, dict) and attempt.get("client_turn_id")
    }
    if len(attempt_turn_ids) > 1:
        hard_failures.append("client_turn_id_changed_across_attempts")
    same_client_turn = bool(trace.get("client_turn_id")) or len(attempt_turn_ids) == 1
    allowed_effects = len(target_meals) if target_meals else (
        1 if expected_operation in _WRITE_OPERATIONS else 0
    )
    if same_client_turn and allowed_effects and len(successful_effect_ids) > allowed_effects:
        hard_failures.append(
            f"duplicate_side_effects:{len(successful_effect_ids)}>{allowed_effects}"
        )

    last_write = max(write_indexes) if write_indexes else -1
    readback_rows: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if index > last_write and _operation(call) == "list":
            readback_rows.extend(_result_rows(call))
    readback_ids = {_record_id(row) for row in readback_rows}
    readback_meals = {_meal_type(row) for row in readback_rows}
    if not expected.get("requires_verification"):
        readback = True
    elif target_meals:
        readback = (
            target_meals.issubset(readback_meals)
            and bool(verified_ids)
            and verified_ids.issubset(readback_ids)
        )
    else:
        readback = bool(verified_ids) and verified_ids.issubset(readback_ids)

    dimensions = {
        "goal": int(_goal_matches(expected, trace.get("goal") or {})),
        "lookup_before_write": int(lookup_before_write),
        "target_updates": int(target_effects),
        # A write may skip a separate readback when the contract allows it, but
        # it may never claim completion without an identity-bearing receipt.
        "verified_receipts": int(
            verified_receipts
            if expected_operation in _WRITE_OPERATIONS
            else True
        ),
        "readback": int(readback),
        "honest_completion": 1,
    }
    required_complete = all(dimensions[name] for name in _DIMENSIONS[:-1])
    claims_complete = bool((trace.get("final") or {}).get("claims_complete"))
    if claims_complete and any(
        _receipt_status(call) in _UNCERTAIN_RECEIPT_STATUSES
        for call in relevant_write_calls
    ):
        hard_failures.append("uncertain_receipt_claimed_complete")
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
