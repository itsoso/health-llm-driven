"""Open-Loop Manager API — 历史查询 + 用户反馈 (snooze / not_interested / done)."""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.open_loop_history import OpenLoopHistory
from app.models.user import User

router = APIRouter(prefix="/open-loop", tags=["open-loop"])


class OpenLoopFeedback(BaseModel):
    action: Literal["opened", "dismissed", "not_interested", "snooze_7d", "done"]
    snooze_days: Optional[int] = Field(None, ge=1, le=30,
        description="snooze_7d 时可覆盖 (默认 7), 范围 1-30")


@router.get("/history", summary="近 N 天的推送历史 + 反馈")
def list_history(
    days: int = Query(14, ge=1, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.query(OpenLoopHistory).filter(
        OpenLoopHistory.user_id == current_user.id,
        OpenLoopHistory.sent_at >= since,
    ).order_by(OpenLoopHistory.sent_at.desc()).all()

    return [{
        "id": r.id,
        "kind": r.kind,
        "signal_key": r.signal_key,
        "score": r.score,
        "title": r.title,
        "body": r.body,
        "deeplink": r.deeplink,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "delivery_ok": bool(r.delivery_ok),
        "user_action": r.user_action,
        "action_at": r.action_at.isoformat() if r.action_at else None,
        "snoozed_until": r.snoozed_until.isoformat() if r.snoozed_until else None,
    } for r in rows]


@router.post("/{history_id}/feedback", summary="对某条推送反馈")
def submit_feedback(
    history_id: int,
    body: OpenLoopFeedback,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    row = db.query(OpenLoopHistory).filter(
        OpenLoopHistory.id == history_id,
        OpenLoopHistory.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(404, "推送记录不存在")

    now = datetime.now(timezone.utc)
    row.user_action = body.action
    row.action_at = now

    if body.action == "snooze_7d":
        days = body.snooze_days or 7
        row.snoozed_until = now + timedelta(days=days)
    elif body.action == "not_interested":
        # 不感兴趣 = 30 天 snooze (重)
        row.snoozed_until = now + timedelta(days=30)

    db.commit()
    return {
        "id": row.id,
        "user_action": row.user_action,
        "snoozed_until": row.snoozed_until.isoformat() if row.snoozed_until else None,
    }


@router.get("/summary", summary="开放循环汇总 (前端面板用, 不发推送)")
def summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """同步调 collect_open_loops, 返回该用户当前所有开放循环 (按 score 倒序).

    用于在 web/mobile 上做 "AI 在跟进的事" 面板, 不依赖推送.
    """
    from app.tasks.open_loop_manager import collect_open_loops
    loops = collect_open_loops(db, current_user.id)
    return [{
        "kind": l.kind,
        "signal_key": l.signal_key,
        "title": l.title,
        "body": l.body,
        "score": l.score,
        "deeplink": l.deeplink,
        "metadata": l.metadata,
    } for l in loops]
