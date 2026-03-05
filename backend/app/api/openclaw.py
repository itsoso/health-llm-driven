"""OpenClaw Channel API — 独立于健康助理的 OpenClaw 对话通道"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.openclaw_service import OpenClawService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openclaw", tags=["openclaw"])


# ── Schemas ───────────────────────────────────────────────

class OpenClawSendRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class OpenClawConversationResponse(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class OpenClawMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


class OpenClawConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: List[OpenClawMessageResponse]

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────

@router.post("/stream", summary="OpenClaw 流式对话")
async def stream_message(
    request: Request,
    req: OpenClawSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """流式发送消息到 OpenClaw Gateway，SSE 实时返回"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    service = OpenClawService(db)

    async def generate():
        try:
            async for event in service.send_message_stream(
                user_id=current_user.id,
                message=req.message.strip(),
                conversation_id=req.conversation_id,
                is_admin=current_user.is_admin,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"OpenClaw 流式异常: {e}", exc_info=True)
            error_event = {"event": "error", "data": {"message": str(e)}}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", summary="OpenClaw 对话列表")
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    convs = service.get_conversations(current_user.id, limit)
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}", summary="OpenClaw 对话详情")
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    conv = service.get_conversation_detail(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": str(m.created_at),
            }
            for m in conv.messages
        ],
    }


@router.delete("/conversations/{conversation_id}", summary="删除 OpenClaw 对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}
