"""Synthetic arrival phrasing must keep context and explicit writes distinct."""
import pytest
from app.services.agent_context_statement import parse_context_statement
from app.services.agent_conversation_service import AgentConversationService
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.services.write_intent_scope import current_turn_trip_payload
from app.services.agent_executor import AgentExecutor
from tests.test_agent_trip_record import execute_trip

ARRIVALS = (
    '记录行程现在到了上海国际机场',
    '记录我的行程，现在到了上海国际机场。',
    '记录行程 我已经抵达上海国际机场',
    '记录行程：我现在到了上海国际机场',
)

@pytest.mark.parametrize('message', ARRIVALS)
def test_explicit_arrival_is_a_write_with_current_facts(message):
    assert classify_agent_utterance(message).is_write
    payload = current_turn_trip_payload(message)
    assert payload is not None
    assert '上海国际机场' in payload['title']
    assert payload['notes'] == payload['title']

@pytest.mark.asyncio
@pytest.mark.parametrize('message', ARRIVALS)
async def test_explicit_arrival_uses_real_gateway_projection(db, monkeypatch, message):
    calls, _ = await execute_trip(db, monkeypatch, message)
    assert len(calls) == 1
    assert calls[0][2] == current_turn_trip_payload(message)
    assert 'occurred_at' not in calls[0][2]

@pytest.mark.parametrize('message', ('现在到了上海国际机场', '我已抵达澳门国际机场', '现在到了北京机场'))
def test_plain_arrival_is_context_not_a_write_or_query(message):
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.is_write) == ('chat', 'context', False)
    assert parse_context_statement(message).allows_local_reply
    assert current_turn_trip_payload(message) is None

@pytest.mark.parametrize('suffix', ('这是示例', '暂时不要存', '这是朋友说的', '然后查询睡眠', '胸痛', '这是附言机场'))
@pytest.mark.asyncio
async def test_unconsumed_arrival_language_never_writes(db, monkeypatch, suffix):
    message = '记录行程现在到了上海国际机场' + suffix
    assert current_turn_trip_payload(message) is None
    calls, _ = await execute_trip(db, monkeypatch, message)
    assert calls == []

@pytest.mark.asyncio
async def test_plain_arrival_after_verified_trip_completes_without_health_queries(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='合成行程进展')
    svc.save_message(conv.id, 'user', '记录我的行程，我现在在口岸，准备去海岛，走的是跨海大桥。')
    svc.save_message(conv.id, 'assistant', '✅ 已记录', meta={
        'client_turn_finalized': True, 'completion_status': 'complete',
        'turn_outcome': {'status': 'complete', 'confirmation_required': False},
        'write_receipts': [{'verified': True, 'status': 'verified', 'action': 'create',
                            'resource_type': 'health_episode', 'resource_id': '99'}],
    })
    executor = AgentExecutor(db)
    def unexpected(*args, **kwargs):
        pytest.fail('A closed trip followed by a location context needs no model or health query')
    monkeypatch.setattr(executor, '_build_system_prompt', unexpected)
    monkeypatch.setattr(executor, '_call_llm_stream', unexpected)
    events = [e async for e in executor.run_stream(user_id=user.id,
        message='现在到了上海国际机场', conversation_id=conv.id, channel='typed')]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['route'] == 'context_statement'
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['verified_receipt_count'] == 0
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert '上海国际机场' in text and '查询' not in text and '已记录' not in text

@pytest.mark.parametrize('override', (
    {'client_turn_finalized': False}, {'completion_status': 'failed'},
    {'turn_outcome': {'status': 'reconciliation_required'}},
    {'pending_choice': {'kind': 'confirm'}}, {'health_fact_draft': {'value': 'test'}},
    {'write_receipts': []}, {'write_receipts': [{'verified': True, 'resource_type': 'diet_record'}]},
    {'turn_outcome': 'malformed'},
))
def test_incomplete_trip_receipt_never_closes_context(override):
    from types import SimpleNamespace
    from app.services.agent_context_statement import _is_closed_trip_pair
    source = SimpleNamespace(role='user', content='记录行程，我现在在口岸', meta={})
    answer = SimpleNamespace(role='assistant', content='✅ 已记录', meta={
        'client_turn_finalized': True, 'completion_status': 'complete',
        'turn_outcome': {'status': 'complete'},
        'write_receipts': [{'verified': True, 'status': 'verified', 'action': 'create',
                            'resource_type': 'health_episode', 'resource_id': '99'}],
        **override,
    })
    assert not _is_closed_trip_pair(source, answer)

@pytest.mark.parametrize('message', (
    '现在到了上海国际机场胸痛', '现在到了上海国际机场这是示例',
    '现在到了上海国际机场，查询昨晚睡眠', '现在到了未知示例国际机场',
    '朋友现在到了上海国际机场', '如果现在到了上海国际机场',
    '“现在到了上海国际机场”', '现在到了上海国际机场？',
))
def test_plain_arrival_does_not_swallow_extra_obligations(message):
    assert parse_context_statement(message) is None
