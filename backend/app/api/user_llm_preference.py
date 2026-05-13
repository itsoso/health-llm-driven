"""用户级 LLM 偏好 API (2026-05-13).

每个登录用户可以选择自己 chat 走哪个 LLM 模型 (model_id from
app/services/llm/model_registry.py). 持久化到 user_profiles.llm_model_id.

跟 /admin/llm/* 区别:
- /admin/llm/* = admin 全局切换, 进程级, 重启失效, 影响所有用户
- /me/llm-preference = 用户个人偏好, 持久化, 只影响自己

优先级: user > admin global > settings 默认.

只能选 list_models(only_available=True) 返回的, 防止 user 随便填字符串.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/me/llm-preference", tags=["user-llm-preference"])


class ModelOption(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    label: str
    provider: str
    model: str
    speed_tier: str
    note: str = ""


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: Optional[str] = Field(None, description="None = 走系统默认")
    options: List[ModelOption]


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: Optional[str] = Field(None, description="None / 空字符串 = 恢复默认")


def _ensure_profile(db: Session, user_id: int) -> UserProfile:
    """user_profile 行不存在时新建空白."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _list_options() -> List[ModelOption]:
    from app.services.llm.model_registry import list_models

    return [
        ModelOption(
            id=m.id, label=m.label, provider=m.provider, model=m.model,
            speed_tier=m.speed_tier, note=m.note,
        )
        for m in list_models(only_available=True)
    ]


@router.get("", response_model=PreferenceResponse)
def get_preference(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """读当前用户的 LLM 偏好 + 可选模型列表."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    return PreferenceResponse(
        model_id=getattr(profile, "llm_model_id", None) if profile else None,
        options=_list_options(),
    )


@router.put("", response_model=PreferenceResponse)
def update_preference(
    body: PreferenceUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """切换当前用户的 LLM 偏好. None / 空 = 恢复默认."""
    new_id = (body.model_id or "").strip() or None
    if new_id is not None:
        from app.services.llm.model_registry import list_models
        allowed = {m.id for m in list_models(only_available=True)}
        if new_id not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"model_id={new_id!r} 不在可用列表; 检查 /me/llm-preference 返回的 options",
            )

    profile = _ensure_profile(db, current_user.id)
    profile.llm_model_id = new_id
    db.commit()
    db.refresh(profile)
    return PreferenceResponse(model_id=profile.llm_model_id, options=_list_options())
