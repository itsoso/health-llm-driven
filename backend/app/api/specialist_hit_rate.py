"""Specialist hit-rate API — 信任循环的"看板".

返回每个 specialist 在最近 N 天内创建的 ActionCard 的命中率,
让用户能看到"哪个 agent 给的建议最准".
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.user import User

router = APIRouter(prefix="/specialists", tags=["specialists"])


@router.get("/hit-rate", summary="各 specialist 的预测命中率 (最近 N 天)")
def specialist_hit_rate(
    days: int = Query(30, ge=7, le=180),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 已评分卡片按 specialist 聚合
    rows = db.query(
        ActionCard.creator_specialist,
        func.count(ActionCard.id).label("total"),
        func.avg(ActionCard.accuracy_score).label("avg_score"),
        func.sum(
            (ActionCard.accuracy_score >= 70).cast(__import__('sqlalchemy').Integer)
        ).label("hits"),
    ).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.creator_specialist.isnot(None),
    ).group_by(ActionCard.creator_specialist).all()

    by_specialist = []
    for r in rows:
        total = int(r.total)
        hits = int(r.hits or 0)
        by_specialist.append({
            "specialist": r.creator_specialist,
            "total_graded": total,
            "hit_rate": round(hits / total, 2) if total else 0,
            "avg_accuracy_score": round(float(r.avg_score or 0), 1),
            "hits": hits,
        })

    by_specialist.sort(key=lambda x: x["hit_rate"], reverse=True)

    # 待评分计数
    pending = db.query(func.count(ActionCard.id)).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.check_back_date.isnot(None),
        ActionCard.graded_at.is_(None),
    ).scalar() or 0

    return {
        "since": since.isoformat(),
        "days": days,
        "by_specialist": by_specialist,
        "pending_grading": int(pending),
        "best_specialist": by_specialist[0]["specialist"] if by_specialist else None,
    }


@router.get("/me/recent-cards", summary="带评分的近期 ActionCard 列表 (信任面板)")
def my_recent_graded_cards(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.graded_at.isnot(None),
    ).order_by(ActionCard.graded_at.desc()).limit(limit).all()

    return [{
        "id": c.id,
        "title": c.title,
        "specialist": c.creator_specialist,
        "metric_key": c.metric_key,
        "baseline": c.baseline_value,
        "target": c.target_value,
        "actual": c.actual_value,
        "accuracy_score": c.accuracy_score,
        "graded_at": c.graded_at.isoformat() if c.graded_at else None,
        "notes": c.grading_notes,
    } for c in cards]
