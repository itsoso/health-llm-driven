"""OpenClaw Channel API — 独立于健康助理的 OpenClaw 对话通道"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.openclaw import OpenClawMessage, OpenClawConversation
from app.models.user import User
from app.services.openclaw_service import OpenClawService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openclaw", tags=["openclaw"])


# ── Schemas ───────────────────────────────────────────────

class OpenClawSendRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    image_base64: str | None = None
    image_type: str | None = "jpeg"
    file_base64: str | None = None
    file_name: str | None = None


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
    rating: int | None = None
    created_at: str

    class Config:
        from_attributes = True


class OpenClawConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: List[OpenClawMessageResponse]

    class Config:
        from_attributes = True


class RateMessageRequest(BaseModel):
    rating: int

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("rating must be 1 (thumbs up) or -1 (thumbs down)")
        return v


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

    # 文件附件：提取文本并注入消息
    message = req.message.strip()
    if req.file_base64 and req.file_name:
        try:
            from app.services.file_extract_service import extract_text_from_base64
            file_text = extract_text_from_base64(req.file_base64, req.file_name)
            if file_text:
                message = f"{message}\n\n[附件: {req.file_name}]\n{file_text}"
        except Exception as e:
            logger.warning(f"文件提取失败: {e}")

    service = OpenClawService(db)

    async def generate():
        try:
            async for event in service.send_message_stream(
                user_id=current_user.id,
                message=message,
                conversation_id=req.conversation_id,
                is_admin=current_user.is_admin,
                image_base64=req.image_base64,
                image_type=req.image_type or "jpeg",
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
                "rating": m.rating,
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


@router.post("/messages/{message_id}/rate", summary="评价 OpenClaw 消息质量")
async def rate_message(
    message_id: int,
    req: RateMessageRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """对 OpenClaw 助手消息进行 thumbs up/down 评价"""
    message = (
        db.query(OpenClawMessage)
        .join(OpenClawConversation, OpenClawMessage.conversation_id == OpenClawConversation.id)
        .filter(
            OpenClawMessage.id == message_id,
            OpenClawConversation.user_id == current_user.id,
        )
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    message.rating = req.rating
    db.commit()
    return {"ok": True, "message_id": message_id, "rating": req.rating}


@router.get("/rating-stats", summary="OpenClaw 消息评价统计")
async def get_rating_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的 OpenClaw 消息评价统计"""
    base_query = (
        db.query(OpenClawMessage)
        .join(OpenClawConversation, OpenClawMessage.conversation_id == OpenClawConversation.id)
        .filter(
            OpenClawConversation.user_id == current_user.id,
            OpenClawMessage.rating.isnot(None),
        )
    )

    total_rated = base_query.count()
    thumbs_up = base_query.filter(OpenClawMessage.rating == 1).count()
    thumbs_down = base_query.filter(OpenClawMessage.rating == -1).count()
    satisfaction_rate = round(thumbs_up / total_rated, 2) if total_rated > 0 else 0.0

    return {
        "total_rated": total_rated,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "satisfaction_rate": satisfaction_rate,
    }
