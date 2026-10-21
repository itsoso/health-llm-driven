import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services.agent_executor import AgentExecutor


def payload(**patch):
    return dict(id=1175, user_id=7, record_date='2026-10-14', meal_type='dinner',
                food_items='面和饮品', calories=650.1234, protein=None, carbs=70.0,
                fat=24.0, fiber=None, updated_at='2026-10-14T10:01:00+00:00', **patch)


@pytest.mark.asyncio
async def test_successful_owned_update_emits_durable_card_from_api_row(monkeypatch):
    executor = AgentExecutor(None)
    executor._current_user_id = 7
    monkeypatch.setattr(executor, '_api_put', AsyncMock(return_value=json.dumps(payload())))
    monkeypatch.setattr(executor, '_invalidate_twin_after_mutation', lambda: None)
    result = await executor._exec_health_manage('http://test', {}, {
        'record_type': 'diet', 'operation': 'update', 'record_id': 1175,
        'data': {'calories': 900, 'food_items': '不可信请求文本'},
    })
    assert json.loads(result)['calories'] == 650.1234
    card = executor._turn_contextual_diet_cards[0]
    assert card['data']['recorded'] is True
    assert card['data']['user_id'] == 7
    assert card['data']['calories'] == 650.12
    assert card['data']['protein'] is None
    assert card['data']['food_items'] == '面和饮品'
    assert card['data']['updated_at'] == '2026-10-14T10:01:00+00:00'
    assert card['data']['adjust_record']['calories'] == 650.1234


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [
    '已更新，热量650', 'Error: failed', json.dumps({'id':1175, 'status':'pending'}),
    json.dumps({**payload(), 'user_id':8}), json.dumps({**payload(), 'id':1176}),
    json.dumps({**payload(), 'updated_at':None}), json.dumps({**payload(), 'success':False}),
    json.dumps({**payload(), 'updated_at':'2026-10-14'}), json.dumps({**payload(), 'calories':'650'}),
    json.dumps({**payload(), 'food_items':None}), json.dumps({**payload(), 'record_date':'bad'}),
])
async def test_failure_pending_or_foreign_results_never_emit_saved_card(monkeypatch, response):
    executor = AgentExecutor(None)
    executor._current_user_id = 7
    monkeypatch.setattr(executor, '_api_put', AsyncMock(return_value=response))
    monkeypatch.setattr(executor, '_invalidate_twin_after_mutation', lambda: None)
    await executor._exec_health_manage('http://test', {}, {
        'record_type':'diet', 'operation':'update', 'record_id':1175, 'data': {'calories':650},
    })
    assert executor._turn_contextual_diet_cards == []


def test_photo_autosave_card_has_owner_and_database_revision():
    executor = AgentExecutor(None)
    executor._current_user_id = 7
    row = SimpleNamespace(**{**payload(), 'record_date':date(2026,10,14),
                            'updated_at':datetime(2026,10,14,10,1,tzinfo=timezone.utc), 'ai_confidence':0.95})
    asset = SimpleNamespace(id='asset-test', user_id=7, storage_key='chat/test.jpeg', capture_session_id='session-test', origin_message_id=1)
    card = executor._contextual_diet_recorded_card(SimpleNamespace(record=row, photo_assets=[asset], photo_asset=asset))
    assert card['data']['user_id'] == 7
    assert card['data']['updated_at'] == row.updated_at.isoformat()
    assert card['data']['adjust_record']['calories'] == 650.1234


def test_verified_text_and_photo_use_the_same_saved_meal_contract():
    from app.services.post_record_quality import build_post_record_quality_response

    saved = payload()
    text_card = build_post_record_quality_response(
        'diet', {**saved, 'calories': 900, 'food_items': '请求值不是保存结果'},
        result=json.dumps(saved), user_id=7, write_verified=True,
    )['cards'][0]
    executor = AgentExecutor(None)
    executor._current_user_id = 7
    row = SimpleNamespace(**{**saved, 'record_date': date(2026, 10, 14),
        'updated_at': datetime(2026, 10, 14, 10, 1, tzinfo=timezone.utc), 'ai_confidence': 0.95})
    asset = SimpleNamespace(id='asset-test', user_id=7, storage_key='chat/test.jpeg',
                           capture_session_id='session-test', origin_message_id=1)
    photo_card = executor._contextual_diet_recorded_card(
        SimpleNamespace(record=row, photo_assets=[asset], photo_asset=asset))
    assert text_card['type'] == photo_card['type'] == 'diet_draft'
    for key in ('recorded', 'record_id', 'user_id', 'record_date', 'meal_type',
                'food_items', 'calories', 'protein', 'carbs', 'fat', 'fiber',
                'updated_at', 'adjust_record'):
        assert text_card['data'][key] == photo_card['data'][key], key
    assert text_card['data']['calories'] == 650.12
    assert text_card['data']['adjust_record']['calories'] == 650.1234
    assert text_card['data']['protein'] is None
    assert text_card['data']['source'] == 'text'
    assert 'photo_url' not in text_card['data']
    assert not any(a['action'] == 'diet_record.create' for a in text_card['actions'])


