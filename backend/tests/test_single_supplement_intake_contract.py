"""One current-turn intake must survive parsing, repair, gateway and replay."""
import json
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from app.services.agent_executor import (
    _build_deterministic_supplement_record_tool_calls,
    _record_intent_needs_detail_message,
)
from app.services.intake_plan import parse_intake_plan
from tests.test_mixed_supplement_intake_scope import decision
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock, owned_data as owned_data, script_executor,
)


@pytest.mark.parametrize('name', ['肌酸', '鱼油', '锌片', '甘氨酸镁'])
@pytest.mark.parametrize('separator', ['', '，', '：'])
def test_single_intake_has_one_exact_identity_across_consumers(name, separator):
    text = f'记录补剂{separator}吃了两粒{name}。'
    plan = parse_intake_plan(text)
    assert plan.status == 'complete'
    assert [(i.name, i.amount_text) for i in plan.items] == [(name, '两粒')]
    calls = _build_deterministic_supplement_record_tool_calls(text, write_receipts=[])
    assert len(calls) == 1
    args = json.loads(calls[0]['function']['arguments'])
    assert args == {'record_type': 'supplement', 'data': {
        'supplement_name': name, 'dosage': '两粒'}}
    assert decision(text, 'supplement', args['data']).action == 'allow'


@pytest.mark.parametrize('text', [
    '不要记录补剂，吃了两粒肌酸。', '妈妈说记录补剂，吃了两粒肌酸。',
    '记录补剂，妈妈吃了两粒肌酸。', '明天记录补剂，吃了两粒肌酸。',
    '记录补剂，没吃两粒肌酸。', '记录补剂，准备吃两粒肌酸。',
    '记录补剂，吃了两粒肌酸吗？', '“记录补剂，吃了两粒肌酸。”',
    '记录补剂，吃了两粒肌酸，不要保存。', '记录补剂，吃了两三粒肌酸。',
    '记录补剂，吃了两粒肌酸激酶。', '记录补剂，吃了两粒肌酸，这是妈妈的。',
])
def test_non_authorizing_text_never_gains_intake_authority(text):
    assert parse_intake_plan(text).status != 'complete'
    assert decision(text, 'supplement', {'supplement_name': '肌酸', 'dosage': '2粒'}).action == 'block'


@pytest.mark.parametrize('data', [
    {'supplement_name': '鱼油', 'dosage': '2粒'},
    {'supplement_name': '肌酸', 'dosage': '3粒'},
    {'supplement_name': '肌酸', 'dosage': '2克'},
    {'supplement_name': '肌酸', 'dosage': '2粒', 'items': []},
])
def test_model_cannot_change_exact_intake(data):
    assert decision('记录补剂，吃了两粒肌酸。', 'supplement', data).action == 'block'


def test_unresolved_target_does_not_invent_create_update_ambiguity():
    reply = _record_intent_needs_detail_message(
        '记录补剂，吃了两粒肌酸。',
        reason_codes=('health_record_authorization_target_unresolved',),
    )
    assert '新增' not in reply and '更新' not in reply
    assert '没有写入' in reply


