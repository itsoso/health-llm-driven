"""全天产出投影进首页脊柱 past(Reva 首页脊柱 · Increment 1)。

把两类「系统在固定时点替你跑了什么」投影成 past 时间线项,让用户能回溯
「为什么 7:30 收到简报 / 23:00 收到一条异常」:
  - 晨间简报(7:30):AgentMessage(role=assistant,会话标题「每日健康简报 · MM-DD」)
  - 异常检测(23:00):AnomalyAlert

硬边界(与 _outcome_items 同一道闸,past 投影**必须**也过这道闸):
  - **绝不**把 critical / medical-grade 告警渲染成首页时间线项(R4 / PRD §7)。
    AnomalyAlert.severity == "critical" → 排除(critical 走专门的安全告警通道,不进脊柱)。
  - 结果/洞察类项一律带 association_only=True(相关非因果,不下因果断言)。

只读投影,无副作用。任一子源失败只记 warning,不拖垮 past(简报/异常是增强回溯,
不是主路径——主路径的今日观测仍由 today_timeline_service.build_timeline 产)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 首页脊柱绝不可见的 severity(与 _outcome_items 的 critical/high 排除同源,
# anomaly 只有 info/warning/critical 三档,critical = medical-grade 边界)。
_HOME_HIDDEN_SEVERITY = {"critical"}


def briefing_past_items(db: Session, user_id: int, on_date: date) -> List[Dict[str, Any]]:
    """当日晨间简报 → past 时间线项(kind=insight,association_only)。"""
    try:
        from app.models.agent_conversation import AgentConversation, AgentMessage
        from app.tasks.notifications import _briefing_title_for

        title = _briefing_title_for(on_date)
        conv = (
            db.query(AgentConversation)
            .filter(
                AgentConversation.user_id == user_id,
                AgentConversation.title == title,
            )
            .first()
        )
        if conv is None:
            return []
        msg = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.conversation_id == conv.id,
                AgentMessage.role == "assistant",
            )
            .order_by(AgentMessage.created_at.desc())
            .first()
        )
        if msg is None:
            return []
    except Exception as e:  # noqa: BLE001 — 回溯增强项,失败降级不拖垮 past
        logger.warning("[timeline-past] briefing load failed for user=%s: %s", user_id, e)
        return []

    occurred = msg.created_at or datetime.combine(on_date, datetime.min.time())
    return [{
        "id": f"briefing_{msg.id}",
        "kind": "insight",
        "time_window": "morning",
        "title": "晨间健康简报",
        "subtitle": _excerpt(msg.content, 60),
        "icon": "sunny-outline",
        "color": "#FF9500",
        "status": None,
        "priority": 0,
        "can_complete": False,
        "complete_ref": None,
        "deep_link": f"chat?conversation_id={conv.id}",
        "severity": None,
        "occurred_at": occurred,
        # 简报是叙事性洞察:相关非因果,不下处方/因果断言。
        "proof": {"association_only": True},
    }]


def anomaly_past_items(db: Session, user_id: int, on_date: date) -> List[Dict[str, Any]]:
    """当日异常检测产出 → past 时间线项(kind=insight)。

    **排除 critical**(绝不把 critical/medical-grade 告警当首页脊柱项;走安全通道)。
    """
    try:
        from app.models.anomaly_alert import AnomalyAlert

        rows = (
            db.query(AnomalyAlert)
            .filter(
                AnomalyAlert.user_id == user_id,
                AnomalyAlert.detection_date == on_date,
                AnomalyAlert.is_suppressed.is_(False),
            )
            .order_by(AnomalyAlert.id.desc())
            .all()
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[timeline-past] anomaly load failed for user=%s: %s", user_id, e)
        return []

    items: List[Dict[str, Any]] = []
    for a in rows:
        # 硬闸:critical/medical-grade 不进首页脊柱(与 _outcome_items 同一道排除)。
        if (a.severity or "").lower() in _HOME_HIDDEN_SEVERITY:
            continue
        color = "#FF9500" if a.severity == "warning" else "#8E8E93"
        occurred = datetime.combine(
            a.detection_date, datetime.min.time().replace(hour=23)
        )
        items.append({
            "id": f"anomaly_{a.id}",
            "kind": "insight",
            "time_window": "bedtime",
            "title": a.message[:40] if a.message else "健康指标提示",
            "subtitle": _metric_subtitle(a),
            "icon": "pulse-outline",
            "color": color,
            "status": None,
            "priority": 0,
            "can_complete": False,
            "complete_ref": None,
            "deep_link": f"trace/anomaly_{a.id}",
            "severity": a.severity,
            "occurred_at": occurred,
            # 异常 = 偏离基线的观测关联,非因果归因。
            "proof": {"association_only": True},
        })
    return items


def _metric_subtitle(a) -> str:
    metric = a.metric_name or ""
    if a.current_value is not None:
        return f"{metric} {a.current_value}".strip()
    return metric or ""


def _excerpt(text: str | None, n: int) -> str:
    if not text:
        return ""
    flat = " ".join(str(text).split())
    return flat[:n] + ("…" if len(flat) > n else "")
