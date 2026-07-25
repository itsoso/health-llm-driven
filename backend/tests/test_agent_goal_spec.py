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
