"""用户合并API"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.services.user_merge import UserMergeService
from app.api.auth import get_current_user_required
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class MergeCandidatesResponse(BaseModel):
    """合并候选用户响应"""
    candidates: List[dict]
    message: str


class MergeUsersRequest(BaseModel):
    """合并用户请求"""
    source_user_id: int  # 被合并的用户ID
    target_user_id: int  # 目标用户ID（保留）
    confirm: bool = False  # 确认合并


class MergeUsersResponse(BaseModel):
    """合并用户响应"""
    success: bool
    message: str
    source_user_id: int
    target_user_id: int
    stats: dict


@router.get("/candidates", response_model=MergeCandidatesResponse, summary="查找可合并的用户")
async def find_merge_candidates(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    查找当前用户可以合并的其他用户

    匹配条件：
    - 手机号相同
    - 邮箱相同
    - UnionID相同
    """
    candidates = UserMergeService.find_potential_merge_candidates(db, current_user)

    candidate_list = []
    for candidate in candidates:
        candidate_list.append({
            "user_id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
            "phone": candidate.phone,
            "username": candidate.username,
            "has_wechat": candidate.wechat_openid is not None,
            "has_password": candidate.hashed_password is not None,
        })

    return MergeCandidatesResponse(
        candidates=candidate_list,
        message=f"找到 {len(candidate_list)} 个可合并的用户" if candidate_list else "未找到可合并的用户"
    )


@router.post("/merge", response_model=MergeUsersResponse, summary="合并用户")
async def merge_users(
    request: MergeUsersRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    合并两个用户

    注意：
    - 只能合并当前用户相关的账户
    - source_user_id 或 target_user_id 必须是当前用户
    - 合并后source_user将被删除，所有数据迁移到target_user
    """
    # 验证权限：只能合并自己的账户
    if current_user.id not in [request.source_user_id, request.target_user_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能合并自己的账户"
        )

    # 验证用户存在
    source_user = db.query(User).filter(User.id == request.source_user_id).first()
    target_user = db.query(User).filter(User.id == request.target_user_id).first()

    if not source_user or not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    if source_user.id == target_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能合并同一个用户"
        )

    # 执行合并
    try:
        result = UserMergeService.merge_users(
            db=db,
            source_user_id=request.source_user_id,
            target_user_id=request.target_user_id
        )

        return MergeUsersResponse(
            success=True,
            message="✅ 用户合并成功",
            source_user_id=result["source_user_id"],
            target_user_id=result["target_user_id"],
            stats=result["stats"]
        )
    except Exception as e:
        logger.error(f"合并用户失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"合并失败: {str(e)}"
        )
