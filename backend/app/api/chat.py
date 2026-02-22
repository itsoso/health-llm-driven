"""
聊天 API - OpenClaw 集成
"""
import base64
import logging
import os
import tempfile
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatSendRequest, ChatSendResponse,
    ConversationResponse, ConversationDetailResponse, ChatMessageResponse,
    TranscribeRequest, TranscribeResponse
)
from app.services.chat_service import ChatService
from app.api.deps import get_current_user_required
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatSendResponse, summary="发送消息")
async def send_message(
    req: ChatSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """发送消息给 AI 助手，自动注入健康上下文"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    service = ChatService(db)
    try:
        result = await service.send_message(
            user_id=current_user.id,
            message=req.message.strip(),
            conversation_id=req.conversation_id,
            is_kids_mode=req.is_kids_mode or False
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    response = ChatSendResponse(
        conversation_id=result["conversation_id"],
        reply=result["reply"],
        message_id=result["message_id"],
        diet_saved=result.get("diet_saved"),
        diet_data=result.get("diet_data"),
        activities_saved=result.get("activities_saved"),
        activities=result.get("activities"),
        reminder=result.get("reminder"),
    )
    return response


@router.get("/conversations", response_model=List[ConversationResponse], summary="对话列表")
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的对话列表"""
    service = ChatService(db)
    convs = service.get_conversations(current_user.id, limit)

    result = []
    for c in convs:
        last_msg = None
        if c.messages:
            last_msg = c.messages[-1].content[:80]
        result.append(ConversationResponse(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            last_message=last_msg
        ))
    return result


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse, summary="对话详情")
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取对话的所有消息"""
    service = ChatService(db)
    conv = service.get_conversation_messages(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        messages=[ChatMessageResponse.model_validate(m) for m in conv.messages]
    )


@router.post("/transcribe", response_model=TranscribeResponse, summary="语音转文字")
async def transcribe_audio(
    req: TranscribeRequest,
    current_user: User = Depends(get_current_user_required),
):
    """将语音音频转为文字，使用 OpenAI Whisper API"""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="语音识别服务不可用")

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        client = OpenAI(**client_kwargs)

        audio_bytes = base64.b64decode(req.audio_base64)
        suffix = f".{req.audio_format}" if req.audio_format else ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            with open(temp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="zh"
                )
            return TranscribeResponse(text=transcript.text)
        finally:
            os.unlink(temp_path)

    except Exception as e:
        logger.error(f"语音转文字失败: {e}")
        raise HTTPException(status_code=500, detail=f"语音识别失败: {str(e)[:100]}")


@router.delete("/conversations/{conversation_id}", summary="删除对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除对话及其所有消息"""
    service = ChatService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}
