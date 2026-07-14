import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api import speech as speech_api
from app.schemas.chat import TranscribeRequest
from app.services import speech_transcription


def test_prefers_dashscope_asr_when_its_key_is_configured(monkeypatch):
    dashscope_call = MagicMock(return_value=speech_transcription.TranscriptionResult(
        text="记录打了一个喷嚏",
        provider="dashscope_qwen_asr",
        model="qwen3-asr-flash",
    ))
    openai_call = MagicMock()
    monkeypatch.setattr(speech_transcription, "_transcribe_with_dashscope", dashscope_call)
    monkeypatch.setattr(speech_transcription, "_transcribe_with_openai", openai_call)
    monkeypatch.setattr(
        speech_transcription,
        "settings",
        SimpleNamespace(
            llm_vision_api_key="dash-key",
            tts_api_key=None,
            openai_api_key="openai-key",
            openai_base_url="https://proxy.example/v1",
            asr_dashscope_model="qwen3-asr-flash",
            asr_dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            asr_openai_model="whisper-1",
            asr_openai_fallback_enabled=True,
            asr_provider_timeout_seconds=12.0,
        ),
    )

    result = speech_transcription.transcribe_audio_bytes(b"audio", "m4a")

    assert result.text == "记录打了一个喷嚏"
    dashscope_call.assert_called_once()
    assert dashscope_call.call_args.kwargs["timeout_seconds"] == 12.0
    openai_call.assert_not_called()


def test_falls_back_to_openai_when_dashscope_fails(monkeypatch):
    monkeypatch.setattr(
        speech_transcription,
        "_transcribe_with_dashscope",
        MagicMock(side_effect=RuntimeError("dashscope unavailable")),
    )
    openai_call = MagicMock(return_value=speech_transcription.TranscriptionResult(
        text="备用识别成功",
        provider="openai_whisper",
        model="whisper-1",
    ))
    monkeypatch.setattr(speech_transcription, "_transcribe_with_openai", openai_call)
    monkeypatch.setattr(
        speech_transcription,
        "settings",
        SimpleNamespace(
            llm_vision_api_key="dash-key",
            tts_api_key=None,
            openai_api_key="openai-key",
            openai_base_url=None,
            asr_dashscope_model="qwen3-asr-flash",
            asr_dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            asr_openai_model="whisper-1",
            asr_openai_fallback_enabled=True,
            asr_provider_timeout_seconds=12.0,
        ),
    )

    result = speech_transcription.transcribe_audio_bytes(b"audio", "m4a")

    assert result.provider == "openai_whisper"
    openai_call.assert_called_once()
    assert openai_call.call_args.kwargs["timeout_seconds"] == 12.0


def test_falls_back_when_dashscope_returns_empty_text(monkeypatch):
    monkeypatch.setattr(
        speech_transcription,
        "_transcribe_with_dashscope",
        MagicMock(return_value=speech_transcription.TranscriptionResult(
            text="  ",
            provider="dashscope_qwen_asr",
            model="qwen3-asr-flash",
        )),
    )
    openai_call = MagicMock(return_value=speech_transcription.TranscriptionResult(
        text="备用识别成功",
        provider="openai_whisper",
        model="whisper-1",
    ))
    monkeypatch.setattr(speech_transcription, "_transcribe_with_openai", openai_call)
    monkeypatch.setattr(
        speech_transcription,
        "settings",
        SimpleNamespace(
            llm_vision_api_key="dash-key",
            tts_api_key=None,
            openai_api_key="openai-key",
            openai_base_url=None,
            asr_dashscope_model="qwen3-asr-flash",
            asr_dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            asr_openai_model="whisper-1",
            asr_openai_fallback_enabled=True,
            asr_provider_timeout_seconds=12.0,
        ),
    )

    result = speech_transcription.transcribe_audio_bytes(b"audio", "m4a")

    assert result.provider == "openai_whisper"
    openai_call.assert_called_once()


def test_reports_unavailable_only_after_all_configured_providers_fail(monkeypatch):
    monkeypatch.setattr(
        speech_transcription,
        "_transcribe_with_dashscope",
        MagicMock(side_effect=RuntimeError("dashscope unavailable")),
    )
    monkeypatch.setattr(
        speech_transcription,
        "_transcribe_with_openai",
        MagicMock(side_effect=RuntimeError("openai quota")),
    )
    monkeypatch.setattr(
        speech_transcription,
        "settings",
        SimpleNamespace(
            llm_vision_api_key="dash-key",
            tts_api_key=None,
            openai_api_key="openai-key",
            openai_base_url=None,
            asr_dashscope_model="qwen3-asr-flash",
            asr_dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            asr_openai_model="whisper-1",
            asr_openai_fallback_enabled=True,
            asr_provider_timeout_seconds=12.0,
        ),
    )

    with pytest.raises(speech_transcription.SpeechTranscriptionUnavailable):
        speech_transcription.transcribe_audio_bytes(b"audio", "m4a")


def test_openai_fallback_is_disabled_without_explicit_privacy_switch(monkeypatch):
    monkeypatch.setattr(
        speech_transcription,
        "_transcribe_with_dashscope",
        MagicMock(side_effect=RuntimeError("dashscope unavailable")),
    )
    openai_call = MagicMock()
    monkeypatch.setattr(speech_transcription, "_transcribe_with_openai", openai_call)
    monkeypatch.setattr(
        speech_transcription,
        "settings",
        SimpleNamespace(
            llm_vision_api_key="dash-key",
            tts_api_key=None,
            openai_api_key="openai-key",
            openai_base_url="https://proxy.example/v1",
            asr_dashscope_model="qwen3-asr-flash",
            asr_dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            asr_openai_model="whisper-1",
            asr_openai_fallback_enabled=False,
            asr_provider_timeout_seconds=12.0,
        ),
    )

    with pytest.raises(speech_transcription.SpeechTranscriptionUnavailable):
        speech_transcription.transcribe_audio_bytes(b"audio", "m4a")

    openai_call.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_endpoint_enforces_total_deadline(monkeypatch):
    async def delayed_to_thread(*_args, **_kwargs):
        await asyncio.sleep(0.05)

    monkeypatch.setattr(speech_api.asyncio, "to_thread", delayed_to_thread)
    monkeypatch.setattr(speech_api.settings, "asr_total_timeout_seconds", 0.001)
    req = TranscribeRequest(
        audio_base64=base64.b64encode(b"audio").decode("ascii"),
        audio_format="m4a",
    )

    with pytest.raises(HTTPException) as exc_info:
        handler = getattr(speech_api.transcribe_audio, "__wrapped__", speech_api.transcribe_audio)
        await handler(MagicMock(), req, MagicMock())

    assert exc_info.value.status_code == 504
