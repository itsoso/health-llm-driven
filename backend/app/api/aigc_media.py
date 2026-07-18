"""Private Xiaoba AIGC media API.

The Agent creates an encrypted, short-lived draft.  Only an authenticated
owner's explicit confirmation card click can consume that draft and contact
Model Studio; clients cannot post a prompt or source asset to this surface.
"""
from __future__ import annotations

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
    AIGCMediaJobService,
)
from app.services.aigc_media_service import AIGCMediaConfigurationError


router = APIRouter(prefix="/aigc/media", tags=["aigc-media"])


def _load_job(db: Session, *, user_id: int, job_id: str) -> AIGCMediaJob:
    job = (
        db.query(AIGCMediaJob)
        .filter(AIGCMediaJob.id == str(job_id), AIGCMediaJob.user_id == user_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="AIGC 任务不存在")
    return job


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
    except AIGCMediaJobError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    if settings.dashscope_aigc_api_key and job.status not in {"succeeded", "failed", "cancelled"}:
        try:
            job = await service.refresh(job)
        except AIGCMediaConfigurationError as exc:
            raise HTTPException(status_code=503, detail="AIGC 媒体服务暂不可用") from exc
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
    return service.project(job)
