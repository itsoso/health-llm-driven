"""Synthetic dinner request exercises the real Pi and persistence path."""
from uuid import uuid4
import pytest
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock,
    owned_data as owned_data, script_executor,
)

MESSAGE = '记录晚餐 白条鱼肉100克 虾50克 羊肉50克 蔬菜100克 海参50克'

@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [False, True])
async def test_explicit_dinner_records_when_provider_returns_no_tool(db, monkeypatch, owned_data, clock, client, auth_user_and_headers, retry):
    from app.models.daily_health import DietRecord
    trace = script_executor(db, monkeypatch, ['收到。'])
    async def dispatch(request, token):
        assert request.tool_name == 'health_record'
        assert request.arguments['record_type'] == 'diet'
        result = client.post('/api/v1/diet/records', json=request.arguments['data'],
                             headers=auth_user_and_headers[1])
        assert result.status_code == 200, result.text
        return result.text
    monkeypatch.setattr(trace.executor, '_dispatch_tool_request', dispatch)
    async def estimate(foods):
        assert foods == MESSAGE.split(' ', 1)[1]
        return {'calories': 380, 'protein': 45, 'carbs': 12, 'fat': 16, 'fiber': 4}
    monkeypatch.setattr('app.services.agent_executor._estimate_simple_diet_nutrition', estimate)
    kwargs = {}
    message = MESSAGE
    if retry:
        from app.services.agent_conversation_service import AgentConversationService
        from tests.test_agent_write_retry_recovery import _save_failed_turn
        service = AgentConversationService(db)
        conversation = service.get_or_create_conversation(owned_data.id, None)
        _save_failed_turn(service, owned_data.id, conversation.id,
                          image_url=None, message=MESSAGE)
        kwargs['conversation_id'] = conversation.id
        message = '重试'
    turn_id = str(uuid4())
    events = [e async for e in trace.executor.run_stream(
        owned_data.id, message, channel='typed', client_turn_id=turn_id, **kwargs,
    )]
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert done['write_receipts']
    rows = db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).all()
    assert len(rows) == 1
    assert rows[0].meal_type == 'dinner'
    replay = [e async for e in trace.executor.run_stream(
        owned_data.id, message, channel='typed', client_turn_id=turn_id, **kwargs,
    )]
    replay_done = next(e['data'] for e in reversed(replay) if e['event'] == 'done')
    assert replay_done['write_receipts'] == done['write_receipts']
    assert db.query(DietRecord).filter_by(user_id=owned_data.id,
                                       record_date=clock[0].date()).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['runtime', 'readonly', 'nutrition'])
async def test_preplanned_dinner_keeps_fail_closed_boundaries(db, monkeypatch, owned_data, boundary):
    trace = script_executor(db, monkeypatch, ['本轮没有记录。'])
    estimated = []
    async def estimate(foods):
        estimated.append(foods)
        return None
    async def forbidden(*args, **kwargs):
        raise AssertionError('blocked or incomplete meal must not dispatch a write')
    monkeypatch.setattr('app.services.agent_executor._estimate_simple_diet_nutrition', estimate)
    monkeypatch.setattr(trace.executor, '_dispatch_tool_request', forbidden)
    kwargs = {'runtime_write_block_reason': 'circuit_paused'} if boundary == 'runtime' else (
        {'read_only_tools': True} if boundary == 'readonly' else {})
    events = [e async for e in trace.executor.run_stream(
        owned_data.id, MESSAGE, channel='typed', client_turn_id=str(uuid4()), **kwargs)]
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert not done['write_receipts']
    if boundary != 'nutrition':
        assert not estimated
    else:
        assert len(estimated) == 1
