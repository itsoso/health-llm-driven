"""cut 7 锻炼时点:pick_workout_start 纯函数 + day_schedule_service 接缝(偏好窗/避工作/readiness 门控)。"""
from types import SimpleNamespace

from app.services.timing_solver import DayContext, RED, _to_min, pick_workout_start
from app.services.day_schedule_service import schedule_from_medications


def _ctx(**kw):
    base = dict(wake="07:00", sleep="22:30",
                meals={"breakfast": "07:30", "lunch": "12:00", "dinner": "18:30"},
                work_start="09:00", work_end="18:00", is_workday=True)
    base.update(kw)
    return DayContext(**base)


# ── pick_workout_start ───────────────────────────────────────────────
def test_evening_after_work_before_bed():
    # 9–18 上班、晚睡 22:30 → 傍晚锻炼排在下班后、避晚餐、睡前 2h 内收口。
    start = pick_workout_start(_ctx(), "evening", 45)
    assert start is not None
    assert start >= _to_min("18:00")          # 下班后
    assert start + 45 <= _to_min("22:30") - 120  # 结束 ≥ 睡前 2h(≤20:30)
    # 避开晚餐 18:30 ±60(不落 17:30–19:30 起步)
    assert not (_to_min("17:30") < start < _to_min("19:30"))


def test_workout_avoids_work_block():
    start = pick_workout_start(_ctx(), "any", 40)
    assert start is not None
    # 整段不落在 09:00–18:00 工作窗内
    assert not (_to_min("09:00") <= start < _to_min("18:00"))
    assert not (_to_min("09:00") < start + 40 <= _to_min("18:00"))


def test_no_slot_returns_none():
    # 极早睡(20:00)+ 9–18 上班 + 90min → latest_end=18:00=工作窗尾,放不下 → None。
    start = pick_workout_start(_ctx(sleep="20:00"), "any", 90)
    assert start is None


def test_rest_day_weekend_widens_window():
    # 周末不避工作窗 → 上午就能排。
    start = pick_workout_start(_ctx(is_workday=False), "morning", 40)
    assert start is not None
    assert start < _to_min("11:30")


# ── schedule_from_medications 接缝 ────────────────────────────────────
def _profile(**kw):
    base = dict(usual_wake_time="07:00", usual_sleep_time="22:30",
                work_start_time="09:00", work_end_time="18:00",
                workout_pref_window="evening", workout_target_minutes=45)
    base.update(kw)
    return SimpleNamespace(**base)


def test_schedule_places_workout():
    out = schedule_from_medications([], profile=_profile())
    workouts = [s for s in out["scheduled"] if s["id"] == "workout:today"]
    assert len(workouts) == 1
    assert workouts[0]["domain"] == "movement"
    assert "锻炼" in workouts[0]["title"]


def test_no_pref_no_workout():
    out = schedule_from_medications([], profile=_profile(workout_pref_window=None))
    assert not any(s["id"] == "workout:today" for s in out["scheduled"])
    assert not any(r["id"] == "workout:today" for r in out["rejected"])


def test_red_readiness_rejects_workout_as_rest():
    out = schedule_from_medications([], profile=_profile(), ctx_overrides={"readiness": RED})
    assert not any(s["id"] == "workout:today" for s in out["scheduled"])
    rej = [r for r in out["rejected"] if r["id"] == "workout:today"]
    assert len(rej) == 1
    assert "休息" in rej[0]["reason"] or "拉伸" in rej[0]["reason"]


def test_default_minutes_when_unset():
    out = schedule_from_medications([], profile=_profile(workout_target_minutes=None))
    w = [s for s in out["scheduled"] if s["id"] == "workout:today"]
    assert w and "40" in w[0]["title"]  # DEFAULT_WORKOUT_MINUTES
