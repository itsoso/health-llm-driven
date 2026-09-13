"""Synthetic owner/window and actual-event regressions, no external data."""
from dataclasses import replace
from datetime import date, datetime

import pytest

from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_longitudinal_read import (
    resolve_longitudinal_read_queries, longitudinal_read_limitations, read_longitudinal_health_query,
)
from app.services.agent_query_window import parse_query_window

TEXT = ('我的既往诊断是几个月前的事情。请基于诊断时间判断当前状况，'
        '结合我每天实际服用的补剂、睡眠、运动、情绪、工作和饮食，先调用工具查询已有记录，再给建议。')


def snapshot(text=TEXT):
    env = AgentEnvelope(user_id=17, channel='typed', text=text)
    ctx = ExecutionContext(current_time=datetime.fromisoformat('2031-04-03T17:10:00+00:00'),
                           timezone='Asia/Shanghai', user_id=17, channel='typed')
    return TurnSnapshot(env, ctx, build_intent_frame(env, ctx))


def window():
    return parse_query_window({'start_date': '2031-03-29', 'end_date': '2031-04-04', 'timezone': 'Asia/Shanghai'})


def test_background_diagnosis_does_not_hijack_recent_personal_read():
    s = snapshot()
    result = resolve_longitudinal_read_queries(s)
    assert {q['dimension'] for q in result} == {'diet', 'sleep', 'workout', 'supplements'}
    assert all(q == {'dimension': q['dimension'], 'days': 7, **window().as_dict()} for q in result)
    assert set(longitudinal_read_limitations(s)) == {'default_recent_7_days', 'mood_not_queried', 'work_not_queried'}


@pytest.mark.parametrize('phrase,days', [('近3天', 3), ('最近31天', 31), ('过去七天', 7), ('近两周', 14)])
def test_explicit_bounded_rolling_window(phrase, days):
    result = resolve_longitudinal_read_queries(snapshot(f'请查询我{phrase}的饮食、运动记录并分析'))
    assert {q['dimension'] for q in result} == {'diet', 'workout'}
    assert all(q['days'] == days for q in result)
    assert 'default_recent_7_days' not in longitudinal_read_limitations(snapshot(f'请查询我{phrase}的饮食记录并分析'))


@pytest.mark.parametrize('text', [
    '不要查询我的记录，只分析睡眠饮食运动补剂的关系',
    '请分析以下例句：“查询我近7天睡眠、饮食记录并分析。”',
    '如果需要，可以查询我最近睡眠饮食记录并分析',
    '请查询我朋友的近期睡眠饮食记录并分析',
    '请查询小王的近期睡眠饮食记录并分析，我想了解',
    '请查询我的运动和小王的饮食记录并分析',
    '请分析我近期饮食睡眠的一般关系，不用读取记录',
    '请查询我近32天饮食记录并分析',
    '请查询我过去几个月饮食记录并分析',
    '请查询我2020-01-01到2020-01-30饮食记录并分析',
    '请查询我最近7天到昨天的睡眠记录并分析',
    '请查询我昨天睡眠和近7天饮食记录并分析',
    '请查询我过去0天睡眠记录并分析',
    '请查询我近期饮食记录，删除补剂记录并分析',
    '请查询我从确诊至今的睡眠记录并分析',
])
def test_no_implicit_owner_authority_or_ambiguous_window(text):
    assert resolve_longitudinal_read_queries(snapshot(text)) is None


def test_context_owner_must_match_and_client_dates_do_not_bind():
    s = snapshot()
    assert resolve_longitudinal_read_queries(replace(s, context=replace(s.context, user_id=18))) is None
    s = replace(s, envelope=replace(s.envelope, client_time_context={'date': '2020-01-01'}))
    assert resolve_longitudinal_read_queries(s)[0]['end_date'] == '2031-04-04'


@pytest.fixture
def owners(db):
    from app.models.user import User
    users = [User(username=f'longitudinal-{n}', email=f'longitudinal-{n}@example.test',
                  name='Synthetic', hashed_password='fixture') for n in ('a', 'b')]
    db.add_all(users); db.flush()
    return users[0].id, users[1].id


