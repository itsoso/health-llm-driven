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
