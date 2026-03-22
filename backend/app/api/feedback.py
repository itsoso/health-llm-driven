"""交互反馈 API — 用户评分 + Skill 性能查询"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.schemas.interaction_feedback import (
    FeedbackCreateRequest,
    FeedbackResponse,
    SkillPerformanceSummary,
    OptimizationLogResponse,
)
from app.services.feedback_service import feedback_service
from app.services.skill_registry import skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    req: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """提交对 AI 回复的评分（👍=5, 👎=1）"""
    feedback = feedback_service.submit_rating(
        db=db,
        user_id=current_user.id,
        conversation_type=req.conversation_type,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        rating=req.rating,
        feedback_text=req.feedback_text,
    )
    return feedback


@router.get("/skills", response_model=list[SkillPerformanceSummary])
async def get_skill_performance(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取所有 Skill 最近 N 天的性能概览（管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看")
    return feedback_service.get_skill_performance(db, days=days)


@router.get("/skills/low-performing")
async def get_low_performing_skills(
    days: int = 7,
    threshold: float = 0.8,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取需要优化的 Skill（success_rate 低于阈值）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看")
    return feedback_service.get_low_performing_skills(db, days=days, threshold=threshold)


@router.get("/optimization-logs", response_model=list[OptimizationLogResponse])
async def get_optimization_logs(
    skill_name: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取 Skill 优化历史"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看")
    return feedback_service.get_optimization_logs(db, skill_name=skill_name, limit=limit)


# ---- Skill 版本管理 ----

@router.get("/skills/registry")
async def list_skill_registry(
    current_user: User = Depends(get_current_user_required),
):
    """列出所有本地 Skill 及其版本信息（管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看")
    return skill_registry.list_skills()


@router.get("/skills/registry/{name}")
async def get_skill_detail(
    name: str,
    current_user: User = Depends(get_current_user_required),
):
    """获取单个 Skill 的详细信息"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看")
    try:
        info = skill_registry.get_skill(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not info:
        raise HTTPException(status_code=404, detail=f"Skill {name} 不存在")
    return info


@router.post("/skills/registry/{name}/promote")
async def promote_skill_version(
    name: str,
    version: str,
    current_user: User = Depends(get_current_user_required),
):
    """将 canary 版本升级为 production"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员操作")
    try:
        skill_registry.promote_version(name, version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "promoted", "skill": name, "version": version}


@router.post("/skills/registry/{name}/rollback")
async def rollback_skill(
    name: str,
    current_user: User = Depends(get_current_user_required),
):
    """回滚 Skill 到上一个稳定版本"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员操作")
    try:
        version = skill_registry.rollback_version(name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not version:
        raise HTTPException(status_code=400, detail="没有可回滚的版本")
    return {"status": "rolled_back", "skill": name, "version": version}
