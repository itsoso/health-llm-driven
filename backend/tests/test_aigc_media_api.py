from datetime import UTC, datetime


def test_aigc_media_job_creation_is_not_a_public_client_endpoint(
    client,
    db,
    auth_user_and_headers,
):
    from app.models.aigc_media_job import AIGCMediaJob

    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/aigc/media/jobs",
        headers=headers,
        json={
            "kind": "text_to_video",
            "prompt": "制作一个 5 秒的晨间拉伸短视频",
            "confirmed_provider_disclosure": True,
        },
    )

    # Creation is a confirmed Agent Kernel capability, not a generic client
    # endpoint. A client can only read or cancel its already-created job.
    assert response.status_code == 404
    assert db.query(AIGCMediaJob).count() == 0


def test_aigc_media_job_public_create_stays_unavailable_even_without_disclosure(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/aigc/media/jobs",
        headers=headers,
        json={
            "kind": "text_to_video",
            "prompt": "制作一个 5 秒的晨间拉伸短视频",
            "confirmed_provider_disclosure": False,
        },
    )

    assert response.status_code == 404


def test_aigc_media_job_is_invisible_to_another_user(client, db, auth_user_and_headers):
    from app.models.aigc_media_job import AIGCMediaJob
    from tests.conftest import create_authenticated_user

    owner, owner_headers = auth_user_and_headers
    other, other_token = create_authenticated_user(db)
    job = AIGCMediaJob(
        id="job-owner-only",
        user_id=owner.id,
        kind="text_to_video",
        status="running",
        progress=20,
        model="wan2.7-t2v",
        idempotency_key="owner-only",
        request_fingerprint="a" * 64,
        created_at=datetime.now(UTC),
    )
    db.add(job)
    db.commit()

    owner_response = client.get("/api/v1/aigc/media/jobs/job-owner-only", headers=owner_headers)
    assert owner_response.status_code == 200
    assert owner_response.json()["status"] == "running"

    other_response = client.get(
        "/api/v1/aigc/media/jobs/job-owner-only",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_response.status_code == 404
    assert other.id != owner.id


def test_aigc_media_job_rejects_cancel_after_completion(client, db, auth_user_and_headers):
    from app.models.aigc_media_job import AIGCMediaJob

    owner, headers = auth_user_and_headers
    job = AIGCMediaJob(
        id="job-complete",
        user_id=owner.id,
        kind="text_to_image",
        status="succeeded",
        progress=100,
        model="wan2.7-image",
        idempotency_key="complete",
        request_fingerprint="b" * 64,
        completed_at=datetime.now(UTC),
    )
    db.add(job)
    db.commit()

    response = client.post("/api/v1/aigc/media/jobs/job-complete/cancel", headers=headers)

    assert response.status_code == 409
    assert "完成" in response.text


def test_aigc_media_job_recovers_historical_video_result_missing_failure(
    client, db, auth_user_and_headers, monkeypatch,
):
    from app.api import aigc_media
    from app.config import settings
    from app.models.aigc_media_job import AIGCMediaJob

    owner, headers = auth_user_and_headers
    job = AIGCMediaJob(
        id="job-recover-video-result",
        user_id=owner.id,
        kind="image_to_video",
        status="failed",
        progress=50,
        model="wan2.7-i2v-2026-04-25",
        provider_task_id="task-recover-video-result",
        idempotency_key="recover-video-result",
        request_fingerprint="c" * 64,
        provider_error_code="provider_result_missing",
        error_message="生成结果不可用，请重新生成",
    )
    db.add(job)
    db.commit()
    monkeypatch.setattr(settings, "dashscope_aigc_api_key", "test-payg-key")

    class RecoveryService:
        def __init__(self, _db):
            pass

        async def refresh(self, target):
            assert target.id == "job-recover-video-result"
            target.status = "succeeded"
            target.progress = 100
            return target

        def project(self, target):
            return {"id": target.id, "status": target.status, "progress": target.progress}

    monkeypatch.setattr(aigc_media, "AIGCMediaJobService", RecoveryService)

    response = client.get("/api/v1/aigc/media/jobs/job-recover-video-result", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_aigc_confirmation_returns_429_when_dispatch_budget_is_exhausted(
    client, auth_user_and_headers, monkeypatch,
):
    from app.api import aigc_media
    from app.services.aigc_media_job_service import AIGCMediaJobQuotaExceeded

    _, headers = auth_user_and_headers

    class BudgetedService:
        def __init__(self, _db):
            pass

        async def confirm_and_dispatch(self, **_kwargs):
            raise AIGCMediaJobQuotaExceeded("你已有进行中的创作任务，请等待结果后再试")

    monkeypatch.setattr(aigc_media, "AIGCMediaJobService", BudgetedService)

    response = client.post("/api/v1/aigc/media/confirmations/aigc_confirm_1/confirm", headers=headers)

    assert response.status_code == 429
    assert "进行中的创作任务" in response.text


def test_aigc_retry_is_owner_scoped_and_returns_the_updated_projection(
    client, db, auth_user_and_headers, monkeypatch,
):
    from app.api import aigc_media
    from app.models.aigc_media_job import AIGCMediaJob
    from tests.conftest import create_authenticated_user

    owner, headers = auth_user_and_headers
    other, other_token = create_authenticated_user(db)
    job = AIGCMediaJob(
        id="job-safe-retry",
        user_id=owner.id,
        kind="text_to_video",
        status="failed",
        progress=0,
        model="wan2.7-t2v",
        idempotency_key="safe-retry",
        request_fingerprint="d" * 64,
        provider_error_code="provider_auth_failed",
        error_message="创作服务授权异常，已通知管理员。",
    )
    db.add(job)
    db.commit()

    class RetryService:
        def __init__(self, _db):
            pass

        async def retry_failed(self, *, user_id, job_id):
            assert user_id == owner.id
            assert job_id == job.id
            job.status = "queued"
            job.progress = 10
            return job

        def project(self, target):
            return {"id": target.id, "status": target.status, "progress": target.progress}

    monkeypatch.setattr(aigc_media, "AIGCMediaJobService", RetryService)

    response = client.post("/api/v1/aigc/media/jobs/job-safe-retry/retry", headers=headers)
    forbidden = client.post(
        "/api/v1/aigc/media/jobs/job-safe-retry/retry",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": "job-safe-retry", "status": "queued", "progress": 10}
    assert forbidden.status_code == 404
    assert other.id != owner.id
