"""events_timeline_service.build_timeline tz-awareness 回归。

钉一个曾让整条 timeline 变空白的 bug:_workouts() 的 occurred_at 是 tz-aware
(WorkoutRecord.start_time 强制 UTC),而 _alerts()/_exams()/_medications()/_sleep_lows()
用 datetime.combine(...) 出 tz-naive。当同一用户在窗口内**同时**有 workout 和
exam/alert/medication/poor-sleep 时,events.sort(key=occurred_at) 抛
`TypeError: can't compare offset-naive and offset-aware datetimes` → 首页 timeline 全空。

修复:所有 occurred_at 统一标 tz-aware UTC,再排序。本测试守这条不变量。
"""
from datetime import date, datetime, timedelta, timezone

from app.services.events_timeline_service import build_timeline


def _seed_workout(db, user_id: int, *, days_ago: int):
    """tz-AWARE occurred_at 一侧(start_time 强制 UTC)。"""
    from app.models.daily_health import WorkoutRecord

    w = WorkoutRecord(
        user_id=user_id,
        workout_date=(datetime.now(timezone.utc) - timedelta(days=days_ago)).date(),
        start_time=datetime.now(timezone.utc) - timedelta(days=days_ago),
        workout_type="running",
        duration_seconds=1080,
        distance_meters=2600,
        avg_heart_rate=150,
    )
    db.add(w)
    db.commit()
    return w


def _seed_exam(db, user_id: int, *, days_ago: int):
    """曾经 tz-NAIVE 的一侧(datetime.combine(exam_date, ...))。"""
    from app.models.medical_exam import MedicalExam

    exam = MedicalExam(
        user_id=user_id,
        exam_date=(datetime.now(timezone.utc) - timedelta(days=days_ago)).date(),
        exam_type="comprehensive",
        hospital_name="测试医院",
    )
    db.add(exam)
    db.commit()
    return exam


def test_workout_plus_exam_sorts_without_typeerror(db, auth_user_and_headers):
    """workout(aware) + exam(曾 naive)同窗 → 不抛、两条都在、按时间倒序。"""
    user, _ = auth_user_and_headers
    # exam 更近(2 天前),workout 更早(5 天前)→ 倒序后 exam 在前。
    _seed_workout(db, user.id, days_ago=5)
    _seed_exam(db, user.id, days_ago=2)

    # 修复前:这一行直接 TypeError(can't compare offset-naive and offset-aware)。
    events = build_timeline(db, user.id, days=30)

    sources = {e.source for e in events}
    assert "workout" in sources, "workout 事件应在 timeline 里"
    assert "exam" in sources, "exam 事件应在 timeline 里"

    # 不变量:所有 occurred_at 必须 tz-aware,sort 才不会再炸。
    assert all(e.occurred_at.tzinfo is not None for e in events), (
        "所有 occurred_at 必须 tz-aware UTC(混入 naive 会让 build_timeline 排序抛 TypeError)"
    )

    # 倒序:相邻项时间单调不增(同时也证明跨 tz 比较没抛)。
    times = [e.occurred_at for e in events]
    assert times == sorted(times, reverse=True), "timeline 应按 occurred_at 倒序"

    # 更近的 exam(2 天前)排在更早的 workout(5 天前)之前。
    exam_idx = next(i for i, e in enumerate(events) if e.source == "exam")
    workout_idx = next(i for i, e in enumerate(events) if e.source == "workout")
    assert exam_idx < workout_idx
