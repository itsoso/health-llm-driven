"""Consent must be checked at every actual media-generation request."""
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from app.services import aigc_media_service as media


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_after_first", [False, True])
async def test_denied_or_revoked_consent_prevents_next_provider_request(monkeypatch, revoke_after_first):
    requests = []

    def guard(*args, **kwargs):
        if not revoke_after_first or requests:
            raise HTTPException(status_code=403, detail={"code": "ai_consent_required"})

    async def handler(request):
        requests.append(request)
        return httpx.Response(401, json={"code": "InvalidApiKey"})

    checked = Mock(side_effect=guard)
    monkeypatch.setattr(media, "require_ai_consent", checked, raising=False)
    provider = media.AIGCMediaProvider(
        api_key="synthetic-test-key",
        api_base_url="https://dashscope.aliyuncs.com/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(HTTPException) as error:
            await provider.generate_image(prompt="合成测试图片")
    finally:
        await provider.aclose()
    assert error.value.status_code == 403
    assert len(requests) == int(revoke_after_first)
    checked.assert_called_with(destination="https://dashscope.aliyuncs.com/api/v1")


@pytest.mark.asyncio
async def test_job_denial_precedes_source_export_and_job_creation(db, auth_user_and_headers, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services import ai_consent
    from app.services.aigc_media_job_service import AIGCMediaJobRequest, AIGCMediaJobService

    user, _ = auth_user_and_headers
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    provider = Mock()
    service = AIGCMediaJobService(db, provider_factory=provider)
    export = Mock(side_effect=AssertionError("no source export before permission"))
    monkeypatch.setattr(service, "_prepare_owned_source", export)
    with pytest.raises(HTTPException) as error:
        await service._dispatch_confirmed(
            user_id=user.id,
            request=AIGCMediaJobRequest(kind="text_to_image", purpose="meal_visual", prompt="合成测试图片"),
            confirmation_id="synthetic-confirmation",
        )
    assert error.value.status_code == 403
    export.assert_not_called()
    provider.assert_not_called()
    assert db.query(AIGCMediaJob).count() == 0
