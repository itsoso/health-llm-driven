"""Screenshot regressions must pass routing, Pi and authenticated persistence."""
import json
import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from app.services.intake_plan import parse_intake_plan
from app.services.intake_intent_classifier import classify_intake_intent, classify_intake_subject
from app.services.utterance_intent_classifier import classify_agent_utterance
from tests.test_mixed_supplement_intake_scope import decision
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock, owned_data as owned_data, script_executor,
)


@pytest.fixture(autouse=True)
def _isolate_twin_cache(request, monkeypatch):
    from datetime import datetime
    from app.twin.schema import HealthTwin, TwinMeta
    from app.utils import redis_cache
    if request.node.originalname not in {
        'test_live_provider_to_isolated_authenticated_intake',
        'test_quick_conflicting_quantities_serialize_on_postgres',
    }:
        request.getfixturevalue('isolated_agent_protocol_transport')
    monkeypatch.setattr(redis_cache, 'get_redis_client', lambda: None)
    monkeypatch.setattr(
        'app.twin.builder.build_twin',
        lambda _db, user_id, **kwargs: HealthTwin(
            meta=TwinMeta(user_id=user_id, generated_at=datetime.now().astimezone())),
    )

CASES = [
    ('记录吃了两粒肌酸。', '肌酸', '两粒'),
    ('记录补剂，吃了两粒肌酸。', '肌酸', '两粒'),
    ('记录吃了一粒复合维生素 VB', '复合维生素vb', '一粒'),
    ('请记录一下：我今天吃了一片复合维生素 B。', '复合维生素b', '一片'),
    ('记录吃了2片维生素Ｂ１２。', '维生素b12', '2片'),
]


@pytest.mark.parametrize('text,name,dose', CASES)
def test_same_complete_fact_controls_routing_and_authority(text, name, dose):
    plan = parse_intake_plan(text)
    assert plan.status == 'complete'
    assert [(i.name, i.amount_text) for i in plan.items] == [(name, dose)]
    assert classify_intake_intent(text).kind == 'supplement'
    assert classify_intake_subject(text).kind == 'supplement'
    intent = classify_agent_utterance(text)
    assert (intent.primary, intent.domain, intent.operation) == ('write', 'supplement', 'create')
    assert decision(text, 'supplement', {'supplement_name': name, 'dosage': dose}).action == 'allow'
    assert decision(text, 'diet', {'food_items': dose + name}).action == 'block'


@pytest.mark.asyncio
@pytest.mark.parametrize('text,name,dose', CASES[:3])
@pytest.mark.parametrize('proposal', ['none', 'correct', 'diet', 'truncated_name'])
@pytest.mark.parametrize('existing', [False, True])
async def test_unlabeled_intake_real_pi_api_path(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers,
    text, name, dose, proposal, existing,
):
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.models.daily_health import DietRecord
    if existing:
        definition = SupplementDefinition(user_id=owned_data.id, name=name, dosage='9粒', is_active=True)
        db.add(definition)
        db.commit()
    first = '好的。'
    if proposal not in {'none', 'live'}:
        args = {'record_type': 'supplement', 'data': {'supplement_name': name, 'dosage': dose}}
        if proposal == 'diet':
            args = {'record_type': 'diet', 'data': {'food_items': dose + name, 'meal_type': 'snack'}}
        elif proposal == 'truncated_name':
            args['data']['supplement_name'] = '复合维生素' if '维生素' in name else '吃了肌酸'
        first = [('health_record', args)]
    trace = script_executor(db, monkeypatch, [first, '已完成记录。'])
    if proposal == 'live':
        from app.services.agent_executor import AgentExecutor
        monkeypatch.setattr(trace.executor, '_call_llm_stream',
                            AgentExecutor._call_llm_stream.__get__(trace.executor))
        monkeypatch.setattr(trace.executor, '_build_system_prompt',
                            AgentExecutor._build_system_prompt.__get__(trace.executor))
    headers = auth_user_and_headers[1]
    async def get_json(url, _headers, **kwargs):
        response = client.get(urlsplit(url).path, headers=headers)
        return response.json(), None if response.status_code == 200 else f'API 返回 {response.status_code}'
    async def post_json(url, _headers, payload, **kwargs):
        response = client.post(urlsplit(url).path, headers=headers, json=payload)
        return response.json(), None if response.status_code == 200 else f'API 返回 {response.status_code}'
    monkeypatch.setattr(trace.executor, '_api_get_json', get_json)
    monkeypatch.setattr(trace.executor, '_api_post_json', post_json)
    before_diet = db.query(DietRecord).count()
    turn_id = str(uuid4())
    async def run():
        events = [e async for e in trace.executor.run_stream(
            owned_data.id, text, channel='typed', client_turn_id=turn_id)]
        return next(e['data'] for e in reversed(events) if e['event'] == 'done')
    done = await run()
    assert done['completion_status'] == 'complete', (done.get('turn_outcome'), trace.results)
    definitions = db.query(SupplementDefinition).filter_by(user_id=owned_data.id, name=name).all()
    assert len(definitions) == 1
    assert definitions[0].dosage == ('9粒' if existing else None)
    records = db.query(SupplementRecord).filter_by(user_id=owned_data.id, supplement_id=definitions[0].id).all()
    assert len(records) == 1
    assert records[0].actual_dosage == dose
    assert records[0].record_date == clock[0].date()
    assert records[0].taken is True
    assert db.query(DietRecord).count() == before_diet
    assert len(done['write_receipts']) == 1 and done['write_receipts'][0]['verified'] is True
    replay = await run()
    assert replay['write_receipts'] == done['write_receipts']