@pytest.mark.parametrize('verified', [False, None])
def test_unverified_text_write_cannot_become_a_saved_meal_card(verified):
    from app.services.post_record_quality import build_post_record_quality_response

    response = build_post_record_quality_response('diet', payload(),
        result=json.dumps(payload()), user_id=7, write_verified=verified)
    assert response is None or all(card['type'] != 'diet_draft' for card in response['cards'])


@pytest.mark.asyncio
async def test_run_stream_owned_put_card_receipt_and_persisted_history(
    db, client, auth_user_and_headers, consenting_agent_user, monkeypatch,
):
    """Only the provider is synthetic: gateway, authenticated API and DB are real."""
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('production write semantics require PostgreSQL')
    from urllib.parse import urlsplit
    from app.models.daily_health import DietRecord
    from app.models.agent_conversation import AgentMessage
    from app.twin.schema import HealthTwin, TwinMeta

    user, headers = auth_user_and_headers
    row = DietRecord(user_id=user.id, record_date=date.today(), meal_type='dinner',
                     food_items='合成面餐', calories=900, protein=42, carbs=78, fat=43, fiber=None)
    db.add(row)
    db.commit()
    record_id = row.id
    executor = AgentExecutor(db)
    requests = []
    monkeypatch.setattr('app.twin.builder.build_twin', lambda _db, user_id, **kwargs: HealthTwin(
        meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc))))
    monkeypatch.setattr('app.utils.redis_cache.get_redis_client', lambda: None)
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **kw: 'SYS')

    async def get_json(url, request_headers):
        parsed = urlsplit(url)
        response = client.get(parsed.path + ('?' + parsed.query if parsed.query else ''), headers=request_headers)
        assert response.status_code == 200, response.text
        return response.json(), None

    async def get(url, request_headers):
        value, _ = await get_json(url, request_headers)
        return json.dumps(value, ensure_ascii=False)

    async def put(url, request_headers, data):
        response = client.put(urlsplit(url).path, headers=request_headers, json=data)
        requests.append(response.status_code)
        assert response.status_code == 200, response.text
        return response.text

    monkeypatch.setattr(executor, '_api_get_json', get_json)
    monkeypatch.setattr(executor, '_api_get', get)
    monkeypatch.setattr(executor, '_api_put', put)
    rounds = 0
    async def model(messages, tools):
        nonlocal rounds
        rounds += 1
        if rounds <= 2:
            args = {'record_type':'diet', 'operation':'list' if rounds == 1 else 'update', 'record_id':record_id, 'date':date.today().isoformat()}
            if rounds == 2:
                args['data'] = {'calories':650.1234}
            yield {'type':'tool_calls', 'tool_calls':[{'id':f'synthetic-diet-{rounds}', 'type':'function',
                'function':{'name':'health_manage', 'arguments':json.dumps(args)}}]}
            yield {'type':'finish', 'finish_reason':'tool_calls'}
        else:
            yield {'type':'content', 'text':'已更新本餐热量。'}
            yield {'type':'finish', 'finish_reason':'stop'}
    monkeypatch.setattr(executor, '_call_llm_stream', model)
    token = headers['Authorization'].split(' ', 1)[1]
    events = [event async for event in executor.run_stream(
        user_id=user.id, message='我吃了二分之一，其实是三人份，重新修改晚餐的热量和分量。',
        user_auth_token=token, client_turn_id='synthetic-diet-nutrition-refresh',
    )]
    done = next(event['data'] for event in events if event.get('event') == 'done')
    assert requests == [200], done
    assert done['completion_status'] == 'complete', done
    assert any(receipt['resource_id'] == str(record_id) and receipt['verified'] is True
               for receipt in done['write_receipts'])
    cards = [card for card in done['cards'] if card['type'] == 'diet_draft']
    assert len(cards) == 1, done
    card = cards[0]['data']
    assert card['user_id'] == user.id and card['record_id'] == record_id
    assert card['calories'] == 450 and card['fiber'] is None
    assert card['updated_at']
    db.expire_all()
    assert db.get(DietRecord, record_id).calories == 450
    message = db.get(AgentMessage, done['message_id'])
    assert message is not None
    assert any(c['data']['record_id'] == record_id for c in message.meta['cards'] if c['type'] == 'diet_draft')