def test_workout_reads_actual_workouts_and_manual_exercise_only_in_window(db, owners):
    from app.models.daily_health import WorkoutRecord, ExerciseRecord
    a, b = owners
    db.add_all([
        WorkoutRecord(user_id=a, workout_date=date(2031,4,1), workout_type='running', duration_seconds=1801, distance_meters=3000.12345),
        WorkoutRecord(user_id=b, workout_date=date(2031,4,1), workout_type='private'),
        WorkoutRecord(user_id=a, workout_date=date(2031,3,1), workout_type='old'),
        ExerciseRecord(user_id=a, record_date=date(2031,4,2), exercise_type='yoga', duration=11),
    ]); db.flush()
    result = read_longitudinal_health_query(db, a, 'workout', window())
    assert result['source_scope'] == 'owned_actual_workout_records'
    assert result['availability'] == 'available' and len(result['records']) == 2
    assert {r['record_kind'] for r in result['records']} == {'workout_record', 'exercise_record'}
    assert result['records'][0]['distance_meters'] == 3000.12345
    assert result['records'][1]['duration_seconds'] == 660


def test_supplements_use_intakes_and_taken_logs_not_definitions_or_plans(db, owners):
    from app.models.daily_health import SupplementIntake
    from app.models.supplement import SupplementDefinition, SupplementRecord
    a, b = owners
    own = SupplementDefinition(user_id=a, name='synthetic taken', dosage='9999mg')
    other = SupplementDefinition(user_id=b, name='private', dosage='9999mg')
    unused = SupplementDefinition(user_id=a, name='definition only', dosage='9999mg')
    db.add_all([own, other, unused]); db.flush()
    db.add_all([
        SupplementIntake(user_id=a, record_date=date(2031,4,1), supplement_name='synthetic intake', dosage=1.23456, unit='mg'),
        SupplementIntake(user_id=b, record_date=date(2031,4,1), supplement_name='private intake'),
        SupplementRecord(user_id=a, supplement_id=own.id, record_date=date(2031,4,2), taken=True),
        SupplementRecord(user_id=a, supplement_id=own.id, record_date=date(2031,4,3), taken=False),
        SupplementRecord(user_id=a, supplement_id=other.id, record_date=date(2031,4,2), taken=True),
    ]); db.flush()
    result = read_longitudinal_health_query(db, a, 'supplements', window())
    assert len(result['records']) == 2 and all(r['taken'] is True for r in result['records'])
    assert result['source_scope'] == 'owned_actual_supplement_intake_logs'
    assert result['records'][0]['dosage'] == 1.23456
    assert result['records'][1]['dosage'] is None
    assert '9999' not in str(result) and 'private' not in str(result)


@pytest.mark.parametrize('dimension', ['workout', 'supplements', 'diet', 'sleep'])
def test_empty_is_no_data_not_zero(db, owners, dimension):
    result = read_longitudinal_health_query(db, owners[0], dimension, window())
    assert result['records'] == [] and result['availability'] == 'no_data'
    assert result['window'] == window().as_dict()


def test_unsupported_dimensions_bad_owner_and_db_errors_are_explicit(db, owners):
    with pytest.raises(ValueError):
        read_longitudinal_health_query(db, owners[0], 'mood', window())
    with pytest.raises(ValueError):
        read_longitudinal_health_query(db, True, 'workout', window())
    class Broken:
        def query(self, *args):
            raise RuntimeError('synthetic failure')
    with pytest.raises(RuntimeError, match='synthetic failure'):
        read_longitudinal_health_query(Broken(), owners[0], 'workout', window())


@pytest.mark.parametrize('text', [
    '请结合我的日常饮食、每天睡眠、运动状态和实际服用的补剂，分析我当前的状况。要分别调用相关模块的HTTP接口或Skills，依据真实数据给我建议。',
    '我三个月前确诊糖尿病，请查询我近期的睡眠饮食记录并分析当前状况。',
])
def test_other_explicit_analysis_forms_keep_background_separate(text):
    queries = resolve_longitudinal_read_queries(snapshot(text))
    assert queries and all(q['days'] == 7 for q in queries)


