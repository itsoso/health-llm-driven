"""Trust Loop Judgment Feedback API — 用户对任意 AI 判断的 "对/不对" 反馈.

区别于 /feedback (旧 skill performance 接口):
  /judgment 是对**具体决策** (insight/anomaly/action_card/...) 的反馈.

写入后自动副作用 (按 target_type):
  - insight: 同步更新 DailyInsight.user_feedback (向后兼容 /insights/{id}/feedback)
  - anomaly_alert: not_helpful → is_suppressed=True (减少同类推送)
  - 其他: 仅记录, orchestrator 下次合成时作负样本注入
"""
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.user_judgment_feedback import (
    FEEDBACK_VALUES, TARGET_TYPES, UserJudgmentFeedback,
)

router = APIRouter(prefix="/judgment", tags=["judgment-feedback"])


class JudgmentFeedbackRequest(BaseModel):
    target_type: str = Field(..., description=f"one of {sorted(TARGET_TYPES)}")
    target_id: int
    feedback: str = Field(..., description=f"one of {sorted(FEEDBACK_VALUES)}")
    note: Optional[str] = Field(None, max_length=1000)
    snapshot: Optional[str] = Field(None, max_length=500, description="冻结的上下文摘要")


@router.post("/feedback", summary="对任意 AI 判断反馈 (Trust Loop 闭环)")
def submit_feedback(
    req: JudgmentFeedbackRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if req.target_type not in TARGET_TYPES:
        raise HTTPException(400, f"target_type 必须是 {sorted(TARGET_TYPES)}")
    if req.feedback not in FEEDBACK_VALUES:
        raise HTTPException(400, f"feedback 必须是 {sorted(FEEDBACK_VALUES)}")

    # 幂等: 同 user+target 已有则覆盖反馈
    existing = db.query(UserJudgmentFeedback).filter(
        UserJudgmentFeedback.user_id == current_user.id,
        UserJudgmentFeedback.target_type == req.target_type,
        UserJudgmentFeedback.target_id == req.target_id,
    ).first()

    if existing:
        existing.feedback = req.feedback
        existing.note = req.note
        if req.snapshot:
            existing.snapshot = req.snapshot
        db.commit()
        row = existing
    else:
        row = UserJudgmentFeedback(
            user_id=current_user.id,
            target_type=req.target_type,
            target_id=req.target_id,
            feedback=req.feedback,
            note=req.note,
            snapshot=req.snapshot,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    _apply_side_effects(db, current_user.id, req)
    db.commit()

    return {
        "id": row.id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "feedback": row.feedback,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _apply_side_effects(db: Session, user_id: int, req: JudgmentFeedbackRequest) -> None:
    """按 target_type 触发下游副作用 (fail-soft)."""
    try:
        if req.target_type == "insight":
            from app.models.daily_insight import DailyInsight
            row = db.query(DailyInsight).filter(
                DailyInsight.id == req.target_id,
                DailyInsight.user_id == user_id,
            ).first()
            if row:
                row.user_feedback = req.feedback
                row.feedback_note = req.note
                row.feedback_at = datetime.now(UTC)

        elif req.target_type == "anomaly_alert" and req.feedback == "not_helpful":
            from app.models.anomaly_alert import AnomalyAlert
            row = db.query(AnomalyAlert).filter(
                AnomalyAlert.id == req.target_id,
                AnomalyAlert.user_id == user_id,
            ).first()
            if row:
                row.is_suppressed = True
    except Exception:
        pass


@router.get("/feedback/recent", summary="本人近期反馈列表 + 汇总")
def list_recent_feedback(
    days: int = Query(30, ge=1, le=180),
    target_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    since = datetime.now(UTC) - timedelta(days=days)
    q = db.query(UserJudgmentFeedback).filter(
        UserJudgmentFeedback.user_id == current_user.id,
        UserJudgmentFeedback.created_at >= since,
    )
    if target_type:
        q = q.filter(UserJudgmentFeedback.target_type == target_type)

    rows = q.order_by(UserJudgmentFeedback.created_at.desc()).limit(100).all()

    by_value: dict = {}
    by_type: dict = {}
    for r in rows:
        by_value[r.feedback] = by_value.get(r.feedback, 0) + 1
        by_type[r.target_type] = by_type.get(r.target_type, 0) + 1

    return {
        "items": [
            {
                "id": r.id,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "feedback": r.feedback,
                "note": r.note,
                "snapshot": r.snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "summary": {
            "total": len(rows),
            "by_value": by_value,
            "by_type": by_type,
        },
    }


def get_recent_negative_feedback(
    db: Session, user_id: int, days: int = 30, limit: int = 5
) -> list:
    """给 orchestrator 注入用的 helper: 取近期 not_helpful/irrelevant 反馈.

    返回 list of dict 便于直接渲染到 prompt.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(UserJudgmentFeedback)
        .filter(
            UserJudgmentFeedback.user_id == user_id,
            UserJudgmentFeedback.created_at >= since,
            UserJudgmentFeedback.feedback.in_(["not_helpful", "irrelevant"]),
        )
        .order_by(UserJudgmentFeedback.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "target_type": r.target_type,
            "target_id": r.target_id,
            "feedback": r.feedback,
            "snapshot": r.snapshot or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