@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get('REVA_LIVE_INTAKE_EVAL') != '1', reason='explicit synthetic live evaluation only')
@pytest.mark.parametrize('text,name,dose', CASES[:3])
async def test_live_provider_to_isolated_authenticated_intake(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers, consenting_agent_user,
    text, name, dose,
):
    await test_unlabeled_intake_real_pi_api_path(
        db, monkeypatch, owned_data, clock, client, auth_user_and_headers,
        text, name, dose, 'live', False,
    )


def test_stale_diet_frame_cannot_compile_a_supplement_as_a_meal():
    from dataclasses import replace
    from app.services.agent_kernel.goal_spec import _compile_simple_health_record_goal
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext
    envelope = AgentEnvelope(user_id=1, channel='typed', text=CASES[0][0])
    context = ExecutionContext.for_test(user_id=1, channel='typed')
    stale = replace(build_intent_frame(envelope, context), domain='diet')
    assert _compile_simple_health_record_goal(
        envelope=envelope, context=context, intent=stale, actionable_references=(),
    ) is None


@pytest.mark.parametrize('text,name,dose', CASES[:3])
@pytest.mark.parametrize('prior', ['new', 'definition', 'unknown_dose', 'same_dose', 'different_dose', 'not_taken'])
def test_quick_record_preserves_typed_intake_without_regimen_inference(
    db, client, auth_user_and_headers, text, name, dose, prior,
):
    from datetime import date
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.models.daily_health import DietRecord
    user, headers = auth_user_and_headers
    definition = None
    if prior != 'new':
        definition = SupplementDefinition(user_id=user.id, name=name, dosage='9粒', timing='bedtime')
        db.add(definition)
        db.flush()
        if prior != 'definition':
            db.add(SupplementRecord(user_id=user.id, supplement_id=definition.id,
                record_date=date.today(), taken=prior != 'not_taken',
                actual_dosage=None if prior == 'unknown_dose' else dose if prior == 'same_dose' else '9粒'))
        db.commit()
    before_diet = db.query(DietRecord).count()
    response = client.post('/api/v1/quick-record', headers=headers, json={'text': text})
    if prior in {'different_dose', 'not_taken'}:
        assert response.status_code == 409
        db.expire_all()
        record = db.query(SupplementRecord).filter_by(supplement_id=definition.id).one()
        assert record.actual_dosage == '9粒'
        assert record.taken is (prior != 'not_taken')
        return
    assert response.status_code == 200, response.text
    assert response.json()['success'] is True and response.json()['type'] == 'supplement'
    record_id = response.json()['record_id']
    db.expire_all()
    record = db.get(SupplementRecord, record_id)
    assert record.user_id == user.id and record.record_date == date.today()
    assert record.actual_dosage == dose and record.taken is True
    definition = db.get(SupplementDefinition, record.supplement_id)
    assert definition.name == name
    assert definition.dosage == (None if prior == 'new' else '9粒')
    assert definition.timing == (None if prior == 'new' else 'bedtime')
    assert dose in response.json()['message']
    repeated = client.post('/api/v1/quick-record', headers=headers, json={'text': text})
    assert repeated.status_code == 200 and repeated.json()['record_id'] == record_id
    assert db.query(DietRecord).count() == before_diet
    assert db.query(SupplementRecord).filter_by(user_id=user.id, supplement_id=definition.id).count() == 1


