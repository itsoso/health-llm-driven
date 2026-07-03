"""events_timeline_service.build_timeline tz-awareness 回归。

钉一个曾让整条 timeline 变空白的 bug:_workouts() 的 occurred_at 是 tz-aware
(WorkoutRecord.start_time 强制 UTC),而 _alerts()/_exams()/_medications()/_sleep_lows()
用 datetime.combine(...) 出 tz-naive。当同一用户在窗口内**同时**有 workout 和
exam/alert/medication/poor-sleep 时,events.sort(key=occurred_at) 抛
`TypeError: can't compare offset-naive and offset-aware datetimes` → 首页 timeline 全空。

修复(两层,加层不减层):
  1. 源头:所有 occurred_at 统一标 tz-aware UTC(本文件守这条不变量);
  2. 兜底:build_timeline 排序 key 只读地把 naive 按 UTC 对待(_sort_key_utc),
     未来某个新源漏带 tzinfo 时,一个源的疏漏不再炸掉整条 timeline。
"""
from datetime import date, datetime, timedelta, timezone

from app.services.events_timeline_service import TimelineEvent, _sort_key_utc, build_timeline


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


def _seed_alert(db, user_id: int, *, days_ago: int):
    """曾经 tz-NAIVE 的另一侧(datetime.combine(detection_date, 12:00))。"""
    from app.models.anomaly_alert import AnomalyAlert

    a = AnomalyAlert(
        user_id=user_id,
        alert_type="rhr_spike",
        severity="warning",
        metric_name="resting_heart_rate",
        current_value=72.0,
        detection_date=(datetime.now(timezone.utc) - timedelta(days=days_ago)).date(),
        message="静息心率较基线明显升高",
    )
    db.add(a)
    db.commit()
    return a


def test_workout_plus_alert_sorts_without_typeerror(db, auth_user_and_headers):
    """workout(aware) + alert(曾 naive)同窗 → 不抛、两条都在、按时间倒序。"""
    user, _ = auth_user_and_headers
    # workout 更近(1 天前),alert 更早(4 天前)→ 倒序后 workout 在前。
    _seed_workout(db, user.id, days_ago=1)
    _seed_alert(db, user.id, days_ago=4)

    events = build_timeline(db, user.id, days=30)

    sources = {e.source for e in events}
    assert "workout" in sources, "workout 事件应在 timeline 里"
    assert "alert" in sources, "alert 事件应在 timeline 里"

    assert all(e.occurred_at.tzinfo is not None for e in events), (
        "所有 occurred_at 必须 tz-aware UTC(源头不变量)"
    )

    times = [e.occurred_at for e in events]
    assert times == sorted(times, reverse=True), "timeline 应按 occurred_at 倒序"

    workout_idx = next(i for i, e in enumerate(events) if e.source == "workout")
    alert_idx = next(i for i, e in enumerate(events) if e.source == "alert")
    assert workout_idx < alert_idx


def _mk_event(source: str, occurred_at: datetime) -> TimelineEvent:
    return TimelineEvent(
        id=f"{source}_x",
        source=source,
        title="t",
        subtitle=None,
        icon="i",
        color="#000",
        occurred_at=occurred_at,
        deep_link=None,
        severity=None,
    )


def test_sort_key_treats_naive_as_utc_readonly():
    """兜底层:未来某源漏带 tzinfo 时,排序不抛 TypeError,且不回写 occurred_at。

    源头不变量(全 aware)由上面两个 DB 测试守;本测试守的是防御深度——
    单个源的疏漏不该让 aware×naive 比较炸掉整条 timeline。
    """
    aware = _mk_event("workout", datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))
    naive = _mk_event("future_source", datetime(2026, 7, 2, 12, 0))  # 故意 naive

    events = [aware, naive]
    # 修复前语义:直接 sort 抛 TypeError。兜底 key 之后不抛且顺序正确(naive 按 UTC 对待)。
    events.sort(key=_sort_key_utc, reverse=True)

    assert [e.source for e in events] == ["future_source", "workout"]
    # read-only:key 不改 occurred_at 本身(naive 的仍是 naive,展示语义不被偷改)。
    assert naive.occurred_at.tzinfo is None
    assert aware.occurred_at.tzinfo is not None
