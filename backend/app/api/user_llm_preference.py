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
    capabilities: List[str] = Field(default_factory=list)
    supports_streaming: bool = True  # False = 整段生成 (无 SSE), 客户端可提示需等待


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
    from app.services.ai_consent import is_disclosed_model

    return [
        ModelOption(
            id=m.id, label=m.label, provider=m.provider, model=m.model,
            speed_tier=m.speed_tier, note=m.note, capabilities=list(m.capabilities),
            supports_streaming=m.supports_streaming,
        )
        for m in list_models(only_available=True)
        if is_disclosed_model(m)
    ]


@router.get("", response_model=PreferenceResponse)
def get_preference(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """读当前用户的 LLM 偏好 + 可选模型列表."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    options = _list_options()
    selected = getattr(profile, "llm_model_id", None) if profile else None
    return PreferenceResponse(
        model_id=selected if selected in {option.id for option in options} else None,
        options=options,
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
        allowed = {m.id for m in _list_options()}
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


class SelfTestResponse(BaseModel):
    """切换 LLM 偏好后的自检结果 (2026-05-14)."""
    model_config = ConfigDict(protected_namespaces=())

    ok: bool
    model_id: Optional[str]    # user 偏好里的 id (None = 系统默认)
    actual_model: Optional[str]  # provider 实际 init 时的 model name (e.g. 'qwen3.6-plus')
    actual_provider: Optional[str]  # 'tokenplan' / 'openai-proxy' / 'langbridge-proxy' 等
    base_url: Optional[str]
    latency_ms: Optional[int]
    sample_reply: Optional[str]
    error: Optional[str] = None


@router.post("/selftest", response_model=SelfTestResponse)
async def selftest(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """自检 — 用当前用户偏好 ping 一次 LLM, 返回实际命中的 model + 延迟 + 样本回复.

    给设置页"切换完成"后立刻调用, 让用户**眼见为实**自己选的模型确实生效.
    """
    import time
    model_id = get_preference(current_user=current_user, db=db).model_id

    try:
        from app.services.llm.factory import create_provider_for_user
        provider = create_provider_for_user(current_user.id, db)

        actual_model = getattr(provider, "model", None) or getattr(provider, "default_model", None)
        actual_provider = getattr(provider, "provider_name", None) or type(provider).__name__
        base_url = getattr(provider, "base_url", None)

        t0 = time.monotonic()
        result = await provider.chat(
            messages=[{"role": "user", "content": "请用一句话告诉我你是哪个模型"}],
            temperature=0.1,
            max_tokens=80,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        sample = result if isinstance(result, str) else (
            (result or {}).get("content") if isinstance(result, dict) else str(result)
        )

        return SelfTestResponse(
            ok=True,
            model_id=model_id,
            actual_model=actual_model,
            actual_provider=actual_provider,
            base_url=base_url,
            latency_ms=latency_ms,
            sample_reply=(sample or "")[:200],
        )
    except Exception as e:  # noqa: BLE001
        return SelfTestResponse(
            ok=False,
            model_id=model_id,
            actual_model=None,
            actual_provider=None,
            base_url=None,
            latency_ms=None,
            sample_reply=None,
            error=str(e)[:200],
        )
