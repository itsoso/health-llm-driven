import base64

import pytest

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
