"""Synthetic full-consumption contract for today's Garmin running review."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.agent_kernel.garmin_workout_review_scope import resolve_garmin_workout_review_scope


@pytest.mark.parametrize('text', [
    '同步我的佳明数据，获取我最新的运动记录，我刚跑了3公里，分析我刚才的跑步，给我建议。',
    '帮我同步佳明数据，获取最新运动数据，我已经跑步了，分析刚才跑步并给我建议。',
    '同步Garmin数据，查看我最新一次运动记录，分析我刚才这次跑步，给我一些建议。',
])
def test_full_owned_garmin_running_review(text):
    scope = resolve_garmin_workout_review_scope(text)
    assert scope is not None
    assert scope.query_args(datetime(2026, 10, 9, 0, 30, tzinfo=ZoneInfo('Asia/Shanghai')), 'Asia/Shanghai') == {
        'dimension': 'workout', 'start_date': '2026-10-09', 'end_date': '2026-10-09', 'timezone': 'Asia/Shanghai',
    }


@pytest.mark.parametrize('text', [
    '同步我朋友的佳明数据，获取最新运动记录，分析他的跑步，给我建议',
    '不要同步佳明数据，获取最新运动记录，分析刚才跑步，给我建议',
    '“同步佳明数据”，获取最新运动记录，分析刚才跑步，给我建议',
    '如果同步佳明数据，获取最新运动记录，分析刚才跑步，给我建议',
    '同步佳明数据，获取昨天最新运动记录，分析刚才跑步，给我建议',
    '同步佳明数据，获取最新运动记录，分析刚才跑步，给我建议，删除旧记录',
    '同步佳明数据，获取最新运动记录，分析刚才跑步，给我建议，顺便看看体检',
    '同步佳明数据，获取最新运动记录，我刚游泳了，分析刚才跑步，给我建议',
    '同步佳明数据，获取最新运动记录，分析刚才跑步，给我建议，不用执行',
])
def test_unconsumed_or_unowned_request_has_no_compound_authority(text):
    assert resolve_garmin_workout_review_scope(text) is None
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    env = AgentEnvelope(user_id=41, channel='chat', text=text)
    context = ExecutionContext.for_test(user_id=41, channel='chat')
    turn = TurnSnapshot(env, context, build_intent_frame(env, context))
    for tool, args in [('health_query', {'dimension': 'workout', 'days': 7}),
                       ('health_record', {'record_type': 'garmin_sync', 'data': {}})]:
        assert decide_tool_capability(turn, ToolExecutionRequest(tool, args)).action == 'block'


def test_gateway_binds_only_current_day_workout_and_sync():
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    text = '同步我的佳明数据，获取我最新的运动记录，我刚跑了3公里，分析我刚才的跑步，给我建议。'
    env = AgentEnvelope(user_id=41, channel='chat', text=text)
    context = ExecutionContext.for_test(user_id=41, channel='chat')
    turn = TurnSnapshot(env, context, build_intent_frame(env, context))
    def check(tool, args):
        return decide_tool_capability(turn, ToolExecutionRequest(tool, args))
    decision = check('health_query', {'dimension': 'workout'})
    assert decision.action == 'allow'
    assert decision.normalized_args == resolve_garmin_workout_review_scope(text).query_args(context.current_time, context.timezone)
    assert check('health_record', {'record_type': 'garmin_sync', 'data': {}}).action == 'allow'
    for tool, args in [
        ('health_query', {'dimension': 'workout', 'days': 7}),
        ('health_query', {'dimension': 'sleep'}),
        ('health_query', {'dimension': 'workout', 'user_id': 99}),
        ('health_record', {'record_type': 'exercise', 'data': {'duration': 30}}),
        ('health_analysis', {'analysis_type': 'comprehensive'}),
    ]:
        assert check(tool, args).action == 'block'


def test_spoken_compound_instruction_consumes_all_roles():
    text = '同步一下佳明的数据，获取到我最新的运动的数据，我跑了3公里，分析一下刚才跑的情况怎么样，给我一些建议。'
    scope = resolve_garmin_workout_review_scope(text)
    assert scope is not None
    assert scope.reported_distance_km == 3
    for suffix in ('，删掉其他记录', '，不要同步', '，分析他人的数据'):
        assert resolve_garmin_workout_review_scope(text.rstrip('。') + suffix) is None


@pytest.mark.parametrize('distance,expected',[('一',1),('三',3),('十',10),('3.5',3.5)])
def test_closed_spoken_distance(distance,expected):
    text=f'同步一下佳明的数据，获取到我最新的运动的数据，我跑了{distance}公里，分析一下刚才跑的情况怎么样，给我一些建议。'
    scope=resolve_garmin_workout_review_scope(text)
    assert scope is not None
    assert scope.reported_distance_km==expected


@pytest.mark.parametrize('background',['我跑了很多公里','我跑了NaN公里','我跑了无限公里','朋友跑了三公里','我没跑三公里','我跑了零公里','我跑了一百公里'])
def test_unknown_or_unowned_distance_is_not_bound(background):
    text=f'同步一下佳明的数据，获取到我最新的运动的数据，{background}，分析一下刚才跑的情况怎么样，给我一些建议。'
    assert resolve_garmin_workout_review_scope(text) is None
