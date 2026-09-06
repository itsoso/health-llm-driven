"""External media providers must not receive private data without consent."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.services import realtime_speech_transcription as realtime
from app.services import speech_transcription as speech
from app.services.tts import cosyvoice


def deny(*args, **kwargs):
    raise HTTPException(status_code=403, detail={"code": "ai_consent_required"})


def test_short_audio_denial_precedes_vendor_upload(monkeypatch):
    import dashscope

    vendor = Mock(return_value=SimpleNamespace(status_code=200, output={"text": "合成测试"}))
    monkeypatch.setattr(dashscope.MultiModalConversation, "call", vendor)
    monkeypatch.setattr(speech, "require_ai_consent", deny, raising=False)
    with pytest.raises(HTTPException) as error:
        speech._transcribe_with_dashscope(
            b"synthetic audio", "wav", api_key="test", model="test",
            base_url="https://dashscope.aliyuncs.com/api/v1", timeout_seconds=1,
        )
    assert error.value.status_code == 403
    vendor.assert_not_called()


@pytest.mark.asyncio
async def test_tts_denial_precedes_cache_and_synthesis(monkeypatch):
    vendor = Mock(return_value=b"synthetic mp3")
    cache = Mock()
    monkeypatch.setattr(cosyvoice, "_synth_blocking", vendor)
    monkeypatch.setattr(cosyvoice, "_cache_path", cache)
    monkeypatch.setattr(cosyvoice, "require_ai_consent", deny, raising=False)
    with pytest.raises(HTTPException):
        await cosyvoice.synthesize("合成健康文本")
    cache.assert_not_called()
    vendor.assert_not_called()


@pytest.mark.asyncio
async def test_realtime_denial_precedes_provider_connection(monkeypatch):
    connect = AsyncMock(side_effect=RuntimeError("must not connect"))
    receive = AsyncMock(return_value={"type": "cancel"})
    send = AsyncMock()
    monkeypatch.setattr(realtime, "_open_dashscope_socket", connect)
    monkeypatch.setattr(realtime, "require_ai_consent", deny, raising=False)
    with pytest.raises(HTTPException):
        await realtime.proxy_realtime_asr(receive, send)
    connect.assert_not_called()
    receive.assert_not_called()
