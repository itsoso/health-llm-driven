"""Model Studio Wan media provider boundary for Xiaoba.

Token Plan is an OpenAI-compatible text-only subscription surface. AIGC media
uses a separate Model Studio pay-as-you-go credential and never exposes it to a
client. This module intentionally contains no persistence or user ownership
logic; callers supply already-authorized source data/URLs and own job state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import logging
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit

import httpx


logger = logging.getLogger(__name__)

IMAGE_MODELS = frozenset({"wan2.7-image", "wan2.7-image-pro"})
VIDEO_KINDS = frozenset({"text_to_video", "image_to_video"})


class AIGCMediaConfigurationError(ValueError):
    """Raised before a request would use an unsupported AIGC configuration."""


class AIGCMediaProviderError(RuntimeError):
    """Safe provider error that never embeds a prompt, media URL, or API key."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "provider_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class AIGCMediaProviderIndeterminateError(AIGCMediaProviderError):
    """The provider may have accepted a billed task but its response was lost."""


@dataclass(frozen=True)
class AIGCTask:
    task_id: str
    status: str


def normalize_api_base_url(value: str) -> str:
    """Return a Model Studio API v1 endpoint, rejecting subscription endpoints."""
    base = str(value or "").strip().rstrip("/")
    parsed = urlsplit(base)
    host = (parsed.hostname or "").lower()
    if not base or parsed.scheme != "https" or not host:
        raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_BASE_URL must be an HTTPS Model Studio endpoint")
    if "token-plan" in host or "coding.dashscope" in host:
        raise AIGCMediaConfigurationError("Token Plan/Coding Plan credentials cannot be used for AIGC media")
    if not (host.endswith("aliyuncs.com") or host.endswith("aliyun.com")):
        raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_BASE_URL must point to Alibaba Cloud Model Studio")
    if not parsed.path or parsed.path == "/":
        base = f"{base}/api/v1"
    elif not parsed.path.rstrip("/").endswith("/api/v1"):
        raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_BASE_URL must end with /api/v1")
    return base


