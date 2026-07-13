# -*- coding: utf-8 -*-
"""今日时间线:驱动标记 + 工作日程合并 + 日程感知 nudge(P1 后端)。

钉(对应设计 §测试计划 1-5):
① driver 各类派生(event_triggered→event;协议→plan;advisory→event;歧义→plan)
② 工作块进/不进 timeline + 绝无标题(隐私)
③ 忙碌窗 P1/P2 静默、**P0 穿透**(安全重点对抗用例)
④ 隐私:工作块序列化无 title/encrypted_title/location;nudge 门不取标题
⑤ user_id 隔离 + fail-soft(日历查询抛错 → nudge 当不忙、timeline 无 work,不崩)

网络/日历全部 patch,绝不真连 CalDAV。
"""
import json
from datetime import datetime, timedelta, timezone as _tz

import pytest

import app.services.proactive_coordinator as pc
import app.services.today_timeline_service as tts
from app.services.proactive_coordinator import can_notify_proactively
from app.services.today_timeline_service import (
    _derive_driver,
    _work_items,
    build_today_spine,
)

_BJ = _tz(timedelta(hours=8))


# ── ① driver 派生 ──────────────────────────────────────────────────────

def test_driver_event_triggered_protocol_is_event():
    item = {"type": "diet", "cadence": "event_triggered",
            "source": {"object_type": "health_protocol", "object_id": 1}}
    assert _derive_driver(item) == "event_driven"


def test_driver_advisory_is_event():
    # 训练决策灯 / 数据质量 / 自纠偏 / 基线漂移 = 信号触发的建议项
    for itype in ("training", "data_quality", "correction", "baseline_deviation"):
        item = {"type": itype, "status": "info",
                "source": {"object_type": "training_decision", "object_id": 1}}
        assert _derive_driver(item) == "event_driven", itype


def test_driver_standing_protocol_is_plan():
    # 常驻承诺协议(用药/补剂/饮水,日/周/月 cadence)→ plan
    for cadence in ("daily", "weekly", "monthly", "quarterly", "annual"):
        item = {"type": "medication", "cadence": cadence,
                "source": {"object_type": "health_protocol", "object_id": 1}}
        assert _derive_driver(item) == "plan_driven", cadence


def test_driver_checkup_is_plan():
    # 复查 = 预定承诺
    item = {"type": "checkup", "status": "due",
            "source": {"object_type": "health_problem", "object_id": 1}}
    assert _derive_driver(item) == "plan_driven"


def test_driver_ambiguous_protocol_defaults_to_plan():
    # 无 cadence、有常驻 source object 的协议 → 歧义偏 plan_driven(设计 §契约1)
    item = {"type": "medication", "cadence": None,
            "source": {"object_type": "health_protocol", "object_id": 1}}
    assert _derive_driver(item) == "plan_driven"


def test_map_agenda_item_carries_driver():
    item = {"type": "medication", "cadence": "daily", "title": "二甲双胍",
            "status": "pending",
            "source": {"object_type": "health_protocol", "object_id": 7}}
    out = tts._map_agenda_item(item)
    assert out["driver"] == "plan_driven"


def test_observation_and_outcome_have_driver(db, auth_user_and_headers):
    # observation / outcome item 也带 driver(纯展示)
    class _Ev:
        id = "workout_1"
        title = "跑步"
        subtitle = "5km"
        icon = "walk-outline"
        color = "#000"
        deep_link = None
        severity = None
    obs = tts._map_observation(_Ev())
    assert "driver" in obs and obs["driver"] == "event_driven"


# ── ② / ④ 工作块进 timeline + 隐私无标题 ──────────────────────────────

