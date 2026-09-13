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


@pytest.mark.parametrize('restriction', [
    '只看今早', '只看今晨', '只看午睡前', '限定在那次检查之后',
    '只看最近一次运动后的记录', '仅查询今天上午',
])
@pytest.mark.parametrize('body', ['查询我的饮食并分析', '查询我今天的饮食并分析'])
def test_unknown_restrictor_blocks_rolling_and_calendar_fallback(restriction, body):
    text = f'{restriction}，{body}'
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({'dimension': 'diet', 'days': 7}, text=text).action == 'block'
    assert decide({'dimension': 'diet', 'start_date': '2026-09-13',
                   'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'}, text=text).action == 'block'


@pytest.mark.parametrize('restriction,expected_start', [
    ('只看今天', '2026-09-13'), ('只看本周一', '2026-09-07'),
    ('只看最近一周', '2026-09-07'), ('只看饮食', '2026-09-07'),
])
def test_supported_restrictor_preserves_exact_read_scope(restriction, expected_start):
    text = f'{restriction}，查询我的饮食并分析'
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    query = scope.query('diet')
    assert query['start_date'] == expected_start
    assert decide(dict(query), text=text).action == 'allow'
    assert decide({'dimension': 'sleep'}, text=text).action == 'block'


@pytest.mark.parametrize('restriction', ['只看今晨', '只看午睡前', '仅查询今天上午'])
def test_unknown_restrictor_cannot_use_manage_list_calendar_bypass(restriction):
    text = f'{restriction}，查询我今天的饮食并分析'
    decision = decide({'record_type': 'diet', 'operation': 'list', 'date': '2026-09-13'},
                      text=text, tool='health_manage')
    assert decision.action == 'block'


@pytest.mark.parametrize('text', [
    '请你只看今早，查询我的饮食并分析',
    '范围仅限今早，查询我的饮食并分析',
    '请查询我的饮食并分析，范围限定在那次检查之后',
    '今天上午，查询我的饮食并分析',
    '查询我今天上午的饮食并分析',
    '今早，查询我的饮食并分析',
])
def test_restriction_v3_no_query_or_list_bypass(text):
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({'dimension': 'diet'}, text=text).action == 'block'
    assert decide({'queries': [{'dimension': 'diet'}]}, text=text, tool='health_query_batch').action == 'block'
    assert decide({'record_type': 'diet', 'operation': 'list', 'date': '2026-09-13'},
                  text=text, tool='health_manage').action == 'block'


@pytest.mark.parametrize('text', [
    '只看饮食和睡眠，查询我的饮食、睡眠并分析',
    '范围仅限饮食和睡眠，查询我的饮食、睡眠并分析',
])
def test_restriction_v3_valid_multiple_domains_keep_actual_scope(text):
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope and {q['dimension'] for q in scope.queries} == {'diet', 'sleep'}
    assert all(q['start_date'] == '2026-09-07' and q['end_date'] == '2026-09-13' for q in scope.queries)
    assert decide({'queries': list(scope.queries)}, text=text, tool='health_query_batch').action == 'allow'
    assert decide({'dimension': 'workout'}, text=text).action == 'block'


@pytest.mark.parametrize('time_scope', [
    '今天晚上', '昨天晚上', '今天任意未支持时段', '早餐前', '早餐后',
    '午餐前', '午餐后', '晚餐前', '晚餐后', '运动前', '运动后', '那次检查之后',
])
def test_projection_v4_no_adapter_can_drop_event_or_day_qualifier(time_scope):
    text = f'{time_scope}，查询我的饮食并分析'
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({'dimension': 'diet'}, text=text).action == 'block'
    assert decide({'queries': [{'dimension': 'diet'}]}, text=text, tool='health_query_batch').action == 'block'
    assert decide({'record_type': 'diet', 'operation': 'list', 'date': '2026-09-13'},
                  text=text, tool='health_manage').action == 'block'


@pytest.mark.parametrize('background', ['我上午工作比较忙', '我今天早上感觉有点累'])
@pytest.mark.parametrize('window', ['最近7天', '今天'])
def test_projection_v4_calendar_and_rolling_use_the_same_background_free_query(background, window):
    text = f'{background}。请查询我{window}的睡眠记录并分析。'
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope and len(scope.queries) == 1
    query = scope.query('sleep')
    assert query['start_date'] == ('2026-09-07' if window == '最近7天' else '2026-09-13')
    assert query['end_date'] == '2026-09-13'
    assert decide(dict(query), text=text).action == 'allow'


