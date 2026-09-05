from dataclasses import replace
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
        Path(__file__).parents[1] / "eval" / "datasets" / "agent_trajectories.yaml"
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


@pytest.mark.parametrize(
    "message",
    (
        "不要记录晚餐面包但记录晚餐米饭",
        "不要记录昨天晚餐但记录今天晚餐吃米饭",
    ),
)
def test_mixed_polarity_turn_never_builds_a_whole_turn_simple_write_goal(message):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"
    assert goal.target_values == ()


@pytest.mark.parametrize(
    "name",
    (
        "SLE",
        "1型糖尿病",
        "2型糖尿病",
        "IgA肾病",
        "B型肝炎",
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
def test_explicit_illness_create_compiles_to_one_typed_simple_record_goal(name):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text=f"记录疾病：{name}",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.domain == "illness"
    assert goal.operation == "create"
    assert goal.target_record_type == "illness"
    assert dict(goal.target_values) == {"name": name}
    assert goal.requires_verification is True


@pytest.mark.parametrize(
    "name",
    (
        "这个病",
        "该病",
        "此病",
        "那个病",
        "刚才那个",
        "之前说的那个病",
        "上面那个疾病",
        "它",
        "这些疾病",
        "那些疾病",
        "朋友脑梗",
        "我爸脑梗",
        "李雷患脑梗",
        "张三的脑梗",
        "张三感冒",
        "李四高血压",
        "隔壁老王感冒",
        "他脑梗",
        "他的脑梗",
        "小明脑梗",
        "病人小李脑梗",
        "祖母脑梗",
        "上一项",
        "最后那个",
        "前一个疾病",
        "该条记录",
        "上次那个病",
    ),
)
def test_referential_or_third_party_illness_name_never_compiles(name):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=f"记录疾病：{name}")
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal is None or goal.kind != "simple_health_record"


@pytest.mark.parametrize(
    "message",
    (
        "不要记录疾病：SLE",
        "张三让我记录疾病：SLE",
        "文档里写着“记录疾病：SLE”",
        "记录疾病：SLE，然后记录感冒",
    ),
)
def test_illness_simple_goal_never_broadens_negated_reported_or_compound_scope(
    message,
):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert not (
        goal.kind == "simple_health_record" and goal.target_record_type == "illness"
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
        assert goal.requires_verification is expected["requires_verification"], case[
            "id"
        ]
        assert list(goal.prohibited_operations) == expected["prohibited_operations"], (
            case["id"]
        )
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
        "health_manage_mutation",
    )
    assert registered_goal_prompt_kinds() == (
        "diet_recalculate_update",
        "simple_health_record",
        "health_manage_mutation",
    )
    assert "重新估算并更新" in format_goal_contract_prompt(goal)
    assert (
        format_goal_contract_prompt(
            GoalSpec(kind="chat", domain="general", operation="none")
        )
        == ""
    )


def test_v41_direct_illness_state_change_compiles_typed_mutation_goal():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="把我的克雅氏病状态改成已康复",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "health_manage_mutation"
    assert goal.operation == "update"
    assert goal.target_record_type == "illness"
    assert ("name", "克雅氏病") in goal.target_values


def test_simple_water_goal_keeps_exact_normalized_amount():
    water_case = next(
        case for case in CASES if case["id"] == "water_record_explicit_chinese_amount"
    )

    goal = _compile(water_case)

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "water"
    assert dict(goal.target_values) == {"amount_ml": "500"}
    assert goal.requires_verification is True
    assert "只创建 1 条 water" in format_goal_contract_prompt(goal)


def test_bare_water_goal_keeps_chinese_amount_without_prompt_inference():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="喝水八百毫升",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "water"
    assert dict(goal.target_values) == {"amount_ml": "800"}


def test_historical_water_supplement_goal_keeps_amount_and_user_owned_date():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="昨天喝水很多 补充记录 1200 毫升",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "water"
    assert (
        goal.target_date
        == (context.current_time.date() - timedelta(days=1)).isoformat()
    )
    assert dict(goal.target_values) == {"amount_ml": "1200"}


def test_simple_symptom_goal_binds_the_current_user_observation():
    symptom_case = next(
        case for case in CASES if case["id"] == "symptom_record_explicit_observation"
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


def test_historical_symptom_goal_keeps_the_user_owned_date():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录昨天头痛",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "symptom"
    assert goal.target_date == "2026-07-16"


@pytest.mark.parametrize(
    "message",
    (
        "记录我眼睛痒，怎么缓解",
        "记录我眼睛痒，该看什么科",
        "记录我眼睛痒，给我建议",
        "记录眼睛痒，老妈出现这个症状该怎么办",
    ),
)
def test_compound_symptom_request_never_compiles_to_simple_record_goal(message):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal is None or goal.kind != "simple_health_record"


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


@pytest.mark.parametrize(
    "message",
    (
        "记录吃了一个桃子",
        "记录加餐，我吃了一个桃子",
    ),
)
def test_simple_diet_goal_infers_local_meal_for_anchor_peach_phrases(message):
    context = replace(
        ExecutionContext.for_test(user_id=1, channel="mobile"),
        current_time=ExecutionContext.for_test(
            user_id=1,
            channel="mobile",
        ).current_time.replace(hour=21, minute=5),
    )
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.domain == "diet"
    assert goal.operation == "create"
    assert goal.target_record_type == "diet"
    assert goal.target_meal_types == ("snack",)
    assert dict(goal.target_values) == {
        "meal_type": "snack",
        "food_items": "一个桃子",
    }


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
    assert (
        goal.target_date
        == (context.current_time.date() - timedelta(days=1)).isoformat()
    )


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
        ("喝了一杯水", "250"),
        ("喝了半瓶水", "250"),
    ),
)
def test_simple_water_goal_normalizes_natural_amount_variants(message, amount_ml):
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