@pytest.mark.parametrize('text', [
    '请查询我过去一个月饮食记录并分析',
    '请查询我近半年饮食记录并分析',
    '请查询我的全部饮食记录并分析',
    '不必查询我近期饮食记录，只分析一般关系',
    '我未授权查询近期睡眠记录，分析一下这个要求',
    '请查询我过去七七天饮食记录并分析',
    '我最近3天饮食和睡眠相关的记录不需要查询，只分析一般关系',
])
def test_unbounded_or_disallowed_requests_never_fall_back_to_seven_days(text):
    assert resolve_longitudinal_read_queries(snapshot(text)) is None


def test_event_reader_total_row_budget_fails_without_silent_truncation(db, owners, monkeypatch):
    from app.models.daily_health import WorkoutRecord, ExerciseRecord
    from app.services import agent_longitudinal_read as reader
    owner = owners[0]
    db.add_all([WorkoutRecord(user_id=owner, workout_date=date(2031,4,1), workout_type='running'),
                ExerciseRecord(user_id=owner, record_date=date(2031,4,2), exercise_type='yoga')]); db.flush()
    monkeypatch.setattr(reader, 'MAX_CALENDAR_ROWS', 1)
    with pytest.raises(ValueError, match='result_limit_exceeded'):
        reader.read_longitudinal_health_query(db, owner, 'workout', window())


def test_original_oral_request_keeps_inverted_http_mcp_skills_authorization():
    text = ('我的感冒其实是三个多月前的事情，你要基于感冒的诊断的时间来推断我当前的状况，'
            '包括我日常在服用的实际服用的补剂，每天的睡眠的状态、运动的状态、情绪的状态，'
            '以及日常工作、饮食等等，来给到我建议。要分别去发起对应模块的HTTP的请求，'
            '或者MCP调用，或者Skills的调用，这样才能给到我精准的建议。')
    result = resolve_longitudinal_read_queries(snapshot(text))
    assert result and {q['dimension'] for q in result} == {'diet', 'sleep', 'workout', 'supplements'}
    assert all(q['days'] == 7 for q in result)


def test_real_stop_instruction_is_not_weakened_by_separate_invocations_fix():
    assert resolve_longitudinal_read_queries(snapshot('别查询我近期饮食睡眠记录，分析一般关系')) is None


@pytest.mark.parametrize('text', [
    '请分析小王近期睡眠和饮食，调用工具获取记录后给我建议。',
    '请结合张三近期饮食和运动，调用模块获取记录后给我建议。',
    '请查询我的运动和李四近期饮食记录并分析。',
])
def test_named_domain_subject_without_possessive_cannot_inherit_requester(text):
    assert resolve_longitudinal_read_queries(snapshot(text)) is None


@pytest.mark.parametrize('text', ['请查询我近半年饮食记录并分析', '请查询我过去一个月睡眠记录并分析',
                                   '请查询我最近99天睡眠记录并分析'])
def test_invalid_longitudinal_request_is_distinguishable_from_not_applicable(text):
    from app.services.agent_longitudinal_read import longitudinal_read_scope_requested
    assert longitudinal_read_scope_requested(snapshot(text))
    assert resolve_longitudinal_read_queries(snapshot(text)) is None


@pytest.mark.parametrize('day', [
    '今天', '今日', '今晚', '今夜', '昨晚', '昨夜', '前晚', '前夜',
    '明晚', '明日', '后晚', '前日', '周二', '9/12',
])
def test_split_calendar_prefix_never_defaults_to_recent_seven_days(day):
    s = snapshot(f'只看{day}，查询我的饮食并分析')
    assert resolve_longitudinal_read_queries(s) is None
    assert longitudinal_read_limitations(s) == ()


def test_explicit_day_survives_removing_historical_diagnosis_context():
    s = snapshot('只看今天。我的既往诊断是几个月前的事情。查询我的饮食并分析。')
    assert resolve_longitudinal_read_queries(s) is None
