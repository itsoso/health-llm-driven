"""Exercise history reference compaction at actual executor provider exits."""
from copy import deepcopy

import pytest

from app.models.agent_conversation import AgentMessage
from app.services import agent_executor as ae
from app.services.pi_kernel import PiKernelSession
from tests.test_agent_history_budget import LONG_ANSWER, seed
from tests.test_agent_prompt_budget_execution import CaptureProvider


def history_bodies(*, with_current=True):
    bodies = [('user', '请回顾'), ('assistant', LONG_ANSWER), ('user', '再回顾'),
              ('assistant', LONG_ANSWER), ('user', '继续说明'), ('assistant', '最近的说明。')]
    return bodies + [('user', '继续刚才的说明')] if with_current else bodies


def wire_provider(executor, monkeypatch):
    provider = CaptureProvider()
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(ae.settings, 'agent_base_url', None)
    monkeypatch.setattr(ae.settings, 'agent_api_key', None)
    monkeypatch.setattr(executor, '_resolve_chat_provider', lambda tools: (provider, tools))
    return provider


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('mode', ['enabled', 'disabled', 'missing_source'])
async def test_provider_history_projection_preserves_runtime_and_database(
    db, auth_user_and_headers, monkeypatch, stream, mode,
):
    svc, conv, rows = seed(db, auth_user_and_headers, history_bodies())
    executor = ae.AgentExecutor(db)
    provider = wire_provider(executor, monkeypatch)
    messages = svc.build_messages(conv.id)
    assert svc.provider_history_references
    executor._provider_history_references = svc.provider_history_references
    if mode == 'missing_source':
        messages.pop(1)
    if mode == 'disabled':
        monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', False)
    executor._current_turn_recent_messages = deepcopy(messages[-6:])
    original = deepcopy(messages)
    recent = deepcopy(executor._current_turn_recent_messages)
    if stream:
        _ = [event async for event in executor._call_llm_stream(messages, [])]
    else:
        await executor._call_llm(messages, [])
    sent = provider.calls[0]['messages']
    assert messages == original
    assert executor._current_turn_recent_messages == recent
    db.expire_all()
    assert db.get(AgentMessage, rows[1].id).content == LONG_ANSWER
    assert db.get(AgentMessage, rows[3].id).content == LONG_ANSWER
    if mode == 'enabled':
        assert sent[1] == original[1]
        assert LONG_ANSWER not in sent[3]['content']
        assert '正文完全相同' in sent[3]['content']
        assert sent[-2:] == original[-2:]
    else:
        assert sent == original


@pytest.mark.asyncio
async def test_run_stream_carries_prepared_references_only_to_provider(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport,
):
    user, _ = auth_user_and_headers
    svc, conv, rows = seed(db, auth_user_and_headers, history_bodies(with_current=False))
    executor = ae.AgentExecutor(db)
    provider = wire_provider(executor, monkeypatch)
    monkeypatch.setattr(ae.settings, 'decision_mode', 'off')
    monkeypatch.setattr(ae.settings, 'task_tiered_routing', False)
    monkeypatch.setattr(ae, 'get_health_tools', lambda **kwargs: [])
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *args, **kwargs: 'SYSTEM')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *args: '')
    monkeypatch.setattr(executor, '_build_system_knowledge_evidence_card', lambda *args: None)
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_user', lambda *args, **kwargs: provider)
    pi_starts = []
    real_start = PiKernelSession.start

    async def capture_start(session, **kwargs):
        pi_starts.append(deepcopy(kwargs['messages']))
        await real_start(session, **kwargs)

    monkeypatch.setattr(PiKernelSession, 'start', capture_start)
    events = [event async for event in executor.run_stream(
        user_id=user.id, conversation_id=conv.id, message='继续刚才的说明',
        user_auth_token='test-token',
    )]
    assert events[-1]['event'] == 'done'
    assert provider.calls and pi_starts
    # Pi's complete transcript retains both historical copies. Only the provider
    # transport uses the references prepared by the real build_messages call.
    assert sum(LONG_ANSWER in m.get('content', '') for m in pi_starts[0]) == 2
    sent = provider.calls[0]['messages']
    assert sum(LONG_ANSWER in m.get('content', '') for m in sent) == 1
    assert any('正文完全相同' in m.get('content', '') for m in sent)
    assert all('正文完全相同' not in m.get('content', '') for m in executor._current_turn_recent_messages)
    db.expire_all()
    assert db.get(AgentMessage, rows[3].id).content == LONG_ANSWER
