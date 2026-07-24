import json

from app.services.agent_kernel.postconditions import (
    registered_goal_verifier_kinds,
    verify_goal_postconditions,
)
from app.services.agent_kernel.types import GoalSpec


def _goal() -> GoalSpec:
    return GoalSpec(
        kind="diet_recalculate_update",
        domain="diet",
        operation="update",
        target_date="2026-07-24",
        target_meal_types=("breakfast", "lunch"),
        requires_lookup=True,
        requires_verification=True,
        postconditions=("existing_records_only", "read_back_verified"),
    )


def test_goal_postconditions_require_receipts_and_matching_readback_rows():
    result = verify_goal_postconditions(
        _goal(),
        write_receipts=[
            {"resource_type": "diet_record", "resource_id": "101"},
            {"resource_type": "diet_record", "resource_id": "102"},
        ],
        verification_result=json.dumps([
            {"id": 101, "meal_type": "breakfast", "calories": 280},
            {"id": 102, "meal_type": "lunch", "calories": 520},
        ]),
    )

    assert result.satisfied is True
    assert result.missing_targets == ()
    assert result.verified_resource_ids == ("101", "102")


def test_goal_postconditions_fail_when_a_target_meal_is_missing():
    result = verify_goal_postconditions(
        _goal(),
        write_receipts=[
            {"resource_type": "diet_record", "resource_id": "101"},
            {"resource_type": "diet_record", "resource_id": "102"},
        ],
        verification_result=json.dumps([
            {"id": 101, "meal_type": "breakfast", "calories": 280},
        ]),
    )

    assert result.satisfied is False
    assert result.missing_targets == ("lunch",)
    assert result.reason == "verification_targets_missing"


def test_goal_postconditions_do_not_accept_unreceipted_rows():
    result = verify_goal_postconditions(
        _goal(),
        write_receipts=[
            {"resource_type": "diet_record", "resource_id": "101"},
        ],
        verification_result=json.dumps([
            {"id": 101, "meal_type": "breakfast", "calories": 280},
            {"id": 102, "meal_type": "lunch", "calories": 520},
        ]),
    )

    assert result.satisfied is False
    assert result.reason == "write_receipts_missing"


def test_diet_postcondition_verifier_is_registered():
    assert registered_goal_verifier_kinds() == ("diet_recalculate_update",)


def test_unregistered_verified_goal_fails_closed():
    result = verify_goal_postconditions(
        GoalSpec(
            kind="unregistered_write",
            domain="health",
            operation="update",
            requires_verification=True,
        ),
        write_receipts=[],
        verification_result=None,
    )

    assert result.satisfied is False
    assert result.reason == "unsupported_goal_verifier"