@pytest.mark.parametrize('time_scope', ['昨晚', '昨天晚上'])
def test_projection_v4_sleep_night_keeps_wake_date(time_scope):
    text = f'{time_scope}，查询我的睡眠并分析'
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope and scope.query('sleep')['start_date'] == '2026-09-13'
    assert scope.query('sleep')['end_date'] == '2026-09-13'
    assert decide(dict(scope.query('sleep')), text=text).action == 'allow'


def test_projection_v4_exact_dinner_plan_keeps_meal_filter():
    text = '我昨天晚上吃了什么'
    decision = decide({'dimension': 'diet'}, text=text)
    assert decision.action == 'allow'
    assert decision.normalized_args['meal_type'] == 'dinner'
    assert decision.normalized_args['date'] == '2026-09-12'


@pytest.mark.parametrize('text,dimension', [
    ('同步一下佳明，再分析昨晚睡眠。', 'sleep'),
    ('帮我看一下昨晚的睡眠，再说说数据有没有同步。', 'sleep'),
    ('分析我昨天的行动。', 'diet'), ('分析我昨天的行动。', 'sleep'),
    ('复盘我2026-09-13的饮食和睡眠。', 'diet'),
])
def test_projection_v5_existing_composed_read_frames_survive(text, dimension):
    result = decide({'dimension': dimension}, text=text)
    assert result.action == 'allow', result.reason


@pytest.mark.parametrize('text,days', [
    ('查一下我近半年睡眠的记录', 183),
    ('查询近一周补剂服用记录', 7),
])
def test_projection_v5_existing_plain_history_keeps_bound_window(text, days):
    dimension = 'supplements' if '补剂' in text else 'sleep'
    result = decide({'dimension': dimension}, text=text)
    assert result.action == 'allow', result.reason
    assert result.normalized_args['days'] == days


@pytest.mark.parametrize('text', [
    '查询我昨天晚上的饮食', '请查我早餐后的饮食',
    '傍晚同步佳明，再查询我今天的饮食',
    '同步一下佳明，傍晚，查询我的睡眠并分析',
])
def test_projection_v5_existing_actions_do_not_erase_unbound_restrictions(text):
    assert decide({'dimension': 'diet' if '饮食' in text else 'sleep'}, text=text).action == 'block'


@pytest.mark.parametrize('disease', ['运动神经元病', '睡眠呼吸暂停综合征', '饮食失调症'])
def test_projection_v5_exact_clinical_entity_is_not_a_record_domain_substring(disease):
    result = decide({'dimension': 'illness'}, text=f'查询近半年{disease}的记录')
    assert result.action == 'allow', result.reason


def test_projection_v5_clinical_clause_does_not_exempt_independent_diet_restriction():
    text = '查询近半年运动神经元病的记录。只看今早，查询我的饮食并分析。'
    assert decide({'dimension': 'diet'}, text=text).action == 'block'


@pytest.mark.parametrize('text', [
    '比较近7天睡眠和近30天HRV',
    '比较睡眠近7天和HRV近30天',
    '睡眠近7天对比HRV近30天',
])
def test_projection_v5_legacy_comparison_keeps_each_window(text):
    args = {'queries': [{'dimension': 'sleep', 'days': 7, 'agg': 'avg'},
                        {'dimension': 'hrv', 'days': 30, 'agg': 'avg'}],
            'compare': {'a': 0, 'b': 1, 'op': 'diff'}}
    assert decide(args, text, 'health_query_batch').action == 'allow'
    args['queries'][0]['days'] = 30
    assert decide(args, text, 'health_query_batch').action == 'block'


@pytest.mark.parametrize('restriction', ['只看晚上', '早餐后', '范围限定在那次检查之后'])
def test_projection_v5_comparison_does_not_consume_unknown_restrictions(restriction):
    args = {'queries': [{'dimension': 'sleep', 'days': 7}, {'dimension': 'hrv', 'days': 30}]}
    assert decide(args, f'比较近7天睡眠和近30天HRV，{restriction}', 'health_query_batch').action == 'block'


@pytest.mark.parametrize('text,day', [
    ('麻烦把我的佳明数据刷新一下，然后看看昨晚睡得怎么样。', '2026-09-13'),
    ('先分析昨天的睡眠，再起草今天的计划', '2026-09-12'),
])
def test_projection_v5_composed_frames_keep_the_read_date(text, day):
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    assert scope.query('sleep')['start_date'] == day


@pytest.mark.parametrize('text', [
    '先分析我的睡眠，再起草今天的计划',
    '先分析早餐后的睡眠，再起草今天的计划',
    '先分析昨天上午的睡眠，再起草今天的计划',
])
def test_projection_v5_draft_never_supplies_or_erases_read_time(text):
    assert resolve_owned_read_scope(snapshot(text)) is None
