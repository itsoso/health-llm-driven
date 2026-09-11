"""Irrecoverable policy decisions do not consume repeated model/tool attempts."""
import json
import pytest
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.types import CapabilityDecision


@pytest.mark.asyncio
async def test_same_blocked_request_is_not_decided_twice(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._start_agent_kernel_turn(user_id=user.id, message='查询他人的昨天饮食', channel='typed')
    calls = []
    async def blocked(name, args, token, **kwargs):
        calls.append(args)
        executor._agent_kernel_record_capability_decision(name, CapabilityDecision(
            'block', 'health_query_subject_not_current_user', name, {'dimension': 'diet'}))
        return json.dumps({'status':'rejected', 'error_code':'health_query_subject_not_current_user'})
    monkeypatch.setattr(executor, '_execute_tool_impl', blocked)
    first = await executor._execute_tool('health_query', '{"dimension":"diet"}', None)
    second = await executor._execute_tool('health_query', {'dimension': 'diet'}, None)
    assert first == second
    assert len(calls) == 1
    await executor._execute_tool('health_query', {'dimension': 'sleep'}, None)
    assert len(calls) == 2, 'Different requests must still be decided.'
    executor._start_agent_kernel_turn(user_id=user.id, message='查询我的昨天饮食', channel='typed')
    await executor._execute_tool('health_query', {'dimension': 'diet'}, None)
    assert len(calls) == 3, 'A new turn must never inherit a stale block.'


@pytest.mark.asyncio
async def test_repairable_parameter_failure_is_not_cached(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._start_agent_kernel_turn(user_id=user.id, message='查询昨天饮食', channel='typed')
    calls = []
    async def blocked(name, args, token, **kwargs):
        calls.append(args)
        executor._agent_kernel_record_capability_decision(name, CapabilityDecision(
            'block', 'health_query_dimension_conflict', name, {'dimension': 'sleep'}))
        return 'Error: dimension conflict'
    monkeypatch.setattr(executor, '_execute_tool_impl', blocked)
    for _ in range(2):
        await executor._execute_tool('health_query', {'dimension': 'sleep'}, None)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_stream_stops_after_an_immutable_owner_block(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *_a, **_k: '健康记录助手。')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *_a, **_k: '')
    calls = []
    async def stream(messages, tools):
        calls.append(1)
        yield {'type':'tool_calls', 'tool_calls':[{'id':'read', 'type':'function', 'function':{
            'name':'health_query', 'arguments':'{"dimension":"diet","days":1}'}}]}
        yield {'type':'finish', 'finish_reason':'tool_calls'}
    async def blocked(name, args, token, **kwargs):
        executor._agent_kernel_record_capability_decision(name, CapabilityDecision(
            'block', 'health_query_subject_not_current_user', name, {'dimension': 'diet'}))
        return json.dumps({'status':'rejected', 'error_code':'health_query_subject_not_current_user'})
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    monkeypatch.setattr(executor, '_execute_tool_impl', blocked)
    events = [e async for e in executor.run_stream(user_id=user.id, message='查询他人的饮食记录', channel='typed')]
    assert len(calls) == 1
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert '本人' in text
    done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
    assert done['turn_outcome']['status'] == 'blocked'