@pytest.mark.asyncio
@pytest.mark.parametrize('separator', ['', '，'])
@pytest.mark.parametrize('model_proposes_write', [False, True])
@pytest.mark.parametrize('existing_definition', [False, True])
async def test_single_intake_real_api_persists_once_even_when_model_omits_tool(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers,
    separator, model_proposes_write, existing_definition,
):
    from datetime import datetime
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.models.agent_conversation import AgentMessage

    monkeypatch.setattr('app.api.nfc._last_tap', {})
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr('app.api.nfc.datetime', FrozenDatetime)
    if existing_definition:
        definition = SupplementDefinition(user_id=owned_data.id, name='肌酸', dosage='1粒', is_active=True)
        db.add(definition)
        db.commit()
    first = [('health_record', {'record_type': 'supplement', 'data': {
        'supplement_name': '肌酸', 'dosage': '2粒'}})] if model_proposes_write else '好的。'
    trace = script_executor(db, monkeypatch, [first, '已完成记录。'])
    headers = auth_user_and_headers[1]
    async def get_json(url, _headers, **kwargs):
        response = client.get(urlsplit(url).path, headers=headers)
        return response.json(), None if response.status_code == 200 else f'API 返回 {response.status_code}'
    async def post_json(url, _headers, payload, **kwargs):
        response = client.post(urlsplit(url).path, headers=headers, json=payload)
        return response.json(), None if response.status_code == 200 else f'API 返回 {response.status_code}'
    monkeypatch.setattr(trace.executor, '_api_get_json', get_json)
    monkeypatch.setattr(trace.executor, '_api_post_json', post_json)
    turn_id = str(uuid4())
    async def run():
        events = [event async for event in trace.executor.run_stream(
            owned_data.id, f'记录补剂{separator}吃了两粒肌酸。',
            channel='typed', client_turn_id=turn_id,
        )]
        return next(event['data'] for event in reversed(events) if event['event'] == 'done')
    done = await run()
    definition = db.query(SupplementDefinition).filter_by(user_id=owned_data.id, name='肌酸').one()
    if existing_definition:
        assert definition.dosage == '1粒'  # Actual intake must not rewrite the regimen.
    records = db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).all()
    assert len(records) == 1, (done.get('turn_outcome'), [result for _, result in trace.results])
    assert records[0].taken is True
    assert records[0].actual_dosage in ('2粒', '两粒')
    assert records[0].record_date == clock[0].date()
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    assert len(done['write_receipts']) == 1
    assert done['write_receipts'][0]['verified'] is True
    assert '还没记下来' not in db.get(AgentMessage, done['message_id']).content
    replayed = await run()
    assert replayed['write_receipts'] == done['write_receipts']
    assert db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definition.id).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('override', [
    {'user_id': 2}, {'supplement_id': 2}, {'taken': False}, {'taken': 'true'},
    {'id': None}, {'actual_dosage': None}, {'actual_dosage': '3粒'},
    {'record_date': '2000-01-01'}, {'status': 'failed'}, {'record_id': 999},
])
async def test_explicit_intake_does_not_verify_incomplete_or_conflicting_receipts(
    db, monkeypatch, clock, override,
):
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = '记录补剂，吃了两粒肌酸。'
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: clock[0])
    async def post(*args, **kwargs):
        return {'id': 10, 'user_id': 1, 'supplement_id': 1, 'taken': True,
                'record_date': clock[0].date().isoformat(), 'actual_dosage': '2粒', **override}, None
    monkeypatch.setattr(executor, '_api_post_json', post)
    result = json.loads(await executor._record_explicit_supplement_intake(
        'http://testserver', {}, definition_id=1, name='肌酸'))
    assert result['status'] == 'unverified'
    assert result['verified'] is False
    assert 'record_id' not in result


@pytest.mark.parametrize('kwargs', [
    {'has_attachment': True, 'write_receipts': []},
    {'write_receipts': [{'verified': True, 'record_id': 123}]},
])
def test_existing_receipt_or_attachment_never_injects_another_intake(kwargs):
    assert _build_deterministic_supplement_record_tool_calls(
        '记录补剂，吃了两粒肌酸。', **kwargs) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('error,status', [
    ('API 返回 401', 'rejected'), ('API 返回 403', 'rejected'),
    ('API 返回 500', 'unverified'), ('timeout', 'unverified'),
])
async def test_explicit_intake_failed_response_never_claims_saved(
    db, monkeypatch, clock, error, status,
):
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = '记录补剂，吃了两粒肌酸。'
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: clock[0])
    async def post(*args, **kwargs):
        return None, error
    monkeypatch.setattr(executor, '_api_post_json', post)
    result = json.loads(await executor._record_explicit_supplement_intake(
        'http://testserver', {}, definition_id=1, name='肌酸'))
    assert result['status'] == status
    assert 'record_id' not in result
    if status == 'rejected':
        assert result['dispatch_started'] is False
