"""Twin `sleep_deep` 分区: 真填出字段 + 失败可观测。

背景: 该分区静默死了 5 周(合并行 AttributeError → 整个 _fill_sleep_deep 被 except 吞)。
下游全是"静默 None", 所以没人发现:
  - physiological.sleep_deep_h_avg_14d / sleep_consistency_score 恒 None
  - `sources.add("sleep")` **永不执行** → source-aware prompting 认为无睡眠源
  - cross_review 的 deep_14d 冲突检测永不触发 (under-alarm)
  - formatter 的"深睡14d均"永不进 prompt

注: `_fill_sleep_deep` 是 build_twin 的**并行** filler, 跑在自开 `SessionLocal()` 的线程里,
看不到测试的内存 SQLite 会话 → 这里按仓库既有做法(见 test_twin_builder.py 对
`_fill_problem_red_lines` 的直调)直接调 filler 并传入测试 db。
"""
from datetime import date, timedelta

import pytest


def _user(db, name="sdp"):
    from app.models.user import User

    u = User(username=name, email=f"{name}@test.com", hashed_password="x", name=name)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _add_night(db, user_id, day_offset=0, **overrides):
    from app.models.daily_health import GarminData

    row = dict(
        user_id=user_id,
        record_date=date.today() - timedelta(days=day_offset),
        total_sleep_duration=420,
        deep_sleep_duration=72,   # 1.2h
        rem_sleep_duration=90,
        light_sleep_duration=250,
        awake_duration=8,
        sleep_score=80,
        hrv=48.0,
        hrv_status="balanced",
        body_battery_charged=65,
        data_source="garmin",
    )
    row.update(overrides)
    db.add(GarminData(**row))
    db.commit()


def _run_fill(db, user_id):
    from app.twin.builder import _fill_sleep_deep
    from app.twin.schema import HealthTwin, TwinMeta
    from datetime import datetime, UTC

    twin = HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(UTC)))
    sources = set()
    _fill_sleep_deep(db, user_id, twin, sources)
    return twin, sources


def test_sleep_deep_partition_fills_deep_hours(db):
    """sleep_deep_h_avg_14d 真被填出 (5 周来恒 None)。"""
    user = _user(db, "sdp1")
    for i in range(5):
        _add_night(db, user.id, day_offset=i)

    twin, _ = _run_fill(db, user.id)

    assert twin.physiological.sleep_deep_h_avg_14d == pytest.approx(1.2, abs=0.01)


def test_sleep_deep_adds_sleep_source(db):
    """`sources.add("sleep")` —— 这是 5 周来一直没执行的那行。

    source-aware prompting 据此判断"有没有睡眠源", 漏了会让 LLM 以为用户没戴睡眠设备。
    """
    user = _user(db, "sdp2")
    for i in range(5):
        _add_night(db, user.id, day_offset=i)

    _, sources = _run_fill(db, user.id)

    assert "sleep" in sources


def test_sleep_deep_partition_not_marked_failed_on_success(db):
    user = _user(db, "sdp3")
    for i in range(5):
        _add_night(db, user.id, day_offset=i)

    twin, _ = _run_fill(db, user.id)

    assert twin.meta.failed_partitions == []


def test_sleep_deep_failure_is_recorded_not_silent(db, monkeypatch):
    """分区评估失败必须在 Twin 上留痕, 与「无数据」可分辨。

    这是让"静默死 5 周"不再可能的那一条: 失败 → failed_partitions 有名字,
    而不是和"用户没睡眠数据"长得一模一样。
    """
    from app.services import sleep_analysis_service as svc_mod

    user = _user(db, "sdp4")
    for i in range(5):
        _add_night(db, user.id, day_offset=i)

    def _boom(self, db_, user_id_, days=14):
        raise AttributeError("'types.SimpleNamespace' object has no attribute 'hrv_status'")

    monkeypatch.setattr(svc_mod.SleepAnalysisService, "get_deep_analysis", _boom)

    twin, sources = _run_fill(db, user.id)

    # 仍降级(不上抛, 不打死整个 Twin)
    assert twin.physiological.sleep_deep_h_avg_14d is None
    # 但失败**可观测**, 且不冒充"有睡眠源"
    assert "sleep_deep" in twin.meta.failed_partitions
    assert "sleep" not in sources


def test_no_data_is_distinguishable_from_failure(db):
    """无数据 → 不进 failed_partitions(这才是"真的没数据")。"""
    user = _user(db, "sdp5")  # 一条睡眠记录都不加

    twin, sources = _run_fill(db, user.id)

    assert twin.physiological.sleep_deep_h_avg_14d is None
    assert twin.meta.failed_partitions == []
    assert "sleep" not in sources
