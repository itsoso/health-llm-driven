"""Specialist hit-rate API — 信任循环的"看板".

返回每个 specialist 在最近 N 天内创建的 ActionCard 的命中率,
让用户能看到"哪个 agent 给的建议最准".
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
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
    from collections import defaultdict
    from app.services.outcome_safety import is_efficacy_score_eligible_card

    # 已评分卡片按 specialist 聚合
    # 过滤低依从度卡 (adherence_confidence < 30): 用户根本没做的不算 specialist 准不准
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.creator_specialist.isnot(None),
        ActionCard.accuracy_score.isnot(None),
        # adherence_confidence 为 NULL (兼容旧卡) 或 >= 30
        or_(
            ActionCard.adherence_confidence.is_(None),
            ActionCard.adherence_confidence >= 30,
        ),
    ).all()

    grouped = defaultdict(list)
    for card in cards:
        if is_efficacy_score_eligible_card(card):
            grouped[card.creator_specialist].append(int(card.accuracy_score))
    by_specialist = []
    for specialist, scores in grouped.items():
        total = len(scores)
        hits = sum(score >= 70 for score in scores)
        # 样本量 < 3 不参与 best_specialist 排名, 但仍展示数据
        by_specialist.append({
            "specialist": specialist,
            "total_graded": total,
            "hit_rate": round(hits / total, 2) if total else 0,
            "avg_accuracy_score": round(sum(scores) / total, 1),
            "hits": hits,
            "is_significant": total >= 3,  # 样本量充足才可信
        })

    by_specialist.sort(key=lambda x: x["hit_rate"], reverse=True)

    # 待评分计数
    pending = db.query(func.count(ActionCard.id)).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.check_back_date.isnot(None),
        ActionCard.graded_at.is_(None),
    ).scalar() or 0

    # best_specialist 必须有足够样本量 (≥3)
    best = next((s["specialist"] for s in by_specialist if s["is_significant"]), None)

    return {
        "since": since.isoformat(),
        "days": days,
        "by_specialist": by_specialist,
        "pending_grading": int(pending),
        "best_specialist": best,
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

    from app.services.outcome_safety import is_efficacy_score_eligible_card
    return [{
        "id": c.id,
        "title": c.title,
        "specialist": c.creator_specialist,
        "metric_key": c.metric_key,
        "baseline": c.baseline_value,
        "target": c.target_value,
        "actual": c.actual_value,
        "accuracy_score": c.accuracy_score if is_efficacy_score_eligible_card(c) else None,
        "graded_at": c.graded_at.isoformat() if c.graded_at else None,
        "notes": c.grading_notes,
        "adherence_kind": c.adherence_kind,
        "adherence_confidence": c.adherence_confidence,
        "score_status": "clinician_review" if not is_efficacy_score_eligible_card(c) else "eligible",
    } for c in cards]


# 合法 specialist names (和 backend/app/orchestrator/ 下注册的保持一致)
_LEGAL_SPECIALISTS = frozenset({
    "recovery_coach",
    "fuel_strategist",
    "movement_coach",
    "mental_health_companion",
    "safety_guardian",
    "hypertension_specialist",
    "metabolic_specialist",
    "rhinitis_specialist",
    "knowledge_librarian",
    "longitudinal_analyst",
})


@router.get("/{name}/scorecard", summary="单 specialist 近 N 天 ActionCard + 评分详情")
def specialist_scorecard(
    name: str,
    days: int = Query(30, ge=1, le=365, description="窗口天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """返回该 specialist 近 N 天产的所有 ActionCard (不过滤依从度): 评分详情 + 实际 vs 目标对比.

    和 /hit-rate 不同: 那个给总览多 specialist 命中率 (过滤低依从); 这个给**详情页展示**,
    所有卡都要列, 评没评分都要列, 过不过滤依从度都要列 (UI 决定怎么呈现).
    """
    if name not in _LEGAL_SPECIALISTS:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"未知 specialist: {name}",
                "legal_specialists": sorted(_LEGAL_SPECIALISTS),
            },
        )

    since = datetime.now(timezone.utc) - timedelta(days=days)

    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == current_user.id,
            ActionCard.creator_specialist == name,
            ActionCard.created_at >= since,
        )
        .order_by(ActionCard.created_at.desc())
        .all()
    )

    from app.services.outcome_safety import is_efficacy_score_eligible_card

    graded = [
        card for card in cards
        if card.accuracy_score is not None and is_efficacy_score_eligible_card(card)
    ]
    proposed_count = len(cards)
    graded_count = len(graded)

    avg_acc = (
        sum(c.accuracy_score for c in graded) / graded_count
        if graded_count else None
    )
    # hit_rate: graded / proposed (给 UI 展示"多少建议最后拿到了评分")
    hit_rate = round(graded_count / proposed_count, 2) if proposed_count else 0.0

    return {
        "specialist": name,
        "window_days": days,
        "proposed_count": proposed_count,
        "graded_count": graded_count,
        "hit_rate": hit_rate,
        "avg_accuracy": round(avg_acc, 1) if avg_acc is not None else None,
        "cards": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "graded_at": c.graded_at.isoformat() if c.graded_at else None,
                "metric_key": c.metric_key,
                "target_value": c.target_value,
                "actual_value": c.actual_value,
                "accuracy_score": c.accuracy_score if is_efficacy_score_eligible_card(c) else None,
                "score_status": "clinician_review" if not is_efficacy_score_eligible_card(c) else "eligible",
                "adherence_kind": c.adherence_kind,
                "adherence_confidence": c.adherence_confidence,
                "why_short": (c.grading_notes or "")[:120] or None,
            }
            for c in cards
        ],
    }
