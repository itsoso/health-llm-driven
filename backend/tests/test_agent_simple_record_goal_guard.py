import json

from app.services.agent_executor import (
    _build_deterministic_simple_record_tool_call,
    _normalize_goal_guarded_tool_calls,
    _write_operation_fingerprint,
)
from app.services.agent_kernel.types import GoalSpec


def _tool_call(
    call_id: str,
    arguments: dict,
    *,
    name: str = "health_record",
) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def test_water_goal_replaces_model_amount_and_record_type_with_goal_payload():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="water",
        operation="create",
        target_date="2026-07-26",
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
        "data": {"amount": 500, "record_date": "2026-07-26"},
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


def test_diet_goal_keeps_model_nutrition_when_food_list_replaces_conjunction():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("dinner",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "dinner"),
            (
                "food_items",
                "牛排和蔬菜，520千卡，蛋白质42克，碳水18克，"
                "脂肪30克，膳食纤维5克",
            ),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "equivalent-diet-list",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": [
                        {"name": "牛排"},
                        {"name": "蔬菜"},
                    ],
                    "calories": 520,
                    "protein": 42,
                    "carbs": 18,
                    "fat": 30,
                    "fiber": 5,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    normalized_data = json.loads(
        normalized[0]["function"]["arguments"]
    )["data"]

    assert normalized_data["food_items"] == "牛排和蔬菜"
    assert normalized_data["calories"] == 520
    assert normalized_data["protein"] == 42
    assert normalized_data["fiber"] == 5


def test_diet_goal_does_not_split_lexicalized_food_name_on_conjunction():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("lunch",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "lunch"),
            ("food_items", "牛肉和风沙拉"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "ambiguous-conjunction-diet",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "lunch",
                    "food_items": [
                        {"name": "牛肉"},
                        {"name": "风沙拉"},
                    ],
                    "calories": 480,
                    "protein": 35,
                    "carbs": 20,
                    "fat": 28,
                    "fiber": 6,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    normalized_data = json.loads(
        normalized[0]["function"]["arguments"]
    )["data"]

    assert normalized_data["food_items"] == "牛肉和风沙拉"
    assert "calories" not in normalized_data
    assert "protein" not in normalized_data


def test_diet_goal_rejects_model_nutrition_that_conflicts_with_user_values():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("dinner",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "dinner"),
            ("food_items", "牛排和蔬菜，520千卡，蛋白质42克"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "conflicting-diet-estimate",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": "牛排, 蔬菜",
                    "calories": 800,
                    "protein": 42,
                    "carbs": 18,
                    "fat": 30,
                    "fiber": 5,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    normalized_data = json.loads(
        normalized[0]["function"]["arguments"]
    )["data"]

    assert normalized_data["food_items"].startswith("牛排和蔬菜")
    assert "calories" not in normalized_data
    assert "protein" not in normalized_data


def test_diet_goal_keeps_complete_estimate_after_analysis_suffix_is_removed():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("breakfast",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "breakfast"),
            ("food_items", "一个包子、一个茶叶蛋、一碗粥"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "estimated-breakfast",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "一个包子，一个茶叶蛋，一碗粥",
                    "calories": 520,
                    "protein": 20,
                    "carbs": 72,
                    "fat": 17,
                    "fiber": 4,
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
            "food_items": "一个包子，一个茶叶蛋，一碗粥",
            "calories": 520,
            "protein": 20,
            "carbs": 72,
            "fat": 17,
            "fiber": 4,
            "source": "agent_text",
        },
    }


def test_diet_goal_keeps_estimate_when_quantity_moves_after_food_name():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("breakfast",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "breakfast"),
            ("food_items", "一个包子、一个茶叶蛋、一碗粥"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "estimated-breakfast",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "包子1个，茶叶蛋1个，粥1碗",
                    "calories": 520,
                    "protein": 20,
                    "carbs": 72,
                    "fat": 17,
                    "fiber": 4,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    normalized_data = json.loads(
        normalized[0]["function"]["arguments"]
    )["data"]

    assert normalized_data["calories"] == 520
    assert normalized_data["protein"] == 20
    assert normalized_data["food_items"] == "包子1个，茶叶蛋1个，粥1碗"


def test_diet_goal_does_not_treat_lexicalized_dish_as_quantity_expression():
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-07-26",
        target_meal_types=("dinner",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "dinner"),
            ("food_items", "三杯鸡"),
        ),
        requires_verification=True,
    )
    calls = [
        _tool_call(
            "wrong-dish-estimate",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": "鸡3杯",
                    "calories": 900,
                    "protein": 80,
                    "carbs": 20,
                    "fat": 50,
                    "fiber": 1,
                },
            },
        ),
    ]

    normalized = _normalize_goal_guarded_tool_calls(calls, goal)
    normalized_data = json.loads(
        normalized[0]["function"]["arguments"]
    )["data"]

    assert normalized_data["food_items"] == "三杯鸡"
    assert "calories" not in normalized_data
    assert "protein" not in normalized_data


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
        target_date="2026-07-26",
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
    assert parsed[0]["data"]["record_date"] == "2026-07-26"
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


def test_read_only_goal_blocks_cross_domain_delete_tool_call():
    goal = GoalSpec(
        kind="answer",
        domain="symptom",
        operation="ask",
        prohibited_operations=("create", "update", "delete"),
    )
    call = {
        "id": "unsafe-delete",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "symptom",
                "operation": "delete",
                "record_id": 75,
            }),
        },
    }

    assert _normalize_goal_guarded_tool_calls([call], goal) == []


def test_read_only_goal_keeps_read_tool_call():
    goal = GoalSpec(
        kind="answer",
        domain="water",
        operation="ask",
        prohibited_operations=("create", "update", "delete"),
    )
    call = {
        "id": "safe-list",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "water",
                "operation": "list",
                "date": "2026-07-28",
            }),
        },
    }

    assert _normalize_goal_guarded_tool_calls([call], goal) == [call]


def test_read_only_goal_blocks_receipt_exempt_background_sync():
    goal = GoalSpec(
        kind="answer",
        domain="device",
        operation="ask",
        prohibited_operations=("create", "update", "delete"),
    )
    call = _tool_call(
        "unsafe-sync",
        {"record_type": "garmin_sync", "data": {}},
    )

    assert _normalize_goal_guarded_tool_calls([call], goal) == []


def test_diet_recalculation_blocks_cross_domain_health_record_create():
    goal = GoalSpec(
        kind="diet_recalculate_update",
        domain="diet",
        operation="update",
        target_date="2026-07-28",
        target_meal_types=("breakfast", "lunch"),
        prohibited_operations=("create", "delete"),
        requires_lookup=True,
        requires_verification=True,
    )
    call = _tool_call(
        "unsafe-symptom",
        {
            "record_type": "symptom",
            "data": {"description": "synthetic"},
        },
    )

    assert _normalize_goal_guarded_tool_calls([call], goal) == []


def test_diet_recalculation_blocks_cross_domain_health_manage_update():
    goal = GoalSpec(
        kind="diet_recalculate_update",
        domain="diet",
        operation="update",
        target_date="2026-07-28",
        target_meal_types=("breakfast", "lunch"),
        prohibited_operations=("create", "delete"),
        requires_lookup=True,
        requires_verification=True,
    )
    call = _tool_call(
        "unsafe-symptom-update",
        {
            "record_type": "symptom",
            "operation": "update",
            "record_id": 88,
            "data": {"description": "synthetic"},
        },
        name="health_manage",
    )

    assert _normalize_goal_guarded_tool_calls([call], goal) == []
