"""Lexical identification is not negation; classification never grants a write."""

from datetime import datetime

import pytest

from app.services.utterance_intent_classifier import classify_agent_utterance
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


@pytest.mark.parametrize('text', [
    '基于识别的这一餐来修改今天午餐记录',
    '根据识别结果修改今天午餐记录',
    '请修改识别的午餐记录',
])
def test_identification_word_is_not_a_mutation_veto(text):
    intent = classify_agent_utterance(text)
    assert (intent.primary, intent.domain, intent.operation, intent.is_write) == ('mutate', 'diet', 'update', True)


@pytest.mark.parametrize('text', [
    '不要基于识别结果修改今天午餐记录',
    '识别后先别修改今天午餐记录',
    '基于识别结果，不要修改今天午餐记录',
])
def test_real_negation_still_blocks_mutation(text):
    assert not classify_agent_utterance(text).is_write


@pytest.mark.parametrize('text', [
    '基于识别的这一餐来修改今天午餐记录',
    '不要基于识别结果修改今天午餐记录',
    '假设基于识别结果修改今天午餐记录',
    '朋友说：基于识别结果修改今天午餐记录',
    '根据识别结果修改朋友的今天午餐记录',
])
def test_classification_cannot_supply_photo_provenance_or_a_record_id(text):
    envelope = AgentEnvelope(user_id=41, channel='typed', text=text)
    context = ExecutionContext(current_time=datetime.fromisoformat('2026-09-23T15:00:00+08:00'),
                               timezone='Asia/Shanghai', user_id=41, channel='typed')
    snapshot = TurnSnapshot(envelope, context, build_intent_frame(envelope, context))
    decision = decide_tool_capability(snapshot, ToolExecutionRequest('health_manage', {
        'operation': 'update', 'record_type': 'diet', 'record_id': 987,
        'data': {'food_items': '模型猜测的食物', 'calories': 600},
    }))
    assert decision.action == 'block'
