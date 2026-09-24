"""Synthetic reproductions of spoken oxygen queries; no production data."""
from dataclasses import replace
from datetime import date, datetime, time
import json

import pytest

from tests.test_sleep_oxygen_read_scope import snapshot, decide
from app.services.agent_kernel.read_task_scope import resolve_sync_status_query, has_owned_sync_instruction
from tests.test_agent_read_repair_round_budget import (
    four_domain_user as four_domain_user, clock as clock,
    owned_data as owned_data, _isolate_twin_cache as _isolate_twin_cache,
)

DIAGNOSTIC = ('我系统里有血氧数据，是不是没有同步，或者有接口有问题，数据没有传上来。'
              '之前我设置了佳明的全天的血氧的监控。')


@pytest.mark.parametrize('text,day', [
    ('分析昨晚的血氧数据。', '2031-04-04'),
    ('分析昨夜的血氧数据', '2031-04-04'),
    ('查询前晚血氧', '2031-04-03'),
])
def test_night_oxygen_is_explicitly_bound_to_wake_date_and_night_period(text, day):
    result = decide({'dimension': 'spo2'}, text)
    assert result.action == 'allow', result.reason
    assert result.normalized_args == {'dimension': 'spo2', 'start_date': day,
        'end_date': day, 'timezone': 'Asia/Shanghai', 'period': 'sleep_night'}


@pytest.mark.parametrize('suffix', ['，只看凌晨', '，只看检查之后', '，不要读取', '，删除记录'])
def test_night_oxygen_does_not_erase_restrictions(suffix):
    assert decide({'dimension': 'spo2'}, '分析昨晚的血氧数据'+suffix).action == 'block'


def test_sync_diagnostic_authorizes_status_only_not_new_sync_or_health_history():
    query = resolve_sync_status_query(snapshot(DIAGNOSTIC))
    assert query == {'dimension': 'garmin', 'start_date': '2031-04-04',
                     'end_date': '2031-04-04', 'timezone': 'Asia/Shanghai'}
    assert decide({'dimension': 'garmin'}, DIAGNOSTIC).action == 'allow'
    assert not has_owned_sync_instruction(DIAGNOSTIC)
    # A proposed oxygen read is routed to the status question, never an
    # unrequested week of health history or the latest old oxygen night.
    result = decide({'dimension': 'spo2'}, DIAGNOSTIC)
    assert result.action == 'allow'
    assert result.normalized_args == query
    assert decide({'dimension': 'sleep'}, DIAGNOSTIC).action == 'block'
    assert decide({}, DIAGNOSTIC, 'garmin_sync').action == 'block'


@pytest.mark.parametrize('text', [
    DIAGNOSTIC.replace('我系统', '朋友系统'),
    DIAGNOSTIC.replace('佳明', '张三的佳明'),
    DIAGNOSTIC+'只查询去年。', DIAGNOSTIC+'不要查询。',
    '分析这个例句：“'+DIAGNOSTIC+'”',
])
def test_sync_diagnostic_cannot_ignore_unknown_owner_date_or_cancel(text):
    assert resolve_sync_status_query(snapshot(text)) is None
    assert decide({'dimension': 'garmin'}, text).action == 'block'


def test_sync_diagnostic_requires_matching_authenticated_owner():
    turn = snapshot(DIAGNOSTIC)
    assert resolve_sync_status_query(replace(turn, context=replace(turn.context, user_id=42))) is None


@pytest.mark.parametrize('extra', [{'user_id':42}, {'days':30}, {'timezone':'UTC'},
                                  {'job_id':'untrusted'}, {'period':'all_day'}])
def test_sync_diagnostic_does_not_accept_model_scope_or_job(extra):
    assert decide({'dimension':'spo2', **extra}, DIAGNOSTIC).action == 'block'


def test_night_period_cannot_be_dropped_or_injected_into_day_query():
    assert decide({'dimension':'spo2', 'period':'all_day'}, '分析昨晚血氧').action == 'block'
    assert decide({'dimension':'spo2', 'period':'sleep_night'}, '查询昨天血氧').action == 'block'
    assert decide({'dimension':'diet', 'period':'sleep_night'}, '查询今天饮食').action == 'block'


