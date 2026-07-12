# -*- coding: utf-8 -*-
"""主动触达三级打扰预算(R15)回归。

钉:P2 永不推;P1 静默时段不推 + 受全局周上限;P0 穿透静默 + 受 P0 周上限 + 全局封顶;
旧埋点无 tier 记为 P1;tier 计数互不串。
"""
from datetime import datetime

import pytest

import app.services.proactive_coordinator as pc
from app.models.notification import UserNotificationSetting
from app.services.proactive_coordinator import (
    can_notify_proactively,
    proactive_notifications_sent,
)


def _audit(db, user_id, agent_type, notified, tier=None):
    from app.models.agent_audit_log import AgentAuditLog
    detail = {"notified": notified}
    if tier is not None:
        detail["tier"] = tier
    db.add(AgentAuditLog(user_id=user_id, agent_type=agent_type, action="proactive_trigger",
                         result_detail=detail))
    db.commit()


@pytest.fixture
def awake(monkeypatch):
    """把当前固定为非静默时段,隔离 P1 测试对挂钟时间的依赖。"""
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: False)


def test_p2_never_pushed(db):
    assert can_notify_proactively(db, 1, tier="P2") is False


def test_p1_allowed_when_awake_and_under_global(db, awake):
    assert can_notify_proactively(db, 1, tier="P1") is True


def test_p1_blocked_in_quiet_hours(db, monkeypatch):
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: True)
    assert can_notify_proactively(db, 1, tier="P1") is False


def test_morning_sleep_floor_overrides_user_quiet_end_before_9am(db, monkeypatch):
    """08:30 仍算静默,即使老用户偏好保存的是 08:00 结束。"""
    db.add(UserNotificationSetting(
        user_id=1,
        enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
    ))
    db.commit()
    monkeypatch.setattr(
        pc,
        "get_user_now",
        lambda _db, _user_id: datetime(2026, 5, 12, 8, 30, 0),
    )

    assert pc._in_quiet_hours(db, 1) is True
    assert can_notify_proactively(db, 1, tier="P1") is False


def test_p1_blocked_at_global_cap(db, awake, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "proactive_global_weekly_budget", 3)
    for _ in range(3):
        _audit(db, 1, "trajectory_watch", True)        # 旧埋点无 tier → 记为 P1
    assert can_notify_proactively(db, 1, tier="P1") is False
    assert can_notify_proactively(db, 1, tier="P0") is False  # 全局封顶含 P0


def test_p0_punches_through_quiet_hours(db, monkeypatch):
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: True)
    assert can_notify_proactively(db, 1, tier="P0") is True   # P0 穿透静默


def test_p0_own_weekly_cap(db, monkeypatch):
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: True)
    from app.config import settings
    monkeypatch.setattr(settings, "proactive_p0_weekly_budget", 2)
    _audit(db, 1, "trajectory_watch", True, tier="P0")
    _audit(db, 1, "trajectory_watch", True, tier="P0")
    assert can_notify_proactively(db, 1, tier="P0") is False  # 2 == P0 上限


def test_tier_counting_isolated(db):
    _audit(db, 1, "longevity_watch", True, tier="P0")
    _audit(db, 1, "trajectory_watch", True)            # 无 tier → P1
    _audit(db, 1, "longevity_watch", False, tier="P0")  # 未推 → 不计
    assert proactive_notifications_sent(db, 1) == 2          # 全部 notified
    assert proactive_notifications_sent(db, 1, tier="P0") == 1
    assert proactive_notifications_sent(db, 1, tier="P1") == 1


def test_proactive_decision_exposes_reason_action_and_fallback(db, monkeypatch):
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: True)
    decision = pc.proactive_notification_decision(
        db,
        1,
        tier="P1",
        reason="睡前流程已到点",
        action="延后提醒",
        fallback_surface="mobile",
    )

    assert decision["allowed"] is False
    assert decision["blocked_reason"] == "quiet_hours"
    assert decision["contract"]["reason"] == "睡前流程已到点"
    assert decision["contract"]["action"] == "延后提醒"
    assert decision["contract"]["fallback_surface"] == "mobile"
    assert decision["contract_complete"] is True


def test_p2_decision_does_not_probe_quiet_or_busy_windows(db, monkeypatch):
    monkeypatch.setattr(
        pc,
        "_in_quiet_hours",
        lambda db, uid: (_ for _ in ()).throw(AssertionError("quiet checked")),
    )
    monkeypatch.setattr(
        pc,
        "_in_busy_window",
        lambda db, uid: (_ for _ in ()).throw(AssertionError("busy checked")),
    )

    decision = pc.proactive_notification_decision(db, 1, tier="P2")

    assert decision["allowed"] is False
    assert decision["blocked_reason"] == "log_only"
