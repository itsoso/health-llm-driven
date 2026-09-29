"""Production entrypoint: bounded advice never needs model/private dispatch."""
import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from tests.test_conversational_advice_scope import BEDTIME, ACTION


def forbid_heavy_work(executor, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Local advice must not invoke provider, context or tool dispatch')
    for name in ('_build_system_prompt', '_call_llm', '_call_llm_stream',
                 '_dispatch_tool_request', '_run_multi_model_stream'):
        monkeypatch.setattr(executor, name, unexpected)
    monkeypatch.setattr('app.twin.builder.build_twin', unexpected)


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [BEDTIME, ACTION, '解释睡眠的一般性建议'])
@pytest.mark.parametrize('panel', [False, True])
async def test_local_answer_is_public_persisted_and_replay_identical(db, auth_user_and_headers, monkeypatch, message, panel):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    async def send():
        return [e async for e in executor.run_stream(user.id, message,
            client_turn_id='local-advice-replay', extra_context='{"multi_model":true}' if panel else None)]
    first = await send()
    done = first[-1]['data']
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert done['model_call_count'] == 0
    assert done['route'] == 'current_input_local_advice'
    assert not done['turn_outcome']['dispatch_started']
    assert not done.get('write_receipts') and not done.get('cards')
    public = ''.join(e['data']['content'] for e in first if e.get('event') == 'token')
    assert '本轮未查询个人记录' in public
    saved = db.get(AgentMessage, done['message_id'])
    assert saved.content == public
    assert saved.meta['turn_outcome'] == done['turn_outcome']
    second = await send()
    assert second[-1]['data']['message_id'] == done['message_id']
    assert ''.join(e['data']['content'] for e in second if e.get('event') == 'token') == public
    assert db.query(AgentMessage).filter_by(conversation_id=done['conversation_id']).count() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('original,attachment', [(BEDTIME, None), ('我胸痛，现在可以睡觉了吗？', None), (BEDTIME, 'synthetic.jpg')])
async def test_ack_recovery_binds_original_request(db, auth_user_and_headers, monkeypatch, original, attachment):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic advice recovery')
    source, _ = svc.save_user_message_once(conv.id, user.id, original, client_turn_id='advice-ack')
    source.image_url = attachment
    db.commit()
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(True)
        yield {'event': 'done', 'data': {'completion_status': 'error'}}
    monkeypatch.setattr(executor, '_run_stream_impl', ordinary)
    events = [e async for e in executor.run_stream(user.id, BEDTIME,
        conversation_id=conv.id, client_turn_id='advice-ack')]
    eligible = original == BEDTIME and not attachment
    assert bool(calls) is not eligible
    assert (events[-1]['data'].get('route') == 'current_input_local_advice') is eligible
    if eligible:
        assert db.query(AgentMessage).filter_by(conversation_id=conv.id, role='user').count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('message', ['我胸痛，现在可以睡觉了吗？', BEDTIME + '查询昨天的睡眠',
    '现在吃安眠药就可以睡觉了吗？', ACTION + '并删除记录', '不要回答现在可以睡觉了吗？',
    '我有鼻炎症状，今天该怎么休息和恢复？'])
async def test_other_goals_still_reach_existing_pipeline(db, auth_user_and_headers, monkeypatch, message):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs['message'])
        yield {'event': 'done', 'data': {'completion_status': 'error'}}
    monkeypatch.setattr(executor, '_run_stream_impl', ordinary)
    _ = [e async for e in executor.run_stream(user.id, message)]
    assert calls == [message]


@pytest.mark.asyncio
async def test_local_advice_cannot_use_another_users_conversation(db, auth_user_and_headers, monkeypatch):
    from tests.conftest import create_authenticated_user
    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(other.id, None, title='Synthetic owner check')
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    with pytest.raises(ValueError, match='对话不存在'):
        _ = [e async for e in executor.run_stream(user.id, BEDTIME, conversation_id=conv.id)]
    assert db.query(AgentMessage).filter_by(conversation_id=conv.id).count() == 0


@pytest.mark.asyncio
async def test_failed_persistence_cannot_emit_success_or_answer(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    original_save = AgentConversationService.save_message
    def fail_assistant(self, conv_id, role, *args, **kwargs):
        if role == 'assistant':
            raise RuntimeError('synthetic persistence failure')
        return original_save(self, conv_id, role, *args, **kwargs)
    monkeypatch.setattr(AgentConversationService, 'save_message', fail_assistant)
    events = []
    with pytest.raises(RuntimeError, match='synthetic persistence failure'):
        async for event in executor.run_stream(user.id, BEDTIME, client_turn_id='failed-advice'):
            events.append(event)
    assert not any(e.get('event') in ('token', 'done') for e in events)
