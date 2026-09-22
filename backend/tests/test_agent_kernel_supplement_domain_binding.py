"""Synthetic write-boundary regressions; no real health conversation data."""

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)


def _decision(message, record_type, **data):
    envelope = AgentEnvelope(user_id=1, channel="chat", text=message)
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    snapshot = TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
    )
    return decide_tool_capability(snapshot, ToolExecutionRequest(
        tool_name="health_record", arguments={"record_type": record_type, "data": data},
    ))


@pytest.mark.parametrize("message", [
    "记录补剂：一粒两粒营养素甲",
    "记录补剂：一粒营养素甲和两粒营养素甲",
    "记录补剂：营养素乙一粒、营养素甲一粒两粒",
])
def test_conflicting_quantity_requires_clarification_before_write(message):
    decision = _decision(message, "supplement", supplement_name="营养素甲", dosage="1粒")
    assert decision.action == "block"
    assert decision.reason == "supplement_dosage_requires_clarification"


def test_unambiguous_sibling_supplement_is_still_authorized():
    decision = _decision("记录补剂：营养素乙一粒、营养素甲一粒两粒", "supplement",
                         supplement_name="营养素乙", dosage="1粒")
    assert decision.action == "allow"


@pytest.mark.parametrize("meal, slot", [("早餐", "breakfast"), ("午餐", "lunch"), ("晚餐", "dinner")])
def test_meal_relative_timing_does_not_authorize_diet_record(meal, slot):
    decision = _decision(f"记录{meal}后吃了补剂营养素甲两粒", "diet",
                         meal_type=slot, food_items="后吃了补剂营养素甲两粒")
    assert decision.action == "block"


@pytest.mark.parametrize("message, food, slot", [
    ("记录早餐吃了一片面包", "一片面包", "breakfast"),
    ("记录加餐吃了两粒花生", "两粒花生", "snack"),
])
def test_countable_food_still_authorizes_diet(message, food, slot):
    decision = _decision(message, "diet", food_items=food, meal_type=slot)
    assert decision.action == "allow"


def test_explicit_supplement_cannot_be_recast_as_food():
    decision = _decision("记录补剂：营养素甲两粒", "diet", food_items="营养素甲两粒")
    assert decision.action == "block"


def test_explicit_named_supplement_keeps_existing_authority():
    decision = _decision("记录补剂：营养素甲两粒", "supplement",
                         supplement_name="营养素甲", dosage="2粒")
    assert decision.action == "allow"


@pytest.mark.parametrize("name,dosage,action", [
    ("Mitoq 心脏版", "1粒", "allow"),
    ("MitoQ心脏版", "1粒", "allow"),
    ("复合VB", "1粒", "allow"),
    ("Mitoq", "1粒", "block"),
    ("Mitoq 标准版", "1粒", "block"),
    ("Mitoq 心脏版", "2粒", "block"),
    ("复合维生素B", "1粒", "block"),
    ("NAC", "1粒", "block"),
])
def test_qualified_product_authority_does_not_drop_variant_or_change_dose(name, dosage, action):
    decision = _decision("记录补剂：1 粒复合VB 1 粒 Mitoq 心脏版", "supplement",
                         supplement_name=name, dosage=dosage)
    assert decision.action == action


@pytest.mark.parametrize("prefix", ["不要", "明天", "替我妈妈", "示例：", "翻译："])
def test_qualified_product_name_does_not_expand_current_user_authority(prefix):
    decision = _decision(f"{prefix}记录补剂：1 粒复合VB 1 粒 Mitoq 心脏版", "supplement",
                         supplement_name="Mitoq 心脏版", dosage="1粒")
    assert decision.action == "block"


@pytest.mark.parametrize("name, dosage", [
    ("Mitoq", "2粒"),
    ("叶酸", "1粒"),
    ("NAC", "1粒"),
])
def test_dose_prefix_batch_authorizes_each_exact_supplement(name, dosage):
    decision = _decision(
        "打卡补剂：2粒Mitoq 1粒叶酸 1粒NAC",
        "supplement",
        supplement_name=name,
        dosage=dosage,
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": "supplement",
        "data": {"supplement_name": name, "dosage": dosage},
    }


