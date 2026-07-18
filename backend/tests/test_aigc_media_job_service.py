import base64
import json
import os

import pytest
import httpx


class _FakeProvider:
    def __init__(self) -> None:
        self.video_requests: list[dict] = []
        self.cancelled_task_ids: list[str] = []
        self.task_payload = {"output": {"task_status": "SUCCEEDED", "results": [{"url": "https://result.aliyuncs.com/generated.png"}]}}

    async def create_video_task(self, **kwargs):
        from app.services.aigc_media_service import AIGCTask

        self.video_requests.append(kwargs)
        return AIGCTask(task_id="task-video-1", status="PENDING")

    async def generate_image(self, **_kwargs):
        return ["https://result.aliyuncs.com/generated.png"]

    async def get_task(self, _task_id: str):
        return self.task_payload

    async def cancel_task(self, task_id: str):
        self.cancelled_task_ids.append(task_id)

    async def aclose(self):
        return None


def _create_source_message(db, user_id: int):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.chat_utils import upload_chat_image

    conversation = AgentConversation(user_id=user_id, title="AIGC test")
    db.add(conversation)
    db.flush()
    source_url = upload_chat_image(
        base64.b64encode(b"test-source-image").decode(),
        user_id,
        image_type="jpeg",
    )
    message = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content="把这张早餐照片做成短视频",
        image_url=json.dumps([source_url]),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message, source_url


async def _issue_and_confirm(service, *, user_id: int, request):
    confirmation = await service.issue_confirmation(user_id=user_id, request=request)
    return await service.confirm_and_dispatch(user_id=user_id, confirmation_id=confirmation.id)


@pytest.mark.asyncio
async def test_image_to_video_uses_owned_short_lived_source_and_persists_task(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService
    from app.services.chat_utils import delete_chat_image

    user, _ = auth_user_and_headers
    message, source_url = _create_source_message(db, user.id)
    provider = _FakeProvider()
    monkeypatch.setattr(settings, "site_base_url", "https://health.example.test")
    service = AIGCMediaJobService(db, provider_factory=lambda: provider)
    try:
        job = await _issue_and_confirm(
            service,
            user_id=user.id,
            request=AIGCMediaJobRequest(
                kind="image_to_video",
                purpose="meal_visual",
                prompt="把这张早餐照片做成 5 秒竖屏短视频",
                source_message_id=message.id,
                source_image_index=0,
                duration_seconds=5,
                ratio="9:16",
            ),
        )
    finally:
        delete_chat_image(source_url, user.id)

    assert job.status == "queued"
    assert job.provider_task_id == "task-video-1"
    assert job.source_message_id == message.id
    assert len(provider.video_requests) == 1
    assert {
        key: value
        for key, value in provider.video_requests[0].items()
        if key != "source_url"
    } == {
        "kind": "image_to_video",
        "prompt": "把这张早餐照片做成 5 秒竖屏短视频",
        "duration_seconds": 5,
        "ratio": "9:16",
    }
    transient_url = provider.video_requests[0]["source_url"]
    assert transient_url.startswith("https://health.example.test/api/v1/upload/files/chat/")
    assert "expires=" in transient_url and "signature=" in transient_url


@pytest.mark.asyncio
async def test_confirmed_provider_dispatch_writes_prompt_free_audit_evidence(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.agent_audit_log import AgentAuditLog
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService
    from app.services.chat_utils import delete_chat_image

    user, _ = auth_user_and_headers
    message, source_url = _create_source_message(db, user.id)
    provider = _FakeProvider()
    prompt = "把这张早餐照片做成 5 秒竖屏短视频，包含我的私人健康目标"
    monkeypatch.setattr(settings, "site_base_url", "https://health.example.test")
    try:
        job = await _issue_and_confirm(
            AIGCMediaJobService(db, provider_factory=lambda: provider),
            user_id=user.id,
            request=AIGCMediaJobRequest(
                kind="image_to_video",
                purpose="meal_visual",
                prompt=prompt,
                source_message_id=message.id,
            ),
        )
    finally:
        delete_chat_image(source_url, user.id)

    audit = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == user.id,
            AgentAuditLog.agent_type == "aigc_media",
            AgentAuditLog.action == "provider_dispatch_confirmed",
        )
        .one()
    )
    assert audit.result_detail == {
        "job_id": job.id,
        "kind": "image_to_video",
        "model": "wan2.7-i2v",
        "source_attached": True,
    }
    assert prompt not in str(audit.result_detail)
    assert source_url not in str(audit.result_detail)


@pytest.mark.asyncio
async def test_source_image_must_belong_to_requesting_user(db, auth_user_and_headers):
    from app.services.aigc_media_job_service import (
        AIGCMediaJobRequest,
        AIGCMediaJobRequestError,
        AIGCMediaJobService,
    )
    from app.services.chat_utils import delete_chat_image
    from tests.conftest import create_authenticated_user

    owner, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    message, source_url = _create_source_message(db, owner.id)
    try:
        with pytest.raises(AIGCMediaJobRequestError, match="源图片不存在"):
            await AIGCMediaJobService(db, provider_factory=_FakeProvider).issue_confirmation(
                user_id=other.id,
                request=AIGCMediaJobRequest(
                    kind="image_to_video",
                    purpose="meal_visual",
                    prompt="制作一段短视频",
                    source_message_id=message.id,
                ),
            )
    finally:
        delete_chat_image(source_url, owner.id)


