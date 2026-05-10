"""Live Run HR replay — 离线工具函数 + replay 逻辑."""
import json
from datetime import datetime, date, timedelta

import pytest

from app.tasks.live_run_hr_replay import (
    _estimate_max_hr,
    _replay_rules,
    _parse_hr_series,
    _find_matching_workout,
)
from app.models.user import User
from app.models.daily_health import WorkoutRecord
from app.models.live_run import LiveRunSession


def _mk_user(birth_offset_years: int | None = 35) -> User:
    u = User(username="x", email="x@x", hashed_password="x", name="x")
    if birth_offset_years is not None:
        u.birth_date = date(date.today().year - birth_offset_years, 1, 1)
    return u


def test_estimate_max_hr_with_age():
    u = _mk_user(35)
    assert _estimate_max_hr(u) == 185


def test_estimate_max_hr_no_birth():
    u = _mk_user(None)
    assert _estimate_max_hr(u) == 185


def test_replay_no_series():
    out = _replay_rules([], datetime.utcnow(), 185, 30)
    assert out == ([], {})


def test_replay_z4_sustained_triggers_r2():
    # 11 分钟 Z5, 心率 170 (>= 0.85 * 185 = 157.25)
    series = [{"time": i * 30, "hr": 170} for i in range(22)]   # 0..630s
    events, stats = _replay_rules(series, datetime(2026, 5, 10, 8, 0), 185, 60)
    r2 = [e for e in events if e["rule_id"] == "hr_zone_overload"]
    assert len(r2) == 1   # 一段连续不重复触发
    assert stats["max_hr"] == 170
    assert stats["z4_plus_minutes"] >= 10.0


def test_replay_z4_short_no_r2():
    # 4 分钟 Z4, 不到 5min 阈值
    series = [{"time": i * 30, "hr": 165} for i in range(8)]
    events, _ = _replay_rules(series, datetime.utcnow(), 185, 60)
    assert all(e["rule_id"] != "hr_zone_overload" for e in events)


def test_replay_total_load_triggers_r3():
    # 50min Z4 → 远超 30min 上限
    series = [{"time": i * 30, "hr": 170} for i in range(100)]
    events, _ = _replay_rules(series, datetime.utcnow(), 185, 30)
    r3 = [e for e in events if e["rule_id"] == "total_load_exceeded"]
    assert len(r3) == 1


def test_parse_hr_series_string_json():
    w = WorkoutRecord(
        user_id=1,
        heart_rate_data=json.dumps([{"time": 0, "hr": 120}, {"time": 30, "hr": 150}]),
    )
    out = _parse_hr_series(w)
    assert len(out) == 2
    assert out[0]["hr"] == 120


def test_parse_hr_series_empty():
    w = WorkoutRecord(user_id=1, heart_rate_data=None)
    assert _parse_hr_series(w) == []


def test_find_matching_workout(db):
    user = User(username="r", email="r@x", hashed_password="x", name="r", is_active=True, is_approved=True)
    db.add(user); db.commit(); db.refresh(user)

    started = datetime(2026, 5, 10, 8, 0, 0)
    w = WorkoutRecord(
        user_id=user.id, workout_type="running",
        workout_date=started.date(),
        start_time=started + timedelta(minutes=2),
        duration_seconds=1800, source="garmin", external_id="g1",
    )
    db.add(w); db.commit()

    found = _find_matching_workout(db, user.id, started, 1800)
    assert found is not None
    assert found.workout_type == "running"


def test_find_matching_workout_out_of_window(db):
    user = User(username="r2", email="r2@x", hashed_password="x", name="r", is_active=True, is_approved=True)
    db.add(user); db.commit(); db.refresh(user)

    started = datetime(2026, 5, 10, 8, 0, 0)
    w = WorkoutRecord(
        user_id=user.id, workout_type="running",
        workout_date=started.date(),
        start_time=started + timedelta(minutes=30),  # 远超 ±15min
        duration_seconds=1800, source="garmin", external_id="g2",
    )
    db.add(w); db.commit()

    assert _find_matching_workout(db, user.id, started, 1800) is None
