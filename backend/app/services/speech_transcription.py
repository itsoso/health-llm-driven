"""Speech-to-text provider routing for short mobile voice messages."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
import os
import tempfile
from typing import Callable

from app.config import settings
from app.services.ai_consent import guard_openai_client, require_ai_consent
from fastapi import HTTPException


logger = logging.getLogger(__name__)


class SpeechTranscriptionUnavailable(RuntimeError):
    """All configured ASR providers failed or no provider is configured."""


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    model: str


_MIME_BY_FORMAT = {
    "aac": "audio/aac",
    "caf": "audio/x-caf",
    "m4a": "audio/mp4",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "webm": "audio/webm",
}


def _normalized_format(audio_format: str) -> str:
    value = str(audio_format or "m4a").strip().lower().lstrip(".")
    return value if value in _MIME_BY_FORMAT else "m4a"


def _extract_dashscope_text(response: object) -> str:
    output = getattr(response, "output", None) or {}
    if not isinstance(output, dict):
        try:
            output = dict(output)
        except (TypeError, ValueError):
            output = {}
    direct_text = output.get("text")
    if direct_text:
        return str(direct_text).strip()
    choices = output.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ).strip()
    return ""


def _transcribe_with_dashscope(
    audio_bytes: bytes,
    audio_format: str,
    *,
    api_key: str,
    model: str,
    base_url: str,
    timeout_seconds: float,
) -> TranscriptionResult:
    require_ai_consent(destination=base_url)
    import dashscope

    dashscope.base_http_api_url = base_url.rstrip("/")
    normalized_format = _normalized_format(audio_format)
    data_uri = (
        f"data:{_MIME_BY_FORMAT[normalized_format]};base64,"
        f"{base64.b64encode(audio_bytes).decode('ascii')}"
    )
    response = dashscope.MultiModalConversation.call(
        api_key=api_key,
        model=model,
        messages=[{"role": "user", "content": [{"audio": data_uri}]}],
        result_format="message",
        asr_options={"language": "zh", "enable_itn": True},
        request_timeout=timeout_seconds,
    )
    status_code = getattr(response, "status_code", None)
    if status_code != 200:
        code = str(getattr(response, "code", "provider_error"))[:80]
        raise RuntimeError(f"DashScope ASR failed ({status_code}, {code})")
    return TranscriptionResult(
        text=_extract_dashscope_text(response),
        provider="dashscope_qwen_asr",
        model=model,
    )


def _transcribe_with_openai(
    audio_bytes: bytes,
    audio_format: str,
    *,
    api_key: str,
    model: str,
    base_url: str | None,
    timeout_seconds: float,
) -> TranscriptionResult:
    require_ai_consent(destination=base_url or "https://api.openai.com/v1")
    from openai import OpenAI

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = guard_openai_client(OpenAI(
        **client_kwargs,
        timeout=timeout_seconds,
        max_retries=0,
    ))
    normalized_format = _normalized_format(audio_format)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{normalized_format}", delete=False) as handle:
            handle.write(audio_bytes)
            temp_path = handle.name
        with open(temp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                language="zh",
            )
        return TranscriptionResult(
            text=str(getattr(transcript, "text", "") or "").strip(),
            provider="openai_whisper",
            model=model,
        )
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def transcribe_audio_bytes(audio_bytes: bytes, audio_format: str) -> TranscriptionResult:
    """Transcribe with the first healthy provider, preferring the in-quota China route."""
    providers: list[tuple[str, Callable[[], TranscriptionResult]]] = []
    dashscope_key = settings.tts_api_key or settings.llm_vision_api_key
    if dashscope_key:
        providers.append((
            "dashscope_qwen_asr",
            lambda: _transcribe_with_dashscope(
                audio_bytes,
                audio_format,
                api_key=dashscope_key,
                model=settings.asr_dashscope_model,
                base_url=settings.asr_dashscope_base_url,
                timeout_seconds=settings.asr_provider_timeout_seconds,
            ),
        ))
    if settings.asr_openai_fallback_enabled and settings.openai_api_key:
        providers.append((
            "openai_whisper",
            lambda: _transcribe_with_openai(
                audio_bytes,
                audio_format,
                api_key=settings.openai_api_key,
                model=settings.asr_openai_model,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.asr_provider_timeout_seconds,
            ),
        ))

    if not providers:
        raise SpeechTranscriptionUnavailable("No ASR provider configured")

    for provider_name, transcribe in providers:
        try:
            result = transcribe()
            if not result.text.strip():
                raise RuntimeError("ASR provider returned empty text")
            return result
        except HTTPException:
            # Permission failures are not provider outages and must never fail over.
            raise
        except Exception as exc:  # noqa: BLE001 - fail over to the next configured provider
            logger.warning(
                "ASR provider failed - provider=%s error_type=%s",
                provider_name,
                type(exc).__name__,
            )
    raise SpeechTranscriptionUnavailable("All configured ASR providers failed")
