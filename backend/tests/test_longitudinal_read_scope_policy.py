"""Longitudinal reads bind model proposals to independently parsed owned scope."""
from datetime import datetime

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot

REQUEST = ('我的既往诊断是几个月前的事情。请基于诊断时间判断当前状况，'
           '结合我每天实际服用的补剂、睡眠、运动、情绪、工作和饮食，'
           '先调用工具查询已有记录，再给建议。')


def snapshot(text=REQUEST):
    env = AgentEnvelope(user_id=41, channel='typed', text=text)
    context = ExecutionContext(current_time=datetime.fromisoformat('2026-09-13T09:00:00+08:00'),
                               timezone='Asia/Shanghai', user_id=41, channel='typed')
    return TurnSnapshot(env, context, build_intent_frame(env, context))


def decide(args, text=REQUEST, tool='health_query'):
    return decide_tool_capability(snapshot(text), ToolExecutionRequest(tool, args))


@pytest.mark.parametrize('dimension', ['diet', 'sleep', 'workout', 'supplements'])
def test_diagnosis_context_does_not_replace_requested_longitudinal_domains(dimension):
    turn = snapshot()
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    query = {'dimension': dimension, 'days': 7, 'start_date': '2026-09-07',
             'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'}
    assert scope.query(dimension) == query
    assert set(scope.limitations) == {'default_recent_7_days', 'mood_not_queried', 'work_not_queried'}
    decision = decide(query)
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == query
    assert decide({'dimension': 'illness'}).action == 'block'
    assert decide({'record_type': 'weight', 'data': {'weight': 70}}, tool='health_record').action == 'block'


@pytest.mark.parametrize('changes', [
    {'days': 30}, {'days': True}, {'days': '7'},
    {'start_date': '2026-09-01'}, {'end_date': '2026-09-14'}, {'timezone': 'UTC'},
    {'user_id': 42}, {'owner_id': 42}, {'tenant_id': 42},
])
def test_longitudinal_model_args_cannot_expand_date_or_owner(changes):
    args = {'dimension': 'sleep', 'days': 7, 'start_date': '2026-09-07',
            'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai', **changes}
    assert decide(args).action == 'block'


def test_longitudinal_batch_binds_all_and_rejects_extra_dimension():
    scope = resolve_owned_read_scope(snapshot())
    assert scope is not None
    queries = [dict(query) for query in scope.queries]
    decision = decide({'queries': queries}, tool='health_query_batch')
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == {'queries': queries}
    assert decide({'queries': [*queries, {'dimension': 'genetic'}]}, tool='health_query_batch').action == 'block'
    assert decide({'queries': queries, 'owner_id': 42}, tool='health_query_batch').action == 'block'
    assert decide({'queries': [{**queries[0], 'days': 31}]}, tool='health_query_batch').action == 'block'


@pytest.mark.parametrize('text', [
    '不要查询我的日常睡眠和饮食记录，也别分析。',
    '如果需要，查询我的日常睡眠和饮食记录再分析。',
    '查询我朋友近期睡眠和饮食记录，再分析。',
    '解释以下例句：“请查询我的日常睡眠和饮食记录，再给建议。”',
])
def test_longitudinal_projection_does_not_invent_authority(text):
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({'dimension': 'sleep', 'days': 7}, text=text).action == 'block'


@pytest.mark.parametrize('text,dimension', [
    ('请查询我近半年饮食记录并分析', 'diet'),
    ('请查询我过去一个月饮食记录并分析', 'diet'),
    ('请查询我最近99天睡眠记录并分析', 'sleep'),
])
def test_rejected_longitudinal_range_cannot_fall_through_to_legacy_rolling_read(text, dimension):
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({'dimension': dimension, 'days': 7}, text=text).action == 'block'
    assert decide({'queries': [{'dimension': dimension, 'days': 7}]},
                  text=text, tool='health_query_batch').action == 'block'


@pytest.mark.parametrize('day,dimension', [('今天', 'diet'), ('今日', 'diet'), ('今天', 'sleep'), ('昨晚', 'sleep')])
def test_explicit_split_day_uses_exact_calendar_binder_not_longitudinal_default(day, dimension):
    domain = '饮食' if dimension == 'diet' else '睡眠'
    text = f'只看{day}，查询我的{domain}并分析'
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    assert scope.query(dimension) == {'dimension': dimension, 'start_date': '2026-09-13',
                                     'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'}
    assert 'default_recent_7_days' not in scope.limitations
    decision = decide({'dimension': dimension}, text=text)
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == scope.query(dimension)


@pytest.mark.parametrize('text,dimension', [
    ('只查今日，查询我的运动记录并分析', 'workout'),
    ('只看今天，查询我的补剂记录并分析', 'supplements'),
    ('只看今晚，查询我的睡眠并分析', 'sleep'),
    ('只看前晚，查询我的睡眠并分析', 'sleep'),
])
def test_unsupported_explicit_day_never_gets_a_seven_day_read(text, dimension):
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({'dimension': dimension, 'days': 7}, text=text).action == 'block'
