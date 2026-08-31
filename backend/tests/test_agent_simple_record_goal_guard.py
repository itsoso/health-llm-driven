import json

import pytest

from app.services.agent_executor import (
    _build_deterministic_simple_record_tool_call,
    _build_deterministic_supplement_record_tool_calls,
    _enrich_simple_diet_goal_tool_calls,
    _estimate_simple_diet_nutrition,
    _normalize_goal_guarded_tool_calls,
    _simple_diet_nutrition_estimator_model_name,
    _simple_diet_nutrition_is_complete,
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
        target_date="2026-07-26",
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
            "record_date": "2026-07-26",
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


def test_diet_goal_keeps_model_nutrition_when_food_matches_but_meal_type_differs():
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
                    "meal_type": "lunch",
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
                "牛排和蔬菜，520千卡，蛋白质42克，碳水18克，脂肪30克，膳食纤维5克",
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
    normalized_data = json.loads(normalized[0]["function"]["arguments"])["data"]

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
    normalized_data = json.loads(normalized[0]["function"]["arguments"])["data"]

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
    normalized_data = json.loads(normalized[0]["function"]["arguments"])["data"]

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
    normalized_data = json.loads(normalized[0]["function"]["arguments"])["data"]

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
    normalized_data = json.loads(normalized[0]["function"]["arguments"])["data"]

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


def test_explicit_multiple_supplements_build_deterministic_calls():
    calls = _build_deterministic_supplement_record_tool_calls(
        "记录下来，吃了一粒甘氨酸镁和一粒褪黑素。",
        write_receipts=[],
    )

    assert [
        json.loads(call["function"]["arguments"])["data"]["supplement_name"]
        for call in calls
    ] == ["甘氨酸镁", "褪黑素"]
    assert all(call["function"]["name"] == "health_record" for call in calls)


def test_contextual_all_supplements_builds_only_owner_authorized_calls():
    calls = _build_deterministic_supplement_record_tool_calls(
        "全部已服用",
        contextual_supplement_names=("NOW Melatonin 3mg", "甘氨酸镁"),
        write_receipts=[],
    )

    assert [
        json.loads(call["function"]["arguments"])["data"]["supplement_name"]
        for call in calls
    ] == ["NOW Melatonin 3mg", "甘氨酸镁"]
    assert _build_deterministic_supplement_record_tool_calls(
        "全部已服用",
        contextual_supplement_names=(),
        write_receipts=[],
    ) == []
    assert _build_deterministic_supplement_record_tool_calls(
        "全部已服用",
        contextual_supplement_names=("甘氨酸镁",),
        write_receipts=[{"resource_id": "1", "verified": True}],
    ) == []


@pytest.mark.parametrize(
    "name",
    (
        "SLE",
        "1型糖尿病",
        "IgA肾病",
        "β地中海贫血",
        "HER2阳性乳腺癌",
        "COVID-19肺炎",
        "H1N1流感",
        "HIV感染",
        "脑梗",
        "睡眠呼吸暂停",
        "偏头痛",
        "慢性疼痛",
        "高血压",
        "低血压",
        "妊娠高血压",
        "运动障碍",
        "运动性哮喘",
        "体重相关性闭经",
        "运动诱发过敏",
    ),
)
def test_illness_goal_builds_deterministic_write_when_model_omits_tool_call(name):
    goal = GoalSpec(
        kind="simple_health_record",
        domain="illness",
        operation="create",
        target_record_type="illness",
        target_values=(("name", name),),
        requires_verification=True,
    )

    tool_call = _build_deterministic_simple_record_tool_call(
        goal,
        write_receipts=[],
    )

    assert tool_call is not None
    assert tool_call["function"]["name"] == "health_record"
    assert json.loads(tool_call["function"]["arguments"]) == {
        "record_type": "illness",
        "data": {"name": name},
    }


@pytest.mark.asyncio
async def test_diet_goal_server_fills_missing_nutrition_without_changing_food(
    monkeypatch,
):
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-08-02",
        target_meal_types=("snack",),
        target_record_type="diet",
        target_values=(
            ("meal_type", "snack"),
            ("food_items", "一个桃子"),
        ),
        requires_verification=True,
    )
    calls = _normalize_goal_guarded_tool_calls(
        [
            _tool_call(
                "peach-without-nutrition",
                {
                    "record_type": "diet",
                    "data": {
                        "meal_type": "snack",
                        "food_items": "一个桃子",
                    },
                },
            ),
        ],
        goal,
    )
    observed_foods = []

    async def fake_estimate(food_items):
        observed_foods.append(food_items)
        return {
            "calories": 58,
            "protein": 1.4,
            "carbs": 14,
            "fat": 0.4,
            "fiber": 2.3,
        }

    monkeypatch.setattr(
        "app.services.agent_executor._estimate_simple_diet_nutrition",
        fake_estimate,
    )

    enriched, attempted = await _enrich_simple_diet_goal_tool_calls(
        calls,
        goal,
        estimation_attempted=False,
        runtime_write_blocked=False,
    )

    assert attempted is True
    assert observed_foods == ["一个桃子"]
    assert json.loads(enriched[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "data": {
            "record_date": "2026-08-02",
            "meal_type": "snack",
            "food_items": "一个桃子",
            "source": "agent_text",
            "calories": 58,
            "protein": 1.4,
            "carbs": 14,
            "fat": 0.4,
            "fiber": 2.3,
        },
    }


@pytest.mark.asyncio
async def test_diet_goal_reuses_one_estimate_for_duplicate_canonical_calls(
    monkeypatch,
):
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-08-02",
        target_meal_types=("snack",),
        target_record_type="diet",
        target_values=(("meal_type", "snack"), ("food_items", "一个桃子")),
        requires_verification=True,
    )
    calls = _normalize_goal_guarded_tool_calls(
        [
            _tool_call(
                call_id,
                {
                    "record_type": "diet",
                    "data": {
                        "meal_type": "snack",
                        "food_items": "一个桃子",
                    },
                },
            )
            for call_id in ("duplicate-peach-a", "duplicate-peach-b")
        ],
        goal,
    )
    estimate_calls = []

    async def fake_estimate(food_items):
        estimate_calls.append(food_items)
        return {
            "calories": 58,
            "protein": 1.4,
            "carbs": 14,
            "fat": 0.4,
            "fiber": 2.3,
        }

    monkeypatch.setattr(
        "app.services.agent_executor._estimate_simple_diet_nutrition",
        fake_estimate,
    )

    enriched, attempted = await _enrich_simple_diet_goal_tool_calls(
        calls,
        goal,
        estimation_attempted=False,
        runtime_write_blocked=False,
    )

    assert attempted is True
    assert estimate_calls == ["一个桃子"]
    assert len(enriched) == 2
    assert json.loads(enriched[0]["function"]["arguments"]) == json.loads(
        enriched[1]["function"]["arguments"]
    )


