from pathlib import Path

import yaml

from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
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
        assert list(goal.target_meal_types) == expected["target_meal_types"], case["id"]
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
