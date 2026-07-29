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

from app.services.agent_kernel.tool_registry import (
    ToolRegistryError,
    classify_tool_effect,
    expected_receipt_resource_type,
)


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


def _normalize_alias(value: Any, *, lower: bool = False) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        normalized = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        normalized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        normalized = str(value).strip()
    return normalized.lower() if lower else normalized


def _resolve_alias(
    value: dict[str, Any] | None,
    keys: tuple[str, ...],
    *,
    include_nested: bool = True,
    lower: bool = False,
) -> tuple[str | None, bool]:
    value = value or {}
    sources = [value]
    nested = value.get("data")
    if include_nested and isinstance(nested, dict):
        sources.append(nested)
    candidates = [
        normalized
        for source in sources
        for key in keys
        if (normalized := _normalize_alias(source.get(key), lower=lower)) is not None
    ]
    unique = list(dict.fromkeys(candidates))
    if len(unique) > 1:
        return None, True
    return (unique[0] if unique else None), False


def _operation(call: dict[str, Any]) -> str:
    name = str(call.get("name") or "").strip()
    if name == "health_record":
        return "create"
    args = call.get("args") or {}
    operation, _ = _resolve_alias(
        args,
        ("operation", "action"),
        include_nested=False,
        lower=True,
    )
    return operation or ""


def _record_type(call: dict[str, Any]) -> str:
    record_type, _ = _resolve_alias(
        call.get("args") or {},
        ("record_type", "type"),
        include_nested=False,
        lower=True,
    )
    return record_type or ""


def _meal_type(value: dict[str, Any] | None) -> str:
    meal_type, _ = _resolve_alias(value, ("meal_type",), lower=True)
    return meal_type or ""


def _record_id(value: dict[str, Any] | None) -> str | None:
    record_id, _ = _resolve_alias(value, ("resource_id", "record_id", "id"))
    return record_id


def _record_date(value: dict[str, Any] | None) -> str:
    record_date, _ = _resolve_alias(value, ("date", "record_date"))
    return record_date or ""