@pytest.mark.asyncio
async def test_diet_goal_does_not_estimate_while_runtime_write_is_blocked(
    monkeypatch,
):
    goal = GoalSpec(
        kind="simple_health_record",
        domain="diet",
        operation="create",
        target_date="2026-08-02",
        target_meal_types=("snack",),
        target_record_type="diet",
        target_values=(("meal_type", "snack"), ("food_items", "一个桃子")),
        requires_verification=True,
    )
    calls = _normalize_goal_guarded_tool_calls(
        [_tool_call("blocked-peach", {"record_type": "diet", "data": {}})],
        goal,
    )

    async def fail_if_called(_food_items):
        raise AssertionError("blocked writes must not call the nutrition provider")

    monkeypatch.setattr(
        "app.services.agent_executor._estimate_simple_diet_nutrition",
        fail_if_called,
    )

    unchanged, attempted = await _enrich_simple_diet_goal_tool_calls(
        calls,
        goal,
        estimation_attempted=False,
        runtime_write_blocked=True,
    )

    assert unchanged == calls
    assert attempted is False


@pytest.mark.parametrize(
    "estimate",
    [
        {"calories": 58, "protein": 1.4, "carbs": 14, "fat": 0.4},
        {
            "calories": 58,
            "protein": 1.4,
            "carbs": 14,
            "fat": 0.4,
            "fiber": float("nan"),
        },
        {
            "calories": 5001,
            "protein": 1.4,
            "carbs": 14,
            "fat": 0.4,
            "fiber": 2.3,
        },
        {
            "calories": 58,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "fiber": 2.3,
        },
    ],
)
def test_simple_diet_nutrition_rejects_incomplete_or_unbounded_estimates(estimate):
    assert _simple_diet_nutrition_is_complete(estimate) is False


def test_simple_diet_nutrition_accepts_alcohol_energy_with_zero_macros():
    assert (
        _simple_diet_nutrition_is_complete(
            {
                "calories": 105,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
                "fiber": 0,
                "alcohol_units": 1.5,
            }
        )
        is True
    )


def test_simple_diet_nutrition_metric_reports_configured_provider_model(
    monkeypatch,
):
    from app.services.ai.food_recognition import food_recognition_service

    monkeypatch.setattr(
        food_recognition_service,
        "_provider",
        type("Provider", (), {"model": "qwen3.6-flash"})(),
    )

    assert _simple_diet_nutrition_estimator_model_name() == "qwen3.6-flash"


@pytest.mark.asyncio
async def test_simple_diet_estimator_uses_sanitized_food_totals(monkeypatch):
    def fake_estimate(_food_items, *, timeout_seconds=None):
        assert timeout_seconds is not None
        return {
            "success": True,
            "foods": [
                {
                    "name": "桃子",
                    "quantity": "1个",
                    "calories": 58,
                    "protein": 1.4,
                    "carbs": 14,
                    "fat": 0.4,
                    "fiber": 2.3,
                }
            ],
            # These untrusted aggregate fields must not bypass sanitization.
            "total_calories": 4999,
            "total_protein": 999,
        }

    monkeypatch.setattr(
        "app.services.ai.food_recognition.food_recognition_service."
        "estimate_nutrition_from_text",
        fake_estimate,
    )

    estimate = await _estimate_simple_diet_nutrition("一个桃子")

    assert estimate == {
        "calories": 58.0,
        "protein": 1.4,
        "carbs": 14.0,
        "fat": 0.4,
        "fiber": 2.3,
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
    parsed = [json.loads(call["function"]["arguments"]) for call in normalized]

    assert parsed[0] == parsed[1]
    assert parsed[0]["data"]["record_date"] == "2026-07-26"
    assert _write_operation_fingerprint(
        "health_record", parsed[0]
    ) == _write_operation_fingerprint("health_record", parsed[1])


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
            "arguments": json.dumps(
                {
                    "record_type": "symptom",
                    "operation": "delete",
                    "record_id": 75,
                }
            ),
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
            "arguments": json.dumps(
                {
                    "record_type": "water",
                    "operation": "list",
                    "date": "2026-07-28",
                }
            ),
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