def test_quick_typed_intake_is_authenticated_and_owner_bound(db, client, auth_user_and_headers):
    from app.models.user import User
    from app.models.supplement import SupplementDefinition, SupplementRecord
    user, headers = auth_user_and_headers
    other = User(name='Synthetic other owner', email='intake-other@example.test')
    db.add(other)
    db.flush()
    other_definition = SupplementDefinition(user_id=other.id, name='肌酸', dosage='9粒')
    db.add(other_definition)
    db.commit()
    body = {'text': CASES[0][0]}
    assert client.post('/api/v1/quick-record', json=body).status_code == 401
    response = client.post('/api/v1/quick-record', headers=headers, json=body)
    assert response.status_code == 200
    record = db.get(SupplementRecord, response.json()['record_id'])
    assert record.user_id == user.id and record.supplement_id != other_definition.id
    assert not db.query(SupplementRecord).filter_by(user_id=other.id).all()


def test_quick_conflicting_quantities_serialize_on_postgres(db, auth_user_and_headers):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    from threading import Barrier
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker
    from app.api.quick_record import quick_record, QuickRecordRequest
    from app.models.user import User
    from app.models.supplement import SupplementDefinition, SupplementRecord
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL row lock semantics')
    user, _ = auth_user_and_headers
    owner = user.id
    definition = SupplementDefinition(user_id=owner, name='肌酸')
    db.add(definition)
    db.flush()
    record = SupplementRecord(user_id=owner, supplement_id=definition.id, record_date=date.today(), taken=True)
    db.add(record)
    db.commit()
    record_id = record.id
    db.commit()
    sessions = sessionmaker(bind=db.get_bind())
    start = Barrier(2)
    def write(amount):
        with sessions() as session:
            actor = session.get(User, owner)
            start.wait(timeout=10)
            try:
                result = quick_record(QuickRecordRequest(text=f'记录吃了{amount}粒肌酸。'), actor, session)
                return 200, str(amount) + '粒', result.record_id
            except HTTPException as exc:
                return exc.status_code, str(amount) + '粒', None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [2, 3]))
    assert sorted(r[0] for r in results) == [200, 409]
    winner = next(r for r in results if r[0] == 200)
    db.expire_all()
    assert winner[2] == record_id
    assert db.get(SupplementRecord, record_id).actual_dosage == winner[1]


@pytest.mark.parametrize('text', [
    '记录妈妈吃了两粒肌酸。', '记录明天吃两粒肌酸。', '记录没吃两粒肌酸。',
    '记录吃了一粒复合维生素 VB，这是妈妈的。',
    '记录吃了一粒复合维生素 VB，不要保存。', '记录吃了两粒肌酸激酶。',
])
def test_quick_typed_intake_rejects_unsupported_context(db, client, auth_user_and_headers, text):
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.models.daily_health import DietRecord
    user, headers = auth_user_and_headers
    response = client.post('/api/v1/quick-record', headers=headers, json={'text': text})
    assert response.status_code == 400
    for model in (SupplementDefinition, SupplementRecord, DietRecord):
        assert not db.query(model).filter_by(user_id=user.id).all()


@pytest.mark.parametrize('dose', ['一粒', '两粒'])
@pytest.mark.parametrize('text', [
    '记录妈妈吃了两粒肌酸。', '记录明天吃两粒肌酸。', '记录没吃两粒肌酸。',
    '记录吃了两粒肌酸吗？', '记录吃了两粒肌酸激酶。',
    '记录吃了一粒复合维生素 VB，不要保存。', '记录吃了一粒复合维生素 VB12mg',
    '记录吃了一粒复合维生素 VB，这是妈妈的。',
    '“记录吃了一粒复合维生素 VB”', '记录吃了两粒肌酸软糖。',
])
def test_expansion_does_not_authorize_residue_or_other_subjects(text, dose):
    assert parse_intake_plan(text).status != 'complete'
    for name in ('肌酸', '复合维生素vb'):
        assert decision(text, 'supplement', {'supplement_name': name, 'dosage': dose}).action == 'block'
