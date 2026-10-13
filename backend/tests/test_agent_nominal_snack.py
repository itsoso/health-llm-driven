"""Meal-labelled, quantified food facts are current-user records, not plans."""
import pytest
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.goal_spec import compile_goal_spec

@pytest.mark.parametrize('message,food', (
    ('加餐一小个桃子', '一小个桃子'), ('加餐一个桃子', '一个桃子'),
    ('今天加餐：一个苹果。', '一个苹果'), ('我的加餐半根香蕉', '半根香蕉'),
))
def test_quantified_meal_fact_is_a_bounded_record(message, food):
    context = ExecutionContext.for_test(user_id=1, channel='mobile')
    envelope = AgentEnvelope(user_id=1, channel='mobile', text=message)
    intent = build_intent_frame(envelope, context)
    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)
    assert intent.is_write and intent.domain == 'diet'
    assert goal.kind == 'simple_health_record'
    assert dict(goal.target_values) == {'meal_type':'snack','food_items':food}

@pytest.mark.parametrize('message', (
    '明天加餐一个桃子', '计划加餐一个桃子', '加餐一个桃子可以吗',
    '妈妈加餐一个桃子', '加餐一个桃子，不要记录', '如果加餐一个桃子',
    '“加餐一个桃子”', '加餐一个桃子？', '加餐一个桃子明天吃',
    '加餐一个桃子还没吃', '加餐一个桃子是妈妈的', '加餐一个桃子模型',
    '加餐一片替尔泊肽', '加餐一个桃子，删除记录',
))
def test_non_observation_snack_is_not_authorized_as_fact(message):
    context = ExecutionContext.for_test(user_id=1, channel='mobile')
    envelope = AgentEnvelope(user_id=1, channel='mobile', text=message)
    intent = build_intent_frame(envelope, context)
    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)
    assert goal.kind != 'simple_health_record'
