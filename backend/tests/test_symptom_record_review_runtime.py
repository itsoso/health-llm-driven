"""Real dispatcher/database and final-response checks using synthetic records."""
import json
from dataclasses import replace
from datetime import date
import pytest
from app.models.medication import Medication, MedicationLog
from app.models.user import User
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from tests.test_recent_workout_read_regression import snapshot
from tests.test_symptom_record_review_scope import REQUEST
from tests.test_agent_composed_synthesis_projection import run_projection
from tests.test_agent_read_repair_round_budget import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock, four_domain_user as four_domain_user, owned_data as owned_data,
)


@pytest.mark.asyncio
async def test_medication_history_joins_both_owners_and_keeps_all_statuses(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    other = User(name='Synthetic other', email='record-review-other@example.test')
    db.add(other); db.flush()
    own = Medication(user_id=user.id, name='Synthetic historical', is_active=False)
    foreign = Medication(user_id=other.id, name='FOREIGN_SECRET', is_active=True)
    active = Medication(user_id=user.id, name='ACTIVE_NOT_INTAKE', is_active=True)
    db.add_all([own, foreign, active]); db.flush()
    rows = [
        (user.id, own.id, date(2026,10,4), 'taken'),
        (user.id, own.id, date(2026,10,9), 'delayed'),
        (user.id, own.id, date(2026,10,10), 'skipped'),
        (user.id, own.id, date(2026,10,3), 'taken'),
        (user.id, own.id, date(2026,10,11), 'taken'),
        (other.id, foreign.id, date(2026,10,10), 'taken'),
        (user.id, foreign.id, date(2026,10,10), 'taken'),
        (other.id, own.id, date(2026,10,10), 'taken'),
    ]
    db.add_all([MedicationLog(user_id=u, medication_id=m, taken_date=d, taken_time=f'{i:02d}:00', status=s)
                for i,(u,m,d,s) in enumerate(rows)]); db.commit()
    turn = snapshot(REQUEST)
    turn = replace(turn, envelope=replace(turn.envelope, user_id=user.id), context=replace(turn.context, user_id=user.id))
    executor = AgentExecutor(db)
    executor._agent_kernel_snapshot = turn
    executor._current_user_id = user.id
    executor._current_turn_user_message = REQUEST
    args = resolve_owned_read_scope(turn).query('medication')
    raw = await executor._exec_health_query('', {}, args)
    payload = json.loads(raw)
    assert payload['source_scope'] == 'owned_medication_intake_logs'
    assert payload['active_medications'] == []
    assert [r['status'] for r in payload['records']] == ['taken','delayed','skipped']
    assert {r['record_date'] for r in payload['records']} == {'2026-10-04','2026-10-09','2026-10-10'}
    assert 'FOREIGN_SECRET' not in raw and 'ACTIVE_NOT_INTAKE' not in raw
    assert all(r['medication_name'] == own.name for r in payload['records'])
    assert db.query(MedicationLog).count() == len(rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper', ['owner','date','extra'])
async def test_history_adapter_rejects_tampering_before_db(tamper):
    turn = snapshot(REQUEST)
    executor = AgentExecutor(None)
    executor._agent_kernel_snapshot = turn
    executor._current_user_id = turn.context.user_id
    executor._current_turn_user_message = REQUEST
    args = resolve_owned_read_scope(turn).query('medication')
    if tamper == 'owner': executor._current_user_id = 42
    if tamper == 'date': args['start_date'] = '2020-01-01'
    if tamper == 'extra': args['status'] = 'taken'
    assert (await executor._exec_health_query('', {}, args)).startswith('Error:')


@pytest.mark.asyncio
@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('partial', [False, True])
@pytest.mark.parametrize('unsafe', [
    '疼痛确定由抗生素引起，可以停药，已排除严重疾病。UNVERIFIED_CAUSE',
    '考虑只是药物刺激，病情不严重，无需就医。UNVERIFIED_CAUSE',
    'UNVERIFIED_CAUSE',
])
async def test_real_gateway_stream_and_saved_response_do_not_invent_cause(
    db, four_domain_user, clock, monkeypatch, panel, partial, unsafe,
):
    import tests.test_agent_composed_synthesis_projection as module
    monkeypatch.setattr(module, 'QUERIES', [{'dimension': d, 'days':7} for d in ('diet','supplements','medication')])
    monkeypatch.setattr(module, 'BAD', [])
    from app.config import settings
    monkeypatch.setattr(settings, 'health_evidence_runtime_enabled', True)
    med = Medication(user_id=four_domain_user.id,name='Synthetic record name UNTRUSTED_DIRECTIVE',is_active=False)
    db.add(med); db.flush()
    db.add_all([MedicationLog(user_id=four_domain_user.id,medication_id=med.id,
        taken_date=clock[0].date(),taken_time=f'{i+8:02d}:00',status=status)
        for i,status in enumerate(('taken','skipped','delayed'))])
    db.commit()
    executor, calls, dispatched, done, saved = await run_projection(
        db, four_domain_user, monkeypatch, query=REQUEST, panel=panel, partial=partial, answer=unsafe)
    assert unsafe not in saved.content and 'UNVERIFIED_CAUSE' not in saved.content
    assert not done.get('write_receipts')
    assert dispatched
    assert 'UNTRUSTED_DIRECTIVE' not in saved.content
    if not partial:
        assert done['turn_outcome']['status'] == 'complete', (done['turn_outcome'], saved.content, executor._composed_read_completion().trusted_fact_summary)
        evidence = executor._composed_read_completion().verified_evidence
        assert {q['query']['dimension'] for q in evidence['queries']} == {'diet','supplements','medication'}
        med = next(q for q in evidence['queries'] if q['query']['dimension'] == 'medication')
        assert med['source_scope'] == 'owned_medication_intake_logs'
        assert med['record_count'] == 3
        assert '已服用1条、跳过1条、延迟1条' in saved.content
        assert '不能确定病因' in saved.content
        assert '范围限制尚不能完整解析' not in saved.content
        assert '在用列表0项' not in saved.content
    else:
        assert done['turn_outcome']['status'] != 'complete'


def test_history_limit_and_empty_are_distinct(db, auth_user_and_headers):
    from app.services.medication_review_read import read_medication_history
    from app.services.agent_query_window import parse_query_window
    user, _ = auth_user_and_headers
    window = parse_query_window(resolve_owned_read_scope(snapshot(REQUEST)).query('medication'))
    assert read_medication_history(db,user.id,window)['availability'] == 'no_data'
    med = Medication(user_id=user.id,name='Synthetic bounded')
    db.add(med); db.flush()
    db.add_all([MedicationLog(user_id=user.id,medication_id=med.id,taken_date=date(2026,10,4),taken_time=f'{i//60:02d}:{i%60:02d}',status='taken') for i in range(501)])
    db.commit()
    with pytest.raises(ValueError, match='limit_exceeded'):
        read_medication_history(db,user.id,window)
