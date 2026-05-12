"""movement_plan API —— Mobile 我的运动方案 (G-W6, 2026-05-12)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.movement_plan import build_movement_plan

router = APIRouter(prefix="/movement", tags=["movement"])


@router.get("/plan/me", summary="我的运动方案 (MovementCoach 输出 + 关联卡片)")
def get_my_movement_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """聚合 Garmin training_status + ACWR + readiness + 基因偏好 + 本周训练处方 +
    近期 workout + N-of-1 实验 + 关联 action_cards. Mobile /movement-plan 用.

    failure modes (返回 has_data=False):
      - twin_build_failed: 用户 Twin 构建异常
      - coach_run_failed: MovementCoach 运行异常 (data 不足时仍返 unknown 状态)
    """
    return build_movement_plan(db, current_user.id)
