"""Deterministic task completion checks for Agent goals."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from app.services.agent_kernel.goal_registry import (
    GoalVerifierRegistry,
    GoalVerifierSpec,
)
from app.services.agent_kernel.types import GoalSpec


@dataclass(frozen=True)
class PostconditionResult:
    satisfied: bool
    reason: str
    missing_targets: tuple[str, ...] = ()
    verified_resource_ids: tuple[str, ...] = ()


def verify_goal_postconditions(
    goal: GoalSpec | None,
    *,
    write_receipts: Sequence[dict[str, Any]],
    verification_result: Any,
) -> PostconditionResult:
    """Verify task outcome from receipts and authoritative read-back data."""
    if goal is None or not goal.requires_verification:
        return PostconditionResult(True, "verification_not_required")
    result = _GOAL_VERIFIER_REGISTRY.verify(
        goal,
        write_receipts=write_receipts,
        verification_result=verification_result,
    )
    if result is None:
        return PostconditionResult(False, "unsupported_goal_verifier")
    return result


def registered_goal_verifier_kinds() -> tuple[str, ...]:
    return _GOAL_VERIFIER_REGISTRY.kinds


def _verify_diet_recalculation(
    goal: GoalSpec,
    *,
    write_receipts: Sequence[dict[str, Any]],
    verification_result: Any,
) -> PostconditionResult:
    receipt_ids = _diet_receipt_ids(write_receipts)
    if len(receipt_ids) < len(goal.target_meal_types):
        return PostconditionResult(False, "write_receipts_missing")

    rows = _result_rows(verification_result)
    verified_ids: list[str] = []
    verified_meals: set[str] = set()
    expected_calories = _exact_calorie_target(goal)
    if (
        "explicit_nutrition_correction" in goal.evidence
        and expected_calories is None
    ):
        return PostconditionResult(False, "verification_target_invalid")
    mismatched_meals: set[str] = set()
    for row in rows:
        resource_id = _row_id(row)
        meal_type = str(row.get("meal_type") or "").strip().lower()
        if resource_id not in receipt_ids or meal_type not in goal.target_meal_types:
            continue
        if expected_calories is not None:
            actual_calories = _decimal_number(row.get("calories"))
            if actual_calories is None or actual_calories != expected_calories:
                mismatched_meals.add(meal_type)
                continue
        verified_ids.append(resource_id)
        verified_meals.add(meal_type)

    if mismatched_meals:
        return PostconditionResult(
            False,
            "verification_value_mismatch",
            missing_targets=tuple(sorted(mismatched_meals)),
            verified_resource_ids=tuple(verified_ids),
        )

    missing = tuple(
        meal_type
        for meal_type in goal.target_meal_types
        if meal_type not in verified_meals
    )
    if missing:
        return PostconditionResult(
            False,
            "verification_targets_missing",
            missing_targets=missing,
            verified_resource_ids=tuple(verified_ids),
        )
    return PostconditionResult(
        True,
        "verified",
        verified_resource_ids=tuple(verified_ids),
    )


def _exact_calorie_target(goal: GoalSpec) -> Decimal | None:
    if "explicit_nutrition_correction" not in goal.evidence:
        return None
    if len(goal.target_values) != 1 or goal.target_values[0][0] != "calories":
        return None
    value = _decimal_number(goal.target_values[0][1])
    if value is None or value <= 0:
        return None
    return value


def _decimal_number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _verify_simple_health_record(
    goal: GoalSpec,
    *,
    write_receipts: Sequence[dict[str, Any]],
    verification_result: Any,
) -> PostconditionResult:
    del verification_result
    expected_resource_type = {
        "water": "water_record",
        "symptom": "symptom_record",
        "diet": "diet_record",
    }.get(str(goal.target_record_type or "").strip().lower())
    if expected_resource_type is None:
        return PostconditionResult(False, "unsupported_record_type")

    receipts = [
        receipt
        for receipt in write_receipts
        if isinstance(receipt, dict)
    ]
    if len(receipts) > 1:
        return PostconditionResult(False, "unexpected_write_receipt_count")

    verified_ids: list[str] = []
    for receipt in receipts:
        if (
            str(receipt.get("resource_type") or "").strip()
            != expected_resource_type
            or receipt.get("verified") is not True
        ):
            continue
        resource_id = receipt.get("resource_id")
        if isinstance(resource_id, bool) or resource_id in (None, ""):
            continue
        verified_ids.append(str(resource_id).strip())

    if not verified_ids:
        return PostconditionResult(
            False,
            "write_receipt_type_mismatch" if receipts else "write_receipt_missing",
        )
    return PostconditionResult(
        True,
        "verified",
        verified_resource_ids=tuple(verified_ids),
    )


def _diet_receipt_ids(
    write_receipts: Sequence[dict[str, Any]],
) -> set[str]:
    result: set[str] = set()
    for receipt in write_receipts:
        if not isinstance(receipt, dict):
            continue
        resource_type = str(receipt.get("resource_type") or "").strip()
        if resource_type not in {"diet", "diet_record"}:
            continue
        resource_id = receipt.get("resource_id")
        if isinstance(resource_id, bool) or resource_id in (None, ""):
            continue
        result.add(str(resource_id).strip())
    return result


def _result_rows(value: Any) -> list[dict[str, Any]]:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if isinstance(parsed, dict):
        for key in ("items", "records", "data", "results"):
            nested = parsed.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
    return []


def _row_id(row: dict[str, Any]) -> str:
    for key in ("id", "record_id"):
        value = row.get(key)
        if isinstance(value, bool) or value in (None, ""):
            continue
        return str(value).strip()
    return ""


_GOAL_VERIFIER_REGISTRY = GoalVerifierRegistry(
    (
        GoalVerifierSpec(
            kind="diet_recalculate_update",
            verifier=_verify_diet_recalculation,
        ),
        GoalVerifierSpec(
            kind="simple_health_record",
            verifier=_verify_simple_health_record,
        ),
    )
)
