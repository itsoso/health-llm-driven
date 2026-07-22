import json

import httpx
import pytest


@pytest.mark.asyncio
async def test_provider_auth_rejection_has_a_stable_safe_error_code():
    from app.services.aigc_media_service import AIGCMediaProvider, AIGCMediaProviderError

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "InvalidApiKey", "message": "secret provider detail"})

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(AIGCMediaProviderError) as captured:
            await provider.create_video_task(
                kind="text_to_video",
                prompt="生成一段 5 秒健康饮食氛围短视频",
            )
    finally:
        await provider.aclose()

    assert captured.value.error_code == "provider_auth_failed"
    assert captured.value.status_code == 401
    assert "secret provider detail" not in str(captured.value)


def test_accepts_token_plan_aigc_endpoint_but_rejects_openai_compatible_endpoint():
    from app.services.aigc_media_service import (
        AIGCMediaConfigurationError,
        normalize_api_base_url,
    )

    assert normalize_api_base_url(
        "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        allow_token_plan=True,
    ) == "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1"
    with pytest.raises(AIGCMediaConfigurationError, match="/api/v1"):
        normalize_api_base_url(
            "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            allow_token_plan=True,
        )


def test_aigc_provider_rejects_reusing_token_plan_credential():
    from app.services.aigc_media_service import AIGCMediaConfigurationError, AIGCMediaProvider

    with pytest.raises(AIGCMediaConfigurationError, match="Token Plan"):
        AIGCMediaProvider(
            api_key="token-plan-secret",
            blocked_api_keys=("token-plan-secret",),
            api_base_url="https://dashscope.aliyuncs.com/api/v1",
        )


def test_token_plan_video_provider_requires_subscription_credential():
    from app.services.aigc_media_service import AIGCMediaConfigurationError, AIGCMediaProvider

    with pytest.raises(AIGCMediaConfigurationError, match="sk-sp-"):
        AIGCMediaProvider(
            api_key="test-payg-key",
            api_base_url="https://dashscope.aliyuncs.com/api/v1",
            video_api_key="sk-standard-key",
            video_api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
            video_provider="tokenplan",
        )


def test_token_plan_video_provider_rejects_non_happyhorse_default_models():
    from app.services.aigc_media_service import AIGCMediaConfigurationError, AIGCMediaProvider

    with pytest.raises(AIGCMediaConfigurationError, match="HappyHorse text-to-video"):
        AIGCMediaProvider(
            api_key="test-payg-key",
            api_base_url="https://dashscope.aliyuncs.com/api/v1",
            video_api_key="sk-sp-test-token-plan-key",
            video_api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
            video_provider="tokenplan",
            text_to_video_model="wan2.7-t2v-2026-06-12",
            image_to_video_model="happyhorse-1.1-i2v",
        )


@pytest.mark.asyncio
async def test_token_plan_video_route_never_falls_back_for_an_unknown_model():
    from app.services.aigc_media_service import AIGCMediaConfigurationError, AIGCMediaProvider

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        video_api_key="sk-sp-test-token-plan-key",
        video_api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        video_provider="tokenplan",
        text_to_video_model="happyhorse-1.1-t2v",
        image_to_video_model="happyhorse-1.1-i2v",
    )
    try:
        with pytest.raises(AIGCMediaConfigurationError, match="Unsupported Token Plan video model"):
            await provider.get_task("unknown-task", model="unexpected-video-model")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_image_generation_reports_its_own_missing_key_when_video_is_unconfigured():
    from app.services.aigc_media_service import AIGCMediaConfigurationError, AIGCMediaProvider

    provider = AIGCMediaProvider(
        api_key=None,
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        video_api_key=None,
        video_provider="tokenplan",
        text_to_video_model="happyhorse-1.1-t2v",
        image_to_video_model="happyhorse-1.1-i2v",
    )
    try:
        with pytest.raises(AIGCMediaConfigurationError, match="image generation"):
            await provider.generate_image(prompt="生成一张早餐海报")
    finally:
        await provider.aclose()


