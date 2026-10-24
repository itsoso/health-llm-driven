"""Synthetic mixed intake through Pi, gateway and authenticated API handlers."""
from urllib.parse import urlsplit
from uuid import uuid4
from datetime import datetime
import pytest
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock,
    owned_data as owned_data, script_executor,
)

MESSAGE = '记录补剂 吃了一粒锌片 喝了一杯豆浆'

@pytest.mark.asyncio
@pytest.mark.parametrize('diet_fails', [False, True])
@pytest.mark.parametrize('message', [MESSAGE, '记录一下，喝了一杯豆浆，吃了一粒锌片'])
@pytest.mark.parametrize('omit_diet', [False, True])
@pytest.mark.parametrize('timezone_changed', [False, True])
async def test_mixed_intake_real_records_receipts_and_replay(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers, diet_fails, message, omit_diet, timezone_changed,
):
    if timezone_changed and (not diet_fails or omit_diet):
        pytest.skip('timezone guard applies to a partial retry')
    from app.models.daily_health import DietRecord
    from app.models.supplement import SupplementDefinition, SupplementRecord
    monkeypatch.setattr('app.api.nfc._last_tap', {})
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr('app.api.nfc.datetime', FrozenDatetime)
    definition = SupplementDefinition(user_id=owned_data.id, name='锌片', dosage='1粒', is_active=True)
    db.add(definition)
    db.commit()
    calls = [
        ('health_record', {'record_type': 'supplement', 'data': {'supplement_name': '锌片', 'dosage': '1粒'}}),
        ('health_record', {'record_type': 'diet', 'data': {'food_items': '豆浆一杯', 'meal_type': 'snack',
         'calories': 80, 'protein': 6, 'carbs': 4, 'fat': 4, 'fiber': 1}}),
    ]
    if omit_diet:
        calls = calls[:1]
    retry_calls = [('health_record', {'record_type': 'diet', 'data': {
        'food_items': '豆浆一杯', 'meal_type': 'snack', 'calories': 80,
        'protein': 6, 'carbs': 4, 'fat': 4, 'fiber': 1}})]
    steps = [calls, '处理完毕。']
    trace = script_executor(db, monkeypatch, steps)
    headers = auth_user_and_headers[1]
    async def get_json(url, _headers, **kwargs):
        response = client.get(urlsplit(url).path, headers=headers)
        return response.json(), None if response.status_code == 200 else f'API 返回 {response.status_code}'
    async def post_json(url, _headers, payload, **kwargs):
        response = client.post(urlsplit(url).path, headers=headers, json=payload)
        return response.json(), None if response.status_code == 200 else f'API 返回 {response.status_code}'
    async def post(url, _headers, payload, **kwargs):
        response = client.post(urlsplit(url).path, headers=headers, json=payload)
        return response.text
    monkeypatch.setattr(trace.executor, '_api_get_json', get_json)
    monkeypatch.setattr(trace.executor, '_api_post_json', post_json)
    monkeypatch.setattr(trace.executor, '_api_post', post)
    original = trace.executor._dispatch_tool_request
    async def dispatch(request, token):
        if diet_fails and request.arguments.get('record_type') == 'diet':
            return '{"status":"failed","success":false,"dispatch_started":false,"error_code":"synthetic_diet_rejected"}'
        return await original(request, token)
    monkeypatch.setattr(trace.executor, '_dispatch_tool_request', dispatch)
    turn = str(uuid4())
    async def run():
        events = [e async for e in trace.executor.run_stream(owned_data.id, message, channel='typed', client_turn_id=turn)]
        return next(e['data'] for e in reversed(events) if e['event'] == 'done')
    done = await run()
    assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1
    supplement = db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).one()
    assert supplement.record_date == clock[0].date()
    meals = db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).all()
    incomplete = diet_fails or omit_diet
    assert len(meals) == (0 if incomplete else 1)
    if meals:
        assert '豆浆' in meals[0].food_items and '锌片' not in meals[0].food_items
    assert len(done['write_receipts']) == (1 if incomplete else 2)
    assert done['completion_status'] == ('error' if incomplete else 'complete')
    assert done['turn_outcome']['status'] == ('partial' if incomplete else 'complete')
    if diet_fails and not omit_diet:
        from app.models.agent_conversation import AgentMessage
        source = db.query(AgentMessage).filter_by(role='user').order_by(AgentMessage.id.desc()).first()
        assert source.meta.get('intake_retry_plan'), source.meta
        assert any(op.get('no_side_effect') is True for op in source.meta['write_operations'].values())
    replay = await run()
    assert replay['write_receipts'] == done['write_receipts']
    assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1
    assert db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).count() == len(meals)
    if diet_fails and not omit_diet:
        from app.services.intake_retry import resolve_intake_retry_selection
        assert resolve_intake_retry_selection(source_text=source.content, owner_id=owned_data.id,
            conversation_id=source.conversation_id, source_message_id=source.id,
            meta=source.meta, now=clock[0]) is not None, source.meta
        assert done.get('recovery_action', {}).get('scope') == 'intake_pending_items', done
        class RetryDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromisoformat(clock[0].astimezone(tz).isoformat())
        monkeypatch.setattr('app.services.intake_retry.datetime', RetryDatetime)
        diet_fails = False
        steps[len(trace.calls):] = [retry_calls, '已完成剩余记录。']
        if timezone_changed:
            from dataclasses import replace
            from zoneinfo import ZoneInfo
            from app.services.agent_kernel.types import ExecutionContext
            original_now = ExecutionContext.now
            def changed_now(cls, **kwargs):
                context = original_now(**kwargs)
                return replace(context, timezone='America/Los_Angeles',
                               current_time=context.current_time.astimezone(ZoneInfo('America/Los_Angeles')))
            monkeypatch.setattr(ExecutionContext, 'now', classmethod(changed_now))
        retry_turn = str(uuid4())
        async def retry():
            events = [e async for e in trace.executor.run_stream(
                owned_data.id, '重试', conversation_id=source.conversation_id,
                channel='typed', client_turn_id=retry_turn)]
            return next(e['data'] for e in reversed(events) if e['event'] == 'done')
        retried = await retry()
        if timezone_changed:
            assert retried['recovery_error'] == 'retry_source_time_context_changed'
            assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1
            assert db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).count() == 0
            return
        assert retried['completion_status'] == 'complete', retried
        assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1
        assert db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).count() == 1
        replayed_retry = await retry()
        assert replayed_retry['write_receipts'] == retried['write_receipts']
        assert db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).count() == 1
