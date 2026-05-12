"""diet_plan API —— Mobile 我的饮食方案 (G-W7, 2026-05-12)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.diet_plan import build_diet_plan

router = APIRouter(prefix="/diet-plan", tags=["diet-plan"])


@router.get("/me", summary="我的饮食方案 (FuelStrategist 输出 + 关联卡片)")
def get_my_diet_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """聚合 TDEE + 蛋白缺口 + 饮水 + 下一餐 + 基因偏好 + 化验异常关联 +
    N-of-1 实验 + 关联 action_cards."""
    return build_diet_plan(db, current_user.id)
