"""External AIGC dispatch requires an owner click on a one-time server draft."""
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import InvalidToken


class _Provider:
    def __init__(self) -> None:
        self.image_requests: list[dict] = []

    async def generate_image(self, **kwargs):
        self.image_requests.append(kwargs)
        return ["https://result.aliyuncs.com/generated.png"]

    async def create_video_task(self, **_kwargs):  # pragma: no cover - test only creates images
        raise AssertionError("unexpected video generation")

    async def get_task(self, _task_id: str, **_kwargs):  # pragma: no cover
        raise AssertionError("unexpected task polling")

    async def cancel_task(self, _task_id: str, **_kwargs):  # pragma: no cover
        raise AssertionError("unexpected task cancellation")

    async def aclose(self):
        return None


def test_aigc_confirmation_ciphertext_uses_a_separate_tenant_crypto_context():
    from app.services.tenant_crypto import (
        decrypt_aigc_confirmation_for,
        decrypt_for,
        encrypt_aigc_confirmation_for,
    )

    token = encrypt_aigc_confirmation_for(42, "制作一张早餐备餐步骤图")

    assert decrypt_aigc_confirmation_for(42, token) == "制作一张早餐备餐步骤图"
    with pytest.raises(InvalidToken):
        decrypt_for(42, token)


@pytest.mark.asyncio
async def test_confirmation_is_encrypted_and_single_use_before_provider_dispatch(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.models.aigc_media_confirmation import AIGCMediaConfirmation
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService

    user, _ = auth_user_and_headers
    provider = _Provider()
    prompt = "制作一张早餐备餐步骤图"
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)

    async def download(_url: str, _kind: str):
        return b"png", "image/png", "png"

    service = AIGCMediaJobService(db, provider_factory=lambda: provider, result_downloader=download)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt=prompt,
        ),
    )

    stored = db.query(AIGCMediaConfirmation).filter_by(id=confirmation.id).one()
    assert stored.status == "pending"
    assert stored.prompt_ciphertext != prompt
    assert prompt not in stored.prompt_ciphertext
    assert provider.image_requests == []

    first = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)
    second = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)

    assert first.id == second.id
    assert first.status == "succeeded"
    assert len(provider.image_requests) == 1
    assert provider.image_requests[0]["prompt"] == prompt


@pytest.mark.asyncio
async def test_expired_confirmation_cannot_contact_provider(db, auth_user_and_headers):
    from app.models.aigc_media_confirmation import AIGCMediaConfirmation
    from app.services.aigc_media_job_service import (
        AIGCMediaJobConflict,
        AIGCMediaJobRequest,
        AIGCMediaJobService,
    )

    user, _ = auth_user_and_headers
    provider = _Provider()
    service = AIGCMediaJobService(db, provider_factory=lambda: provider)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="wellness_story",
            prompt="制作一张早晨散步的温和插画",
        ),
    )
    db.query(AIGCMediaConfirmation).filter_by(id=confirmation.id).update(
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    db.commit()

    with pytest.raises(AIGCMediaJobConflict, match="已过期"):
        await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)
    assert provider.image_requests == []


@pytest.mark.asyncio
async def test_retry_recovers_job_persisted_before_confirmation_link(db, auth_user_and_headers, monkeypatch, tmp_path):
    """A crash after job persistence must not leave the user-facing draft spinning."""
    from app.models.aigc_media_confirmation import AIGCMediaConfirmation
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService
    from app.services.tenant_crypto import decrypt_aigc_confirmation_for

    user, _ = auth_user_and_headers
    provider = _Provider()
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)

    async def download(_url: str, _kind: str):
        return b"png", "image/png", "png"

    service = AIGCMediaJobService(db, provider_factory=lambda: provider, result_downloader=download)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt="制作一张早餐备餐步骤图",
        ),
    )
    request = AIGCMediaJobRequest(
        kind=confirmation.kind,
        purpose=confirmation.purpose,
        prompt=decrypt_aigc_confirmation_for(user.id, confirmation.prompt_ciphertext),
        duration_seconds=confirmation.duration_seconds,
        ratio=confirmation.ratio,
    )
    job = await service._dispatch_confirmed(
        user_id=user.id,
        request=request,
        confirmation_id=confirmation.id,
    )

    # Simulate process death between durable job creation and confirmation.job_id.
    db.query(AIGCMediaConfirmation).filter_by(id=confirmation.id).update(
        {"status": "dispatching", "job_id": None, "consumed_at": datetime.now(UTC)}
    )
    db.commit()

    recovered = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)
    persisted = db.query(AIGCMediaConfirmation).filter_by(id=confirmation.id).one()

    assert recovered.id == job.id
    assert persisted.status == "dispatched"
    assert persisted.job_id == job.id
    assert len(provider.image_requests) == 1


