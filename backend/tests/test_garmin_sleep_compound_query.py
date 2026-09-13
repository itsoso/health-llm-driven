"""Synthetic compound sleep/status reads must not become synchronization writes."""
from unittest.mock import AsyncMock
import json
import pytest

from tests.test_agent_read_plan_binding import snapshot, decide
from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan

QUESTION = '昨天晚上我睡得怎么样？佳明的数据同步完了吗？'


@pytest.mark.parametrize('payload', [None, [], {}, {'bound': 'true'},
    {'bound': True}, {'bound': True, 'sync_enabled': True, 'credentials_valid': True,
     'requires_mfa': False, 'error_count': -1},
    {'bound': True, 'sync_enabled': True, 'credentials_valid': True,
     'requires_mfa': False, 'error_count': 0, 'last_sync_at': 'invalid'}])
def test_malformed_status_never_becomes_verified(payload):
    from app.services.agent_garmin_status import project_garmin_status, garmin_status_text
    from app.services.agent_daily_read_execution import sync_status_goal
    projected = project_garmin_status(payload)
    assert projected == {'lookup_status': 'failed', 'current_task_status': 'unknown'}
    assert sync_status_goal({'sync_check': projected})['status'] == 'failed'
    assert '无法确认' in garmin_status_text(projected)


def test_status_projection_excludes_secrets_and_untrusted_completion_claims():
    from app.services.agent_garmin_status import project_garmin_status, garmin_status_text
    raw = {'bound': True, 'sync_enabled': True, 'credentials_valid': True,
           'requires_mfa': False, 'error_count': 0, 'last_sync_at': None,
           'garmin_email': 'fixture@example.test', 'encrypted_password': 'synthetic-secret',
           'last_error': 'synthetic-secret', 'current_task_status': 'completed'}
    projected = project_garmin_status(raw)
    assert projected['current_task_status'] == 'unknown'
    assert not {'garmin_email', 'encrypted_password', 'last_error'} & projected.keys()
    assert 'synthetic-secret' not in garmin_status_text(projected)
    assert '无法确认' in garmin_status_text(projected)


@pytest.mark.parametrize('question', [QUESTION, '昨晚睡眠如何，Garmin同步完成了吗？'])
def test_sleep_and_sync_status_bind_wake_date_without_sync_write(question):
    snap = snapshot(question)
    plan = resolve_daily_read_plan(question, snap.context.current_time)
    assert plan is not None
    assert plan.start_date == plan.end_date == '2026-07-17'
    assert plan.dimensions == ('sleep',)
    assert plan.sync_status_requested
    decision = decide(question, 'health_query', {'dimension': 'sleep', 'days': 30})
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args['start_date'] == '2026-07-17'
    assert decide(question, 'health_record', {'record_type': 'garmin_sync', 'data': {}}).action == 'block'


@pytest.mark.parametrize('question', [
    '昨晚妈妈睡眠如何？佳明的数据同步完了吗？',
    '昨晚睡眠如何？妈妈的佳明数据同步完了吗？',
    '不要查询昨晚睡眠如何？佳明的数据同步完了吗？',
    '分析这句文案：昨晚睡眠如何？佳明的数据同步完了吗？',
    '昨晚睡眠如何？同步佳明数据。',
])
def test_compound_status_suffix_does_not_expand_authority(question):
    snap = snapshot(question)
    assert resolve_daily_read_plan(question, snap.context.current_time) is None


@pytest.mark.asyncio
async def test_actual_calendar_adapter_reads_owned_status_without_triggering_sync(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)
    ex._current_user_id = 41
    ex._current_turn_user_message = QUESTION
    ex._agent_kernel_snapshot = snapshot(QUESTION)
    ex._api_get_json = AsyncMock(return_value=({'bound': True, 'sync_enabled': True,
        'credentials_valid': True, 'requires_mfa': False, 'error_count': 0,
        'last_sync_at': '2026-07-17T00:00:00+00:00', 'last_error': None}, None))
    ex._trigger_garmin_sync = AsyncMock()
    decision = decide(QUESTION, 'health_query', {'dimension': 'sleep'})
    assert decision.action == 'allow'
    result = json.loads(await ex._exec_health_query('http://unused', {'Authorization': 'synthetic'}, decision.normalized_args))
    assert result['sync_check']['lookup_status'] == 'available'
    assert result['sync_check']['current_task_status'] == 'unknown'
    ex._api_get_json.assert_awaited_once_with('http://unused/data-collection/garmin/me/credential-status', {'Authorization': 'synthetic'})
    ex._trigger_garmin_sync.assert_not_awaited()


