"""Bounded, consent-gated streaming TTS bridge for Mobile voice chat."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Awaitable, Callable, Protocol

from app.services.ai_consent import require_ai_consent
from app.services.tts import cosyvoice


logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
MAX_FRAGMENT_CHARS = 500
MAX_TEXT_CHARS = 4000
MAX_SESSION_SECONDS = 180
MAX_AUDIO_EVENTS = 256
_DASHSCOPE_DESTINATION = "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"


class StreamingSynthesizer(Protocol):
    def append(self, text: str) -> None: ...
    def complete(self) -> None: ...
    def cancel(self) -> None: ...


class _DashScopeStreamingSynthesizer:
    def __init__(
        self,
        *,
        voice_style: str,
        speed: float,
        on_audio: Callable[[bytes], None],
        on_error: Callable[[str], None],
    ) -> None:
        import dashscope
        from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

        require_ai_consent(destination=dashscope.base_websocket_api_url)
        key = cosyvoice._resolve_api_key()
        if not key:
            raise RuntimeError("TTS API key 未配置")
        dashscope.api_key = key

        voice_id = cosyvoice._resolve_voice_id(voice_style)
        model = cosyvoice._resolve_model(voice_id)

        class Callback(ResultCallback):
            def on_data(self, data: bytes) -> None:
                if data:
                    on_audio(bytes(data))

            def on_error(self, message: object) -> None:
                on_error(str(message or "TTS provider error"))

        self._synth = SpeechSynthesizer(
            model=model,
            voice=voice_id,
            format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            speech_rate=speed,
            callback=Callback(),
        )

    def append(self, text: str) -> None:
        self._synth.streaming_call(text)

    def complete(self) -> None:
        self._synth.streaming_complete(complete_timeout_millis=60_000)

    def cancel(self) -> None:
        self._synth.streaming_cancel(complete_timeout_millis=3_000)


def _create_synthesizer(
    *,
    voice_style: str,
    speed: float,
    on_audio: Callable[[bytes], None],
    on_error: Callable[[str], None],
) -> StreamingSynthesizer:
    return _DashScopeStreamingSynthesizer(
        voice_style=voice_style,
        speed=speed,
        on_audio=on_audio,
        on_error=on_error,
    )


async def proxy_realtime_tts(
    receive_json: Callable[[], Awaitable[dict[str, Any]]],
    send_json: Callable[[dict[str, Any]], Awaitable[None]],
    *,
    voice_style: str = cosyvoice.DEFAULT_VOICE_KEY,
    speed: float = 1.0,
) -> None:
    """Stream text into CosyVoice and relay transient PCM chunks to one client."""
    require_ai_consent(destination=_DASHSCOPE_DESTINATION)
    if not 0.5 <= speed <= 2.0:
        raise ValueError("语速参数无效")

    loop = asyncio.get_running_loop()
    audio_events: asyncio.Queue[tuple[str, bytes | str | None]] = asyncio.Queue(
        maxsize=MAX_AUDIO_EVENTS,
    )
    provider_error: list[str] = []
    overflowed = False

    def enqueue(kind: str, payload: bytes | str | None) -> None:
        nonlocal overflowed
        if overflowed:
            return
        try:
            audio_events.put_nowait((kind, payload))
        except asyncio.QueueFull:
            overflowed = True
            provider_error.append("TTS 音频缓冲区已满")

    def on_audio(data: bytes) -> None:
        loop.call_soon_threadsafe(enqueue, "audio", data)

    def on_error(message: str) -> None:
        provider_error.append(message)
        loop.call_soon_threadsafe(enqueue, "error", message)

    synth = _create_synthesizer(
        voice_style=voice_style,
        speed=speed,
        on_audio=on_audio,
        on_error=on_error,
    )
    started_at = time.monotonic()
    total_chars = 0
    provider_started = False
    cancelled = False

    async def relay_audio() -> None:
        while True:
            kind, payload = await audio_events.get()
            if kind == "stop":
                return
            if kind == "error":
                await send_json({"type": "error", "message": "TTS 服务暂时不可用"})
                continue
            assert isinstance(payload, bytes)
            await send_json({
                "type": "audio",
                "audio": base64.b64encode(payload).decode("ascii"),
            })

    relay_task = asyncio.create_task(relay_audio())
    await send_json({
        "type": "ready",
        "encoding": "pcm_s16le",
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
    })

    try:
        while True:
            remaining = MAX_SESSION_SECONDS - (time.monotonic() - started_at)
            if remaining <= 0:
                raise TimeoutError("TTS 会话时间过长")
            message = await asyncio.wait_for(receive_json(), timeout=remaining)
            message_type = message.get("type")
            if message_type == "cancel":
                cancelled = True
                if provider_started:
                    await asyncio.to_thread(synth.cancel)
                return
            if message_type == "append":
                require_ai_consent(destination=_DASHSCOPE_DESTINATION)
                raw_text = str(message.get("text") or "")
                text = cosyvoice._normalize_for_tts(raw_text).strip()
                if not text:
                    raise ValueError("TTS 文本不能为空")
                if len(text) > MAX_FRAGMENT_CHARS or total_chars + len(text) > MAX_TEXT_CHARS:
                    raise ValueError("TTS 文本过长")
                total_chars += len(text)
                provider_started = True
                await asyncio.to_thread(synth.append, text)
                if overflowed:
                    raise RuntimeError("TTS 音频缓冲区已满")
                continue
            if message_type != "finish":
                raise ValueError("不支持的 TTS 会话事件")
            if not provider_started:
                raise ValueError("没有收到可合成的文本")
            require_ai_consent(destination=_DASHSCOPE_DESTINATION)
            await asyncio.to_thread(synth.complete)
            await audio_events.put(("stop", None))
            await relay_task
            if provider_error:
                raise RuntimeError("TTS provider failed")
            await send_json({"type": "done"})
            return
    finally:
        if provider_started and not cancelled and not relay_task.done():
            try:
                await asyncio.to_thread(synth.cancel)
            except Exception as exc:  # noqa: BLE001 - cleanup must not hide the primary failure
                logger.warning("Realtime TTS cleanup failed - error_type=%s", type(exc).__name__)
        if not relay_task.done():
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass
        while not audio_events.empty():
            audio_events.get_nowait()
