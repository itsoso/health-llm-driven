import asyncio
import base64
import json

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
            "input_audio_transcription": {
                "language": "zh",
                "corpus": {
                    "text": (
                        "健康记录 饮食 用药 补剂 喝水 睡眠 运动 体重 腰围 心率 HRV "
                        "血压 血糖 血氧 Garmin HealthKit 千卡 毫升 毫克"
                    ),
                },
            },
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


def test_normalizes_session_ready_for_proxy_handshake():
    event = normalize_server_event(json.dumps({"type": "session.updated"}))

    assert event == {"type": "session_ready"}


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
async def test_does_not_switch_to_a_second_asr_provider_when_realtime_is_unavailable(monkeypatch):
    pcm = b"\x01\x00" * 160
    incoming = iter([
        {"type": "audio", "audio": base64.b64encode(pcm).decode("ascii")},
        {"type": "finish"},
    ])
    outgoing = []
    async def unavailable_socket():
        raise RuntimeError("realtime unavailable")

    async def receive_json():
        return next(incoming)

    async def send_json(payload):
        outgoing.append(payload)

    monkeypatch.setattr(realtime_speech, "_open_dashscope_socket", unavailable_socket)

    await realtime_speech.proxy_realtime_asr(receive_json, send_json)

    assert outgoing == [{
        "type": "error",
        "message": "阿里云实时语音服务暂不可用，请稍后重试",
    }]


@pytest.mark.asyncio
async def test_reports_an_upstream_disconnect_once_after_realtime_session_is_ready(monkeypatch):
    class BrokenUpstream:
        def __init__(self):
            self.sent = []
            self.ready_event_pending = True
            self.closed = False

        async def send(self, payload):
            self.sent.append(json.loads(payload))

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.ready_event_pending:
                self.ready_event_pending = False
                return json.dumps({"type": "session.updated"})
            raise RuntimeError("upstream socket dropped")

        async def close(self):
            self.closed = True

    upstream = BrokenUpstream()
    outgoing = []

    async def open_socket():
        return upstream

    async def receive_json():
        await asyncio.sleep(0.01)
        return {"type": "cancel"}

    async def send_json(payload):
        outgoing.append(payload)

    monkeypatch.setattr(realtime_speech, "_open_dashscope_socket", open_socket)

    await realtime_speech.proxy_realtime_asr(receive_json, send_json)

    assert outgoing.count({
        "type": "error",
        "message": "阿里云实时语音连接中断",
    }) == 1
    assert all(payload["type"] in {"ready", "error"} for payload in outgoing)
    assert upstream.closed is True
