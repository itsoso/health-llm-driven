"""Alibaba Model Studio media provider boundary for Xiaoba.

Images use the standard Model Studio credential. Videos can use either that
credential or the TokenPlan AIGC surface. This module intentionally contains no
persistence or user ownership logic; callers supply already-authorized source
data/URLs and own job state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import logging
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit

import httpx

from app.services.aigc_media_capabilities import validate_video_spec


logger = logging.getLogger(__name__)

IMAGE_MODELS = frozenset({"wan2.7-image", "wan2.7-image-pro"})
VIDEO_KINDS = frozenset({"text_to_video", "image_to_video"})
TOKENPLAN_AIGC_DEFAULT_BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1"
HAPPYHORSE_TEXT_TO_VIDEO_MODELS = frozenset({"happyhorse-1.1-t2v", "happyhorse-1.0-t2v"})
HAPPYHORSE_IMAGE_TO_VIDEO_MODELS = frozenset({"happyhorse-1.1-i2v", "happyhorse-1.0-i2v"})
HAPPYHORSE_VIDEO_MODELS = HAPPYHORSE_TEXT_TO_VIDEO_MODELS | HAPPYHORSE_IMAGE_TO_VIDEO_MODELS
VIDEO_PROVIDERS = frozenset({"model_studio", "tokenplan"})


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


def normalize_api_base_url(value: str, *, allow_token_plan: bool = False) -> str:
    """Return an AIGC API v1 endpoint and reject OpenAI-compatible paths."""
    base = str(value or "").strip().rstrip("/")
    parsed = urlsplit(base)
    host = (parsed.hostname or "").lower()
    if not base or parsed.scheme != "https" or not host:
        raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_BASE_URL must be an HTTPS Model Studio endpoint")
    is_token_plan = host == "token-plan.cn-beijing.maas.aliyuncs.com"
    if is_token_plan and not allow_token_plan:
        raise AIGCMediaConfigurationError("Token Plan endpoint is only valid for the configured video provider")
    if "coding.dashscope" in host:
        raise AIGCMediaConfigurationError("Coding Plan credentials cannot be used for AIGC media")
    if not (host.endswith("aliyuncs.com") or host.endswith("aliyun.com")):
        raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_BASE_URL must point to Alibaba Cloud Model Studio")
    if is_token_plan:
        if parsed.path.rstrip("/") != "/api/v1":
            raise AIGCMediaConfigurationError("Token Plan AIGC base URL must end with /api/v1")
        return base
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
        video_api_key: str | None = None,
        video_api_base_url: str | None = None,
        video_provider: str = "model_studio",
        blocked_api_keys: Iterable[str | None] = (),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        candidate_key = str(api_key or "").strip()
        # TokenPlan media credentials are valid only on the dedicated video
        # route. Never let one become the standard image credential.
        if any(
            secret and hmac.compare_digest(candidate_key, str(secret).strip())
            for secret in blocked_api_keys
        ):
            raise AIGCMediaConfigurationError("Token Plan credentials cannot be used for AIGC media")
        if image_model not in IMAGE_MODELS:
            raise AIGCMediaConfigurationError("Unsupported Wan image model")
        self._api_key = candidate_key
        self._api_base_url = normalize_api_base_url(api_base_url)
        normalized_video_provider = str(video_provider or "").strip().lower()
        if normalized_video_provider not in VIDEO_PROVIDERS:
            raise AIGCMediaConfigurationError("Unsupported AIGC video provider")
        candidate_video_key = (
            str(video_api_key or "").strip()
            if normalized_video_provider == "tokenplan"
            else str(video_api_key or candidate_key).strip()
        )
        if (
            normalized_video_provider == "tokenplan"
            and candidate_video_key
            and not candidate_video_key.startswith("sk-sp-")
        ):
            raise AIGCMediaConfigurationError("Token Plan AIGC video credential must use the sk-sp- prefix")
        self.video_provider = normalized_video_provider
        self._video_api_key = candidate_video_key
        default_video_base = (
            TOKENPLAN_AIGC_DEFAULT_BASE_URL
            if normalized_video_provider == "tokenplan"
            else self._api_base_url
        )
        self._video_api_base_url = normalize_api_base_url(
            video_api_base_url or default_video_base,
            allow_token_plan=normalized_video_provider == "tokenplan",
        )
        self.image_model = image_model
        self.text_to_video_model = str(text_to_video_model).strip()
        self.image_to_video_model = str(image_to_video_model).strip()
        if not self.text_to_video_model or not self.image_to_video_model:
            raise AIGCMediaConfigurationError("Wan video model IDs are required")
        if normalized_video_provider == "tokenplan":
            if self.text_to_video_model not in HAPPYHORSE_TEXT_TO_VIDEO_MODELS:
                raise AIGCMediaConfigurationError("Token Plan requires a supported HappyHorse text-to-video model")
            if self.image_to_video_model not in HAPPYHORSE_IMAGE_TO_VIDEO_MODELS:
                raise AIGCMediaConfigurationError("Token Plan requires a supported HappyHorse image-to-video model")
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AIGCMediaConfigurationError("DASHSCOPE_AIGC_API_KEY is not configured for image generation")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @property
    def _video_headers(self) -> dict[str, str]:
        if not self._video_api_key:
            raise AIGCMediaConfigurationError("AIGC video API key is not configured")
        return {
            "Authorization": f"Bearer {self._video_api_key}",
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
        resolution: str = "720P",
        model: str | None = None,
    ) -> AIGCTask:
        if kind not in VIDEO_KINDS:
            raise AIGCMediaConfigurationError("Unsupported AIGC video kind")
        if kind == "image_to_video" and not str(source_url or "").strip():
            raise AIGCMediaConfigurationError("Image-to-video requires an authorized source image")
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
        try:
            validate_video_spec(
                model=model,
                kind=kind,
                duration_seconds=duration_seconds,
                ratio=ratio,
                resolution=resolution,
            )
        except ValueError as exc:
            raise AIGCMediaConfigurationError(str(exc)) from exc
        parameters: dict[str, Any] = {
            "resolution": resolution.upper(),
            "duration": duration_seconds,
            "watermark": False,
        }
        if model in HAPPYHORSE_VIDEO_MODELS:
            # HappyHorse I2V preserves the first frame's aspect ratio and does
            # not accept ratio/prompt_extend. T2V accepts ratio directly.
            if kind == "text_to_video":
                parameters["ratio"] = ratio
        else:
            parameters.update({"ratio": ratio, "prompt_extend": True})
        data = await self._post_json(
            "/services/aigc/video-generation/video-synthesis",
            {
                "model": model,
                "input": input_payload,
                "parameters": parameters,
            },
            async_request=True,
            video_model=model,
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

    async def get_task(self, task_id: str, *, model: str | None = None) -> dict[str, Any]:
        safe_task_id = str(task_id or "").strip()
        if not safe_task_id:
            raise AIGCMediaConfigurationError("task_id is required")
        try:
            api_base_url, headers = self._video_route(model, allow_historical_standard=True)
            response = await self._http_client.get(
                f"{api_base_url}/tasks/{safe_task_id}",
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise AIGCMediaProviderError("Model Studio task query failed") from exc
        return self._response_json(response, operation="task_query")

    async def cancel_task(self, task_id: str, *, model: str | None = None) -> None:
        safe_task_id = str(task_id or "").strip()
        if not safe_task_id:
            raise AIGCMediaConfigurationError("task_id is required")
        try:
            api_base_url, headers = self._video_route(model, allow_historical_standard=True)
            response = await self._http_client.delete(
                f"{api_base_url}/tasks/{safe_task_id}",
                headers=headers,
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
        video_model: str | None = None,
    ) -> dict[str, Any]:
        api_base_url, selected_headers = (
            self._video_route(video_model)
            if video_model
            else (self._api_base_url, self._headers)
        )
        headers = dict(selected_headers)
        if async_request:
            headers["X-DashScope-Async"] = "enable"
        response: httpx.Response | None = None
        for attempt in range(2):
            try:
                response = await self._http_client.post(
                    f"{api_base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                # A transport failure is not proof that the provider rejected
                # the task. Never replay it automatically because the first
                # request may already have created a billed provider task.
                raise AIGCMediaProviderIndeterminateError(
                    "Model Studio media request outcome is unknown"
                ) from exc
            if response.status_code != 401 or attempt > 0:
                break
            # A 401 is an explicit provider rejection: no task was accepted and
            # one immediate replay cannot duplicate billing. This absorbs a
            # transient credential/cache mismatch between provider gateways.
            logger.warning(
                "[aigc_media] provider media_generation auth rejected; retrying once"
            )
        assert response is not None
        return self._response_json(response, operation="media_generation")

    def _video_route(
        self,
        model: str | None,
        *,
        allow_historical_standard: bool = False,
    ) -> tuple[str, dict[str, str]]:
        selected_model = str(model or self.text_to_video_model).strip()
        if self.video_provider == "tokenplan":
            if selected_model in HAPPYHORSE_VIDEO_MODELS:
                return self._video_api_base_url, self._video_headers
            if allow_historical_standard and selected_model.startswith("wan"):
                return self._api_base_url, self._headers
            raise AIGCMediaConfigurationError("Unsupported Token Plan video model")
        return self._api_base_url, self._headers

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
