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
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock, owned_data as owned_data, script_executor,
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


@pytest.mark.parametrize('text', [
    '记录妈妈吃了两粒肌酸。', '记录明天吃两粒肌酸。', '记录没吃两粒肌酸。',
    '记录吃了两粒肌酸吗？', '记录吃了两粒肌酸激酶。',
    '记录吃了一粒复合维生素 VB，不要保存。', '记录吃了一粒复合维生素 VB12mg',
    '记录吃了一粒复合维生素 VB，这是妈妈的。',
    '“记录吃了一粒复合维生素 VB”', '记录吃了两粒肌酸软糖。',
])
def test_expansion_does_not_authorize_residue_or_other_subjects(text):
    assert parse_intake_plan(text).status != 'complete'
    for name in ('肌酸', '复合维生素vb'):
        assert decision(text, 'supplement', {'supplement_name': name, 'dosage': '两粒'}).action == 'block'
