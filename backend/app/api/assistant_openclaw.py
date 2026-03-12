"""智能助理专用 OpenClaw API"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.assistant_openclaw_binding_service import AssistantOpenClawBindingService
from app.services.assistant_openclaw_service import AssistantOpenClawService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant-openclaw", tags=["assistant-openclaw"])
limiter = Limiter(key_func=get_remote_address)


class AssistantOpenClawBindingRequest(BaseModel):
    display_name: str = "我的 OpenClaw"
    gateway_url: str
    gateway_token: Optional[str] = None
    enabled: bool = False


class AssistantOpenClawBindingTestRequest(BaseModel):
    gateway_url: Optional[str] = None
    gateway_token: Optional[str] = None


class AssistantOpenClawSendRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None


@router.get("/binding/me", summary="获取当前账号的智能助理 OpenClaw 绑定")
async def get_my_binding(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = AssistantOpenClawBindingService(db)
    return await service.get_binding_response_with_refresh(current_user.id)


@router.put("/binding/me", summary="保存当前账号的智能助理 OpenClaw 绑定")
@limiter.limit("10/minute")
async def save_my_binding(
    request: Request,
    req: AssistantOpenClawBindingRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = AssistantOpenClawBindingService(db)
    try:
        binding = service.upsert_binding(
            user_id=current_user.id,
            display_name=req.display_name,
            gateway_url=req.gateway_url,
            gateway_token=req.gateway_token,
            enabled=req.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "ok": True,
        "configured": True,
        "enabled": binding.enabled,
        "status": binding.status,
        "gateway_token_last4": binding.gateway_token_last4,
        "message": "绑定已保存，请测试连接以激活该实例",
    }


@router.post("/binding/me/test", summary="测试智能助理 OpenClaw 绑定")
@limiter.limit("10/minute")
async def test_my_binding(
    request: Request,
    req: AssistantOpenClawBindingTestRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = AssistantOpenClawBindingService(db)
    try:
        persist_result = not req.gateway_url and not req.gateway_token
        result = await service.test_binding(
            user_id=current_user.id,
            gateway_url=req.gateway_url,
            gateway_token=req.gateway_token,
            persist_result=persist_result,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/binding/me", summary="删除当前账号的智能助理 OpenClaw 绑定")
async def delete_my_binding(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = AssistantOpenClawBindingService(db)
    ok = service.delete_binding(current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="当前账号尚未绑定 OpenClaw")
    return {"ok": True}


@router.post("/stream", summary="智能助理专用 OpenClaw 流式对话")
@limiter.limit("20/minute")
async def stream_message(
    request: Request,
    req: AssistantOpenClawSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    service = AssistantOpenClawService(db)

    async def generate():
        try:
            async for event in service.send_message_stream(
                user_id=current_user.id,
                message=req.message.strip(),
                conversation_id=req.conversation_id,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'event': 'error', 'data': {'message': str(exc)}}, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("智能助理 OpenClaw 流式异常")
            yield f"data: {json.dumps({'event': 'error', 'data': {'message': '智能助理 OpenClaw 暂时不可用，请稍后重试'}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", summary="智能助理 OpenClaw 对话列表")
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    binding_service = AssistantOpenClawBindingService(db)
    binding = binding_service.get_binding(current_user.id)
    if not binding or not binding.enabled or binding.status != "active":
        return []

    service = AssistantOpenClawService(db)
    convs = service.get_conversations(current_user.id, limit)
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
            "mode": "assistant_openclaw",
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}", summary="智能助理 OpenClaw 对话详情")
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = AssistantOpenClawService(db)
    conv = service.get_conversation_detail(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "mode": "assistant_openclaw",
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


@router.delete("/conversations/{conversation_id}", summary="删除智能助理 OpenClaw 对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = AssistantOpenClawService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}
