import copy
import json

import pytest

from app.services import agent_executor as ae
from app.services.tool_schema_registry import get_health_tools
from tests.test_agent_longitudinal_read_regression import ANALYSIS_REQUESTS
from tests.test_agent_prompt_budget_execution import CaptureProvider


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_provider_receives_owned_schema_guidance(db, auth_user_and_headers, monkeypatch, stream):
    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    query = ANALYSIS_REQUESTS[0]
    executor._current_user_id = user.id
    executor._current_turn_user_message = query
    executor._start_agent_kernel_turn(user_id=user.id, message=query, channel='typed')
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(ae.settings, 'agent_base_url', None)
    monkeypatch.setattr(ae.settings, 'agent_api_key', None)
    provider = CaptureProvider()
    monkeypatch.setattr(executor, '_resolve_chat_provider', lambda tools: (provider, tools))
    tools = get_health_tools(subset=['health_query', 'health_query_batch', 'knowledge_search'])
    original = copy.deepcopy(tools)
    messages = [{'role': 'user', 'content': query}]
    if stream:
        _ = [e async for e in executor._call_llm_stream(messages, tools)]
    else:
        await executor._call_llm(messages, tools)
    sent = provider.calls[0]['tools']
    assert tools == original
    assert len(json.dumps(sent, ensure_ascii=False)) < len(json.dumps(tools, ensure_ascii=False)) * .8
    original_by_name = {t['function']['name']: t['function'] for t in tools}
    for t in sent:
        f = t['function']
        assert f['parameters'] == original_by_name[f['name']]['parameters']
    assert '本轮服务端已绑定查询维度' in sent[0]['function']['description']


def test_another_owner_snapshot_cannot_project_schema(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    executor._current_user_id = user.id + 1
    executor._start_agent_kernel_turn(user_id=user.id, message=ANALYSIS_REQUESTS[0], channel='typed')
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', True)
    tools = get_health_tools(subset=['health_query', 'health_query_batch'])
    assert executor._model_tools_for_turn(tools) == tools


def test_orchestrator_error_survives_model_projection():
    raw = {'synthesis': '请联系专业支持。', 'error': 'upstream_failed', 'status': 'failed'}
    projected = json.loads(ae._project_orchestrator_result(json.dumps(raw)))
    assert projected['error'] == 'upstream_failed'
    assert projected['status'] == 'failed'
