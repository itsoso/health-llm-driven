import pytest


@pytest.mark.asyncio
async def test_reconcile_active_aigc_media_jobs_refreshes_only_nonterminal_owner_jobs(
    db,
    auth_user_and_headers,
):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.tasks.aigc_media import reconcile_active_aigc_media_jobs

    user, _ = auth_user_and_headers
    active = AIGCMediaJob(
        id="aigc-active",
        user_id=user.id,
        kind="text_to_video",
        status="running",
        progress=25,
        model="wan2.7-t2v",
        provider_task_id="task-active",
        idempotency_key="active",
        request_fingerprint="a" * 64,
    )
    completed = AIGCMediaJob(
        id="aigc-completed",
        user_id=user.id,
        kind="text_to_image",
        status="succeeded",
        progress=100,
        model="wan2.7-image",
        idempotency_key="completed",
        request_fingerprint="b" * 64,
    )
    db.add_all([active, completed])
    db.commit()

    refreshed_ids = []

    class FakeService:
        def __init__(self, _db):
            pass

        async def refresh(self, job):
            refreshed_ids.append(job.id)
            job.status = "succeeded"
            job.progress = 100
            db.commit()
            return job

    result = await reconcile_active_aigc_media_jobs(
        db,
        service_factory=FakeService,
    )

    assert result == {"scanned": 1, "succeeded": 1, "failed": 0}
    assert refreshed_ids == ["aigc-active"]
