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
async def test_mixed_intake_real_records_receipts_and_replay(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers, diet_fails,
):
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
    trace = script_executor(db, monkeypatch, [calls, '处理完毕。'])
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
        events = [e async for e in trace.executor.run_stream(owned_data.id, MESSAGE, channel='typed', client_turn_id=turn)]
        return next(e['data'] for e in reversed(events) if e['event'] == 'done')
    done = await run()
    assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1
    supplement = db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).one()
    assert supplement.record_date == clock[0].date()
    meals = db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).all()
    assert len(meals) == (0 if diet_fails else 1)
    if meals:
        assert '豆浆' in meals[0].food_items and '锌片' not in meals[0].food_items
    assert len(done['write_receipts']) == (1 if diet_fails else 2)
    assert done['completion_status'] == ('error' if diet_fails else 'complete')
    replay = await run()
    assert replay['write_receipts'] == done['write_receipts']
    assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1
    assert db.query(DietRecord).filter_by(user_id=owned_data.id, record_date=clock[0].date()).count() == len(meals)
