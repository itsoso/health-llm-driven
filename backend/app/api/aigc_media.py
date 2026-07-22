"""Private Xiaoba AIGC media API.

The Agent creates an encrypted, short-lived draft.  Only an authenticated
owner's explicit confirmation card click can consume that draft and contact
Model Studio; clients cannot post a prompt or source asset to this surface.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.config import settings
from app.database import get_db
from app.models.aigc_media_job import AIGCMediaJob
from app.models.user import User
from app.services.aigc_media_job_service import (
    AIGCMediaJobConflict,
    AIGCMediaJobError,
    AIGCMediaJobQuotaExceeded,
    AIGCMediaJobService,
    is_recoverable_provider_result_missing_job,
)
from app.services.aigc_media_service import AIGCMediaConfigurationError


router = APIRouter(prefix="/aigc/media", tags=["aigc-media"])
logger = logging.getLogger(__name__)


def _persist_job_card_safely(
    service: AIGCMediaJobService,
    *,
    user_id: int,
    job: AIGCMediaJob,
    confirmation_id: str | None = None,
) -> None:
    """Keep the job response authoritative if transcript repair is delayed."""
    try:
        service.persist_job_card(
            user_id=user_id,
            job=job,
            confirmation_id=confirmation_id,
        )
    except Exception as exc:
        logger.error(
            "[aigc_media] job card persistence failed job_id=%s error_type=%s",
            job.id,
            type(exc).__name__,
        )


def _load_job(db: Session, *, user_id: int, job_id: str) -> AIGCMediaJob:
    job = (
        db.query(AIGCMediaJob)
        .filter(AIGCMediaJob.id == str(job_id), AIGCMediaJob.user_id == user_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="AIGC 任务不存在")
    return job


@router.get("/confirmations/{confirmation_id}")
async def get_aigc_media_confirmation(
    confirmation_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict:
    """Resolve a persisted draft to its existing job without dispatching it."""
    service = AIGCMediaJobService(db)
    try:
        projection = service.confirmation_projection(
            user_id=current_user.id,
            confirmation_id=confirmation_id,
        )
    except AIGCMediaJobError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    job_projection = projection.get("job")
    if isinstance(job_projection, dict):
        job = _load_job(
            db,
            user_id=current_user.id,
            job_id=str(job_projection.get("id") or ""),
        )
        _persist_job_card_safely(
            service,
            user_id=current_user.id,
            job=job,
            confirmation_id=confirmation_id,
        )
    return projection


@router.post("/confirmations/{confirmation_id}/confirm")
async def confirm_aigc_media_draft(
    confirmation_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict:
    """Consume an owner-bound draft after a direct user confirmation gesture."""
    service = AIGCMediaJobService(db)
    try:
        job = await service.confirm_and_dispatch(
            user_id=current_user.id,
            confirmation_id=confirmation_id,
        )
    except AIGCMediaConfigurationError as exc:
        raise HTTPException(status_code=503, detail="AIGC 媒体服务暂不可用") from exc
    except AIGCMediaJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIGCMediaJobQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AIGCMediaJobError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _persist_job_card_safely(
        service,
        user_id=current_user.id,
        job=job,
        confirmation_id=confirmation_id,
    )
    return service.project(job)


@router.get("/jobs/{job_id}")
async def get_aigc_media_job(
    job_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict:
    job = _load_job(db, user_id=current_user.id, job_id=job_id)
    service = AIGCMediaJobService(db)
    # Historical rows remain readable during a credential outage.  Do not turn
    # an existing status into a false failure merely because this request cannot
    # poll the provider at this moment.
    if settings.dashscope_aigc_api_key and job.provider_task_id and (
        job.status not in {"succeeded", "failed", "cancelled", "submission_unknown"}
        or is_recoverable_provider_result_missing_job(job)
    ):
        try:
            job = await service.refresh(job)
        except AIGCMediaConfigurationError as exc:
            raise HTTPException(status_code=503, detail="AIGC 媒体服务暂不可用") from exc
    _persist_job_card_safely(service, user_id=current_user.id, job=job)
    return service.project(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_aigc_media_job(
    job_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict:
    job = _load_job(db, user_id=current_user.id, job_id=job_id)
    service = AIGCMediaJobService(db)
    try:
        job = await service.cancel(job)
    except AIGCMediaConfigurationError as exc:
        raise HTTPException(status_code=503, detail="AIGC 媒体服务暂不可用") from exc
    except AIGCMediaJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIGCMediaJobError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _persist_job_card_safely(service, user_id=current_user.id, job=job)
    return service.project(job)


@router.post("/jobs/{job_id}/retry")
async def retry_aigc_media_job(
    job_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict:
    """Explicitly retry a definitively rejected, never-accepted provider job."""
    _load_job(db, user_id=current_user.id, job_id=job_id)
    service = AIGCMediaJobService(db)
    try:
        job = await service.retry_failed(user_id=current_user.id, job_id=job_id)
    except AIGCMediaJobQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AIGCMediaJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIGCMediaJobError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _persist_job_card_safely(service, user_id=current_user.id, job=job)
    return service.project(job)
