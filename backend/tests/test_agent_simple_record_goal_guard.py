import json

from app.services.agent_executor import (
    _build_deterministic_simple_record_tool_call,
    _normalize_goal_guarded_tool_calls,
    _write_operation_fingerprint,
)
from app.services.agent_kernel.types import GoalSpec


def _tool_call(call_id: str, arguments: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def test_water_goal_replaces_model_amount_and_record_type_with_goal_payload():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="water",
        operation="create",
        target_record_type="water",
        target_values=(("amount_ml", "500"),),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "wrong-water",
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛",
                    "amount": 300,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    function = normalized[0]["function"]

    assert function["name"] == "health_record"
    assert json.loads(function["arguments"]) == {
        "record_type": "water",
        "data": {"amount": 500},
    }


def test_symptom_goal_replaces_model_invented_symptom_with_current_turn_payload():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="symptom",
        operation="create",
        target_record_type="symptom",
        target_values=(
            ("body_part", "respiratory"),
            ("description", "记录刚才打了一个喷嚏"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "wrong-symptom",
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛",
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)

    assert json.loads(normalized[0]["function"]["arguments"]) == {
        "record_type": "symptom",
        "data": {
            "body_part": "respiratory",
            "description": "记录刚才打了一个喷嚏",
        },
    }


def test_diet_goal_replaces_model_foods_with_current_turn_payload():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("lunch",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "lunch"),
            ("food_items", "5个虾100克大黄鱼200克哈密瓜"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "wrong-diet",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": "牛肉面",
                    "calories": 900,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)

    assert json.loads(normalized[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-26",
            "meal_type": "lunch",
            "food_items": "5个虾100克大黄鱼200克哈密瓜",
            "source": "agent_text",
        },
    }


def test_diet_goal_keeps_model_nutrition_when_food_text_is_equivalent():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("breakfast",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "breakfast"),
            ("food_items", "两个鸡蛋一杯牛奶"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "equivalent-diet",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "两个鸡蛋,一杯牛奶",
                    "calories": 280,
                    "protein": 20,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)

    assert json.loads(normalized[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-26",
            "meal_type": "breakfast",
            "food_items": "两个鸡蛋,一杯牛奶",
            "calories": 280,
            "protein": 20,
            "source": "agent_text",
        },
    }


def test_diet_goal_builds_deterministic_write_when_model_omits_tool_call():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("lunch",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "lunch"),
            ("food_items", "5个虾100克大黄鱼200克哈密瓜"),
        ),
        requires_verification=True,
    )

    tool_call = _build_deterministic_simple_record_tool_call(
        goal,
        write_receipts=[],
    )

    assert tool_call is not None
    assert tool_call["function"]["name"] == "health_record"
    assert json.loads(tool_call["function"]["arguments"]) == {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-26",
            "meal_type": "lunch",
            "food_items": "5个虾100克大黄鱼200克哈密瓜",
            "source": "agent_text",
        },
    }


def test_equivalent_model_writes_share_one_canonical_fingerprint():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="water",
        operation="create",
        target_record_type="water",
        target_values=(("amount_ml", "500"),),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "first",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        _tool_call(
            "second",
            {
                "record_type": "water",
                "data": {"drink_type": "water", "amount": 500.0},
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    parsed = [
        json.loads(call["function"]["arguments"])
        for call in normalized
    ]

    assert parsed[0] == parsed[1]
    assert (
        _write_operation_fingerprint("health_record", parsed[0])
        == _write_operation_fingerprint("health_record", parsed[1])
    )


def test_invalid_simple_goal_blocks_model_write_instead_of_failing_open():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="water",
        operation="create",
        target_record_type="water",
        target_values=(),
        requires_verification=True,
    )

    normalized = _normalize_goal_guarded_tool_calls(
        [
            _tool_call(
                "invented",
                {"record_type": "water", "data": {"amount": 300}},
            ),
        ],
        goal,
    )

    assert normalized == []
