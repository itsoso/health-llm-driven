"""语音 API — 语音转文字 + 语音指令（从 chat.py 独立出来）"""
import base64
import logging
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.user import User
from app.schemas.chat import TranscribeRequest, TranscribeResponse
from app.api.deps import get_current_user_required
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["speech"])

limiter = Limiter(key_func=get_remote_address)


@router.post("/transcribe", response_model=TranscribeResponse, summary="语音转文字")
@limiter.limit("10/minute")
async def transcribe_audio(
    request: Request,
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
                    language="zh",
                )
            return TranscribeResponse(text=transcript.text)
        finally:
            os.unlink(temp_path)

    except Exception as e:
        logger.error(f"语音转文字失败: {e}")
        raise HTTPException(status_code=500, detail=f"语音识别失败: {str(e)[:100]}")


@router.post("/voice-command", summary="语音指令快速执行")
@limiter.limit("30/minute")
async def voice_command(
    request: Request,
    req: dict,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """语音转文字后，尝试匹配快捷指令直接执行"""
    from app.services.voice_command_service import VoiceCommandService

    text = (req.get("text") or "").strip()
    if not text:
        return {"matched": False}

    svc = VoiceCommandService(db, current_user.id)
    result = svc.try_execute(text)
    if result:
        return {"matched": True, **result}
    return {"matched": False}
