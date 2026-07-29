from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from app.services.agent_kernel.goal_spec import (
    compile_goal_spec,
    format_goal_contract_prompt,
    registered_goal_compiler_names,
    registered_goal_prompt_kinds,
)
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    GoalSpec,
)
from app.services.agent_kernel.intent_frame import build_intent_frame


CASES = yaml.safe_load(
    (
        Path(__file__).parents[1]
        / "eval"
        / "datasets"
        / "agent_trajectories.yaml"
    ).read_text(encoding="utf-8")
)["cases"]


def _compile(case: dict):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text=case["user"],
    )
    intent = build_intent_frame(envelope, context)
    references = tuple(
        ActionableReference(
            kind=item["kind"],
            source_message_id=item.get("source_message_id"),
            data=item["data"],
        )
        for item in case.get("prior_actionable") or []
    )
    return compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
        actionable_references=references,
    )


def test_stateful_agent_trajectory_cases_compile_expected_goal():
    for case in CASES:
        goal = _compile(case)
        expected = case["expected"]

        assert goal.kind == expected["goal_kind"], case["id"]
        assert goal.domain == expected["domain"], case["id"]
        assert goal.operation == expected["operation"], case["id"]
        assert goal.target_date == expected["target_date"], case["id"]
        assert list(goal.target_meal_types) == expected["target_meal_types"], case["id"]
        assert goal.target_record_type == expected.get("target_record_type"), case["id"]
        assert dict(goal.target_values) == expected.get("target_values", {}), case["id"]
        assert goal.requires_lookup is expected["requires_lookup"], case["id"]
        assert goal.requires_verification is expected["requires_verification"], case["id"]
        assert list(goal.prohibited_operations) == expected["prohibited_operations"], case["id"]
        assert goal.requires_clarification is expected["clarification"], case["id"]


def test_recalculate_update_goal_keeps_visible_foods_as_context_not_write_authority():
    goal = _compile(CASES[0])

    assert goal.kind == "diet_recalculate_update"
    assert goal.target_date == "2026-07-24"
    assert goal.reference_foods == (
        ("breakfast", "豆腐脑约1碗 + 小笼包1个"),
        ("lunch", "三文鱼约1块 + 藜麦约半碗"),
    )
    assert "visible_card" in goal.evidence
    assert "existing_records_only" in goal.postconditions
    assert set(goal.prohibited_operations) == {"create", "delete"}


def test_recalculate_goal_uses_only_the_latest_card_date_for_visible_foods():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="重新估算和写入早午两餐",
    )
    intent = build_intent_frame(envelope, context)
    references = (
        ActionableReference(
            kind="diet_daily_summary",
            source_message_id="new",
            data={
                "record_date": "2026-07-24",
                "meals": [
                    {"meal_type": "breakfast", "food_items": "今天的小米粥"},
                    {"meal_type": "lunch", "food_items": "今天的三文鱼"},
                ],
            },
        ),
        ActionableReference(
            kind="diet_daily_summary",
            source_message_id="old",
            data={
                "record_date": "2026-07-23",
                "meals": [
                    {"meal_type": "breakfast", "food_items": "昨天的豆腐脑"},
                    {"meal_type": "lunch", "food_items": "昨天的牛肉面"},
                ],
            },
        ),
    )

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
        actionable_references=references,
    )

    assert goal.target_date == "2026-07-24"
    assert goal.reference_foods == (
        ("breakfast", "今天的小米粥"),
        ("lunch", "今天的三文鱼"),
    )