def test_night_followup_preserves_period_and_owner():
    from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
    from app.services.agent_kernel.types import ActionableReference
    from app.services.agent_read_task_continuation import read_task_metadata, resolve_read_task_continuation
    turn = snapshot('分析昨晚的血氧数据')
    scope = resolve_owned_read_scope(turn)
    raw = read_task_metadata(turn, scope, sync_status=False)
    assert raw is not None
    followup = snapshot('继续分析')
    followup = replace(followup, actionable_references=(ActionableReference(
        kind='owned_read_task', source_message_id='21', data=raw),))
    resumed = resolve_read_task_continuation(followup)
    assert resumed is not None
    assert resumed['queries'][0]['period'] == 'sleep_night'
    assert resolve_read_task_continuation(replace(followup, context=replace(followup.context, user_id=42))) is None


def test_night_scope_requires_consistent_owner():
    from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
    turn = snapshot('分析昨晚的血氧数据')
    assert resolve_owned_read_scope(replace(turn, context=replace(turn.context, user_id=42))) is None


@pytest.mark.parametrize('mode', ['missing', 'conflicting_sources', 'equal_clocks', 'excess_duration',
                                  'timezone', 'no_absolute_interval', 'foreign_zone', 'foreign_owner', 'foreign_source'])
def test_night_without_coherent_sleep_interval_never_falls_back_to_day(db, mode):
    from app.models.user import User
    from app.models.daily_health import GarminData, SpO2Sample, SleepLevelInterval
    from app.services.agent_query_window import parse_query_window, read_calendar_health_query
    user = User(name='Synthetic', username='night-gap', email='night-gap@example.test', hashed_password='fixture')
    db.add(user); db.flush()
    start, end = time(23), time(7)
    if mode == 'equal_clocks':
        start = end
    if mode == 'excess_duration':
        start, end = time(8), time(7)
    db.add(GarminData(user_id=user.id, record_date=date(2031,4,4), data_source='ringconn',
        sleep_start_time=None if mode == 'missing' else start,
        sleep_end_time=None if mode == 'conflicting_sources' else end, spo2_avg=97))
    if mode == 'conflicting_sources':
        db.add(GarminData(user_id=user.id, record_date=date(2031,4,4), data_source='garmin', sleep_end_time=end))
    db.add(SpO2Sample(user_id=user.id, record_date=date(2031,4,4), sample_time=time(1),
        epoch_ms=int(datetime.fromisoformat('2031-04-04T01:00:00+08:00').timestamp()*1000), source='ringconn', spo2_value=98))
    if mode in {'foreign_zone', 'foreign_owner', 'foreign_source'}:
        other = User(name='Synthetic', username='night-gap-other', email='night-gap-other@example.test', hashed_password='fixture')
        db.add(other); db.flush()
        offset = '+00:00' if mode == 'foreign_zone' else '+08:00'
        db.add(SleepLevelInterval(user_id=other.id if mode == 'foreign_owner' else user.id,
            record_date=date(2031,4,4), source='apple-watch' if mode == 'foreign_source' else 'ringconn', activity_level='light',
            start_epoch_ms=int(datetime.fromisoformat('2031-04-03T23:00:00'+offset).timestamp()*1000),
            end_epoch_ms=int(datetime.fromisoformat('2031-04-04T07:00:00'+offset).timestamp()*1000)))
    db.flush()
    window = parse_query_window({'start_date':'2031-04-04', 'end_date':'2031-04-04',
        'timezone': 'UTC' if mode == 'timezone' else 'Asia/Shanghai', 'period':'sleep_night'})
    result = read_calendar_health_query(db, user.id, 'spo2', window)
    assert result['records'] == []
    assert 'sleep_interval_unavailable' in result['limitations']


