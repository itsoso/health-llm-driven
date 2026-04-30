"""Daily Insight API — 今日洞察 + 用户反馈."""
from datetime import UTC, date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.daily_insight import DailyInsight
from app.models.user import User

router = APIRouter(prefix="/insights", tags=["insights"])


_ALLOWED_FEEDBACK = {"helpful", "not_helpful", "irrelevant", "already_knew"}


class FeedbackRequest(BaseModel):
    feedback: str = Field(..., description="helpful / not_helpful / irrelevant / already_knew")
    note: Optional[str] = Field(None, max_length=1000)


@router.get("/today", summary="今日 Insight (幂等: 未生成时 lazy 触发 generator)")
def get_today_insight(
    generate_if_missing: bool = Query(True, description="今日未生成时是否立即触发生成"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = date.today()
    row = db.query(DailyInsight).filter(
        DailyInsight.user_id == current_user.id,
        DailyInsight.insight_date == today,
    ).first()

    if not row and generate_if_missing:
        from app.services.insight_generator import generate_daily_insight
        new_id = generate_daily_insight(db, current_user.id, today)
        if new_id:
            row = db.query(DailyInsight).filter(DailyInsight.id == new_id).first()

    if not row:
        return {"insight": None, "message": "今日暂无洞察 (数据不足或无匹配模式)"}

    return {"insight": _serialize(row)}


@router.get("/recent", summary="最近 N 天 Insight 列表")
def list_recent_insights(
    days: int = Query(14, ge=1, le=60),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(DailyInsight)
        .filter(
            DailyInsight.user_id == current_user.id,
            DailyInsight.insight_date >= since,
        )
        .order_by(DailyInsight.insight_date.desc())
        .all()
    )
    return {"insights": [_serialize(r) for r in rows]}


@router.post("/{insight_id}/feedback", summary="对 Insight 反馈 (Trust Loop)")
def submit_feedback(
    insight_id: int,
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if req.feedback not in _ALLOWED_FEEDBACK:
        raise HTTPException(400, f"feedback 必须是 {sorted(_ALLOWED_FEEDBACK)} 之一")

    row = db.query(DailyInsight).filter(
        DailyInsight.id == insight_id,
        DailyInsight.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(404, "insight 不存在")

    row.user_feedback = req.feedback
    row.feedback_note = req.note
    row.feedback_at = datetime.now(UTC)
    db.commit()
    return {"message": "已记录", "insight_id": insight_id, "feedback": req.feedback}


def _serialize(r: DailyInsight) -> dict:
    return {
        "id": r.id,
        "insight_date": r.insight_date.isoformat() if r.insight_date else None,
        "kind": r.kind,
        "rule_id": r.rule_id,
        "title": r.title,
        "body": r.body,
        "evidence": r.evidence or {},
        "confidence": r.confidence,
        "severity": r.severity,
        "user_feedback": r.user_feedback,
        "feedback_note": r.feedback_note,
        "feedback_at": r.feedback_at.isoformat() if r.feedback_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