def test_explicit_relative_date_overrides_the_latest_visible_card_date():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="把昨天早饭和午饭重新算一下，直接更新记录",
    )
    intent = build_intent_frame(envelope, context)
    references = (
        ActionableReference(
            kind="diet_daily_summary",
            source_message_id="today",
            data={
                "record_date": "2026-07-17",
                "meals": [
                    {"meal_type": "breakfast", "food_items": "今天的小米粥"},
                    {"meal_type": "lunch", "food_items": "今天的三文鱼"},
                ],
            },
        ),
        ActionableReference(
            kind="diet_daily_summary",
            source_message_id="yesterday",
            data={
                "record_date": "2026-07-16",
                "meals": [
                    {"meal_type": "breakfast", "food_items": "昨天的豆腐脑"},
                    {"meal_type": "lunch", "food_items": "昨天的牛肉面"},
                ],
            },
        ),
    )

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
        actionable_references=references,
    )

    assert goal.kind == "diet_recalculate_update"
    assert goal.target_date == "2026-07-16"
    assert goal.target_meal_types == ("breakfast", "lunch")
    assert goal.reference_foods == (
        ("breakfast", "昨天的豆腐脑"),
        ("lunch", "昨天的牛肉面"),
    )


def test_colloquial_recalculate_and_write_back_resolves_visible_two_meals():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="把这两餐重估一下后补回记录",
    )
    intent = build_intent_frame(envelope, context)
    references = (
        ActionableReference(
            kind="diet_daily_summary",
            source_message_id="latest",
            data={
                "record_date": "2026-07-17",
                "meals": [
                    {"meal_type": "breakfast", "food_items": "小米粥"},
                    {"meal_type": "lunch", "food_items": "鸡胸肉沙拉"},
                ],
            },
        ),
    )

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
        actionable_references=references,
    )

    assert goal.kind == "diet_recalculate_update"
    assert goal.operation == "update"
    assert goal.target_meal_types == ("breakfast", "lunch")


def test_diet_goal_contract_is_registered_without_changing_public_facade():
    goal = _compile(CASES[0])

    assert registered_goal_compiler_names() == (
        "diet_recalculation",
        "simple_health_record",
    )
    assert registered_goal_prompt_kinds() == (
        "diet_recalculate_update",
        "simple_health_record",
    )
    assert "重新估算并更新" in format_goal_contract_prompt(goal)
    assert format_goal_contract_prompt(
        GoalSpec(kind="chat", domain="general", operation="none")
    ) == ""


def test_simple_water_goal_keeps_exact_normalized_amount():
    water_case = next(
        case
        for case in CASES
        if case["id"] == "water_record_explicit_chinese_amount"
    )

    goal = _compile(water_case)

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "water"
    assert dict(goal.target_values) == {"amount_ml": "500"}
    assert goal.requires_verification is True
    assert "只创建 1 条 water" in format_goal_contract_prompt(goal)


def test_simple_symptom_goal_binds_the_current_user_observation():
    symptom_case = next(
        case
        for case in CASES
        if case["id"] == "symptom_record_explicit_observation"
    )

    goal = _compile(symptom_case)

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "symptom"
    assert dict(goal.target_values) == {
        "body_part": "respiratory",
        "description": "记录刚才打了一个喷嚏",
    }
    prompt = format_goal_contract_prompt(goal)
    assert "记录刚才打了一个喷嚏" in prompt
    assert "只创建 1 条 symptom" in prompt


def test_simple_diet_goal_binds_explicit_meal_and_foods_from_current_turn():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录午餐5个虾100克大黄鱼200克哈密瓜",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.domain == "diet"
    assert goal.target_record_type == "diet"
    assert goal.target_date == context.current_time.date().isoformat()
    assert goal.target_meal_types == ("lunch",)
    assert dict(goal.target_values) == {
        "meal_type": "lunch",
        "food_items": "5个虾100克大黄鱼200克哈密瓜",
    }
    prompt = format_goal_contract_prompt(goal)
    assert "5个虾100克大黄鱼200克哈密瓜" in prompt
    assert "只创建 1 条 diet" in prompt
    assert "calories/protein/carbs/fat/fiber" in prompt


def test_simple_diet_goal_uses_user_owned_relative_date():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录昨天午餐牛肉面",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_date == (
        context.current_time.date() - timedelta(days=1)
    ).isoformat()


def test_simple_diet_goal_requires_food_details():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录午餐",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"
    assert goal.target_record_type is None


