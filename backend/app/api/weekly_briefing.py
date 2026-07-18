"""用户面 Weekly Briefing API (2026-05-14).

把 WeeklyAdvisor 跑出来的 action_cards (source_type='weekly_advisor') 组成
"本周 AI 给你 3-5 件事" 的用户视图. 直接复用 ActionCard 数据, 加聚合.

跟 /admin/wscla 区别: admin 看全员命中率, /me/weekly-briefing 看个人本周.
跟 weekly_advisor (Celery 周日 21:07) 区别: 这只是查询; 没卡时让用户能 on-demand 触发一次.

Phase 1 完整闭环最后一公里: 用户能在 App 里看到 "本周 AI 给我的 X 件事".
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.outcome_safety import user_facing_efficacy_fields

logger = logging.getLogger(__name__)
router = APIRouter()


def _week_start_utc(now: datetime) -> datetime:
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )


def _card_to_dict(c: ActionCard) -> dict:
    efficacy_fields = user_facing_efficacy_fields(c)
    return {
        "id": c.id,
        "title": c.title,
        "content": c.content,
        "metric_key": c.metric_key,
        "baseline_value": c.baseline_value,
        "target_value": c.target_value,
        "actual_value": getattr(c, "actual_value", None),
        "verification_days": c.verification_days,
        "evidence_level": getattr(c, "evidence_level", None),
        "outcome": efficacy_fields["outcome"],
        "score_status": efficacy_fields["score_status"],
        "status": c.status,
        "user_decision": getattr(c, "user_decision", None),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "graded_at": c.graded_at.isoformat() if c.graded_at else None,
    }


@router.get("/me/weekly-briefing", summary="本周 AI 给你的 3-5 件事")
def get_weekly_briefing(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """返回:
      week_start: 本周一 ISO
      primary_goal: 用户主目标 (来自 onboarding step 5)
      cards: [...] 本周 AI 给的建议
      stats: {total, accepted, completed, improved}
      last_run_at: 最近一次 weekly_advisor 跑的时间
      can_trigger: bool 用户可否手动触发 (本周没卡才允许)
    """
    now = datetime.now(timezone.utc)
    week_start = _week_start_utc(now)

    cards_q = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == current_user.id,
            ActionCard.source_type == "weekly_advisor",
            ActionCard.created_at >= week_start,
        )
        .order_by(desc(ActionCard.created_at))
    )
    cards = cards_q.all()

    accepted = sum(1 for c in cards if (c.user_decision or "") == "accepted")
    completed = sum(1 for c in cards if c.completed_at is not None)
    improved = sum(
        1 for c in cards
        if user_facing_efficacy_fields(c)["outcome"] == "improved"
    )

    last_run_at = cards[0].created_at if cards else None

    # primary_goal
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    primary_goal = getattr(profile, "primary_goal", None) if profile else None

    return {
        "week_start": week_start.isoformat(),
        "primary_goal": primary_goal,
        "cards": [_card_to_dict(c) for c in cards],
        "stats": {
            "total": len(cards),
            "accepted": accepted,
            "completed": completed,
            "improved": improved,
        },
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        "can_trigger": len(cards) == 0,
    }


@router.post("/me/weekly-briefing/trigger", summary="手动触发本周 AI 建议生成")
async def trigger_weekly_briefing(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """本周还没生成时, 让用户手动触发一次 (周日 21:07 之前 / 新用户).

    幂等: weekly_advisor 内部已有"本周一来已写过 → skip"保护, 重复点击安全.
    LLM 调用慢 (~30s), 用 BackgroundTasks 异步, 立刻 200 返回.
    """
    now = datetime.now(timezone.utc)
    week_start = _week_start_utc(now)
    has_card = (
        db.query(ActionCard.id)
        .filter(
            ActionCard.user_id == current_user.id,
            ActionCard.source_type == "weekly_advisor",
            ActionCard.created_at >= week_start,
        )
        .first()
        is not None
    )
    if has_card:
        return {"queued": False, "reason": "本周已有 AI 建议, 不重复生成"}

    user_id = current_user.id

    async def _run():
        from app.database import SessionLocal
        from app.services.weekly_advisor import generate_weekly_advice
        _db = SessionLocal()
        try:
            await generate_weekly_advice(_db, user_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[weekly-briefing trigger] user={user_id} 失败: {e}")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"queued": True, "estimated_seconds": 30}