class AIGCMediaProvider:
    """Small HTTP adapter for the current Wan 2.7 image and video APIs."""

    def __init__(
        self,
        *,
        api_key: str | None,
        api_base_url: str,
        image_model: str = "wan2.7-image",
        text_to_video_model: str = "wan2.7-t2v-2026-06-12",
        image_to_video_model: str = "wan2.7-i2v-2026-04-25",
        blocked_api_keys: Iterable[str | None] = (),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not str(api_key or "").strip():
            raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_API_KEY is not configured")
        candidate_key = str(api_key).strip()
        # A Token Plan credential is a subscription credential for text models,
        # not an AIGC entitlement.  Endpoint validation alone is insufficient:
        # the same secret could otherwise be pasted into the AIGC setting.
        if any(
            secret and hmac.compare_digest(candidate_key, str(secret).strip())
            for secret in blocked_api_keys
        ):
            raise AIGCMediaConfigurationError("Token Plan credentials cannot be used for AIGC media")
        if image_model not in IMAGE_MODELS:
            raise AIGCMediaConfigurationError("Unsupported Wan image model")
        self._api_key = candidate_key
        self._api_base_url = normalize_api_base_url(api_base_url)
        self.image_model = image_model
        self.text_to_video_model = str(text_to_video_model).strip()
        self.image_to_video_model = str(image_to_video_model).strip()
        if not self.text_to_video_model or not self.image_to_video_model:
            raise AIGCMediaConfigurationError("Wan video model IDs are required")
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def build_image_request(
        self,
        *,
        prompt: str,
        image_data_uri: str | None = None,
        model: str | None = None,
        size: str = "2K",
    ) -> tuple[str, dict[str, Any]]:
        selected_model = str(model or self.image_model).strip()
        if selected_model not in IMAGE_MODELS:
            raise AIGCMediaConfigurationError("Unsupported Wan image model")
        normalized_prompt = _bounded_text(prompt, maximum=5000, field="prompt")
        content: list[dict[str, str]] = []
        if image_data_uri:
            normalized_image = str(image_data_uri).strip()
            if not normalized_image.startswith("data:image/") or ";base64," not in normalized_image:
                raise AIGCMediaConfigurationError("Image generation requires a data:image base64 source")
            content.append({"image": normalized_image})
        content.append({"text": normalized_prompt})
        return (
            "/services/aigc/multimodal-generation/generation",
            {
                "model": selected_model,
                "input": {"messages": [{"role": "user", "content": content}]},
                "parameters": {"size": size, "n": 1, "watermark": False},
            },
        )

    async def generate_image(
        self,
        *,
        prompt: str,
        image_data_uri: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        path, payload = self.build_image_request(
            prompt=prompt,
            image_data_uri=image_data_uri,
            model=model,
        )
        data = await self._post_json(path, payload)
        urls = _extract_result_urls(data)
        if not urls:
            # The provider acknowledged a successful request but did not give
            # us an asset reference. Retrying could create a second billable
            # request, so persist an indeterminate job instead.
            raise AIGCMediaProviderIndeterminateError("Model Studio image outcome is unknown")
        return urls

    async def create_video_task(
        self,
        *,
        kind: Literal["text_to_video", "image_to_video"],
        prompt: str,
        source_url: str | None = None,
        duration_seconds: int = 5,
        ratio: str = "9:16",
        model: str | None = None,
    ) -> AIGCTask:
        if kind not in VIDEO_KINDS:
            raise AIGCMediaConfigurationError("Unsupported AIGC video kind")
        if kind == "image_to_video" and not str(source_url or "").strip():
            raise AIGCMediaConfigurationError("Image-to-video requires an authorized source image")
        if duration_seconds < 2 or duration_seconds > 15:
            raise AIGCMediaConfigurationError("Video duration must be between 2 and 15 seconds")
        if ratio not in {"16:9", "9:16", "1:1", "4:3", "3:4"}:
            raise AIGCMediaConfigurationError("Unsupported video aspect ratio")
        input_payload: dict[str, Any] = {"prompt": _bounded_text(prompt, maximum=5000, field="prompt")}
        if kind == "image_to_video":
            input_payload["media"] = [{"type": "first_frame", "url": str(source_url)}]
        model = str(
            model or (self.image_to_video_model if kind == "image_to_video" else self.text_to_video_model)
        ).strip()
        if not model:
            raise AIGCMediaConfigurationError("Wan video model ID is required")
        data = await self._post_json(
            "/services/aigc/video-generation/video-synthesis",
            {
                "model": model,
                "input": input_payload,
                "parameters": {
                    "resolution": "720P",
                    "ratio": ratio,
                    "duration": duration_seconds,
                    "prompt_extend": True,
                    "watermark": False,
                },
            },
            async_request=True,
        )
        output = data.get("output") if isinstance(data, dict) else None
        task_id = str((output or {}).get("task_id") or "").strip()
        status = str((output or {}).get("task_status") or "PENDING").strip().upper()
        if not task_id:
            # A 2xx response without the durable task ID cannot prove that the
            # provider rejected the request. Treat it as unknown to prevent an
            # automatic or user-guided duplicate submission.
            raise AIGCMediaProviderIndeterminateError("Model Studio video outcome is unknown")
        return AIGCTask(task_id=task_id, status=status)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        safe_task_id = str(task_id or "").strip()
        if not safe_task_id:
            raise AIGCMediaConfigurationError("task_id is required")
        try:
            response = await self._http_client.get(
                f"{self._api_base_url}/tasks/{safe_task_id}",
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise AIGCMediaProviderError("Model Studio task query failed") from exc
        return self._response_json(response, operation="task_query")

    async def cancel_task(self, task_id: str) -> None:
        safe_task_id = str(task_id or "").strip()
        if not safe_task_id:
            raise AIGCMediaConfigurationError("task_id is required")
        try:
            response = await self._http_client.delete(
                f"{self._api_base_url}/tasks/{safe_task_id}",
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise AIGCMediaProviderError("Model Studio task cancellation failed") from exc
        self._response_json(response, operation="task_cancel")

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        async_request: bool = False,
    ) -> dict[str, Any]:
        headers = dict(self._headers)
        if async_request:
            headers["X-DashScope-Async"] = "enable"
        try:
            response = await self._http_client.post(
                f"{self._api_base_url}{path}",
                headers=headers,
                json=payload,
            )
        except httpx.HTTPError as exc:
            # A transport failure is not proof that the provider rejected the
            # task. The job layer records an indeterminate submission and
            # refuses automatic replay to prevent duplicate billing.
            raise AIGCMediaProviderIndeterminateError(
                "Model Studio media request outcome is unknown"
            ) from exc
        return self._response_json(response, operation="media_generation")

    @staticmethod
    def _response_json(response: httpx.Response, *, operation: str) -> dict[str, Any]:
        if response.status_code >= 400:
            status_code = int(response.status_code)
            if status_code in {401, 403}:
                error_code = "provider_auth_failed"
            elif status_code == 429:
                error_code = "provider_rate_limited"
            elif status_code >= 500:
                error_code = "provider_unavailable"
            else:
                error_code = "provider_request_rejected"
            logger.warning(
                "[aigc_media] provider %s failed status=%s code=%s",
                operation,
                status_code,
                error_code,
            )
            raise AIGCMediaProviderError(
                "Model Studio media request was rejected",
                error_code=error_code,
                status_code=status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            if operation == "media_generation":
                raise AIGCMediaProviderIndeterminateError(
                    "Model Studio media request outcome is unknown"
                ) from exc
            raise AIGCMediaProviderError("Model Studio returned an invalid response") from exc
        if not isinstance(payload, dict):
            if operation == "media_generation":
                raise AIGCMediaProviderIndeterminateError(
                    "Model Studio media request outcome is unknown"
                )
            raise AIGCMediaProviderError("Model Studio returned an invalid response")
        return payload


def _bounded_text(value: str, *, maximum: int, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AIGCMediaConfigurationError(f"{field} is required")
    if len(text) > maximum:
        raise AIGCMediaConfigurationError(f"{field} exceeds the provider limit")
    return text


def _extract_result_urls(payload: dict[str, Any]) -> list[str]:
    output = payload.get("output") if isinstance(payload, dict) else None
    urls: list[str] = []
    if not isinstance(output, dict):
        return urls

    # Wan video tasks return a single output.video_url, while image generation
    # returns output.results[].url. Normalize both provider result shapes here.
    video_url = str(output.get("video_url") or "").strip()
    if video_url.startswith(("https://", "http://")):
        urls.append(video_url)

    results = output.get("results")
    if not isinstance(results, list):
        return urls
    for result in results:
        url = str((result or {}).get("url") or "").strip() if isinstance(result, dict) else ""
        if url.startswith(("https://", "http://")):
            urls.append(url)
    return urls
