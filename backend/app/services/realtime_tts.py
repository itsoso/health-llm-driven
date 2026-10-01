"""Bounded, consent-gated streaming TTS bridge for Mobile voice chat."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Awaitable, Callable, NoReturn, Protocol

from app.services.ai_consent import require_ai_consent
from app.services.tts import cosyvoice


logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
MAX_FRAGMENT_CHARS = 500
MAX_TEXT_CHARS = 4000
MAX_SESSION_SECONDS = 180
MAX_AUDIO_EVENTS = 256
BYTES_PER_SECOND = SAMPLE_RATE * 2
MAX_AUDIO_CHUNK_BYTES = 256 * 1024
MAX_AUDIO_BYTES = BYTES_PER_SECOND * MAX_SESSION_SECONDS
PROVIDER_CANCEL_TIMEOUT_SECONDS = 3
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
    audio_bytes = 0

    def enqueue(kind: str, payload: bytes | str | None) -> None:
        nonlocal audio_bytes, overflowed
        if overflowed:
            return
        if kind == "audio":
            if not isinstance(payload, bytes) or len(payload) % 2 != 0:
                overflowed = True
                provider_error.append("TTS invalid PCM audio")
                return
            if len(payload) > MAX_AUDIO_CHUNK_BYTES:
                overflowed = True
                provider_error.append("TTS audio limit exceeded")
                return
            if audio_bytes + len(payload) > MAX_AUDIO_BYTES:
                overflowed = True
                provider_error.append("TTS audio limit exceeded")
                return
            audio_bytes += len(payload)
        elif kind == "error":
            provider_error.append(str(payload or "TTS provider failed"))
        try:
            audio_events.put_nowait((kind, payload))
        except asyncio.QueueFull:
            overflowed = True
            provider_error.append("TTS 音频缓冲区已满")

    def on_audio(data: bytes) -> None:
        loop.call_soon_threadsafe(enqueue, "audio", data)

    def on_error(message: str) -> None:
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
    session_succeeded = False

    async def relay_audio() -> None:
        while True:
            kind, payload = await audio_events.get()
            if kind == "stop":
                return
            if kind == "error":
                await send_json({"type": "error", "message": "TTS 服务暂时不可用"})
                raise RuntimeError("TTS provider failed")
            assert isinstance(payload, bytes)
            await send_json({
                "type": "audio",
                "audio": base64.b64encode(payload).decode("ascii"),
            })
            # Keep downstream delivery close to realtime playback speed so a
            # fast provider cannot move the whole response into Mobile memory.
            await asyncio.sleep(len(payload) / BYTES_PER_SECOND)

    relay_task = asyncio.create_task(relay_audio())

    def remaining_seconds() -> float:
        remaining = MAX_SESSION_SECONDS - (time.monotonic() - started_at)
        if remaining <= 0:
            raise TimeoutError("TTS 会话时间过长")
        return remaining

    async def raise_relay_failure() -> NoReturn:
        try:
            await relay_task
        except Exception as exc:
            raise RuntimeError("TTS downstream failed") from exc
        raise RuntimeError("TTS downstream stopped")

    async def receive_or_relay_failure() -> dict[str, Any]:
        receive_task = asyncio.create_task(receive_json())
        done, _ = await asyncio.wait(
            {receive_task, relay_task},
            timeout=remaining_seconds(),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
            raise TimeoutError("TTS 会话时间过长")
        if relay_task in done:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
            await raise_relay_failure()
        return receive_task.result()

    async def finish_relay() -> None:
        stop_task = asyncio.create_task(audio_events.put(("stop", None)))
        done, _ = await asyncio.wait(
            {stop_task, relay_task},
            timeout=remaining_seconds(),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            raise TimeoutError("TTS 音频发送超时")
        if relay_task in done:
            if not stop_task.done():
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)
                await raise_relay_failure()
            # The relay can consume the stop sentinel and complete in the same
            # event-loop turn as the queue put. That is the expected success
            # path; awaiting it still propagates a concurrent send failure.
            await stop_task
            await relay_task
            return
        await stop_task
        await asyncio.wait_for(relay_task, timeout=remaining_seconds())

    try:
        await asyncio.wait_for(
            send_json({
                "type": "ready",
                "encoding": "pcm_s16le",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
            }),
            timeout=remaining_seconds(),
        )
        while True:
            message = await receive_or_relay_failure()
            message_type = message.get("type")
            if message_type == "cancel":
                if provider_started:
                    await asyncio.wait_for(
                        asyncio.to_thread(synth.cancel),
                        timeout=min(PROVIDER_CANCEL_TIMEOUT_SECONDS, remaining_seconds()),
                    )
                cancelled = True
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
                await asyncio.wait_for(
                    asyncio.to_thread(synth.append, text),
                    timeout=remaining_seconds(),
                )
                await asyncio.sleep(0)
                if relay_task.done():
                    await raise_relay_failure()
                if provider_error:
                    raise RuntimeError(provider_error[-1])
                continue
            if message_type != "finish":
                raise ValueError("不支持的 TTS 会话事件")
            if not provider_started:
                raise ValueError("没有收到可合成的文本")
            require_ai_consent(destination=_DASHSCOPE_DESTINATION)
            await asyncio.wait_for(
                asyncio.to_thread(synth.complete),
                timeout=remaining_seconds(),
            )
            await asyncio.sleep(0)
            if relay_task.done():
                await raise_relay_failure()
            if provider_error:
                raise RuntimeError(provider_error[-1])
            await finish_relay()
            await asyncio.wait_for(
                send_json({"type": "done"}),
                timeout=remaining_seconds(),
            )
            session_succeeded = True
            return
    finally:
        if provider_started and not cancelled and not session_succeeded:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(synth.cancel),
                    timeout=PROVIDER_CANCEL_TIMEOUT_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001 - cleanup must not hide the primary failure
                logger.warning("Realtime TTS cleanup failed - error_type=%s", type(exc).__name__)
        if not relay_task.done():
            relay_task.cancel()
        await asyncio.gather(relay_task, return_exceptions=True)
        while not audio_events.empty():
            audio_events.get_nowait()