@pytest.mark.asyncio
async def test_medical_decision_prompt_is_rejected_before_external_dispatch(db, auth_user_and_headers):
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobRequestError, AIGCMediaJobService

    user, _ = auth_user_and_headers
    provider = _Provider()
    with pytest.raises(AIGCMediaJobRequestError, match="不能生成诊断"):
        await AIGCMediaJobService(db, provider_factory=lambda: provider).issue_confirmation(
            user_id=user.id,
            request=AIGCMediaJobRequest(
                kind="text_to_video",
                purpose="wellness_story",
                prompt="为我的高血压诊断并给出降压药剂量的短视频",
            ),
        )
    assert provider.image_requests == []


@pytest.mark.asyncio
async def test_confirmation_binds_the_wan_model_before_a_user_confirms(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.config import settings
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService

    user, _ = auth_user_and_headers
    provider = _Provider()
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(settings, "dashscope_aigc_image_model", "wan2.7-image")

    async def download(_url: str, _kind: str):
        return b"png", "image/png", "png"

    service = AIGCMediaJobService(db, provider_factory=lambda: provider, result_downloader=download)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt="制作一张早餐备餐步骤图",
        ),
    )
    monkeypatch.setattr(settings, "dashscope_aigc_image_model", "wan2.7-image-pro")

    job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)

    assert confirmation.model == "wan2.7-image"
    assert job.model == "wan2.7-image"
    assert provider.image_requests == [{
        "prompt": "制作一张早餐备餐步骤图",
        "image_data_uri": None,
        "model": "wan2.7-image",
    }]


@pytest.mark.asyncio
async def test_uncertain_provider_submission_is_not_replayed_by_a_second_confirmation(
    db, auth_user_and_headers,
):
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService
    from app.services.aigc_media_service import AIGCMediaProviderIndeterminateError

    class UncertainProvider(_Provider):
        async def generate_image(self, **kwargs):
            self.image_requests.append(kwargs)
            raise AIGCMediaProviderIndeterminateError("response lost after submission")

    user, _ = auth_user_and_headers
    provider = UncertainProvider()
    service = AIGCMediaJobService(db, provider_factory=lambda: provider)
    request = AIGCMediaJobRequest(
        kind="text_to_image",
        purpose="meal_visual",
        prompt="制作一张早餐备餐步骤图",
    )
    first_confirmation = await service.issue_confirmation(user_id=user.id, request=request)
    first_job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=first_confirmation.id)

    duplicate_confirmation = await service.issue_confirmation(user_id=user.id, request=request)
    duplicate_job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=duplicate_confirmation.id)
    retried_duplicate_job = await service.confirm_and_dispatch(
        user_id=user.id,
        confirmation_id=duplicate_confirmation.id,
    )

    assert first_job.status == "submission_unknown"
    assert duplicate_job.id == first_job.id
    assert retried_duplicate_job.id == first_job.id
    assert len(provider.image_requests) == 1


@pytest.mark.asyncio
async def test_dispatch_rechecks_the_fingerprint_after_acquiring_the_cost_lock(
    db, auth_user_and_headers,
):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService

    user, _ = auth_user_and_headers
    provider = _Provider()
    service = AIGCMediaJobService(db, provider_factory=lambda: provider)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt="制作一张早餐备餐步骤图",
        ),
    )
    original_reserve = service._reserve_dispatch_capacity

    def reserve_then_simulate_a_racing_committed_job(*, user_id: int, lock_acquired: bool = False) -> None:
        original_reserve(user_id=user_id, lock_acquired=lock_acquired)
        db.add(AIGCMediaJob(
            id="aigc-racing-fingerprint",
            user_id=user_id,
            kind=confirmation.kind,
            status="submission_unknown",
            progress=0,
            model=confirmation.model,
            idempotency_key="racing-confirmation",
            request_fingerprint=confirmation.prompt_fingerprint,
        ))
        db.commit()

    service._reserve_dispatch_capacity = reserve_then_simulate_a_racing_committed_job  # type: ignore[method-assign]

    job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)

    assert job.id == "aigc-racing-fingerprint"
    assert provider.image_requests == []


@pytest.mark.asyncio
async def test_unexpected_failure_after_provider_request_links_an_unknown_job_to_confirmation(
    db, auth_user_and_headers,
):
    from app.models.aigc_media_confirmation import AIGCMediaConfirmation
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService

    class CrashingProvider(_Provider):
        async def generate_image(self, **kwargs):
            self.image_requests.append(kwargs)
            raise RuntimeError("connection closed after request")

    user, _ = auth_user_and_headers
    provider = CrashingProvider()
    service = AIGCMediaJobService(db, provider_factory=lambda: provider)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt="制作一张早餐备餐步骤图",
        ),
    )

    job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)
    persisted_confirmation = db.query(AIGCMediaConfirmation).filter_by(id=confirmation.id).one()

    assert job.status == "submission_unknown"
    assert persisted_confirmation.job_id == job.id
    assert len(provider.image_requests) == 1


