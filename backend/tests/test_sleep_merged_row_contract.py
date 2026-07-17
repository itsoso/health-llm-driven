"""合并行(SimpleNamespace) × sleep_analysis_service 的属性契约。

生产实锤(2026-07): `[twin] sleep_deep 失败: 'types.SimpleNamespace' object has no
attribute 'hrv_status'` 24h 内 698 次, `GET /api/v1/sleep/deep-analysis` 直接 500。

根因: `merged_daily_rows` 返回的合并行只暴露 `METRIC_SOURCE_PRIORITY` 的 key +
`require_metrics`/`extra_metrics`。`hrv_status` / `sleep_start_time` 是 GarminData
的真列但不在优先级表里 → 属性不存在 → AttributeError。引入于 380dc6ab5(多源合并),
把直查 GarminData ORM(有全部列)换成了只暴露优先级表子集的 SimpleNamespace。

这里的契约测试**从源码解析**属性访问点(而非硬编清单), 所以下次有人在本 service 里
新读一个优先级表外的字段却忘了加进 `extra_metrics` 时, 这条会直接红 —— 而不是等到
生产 twin 里静默死 5 周。
"""
import ast
import inspect
from datetime import date, timedelta

import pytest

from app.services import sleep_analysis_service as svc_mod


def _attrs_read_on_merged_rows() -> set:
    """AST 扫出本 service 里对合并行的属性访问名。

    覆盖两种写法: `r.<attr>` / `<x> for r in records` 里的 r, 以及 `records[0].<attr>`。
    (`getattr(r, _field[s])` 是动态访问, AST 抓不到; `_field` 的值全在优先级表内,
    由下面的 e2e 测试兜底 —— 真跑一遍, 缺属性就 AttributeError。)
    """
    tree = ast.parse(inspect.getsource(svc_mod))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        val = node.value
        # r.<attr>
        if isinstance(val, ast.Name) and val.id == "r":
            names.add(node.attr)
        # records[0].<attr>
        elif (
            isinstance(val, ast.Subscript)
            and isinstance(val.value, ast.Name)
            and val.value.id == "records"
        ):
            names.add(node.attr)
    return names


def _user(db, name="slpc"):
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
        deep_sleep_duration=72,
        rem_sleep_duration=90,
        light_sleep_duration=250,
        awake_duration=8,
        sleep_score=80,
        hrv=48.0,
        hrv_7day_avg=50.0,
        hrv_status="balanced",
        body_battery_charged=65,
        data_source="garmin",
    )
    row.update(overrides)
    db.add(GarminData(**row))
    db.commit()


def test_ast_scan_actually_finds_the_known_landmines():
    """先自检扫描器有效 —— 否则下面的契约测试可能是「扫出空集恒绿」的假护栏。"""
    attrs = _attrs_read_on_merged_rows()
    # 这两个就是炸生产的字段, 必须被扫到
    assert "hrv_status" in attrs
    assert "sleep_start_time" in attrs
    # 优先级表内的常规字段也应扫到
    assert "total_sleep_duration" in attrs
    assert "deep_sleep_duration" in attrs


def test_merged_row_exposes_every_attribute_the_service_reads(db):
    """合并行必须暴露 service 读的**全部**属性 —— 修一个漏一个的话下周又炸。"""
    user = _user(db, "slpc1")
    _add_night(db, user.id)

    rows = svc_mod._fetch_sleep_data(db, user.id, 14)
    assert rows, "fixture 应至少产出一行合并行"
    row = rows[0]

    missing = sorted(a for a in _attrs_read_on_merged_rows() if not hasattr(row, a))
    assert not missing, (
        f"sleep_analysis_service 读了合并行上不存在的属性 {missing} —— "
        f"把它们加进 _fetch_sleep_data 的 extra_metrics(或 METRIC_SOURCE_PRIORITY)。"
    )


def test_get_deep_analysis_runs_end_to_end_without_attribute_error(db):
    """真跑一遍: 这是 698 次/24h 生产异常的直接回归锁(含 getattr 动态访问路径)。"""
    user = _user(db, "slpc2")
    for i in range(5):
        _add_night(db, user.id, day_offset=i)

    out = svc_mod.SleepAnalysisService().get_deep_analysis(db, user.id, days=14)

    assert out["status"] == "success"
    assert out["hrv_recovery"]["hrv_status"] == "balanced"


def test_deep_hours_emitted_in_hours_not_percent(db):
    """builder 读 architecture['deep_hours'] 填 sleep_deep_h_avg_14d(单位=小时)。"""
    user = _user(db, "slpc3")
    for i in range(5):
        _add_night(db, user.id, day_offset=i, deep_sleep_duration=72)  # 72min = 1.2h

    arch = svc_mod.SleepAnalysisService().get_deep_analysis(db, user.id, days=14)["architecture"]

    assert arch["deep_hours"] == pytest.approx(1.2, abs=0.01)
    # 百分比字段仍在(未破坏既有契约), 且与 hours 不是同一个数
    assert arch["deep_pct"] == pytest.approx(72 / 420 * 100, abs=0.1)


def test_deep_hours_is_none_not_zero_when_no_deep_data(db):
    """无深睡数据 → None(未知), 不是 0.0。

    0.0 会被 cross_review 的 `deep_14d < 0.8` 当成「深睡严重不足」触发假冲突 ——
    把「不知道」讲成「很差」= 编造。
    """
    user = _user(db, "slpc4")
    for i in range(5):
        _add_night(db, user.id, day_offset=i, deep_sleep_duration=None)

    arch = svc_mod.SleepAnalysisService().get_deep_analysis(db, user.id, days=14)["architecture"]

    assert arch["deep_hours"] is None
