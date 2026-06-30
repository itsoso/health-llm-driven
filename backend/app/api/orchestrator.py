"""
Orchestrator API 端点。

- POST /api/v1/orchestrator/chat           非流式（带 Redis 缓存 30min）
- POST /api/v1/orchestrator/chat/stream    SSE 流式
"""

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.orchestrator import (
    OrchestratorRequest,
    run_orchestrator,
    stream_orchestrator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

# Orchestrator 结果缓存（Redis，30min TTL）— 减少 LLM 调用和 429 限流
_ORCH_CACHE_TTL = 1800  # 30 min


# 头解析提到共享 util (agent.py 同用), 这里保留同名 re-export 供既有 import / 测试。
from app.api._client_caps import parse_client_caps as _parse_client_caps  # noqa: E402,F401


def _orch_cache_key(user_id: int, query: str, specialists: list | None, caps: list[str]) -> str:
    # caps 进 key: genui-v1 客户端与旧端对同一 query 得到不同响应 (block vs 现状), 不能串味。
    payload = f"{user_id}:{query}:{sorted(specialists or [])}:{sorted(caps)}"
    return f"orch:v1:{hashlib.sha1(payload.encode()).hexdigest()[:16]}"


def _get_orch_cache(key: str):
    try:
        from app.utils.redis_cache import get_redis_client
        client = get_redis_client()
        if not client:
            return None
        raw = client.get(key)
        if raw:
            return json.loads(raw if isinstance(raw, str) else raw.decode())
    except Exception:
        pass
    return None


def _set_orch_cache(key: str, data: dict):
    try:
        from app.utils.redis_cache import get_redis_client
        client = get_redis_client()
        if client:
            client.setex(key, _ORCH_CACHE_TTL, json.dumps(data, default=str, ensure_ascii=False))
    except Exception:
        pass


@router.post("/chat")
async def chat(
    req: OrchestratorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
    x_reva_client_caps: str | None = Header(default=None),
):
    """
    非流式综合分析。

    返回完整 OrchestratorResponse（intent + findings + synthesis）。
    """
    # GenUI 能力协商: 头里的 caps 合入 request (body 也可带 client_caps, 取并集)。
    req.client_caps = sorted(set(req.client_caps) | set(_parse_client_caps(x_reva_client_caps)))

    # 检查缓存
    cache_key = _orch_cache_key(current_user.id, req.query, req.specialists, req.client_caps)
    cached = _get_orch_cache(cache_key)
    if cached:
        cached["_cached"] = True
        return cached

    response = await run_orchestrator(db, current_user.id, req)

    # 审计日志
    try:
        from app.agents.audit import log_orchestrator_run

        log_orchestrator_run(
            db=db,
            user_id=current_user.id,
            query=req.query,
            intent_categories=response.intent.categories,
            used_specialists=response.used_specialists,
            findings_count=sum(len(f.findings) for f in response.findings),
            twin_build_ms=response.twin_build_ms,
            total_ms=response.total_ms,
            source=req.source,
        )
    except Exception:
        pass

    result = response.model_dump(mode="json")

    # 写缓存（仅当有 synthesis 时，避免缓存空结果）
    if response.synthesis:
        _set_orch_cache(cache_key, result)

    return result


@router.post("/chat/stream")
async def chat_stream(
    req: OrchestratorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
    x_reva_client_caps: str | None = Header(default=None),
):
    """SSE 流式综合分析。"""
    req.stream = True
    # GenUI 能力协商 (头优先, 与 body client_caps 取并集)。
    req.client_caps = sorted(set(req.client_caps) | set(_parse_client_caps(x_reva_client_caps)))

    async def event_source():
        async for chunk in stream_orchestrator(db, current_user.id, req):
            yield chunk

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