def test_compound_reply_uses_facts_and_never_claims_current_sync_complete():
    from app.services.agent_daily_read_execution import sleep_sync_reply, sync_status_goal
    plan = resolve_daily_read_plan(QUESTION, snapshot(QUESTION).context.current_time)
    payload = {'dimension': 'sleep', 'records': [{'record_date': '2026-07-17',
        'total_sleep_duration': 450, 'sleep_score': 82}], 'sync_check': {
        'lookup_status': 'available', 'current_task_status': 'unknown', 'bound': True,
        'sync_enabled': True, 'credentials_valid': True, 'requires_mfa': False,
        'error_count': 0, 'last_sync_at': '2026-07-17T00:00:00+00:00'}}
    goals = {'sleep': {'status': 'verified', 'evidence_kind': 'read_result'}}
    text = sleep_sync_reply(plan, {'sleep': payload}, goals)
    assert '7.5小时' in text and '82' in text
    assert '最近一次成功同步' in text
    assert '无法确认刚才的任务是否完成' in text
    assert sync_status_goal(payload)['kind'] == 'query'
    assert sync_status_goal({'sync_check': {'lookup_status': 'failed'}})['status'] == 'failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('lookup_failed', [False, True])
async def test_real_pi_public_and_history_keep_sleep_facts_and_sync_uncertainty(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, lookup_failed,
):
    from tests.test_query_reliability_outcomes import _run_scripted
    user, _ = auth_user_and_headers
    def dispatch(request):
        assert request.tool_name == 'health_query'
        assert request.arguments['dimension'] == 'sleep'
        return {'dimension': 'sleep', 'window': {k: request.arguments[k] for k in ('start_date', 'end_date', 'timezone')},
            'records': [{'record_date': request.arguments['start_date'], 'total_sleep_duration': 450, 'sleep_score': 82}],
            'availability': 'available', 'sync_check': {'lookup_status': 'failed'} if lookup_failed else {
                'lookup_status': 'available', 'current_task_status': 'unknown', 'bound': False}}
    executor, done, persisted, public, calls = await _run_scripted(
        db, user, monkeypatch, query=QUESTION, first_tool='health_query', first_args={'dimension': 'sleep', 'days': 30},
        dispatch=dispatch, reply='佳明已经全部同步完成，睡了九小时。', turn_id=f'synthetic-sleep-sync-{lookup_failed}',
    )
    assert calls
    assert not executor._turn_sync_queued
    for text in (persisted.content, public):
        assert '7.5小时' in text
        assert '已经全部同步完成' not in text
        assert '九小时' not in text
    goal = next(g for g in done['turn_outcome']['goals'] if g['goal_id'] == 'garmin_sync_status')
    assert goal['status'] == ('failed' if lookup_failed else 'verified')
    if lookup_failed:
        assert done['turn_outcome']['status'] == 'partial'


@pytest.mark.asyncio
async def test_postgres_compound_read_keeps_sleep_and_credential_owner_isolated(db, client, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires isolated PostgreSQL')
    from dataclasses import replace
    from datetime import date, datetime, timezone
    from app.models.user import User, GarminCredential
    from app.models.daily_health import GarminData
    from app.services.agent_executor import AgentExecutor
    user, headers = auth_user_and_headers
    other = User(username='synthetic-garmin-other', name='Synthetic', hashed_password='fixture')
    db.add(other)
    db.flush()
    for owner, duration, hour in ((user.id, 450, 1), (other.id, 123, 2)):
        db.add(GarminData(user_id=owner, record_date=date(2026, 7, 17), data_source='garmin', total_sleep_duration=duration))
        db.add(GarminCredential(user_id=owner, garmin_email='synthetic@example.test', encrypted_password='fixture',
            sync_enabled=True, credentials_valid=True, requires_mfa=False,
            last_sync_at=datetime(2026, 7, 17, hour, tzinfo=timezone.utc)))
    db.commit()
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    ex._current_turn_user_message = QUESTION
    snap = snapshot(QUESTION)
    ex._agent_kernel_snapshot = replace(snap, envelope=replace(snap.envelope, user_id=user.id), context=replace(snap.context, user_id=user.id))
    async def authenticated_get(url, request_headers):
        response = client.get('/api/v1/data-collection/garmin/me/credential-status', headers=request_headers)
        assert response.status_code == 200
        return response.json(), None
    ex._api_get_json = AsyncMock(side_effect=authenticated_get)
    args = decide(QUESTION, 'health_query', {'dimension': 'sleep'}).normalized_args
    raw = await ex._exec_health_query('http://unused', headers, args)
    assert not raw.startswith('Error:'), raw
    result = json.loads(raw)
    assert result['records'][0]['total_sleep_duration'] == 450
    assert len(result['records']) == 1
    assert datetime.fromisoformat(result['sync_check']['last_sync_at']) == datetime(2026, 7, 17, 1, tzinfo=timezone.utc)
    assert 'garmin_email' not in result['sync_check']
    assert db.query(GarminData).count() == 2
    assert client.get('/api/v1/data-collection/garmin/me/credential-status').status_code == 401