@pytest.mark.parametrize(
    ("message", "meal_type", "food_items"),
    (
        ("记录早餐两个豆腐包子", "breakfast", "两个豆腐包子"),
        ("帮我记录晚餐：牛肉饭", "dinner", "牛肉饭"),
        ("午餐吃了牛肉面，帮我记录一下", "lunch", "牛肉面"),
        (
            "记录早餐，吃了一个包子、一个茶叶蛋、一碗粥，计算热量和营养成分。",
            "breakfast",
            "一个包子、一个茶叶蛋、一碗粥",
        ),
        (
            "记录早餐吃了一个包子一个茶叶蛋一碗粥计算热量和营养成分",
            "breakfast",
            "一个包子一个茶叶蛋一碗粥",
        ),
        (
            "记录午餐牛肉面，并帮我估算一下热量和蛋白质",
            "lunch",
            "牛肉面",
        ),
        (
            "记录晚餐吃了沙拉，同时计算这餐的卡路里、蛋白质、碳水、脂肪和膳食纤维",
            "dinner",
            "沙拉",
        ),
        ("记录早餐包子需要计算热量", "breakfast", "包子"),
        ("记录早餐包子帮忙估算热量", "breakfast", "包子"),
        ("记录早餐包子算算热量", "breakfast", "包子"),
        ("记录早餐包子不需要计算热量", "breakfast", "包子"),
        ("记录早餐包子不用帮忙估算营养成分", "breakfast", "包子"),
        ("记录早餐包子无需再分析宏量营养素", "breakfast", "包子"),
        ("记录午餐低热量沙拉", "lunch", "低热量沙拉"),
        ("记录加餐 苹果一个", "snack", "苹果一个"),
    ),
)
def test_simple_diet_goal_accepts_common_text_record_variants(
    message, meal_type, food_items
):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_meal_types == (meal_type,)
    assert dict(goal.target_values) == {
        "meal_type": meal_type,
        "food_items": food_items,
    }


def test_simple_diet_goal_does_not_collapse_multiple_meals():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录早餐鸡蛋和午餐牛肉面",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"
    assert goal.target_record_type is None


@pytest.mark.parametrize(
    ("message", "food_items"),
    (
        ("记录午餐牛肉面不要辣", "牛肉面不要辣"),
        ("记录午餐牛肉面别放香菜", "牛肉面别放香菜"),
        ("记录午餐牛肉面需要少盐", "牛肉面需要少盐"),
    ),
)
def test_simple_diet_goal_keeps_food_preference_language(message, food_items):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "diet"
    assert dict(goal.target_values)["food_items"] == food_items


def test_simple_diet_goal_respects_explicit_write_cancellation():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="不要记录午餐牛肉面",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"


@pytest.mark.parametrize(
    "message",
    (
        "记录2026-02-30午餐牛肉面",
        "记录2月30日午餐牛肉面",
    ),
)
def test_invalid_explicit_diet_date_requires_clarification(message):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "clarify"
    assert goal.target_date is None
    assert goal.requires_clarification is True
    assert "create" in goal.prohibited_operations
    assert "invalid_explicit_date" in goal.evidence


@pytest.mark.parametrize(
    ("message", "amount_ml"),
    (
        ("记录喝水了大约五百毫升", "500"),
        ("记录饮水半升", "500"),
        ("记录补水1千毫升", "1000"),
    ),
)
def test_simple_water_goal_normalizes_natural_amount_variants(
    message, amount_ml
):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text=message,
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "water"
    assert dict(goal.target_values) == {"amount_ml": amount_ml}


def test_simple_record_goal_does_not_claim_authority_on_attachment_turn():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录喝水五百毫升",
        media=({"kind": "image"},),
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"
    assert goal.target_record_type is None


@pytest.mark.parametrize(
    "message",
    (
        "记录早餐鸡蛋和喝水300ml",
        "记录喝水300ml和喝水200ml",
        "记录刚才打了一个喷嚏并喝水300ml",
        "记录刚才打了一个喷嚏和咳嗽一次",
    ),
)
def test_simple_record_goal_does_not_collapse_compound_writes(message):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text=message,
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"
    assert goal.target_record_type is None
