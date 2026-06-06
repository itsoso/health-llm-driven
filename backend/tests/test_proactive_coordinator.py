# -*- coding: utf-8 -*-
"""主动触达全局协调(P0,堵主动化泛化的回归风险)回归。

钉:跨 *_watch 统计 notified;全局预算 gate;notified=False 不计;非 watcher 不计;
budget=0 = 不限。
"""
from app.services.proactive_coordinator import (
    can_notify_proactively,
    proactive_notifications_sent,
)


def _audit(db, user_id, agent_type, notified):
    from app.models.agent_audit_log import AgentAuditLog
    db.add(AgentAuditLog(user_id=user_id, agent_type=agent_type, action="proactive_trigger",
                         result_detail={"notified": notified}))
    db.commit()


def test_counts_across_watchers_notified_only(db):
    _audit(db, 1, "longevity_watch", True)
    _audit(db, 1, "trajectory_watch", True)
    _audit(db, 1, "longevity_watch", False)   # 未推 → 不计
    _audit(db, 1, "orchestrator", True)       # 非 *_watch → 不计
    assert proactive_notifications_sent(db, 1) == 2


def test_gate_blocks_over_budget(db):
    # 默认预算 1:0 条 → 允许
    assert can_notify_proactively(db, 1) is True
    _audit(db, 1, "longevity_watch", True)    # 已推 1 条
    assert can_notify_proactively(db, 1) is False   # 达预算 → 抑制
    # 另一用户不受影响
    assert can_notify_proactively(db, 2) is True


def test_budget_zero_means_unlimited(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "proactive_weekly_budget", 0)
    _audit(db, 1, "longevity_watch", True)
    _audit(db, 1, "trajectory_watch", True)
    assert can_notify_proactively(db, 1) is True   # 0 = 不限


def test_higher_budget_allows_more(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "proactive_weekly_budget", 2)
    _audit(db, 1, "longevity_watch", True)
    assert can_notify_proactively(db, 1) is True    # 1 < 2
    _audit(db, 1, "trajectory_watch", True)
    assert can_notify_proactively(db, 1) is False   # 2 == 2