def test_builds_wan27_image_request_with_private_image_as_data_uri():
    from app.services.aigc_media_service import AIGCMediaProvider

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
    )

    path, payload = provider.build_image_request(
        prompt="把这张健康早餐照片做成清爽的竖屏封面",
        image_data_uri="data:image/jpeg;base64,aGVsbG8=",
        model="wan2.7-image",
    )

    assert path == "/services/aigc/multimodal-generation/generation"
    assert payload["model"] == "wan2.7-image"
    content = payload["input"]["messages"][0]["content"]
    assert content == [
        {"image": "data:image/jpeg;base64,aGVsbG8="},
        {"text": "把这张健康早餐照片做成清爽的竖屏封面"},
    ]
    assert payload["parameters"] == {"size": "2K", "n": 1, "watermark": False}


@pytest.mark.asyncio
async def test_creates_wan27_image_to_video_asynchronous_task():
    from app.services.aigc_media_service import AIGCMediaProvider

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output": {"task_id": "task-123", "task_status": "PENDING"}})

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        created = await provider.create_video_task(
            kind="image_to_video",
            prompt="把参考图片做成 5 秒竖屏晨间准备短视频",
            source_url="https://example.invalid/private-source.jpg?signature=temporary",
            duration_seconds=5,
            ratio="9:16",
        )
    finally:
        await provider.aclose()

    assert created.task_id == "task-123"
    assert created.status == "PENDING"
    assert captured["url"].endswith("/services/aigc/video-generation/video-synthesis")
    assert captured["headers"]["x-dashscope-async"] == "enable"
    assert captured["body"] == {
        "model": "wan2.7-i2v-2026-04-25",
        "input": {
            "prompt": "把参考图片做成 5 秒竖屏晨间准备短视频",
            "media": [{"type": "first_frame", "url": "https://example.invalid/private-source.jpg?signature=temporary"}],
        },
        "parameters": {
            "resolution": "720P",
            "ratio": "9:16",
            "duration": 5,
            "prompt_extend": True,
            "watermark": False,
        },
    }


@pytest.mark.asyncio
async def test_creates_wan27_text_to_video_with_the_versioned_default_model():
    from app.services.aigc_media_service import AIGCMediaProvider

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output": {"task_id": "task-456", "task_status": "PENDING"}})

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        created = await provider.create_video_task(
            kind="text_to_video",
            prompt="生成一段 5 秒晨间拉伸演示视频",
        )
    finally:
        await provider.aclose()

    assert created.task_id == "task-456"
    assert captured["body"]["model"] == "wan2.7-t2v-2026-06-12"


