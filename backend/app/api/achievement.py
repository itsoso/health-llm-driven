"""成就徽章API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.achievement_service import AchievementService

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("/definitions")
async def get_definitions(db: Session = Depends(get_db)):
    """获取所有徽章定义（公开）"""
    svc = AchievementService(db)
    svc.seed_badges()  # 确保种子数据存在
    defs = svc.get_all_definitions()
    return [
        {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "description": d.description,
            "icon": d.icon,
            "category": d.category,
            "criteria_type": d.criteria_type,
            "criteria_value": d.criteria_value,
            "rarity": d.rarity,
            "sort_order": d.sort_order,
        }
        for d in defs
    ]


@router.get("/me")
async def get_my_achievements(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户成就 + 进度"""
    svc = AchievementService(db)
    svc.seed_badges()
    achievements = svc.get_user_achievements(current_user.id)
    unlocked_count = sum(1 for a in achievements if a["unlocked"])
    return {
        "total": len(achievements),
        "unlocked": unlocked_count,
        "achievements": achievements,
    }


@router.post("/check")
async def check_achievements(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动触发成就检查"""
    svc = AchievementService(db)
    svc.seed_badges()
    newly = svc.check_and_award(current_user.id)
    return {
        "newly_unlocked": len(newly),
        "badges": [
            {"badge_id": ub.badge_id, "progress": ub.progress_value}
            for ub in newly
        ],
    }
