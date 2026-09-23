"""Sleep oxygen requests bind real owned windows, never a latest-night fallback."""
from datetime import date, datetime, time
import json
from unittest.mock import AsyncMock

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot

REQUEST = '分析最近一周的睡眠血氧情况，给出你的建议'


def snapshot(text=REQUEST, owner=41):
    env = AgentEnvelope(user_id=owner, channel='typed', text=text)
    ctx = ExecutionContext(user_id=owner, channel='typed', timezone='Asia/Shanghai',
                           current_time=datetime.fromisoformat('2031-04-03T17:10:00+00:00'))
    return TurnSnapshot(env, ctx, build_intent_frame(env, ctx))


def decide(args, text=REQUEST, tool='health_query'):
    return decide_tool_capability(snapshot(text), ToolExecutionRequest(tool, args))


@pytest.mark.parametrize('text', [REQUEST, '分析我最近一周的睡眠血氧情况，给出你的建议',
                                 '分析最近七天的睡眠血氧情况', '查询我近7天的睡眠血氧并分析'])
@pytest.mark.parametrize('dimension', ['sleep', 'spo2'])
def test_compound_request_binds_every_metric_to_same_frozen_week(text, dimension):
    result = decide({'dimension': dimension, 'days': 7}, text)
    assert result.action == 'allow', result.reason
    assert result.normalized_args == {'dimension': dimension, 'days': 7,
        'start_date': '2031-03-29', 'end_date': '2031-04-04', 'timezone': 'Asia/Shanghai'}


@pytest.mark.parametrize('text', [
    '分析我朋友最近一周的睡眠血氧情况，给出你的建议',
    '分析张三最近一周的睡眠血氧情况，给出你的建议',
    '不要分析最近一周的睡眠血氧情况',
    '假如分析最近一周的睡眠血氧情况',
    '分析最近一周的睡眠血氧情况，只看今早',
    '分析最近一周的睡眠血氧情况，给出你的建议但只看检查之后',
    '分析最近99天的睡眠血氧情况',
    '分析最近一周和昨天的睡眠血氧情况',
    '分析最近一周的睡眠血氧情况，给出张三的建议',
])
@pytest.mark.parametrize('dimension', ['sleep', 'spo2'])
def test_compound_request_cannot_erase_owners_cancellation_or_filters(text, dimension):
    assert decide({'dimension': dimension, 'days': 7}, text).action == 'block'


@pytest.mark.parametrize('extra', [{'days': 30}, {'days': '7'}, {'user_id': 42},
                                 {'start_date': '2030-01-01'}, {'timezone': 'UTC'}])
def test_model_cannot_widen_compound_read(extra):
    assert decide({'dimension': 'spo2', **extra}).action == 'block'


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension':'spo2'}),
    ('health_query_batch', {'queries':[{'dimension':'sleep'},{'dimension':'spo2'}]}),
    ('health_query_batch', {'plan':{'queries':[{'dimension':'sleep'},{'dimension':'spo2'}]}}),
])
def test_sleep_only_restriction_cannot_expand_compound_oxygen(tool,args):
    assert decide(args,'分析最近一周的睡眠血氧情况，只看睡眠',tool).action == 'block'


def test_batch_binds_both_domains_and_does_not_grant_other_tools():
    result = decide({'queries': [{'dimension': 'sleep'}, {'dimension': 'spo2'}]}, tool='health_query_batch')
    assert result.action == 'allow', result.reason
    assert {q['dimension'] for q in result.normalized_args['queries']} == {'sleep', 'spo2'}
    assert all(q['start_date'] == '2031-03-29' for q in result.normalized_args['queries'])
    assert decide({'dimension': 'genetic'}).action == 'block'
    assert decide({'dimension': 'spo2_sleep_correlation'}).action == 'block'
    assert decide({'record_type': 'sleep', 'data': {}}, tool='health_record').action == 'block'


def test_advice_author_is_not_data_owner_but_does_not_expand_sleep_only_scope():
    result = decide({'dimension': 'sleep', 'days': 7}, '分析最近一周的睡眠情况，给出你的建议')
    assert result.action == 'allow', result.reason
    assert decide({'dimension': 'spo2'}, '分析最近一周的睡眠情况，给出你的建议').action == 'block'


@pytest.fixture
def owners(db):
    from app.models.user import User
    users = [User(name=f'Synthetic {n}', username=f'oxygen-synthetic-{n}', email=f'oxygen-{n}@example.test', hashed_password='unused') for n in range(2)]
    db.add_all(users)
    db.flush()
    return users[0].id, users[1].id


