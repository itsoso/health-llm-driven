"""Durable reconciliation for asynchronous Wan video jobs."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.aigc_media_job import AIGCMediaJob
from app.services.aigc_media_job_service import AIGCMediaJobService


logger = logging.getLogger(__name__)


async def reconcile_active_aigc_media_jobs(
    db: Session,
    *,
    limit: int = 100,
    service_factory: Callable[[Session], AIGCMediaJobService] = AIGCMediaJobService,
) -> dict[str, int]:
    """Poll only active jobs and copy successful outputs into private storage."""
    jobs = (
        db.query(AIGCMediaJob)
        .filter(AIGCMediaJob.status.in_(("queued", "running")))
        .order_by(AIGCMediaJob.created_at.asc())
        .limit(max(1, min(int(limit), 500)))
        .all()
    )
    result = {"scanned": len(jobs), "succeeded": 0, "failed": 0}
    service = service_factory(db)
    for job in jobs:
        try:
            refreshed = await service.refresh(job)
            if refreshed.status == "succeeded":
                result["succeeded"] += 1
            elif refreshed.status == "failed":
                result["failed"] += 1
        except Exception as exc:  # noqa: BLE001 - one provider job must not stall the queue
            db.rollback()
            result["failed"] += 1
            logger.warning(
                "[aigc_media] reconciliation failed job_id=%s error=%s",
                job.id,
                type(exc).__name__,
            )
    return result


@celery_app.task(name="app.tasks.aigc_media.reconcile_aigc_media_jobs")
def reconcile_aigc_media_jobs() -> dict[str, int]:
    """Celery wrapper; succeeds only after every active job was considered."""
    with SessionLocal() as db:
        result = asyncio.run(reconcile_active_aigc_media_jobs(db))
    logger.info(
        "[aigc_media] reconcile scanned=%s succeeded=%s failed=%s",
        result["scanned"],
        result["succeeded"],
        result["failed"],
    )
    return result
