"""
admin_wscla —— Weekly Safe Closed-Loop Actions 北极星看板 API.

WSCLA 定义:
  在指定时间窗口内, action_cards 满足全部条件的计数:
    user_decision = 'accepted'
    completed_at  IS NOT NULL
    graded_at     IN 时间窗口 (闭环完成时间)
    outcome       IN ('improved', 'unchanged')   # worsened 不算 "safe"

辅助指标:
  - suggestion_acceptance_rate: decided 中 accepted 占比
  - verification_rate:           accepted+completed 中 graded 占比
  - push_ctr:                    push_sent 中 push_clicked 占比
  - safety_fp_rate:              safety_alert 中 false_positive 占比

用法:
  GET /api/v1/admin/wscla            # 本周, 所有用户
  GET /api/v1/admin/wscla?user_id=1  # 本周, 用户 1
  GET /api/v1/admin/wscla?since=2026-05-04T00:00:00Z&until=2026-05-11T00:00:00Z
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.user import User

router = APIRouter()


def _week_start(now: datetime) -> datetime:
    """本周 (周一 00:00 UTC) 起点."""
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start


def _safe_ratio(numer: int, denom: int) -> Optional[float]:
    """分母为 0 返回 None 而不是 0.0, 避免前端误判 '率为 0' vs '无数据'."""
    if denom <= 0:
        return None
    return round(numer / denom, 4)


@router.get("")
def get_wscla_dashboard(
    user_id: Optional[int] = Query(None, description="过滤单用户; 省略则聚合全部"),
    since: Optional[datetime] = Query(None, description="窗口起点 ISO 8601, 默认本周一 00:00 UTC"),
    until: Optional[datetime] = Query(None, description="窗口终点 ISO 8601, 默认现在"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    返回 WSCLA 北极星 + 4 项辅助指标 + 明细.

    Phase 0 看板: 先不做跨周趋势, 只看当前窗口的一个截面.
    Phase 1+ 会加 series (日粒度 WSCLA 条形图).
    """
    now = datetime.now(timezone.utc)
    window_start = since or _week_start(now)
    window_end = until or now

    # --- 基础查询: 窗口内所有 action_cards (按 created_at 入池) ---
    base = db.query(ActionCard).filter(ActionCard.created_at < window_end)
    if user_id is not None:
        base = base.filter(ActionCard.user_id == user_id)

    # --- WSCLA: graded_at 在窗口内, 闭环完整, outcome safe ---
    wscla_q = base.filter(
        ActionCard.user_decision == "accepted",
        ActionCard.completed_at.isnot(None),
        ActionCard.graded_at >= window_start,
        ActionCard.graded_at <= window_end,
        ActionCard.outcome.in_(["improved", "unchanged"]),
    )
    wscla_count = wscla_q.count()

    # --- 辅助: decided 总数 & accepted 总数 (窗口内 decided_at) ---
    decided_in_window = base.filter(
        ActionCard.decided_at >= window_start,
        ActionCard.decided_at <= window_end,
        ActionCard.user_decision.isnot(None),
    )
    decided_count = decided_in_window.count()
    accepted_count = decided_in_window.filter(
        ActionCard.user_decision == "accepted"
    ).count()

    # --- 辅助: verification_rate = graded / (accepted + completed) ---
    # 分母: 已 accepted 且 completed 的卡 (在窗口内完成的)
    eligible_for_verify = base.filter(
        ActionCard.user_decision == "accepted",
        ActionCard.completed_at.isnot(None),
        ActionCard.completed_at >= window_start,
        ActionCard.completed_at <= window_end,
    )
    eligible_verify_count = eligible_for_verify.count()
    graded_count = eligible_for_verify.filter(ActionCard.graded_at.isnot(None)).count()

    # --- 辅助: push_ctr = push_clicked / push_sent (窗口内 push_sent_at) ---
    push_sent_q = base.filter(
        ActionCard.push_sent_at >= window_start,
        ActionCard.push_sent_at <= window_end,
    )
    push_sent_count = push_sent_q.count()
    push_clicked_count = push_sent_q.filter(
        ActionCard.push_clicked_at.isnot(None)
    ).count()

    # --- 辅助: safety_fp_rate = false_positive / safety_alert (窗口内 decided) ---
    safety_decided = base.filter(
        ActionCard.source_type == "safety_alert",
        ActionCard.decided_at >= window_start,
        ActionCard.decided_at <= window_end,
        ActionCard.user_decision.isnot(None),
    )
    safety_decided_count = safety_decided.count()
    safety_fp_count = safety_decided.filter(
        ActionCard.user_decision == "false_positive"
    ).count()

    # --- 分布: severity × source_type (窗口内创建的) ---
    window_q = base.filter(
        ActionCard.created_at >= window_start,
        ActionCard.created_at <= window_end,
    )

    by_severity_rows = (
        window_q.with_entities(ActionCard.severity, func.count(ActionCard.id))
        .group_by(ActionCard.severity)
        .all()
    )
    by_severity = {(s or "none"): c for s, c in by_severity_rows}

    by_source_rows = (
        window_q.with_entities(ActionCard.source_type, func.count(ActionCard.id))
        .group_by(ActionCard.source_type)
        .all()
    )
    by_source_type = {(s or "none"): c for s, c in by_source_rows}

    # --- 近 20 条 action_cards 列表 (看板预览) ---
    recent_cards_q = (
        base.order_by(ActionCard.created_at.desc())
        .limit(20)
        .all()
    )
    recent: List[Dict[str, Any]] = []
    for c in recent_cards_q:
        recent.append(
            {
                "id": c.id,
                "user_id": c.user_id,
                "title": c.title,
                "card_type": c.card_type,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "severity": c.severity,
                "status": c.status,
                "user_decision": c.user_decision,
                "outcome": c.outcome,
                "accuracy_score": c.accuracy_score,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "decided_at": c.decided_at.isoformat() if c.decided_at else None,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                "graded_at": c.graded_at.isoformat() if c.graded_at else None,
                "push_sent_at": c.push_sent_at.isoformat() if c.push_sent_at else None,
                "push_clicked_at": c.push_clicked_at.isoformat() if c.push_clicked_at else None,
            }
        )

    return {
        "window": {
            "since": window_start.isoformat(),
            "until": window_end.isoformat(),
            "user_id": user_id,
        },
        "metrics": {
            "wscla_count": wscla_count,
            "suggestion_acceptance_rate": _safe_ratio(accepted_count, decided_count),
            "verification_rate": _safe_ratio(graded_count, eligible_verify_count),
            "push_ctr": _safe_ratio(push_clicked_count, push_sent_count),
            "safety_fp_rate": _safe_ratio(safety_fp_count, safety_decided_count),
        },
        "counts": {
            "decided": decided_count,
            "accepted": accepted_count,
            "eligible_for_verify": eligible_verify_count,
            "graded": graded_count,
            "push_sent": push_sent_count,
            "push_clicked": push_clicked_count,
            "safety_decided": safety_decided_count,
            "safety_false_positive": safety_fp_count,
        },
        "by_severity": by_severity,
        "by_source_type": by_source_type,
        "recent_cards": recent,
    }
