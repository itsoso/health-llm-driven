"""
Orchestrator API 端点。

- POST /api/v1/orchestrator/chat           非流式（带 Redis 缓存 30min）
- POST /api/v1/orchestrator/chat/stream    SSE 流式
"""

import asyncio
import hashlib
import json
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException
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
from app.services.llm.error_messages import safe_llm_error_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

# Orchestrator 结果缓存（Redis，30min TTL）— 减少 LLM 调用和 429 限流
_ORCH_CACHE_TTL = 1800  # 30 min

# /chat 保活流式聚合(2026-07-06,与 agent.py /send 同款模式):深分析回合可超过
# main.py 60s 请求超时中间件(wait_for 只计到 response start,非流式 JSON 要到回合
# 结束才发 start → 必 504)。更紧的约束是 Siri 意图扩展(withIntentsExtension.js
# HealthAnalysisIntent):URLSession timeoutInterval=25 是 socket idle 语义,25s 内
# 无任何字节客户端就先断 —— 所以快窗必须 <20s、保活间隔必须 ≤10s。
# 修法:快窗内完成走历史非流式路径(错误保持 4xx/5xx,契约零变化);超窗切 chunked
# 响应,周期吐一个空格(RFC 8259 合法 JSON 前导空白)同时重置三层 idle 计时器 ——
# 服务端 wait_for(start 已发出)、nginx proxy_read_timeout(每次读重置,配
# X-Accel-Buffering: no)、客户端 URLSession/浏览器 socket idle。缓冲整 body 再
# JSON.parse / JSONSerialization 的客户端(Siri / frontend axios / skill curl+jq)
# 对前导空白零感知。
ORCH_CHAT_KEEPALIVE_SECONDS = 10.0
# 保底硬上限:流式豁免不能让真卡死的回合永远吊着 worker。超限 → 取消回合 +
# in-body error,fail-loud。
ORCH_CHAT_HARD_CAP_SECONDS = 300.0


def _chat_error_envelope(query: str, message: str) -> dict:
    """流已开始(200 已定格)后的错误载体:形状与 OrchestratorResponse 一致 + error 字段。

    synthesis 恒空 → Siri 端 (读 synthesis 非空才播报) 自然降级为「暂无分析结论」;
    web 端渲染空结果;显式消费方判 error 非空 = 失败。
    """
    return {
        "query": query,
        "intent": {"raw_query": query, "categories": [], "keywords": []},
        "findings": [],
        "synthesis": "",
        "used_specialists": [],
        "twin_build_ms": 0,
        "total_ms": 0,
        "error": message,
    }


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

    长回合(> ORCH_CHAT_KEEPALIVE_SECONDS)返回 chunked JSON:前导空白是保活
    字节,末尾才是完整 JSON 对象。流一旦开始,状态码已定格 200,错误改为
    body.error 字段(消费方判 error 非空 = 失败)。快回合行为与历史完全一致。
    """
    # GenUI 能力协商: 头里的 caps 合入 request (body 也可带 client_caps, 取并集)。
    req.client_caps = sorted(set(req.client_caps) | set(_parse_client_caps(x_reva_client_caps)))

    # 检查缓存
    cache_key = _orch_cache_key(current_user.id, req.query, req.specialists, req.client_caps)
    cached = _get_orch_cache(cache_key)
    if cached:
        cached["_cached"] = True
        return cached

    async def _aggregate() -> dict:
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

    agg_task = asyncio.create_task(_aggregate())

    # 快窗:绝大多数回合(Siri fast path 3-5s / 缓存未命中的常规分析)在这里完成,
    # 走历史非流式路径 + 原状态码语义。
    finished, _ = await asyncio.wait({agg_task}, timeout=ORCH_CHAT_KEEPALIVE_SECONDS)
    if finished:
        try:
            return agg_task.result()
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("[orchestrator.chat] failed: %s", e)
            raise HTTPException(status_code=500, detail=safe_llm_error_message(str(e))) from e

    started_at = time.monotonic()

    async def _keepalive_body():
        try:
            while True:
                if time.monotonic() - started_at > ORCH_CHAT_HARD_CAP_SECONDS:
                    logger.error(
                        "[orchestrator.chat] turn exceeded hard cap %.0fs, cancelling",
                        ORCH_CHAT_HARD_CAP_SECONDS,
                    )
                    agg_task.cancel()
                    try:
                        await agg_task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001 — 只等 unwind 完成
                        pass
                    yield json.dumps(
                        _chat_error_envelope(req.query, "请求处理超时，请稍后重试"),
                        ensure_ascii=False,
                    )
                    return
                done_set, _ = await asyncio.wait(
                    {agg_task}, timeout=ORCH_CHAT_KEEPALIVE_SECONDS
                )
                if not done_set:
                    yield " "  # JSON 合法前导空白 → 三层 idle 计时器全部重置
                    continue
                try:
                    payload = agg_task.result()
                except Exception as e:  # noqa: BLE001
                    logger.exception("[orchestrator.chat] streaming turn failed: %s", e)
                    payload = _chat_error_envelope(req.query, safe_llm_error_message(str(e)))
                yield json.dumps(payload, ensure_ascii=False, default=str)
                return
        finally:
            if not agg_task.done():
                # 客户端断开:与历史行为一致(整请求被杀),取消回合,
                # 不留孤儿任务占用请求级 db session。
                agg_task.cancel()
                try:
                    await agg_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    return StreamingResponse(
        _keepalive_body(),
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache",
            # nginx 不缓冲:保活字节必须实时到达客户端才能重置其 idle 计时器
            "X-Accel-Buffering": "no",
        },
    )


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