@pytest.mark.asyncio
async def test_creates_happyhorse_video_through_token_plan_aigc_endpoint():
    from app.services.aigc_media_service import AIGCMediaProvider

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output": {"task_id": "hh-task-1", "task_status": "PENDING"}})

    provider = AIGCMediaProvider(
        api_key=None,
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        video_api_key="sk-sp-test-token-plan-key",
        video_api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        video_provider="tokenplan",
        text_to_video_model="happyhorse-1.1-t2v",
        image_to_video_model="happyhorse-1.1-i2v",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        created = await provider.create_video_task(
            kind="text_to_video",
            prompt="生成一段 5 秒健康饮食氛围短视频",
            duration_seconds=5,
            ratio="9:16",
        )
    finally:
        await provider.aclose()

    assert created.task_id == "hh-task-1"
    assert captured["url"] == (
        "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/"
        "services/aigc/video-generation/video-synthesis"
    )
    assert captured["authorization"] == "Bearer sk-sp-test-token-plan-key"
    assert captured["body"] == {
        "model": "happyhorse-1.1-t2v",
        "input": {"prompt": "生成一段 5 秒健康饮食氛围短视频"},
        "parameters": {
            "resolution": "720P",
            "ratio": "9:16",
            "duration": 5,
            "watermark": False,
        },
    }


@pytest.mark.asyncio
async def test_happyhorse_image_to_video_uses_first_frame_without_ratio():
    from app.services.aigc_media_service import AIGCMediaProvider

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output": {"task_id": "hh-task-2", "task_status": "PENDING"}})

    provider = AIGCMediaProvider(
        api_key=None,
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        video_api_key="sk-sp-test-token-plan-key",
        video_api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        video_provider="tokenplan",
        text_to_video_model="happyhorse-1.1-t2v",
        image_to_video_model="happyhorse-1.1-i2v",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        await provider.create_video_task(
            kind="image_to_video",
            prompt="让早餐照片产生轻微自然运镜",
            source_url="https://health.example.com/private/source.jpg?sig=short-lived",
            duration_seconds=5,
            ratio="9:16",
        )
    finally:
        await provider.aclose()

    assert captured["body"] == {
        "model": "happyhorse-1.1-i2v",
        "input": {
            "prompt": "让早餐照片产生轻微自然运镜",
            "media": [{
                "type": "first_frame",
                "url": "https://health.example.com/private/source.jpg?sig=short-lived",
            }],
        },
        "parameters": {
            "resolution": "720P",
            "duration": 5,
            "watermark": False,
        },
    }


@pytest.mark.asyncio
async def test_poll_routes_happyhorse_and_historical_wan_tasks_to_their_credential_domains():
    from app.services.aigc_media_service import AIGCMediaProvider

    captured: list[tuple[str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        video_api_key="sk-sp-test-token-plan-key",
        video_api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        video_provider="tokenplan",
        text_to_video_model="happyhorse-1.1-t2v",
        image_to_video_model="happyhorse-1.1-i2v",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        await provider.get_task("hh-task", model="happyhorse-1.1-t2v")
        await provider.get_task("wan-task", model="wan2.7-t2v-2026-06-12")
    finally:
        await provider.aclose()

    assert captured == [
        (
            "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/tasks/hh-task",
            "Bearer sk-sp-test-token-plan-key",
        ),
        (
            "https://dashscope.aliyuncs.com/api/v1/tasks/wan-task",
            "Bearer test-payg-key",
        ),
    ]


@pytest.mark.asyncio
async def test_video_submission_retries_one_explicit_401_rejection_before_failing():
    from app.services.aigc_media_service import AIGCMediaProvider

    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                401,
                json={"code": "InvalidApiKey", "message": "authorization temporarily unavailable"},
            )
        return httpx.Response(
            200,
            json={"output": {"task_id": "task-after-auth-retry", "task_status": "PENDING"}},
        )

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        created = await provider.create_video_task(
            kind="text_to_video",
            prompt="生成一段晚间健康回顾短视频",
        )
    finally:
        await provider.aclose()

    assert created.task_id == "task-after-auth-retry"
    assert attempts == 2


@pytest.mark.asyncio
async def test_malformed_success_response_is_indeterminate_not_retryable_failure():
    from app.services.aigc_media_service import (
        AIGCMediaProvider,
        AIGCMediaProviderIndeterminateError,
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(AIGCMediaProviderIndeterminateError, match="outcome is unknown"):
            await provider.generate_image(prompt="生成一张早餐备餐步骤图")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_video_success_response_without_task_id_is_indeterminate_not_retryable_failure():
    from app.services.aigc_media_service import (
        AIGCMediaProvider,
        AIGCMediaProviderIndeterminateError,
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": {"task_status": "PENDING"}})

    provider = AIGCMediaProvider(
        api_key="test-payg-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(AIGCMediaProviderIndeterminateError, match="outcome is unknown"):
            await provider.create_video_task(
                kind="text_to_video",
                prompt="生成一段 5 秒晨间拉伸演示视频",
            )
    finally:
        await provider.aclose()
