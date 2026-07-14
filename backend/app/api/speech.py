"""语音 API — 语音转文字 + 语音指令（从 chat.py 独立出来）"""
import base64
import binascii
import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.user import User
from app.schemas.chat import TranscribeRequest, TranscribeResponse
from app.api.deps import get_current_user_required
from app.config import settings
from app.services.speech_transcription import (
    SpeechTranscriptionUnavailable,
    transcribe_audio_bytes,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["speech"])

limiter = Limiter(key_func=get_remote_address)


def _transcript_confidence(text: str) -> str:
    clean = (text or "").strip()
    if not clean:
        return "low"
    if len(clean) >= 24 and any(ch in clean for ch in "，。；;"):
        return "high"
    return "medium" if len(clean) >= 4 else "low"


@router.post("/transcribe", response_model=TranscribeResponse, summary="语音转文字")
@limiter.limit("10/minute")
async def transcribe_audio(
    request: Request,
    req: TranscribeRequest,
    current_user: User = Depends(get_current_user_required),
):
    """将短语音转为文字;按隐私配置使用有时限的 ASR 通道。"""
    started_at = time.monotonic()
    try:
        audio_bytes = base64.b64decode(req.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="音频数据格式无效")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频内容为空")
    if len(audio_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="音频过长，请控制在 5 分钟内")

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(transcribe_audio_bytes, audio_bytes, req.audio_format),
            timeout=settings.asr_total_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.error("语音转文字超时: total ASR deadline exceeded")
        raise HTTPException(status_code=504, detail="语音识别超时，请稍后重试")
    except SpeechTranscriptionUnavailable:
        logger.error("语音转文字失败: all ASR providers unavailable")
        raise HTTPException(status_code=503, detail="语音识别服务暂不可用，请稍后重试")

    duration_ms = max(0, round((time.monotonic() - started_at) * 1000))
    return TranscribeResponse(
        text=result.text,
        provider=result.provider,
        model=result.model,
        duration_ms=duration_ms,
        confidence=_transcript_confidence(result.text),
    )


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
