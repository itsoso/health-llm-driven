"""Real stream persistence to a numbered continuation with no write authority."""
import pytest
from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor


@pytest.mark.asyncio
@pytest.mark.parametrize('extra_context', [None, '{"multi_model": true}'])
async def test_current_number_continues_owned_persisted_read_choice(db, auth_user_and_headers, monkeypatch, extra_context):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *_a, **_k: '健康记录助手。')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *_a, **_k: '')
    captured = []
    async def stream(messages, tools):
        captured.append(messages)
        text = ('请选择一项，回复编号：\n1. 查看昨晚睡眠\n2. 查看昨天饮食'
                if len(captured) == 1 else '目标日期暂未查询到可核验数据。')
        yield {'type':'content', 'text':text}
        yield {'type':'finish', 'finish_reason':'stop'}
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    first = [e async for e in executor.run_stream(user_id=user.id, message='我可以查看哪些记录', channel='typed')]
    done = next(e['data'] for e in reversed(first) if e.get('event') == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert saved.meta.get('pending_choice'), repr(saved.content)
    multi_model_calls = []
    async def unexpected_multi_model(*args, **kwargs):
        multi_model_calls.append(True)
        raise AssertionError('Read-only choices must retain the guarded ordinary stream.')
        yield  # pragma: no cover - preserve the async-generator interface
    monkeypatch.setattr(executor, '_run_multi_model_stream', unexpected_multi_model)
    second = [e async for e in executor.run_stream(user_id=user.id, message='1', conversation_id=done['conversation_id'], channel='typed', extra_context=extra_context)]
    assert multi_model_calls == []
    assert len(captured) == 2
    assert captured[-1][-1]['role'] == 'user'
    assert captured[-1][-1]['content'].split('[用户消息]\n')[-1].startswith('查询20')
    assert captured[-1][-1]['content'].endswith('的睡眠')
    final = next(e['data'] for e in reversed(second) if e.get('event') == 'done')
    assert not final['write_receipts']
    assert executor._read_only_turn is True
    numeric = db.query(AgentMessage).filter(AgentMessage.conversation_id == done['conversation_id'], AgentMessage.role == 'user').order_by(AgentMessage.id.desc()).first()
    assert numeric.content == '1', 'History keeps what the user actually entered.'
