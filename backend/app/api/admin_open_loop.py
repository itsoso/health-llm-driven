"""Admin Open-Loop 看板 API (2026-05-13).

把 OpenLoopHistory 聚合给 admin 看:
  - 7 天 / 30 天总推送数 + 成功率
  - 按 kind 分布 (lab_overdue / action_card_due / sync_stale / trend_anomaly / plan_drift)
  - 用户反馈分布 (opened / dismissed / done / no_action)
  - 接受率 = (opened + done) / total
  - top failure kinds — 哪类信号用户最常 dismiss

Phase 1 Protection 闭环要看的就是这页:
  "AI 主动盯了多少, 真到达多少, 被接受多少, 哪类信号噪声最大."
没这个看板, "主动循环" 就只是 Celery 跑了, 没人知道效果.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.open_loop_history import OpenLoopHistory
from app.models.user import User

router = APIRouter()


@router.get("/stats", summary="Open-Loop 主动推送看板")
def open_loop_stats(
    days: int = Query(7, ge=1, le=90),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """聚合最近 N 天的 OpenLoopHistory.

    返回字段:
      total / delivered_ok / delivery_rate
      acceptance_rate = (opened + done) / total
      by_kind = [{kind, count, ok, opened, dismissed, done, acceptance_rate}]
      by_action = {opened, dismissed, done, snooze_7d, not_interested, no_action}
      by_day = [{date, count, ok}]   过去 N 天每天推送数
      active_users = unique user 数
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.query(OpenLoopHistory).filter(OpenLoopHistory.sent_at >= since).all()

    total = len(rows)
    delivered_ok = sum(1 for r in rows if r.delivery_ok)
    delivery_rate = round(delivered_ok / total, 3) if total else 0.0

    # 接受 = opened or done; 拒绝 = dismissed/not_interested; 中性 = snooze_7d/None
    accept_set = {"opened", "done"}
    accepted = sum(1 for r in rows if (r.user_action or "") in accept_set)
    acceptance_rate = round(accepted / total, 3) if total else 0.0

    # 按 kind 聚合
    kind_buckets: dict = defaultdict(lambda: {
        "count": 0, "ok": 0, "opened": 0, "dismissed": 0,
        "done": 0, "snooze_7d": 0, "not_interested": 0, "no_action": 0,
    })
    for r in rows:
        b = kind_buckets[r.kind]
        b["count"] += 1
        if r.delivery_ok:
            b["ok"] += 1
        a = r.user_action or "no_action"
        if a in b:
            b[a] += 1
        else:
            b["no_action"] += 1

    by_kind = []
    for k, b in kind_buckets.items():
        accepted_k = b["opened"] + b["done"]
        by_kind.append({
            "kind": k,
            **b,
            "acceptance_rate": round(accepted_k / b["count"], 3) if b["count"] else 0.0,
        })
    by_kind.sort(key=lambda x: x["count"], reverse=True)

    # 按 action 全局
    by_action: dict = defaultdict(int)
    for r in rows:
        by_action[r.user_action or "no_action"] += 1

    # 按天 (UTC date)
    day_buckets: dict = defaultdict(lambda: {"count": 0, "ok": 0})
    for r in rows:
        d = r.sent_at.date().isoformat()
        day_buckets[d]["count"] += 1
        if r.delivery_ok:
            day_buckets[d]["ok"] += 1
    by_day = [{"date": d, **v} for d, v in sorted(day_buckets.items())]

    # 活跃用户
    active_users = len({r.user_id for r in rows})

    return {
        "window_days": days,
        "total": total,
        "delivered_ok": delivered_ok,
        "delivery_rate": delivery_rate,
        "acceptance_rate": acceptance_rate,
        "active_users": active_users,
        "by_kind": by_kind,
        "by_action": dict(by_action),
        "by_day": by_day,
    }


@router.get("/recent", summary="最近 N 条推送明细 (admin debug)")
def open_loop_recent(
    limit: int = Query(50, ge=1, le=500),
    kind: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """看具体推送内容, debug 高 dismiss 率的 kind."""
    q = db.query(OpenLoopHistory).order_by(OpenLoopHistory.sent_at.desc())
    if kind:
        q = q.filter(OpenLoopHistory.kind == kind)
    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "kind": r.kind,
            "signal_key": r.signal_key,
            "score": r.score,
            "title": r.title,
            "body": r.body,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "delivery_ok": bool(r.delivery_ok),
            "delivery_error": r.delivery_error,
            "user_action": r.user_action,
            "action_at": r.action_at.isoformat() if r.action_at else None,
        }
        for r in rows
    ]