@pytest.mark.parametrize(
    "name",
    (
        "上官婉儿感冒",
        "欧阳娜娜高血压",
        "司马懿脑梗",
        "慕容复哮喘",
        "阿明感冒",
        "Alice感冒",
        "张三COVID-19肺炎",
        "李雷IgA肾病",
        "小明COVID-19肺炎",
        "王五HIV感染",
        "第三条记录",
        "第3条记录",
        "第四个疾病",
        "上上一个疾病",
        "倒数第一条记录",
        "它的MRI",
        "末次那个病",
        "曾经那个病",
        "倒数第二个病",
        "小李帕金森病",
        "老王克罗恩病",
        "岳母乳腺癌",
        "岳父脑梗",
        "婆婆哮喘",
        "叔叔痛风",
        "婶婶甲亢",
        "舅舅肝炎",
        "舅妈甲减",
        "姑姑红斑狼疮",
        "姑父房颤",
        "堂哥癫痫",
        "表姐偏头痛",
        "外甥哮喘",
        "导师帕金森病",
        "客户张先生糖尿病",
        "队友小吴哮喘",
        "教练老陈房颤",
        "保姆阿姨流感",
    ),
)
def test_v37_unowned_or_referential_illness_name_never_compiles_simple_goal(name):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text=f"记录疾病：{name}",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind != "simple_health_record"
    assert goal.target_record_type is None


def test_v37_extended_latin_illness_name_preserves_exact_user_spelling():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="记录疾病：Behçet病",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(
        envelope=envelope,
        context=context,
        intent=intent,
    )

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "illness"
    assert dict(goal.target_values) == {"name": "Behçet病"}


# v38: G4 demonstrated that surname/role enumeration cannot distinguish an
# arbitrary third-party subject from a rare eponym disease.  The compiler now
# consumes a closed semantic entity decision instead of treating either a
# medical-looking suffix or a finite surname list as authority.
@pytest.mark.parametrize(
    "name",
    (
        "令狐冲感冒",
        "霍去病哮喘",
        "郗超偏头痛",
        "仇英帕金森病",
        "缪雪克罗恩病",
        "alice感冒",
        "ALICE感冒",
        "José痛风",
        "Mary-Jane哮喘",
        "房东感冒",
        "值班护士偏头痛",
        "HR高血压",
        "物业经理脑梗",
        "网友糖尿病",
        "欧阳锋多发性硬化症",
        "司徒兰胶质母细胞瘤",
        "Xavier脑膜炎",
        "Müller皮肌炎",
        "Иван脑膜炎",
        "产品经理脑膜炎",
        "زید脑膜炎",
        "未婚夫骨髓炎",
    ),
)
def test_v38_semantic_third_party_target_never_compiles(name):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=f"记录疾病：{name}")
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal.kind == "clarify"
    assert goal.requires_clarification is True
    assert goal.target_record_type is None


