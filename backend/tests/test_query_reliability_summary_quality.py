"""Summary quality floor at every actual provider boundary."""
from datetime import datetime
from types import SimpleNamespace
import pytest
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan

@pytest.fixture(autouse=True)
def isolate(isolated_agent_protocol_transport):
    pass

def summary_executor(db):
    executor = AgentExecutor(db)
    executor._current_user_id = 41
    executor._turn_daily_read_plan = resolve_daily_read_plan('给我今天总结', datetime(2026, 9, 12))
    assert executor._turn_daily_read_plan.is_summary
    return executor

@pytest.mark.parametrize('mode', ['off', 'shadow', 'on'])
def test_summary_explicit_fast_cannot_survive_route(db, monkeypatch, mode):
    executor = summary_executor(db)
    executor._request_model_id = 'qwen3.6-flash'
    monkeypatch.setattr('app.services.agent_executor.settings.staged_response_mode', mode)
    monkeypatch.setattr('app.services.llm.task_routing.pick_model_id_by_tier', lambda *a, **k: 'qwen3.8-max-preview')
    executor._configure_staged_answer_routing('给我今天总结', has_attachments=False)
    assert executor._requires_quality_floor()
    assert executor._staged_answer_task_tier in {'balanced', 'high_stakes'}
    assert executor._request_model_id == 'qwen3.8-max-preview'
    monkeypatch.setattr('app.services.agent_executor.settings.task_tiered_routing', True)
    assert executor._maybe_fast_route_tool_round(executor._request_model_id) is None

@pytest.mark.parametrize('model_id,allowed', [('qwen3.7-max', True), ('qwen3.6-flash', False), ('unknown-synthetic', False)])
def test_summary_empty_picker_actual_provider_quality(db, monkeypatch, model_id, allowed):
    executor = summary_executor(db)
    monkeypatch.setattr('app.services.agent_executor.settings.staged_response_mode', 'off')
    monkeypatch.setattr('app.services.llm.task_routing.pick_model_id_by_tier', lambda *a, **k: None)
    executor._configure_staged_answer_routing('给我今天总结', has_attachments=False)
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_user', lambda *a, **k: SimpleNamespace(model=model_id, provider_name='synthetic'))
    monkeypatch.setattr(executor, '_user_effective_model_id', lambda: model_id)
    if allowed:
        provider, _ = executor._resolve_chat_provider([])
        assert provider.model == model_id
    else:
        with pytest.raises(RuntimeError):
            executor._resolve_chat_provider([])

@pytest.mark.asyncio
async def test_summary_direct_fast_cannot_execute(db, monkeypatch):
    executor = summary_executor(db)
    monkeypatch.setattr('app.services.agent_executor.settings.agent_base_url', 'http://synthetic.invalid')
    monkeypatch.setattr('app.services.agent_executor.settings.agent_api_key', 'synthetic-test-key')
    monkeypatch.setattr('app.services.agent_executor.settings.agent_model', 'qwen3.6-flash')
    calls = []
    async def direct(*a, **k):
        calls.append(True)
        return {'content': 'must not run', 'finish_reason': 'stop'}
    monkeypatch.setattr(executor, '_call_llm_direct', direct)
    with pytest.raises(RuntimeError):
        await executor._call_llm([], [])
    assert calls == []

def test_summary_stable_fallback_cannot_execute(db):
    executor = summary_executor(db)
    with pytest.raises(RuntimeError):
        executor._stable_fallback_provider(False)

def test_plain_diet_read_does_not_gain_summary_quality_scope(db):
    executor = AgentExecutor(db)
    executor._turn_daily_read_plan = resolve_daily_read_plan('今天我吃了什么', datetime(2026, 9, 12))
    assert not executor._turn_daily_read_plan.is_summary
    assert not executor._requires_quality_floor()
