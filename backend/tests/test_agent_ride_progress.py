"""Synthetic ride updates are conversation context, not health query goals."""
import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_context_statement import parse_context_statement
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from app.services.utterance_intent_classifier import classify_agent_utterance
from tests.test_agent_context_statement import _no_heavy_work


@pytest.mark.parametrize('message', [
    '上车了 往酒店方向', '我上车了，正在往酒店方向走。',
    '现在已经坐上车了，去酒店了', '我刚打上车，前往宾馆',
    '上车了，朝民宿方向开', '上车了，往住处方向',
])
def test_ride_progress_is_closed_context(message):
    statement = parse_context_statement(message)
    assert statement is not None and statement.kind == 'ride_progress'
    assert statement.allows_local_reply
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.is_write) == ('chat', 'context', False)
    assert not any(word in statement.reply for word in ('已记录', '查询', '信息来源', '到达'))


@pytest.mark.parametrize('message', [
    '上车了', '上车往酒店方向', '我上车去酒店', '准备上车往酒店方向', '还没上车往酒店方向', '明天上车往酒店方向',
    '朋友上车了往酒店方向', '如果上车了往酒店方向', '他说上车了往酒店方向',
    '“上车了往酒店方向”', '上车了往酒店方向？', '记录上车了往酒店方向',
    '上车了往酒店方向，帮我查睡眠', '上车了往酒店方向，胸痛',
    '上车了往酒店方向，提醒我吃药', '上车了往医院方向',
    '上车了往胸痛酒店方向', '上车了往酒店方向\n呼吸困难',
    '上车了往酒店方向，删除记录', '上车了往酒店方向，怎么走',
    '上车了往酒店方向，预计十分钟到', '上车了往酒店方向，确认',
])
def test_other_obligations_are_not_consumed(message):
    assert parse_context_statement(message) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('channel', ['mobile', 'typed', 'mac'])
@pytest.mark.parametrize('prior_status', ['complete', 'failed'])
async def test_ride_after_transfer_conversation_never_queries_or_writes_health(db, auth_user_and_headers, monkeypatch, channel, prior_status):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic ride conversation')
    old = svc.save_message(conv.id, 'assistant', '本轮数据查询未完成，请明确类别和日期。',
                           meta={'completion_status': 'failed', 'turn_outcome': {'status': 'failed'}})
    prior = svc.save_message(conv.id, 'user', '选了另一处接站门，司机得绕路，下次换个地方。')
    svc.save_message(conv.id, 'assistant', '下次可以先和司机确认接站位置。',
                     meta={'completion_status': prior_status, 'client_turn_finalized': True,
                           'turn_outcome': {'status': prior_status}})
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    events = [e async for e in executor.run_stream(user_id=user.id, message='上车了 往酒店方向',
        conversation_id=conv.id, channel=channel, client_turn_id='synthetic-ride')]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['route'] == 'context_statement'
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert done['model_call_count'] == done['turn_outcome']['verified_receipt_count'] == 0
    assert done['turn_outcome']['capability_block_count'] == 0
    assert not any(e.get('event') in ('tool_call', 'tool_result') for e in events)
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert text == db.get(AgentMessage, done['message_id']).content == parse_context_statement('上车了 往酒店方向').reply
    assert db.get(AgentMessage, old.id).meta['turn_outcome']['status'] == 'failed'
    assert db.get(AgentMessage, prior.id).content == prior.content
    replay = [e async for e in executor.run_stream(user_id=user.id, message='上车了 往酒店方向',
        conversation_id=conv.id, channel=channel, client_turn_id='synthetic-ride')]
    assert next(e['data'] for e in replay if e.get('event') == 'done')['message_id'] == done['message_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('prior,answer,meta', [
    ('我胸痛喘不上气', '你现在在哪里？', {}),
    ('我头晕', '请告诉我现在的情况。', {}),
    ('记录行程', '请确认是否保存。', {'pending_choice': {'kind': 'confirm'}}),
    ('去酒店', '你在哪里？', {}),
    ('去酒店', '请补充位置。', {'turn_outcome': {'status': 'waiting_for_user'}}),
    ('去酒店', '正在核对写入结果。', {'turn_outcome': {'status': 'reconciliation_required'}}),
])
async def test_ride_does_not_intercept_medical_or_pending_followup(db, auth_user_and_headers, monkeypatch, prior, answer, meta):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic pending context')
    svc.save_message(conv.id, 'user', prior)
    svc.save_message(conv.id, 'assistant', answer, meta={
        'completion_status': 'complete', 'client_turn_finalized': True,
        'turn_outcome': {'status': 'complete'}, **meta})
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs['message'])
        yield {'event': 'done', 'data': {'completion_status': 'complete'}}
    monkeypatch.setattr(executor, '_run_stream_impl', ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message='上车了 往酒店方向', conversation_id=conv.id)]
    assert calls == ['上车了 往酒店方向']


@pytest.mark.asyncio
async def test_ride_progress_rejects_foreign_conversation(db, auth_user_and_headers, monkeypatch):
    from tests.conftest import create_authenticated_user
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic owned ride')
    other, _ = create_authenticated_user(db)
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    with pytest.raises(ValueError, match='对话不存在'):
        _ = [e async for e in executor.run_stream(user_id=other.id,
            message='上车了 往酒店方向', conversation_id=conv.id)]


@pytest.mark.parametrize('dimension', ['diet', 'sleep', 'spo2'])
def test_ride_progress_does_not_authorize_personal_reads(dimension):
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from app.services.agent_kernel.types import ToolExecutionRequest
    from tests.test_recent_workout_read_regression import snapshot
    assert decide_tool_capability(snapshot('上车了 往酒店方向'), ToolExecutionRequest(
        'health_query', {'dimension': dimension})).action == 'block'
