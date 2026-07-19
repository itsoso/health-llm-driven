"""DashScope realtime ASR protocol helpers and WebSocket proxy session."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time
import uuid
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode

from app.config import settings


logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 4 * 1024 * 1024
MAX_CHUNK_BYTES = 128 * 1024
MAX_SESSION_SECONDS = 125
REALTIME_CONTEXT_TEXT = (
    "健康记录 饮食 用药 补剂 喝水 睡眠 运动 体重 腰围 心率 HRV "
    "血压 血糖 血氧 Garmin HealthKit 千卡 毫升 毫克"
)


def _event_id() -> str:
    return f"event_{uuid.uuid4().hex}"


def build_session_update_event(event_id: str | None = None) -> dict[str, Any]:
    return {
        "event_id": event_id or _event_id(),
        "type": "session.update",
        "session": {
            "input_audio_format": "pcm",
            "sample_rate": 16000,
            "input_audio_transcription": {
                "language": "zh",
                "corpus": {"text": REALTIME_CONTEXT_TEXT},
            },
            "turn_detection": None,
        },
    }


def build_audio_append_event(event_id: str, audio_base64: str) -> dict[str, str]:
    return {
        "event_id": event_id,
        "type": "input_audio_buffer.append",
        "audio": audio_base64,
    }


def normalize_server_event(raw: str | bytes) -> dict[str, str] | None:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"type": "error", "message": "云端语音服务返回了无效数据"}
    event_type = payload.get("type")
    if event_type == "conversation.item.input_audio_transcription.text":
        text = f"{payload.get('text') or ''}{payload.get('stash') or ''}".strip()
        return {"type": "partial", "text": text} if text else None
    if event_type == "conversation.item.input_audio_transcription.completed":
        text = str(payload.get("transcript") or "").strip()
        return {"type": "final", "text": text}
    if event_type == "session.updated":
        return {"type": "session_ready"}
    if event_type == "session.finished":
        return {"type": "done"}
    if event_type == "error":
        error = payload.get("error") or {}
        return {
            "type": "error",
            "message": str(error.get("message") or "云端语音识别失败"),
        }
    return None


def _upstream_url() -> str:
    base = settings.asr_realtime_base_url.rstrip("?")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'model': settings.asr_realtime_model})}"


async def _open_dashscope_socket():
    from websockets.asyncio.client import connect

    api_key = settings.tts_api_key or settings.llm_vision_api_key
    if not api_key:
        raise RuntimeError("DashScope API key is not configured")
    return await connect(
        _upstream_url(),
        additional_headers={"Authorization": f"Bearer {api_key}"},
        open_timeout=settings.asr_realtime_connect_timeout_seconds,
        close_timeout=3,
        max_size=2 * 1024 * 1024,
    )


async def proxy_realtime_asr(
    receive_json: Callable[[], Awaitable[dict[str, Any]]],
    send_json: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Proxy one authenticated mobile PCM session without persisting raw audio."""
    started_at = time.monotonic()
    pcm_buffer = bytearray()
    upstream = None
    upstream_reader: asyncio.Task[None] | None = None
    upstream_done = asyncio.Event()
    upstream_ready = asyncio.Event()
    final_sent = False
    upstream_error: str | None = None
    error_sent = False

    async def send_upstream_error(message: str) -> None:
        nonlocal error_sent
        if error_sent:
            return
        error_sent = True
        await send_json({"type": "error", "message": message})

    async def read_upstream() -> None:
        nonlocal final_sent, upstream_error
        assert upstream is not None
        try:
            async for raw in upstream:
                normalized = normalize_server_event(raw)
                if not normalized:
                    continue
                if normalized["type"] == "session_ready":
                    upstream_ready.set()
                    continue
                if normalized["type"] == "final":
                    final_sent = bool(normalized.get("text"))
                    normalized.update({
                        "provider": "dashscope_qwen_asr_realtime",
                        "model": settings.asr_realtime_model,
                        "duration_ms": max(0, round((time.monotonic() - started_at) * 1000)),
                    })
                if normalized["type"] == "done":
                    break
                if normalized["type"] == "error":
                    upstream_error = normalized.get("message") or "阿里云实时语音识别失败"
                    logger.warning("Realtime ASR upstream returned an error")
                    await send_upstream_error(upstream_error)
                    break
                await send_json(normalized)
        except Exception as exc:  # noqa: BLE001 - surface the single-provider failure to Mobile
            upstream_error = "阿里云实时语音连接中断"
            logger.warning(
                "Realtime ASR upstream ended - error_type=%s",
                type(exc).__name__,
            )
            await send_upstream_error(upstream_error)
        finally:
            upstream_done.set()

    try:
        try:
            upstream = await _open_dashscope_socket()
            await upstream.send(json.dumps(build_session_update_event(), ensure_ascii=False))
            upstream_reader = asyncio.create_task(read_upstream())
            await asyncio.wait_for(
                upstream_ready.wait(),
                timeout=settings.asr_realtime_connect_timeout_seconds,
            )
            await send_json({"type": "ready", "mode": "realtime"})
        except Exception as exc:  # noqa: BLE001 - the composer has one ASR provider
            logger.warning(
                "Realtime ASR unavailable - error_type=%s",
                type(exc).__name__,
            )
            await send_upstream_error("阿里云实时语音服务暂不可用，请稍后重试")
            return

        while True:
            if time.monotonic() - started_at > MAX_SESSION_SECONDS:
                raise TimeoutError("语音输入时间过长")
            message = await asyncio.wait_for(receive_json(), timeout=MAX_SESSION_SECONDS)
            message_type = message.get("type")
            if message_type == "cancel":
                return
            if message_type == "audio":
                encoded = str(message.get("audio") or "")
                try:
                    chunk = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError("音频数据格式无效")
                if not chunk or len(chunk) > MAX_CHUNK_BYTES:
                    raise ValueError("音频分片大小无效")
                if len(pcm_buffer) + len(chunk) > MAX_AUDIO_BYTES:
                    raise ValueError("语音输入时间过长")
                pcm_buffer.extend(chunk)
                if upstream_error:
                    await send_upstream_error(upstream_error)
                    return
                try:
                    await upstream.send(json.dumps(
                        build_audio_append_event(_event_id(), encoded),
                        ensure_ascii=False,
                    ))
                except Exception as exc:  # noqa: BLE001 - no provider switching in realtime ASR
                    logger.warning(
                        "Realtime ASR audio send failed - error_type=%s",
                        type(exc).__name__,
                    )
                    upstream_error = "阿里云实时语音连接中断"
                    await send_upstream_error(upstream_error)
                    return
                continue
            if message_type != "finish":
                raise ValueError("不支持的语音会话事件")
            if not pcm_buffer:
                raise ValueError("没有收到可识别的语音")
            if upstream_error:
                await send_upstream_error(upstream_error)
                return
            await upstream.send(json.dumps({"event_id": _event_id(), "type": "input_audio_buffer.commit"}))
            await upstream.send(json.dumps({"event_id": _event_id(), "type": "session.finish"}))
            try:
                await asyncio.wait_for(
                    upstream_done.wait(),
                    timeout=settings.asr_realtime_final_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                logger.warning("Realtime ASR final result timed out")
                raise TimeoutError("等待阿里云实时语音最终结果超时") from exc
            if upstream_error:
                await send_upstream_error(upstream_error)
                return
            await send_json({"type": "done"})
            return
    finally:
        pcm_buffer.clear()
        if upstream_reader and not upstream_reader.done():
            upstream_reader.cancel()
        if upstream is not None:
            await upstream.close()
