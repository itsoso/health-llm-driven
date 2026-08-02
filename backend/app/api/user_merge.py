"""用户合并API"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from app.database import get_db
from app.models.user import User
from app.services.user_merge import UserMergeService
from app.api.auth import get_current_user_required

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
    """Reject the legacy ID-only merge until both accounts can reauthenticate."""
    # Destructive self-service merging needs recent authentication proof from
    # both accounts. The legacy request carries only two numeric IDs, so it is
    # disabled before either ID is resolved or the merge service is invoked.
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "ACCOUNT_MERGE_REAUTH_REQUIRED",
            "message": "账号合并需要双方重新验证，请联系管理员处理",
        },
    )
