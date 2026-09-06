"""
POST /api/v1/tts/synthesize — 文本转 mp3.
GET  /api/v1/tts/voices — 列可选声色.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_required
from app.models.user import User
from app.services.tts import cosyvoice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500, description="文本 (句级, 建议 <200 字)")
    voice_style: str = Field(default=cosyvoice.DEFAULT_VOICE_KEY, description="声色 key")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速倍率")


@router.post("/synthesize")
async def synthesize(
    req: TTSRequest,
    current_user: User = Depends(get_current_user_required),
):
    try:
        audio = await cosyvoice.synthesize(
            text=req.text,
            voice_style=req.voice_style,
            speed=req.speed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.warning("TTS 失败 user=%s error_type=%s", current_user.id, type(e).__name__)
        raise HTTPException(status_code=503, detail="TTS 服务暂时不可用")

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Length": str(len(audio)),
        },
    )


@router.get("/voices")
def list_voices(_: User = Depends(get_current_user_required)):
    return {"voices": cosyvoice.list_voices(), "default": cosyvoice.DEFAULT_VOICE_KEY}
