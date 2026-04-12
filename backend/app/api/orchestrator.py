"""
Orchestrator API 端点。

- POST /api/v1/orchestrator/chat           非流式
- POST /api/v1/orchestrator/chat/stream    SSE 流式
"""

import logging

from fastapi import APIRouter, Depends
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


@router.post("/chat")
async def chat(
    req: OrchestratorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    非流式综合分析。

    返回完整 OrchestratorResponse（intent + findings + synthesis）。
    """
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
        )
    except Exception:
        pass

    return response.model_dump(mode="json")


@router.post("/chat/stream")
async def chat_stream(
    req: OrchestratorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """SSE 流式综合分析。"""
    req.stream = True

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
