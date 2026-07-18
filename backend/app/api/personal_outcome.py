"""Personal Outcome API

长期健康改善档案：时间序列 × 干预事件 × 摘要。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.personal_outcome_service import PersonalOutcomeService

router = APIRouter(prefix="/personal-outcome", tags=["personal-outcome"])

_service = PersonalOutcomeService()


@router.get("/me/causal-notes", summary="事件观察:指标变化(时序相关,非因果)")
def get_my_causal_notes(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """仅在证据完整时返回事件前后观察，不做因果归因。"""
    from app.services.causal_memory import derive_causal_notes

    return derive_causal_notes(db, current_user.id)


@router.get("/me/timeline")
def get_my_timeline(
    range: str = Query("2y", pattern="^(6m|1y|2y|all)$"),
    granularity: str = Query("month", pattern="^(week|month)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的个人健康改善时间线。

    range:
    - 6m: 最近 180 天
    - 1y: 最近 365 天
    - 2y: 最近 730 天
    - all: 全部历史
    granularity:
    - week: 按 ISO 周聚合
    - month: 按月聚合（默认）
    """
    return _service.get_timeline(
        db=db,
        user_id=current_user.id,
        range_key=range,
        granularity=granularity,
    )


@router.get("/me/events/{event_id}/impact")
def get_my_event_impact(
    event_id: str,
    window_days: int = Query(30, ge=7, le=180),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取单个干预事件前后窗口的指标对比。

    event_id 规范：
    - sup-{definition_id}
    - exam-{exam_id}
    - milestone-garmin-start
    """
    return _service.get_event_impact(
        db=db,
        user_id=current_user.id,
        event_id=event_id,
        window_days=window_days,
    )


@router.get("/me/scorecard", summary="AI 建议成绩单: 命中率 + top 高分/低分")
def get_my_scorecard(
    days: int = Query(90, ge=7, le=365),
    top_n: int = Query(3, ge=1, le=10),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """AI 建议成绩单 — 给 AI 画像页下半部使用.

    返回:
      overall: {total, high_count, low_count, avg_score, hit_rate}
      by_specialist: [{name, total, hits, hit_rate, avg_score}]
      top_hits:   [{card_id, title, metric, score, graded_at, specialist}]
      top_misses: [{...}]
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func, Integer
    from app.models.action_card import ActionCard

    since = datetime.now(timezone.utc) - timedelta(days=days)

    graded_q = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.accuracy_score.isnot(None),
    )

    # Overall
    overall_row = db.query(
        func.count(ActionCard.id).label("total"),
        func.avg(ActionCard.accuracy_score).label("avg_score"),
        func.sum((ActionCard.accuracy_score >= 70).cast(Integer)).label("hits"),
        func.sum((ActionCard.accuracy_score <= 30).cast(Integer)).label("misses"),
    ).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.accuracy_score.isnot(None),
    ).first()

    total = int(overall_row.total or 0)
    hits = int(overall_row.hits or 0)
    misses = int(overall_row.misses or 0)
    overall = {
        "total": total,
        "high_count": hits,
        "low_count": misses,
        "avg_score": round(float(overall_row.avg_score or 0), 1),
        "hit_rate": round(hits / total * 100, 1) if total else 0.0,
    }

    # By specialist
    sp_rows = db.query(
        ActionCard.creator_specialist,
        func.count(ActionCard.id).label("total"),
        func.avg(ActionCard.accuracy_score).label("avg_score"),
        func.sum((ActionCard.accuracy_score >= 70).cast(Integer)).label("hits"),
    ).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.accuracy_score.isnot(None),
        ActionCard.creator_specialist.isnot(None),
    ).group_by(ActionCard.creator_specialist).all()

    by_specialist = [
        {
            "name": r.creator_specialist,
            "total": int(r.total),
            "hits": int(r.hits or 0),
            "hit_rate": round(int(r.hits or 0) / int(r.total) * 100, 1) if r.total else 0.0,
            "avg_score": round(float(r.avg_score or 0), 1),
        }
        for r in sorted(sp_rows, key=lambda x: -(int(x.hits or 0) / (int(x.total) or 1)))
    ]

    def _card_summary(c: ActionCard) -> dict:
        return {
            "card_id": c.id,
            "title": c.title,
            "metric": c.metric_key,
            "score": int(c.accuracy_score or 0),
            "graded_at": c.graded_at.isoformat() if c.graded_at else None,
            "specialist": c.creator_specialist,
        }

    top_hits = graded_q.filter(ActionCard.accuracy_score >= 70)\
        .order_by(ActionCard.accuracy_score.desc()).limit(top_n).all()
    top_misses = graded_q.filter(ActionCard.accuracy_score <= 30)\
        .order_by(ActionCard.accuracy_score.asc()).limit(top_n).all()

    return {
        "window_days": days,
        "overall": overall,
        "by_specialist": by_specialist,
        "top_hits": [_card_summary(c) for c in top_hits],
        "top_misses": [_card_summary(c) for c in top_misses],
    }