@pytest.mark.asyncio
async def test_text_to_image_downloads_result_into_private_owner_storage(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService

    user, _ = auth_user_and_headers
    provider = _FakeProvider()
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)

    async def download(_url: str, _kind: str):
        return b"generated-image", "image/png", "png"

    service = AIGCMediaJobService(
        db,
        provider_factory=lambda: provider,
        result_downloader=download,
    )
    job = await _issue_and_confirm(
        service,
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="hydration_reminder",
            prompt="生成一张晨间补水行动卡封面",
        ),
    )

    assert job.status == "succeeded"
    assert job.output_media_type == "image/png"
    assert job.output_filename and os.path.isfile(tmp_path / str(user.id) / job.output_filename)
    assert service.project(job)["result"]["url"].startswith(
        f"/api/v1/upload/files/aigc/{user.id}/"
    )


@pytest.mark.asyncio
async def test_refresh_and_cancel_use_provider_task_state(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobService

    user, _ = auth_user_and_headers
    provider = _FakeProvider()
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)
    job = AIGCMediaJob(
        id="aigc-task-refresh",
        user_id=user.id,
        kind="text_to_video",
        status="running",
        progress=25,
        model="wan2.7-t2v",
        provider_task_id="task-video-1",
        idempotency_key="refresh-task",
        request_fingerprint="c" * 64,
    )
    db.add(job)
    db.commit()

    async def download(_url: str, _kind: str):
        return b"generated-video", "video/mp4", "mp4"

    service = AIGCMediaJobService(
        db,
        provider_factory=lambda: provider,
        result_downloader=download,
    )
    refreshed = await service.refresh(job)
    assert refreshed.status == "succeeded"
    assert refreshed.progress == 100

    pending = AIGCMediaJob(
        id="aigc-task-cancel",
        user_id=user.id,
        kind="text_to_video",
        status="running",
        progress=25,
        model="wan2.7-t2v",
        provider_task_id="task-video-cancel",
        idempotency_key="cancel-task",
        request_fingerprint="d" * 64,
    )
    db.add(pending)
    db.commit()
    cancelled = await service.cancel(pending)

    assert cancelled.status == "cancelled"
    assert provider.cancelled_task_ids == ["task-video-cancel"]


@pytest.mark.asyncio
async def test_transient_refresh_failure_keeps_accepted_job_active(db, auth_user_and_headers):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services.aigc_media_job_service import AIGCMediaJobService
    from app.services.aigc_media_service import AIGCMediaProviderError

    class FailingProvider(_FakeProvider):
        async def get_task(self, _task_id: str):
            raise AIGCMediaProviderError("temporary")

    user, _ = auth_user_and_headers
    job = AIGCMediaJob(
        id="aigc-transient-refresh",
        user_id=user.id,
        kind="text_to_video",
        status="running",
        progress=25,
        model="wan2.7-t2v",
        provider_task_id="task-transient",
        idempotency_key="transient-refresh",
        request_fingerprint="e" * 64,
    )
    db.add(job)
    db.commit()

    refreshed = await AIGCMediaJobService(db, provider_factory=FailingProvider).refresh(job)

    assert refreshed.status == "running"
    assert refreshed.error_message is None


@pytest.mark.asyncio
async def test_completion_does_not_resurrect_cancelled_job_or_keep_orphaned_file(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobService

    user, _ = auth_user_and_headers
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)
    job = AIGCMediaJob(
        id="aigc-race-cancel",
        user_id=user.id,
        kind="text_to_image",
        status="running",
        progress=50,
        model="wan2.7-image",
        idempotency_key="race-cancel",
        request_fingerprint="f" * 64,
    )
    db.add(job)
    db.commit()

    async def downloader(_url: str, _kind: str):
        db.query(AIGCMediaJob).filter_by(id=job.id).update({"status": "cancelled"})
        db.commit()
        return b"late-image", "image/png", "png"

    await AIGCMediaJobService(db, provider_factory=_FakeProvider, result_downloader=downloader)._complete_from_provider_url(
        job, "https://result.aliyuncs.com/late.png", kind="text_to_image"
    )

    db.refresh(job)
    assert job.status == "cancelled"
    assert list((tmp_path / str(user.id)).glob("*")) == []


@pytest.mark.asyncio
async def test_result_download_rejects_oversized_content_before_buffering(db, auth_user_and_headers):
    from app.services.aigc_media_job_service import AIGCMediaJobService
    from app.services.aigc_media_service import AIGCMediaProviderError

    user, _ = auth_user_and_headers

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-length": str(20 * 1024 * 1024 + 1)},
            content=b"not-read",
        )

    service = AIGCMediaJobService(
        db,
        provider_factory=_FakeProvider,
        result_http_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(AIGCMediaProviderError, match="result download failed"):
        await service._download_provider_result("https://result.aliyuncs.com/image.png", "text_to_image")
    assert user.id > 0
