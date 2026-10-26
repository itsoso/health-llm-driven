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
@pytest.mark.parametrize("request_text, foods", [
    (MESSAGE, MESSAGE.split(' ', 1)[1]),
    ('记录晚餐 吃了五颗干枣', '五颗干枣'),
])
async def test_explicit_dinner_records_when_provider_returns_no_tool(db, monkeypatch, owned_data, clock, client, auth_user_and_headers, retry, request_text, foods):
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
    async def estimate(food_description):
        assert food_description == foods
        return {'calories': 380, 'protein': 45, 'carbs': 12, 'fat': 16, 'fiber': 4}
    monkeypatch.setattr('app.services.agent_executor._estimate_simple_diet_nutrition', estimate)
    kwargs = {}
    message = request_text
    if retry:
        from app.services.agent_conversation_service import AgentConversationService
        from tests.test_agent_write_retry_recovery import _save_failed_turn
        service = AgentConversationService(db)
        conversation = service.get_or_create_conversation(owned_data.id, None)
        _save_failed_turn(service, owned_data.id, conversation.id,
                          image_url=None, message=request_text)
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
    assert rows[0].food_items == foods
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


@pytest.mark.asyncio
@pytest.mark.parametrize('repair_kind', ['complete', 'incomplete', 'different_food'])
async def test_nutrition_timeout_allows_one_validated_repair_without_duplicate_write(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers, repair_kind,
):
    from datetime import datetime
    from app.models.daily_health import DietRecord

    clock[0] = datetime.fromisoformat('2026-10-27T00:00:00+08:00')
    repair_complete = repair_kind == 'complete'
    incomplete = ('health_record', {'record_type': 'diet', 'data': {
        'meal_type': 'dinner', 'food_items': '五颗干枣',
    }})
    repaired = ('health_record', {'record_type': 'diet', 'data': {
        'meal_type': 'dinner',
        'food_items': '其他食物' if repair_kind == 'different_food' else '五颗干枣',
        'record_date': '2026-10-27',
        **({'calories': 100, 'protein': 1, 'carbs': 24, 'fat': 0.2, 'fiber': 2}
           if repair_kind != 'incomplete' else {}),
    }})
    trace = script_executor(db, monkeypatch, [incomplete, repaired, '已记录。'])
    estimates, dispatches = [], []

    def timed_out(foods, *, timeout_seconds):
        estimates.append(foods)
        return {'success': False, 'timed_out': True, 'foods': []}

    async def dispatch(request, token):
        dispatches.append(request)
        assert request.tool_name == 'health_record'
        assert request.arguments['data']['food_items'] == '五颗干枣'
        assert request.arguments['data']['record_date'] == '2026-10-27'
        result = client.post('/api/v1/diet/records', json=request.arguments['data'],
                             headers=auth_user_and_headers[1])
        assert result.status_code == 200, result.text
        return result.text

    monkeypatch.setattr('app.services.ai.food_recognition.food_recognition_service.'
                        'estimate_nutrition_from_text', timed_out)
    monkeypatch.setattr(trace.executor, '_dispatch_tool_request', dispatch)
    turn_id = str(uuid4())
    events = [e async for e in trace.executor.run_stream(
        owned_data.id, '记录晚餐 吃了五颗干枣', channel='typed', client_turn_id=turn_id)]
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert estimates == ['五颗干枣']
    assert len(trace.calls) == (3 if repair_complete else 2)
    assert len(dispatches) == int(repair_complete), done
    assert bool(done['write_receipts']) is repair_complete
    assert done['completion_status'] == ('complete' if repair_complete else 'error')
    assert done['perf']['nutrition_estimate_calls'] == 1
    assert done['perf']['nutrition_estimate_timed_out'] is True
    assert done['perf']['nutrition_estimate_ms'] is not None
    assert db.query(DietRecord).filter_by(user_id=owned_data.id,
        record_date=clock[0].date(), meal_type='dinner').count() == int(repair_complete)
    if repair_complete:
        replay = [e async for e in trace.executor.run_stream(
            owned_data.id, '记录晚餐 吃了五颗干枣', channel='typed', client_turn_id=turn_id)]
        replay_done = next(e['data'] for e in reversed(replay) if e['event'] == 'done')
        assert replay_done['write_receipts'] == done['write_receipts']
        assert len(dispatches) == 1
    else:
        visible = ''.join(e['data'].get('content', '') for e in events if e.get('event') == 'token')
        assert '已记录' not in visible
