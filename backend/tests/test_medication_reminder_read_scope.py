"""Notification draft -> owned slot read -> persisted answer, without dose writes."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
import json

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest, ToolExecutionResult
from tests.test_recent_workout_read_regression import snapshot

PROMPT = '请帮我查看 2026-10-20 09:00 （北京时间） 的用药提醒，先查询核实药品、计划时间和记录状态，不要记录服药。'
QUERY = {'dimension': 'medication', 'start_date': '2026-10-20',
         'end_date': '2026-10-20', 'timezone': 'Asia/Shanghai'}


def test_reminder_scope_is_not_persisted_as_a_broader_day_continuation():
    from app.services.agent_read_task_continuation import read_task_metadata
    turn = snapshot(PROMPT)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert read_task_metadata(turn, scope, sync_status=False) is None


@pytest.mark.parametrize('change', ['source', 'time', 'row_time', 'plan_time'])
def test_completion_rejects_whole_day_or_other_slot_evidence(change):
    from app.services.agent_composed_read_completion import evaluate_composed_read_completion
    turn = snapshot(PROMPT)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    decision = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'medication'}))
    payload = {'dimension': 'medication', 'window': {k:v for k,v in QUERY.items() if k != 'dimension'},
               'source_scope': 'owned_medication_reminder_slot', 'reminder_time': '09:00',
               'availability': 'available', 'limitations': [],
               'active_medications': [{'id': 1, 'name': 'Synthetic', 'reminder_times': ['09:00']}],
               'records': [{'record_date': '2026-10-20', 'medication_id': 1, 'taken_time': '09:00', 'status': 'taken'}]}
    def verify(value):
        return evaluate_composed_read_completion(scope, [ToolExecutionResult('health_query', value, decision=decision)])
    assert verify(payload).complete
    payload = deepcopy(payload)
    if change == 'source': payload['source_scope'] = 'owned_medication_intake_logs'
    if change == 'time': payload['reminder_time'] = '08:00'
    if change == 'row_time': payload['records'][0]['taken_time'] = '08:00'
    if change == 'plan_time': payload['active_medications'][0]['reminder_times'] = ['09:00', '20:00']
    assert not verify(payload).complete


@pytest.mark.parametrize('tool', ['health_query', 'health_query_batch'])
def test_exact_mobile_prompt_authorizes_only_owned_day_and_slot(tool):
    turn = snapshot(PROMPT)
    args = {'dimension': 'medication'} if tool == 'health_query' else {'queries': [{'dimension': 'medication'}]}
    decision = decide_tool_capability(turn, ToolExecutionRequest(tool, args))
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == (QUERY if tool == 'health_query' else {'queries': [QUERY]})
    assert resolve_owned_read_scope(turn).medication_reminder_time == '09:00'


@pytest.mark.parametrize('text', [
    PROMPT.replace('帮我查看', '帮我妈妈查看'), '解释“' + PROMPT + '”',
    '如果用户说' + PROMPT, '不要查询。' + PROMPT, PROMPT + '再查妈妈的用药',
    PROMPT + '查询去年全部记录', PROMPT.replace('2026-10-20', '2026-02-30'),
    PROMPT.replace('09:00', '25:00'), PROMPT.replace('09:00', '时间未确认'),
    PROMPT.replace('北京时间', '请核实提醒时区'), PROMPT.replace('北京时间', 'UTC'),
    PROMPT.replace('2026-10-20', '日期未确认'), PROMPT.replace('不要记录服药', '已经服药请记录'),
    '请帮我查看用药提醒。通知信息不完整，请先核实，不要记录服药。',
])
def test_incomplete_modified_or_foreign_reminder_cannot_fall_back(text):
    for tool, args in [('health_query', {'dimension': 'medication'}),
                       ('health_query_batch', {'queries': [{'dimension': 'medication'}]}),
                       ('health_manage', {'operation': 'list', 'record_type': 'medication'})]:
        assert decide_tool_capability(snapshot(text), ToolExecutionRequest(tool, args)).action == 'block'


@pytest.mark.parametrize('args', [
    {'dimension': 'medication', 'user_id': 42}, {'dimension': 'medication', 'days': 30},
    {'dimension': 'medication', 'start_date': '2026-10-19'},
    {'dimension': 'medication', 'timezone': 'UTC'}, {'dimension': 'medication', 'time': '08:00'},
    {'dimension': 'medication', 'medication_id': 99}, {'dimension': 'diet'},
])
def test_model_cannot_change_scope(args):
    assert decide_tool_capability(snapshot(PROMPT), ToolExecutionRequest('health_query', args)).action == 'block'


@pytest.mark.parametrize('tool,args', [
    ('health_record', {'record_type': 'medication', 'data': {'name': 'Synthetic', 'status': 'taken'}}),
    ('health_manage', {'operation': 'list', 'record_type': 'medication'}),
    ('health_manage', {'operation': 'delete', 'record_type': 'medication', 'id': 1}),
    ('health_analysis', {'analysis_type': 'comprehensive'}),
])
def test_read_request_never_grants_other_reads_or_writes(tool, args):
    assert decide_tool_capability(snapshot(PROMPT), ToolExecutionRequest(tool, args)).action == 'block'


def test_owner_and_explicit_timezone_must_match_server_context():
    turn = snapshot(PROMPT)
    for changed in [replace(turn.context, user_id=42), replace(turn.context, user_id=True),
                    replace(turn.context, timezone='America/Los_Angeles')]:
        assert decide_tool_capability(replace(turn, context=changed), ToolExecutionRequest('health_query', {'dimension': 'medication'})).action == 'block'
    turn = snapshot(PROMPT.replace('北京时间', 'America/Los_Angeles'))
    turn = replace(turn, context=replace(turn.context, timezone='America/Los_Angeles'))
    assert resolve_owned_read_scope(turn).query('medication')['timezone'] == 'America/Los_Angeles'


def test_empty_schedule_and_absent_log_are_honest_read_results(db, auth_user_and_headers):
    from app.services.medication_review_read import read_medication_reminder_slot
    from app.services.agent_query_window import parse_query_window
    user, _ = auth_user_and_headers
    result = read_medication_reminder_slot(db, user.id, parse_query_window(QUERY), '09:00')
    assert result['availability'] == 'no_data'
    assert result['active_medications'] == result['records'] == []
    assert '无打卡不等于未服用' in ''.join(result['limitations'])


def test_slot_query_refuses_result_overflow_and_malformed_schedule(db, auth_user_and_headers):
    from app.models.medication import Medication
    from app.services.medication_review_read import read_medication_reminder_slot
    from app.services.agent_query_window import parse_query_window
    user, _ = auth_user_and_headers
    med = Medication(user_id=user.id, name='Synthetic invalid', is_active=True, reminder_times='09:00')
    db.add(med); db.commit()
    with pytest.raises(ValueError, match='schedule_invalid'):
        read_medication_reminder_slot(db, user.id, parse_query_window(QUERY), '09:00')
    med.reminder_times = ['09:00']
    db.add_all([Medication(user_id=user.id, name=f'Synthetic {i}', is_active=True, reminder_times=['09:00']) for i in range(200)])
    db.commit()
    with pytest.raises(ValueError, match='result_limit_exceeded'):
        read_medication_reminder_slot(db, user.id, parse_query_window(QUERY), '09:00')


def seed(db, user):
    from app.models.medication import Medication, MedicationLog
    from app.models.user import User
    other = User(name='Synthetic other', email='reminder-scope-other@example.test')
    db.add(other); db.flush()
    meds = [Medication(user_id=user.id, name='Synthetic slot', dosage='saved dose', is_active=True, reminder_times=['09:00', '20:00']),
            Medication(user_id=user.id, name='Other slot secret', is_active=True, reminder_times=['08:00']),
            Medication(user_id=other.id, name='Foreign secret', is_active=True, reminder_times=['09:00']),
            Medication(user_id=user.id, name='Expired secret', is_active=True, reminder_times=['09:00'], end_date=date(2026, 10, 19))]
    db.add_all(meds); db.flush()
    logs = [MedicationLog(user_id=uid, medication_id=mid, taken_date=day, taken_time=time, status=status)
            for uid, mid, day, time, status in [
                (user.id, meds[0].id, date(2026,10,20), '09:00', 'skipped'),
                (user.id, meds[0].id, date(2026,10,20), '20:00', 'taken'),
                (user.id, meds[0].id, date(2026,10,19), '09:00', 'taken'),
                (user.id, meds[2].id, date(2026,10,20), '09:00', 'taken'),
                (other.id, meds[1].id, date(2026,10,20), '09:00', 'taken')]]
    db.add_all(logs); db.commit()
    return meds[0].id


@pytest.mark.asyncio
async def test_adapter_returns_only_owned_slot_and_preserves_database(db, auth_user_and_headers):
    from app.models.medication import MedicationLog
    from app.services.agent_executor import AgentExecutor
    user, _ = auth_user_and_headers
    med_id = seed(db, user)
    turn = snapshot(PROMPT)
    turn = replace(turn, envelope=replace(turn.envelope, user_id=user.id), context=replace(turn.context, user_id=user.id))
    executor = AgentExecutor(db)
    executor._agent_kernel_snapshot = turn
    executor._current_user_id = user.id
    executor._current_turn_user_message = PROMPT
    result = json.loads(await executor._exec_health_query('', {}, QUERY))
    assert result['source_scope'] == 'owned_medication_reminder_slot'
    assert result['reminder_time'] == '09:00'
    assert [m['id'] for m in result['active_medications']] == [med_id]
    assert result['active_medications'][0]['reminder_times'] == ['09:00']
    assert len(result['records']) == 1 and result['records'][0]['status'] == 'skipped'
    assert 'secret' not in json.dumps(result)
    assert db.query(MedicationLog).count() == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper', ['owner', 'window', 'extra', 'text'])
async def test_adapter_rechecks_before_database_access(tamper):
    from app.services.agent_executor import AgentExecutor
    turn = snapshot(PROMPT)
    executor = AgentExecutor(None)
    executor._agent_kernel_snapshot = turn
    executor._current_user_id = 42 if tamper == 'owner' else 41
    executor._current_turn_user_message = PROMPT
    args = dict(QUERY)
    if tamper == 'window': args['start_date'] = '2020-01-01'
    if tamper == 'extra': args['user_id'] = 42
    if tamper == 'text': executor._agent_kernel_snapshot = replace(turn, envelope=replace(turn.envelope, text=PROMPT + '再查全部'))
    assert (await executor._exec_health_query('', {}, args)).startswith('Error:')


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['health_query', 'health_query_batch'])
async def test_real_gateway_persists_read_answer_without_medication_write(db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, tool):
    from app.models.agent_conversation import AgentMessage
    from app.models.medication import MedicationLog
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ExecutionContext
    from app.twin.schema import HealthTwin, TwinMeta
    user, _ = auth_user_and_headers
    seed(db, user)
    now = datetime.fromisoformat('2026-10-20T09:50:00+08:00')
    clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, 'now', classmethod(lambda cls, **kw: clock(cls, **{**kw, 'now_utc': now})))
    monkeypatch.setattr('app.twin.builder.build_twin', lambda _db, uid, **kw: HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    executor = AgentExecutor(db)
    calls = 0
    results = []
    dispatch = executor._dispatch_tool_request
    async def provider(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            args = {'dimension': 'medication'} if tool == 'health_query' else {'queries': [{'dimension': 'medication'}]}
            yield {'type': 'tool_calls', 'tool_calls': [{'id': 'reminder-read', 'type': 'function', 'function': {'name': tool, 'arguments': json.dumps(args)}}]}
            yield {'type': 'finish', 'finish_reason': 'tool_calls'}
        else:
            yield {'type': 'content', 'text': '已核对指定时段的保存计划和记录，无打卡不等于未服用。没有记录服药。'}
            yield {'type': 'finish', 'finish_reason': 'stop'}
    async def observe(request, token):
        result = await dispatch(request, token); results.append(result); return result
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    monkeypatch.setattr(executor, '_dispatch_tool_request', observe)
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **k: '只读核对，不更改用药。')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *a, **k: '')
    events = [e async for e in executor.run_stream(user.id, PROMPT, client_turn_id=f'reminder-read-{tool}')]
    done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
    assert done['turn_outcome']['status'] == 'complete', done
    completion = executor._composed_read_completion()
    assert completion.complete
    evidence = completion.verified_evidence['queries'][0]
    assert evidence['reminder_time'] == '09:00' and evidence['record_count'] == 1
    saved = db.get(AgentMessage, done['message_id']).content
    assert '当前请求没有授权' not in saved and 'secret' not in saved
    assert not done.get('write_receipts')
    assert db.query(MedicationLog).count() == 5