def test_work_items_from_busy_blocks_no_title(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(
        tts, "today_busy_blocks",
        lambda d, uid: [("09:30", "10:30"), ("14:00", "15:00")],
    )
    items = _work_items(db, user.id)
    assert len(items) == 2
    for it in items:
        assert it["kind"] == "work"
        assert it["driver"] == "plan_driven"
        assert it["can_complete"] is False
        assert it["status"] is None
        # 隐私:绝无标题/位置/原文键
        assert "encrypted_title" not in it
        assert "location" not in it
        # 序列化整体也不含任何敏感关键字
        blob = json.dumps(it, ensure_ascii=False)
        for forbidden in ("encrypted", "location", "attendee", "uid", "description"):
            assert forbidden not in blob.lower()
    # 09:30 → morning,14:00 → afternoon
    assert items[0]["time_window"] == "morning"
    assert items[1]["time_window"] == "afternoon"
    # 时长进标题(粗粒度,不含日历标题)
    assert "60min" in items[0]["title"] or "忙碌" in items[0]["title"]


def test_work_items_no_credentials_empty(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    # 无 CalendarEvent → today_busy_blocks 返回 [] → 无 work item
    assert _work_items(db, user.id) == []


def test_work_items_fail_soft_on_error(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers

    def _boom(d, uid):
        raise RuntimeError("caldav down")

    monkeypatch.setattr(tts, "today_busy_blocks", _boom)
    # fail-soft:日历坏 → 无 work item,不崩
    assert _work_items(db, user.id) == []


def test_build_spine_includes_work_item(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(
        tts, "today_busy_blocks",
        lambda d, uid: [("11:00", "12:00")],
    )
    spine = build_today_spine(db, user.id)
    works = [it for it in spine["items"] if it["kind"] == "work"]
    assert len(works) == 1
    assert works[0]["driver"] == "plan_driven"
    # 隐私:整条脊柱序列化无标题泄露通道
    blob = json.dumps(spine, ensure_ascii=False)
    assert "encrypted_title" not in blob


def test_build_spine_fail_soft_no_work_when_calendar_errors(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers

    def _boom(d, uid):
        raise RuntimeError("caldav down")

    monkeypatch.setattr(tts, "today_busy_blocks", _boom)
    spine = build_today_spine(db, user.id)  # 不崩
    assert all(it["kind"] != "work" for it in spine["items"])


# ── ③ nudge 门:忙碌窗 P1/P2 静默、P0 穿透 ─────────────────────────────

def _set_busy(monkeypatch, busy: bool):
    monkeypatch.setattr(pc, "_in_busy_window", lambda db, uid: busy)


def test_p1_silenced_in_busy_window(db, monkeypatch):
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: False)
    monkeypatch.setattr(pc, "_in_morning_sleep_floor", lambda db, uid: False)
    _set_busy(monkeypatch, True)
    assert can_notify_proactively(db, 1, tier="P1") is False


def test_p2_silenced_in_busy_window(db, monkeypatch):
    # P2 本就永不推(忙不忙都 False)
    _set_busy(monkeypatch, True)
    assert can_notify_proactively(db, 1, tier="P2") is False


def test_p0_punches_through_busy_window(db, monkeypatch):
    """安全重点对抗用例:不在睡眠保护窗时,P0 安全告警穿透忙碌窗。"""
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: True)
    monkeypatch.setattr(pc, "_in_morning_sleep_floor", lambda db, uid: False)
    _set_busy(monkeypatch, True)
    assert can_notify_proactively(db, 1, tier="P0") is True


def test_p1_normal_when_not_busy(db, monkeypatch):
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: False)
    monkeypatch.setattr(pc, "_in_morning_sleep_floor", lambda db, uid: False)
    _set_busy(monkeypatch, False)
    assert can_notify_proactively(db, 1, tier="P1") is True


# ── ⑤ _in_busy_window 真逻辑 + user_id 隔离 + fail-soft ────────────────

def test_in_busy_window_true_when_now_inside(db, monkeypatch):
    now = datetime.now(_BJ)
    start = (now - timedelta(minutes=30)).strftime("%H:%M")
    end = (now + timedelta(minutes=30)).strftime("%H:%M")
    monkeypatch.setattr(pc, "today_busy_blocks", lambda d, uid: [(start, end)])
    assert pc._in_busy_window(db, 1) is True


def test_in_busy_window_false_when_now_outside(db, monkeypatch):
    now = datetime.now(_BJ)
    start = (now + timedelta(hours=2)).strftime("%H:%M")
    end = (now + timedelta(hours=3)).strftime("%H:%M")
    monkeypatch.setattr(pc, "today_busy_blocks", lambda d, uid: [(start, end)])
    assert pc._in_busy_window(db, 1) is False


def test_in_busy_window_false_when_no_blocks(db, monkeypatch):
    monkeypatch.setattr(pc, "today_busy_blocks", lambda d, uid: [])
    assert pc._in_busy_window(db, 1) is False


def test_in_busy_window_handles_midnight_wrap(db, monkeypatch):
    """跨午夜忙碌块(end<start,如 23:00–00:30 会议 / 22:00–07:00 睡眠 DND)在午夜两侧都算忙。

    钉死 get_china_now(不靠墙钟)→ 确定性。修复前 `_in_busy_window` 的单条 `start<=now<end`
    对 end<start 恒 False → 跨午夜块永不静默(真 bug),且让 23:30–00:29 北京时刻构造跨午夜窗的
    既有 busy-window 测试必红(CI 在 23:40 实锤)。还原 wrap 分支 → 本测试转红。
    """
    monkeypatch.setattr(pc, "today_busy_blocks", lambda d, uid: [("23:00", "00:30")])

    def _at(hhmm):
        h, m = (int(x) for x in hhmm.split(":"))
        monkeypatch.setattr(
            pc, "get_china_now", lambda: datetime(2026, 6, 26, h, m, tzinfo=_BJ)
        )

    _at("23:40")
    assert pc._in_busy_window(db, 1) is True, "午夜前侧 [start,24:00) 应算忙"
    _at("00:15")
    assert pc._in_busy_window(db, 1) is True, "午夜后侧 [00:00,end) 应算忙"
    _at("12:00")
    assert pc._in_busy_window(db, 1) is False, "窗外不算忙"


def test_in_busy_window_fail_soft_on_error(db, monkeypatch):
    def _boom(d, uid):
        raise RuntimeError("caldav down")

    monkeypatch.setattr(pc, "today_busy_blocks", _boom)
    # fail-soft:日历坏 → 当「不忙」(别把所有 nudge 静默),不崩
    assert pc._in_busy_window(db, 1) is False


def test_busy_window_user_id_isolation(db, monkeypatch):
    """user 1 忙、user 2 不忙:nudge 门按各自 user_id。"""
    def _blocks(d, uid):
        now = datetime.now(_BJ)
        if uid == 1:
            return [((now - timedelta(minutes=10)).strftime("%H:%M"),
                     (now + timedelta(minutes=10)).strftime("%H:%M"))]
        return []

    monkeypatch.setattr(pc, "today_busy_blocks", _blocks)
    assert pc._in_busy_window(db, 1) is True
    assert pc._in_busy_window(db, 2) is False