@pytest.mark.asyncio
async def test_explicit_retry_reuses_a_definitively_rejected_job_without_duplicate_ledger(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService
    from app.services.aigc_media_service import AIGCMediaProviderError

    class RejectThenSucceedProvider(_Provider):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def generate_image(self, **kwargs):
            self.image_requests.append(kwargs)
            self.attempts += 1
            if self.attempts == 1:
                raise AIGCMediaProviderError(
                    "Model Studio media request was rejected",
                    error_code="provider_auth_failed",
                    status_code=401,
                )
            return ["https://result.aliyuncs.com/generated.png"]

    user, _ = auth_user_and_headers
    provider = RejectThenSucceedProvider()
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)

    async def download(_url: str, _kind: str):
        return b"png", "image/png", "png"

    service = AIGCMediaJobService(db, provider_factory=lambda: provider, result_downloader=download)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt="制作一张早餐备餐步骤图",
        ),
    )

    failed = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)
    retried = await service.retry_failed(user_id=user.id, job_id=failed.id)

    assert failed.id == retried.id
    assert retried.status == "succeeded"
    assert provider.attempts == 2
    assert db.query(AIGCMediaJob).filter_by(user_id=user.id).count() == 1
    assert service.project(retried)["can_retry"] is False


@pytest.mark.asyncio
async def test_confirmed_job_replaces_persisted_confirmation_card(
    db, auth_user_and_headers, monkeypatch, tmp_path,
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services import aigc_media_job_service
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService
    from app.services.aigc_media_service import AIGCMediaProviderError

    class RejectedProvider(_Provider):
        def __init__(self) -> None:
            super().__init__()
            self.video_requests: list[dict] = []

        async def create_video_task(self, **kwargs):
            self.video_requests.append(kwargs)
            raise AIGCMediaProviderError(
                "Model Studio media request was rejected",
                error_code="provider_auth_failed",
                status_code=401,
            )

    user, _ = auth_user_and_headers
    conversation = AgentConversation(user_id=user.id, title="AIGC test")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    monkeypatch.setattr(aigc_media_job_service, "_AIGC_UPLOAD_ROOT", tmp_path)
    service = AIGCMediaJobService(db, provider_factory=RejectedProvider)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        conversation_id=conversation.id,
        request=AIGCMediaJobRequest(
            kind="text_to_video",
            purpose="wellness_story",
            prompt="生成一段今日健康活动短视频",
        ),
    )
    assistant = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="已创建草稿",
        meta={
            "cards": [{
                "type": "aigc_media_confirmation",
                "data": {
                    "confirmation_id": confirmation.id,
                    "kind": "text_to_video",
                    "status": "pending",
                },
            }],
        },
    )
    duplicate_assistant = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="旧版本重复草稿",
        meta={
            "cards": [{
                "type": "aigc_media_confirmation",
                "data": {
                    "confirmation_id": confirmation.id,
                    "kind": "text_to_video",
                    "status": "pending",
                },
            }],
        },
    )
    db.add_all([assistant, duplicate_assistant])
    db.commit()

    job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)
    assert service.persist_job_card(user_id=user.id, job=job, confirmation_id=confirmation.id) is True

    db.refresh(assistant)
    cards = assistant.meta["cards"]
    assert len(cards) == 1
    assert cards[0]["type"] == "aigc_media_job"
    assert cards[0]["data"] == {
        "job_id": job.id,
        "kind": "text_to_video",
        "status": "failed",
        "progress": 0,
        "title": "小巴创作",
        "error_message": "创作服务授权异常，已通知管理员。",
        "error_code": "provider_auth_failed",
        "can_retry": True,
    }
    db.refresh(duplicate_assistant)
    assert duplicate_assistant.meta["cards"] == cards


@pytest.mark.asyncio
async def test_indeterminate_submission_cannot_be_retried(db, auth_user_and_headers):
    from app.services.aigc_media_job_service import (
        AIGCMediaJobConflict,
        AIGCMediaJobRequest,
        AIGCMediaJobService,
    )
    from app.services.aigc_media_service import AIGCMediaProviderIndeterminateError

    class UncertainProvider(_Provider):
        async def generate_image(self, **kwargs):
            self.image_requests.append(kwargs)
            raise AIGCMediaProviderIndeterminateError("response lost after submission")

    user, _ = auth_user_and_headers
    provider = UncertainProvider()
    service = AIGCMediaJobService(db, provider_factory=lambda: provider)
    confirmation = await service.issue_confirmation(
        user_id=user.id,
        request=AIGCMediaJobRequest(
            kind="text_to_image",
            purpose="meal_visual",
            prompt="制作一张早餐备餐步骤图",
        ),
    )
    job = await service.confirm_and_dispatch(user_id=user.id, confirmation_id=confirmation.id)

    with pytest.raises(AIGCMediaJobConflict, match="不能重新提交"):
        await service.retry_failed(user_id=user.id, job_id=job.id)
    assert len(provider.image_requests) == 1
