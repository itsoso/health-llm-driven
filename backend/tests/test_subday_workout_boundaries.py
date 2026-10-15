"""Local event boundaries and follow-up scope must not widen personal reads."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ActionableReference
from app.services.agent_longitudinal_read import read_longitudinal_health_query, workout_period_bounds
from app.services.agent_query_window import parse_query_window
from app.services.agent_read_task_continuation import read_task_metadata, resolve_read_task_continuation
from tests.test_recent_workout_read_regression import snapshot


@pytest.mark.parametrize('zone,day,hours', [
    ('Asia/Shanghai', '2026-10-10', 12),
    ('America/New_York', '2026-03-08', 11),
    ('America/New_York', '2026-11-01', 13),
])
def test_real_database_half_open_local_morning_including_dst(db, auth_user_and_headers, zone, day, hours):
    from app.models.daily_health import WorkoutRecord

    user, _ = auth_user_and_headers
    local_day = date.fromisoformat(day)
    turn = snapshot('分析上午的跑步')
    turn = replace(turn, context=replace(turn.context, timezone=zone,
        current_time=datetime.combine(local_day, datetime.min.time(), ZoneInfo(zone))))
    scope = resolve_owned_read_scope(turn)
    window = parse_query_window(scope.query('workout'))
    start, end = workout_period_bounds(window, scope.workout_selection)
    utc_start, utc_end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    assert (utc_end - utc_start).total_seconds() == hours * 3600
    times = [utc_start - timedelta(microseconds=1), utc_start,
             utc_end - timedelta(microseconds=1), utc_end]
    rows = [WorkoutRecord(user_id=user.id, workout_date=local_day - timedelta(days=1),
                          workout_type='running', start_time=stamp) for stamp in times]
    db.add_all(rows)
    db.commit()
    payload = read_longitudinal_health_query(db, user.id, 'workout', window,
                                            selection=scope.workout_selection)
    assert {r['id'] for r in payload['records']} == {rows[1].id, rows[2].id}
    assert all(r['record_date'] == day for r in payload['records'])
    assert all(datetime.fromisoformat(r['event_start_time']).utcoffset() is not None
               for r in payload['records'])


@pytest.mark.parametrize('text', ['继续', '重试', '给我一些启发'])
def test_followup_cannot_drop_period_or_type(text):
    original = snapshot('分析上午的跑步')
    scope = resolve_owned_read_scope(original)
    assert read_task_metadata(original, scope, sync_status=False) is None
    # Even a persisted legacy-shaped envelope with the narrower limitation must
    # not become a full-day read just because it omits the internal selector.
    raw = {'version': 'owned-read-task.v2', 'created_at': original.context.current_time.isoformat(),
           'queries': list(scope.queries), 'sync_status': False, 'limitations': list(scope.limitations)}
    followup = replace(snapshot(text), actionable_references=(
        ActionableReference(kind='owned_read_task', source_message_id='123', data=raw),))
    assert resolve_read_task_continuation(followup) is None
    assert resolve_owned_read_scope(followup) is None


@pytest.mark.parametrize('text', ['分析明天上午的跑步', '分析上午的跑步并删除记录',
                                  '分析今天上午的跑步并同步'])
def test_unresolved_time_is_not_misreported_as_missing_identity(text):
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from app.services.agent_kernel.types import ToolExecutionRequest
    from app.services.agent_policy_retry import is_terminal_policy_reason, is_repairable_read_reason
    decision = decide_tool_capability(snapshot(text), ToolExecutionRequest('health_query', {'dimension': 'workout'}))
    assert decision.action == 'block'
    assert decision.reason == 'longitudinal_read_scope_unresolved'
    assert is_terminal_policy_reason(decision.reason)
    assert not is_repairable_read_reason(decision.reason)


def test_real_identity_mismatch_keeps_identity_failure():
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from app.services.agent_kernel.types import ToolExecutionRequest
    turn = snapshot('分析上午的跑步')
    turn = replace(turn, context=replace(turn.context, user_id=42))
    decision = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'workout'}))
    assert decision.action == 'block'
    assert decision.reason == 'health_query_subject_not_current_user'