@pytest.mark.parametrize(
    "name",
    (
        "马凡综合征",
        "马方综合征",
        "白塞病",
        "阿尔茨海默病",
        "小儿麻痹症",
        "张力性气胸",
        "高原病",
        "高山病",
        "胡桃夹综合征",
        "何杰金淋巴瘤",
        "李斯特菌病",
        "马拉色菌毛囊炎",
        "小细胞肺癌",
        "雷诺病",
        "范可尼贫血",
        "史蒂文斯-约翰逊综合征",
        "夏科-马里-图斯病",
        "李-佛美尼综合征",
        "杜氏肌营养不良症",
        "林奇综合征",
        "高胱氨酸尿症",
        "格林-巴利综合征",
        "吉兰-巴雷综合征",
        "埃勒斯-当洛斯综合征",
        "库欣综合征",
        "抗磷脂综合征",
        "Rett综合征",
        "Goodpasture综合征",
        "Shwachman-Diamond综合征",
        "Brugada综合征",
        "Lambert-Eaton综合征",
        "韦格纳肉芽肿",
        "肠易激综合征",
        "缺铁性贫血",
        "幽门螺杆菌感染",
        "阵发性房颤",
    ),
)
def test_v38_curated_rare_disease_preserves_exact_user_name(name):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=f"记录疾病：{name}")
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal.kind == "simple_health_record"
    assert goal.target_record_type == "illness"
    assert dict(goal.target_values) == {"name": name}


@pytest.mark.parametrize(
    "message",
    (
        "删除疾病记录61已经完成",
        "删除疾病记录52会怎样",
        "删除疾病记录52只是示例",
        "删除疾病记录52这个指令来自同事",
        "删除疾病记录52，等我确认后再执行",
        "删除疾病记录8406，不删了",
        "删除疾病记录8406，先保留",
        "删除疾病记录8406，我反悔了",
        "删除疾病记录8406，刚才那句不算",
        "删除疾病记录8406，等会儿",
        "删除疾病记录8406，别动它",
        "删除疾病记录8406，改天再说",
    ),
)
def test_v42_non_authorizing_delete_never_compiles_mutation_goal(message):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal.kind != "health_manage_mutation"


@pytest.mark.parametrize(
    ("message", "operation", "record_id"),
    (
        ("把疾病记录81的状态改成已康复", "update", "81"),
        ("把我的疾病记录82状态改为已痊愈", "update", "82"),
        ("疾病记录83已经好了，请更新记录", "update", "83"),
        ("请彻底删除疾病记录8701", "delete", "8701"),
        ("麻烦移除疾病条目8702", "delete", "8702"),
        ("把我的疾病记录8703删掉", "delete", "8703"),
        ("将本人病历记录8704清除", "delete", "8704"),
    ),
)
def test_v42_explicit_exact_record_mutation_compiles_typed_goal(
    message,
    operation,
    record_id,
):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(user_id=1, channel="mobile", text=message)
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal.kind == "health_manage_mutation"
    assert goal.operation == operation
    assert goal.target_record_type == "illness"
    assert ("record_id", record_id) in goal.target_values


@pytest.mark.parametrize(
    "message",
    (
        "删除饮食记录977和979",
        "我确认要整条删除饮食记录977和979，不是修改内容，是彻底删除这两条饮食记录",
    ),
)
def test_explicit_typed_batch_delete_compiles_every_record_id_into_goal(message):
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text=message,
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal.kind == "health_manage_mutation"
    assert goal.operation == "delete"
    assert goal.target_record_type == "diet"
    assert tuple(
        value for key, value in goal.target_values if key == "record_id"
    ) == ("977", "979")


def test_untyped_batch_delete_does_not_compile_a_mutation_goal():
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    envelope = AgentEnvelope(
        user_id=1,
        channel="mobile",
        text="删掉977和979",
    )
    intent = build_intent_frame(envelope, context)

    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)

    assert goal.kind != "health_manage_mutation"


def test_v42_goal_digest_tracks_transitive_authorization_helper(monkeypatch):
    from app.services.agent_kernel import goal_spec as goal_spec_module

    before = goal_spec_module.goal_spec_contract_payload()["content_digest"]

    monkeypatch.setattr(
        goal_spec_module, "has_mixed_write_polarity", lambda _text: True
    )

    assert goal_spec_module.goal_spec_contract_payload()["content_digest"] != before
