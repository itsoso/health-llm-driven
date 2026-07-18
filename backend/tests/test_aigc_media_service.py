import json

import httpx
import pytest


def test_rejects_token_plan_endpoint_for_aigc_media():
    from app.services.aigc_media_service import (
        AIGCMediaConfigurationError,
        AIGCMediaProvider,
    )

    with pytest.raises(AIGCMediaConfigurationError, match="Token Plan"):
        AIGCMediaProvider(
            api_key="test-payg-key",
            api_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        )


def test_aigc_provider_rejects_reusing_token_plan_credential():
    from app.services.aigc_media_service import AIGCMediaConfigurationError, AIGCMediaProvider

    with pytest.raises(AIGCMediaConfigurationError, match="Token Plan"):
        AIGCMediaProvider(
            api_key="token-plan-secret",
            blocked_api_keys=("token-plan-secret",),
            api_base_url="https://dashscope.aliyuncs.com/api/v1",
        )


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
        "model": "wan2.7-i2v",
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
