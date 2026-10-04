"""Rejected write projection must remain absent from live provider and Pi paths."""
from copy import deepcopy

import pytest

from app.services import agent_executor as ae
from app.services.tool_schema_registry import get_health_tools
from tests.test_agent_prompt_budget_execution import CaptureProvider


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('query', ['记录喝水350毫升。', '记录喝水250ml', '今天记录我喝水1000ML', '请帮我记录饮水500毫升。', '记录喝水0.5升。'])
async def test_production_provider_retains_full_record_schema(db, auth_user_and_headers, monkeypatch, stream, query):
    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    # Even an obsolete experimental flag cannot activate rejected projection.
    executor._record_prompt_projection_allowed = True
    executor._current_user_id = user.id
    executor._current_turn_user_message = query
    executor._start_agent_kernel_turn(user_id=user.id, message=query, channel='typed')
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(ae.settings, 'agent_base_url', None)
    monkeypatch.setattr(ae.settings, 'agent_api_key', None)
    provider = CaptureProvider()
    monkeypatch.setattr(executor, '_resolve_chat_provider', lambda tools: (provider, tools))
    tools = get_health_tools(subset=['health_record', 'health_query'])
    original = deepcopy(tools)
    messages = [{'role': 'user', 'content': query}]
    if stream:
        _ = [e async for e in executor._call_llm_stream(messages, tools)]
    else:
        await executor._call_llm(messages, tools)
    assert provider.calls[0]['tools'] == original
    assert tools == original


@pytest.mark.parametrize('kind', ['owner', 'attachment', 'disabled', 'mixed', 'missing', 'diet', 'repair', 'pending', 'read_only', 'runtime_block', 'untyped_word_order', 'repair_frame', 'context_disabled', 'half_liter', 'one_liter'])
async def test_noneligible_record_requests_keep_full_provider_material(db, auth_user_and_headers, monkeypatch, kind):
    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    query = {'mixed': '记录喝水250毫升，再查一下天气', 'missing': '帮我记录喝了一杯水', 'diet': '记录午餐吃了一个苹果', 'untyped_word_order': '记录我喝了500ml水', 'half_liter': '记录喝水0.5升。', 'one_liter': '今天记录我喝水1L。'}.get(kind, '记录喝水500ml')
    executor._record_prompt_projection_allowed = True
    executor._current_user_id = user.id + (kind == 'owner')
    executor._current_turn_user_message = query
    executor._current_turn_has_attachment = kind == 'attachment'
    executor._start_agent_kernel_turn(user_id=user.id, message=query, channel='typed')
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', kind != 'disabled')
    monkeypatch.setattr(ae.settings, 'agent_base_url', None)
    monkeypatch.setattr(ae.settings, 'agent_api_key', None)
    provider = CaptureProvider()
    monkeypatch.setattr(executor, '_resolve_chat_provider', lambda tools: (provider, tools))
    tools = get_health_tools(subset=['health_record', 'health_query'])
    if kind == 'pending':
        executor._agent_kernel_pending_confirmation_tools = ['health_record']
    if kind == 'read_only':
        executor._read_only_turn = True
    if kind == 'runtime_block':
        executor._runtime_write_block_reason = 'denied'
    if kind == 'repair':
        executor._agent_kernel_tool_failure_tools = ['health_record']
    messages = [{'role': 'user', 'content': query}]
    if kind == 'repair_frame':
        messages.append({'role': 'tool', 'tool_call_id': 'previous', 'content': '{"error":"missing_data"}'})
    if kind == 'context_disabled':
        executor._record_prompt_projection_allowed = False
    await executor._call_llm(messages, tools)
    assert provider.calls[0]['tools'] == tools


async def test_full_pi_initial_request_preserves_authoritative_schema(db, auth_user_and_headers, monkeypatch):
    from app.services.pi_kernel import PiKernelSession
    from tests.test_agent_executor_fast_routing import _wire_common

    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    provider = CaptureProvider()
    _wire_common(executor, monkeypatch, lambda _: provider)
    monkeypatch.setattr(ae, 'get_health_tools', get_health_tools)
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(executor, '_resolve_chat_provider', lambda tools: (provider, tools))
    actual_start = PiKernelSession.start
    pi_tools = []
    async def start(self, **kwargs):
        pi_tools.extend(deepcopy(kwargs['tools']))
        return await actual_start(self, **kwargs)
    monkeypatch.setattr(PiKernelSession, 'start', start)
    events = [e async for e in executor.run_stream(user.id, '记录喝水500ml', channel='typed', client_turn_id='record-projection-initial')]
    assert any(e.get('event') == 'done' for e in events)
    assert provider.calls
    original = next(t['function'] for t in pi_tools if t['function']['name'] == 'health_record')
    sent = next(t['function'] for t in provider.calls[0]['tools'] if t['function']['name'] == 'health_record')
    assert sent == original
    assert original == next(t['function'] for t in get_health_tools() if t['function']['name'] == 'health_record')
