"""
GET  /api/v1/admin/llm/status   — 当前活跃 provider + 配置概况
POST /api/v1/admin/llm/switch   — 临时切换 (内存) provider, 不改 .env
POST /api/v1/admin/llm/ping     — 测当前 provider 延迟 + 中文 tool calling

Karpathy "autonomy slider" 思想: 让管理员能 A/B 切多 LLM 后端验证体验.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.api.deps import get_db
from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/llm", tags=["admin"])


class LLMStatusResponse(BaseModel):
    active_provider: str
    available_providers: list[str]
    current_model: str
    base_url_preview: str
    has_api_key: bool


@router.get("/status", response_model=LLMStatusResponse)
def llm_status(
    admin: User = Depends(get_admin_user),
):
    """看现在用的是哪家 LLM."""
    from app.services.llm.factory import get_llm_provider, _provider_instance

    provider = get_llm_provider()
    provider_type = settings.llm_provider

    # 模型 + base_url 按 provider 取
    if provider_type == "openai":
        model = settings.openai_model
        base = settings.openai_base_url or "https://api.openai.com/v1"
        has_key = bool(settings.openai_api_key)
    elif provider_type == "tokenplan":
        model = settings.tokenplan_model
        base = settings.tokenplan_base_url
        has_key = bool(settings.tokenplan_api_key)
    elif provider_type == "openclaw":
        model = settings.openclaw_model
        base = settings.openclaw_base_url
        has_key = bool(settings.openclaw_api_key)
    elif provider_type == "ollama":
        model = settings.ollama_model
        base = settings.ollama_base_url
        has_key = True  # 本地无需 key
    else:
        model = "unknown"
        base = ""
        has_key = False

    available = ["openclaw", "openai", "ollama"]
    if settings.tokenplan_api_key:
        available.append("tokenplan")

    return LLMStatusResponse(
        active_provider=provider_type,
        available_providers=available,
        current_model=model,
        base_url_preview=base[:80] if base else "",
        has_api_key=has_key,
    )


class LLMSwitchRequest(BaseModel):
    provider: str  # openai | openclaw | ollama | tokenplan


@router.post("/switch")
def llm_switch(
    req: LLMSwitchRequest,
    admin: User = Depends(get_admin_user),
):
    """
    临时切换 LLM provider (改进程内 settings + 重置 factory 单例).
    重启进程后会回退到 .env 的 LLM_PROVIDER.

    生产场景永久切换请改 .env-online + 重启服务.
    """
    valid = {"openai", "openclaw", "ollama", "tokenplan"}
    if req.provider not in valid:
        raise HTTPException(400, f"不支持的 provider: {req.provider}, 可选 {sorted(valid)}")

    # tokenplan 必须有 key
    if req.provider == "tokenplan" and not settings.tokenplan_api_key:
        raise HTTPException(400, "tokenplan 切换前需先配置 TOKENPLAN_API_KEY")

    old = settings.llm_provider
    settings.llm_provider = req.provider

    # 重置 factory 单例, 下次 get_llm_provider() 重新创建
    from app.services.llm.factory import reset_llm_provider
    reset_llm_provider()

    logger.warning(
        f"[admin.llm.switch] user={admin.id} {old} → {req.provider} (内存级, 重启失效)"
    )
    return {
        "ok": True,
        "from": old,
        "to": req.provider,
        "note": "进程内切换. 永久切换请改 .env-online 并重启服务",
    }


class LLMPingResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int
    sample_reply: str
    error: Optional[str] = None


@router.post("/ping", response_model=LLMPingResponse)
async def llm_ping(
    admin: User = Depends(get_admin_user),
):
    """
    测当前 provider 延迟 + 中文回复. 给管理员 A/B 用.
    """
    from app.services.llm.factory import get_llm_provider

    provider = get_llm_provider()
    provider_type = settings.llm_provider
    model = ""
    if provider_type == "openai":
        model = settings.openai_model
    elif provider_type == "tokenplan":
        model = settings.tokenplan_model
    elif provider_type == "openclaw":
        model = settings.openclaw_model
    elif provider_type == "ollama":
        model = settings.ollama_model

    t0 = time.time()
    try:
        raw = await provider.chat(
            messages=[
                {"role": "system", "content": "你是健康助理. 用 ≤30 字回答."},
                {"role": "user", "content": "我今天 HRV 比平时低 12, 怎么办?"},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        if isinstance(raw, dict):
            raw = raw.get("content", "") or ""
        latency = int((time.time() - t0) * 1000)
        return LLMPingResponse(
            ok=True,
            provider=provider_type,
            model=model,
            latency_ms=latency,
            sample_reply=(raw or "")[:200],
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        logger.warning(f"[admin.llm.ping] failed: {e}")
        return LLMPingResponse(
            ok=False,
            provider=provider_type,
            model=model,
            latency_ms=latency,
            sample_reply="",
            error=str(e)[:200],
        )