def _trace_tool_calls(
    trace: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    raw_root_calls = trace.get("tool_calls") or []
    if not isinstance(raw_root_calls, list):
        failures.append("invalid_top_level_tool_calls")
        raw_root_calls = []
    root_calls = []
    for call in raw_root_calls:
        if not isinstance(call, dict):
            failures.append("malformed_top_level_tool_call")
            continue
        root_calls.append(call)

    attempt_calls: list[dict[str, Any]] = []
    attempts = trace.get("attempts")
    if "attempts" in trace and not isinstance(attempts, list):
        failures.append("invalid_attempts_projection")
        return root_calls, failures
    if isinstance(attempts, list):
        if not attempts:
            failures.append("empty_attempts_projection")
        for attempt in attempts:
            if not isinstance(attempt, dict):
                failures.append("malformed_attempt")
                continue
            raw_calls = attempt.get("tool_calls")
            if not isinstance(raw_calls, list):
                failures.append("invalid_attempt_tool_calls")
                continue
            for call in raw_calls:
                if not isinstance(call, dict):
                    failures.append("malformed_attempt_tool_call")
                    continue
                attempt_calls.append(call)
        if "tool_calls" in trace and root_calls != attempt_calls:
            failures.append("inconsistent_top_level_tool_calls")
            # The ordering cannot be trusted, but every represented side effect
            # must still be inspected so an invalid projection cannot hide a
            # prohibited write.
            return root_calls + attempt_calls, failures
        return attempt_calls, failures
    return root_calls, []


def _write_indexes_and_contract_failures(
    calls: list[dict[str, Any]],
) -> tuple[list[int], list[str]]:
    indexes: list[int] = []
    failures: list[str] = []
    for index, call in enumerate(calls):
        name = str(call.get("name") or "").strip()
        try:
            effect = classify_tool_effect(name, call.get("args") or {})
        except ToolRegistryError as exc:
            failures.append(str(exc))
            if _operation(call) in _WRITE_OPERATIONS:
                indexes.append(index)
            continue
        if effect == "write":
            indexes.append(index)
    return indexes, failures


def _arg_value(call: dict[str, Any], key: str) -> Any:
    args = call.get("args") or {}
    value, _ = _resolve_alias(args, (key,))
    return value


def _receipt_status(call: dict[str, Any]) -> str:
    receipt = call.get("receipt")
    if not isinstance(receipt, dict):
        return ""
    return str(receipt.get("status") or "").strip().lower()


def _receipt_is_verified(call: dict[str, Any]) -> bool:
    receipt = call.get("receipt")
    return (
        isinstance(receipt, dict)
        and _receipt_status(call) in _VERIFIED_RECEIPT_STATUSES
        and receipt.get("verified") is True
    )


def _receipt_resource_type(call: dict[str, Any]) -> str:
    receipt = call.get("receipt")
    if not isinstance(receipt, dict):
        return ""
    resource_type, _ = _resolve_alias(
        receipt,
        ("resource_type", "record_type"),
        lower=True,
    )
    return resource_type or ""


def _receipt_matches_target(
    call: dict[str, Any],
    *,
    expected_resource_type: str,
    expected_date: str,
) -> bool:
    receipt = call.get("receipt")
    if not _receipt_is_verified(call) or not isinstance(receipt, dict):
        return False
    if (
        expected_resource_type
        and _receipt_resource_type(call) != expected_resource_type
    ):
        return False
    return not expected_date or _record_date(receipt) == expected_date


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
    calls, trace_contract_failures = _trace_tool_calls(trace)
    target_meals = set(expected.get("target_meal_types") or [])
    prohibited = set(expected.get("prohibited_operations") or [])
    hard_failures: list[str] = list(trace_contract_failures)
    expected_record_type = str(
        expected.get("target_record_type") or expected.get("domain") or ""
    ).strip().lower()
    expected_operation = str(expected.get("operation") or "").strip().lower()
    expected_date = str(expected.get("target_date") or "").strip()
    expected_resource_type = expected_receipt_resource_type(
        "health_record" if expected_operation == "create" else "health_manage",
        {"record_type": expected_record_type},
    ) or expected_record_type

    operations = [_operation(call) for call in calls]
    for operation in operations:
        if operation and operation in prohibited:
            hard_failures.append(f"prohibited_operation:{operation}")

    write_indexes, tool_contract_failures = _write_indexes_and_contract_failures(calls)
    hard_failures.extend(tool_contract_failures)
    write_calls = [calls[index] for index in write_indexes]
    if expected_operation not in _WRITE_OPERATIONS:
        for operation in sorted({_operation(call) for call in write_calls}):
            hard_failures.append(f"unexpected_write_operation:{operation}")
    else:
        for call in write_calls:
            operation = _operation(call)
            record_type = _record_type(call)
            write_date = _record_date(call.get("args"))
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            _, operation_conflict = _resolve_alias(
                args,
                ("operation", "action"),
                include_nested=False,
                lower=True,
            )
            _, record_type_conflict = _resolve_alias(
                args,
                ("record_type", "type"),
                include_nested=False,
                lower=True,
            )
            _, date_conflict = _resolve_alias(args, ("date", "record_date"))
            _, identity_conflict = _resolve_alias(
                args,
                ("resource_id", "record_id", "id"),
            )
            _, meal_conflict = _resolve_alias(args, ("meal_type",), lower=True)
            if operation_conflict:
                hard_failures.append("conflicting_write_operation")
            if record_type_conflict:
                hard_failures.append("conflicting_write_record_type")
            if date_conflict:
                hard_failures.append("conflicting_write_target_date")
            if identity_conflict:
                hard_failures.append("conflicting_write_record_identity")
            if meal_conflict:
                hard_failures.append("conflicting_write_meal_type")
            for key in (expected.get("target_values") or {}):
                _, value_conflict = _resolve_alias(args, (str(key),))
                if value_conflict:
                    hard_failures.append(
                        f"conflicting_write_target_value:{key}"
                    )
            if operation != expected_operation:
                hard_failures.append(f"unexpected_write_operation:{operation}")
            if expected_record_type and record_type != expected_record_type:
                hard_failures.append(
                    f"unexpected_write_target:{record_type or 'missing'}"
                )
            if expected_date:
                if not write_date:
                    hard_failures.append("write_target_date_missing")
                elif write_date != expected_date:
                    hard_failures.append("write_target_date_mismatch")
    domain_lookup_indexes: list[int] = []
    for index, call in enumerate(calls):
        if _operation(call) != "list" or _record_type(call) != expected.get("domain"):
            continue
        lookup_args = call.get("args") if isinstance(call.get("args"), dict) else {}
        _, lookup_date_conflict = _resolve_alias(
            lookup_args,
            ("date", "record_date"),
        )
        if lookup_date_conflict:
            hard_failures.append("conflicting_lookup_target_date")
            continue
        domain_lookup_indexes.append(index)
    lookup_indexes = [
        index
        for index in domain_lookup_indexes
        if not expected_date or _record_date(calls[index].get("args")) == expected_date
    ]
    if (
        expected.get("requires_lookup")
        and expected_date
        and domain_lookup_indexes
        and not lookup_indexes
    ):
        hard_failures.append("lookup_target_date_mismatch")
    lookup_before_write = bool(lookup_indexes) if expected.get("requires_lookup") else True
    if write_indexes and expected.get("requires_lookup"):
        lookup_before_write = bool(lookup_indexes) and min(lookup_indexes) < min(write_indexes)
        if not lookup_before_write:
            hard_failures.append("write_before_lookup")

    authoritative_ids_by_meal: dict[str, set[Any]] = defaultdict(set)
    if target_meals and lookup_indexes:
        for row in _result_rows(calls[lookup_indexes[0]]):
            _, row_date_conflict = _resolve_alias(
                row,
                ("date", "record_date"),
            )
            _, row_id_conflict = _resolve_alias(
                row,
                ("resource_id", "record_id", "id"),
            )
            _, row_meal_conflict = _resolve_alias(
                row,
                ("meal_type",),
                lower=True,
            )
            if row_date_conflict:
                hard_failures.append("conflicting_lookup_result_date")
            if row_id_conflict:
                hard_failures.append("conflicting_lookup_result_identity")
            if row_meal_conflict:
                hard_failures.append("conflicting_lookup_result_meal_type")
            if row_date_conflict or row_id_conflict or row_meal_conflict:
                continue
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
    exact_target_updates = (
        bool(target_meals)
        and target_meals.issubset(updated_by_meal)
        and len(update_calls) == len(target_meals)
    )
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
        and _operation(call) == expected_operation
        and (not expected_record_type or _record_type(call) == expected_record_type)
    ]
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
        _, receipt_type_conflict = _resolve_alias(
            receipt,
            ("resource_type", "record_type"),
            lower=True,
        )
        _, receipt_id_conflict = _resolve_alias(
            receipt,
            ("resource_id", "record_id", "id"),
        )
        _, receipt_date_conflict = _resolve_alias(
            receipt,
            ("date", "record_date"),
        )
        _, receipt_meal_conflict = _resolve_alias(
            receipt,
            ("meal_type",),
            lower=True,
        )
        if receipt_type_conflict:
            hard_failures.append("conflicting_write_receipt_resource_type")
        if receipt_id_conflict:
            hard_failures.append("conflicting_write_receipt_identity")
        if receipt_date_conflict:
            hard_failures.append("conflicting_write_receipt_target_date")
        if receipt_meal_conflict:
            hard_failures.append("conflicting_write_receipt_meal_type")
        if _receipt_status(call) in _VERIFIED_RECEIPT_STATUSES:
            if receipt.get("verified") is False:
                hard_failures.append("write_receipt_explicitly_unverified")
            elif receipt.get("verified") is not True:
                hard_failures.append("write_receipt_not_explicitly_verified")
        if _receipt_is_verified(call):
            if (
                expected_resource_type
                and _receipt_resource_type(call) != expected_resource_type
            ):
                hard_failures.append("write_receipt_resource_type_mismatch")
            if expected_date and _record_date(receipt) != expected_date:
                hard_failures.append("write_receipt_date_mismatch")
        if not _receipt_matches_target(
            call,
            expected_resource_type=expected_resource_type,
            expected_date=expected_date,
        ):
            continue
        record_id = _record_id(receipt)
        write_record_id = _record_id(call.get("args"))
        if (
            _operation(call) in {"update", "delete"}
            and write_record_id is not None
            and record_id is not None
            and record_id != write_record_id
        ):
            hard_failures.append("write_receipt_identity_mismatch")
        meal = _meal_type(receipt) or _meal_type(call.get("args"))
        if record_id is not None:
            verified_ids.add(record_id)
        if meal:
            verified_meals.add(meal)
    missing_identity_receipts = [
        call
        for call in relevant_write_calls
        if _receipt_matches_target(
            call,
            expected_resource_type=expected_resource_type,
            expected_date=expected_date,
        )
        and _record_id(call.get("receipt")) is None
    ]
    if missing_identity_receipts:
        hard_failures.append("write_receipt_missing_identity")
    every_write_has_identity_receipt = bool(relevant_write_calls) and all(
        _receipt_matches_target(
            call,
            expected_resource_type=expected_resource_type,
            expected_date=expected_date,
        )
        and _record_id(call.get("receipt")) is not None
        for call in relevant_write_calls
    )
    if target_meals:
        verified_receipts = (
            every_write_has_identity_receipt
            and verified_meals == target_meals
            and len(relevant_write_calls) == len(target_meals)
        )
    elif expected_operation in _WRITE_OPERATIONS:
        verified_receipts = every_write_has_identity_receipt
    else:
        verified_receipts = True

    successful_write_calls = [
        call
        for call in relevant_write_calls
        if _receipt_matches_target(
            call,
            expected_resource_type=expected_resource_type,
            expected_date=expected_date,
        )
    ]
    root_turn_id = str(trace.get("client_turn_id") or "").strip()
    if not root_turn_id:
        hard_failures.append("client_turn_id_missing")
    attempts = trace.get("attempts")
    if isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            attempt_turn_id = str(attempt.get("client_turn_id") or "").strip()
            if not attempt_turn_id:
                hard_failures.append("attempt_client_turn_id_missing")
            elif root_turn_id and attempt_turn_id != root_turn_id:
                hard_failures.append("client_turn_id_changed_across_attempts")
    allowed_effects = len(target_meals) if target_meals else (
        1 if expected_operation in _WRITE_OPERATIONS else 0
    )
    if (
        allowed_effects
        and len(successful_write_calls) > allowed_effects
    ):
        hard_failures.append(
            f"duplicate_side_effects:{len(successful_write_calls)}>{allowed_effects}"
        )

    last_write = max(write_indexes) if write_indexes else -1
    readback_rows: list[dict[str, Any]] = []
    mismatched_readback_date = False
    mismatched_readback_result_date = False
    for index, call in enumerate(calls):
        if index > last_write and _operation(call) == "list":
            read_args = call.get("args") if isinstance(call.get("args"), dict) else {}
            _, read_date_conflict = _resolve_alias(
                read_args,
                ("date", "record_date"),
            )
            if read_date_conflict:
                hard_failures.append("conflicting_readback_target_date")
                continue
            if expected_date and _record_date(call.get("args")) != expected_date:
                mismatched_readback_date = True
                continue
            for row in _result_rows(call):
                _, row_date_conflict = _resolve_alias(
                    row,
                    ("date", "record_date"),
                )
                _, row_id_conflict = _resolve_alias(
                    row,
                    ("resource_id", "record_id", "id"),
                )
                _, row_meal_conflict = _resolve_alias(
                    row,
                    ("meal_type",),
                    lower=True,
                )
                if row_date_conflict:
                    hard_failures.append("conflicting_readback_result_date")
                    continue
                if row_id_conflict:
                    hard_failures.append("conflicting_readback_result_identity")
                    continue
                if row_meal_conflict:
                    hard_failures.append("conflicting_readback_result_meal_type")
                    continue
                if expected_date and _record_date(row) != expected_date:
                    mismatched_readback_result_date = True
                    continue
                readback_rows.append(row)
    if (
        expected.get("requires_verification")
        and mismatched_readback_date
        and not readback_rows
    ):
        hard_failures.append("readback_target_date_mismatch")
    if expected.get("requires_verification") and mismatched_readback_result_date:
        hard_failures.append("readback_result_date_mismatch")
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
