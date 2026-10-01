"""
POST /api/v1/tts/synthesize — 文本转 mp3.
WS   /api/v1/tts/stream — 增量文本转临时 PCM 分片.
GET  /api/v1/tts/voices — 列可选声色.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.auth import auth_service
from app.services.ai_consent import ai_user_scope, require_ai_consent
from app.services.realtime_tts import proxy_realtime_tts
from app.services.tts import cosyvoice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500, description="文本 (句级, 建议 <200 字)")
    voice_style: str = Field(default=cosyvoice.DEFAULT_VOICE_KEY, description="声色 key")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速倍率")


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    return token.strip() or None


@router.websocket("/stream", name="stream_tts")
async def stream_tts(websocket: WebSocket, db: Session = Depends(get_db)):
    """Stream transient PCM for one authenticated assistant response."""
    token = _bearer_token(websocket.headers.get("authorization"))
    payload = auth_service.decode_token(token) if token else None
    user_id = payload.get("sub") if payload else None
    try:
        current_user = auth_service.get_user_by_id(db, int(user_id)) if user_id else None
    except (TypeError, ValueError):
        current_user = None
    if not current_user:
        await websocket.close(code=4401, reason="未登录或登录已过期")
        return
    if not current_user.is_active or not current_user.is_approved:
        await websocket.close(code=4403, reason="账户不可用")
        return
    try:
        require_ai_consent(
            current_user.id,
            destination="wss://dashscope.aliyuncs.com/api-ws/v1/inference/",
        )
    except HTTPException:
        await websocket.close(code=4403, reason="请先确认 AI 数据使用授权")
        return

    voice_style = websocket.query_params.get("voice_style") or cosyvoice.DEFAULT_VOICE_KEY
    try:
        speed = float(websocket.query_params.get("speed") or 1.0)
    except ValueError:
        await websocket.close(code=4400, reason="语速参数无效")
        return

    await websocket.accept()
    logger.info("Realtime TTS session started - user_id=%s", current_user.id)
    try:
        with ai_user_scope(current_user.id):
            await proxy_realtime_tts(
                websocket.receive_json,
                websocket.send_json,
                voice_style=voice_style,
                speed=speed,
            )
    except HTTPException:
        await websocket.close(code=4403, reason="AI 数据使用授权已撤回或失效")
    except WebSocketDisconnect:
        logger.info("Realtime TTS client disconnected - user_id=%s", current_user.id)
    except (TimeoutError, ValueError) as exc:
        logger.warning(
            "Realtime TTS request rejected - user_id=%s error_type=%s",
            current_user.id,
            type(exc).__name__,
        )
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except (RuntimeError, WebSocketDisconnect):
            pass
    except Exception as exc:  # noqa: BLE001 - do not expose provider details
        logger.error(
            "Realtime TTS session failed - user_id=%s error_type=%s",
            current_user.id,
            type(exc).__name__,
        )
        try:
            await websocket.send_json({"type": "error", "message": "TTS 服务暂时不可用"})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        logger.info("Realtime TTS session ended - user_id=%s", current_user.id)


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
