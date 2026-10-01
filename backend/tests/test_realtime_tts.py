import asyncio
import base64

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

from app.api import tts
from app.services import realtime_tts


@pytest.fixture(autouse=True)
def _authorized_protocol_unit_boundary(monkeypatch):
    monkeypatch.setattr(realtime_tts, "require_ai_consent", lambda **kwargs: None)


class FakeSynthesizer:
    def __init__(self, on_audio, on_error):
        self.on_audio = on_audio
        self.on_error = on_error
        self.appended = []
        self.completed = False
        self.cancelled = False

    def append(self, text):
        self.appended.append(text)
        self.on_audio(b"\x01\x00\x02\x00")

    def complete(self):
        self.completed = True

    def cancel(self):
        self.cancelled = True


def test_registers_authenticated_realtime_tts_websocket():
    route = next(
        item for item in tts.router.routes
        if getattr(item, "path", "") == "/tts/stream"
    )

    assert route.name == "stream_tts"


def test_extracts_only_bearer_tokens_for_realtime_tts():
    assert tts._bearer_token("Bearer jwt-value") == "jwt-value"
    assert tts._bearer_token("Basic abc") is None
    assert tts._bearer_token(None) is None


def test_realtime_tts_websocket_rejects_unauthenticated_client(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/tts/stream"):
            pass

    assert exc_info.value.code == 4401


def test_realtime_tts_websocket_accepts_authenticated_consented_user(
    client, auth_user_and_headers, monkeypatch
):
    _user, headers = auth_user_and_headers
    captured = {}

    async def fake_proxy(_receive_json, send_json, **kwargs):
        captured.update(kwargs)
        await send_json({"type": "ready", "sample_rate": 24000})

    monkeypatch.setattr(tts, "require_ai_consent", lambda *args, **kwargs: None)
    monkeypatch.setattr(tts, "proxy_realtime_tts", fake_proxy)

    with client.websocket_connect(
        "/api/v1/tts/stream?voice_style=warm_female&speed=1.1",
        headers=headers,
    ) as websocket:
        assert websocket.receive_json() == {"type": "ready", "sample_rate": 24000}

    assert captured == {"voice_style": "warm_female", "speed": 1.1}


def test_realtime_tts_websocket_rejects_missing_ai_consent(
    client, auth_user_and_headers, monkeypatch
):
    _user, headers = auth_user_and_headers

    def deny_consent(*args, **kwargs):
        raise HTTPException(status_code=403, detail="consent required")

    monkeypatch.setattr(tts, "require_ai_consent", deny_consent)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/tts/stream", headers=headers):
            pass

    assert exc_info.value.code == 4403


@pytest.mark.asyncio
async def test_streams_pcm_chunks_without_persisting_audio(monkeypatch):
    incoming = iter([
        {"type": "append", "text": "今天先喝一杯水，"},
        {"type": "append", "text": "再去散步。"},
        {"type": "finish"},
    ])
    outgoing = []
    created = []

    async def receive_json():
        return next(incoming)

    async def send_json(payload):
        outgoing.append(payload)

    def create_synthesizer(*, voice_style, speed, on_audio, on_error):
        synth = FakeSynthesizer(on_audio, on_error)
        created.append((voice_style, speed, synth))
        return synth

    monkeypatch.setattr(realtime_tts, "_create_synthesizer", create_synthesizer)

    await realtime_tts.proxy_realtime_tts(
        receive_json,
        send_json,
        voice_style="warm_female",
        speed=1.1,
    )

    _, _, synth = created[0]
    assert synth.appended == ["今天先喝一杯水，", "再去散步。"]
    assert synth.completed is True
    assert outgoing[0] == {
        "type": "ready",
        "encoding": "pcm_s16le",
        "sample_rate": 24000,
        "channels": 1,
    }
    assert {
        "type": "audio",
        "audio": base64.b64encode(b"\x01\x00\x02\x00").decode("ascii"),
    } in outgoing
    assert outgoing[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_cancel_stops_provider_without_completing(monkeypatch):
    incoming = iter([
        {"type": "append", "text": "这段会被打断"},
        {"type": "cancel"},
    ])
    outgoing = []
    created = []

    async def receive_json():
        return next(incoming)

    async def send_json(payload):
        outgoing.append(payload)

    def create_synthesizer(**kwargs):
        synth = FakeSynthesizer(kwargs["on_audio"], kwargs["on_error"])
        created.append(synth)
        return synth

    monkeypatch.setattr(realtime_tts, "_create_synthesizer", create_synthesizer)

    await realtime_tts.proxy_realtime_tts(receive_json, send_json)

    assert created[0].cancelled is True
    assert created[0].completed is False
    assert {"type": "done"} not in outgoing


@pytest.mark.asyncio
async def test_rejects_oversized_stream_before_provider_receives_it(monkeypatch):
    incoming = iter([{"type": "append", "text": "字" * (realtime_tts.MAX_TEXT_CHARS + 1)}])
    created = []

    async def receive_json():
        return next(incoming)

    async def send_json(_payload):
        return None

    def create_synthesizer(**kwargs):
        synth = FakeSynthesizer(kwargs["on_audio"], kwargs["on_error"])
        created.append(synth)
        return synth

    monkeypatch.setattr(realtime_tts, "_create_synthesizer", create_synthesizer)

    with pytest.raises(ValueError, match="文本过长"):
        await realtime_tts.proxy_realtime_tts(receive_json, send_json)

    assert created[0].appended == []


@pytest.mark.asyncio
async def test_downstream_failure_cancels_provider_without_queue_deadlock(monkeypatch):
    incoming = iter([
        {"type": "append", "text": "需要停止的回复"},
        {"type": "finish"},
    ])
    created = []

    async def receive_json():
        return next(incoming)

    audio_send_attempts = 0

    async def send_json(payload):
        nonlocal audio_send_attempts
        if payload.get("type") == "audio":
            audio_send_attempts += 1
            raise RuntimeError("client disconnected")

    class BurstSynthesizer(FakeSynthesizer):
        def append(self, text):
            self.appended.append(text)

        def complete(self):
            self.completed = True
            for _ in range(realtime_tts.MAX_AUDIO_EVENTS + 8):
                self.on_audio(b"\x01\x00" * 64)

    def create_synthesizer(**kwargs):
        synth = BurstSynthesizer(kwargs["on_audio"], kwargs["on_error"])
        created.append(synth)
        return synth

    monkeypatch.setattr(realtime_tts, "_create_synthesizer", create_synthesizer)

    with pytest.raises(RuntimeError, match="downstream"):
        await asyncio.wait_for(
            realtime_tts.proxy_realtime_tts(receive_json, send_json),
            timeout=1,
        )

    assert audio_send_attempts == 1
    assert created[0].cancelled is True


@pytest.mark.asyncio
async def test_rejects_provider_audio_chunk_over_byte_limit(monkeypatch):
    incoming = iter([
        {"type": "append", "text": "异常音频分片"},
        {"type": "finish"},
    ])
    created = []

    async def receive_json():
        return next(incoming)

    async def send_json(_payload):
        return None

    class OversizedChunkSynthesizer(FakeSynthesizer):
        def append(self, text):
            self.appended.append(text)
            self.on_audio(b"\x00" * (realtime_tts.MAX_AUDIO_CHUNK_BYTES + 2))

    def create_synthesizer(**kwargs):
        synth = OversizedChunkSynthesizer(kwargs["on_audio"], kwargs["on_error"])
        created.append(synth)
        return synth

    monkeypatch.setattr(realtime_tts, "_create_synthesizer", create_synthesizer)

    with pytest.raises(RuntimeError, match="audio limit"):
        await realtime_tts.proxy_realtime_tts(receive_json, send_json)

    assert created[0].cancelled is True


@pytest.mark.asyncio
async def test_rejects_provider_audio_over_session_byte_limit(monkeypatch):
    incoming = iter([
        {"type": "append", "text": "累计音频过长"},
        {"type": "finish"},
    ])
    created = []

    async def receive_json():
        return next(incoming)

    async def send_json(_payload):
        return None

    class SessionOverflowSynthesizer(FakeSynthesizer):
        def append(self, text):
            self.appended.append(text)
            self.on_audio(b"\x00" * 4)
            self.on_audio(b"\x00" * 4)

    def create_synthesizer(**kwargs):
        synth = SessionOverflowSynthesizer(kwargs["on_audio"], kwargs["on_error"])
        created.append(synth)
        return synth

    monkeypatch.setattr(realtime_tts, "MAX_AUDIO_BYTES", 6)
    monkeypatch.setattr(realtime_tts, "_create_synthesizer", create_synthesizer)

    with pytest.raises(RuntimeError, match="audio limit"):
        await realtime_tts.proxy_realtime_tts(receive_json, send_json)

    assert created[0].cancelled is True