@pytest.mark.asyncio
@pytest.mark.parametrize('has_sleep', [True, False])
async def test_night_reader_filters_real_epochs_not_daily_summary_or_latest_night(db, has_sleep, monkeypatch):
    from app.models.user import User
    from app.models.daily_health import GarminData, SpO2Sample, SleepLevelInterval
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from app.services.agent_kernel.types import ToolExecutionRequest
    owner = User(name='Synthetic', username='oxygen-night-owner', email='oxygen-night@example.test', hashed_password='fixture')
    other = User(name='Synthetic', username='oxygen-night-other', email='oxygen-other@example.test', hashed_password='fixture')
    db.add_all([owner, other]); db.flush()
    if has_sleep:
        db.add(GarminData(user_id=owner.id, record_date=date(2031,4,4), data_source='ringconn',
            sleep_start_time=time(23), sleep_end_time=time(7), total_sleep_duration=480,
            spo2_avg=50, spo2_min=40))
        db.add(SleepLevelInterval(user_id=owner.id, record_date=date(2031,4,4), source='ringconn', activity_level='light',
            start_epoch_ms=int(datetime.fromisoformat('2031-04-03T23:00:00+08:00').timestamp()*1000),
            end_epoch_ms=int(datetime.fromisoformat('2031-04-04T07:00:00+08:00').timestamp()*1000)))
    for uid, moment, source, value in [
        (owner.id, '2031-04-03T23:30:00+08:00', 'apple-watch', 96),
        (owner.id, '2031-04-04T06:30:00+08:00', 'apple-watch', 98),
        (owner.id, '2031-04-04T14:00:00+08:00', 'apple-watch', 51),
        (owner.id, '2031-04-03T12:00:00+08:00', 'apple-watch', 52),
        (owner.id, '2031-04-04T06:30:00+08:00', 'garmin', 53),
        (other.id, '2031-04-04T06:30:00+08:00', 'apple-watch', 54),
    ]:
        dt = datetime.fromisoformat(moment)
        db.add(SpO2Sample(user_id=uid, record_date=dt.date(), sample_time=dt.time(),
                         source=source, spo2_value=value, epoch_ms=int(dt.timestamp()*1000)))
    db.add(SpO2Sample(user_id=owner.id, record_date=date(2031,4,4), sample_time=time(5),
                     source='apple-watch', spo2_value=55))  # no absolute timestamp
    db.flush()
    turn = snapshot('分析昨晚的血氧数据。', owner=owner.id)
    policy = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension':'spo2'}))
    assert policy.action == 'allow', policy.reason
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    monkeypatch.setattr(executor, '_ensure_agent_kernel_turn', lambda **_kw: turn)
    executor._current_turn_user_message = turn.envelope.text
    raw = await executor._exec_health_query('http://unused', {}, policy.normalized_args)
    assert not raw.startswith('Error:'), raw
    result = json.loads(raw)
    assert result['window']['period'] == 'sleep_night'
    assert result['date_attribution'] == 'wake_date'
    if has_sleep:
        assert result['records'] == [{'record_date':'2031-04-04',
            'daily_metrics': {'spo2_avg':None, 'spo2_min':None, 'spo2_max':None},
            'daily_sources': {}, 'sample_summaries': [{'source':'apple-watch', 'data_points':2,
                'min_spo2':96, 'max_spo2':98, 'avg_spo2':97.0}]}]
    else:
        assert result['records'] == []
        assert 'sleep_interval_unavailable' in result['limitations']
    assert result['sync_status'] == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('query', ['分析昨晚的血氧数据。', DIAGNOSTIC])
async def test_screenshot_requests_complete_stream_and_persistence(db, four_domain_user, clock, monkeypatch, panel, query):
    import tests.test_agent_composed_synthesis_projection as projection
    monkeypatch.setattr(projection, 'QUERIES', [{'dimension':'spo2'}])
    monkeypatch.setattr(projection, 'BAD', [])
    unsafe = '接口已经损坏，我已重置设备并同步了整夜血氧，已排除睡眠呼吸暂停。'
    _, _, dispatched, done, saved = await projection.run_projection(
        db, four_domain_user, monkeypatch, query=query, layout='individual', panel=panel, answer=unsafe)
    assert dispatched
    assert not done['write_receipts']
    assert done['turn_outcome']['status'] == 'complete'
    assert unsafe not in saved.content
    assert '只能查询当前登录用户本人的记录' not in saved.content
    if query == DIAGNOSTIC:
        assert dispatched[0].arguments['dimension'] == 'garmin'
        assert '当前血氧分析规则不采用佳明来源' in saved.content
        assert '没有发起新的同步' in saved.content
    else:
        assert dispatched[0].arguments['period'] == 'sleep_night'
        assert '缺少可定位的睡眠时段' in saved.content
