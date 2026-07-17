import base64
import json
from types import SimpleNamespace

import pytest

from app.services import realtime_speech_transcription as realtime_speech
from app.services.realtime_speech_transcription import (
    build_audio_append_event,
    build_session_update_event,
    normalize_server_event,
)
from app.api import speech


def test_builds_manual_pcm_session_for_push_to_talk():
    event = build_session_update_event("event-1")

    assert event == {
        "event_id": "event-1",
        "type": "session.update",
        "session": {
            "input_audio_format": "pcm",
            "sample_rate": 16000,
            "input_audio_transcription": {"language": "zh"},
            "turn_detection": None,
        },
    }


def test_wraps_pcm_chunk_without_changing_audio_bytes():
    event = build_audio_append_event("event-2", "cGNt")

    assert event == {
        "event_id": "event-2",
        "type": "input_audio_buffer.append",
        "audio": "cGNt",
    }


def test_normalizes_partial_text_and_stash_for_mobile():
    event = normalize_server_event(json.dumps({
        "type": "conversation.item.input_audio_transcription.text",
        "text": "记录今天",
        "stash": "喝水",
    }))

    assert event == {"type": "partial", "text": "记录今天喝水"}


def test_normalizes_final_transcript_for_mobile():
    event = normalize_server_event(json.dumps({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "记录今天喝水 500 毫升",
    }))

    assert event == {"type": "final", "text": "记录今天喝水 500 毫升"}


def test_registers_authenticated_realtime_transcription_websocket():
    route = next(
        item for item in speech.router.routes
        if getattr(item, "path", "") == "/chat/transcribe/realtime"
    )

    assert route.name == "transcribe_audio_realtime"


def test_extracts_only_bearer_tokens_for_realtime_audio():
    assert speech._bearer_token("Bearer jwt-value") == "jwt-value"
    assert speech._bearer_token("Basic abc") is None
    assert speech._bearer_token(None) is None


@pytest.mark.asyncio
async def test_uses_final_cloud_asr_when_realtime_upstream_is_unavailable(monkeypatch):
    pcm = b"\x01\x00" * 160
    incoming = iter([
        {"type": "audio", "audio": base64.b64encode(pcm).decode("ascii")},
        {"type": "finish"},
    ])
    outgoing = []
    transcribed = []

    async def unavailable_socket():
        raise RuntimeError("realtime unavailable")

    async def receive_json():
        return next(incoming)

    async def send_json(payload):
        outgoing.append(payload)

    def transcribe(wav_bytes, extension):
        transcribed.append((wav_bytes, extension))
        return SimpleNamespace(
            text="记录今天喝水 500 毫升",
            provider="dashscope_qwen_asr",
            model="qwen3-asr-flash",
        )

    monkeypatch.setattr(realtime_speech, "_open_dashscope_socket", unavailable_socket)
    monkeypatch.setattr(realtime_speech, "transcribe_audio_bytes", transcribe)

    await realtime_speech.proxy_realtime_asr(receive_json, send_json)

    assert outgoing[0] == {"type": "ready", "mode": "final_fallback"}
    assert outgoing[-2]["type"] == "final"
    assert outgoing[-2]["text"] == "记录今天喝水 500 毫升"
    assert outgoing[-1] == {"type": "done"}
    assert transcribed[0][0].startswith(b"RIFF")
    assert transcribed[0][1] == "wav"