@pytest.mark.asyncio
async def test_executor_reads_whole_frozen_window_with_source_and_owner_boundaries(db, owners):
    from app.models.daily_health import GarminData, SpO2Sample
    from app.services.agent_executor import AgentExecutor
    owner, other = owners
    for uid, day, source, value in [(owner, date(2031,3,28), 'ringconn', 70),
        (owner,date(2031,3,29),'ringconn',97), (owner,date(2031,4,4),'ringconn',96),
        (owner,date(2031,4,5),'ringconn',71), (other,date(2031,4,4),'ringconn',72),
        (owner,date(2031,4,4),'garmin',73), (owner,date(2031,4,4),'garmin-app',74)]:
        db.add(SpO2Sample(user_id=uid, record_date=day, sample_time=time(1), source=source, spo2_value=value))
    db.add_all([
        GarminData(user_id=owner,record_date=date(2031,4,4),data_source='ringconn',spo2_min=95,spo2_avg=97),
        GarminData(user_id=owner,record_date=date(2031,4,4),data_source='garmin',spo2_min=65,spo2_avg=80),
        GarminData(user_id=other,record_date=date(2031,4,4),data_source='ringconn',spo2_min=61),
    ])
    db.flush()
    turn = snapshot(owner=owner)
    policy = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'spo2', 'days': 7}))
    assert policy.action == 'allow', policy.reason
    executor = AgentExecutor(db)
    executor._current_user_id = owner
    executor._ensure_agent_kernel_turn = lambda: turn
    executor._api_get = AsyncMock(side_effect=AssertionError('must not fall back to latest-night HTTP'))
    result = json.loads(await executor._exec_health_query('http://unused', {}, policy.normalized_args))
    assert result['window']['start_date'] == '2031-03-29'
    assert result['window']['end_date'] == '2031-04-04'
    assert [r['record_date'] for r in result['records']] == ['2031-03-29', '2031-04-04']
    assert result['records'][1]['daily_metrics']['spo2_min'] == 95
    assert result['records'][1]['daily_sources']['spo2_min'] == 'ringconn'
    assert [r['sample_summaries'][0]['min_spo2'] for r in result['records']] == [97,96]
    assert all(r['sample_summaries'][0]['source'] == 'ringconn' for r in result['records'])
    assert result['availability'] == 'partial'
    assert 'sleep_interval_not_verified' in result['limitations']
    assert 'not_diagnostic_no_apnea_inference' in result['limitations']
    assert result['coverage']['days_with_data'] == 2
    executor._api_get.assert_not_called()
    from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
    from app.services.agent_kernel.types import ToolExecutionResult
    from app.services.agent_composed_read_completion import evaluate_composed_read_completion
    sleep_policy = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension':'sleep'}))
    sleep_result = json.loads(await executor._exec_health_query('http://unused', {}, sleep_policy.normalized_args))
    completion = evaluate_composed_read_completion(resolve_owned_read_scope(turn), [
        ToolExecutionResult('health_query', result, decision=policy),
        ToolExecutionResult('health_query', sleep_result, decision=sleep_policy),
    ])
    assert completion.complete
    oxygen_evidence = next(q for q in completion.verified_evidence['queries'] if q['query']['dimension']=='spo2')
    assert oxygen_evidence['records'][1]['known_fields']['daily_metrics']['spo2_min'] == 95
    assert oxygen_evidence['records'][1]['known_fields']['sample_summaries'][0]['source'] == 'ringconn'
    assert 'sleep_interval_not_verified' in oxygen_evidence['limitations']
    assert '不能' in completion.trusted_fact_summary and '血氧' in completion.trusted_fact_summary


def test_excluded_only_oxygen_is_no_data_not_normal_and_never_uses_old_night(db, owners):
    from app.models.daily_health import GarminData, SpO2Sample
    from app.services.agent_query_window import parse_query_window, read_calendar_health_query
    owner, _ = owners
    db.add_all([
        GarminData(user_id=owner,record_date=date(2031,4,4),data_source='garmin',spo2_min=60),
        SpO2Sample(user_id=owner,record_date=date(2031,4,4),sample_time=time(1),source='garmin-app',spo2_value=65),
        SpO2Sample(user_id=owner,record_date=date(2031,3,28),sample_time=time(1),source='ringconn',spo2_value=98),
    ])
    db.flush()
    window = parse_query_window({'start_date':'2031-03-29','end_date':'2031-04-04'})
    result = read_calendar_health_query(db, owner, 'spo2', window)
    assert result['availability'] == 'no_data' and result['records'] == []
    assert result['coverage']['days_with_data'] == 0
    with pytest.raises(ValueError):
        read_calendar_health_query(db, None, 'spo2', window)


def test_oxygen_database_failure_is_not_empty_success():
    from app.services.agent_query_window import parse_query_window, read_calendar_health_query
    class BrokenDatabase:
        def query(self, *args):
            raise RuntimeError('synthetic DB failure')
    with pytest.raises(RuntimeError, match='synthetic DB failure'):
        read_calendar_health_query(BrokenDatabase(), 41, 'spo2', parse_query_window({
            'start_date':'2031-03-29','end_date':'2031-04-04'}))


@pytest.mark.parametrize('answer', ['UNVERIFIED_FACT', '血氧正常', '无法确认数据完整性且血氧正常',
                                  'A completely novel unsupported assertion'])
def test_oxygen_answer_is_a_deterministic_projection_not_a_phrase_blacklist(answer):
    from app.services.agent_composed_read_completion import (
        enforce_composed_synthesis_boundaries, evaluate_composed_read_completion,
    )
    from tests.test_agent_composed_read_completion import scope, execution
    completion = evaluate_composed_read_completion(scope('sleep','spo2'), [
        execution('sleep',rows=[]),execution('spo2',rows=[]),
    ])
    result = enforce_composed_synthesis_boundaries(answer, completion)
    assert result.text.startswith(completion.trusted_fact_summary)
    assert result.text == enforce_composed_synthesis_boundaries('UNTRUSTED_PROSE', completion).text
    assert not result.flagged
    assert enforce_composed_synthesis_boundaries(result.text, completion).text == result.text
