"""Explicit sync and last-night sleep review share one owner/date-bound plan."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from tests.test_agent_read_plan_binding import snapshot, decide
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope, has_owned_sync_instruction

PROMPT = '昨晚睡得怎么样 更新garmin数据'


@pytest.mark.parametrize('text', [PROMPT, '更新Garmin数据，昨晚睡得怎么样？',
    '昨天晚上我睡得怎么样？请同步一下我的佳明数据。',
    '请帮我查看昨晚的睡眠情况，然后刷新佳明数据',
    '同步佳明数据 昨晚睡眠如何'])
def test_explicit_compound_request_binds_only_wake_date_and_empty_sync(text):
    assert has_owned_sync_instruction(text)
    scope = resolve_owned_read_scope(snapshot(text))
    expected = {'dimension': 'sleep', 'start_date': '2026-07-17',
                'end_date': '2026-07-17', 'timezone': 'Asia/Shanghai'}
    assert scope is not None and scope.queries == (expected,)
    decision = decide(text, 'health_query', {'dimension': 'sleep'})
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == expected
    assert decide(text, 'health_record', {'record_type': 'garmin_sync', 'data': {}}).action == 'allow'


@pytest.mark.parametrize('text', ['“' + PROMPT + '”', '如果' + PROMPT, '不要' + PROMPT,
    '妈妈' + PROMPT, PROMPT.replace('garmin', '妈妈的garmin'),
    PROMPT + '，先别更新', PROMPT + '，删除睡眠',
    '分析这句文案：' + PROMPT, '昨晚睡得怎么样 Garmin数据更新了吗',
    '昨晚睡得怎么样 明天更新garmin数据', '昨晚和前晚睡得怎么样 更新garmin数据'])
def test_unknown_or_non_imperative_clauses_cannot_grant_sync(text):
    assert not has_owned_sync_instruction(text)
    assert decide(text, 'health_record', {'record_type': 'garmin_sync', 'data': {}}).action == 'block'


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep', 'start_date': '2026-07-16'}),
    ('health_query', {'dimension': 'sleep', 'days': 30}),
    ('health_query', {'dimension': 'sleep', 'user_id': 42}),
    ('health_query', {'dimension': 'diet'}),
    ('health_record', {'record_type': 'garmin_sync', 'data': {'days': 30}}),
    ('health_record', {'record_type': 'sleep', 'data': {'duration': 480}}),
])
def test_model_cannot_expand_compound_authority(tool, args):
    assert decide(PROMPT, tool, args).action == 'block'


def test_owner_and_timezone_are_bound_by_server():
    snap = snapshot(PROMPT)
    snap = replace(snap, context=replace(snap.context,
        current_time=datetime(2026, 10, 26, 16, 5, tzinfo=timezone.utc)))
    assert resolve_owned_read_scope(snap).query('sleep')['start_date'] == '2026-10-27'
    assert resolve_owned_read_scope(replace(snap, envelope=replace(snap.envelope, user_id=42))) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('job_state', ['PENDING', 'SUCCESS', 'FAILURE', 'INVALID_STATE', 'missing_credentials', 'enqueue_error'])
@pytest.mark.parametrize('available', [True, False])
async def test_real_pi_sync_once_and_exact_sleep_facts(db, auth_user_and_headers, monkeypatch, job_state, available):
    from app.services.agent_executor import AgentExecutor
    from app.services import agent_executor as ae, agent_garmin_sync_status as status
    from app.services.agent_kernel.types import ExecutionContext
    from app.models.daily_health import GarminData
    from app.models.user import GarminCredential, User
    from app.models.agent_conversation import AgentMessage
    from app.tasks.garmin_sync import sync_user_garmin_data
    user, _ = auth_user_and_headers
    fixed = datetime(2026, 10, 27, 1, tzinfo=timezone.utc)
    clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, 'now', classmethod(
        lambda cls, **kw: clock(cls, **{**kw, 'now_utc': fixed})))
    if job_state != 'missing_credentials':
        db.add(GarminCredential(user_id=user.id, garmin_email='synthetic@example.invalid',
            encrypted_password='unused', sync_enabled=True, credentials_valid=True))
    db.add(GarminData(user_id=user.id, record_date=fixed.date()-timedelta(days=1),
        data_source='garmin', total_sleep_duration=111, sleep_score=11))
    if available:
        db.add(GarminData(user_id=user.id, record_date=fixed.date(),
            data_source='garmin', total_sleep_duration=450, sleep_score=82))
    other = User(username='synthetic-sleep-other', name='Synthetic', hashed_password='unused')
    db.add(other)
    db.flush()
    db.add(GarminData(user_id=other.id, record_date=fixed.date(),
        data_source='garmin', total_sleep_duration=123, sleep_score=13))
    db.commit()
    job = str(uuid4())
    enqueue = Mock(return_value=Mock(id=job), side_effect=RuntimeError('synthetic') if job_state == 'enqueue_error' else None)
    monkeypatch.setattr(sync_user_garmin_data, 'delay', enqueue)
    monkeypatch.setattr(status, '_read_task_meta', lambda _: {'task_id': job, 'status': job_state,
        'result': {'status': 'success', 'success_count': 1, 'error_count': 0, 'activities_count': 0}})
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', True)
    ex = AgentExecutor(db)
    calls = []
    dispatch = ex._dispatch_tool_request
    async def capture(request, token):
        calls.append((request.tool_name, dict(request.arguments)))
        return await dispatch(request, token)
    monkeypatch.setattr(ex, '_dispatch_tool_request', capture)
    async def model(*args, **kwargs):
        pytest.fail('closed sleep review must use verified records, not model guesses')
        yield
    monkeypatch.setattr(ex, '_call_llm_stream', model)
    events = [e async for e in ex.run_stream(user_id=user.id, channel='typed', message=PROMPT)]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert calls == [('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        ('health_query', {'dimension': 'sleep', 'start_date': '2026-10-27',
                          'end_date': '2026-10-27', 'timezone': 'Asia/Shanghai'})]
    assert enqueue.call_count == (0 if job_state == 'missing_credentials' else 1)
    if enqueue.call_count:
        assert enqueue.call_args.args == (user.id,)
    assert not ex._agent_kernel_capability_block_reasons
    assert ex._turn_sync_status_result['job_success_verified'] is (job_state == 'SUCCESS')
    saved = db.get(AgentMessage, done['message_id']).content
    public = ''.join(e.get('data', {}).get('content', '') for e in events if e.get('event') == 'token')
    for body in (saved, public):
        assert '请明确' not in body
        assert '2026-10-27' in body
        assert '1.85小时' not in body
        assert '2.05小时' not in body
        if available:
            assert '7.5小时' in body and '82' in body
        else:
            assert '不能据此判断睡眠情况' in body
        if job_state == 'SUCCESS':
            assert '同步任务已返回成功' in body
        elif job_state in {'enqueue_error', 'missing_credentials'}:
            assert '本轮同步没有取得已提交确认' in body
        elif job_state == 'FAILURE':
            assert '同步任务失败' in body
        else:
            assert '同步任务已提交，尚未核实完成' in body
    assert db.query(GarminData).filter_by(user_id=user.id).count() == (2 if available else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['read_only', 'owned_no_model_surface'])
async def test_sleep_review_preserves_turn_tool_boundaries(db, auth_user_and_headers, monkeypatch, boundary):
    from tests import test_agent_garmin_preplanned_review as running
    monkeypatch.setattr(running, 'PROMPT', PROMPT)
    await running.test_pi_cannot_dispatch_sync_outside_turn_boundary(
        db, auth_user_and_headers, monkeypatch, boundary)