@pytest.mark.parametrize("name, dosage", [
    ("Mitoq", "2粒"),
    ("叶酸", "1粒"),
    ("NAC", "1粒"),
])
def test_name_first_batch_authorizes_each_exact_supplement(name, dosage):
    decision = _decision(
        "打卡补剂：Mitoq 2粒，叶酸1粒，NAC1粒",
        "supplement",
        supplement_name=name,
        dosage=dosage,
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(("name", "dosage"), [("A-B", "1粒"), ("AB", "2粒")])
def test_colliding_gateway_names_are_not_independently_authorized(name, dosage):
    decision = _decision(
        "打卡补剂：1粒A-B 2粒AB",
        "supplement",
        supplement_name=name,
        dosage=dosage,
    )

    assert decision.action == "block"


@pytest.mark.parametrize("prefix", [
    "记录饮水300ml，然后",
    "记录午餐吃了米饭，然后",
])
def test_concrete_non_weight_write_can_precede_supplement_batch(prefix):
    decision = _decision(
        f"{prefix}打卡补剂：2粒Mitoq 1粒NAC",
        "supplement",
        supplement_name="Mitoq",
        dosage="2粒",
    )

    assert decision.action == "allow"


@pytest.mark.parametrize("prefix", [
    "记录饮水300ml，然后帮我写一句",
    "记录午餐吃了米饭，然后把下面这句作为示例",
])
def test_preceding_write_does_not_authorize_metalinguistic_supplement_batch(prefix):
    decision = _decision(
        f"{prefix}打卡补剂：2粒Mitoq 1粒NAC",
        "supplement",
        supplement_name="Mitoq",
        dosage="2粒",
    )

    assert decision.action == "block"


@pytest.mark.parametrize("name, dosage", [
    ("Mitoq", "1粒"),
    ("虚构鱼油", "1粒"),
])
def test_dose_prefix_batch_rejects_unowned_name_or_dosage(name, dosage):
    decision = _decision(
        "记录补剂：2粒Mitoq 1粒叶酸 1粒NAC",
        "supplement",
        supplement_name=name,
        dosage=dosage,
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize("message", [
    "明天打卡补剂：2粒Mitoq 1粒NAC",
    "明天，打卡补剂：2粒Mitoq 1粒NAC",
    "不要。打卡补剂：2粒Mitoq 1粒NAC",
    "计划；打卡补剂：2粒Mitoq 1粒NAC",
    "记录补剂的示例是：打卡补剂：2粒Mitoq 1粒NAC",
    "记录体重的示例是：打卡补剂：2粒Mitoq 1粒NAC",
    "记录补剂格式：打卡补剂：2粒Mitoq 1粒NAC",
    "记录体重的演示：打卡补剂：2粒Mitoq 1粒NAC",
    "记录体重的文案：打卡补剂：2粒Mitoq 1粒NAC",
    "记录体重的示范：打卡补剂：2粒Mitoq 1粒NAC",
    "记录饮水的示范：打卡补剂：2粒Mitoq 1粒NAC",
    "记录睡眠范例：打卡补剂：2粒Mitoq 1粒NAC",
    "记录饮食DEMO：打卡补剂：2粒Mitoq 1粒NAC",
    "记录睡眠fixture：打卡补剂：2粒Mitoq 1粒NAC",
    "帮我写一句：打卡补剂：2粒Mitoq 1粒NAC",
    "医生建议打卡补剂：2粒Mitoq 1粒NAC",
    "给妈妈打卡补剂：2粒Mitoq 1粒NAC",
    "打卡补剂：0粒Mitoq 1粒NAC",
    "打卡补剂：0粒Mitoq，1粒NAC",
    "打卡补剂：半半粒Mitoq，1粒NAC",
    "打卡补剂：2粒Mitoq，1粒",
    "打卡补剂：两粒Mitoq 一粒",
    "打卡补剂：，0粒Mitoq，1粒NAC",
    "打卡补剂：：0粒Mitoq，1粒NAC",
    "记录补剂：Mitoq 2粒。记录补剂：2粒NAC，1粒",
    "打卡补剂：2粒Mitoq 1粒叶酸，鱼油",
    "打卡补剂：2粒Mitoq 1粒叶酸、鱼油",
    "打卡补剂：2粒Mitoq 1粒叶酸和鱼油",
    "打卡补剂：2粒Mitoq 1粒叶酸以及鱼油",
])
def test_dose_prefix_batch_rejects_unowned_or_non_consumed_actions(message):
    decision = _decision(
        message,
        "supplement",
        supplement_name="Mitoq",
        dosage="2粒",
    )

    assert decision.action == "block"


@pytest.mark.parametrize("message, data", [
    ("记录补剂：营养素甲", {}),
    ("记录补剂：营养素甲两粒和营养素甲2粒", {"dosage": "2粒"}),
])
def test_absent_or_equivalent_amount_is_not_conflicting(message, data):
    assert _decision(message, "supplement", supplement_name="营养素甲", **data).action == "allow"


def test_clarification_does_not_authorize_a_similarly_named_entity():
    decision = _decision("记录补剂：营养素甲一粒两粒", "supplement",
                         supplement_name="营养素甲加强版")
    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize("message", ["不要记录补剂营养素甲两粒", "可以记录补剂营养素甲两粒吗？"])
def test_negation_and_question_do_not_authorize_supplement(message):
    assert _decision(message, "supplement", supplement_name="营养素甲", dosage="2粒").action == "block"
