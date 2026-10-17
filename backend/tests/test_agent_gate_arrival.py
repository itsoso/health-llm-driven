"""Synthetic boarding-gate updates remain bounded, non-writing context."""
import pytest

from app.models.agent_conversation import AgentMessage
from app.models.episode import HealthEpisode
from app.services.agent_context_statement import parse_context_statement
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.services.write_intent_scope import current_turn_trip_payload
from tests.test_agent_context_statement import _no_heavy_work


@pytest.mark.parametrize('message', [
    '到了18号门 20:40 降落', '我现在到了18号登机口，预计20:40降落。',
    '已到达A18登机口', '到了18号门', '我刚抵达B12登机口，08:05起飞',
    '到了１８号门，２０：４０降落。',
])
def test_gate_update_is_context_not_read_or_write(message):
    parsed = parse_context_statement(message)
    assert parsed is not None and parsed.allows_local_reply
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.is_write) == ('chat', 'context', False)
    assert current_turn_trip_payload(message) is None
    assert '已记录' not in parsed.reply
    assert '已降落' not in parsed.reply


@pytest.mark.parametrize('message', [
    '到了18号门 24:00 降落', '到了18号门 20:60 降落', '到了18号门 20:40',
    '到了18号门 20:40 降落胸痛', '到了18号门，帮我查睡眠',
    '到了18号门，20:40提醒我', '记录到了18号门 20:40降落',
    '朋友到了18号门 20:40降落', '如果到了18号门 20:40降落',
    '还没到18号门', '到了18号门？', '“到了18号门”',
    '到了18号门\n胸痛', '到了18号门 明天20:40降落',
    '到了18号门 20:40降落，改成21:00', '到了18号门 20:40降落这是示例',
    '到了0号门', '到了18号门 20:40降落，取消提醒',
])
def test_unconsumed_gate_obligations_keep_normal_pipeline(message):
    assert parse_context_statement(message) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('previous_refusal', [False, True])
async def test_airport_gate_time_continuation_completes_durably_without_health_work(db, auth_user_and_headers, monkeypatch, previous_refusal):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='合成登机口续聊')
    svc.save_message(conv.id, 'user', '现在到了上海国际机场')
    svc.save_message(conv.id, 'assistant', '收到，你已到上海国际机场。')
    if previous_refusal:
        from app.services.guidance_validator import _ADVICE_HOLD
        svc.save_message(conv.id, 'user', '到了18号门 20:40 降落')
        svc.save_message(conv.id, 'assistant', '信息来源：上下文信息（未逐项核验）、已检索证据（未逐句核验）、模型推断。\n' + _ADVICE_HOLD)
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    for i, message in enumerate(('到了18号门 20:40 降落', '到了B12登机口，预计21:10起飞', '我在上海出差')):
        events = [e async for e in executor.run_stream(user_id=user.id, message=message,
            conversation_id=conv.id, channel='mobile', client_turn_id=f'synthetic-gate-{i}')]
        done = next(e['data'] for e in events if e.get('event') == 'done')
        assert done['route'] == 'context_statement'
        assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
        assert done['model_call_count'] == done['turn_outcome']['verified_receipt_count'] == 0
        text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
        assert text == parse_context_statement(message).reply == db.get(AgentMessage, done['message_id']).content
        assert not any(word in text for word in ('查询未完成', '已记录', '已降落'))
        assert not any(e.get('event') in ('tool_call', 'tool_result') for e in events)
    assert db.query(HealthEpisode).filter_by(user_id=user.id).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('prior,answer,meta', [
    ('我胸痛', '你现在在哪里？', {}),
    ('记录行程', '请补充地点。', {'pending_choice': {'kind': 'confirm'}}),
    ('现在到了上海国际机场', '请补充你的症状。', {}),
])
async def test_gate_update_does_not_hide_unfinished_or_medical_history(db, auth_user_and_headers, monkeypatch, prior, answer, meta):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='合成未完成续问')
    svc.save_message(conv.id, 'user', prior)
    svc.save_message(conv.id, 'assistant', answer, meta=meta)
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs['message'])
        yield {'event': 'done', 'data': {'completion_status': 'complete'}}
    monkeypatch.setattr(executor, '_run_stream_impl', ordinary)
    message = '到了18号门 20:40 降落'
    _ = [e async for e in executor.run_stream(user_id=user.id, message=message, conversation_id=conv.id)]
    assert calls == [message]


def test_gate_clock_reply_does_not_infer_flight_completion_date_or_timezone():
    assert parse_context_statement('到了18号门 20:40 降落').reply == '收到，你已到18号门。你补充的降落时间是20:40。'
    assert parse_context_statement('到了A18登机口，预计00:05起飞').reply == '收到，你已到A18登机口。你补充的预计起飞时间是00:05。'


@pytest.mark.asyncio
async def test_gate_context_is_owned_and_replay_does_not_duplicate_messages(db, auth_user_and_headers, monkeypatch):
    from tests.conftest import create_authenticated_user
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    first = [e async for e in executor.run_stream(user_id=user.id, message='到了18号门 20:40降落', client_turn_id='synthetic-gate-replay')]
    done = next(e['data'] for e in first if e.get('event') == 'done')
    replay = [e async for e in executor.run_stream(user_id=user.id, message='到了18号门 20:40降落', conversation_id=done['conversation_id'], client_turn_id='synthetic-gate-replay')]
    replay_done = next(e['data'] for e in replay if e.get('event') == 'done')
    assert replay_done['message_id'] == done['message_id']
    assert db.query(AgentMessage).filter_by(conversation_id=done['conversation_id']).count() == 2
    other, _ = create_authenticated_user(db)
    with pytest.raises(ValueError, match='对话不存在'):
        _ = [e async for e in executor.run_stream(user_id=other.id, message='到了18号门 20:40降落', conversation_id=done['conversation_id'])]
