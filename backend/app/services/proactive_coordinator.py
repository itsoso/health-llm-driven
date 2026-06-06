# -*- coding: utf-8 -*-
"""主动触达协调 —— 跨 watcher 全局打扰预算(堵主动化泛化留下的回归风险)。

主动化已从 longevity_watch 泛化到 trajectory_watch(未来更多 *_watch),各自的
打扰预算是局部的;同一用户一周可能收到多条主动推送。本模块提供**跨所有主动 Agent
的全局预算 gate**:每个 watcher 推送前先问 can_notify_proactively,超预算则抑制
(仍埋点 notified=False)。longevity 周日 10:10 先跑,trajectory 10:25 看到前者已推 → 择优抑制。

预算来源 = agent_audit_log(已有埋点):近 7 天 agent_type∈*_watch 且 notified=True 的次数。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_audit_log import AgentAuditLog


def proactive_notifications_sent(db: Session, user_id: int, days: int = 7) -> int:
    """近 days 天,该用户已收到的主动推送数(跨所有 *_watch)。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == user_id,
            AgentAuditLog.action == "proactive_trigger",
            AgentAuditLog.created_at >= cutoff,
        )
        .all()
    )
    return sum(
        1 for r in rows
        if (r.agent_type or "").endswith("_watch")
        and (r.result_detail or {}).get("notified")
    )


def can_notify_proactively(db: Session, user_id: int) -> bool:
    """全局打扰预算 gate:近 7 天主动推送数 < 预算 → 允许。

    预算 settings.proactive_weekly_budget(默认 1);失败时放行(不因协调层崩坏阻断告知)。
    """
    budget = getattr(settings, "proactive_weekly_budget", 1)
    if budget <= 0:
        return True  # 0/负 = 不限(关闭协调)
    try:
        return proactive_notifications_sent(db, user_id) < budget
    except Exception:  # noqa: BLE001
        return True
