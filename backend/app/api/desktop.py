"""Desktop client aggregate APIs.

The Swift-native Mac app should launch with one compact request instead of
replaying every mobile screen request one by one.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.daily_health import DietRecord, WaterIntake
from app.models.desktop_job import DesktopJob
from app.models.memory_fact import MemoryFact
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.daily_operating_plan import build_daily_operating_plan
from app.services.health_trajectory import build_health_trajectory_snapshot

router = APIRouter(prefix="/desktop", tags=["desktop"])

DesktopJobType = Literal[
    "gene_reanalysis",
    "medical_import",
    "system_kb_rebuild",
    "dedao_compile",
    "eval_run",
]


class DesktopJobCreate(BaseModel):
    job_type: DesktopJobType
    source_kind: str | None = Field(None, max_length=50)
    source_name: str | None = Field(None, max_length=500)
    source_hash: str | None = Field(None, max_length=128)
    request_payload: dict[str, Any] = Field(default_factory=dict)


def _action_card_to_dict(card: ActionCard) -> dict[str, Any]:
    return {
        "id": card.id,
        "title": card.title,
        "content": card.content,
        "card_type": card.card_type,
        "source_type": card.source_type,
        "source_id": card.source_id,
        "status": card.status,
        "priority": card.priority,
        "metric_key": card.metric_key,
        "evidence_refs": card.evidence_refs or [],
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
    }


def _memory_fact_to_dict(fact: MemoryFact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "tier": fact.tier,
        "subject": fact.subject,
        "predicate": fact.predicate,
        "object_value": fact.object_value,
        "object_unit": fact.object_unit,
        "confidence": fact.confidence,
        "effective_confidence": round(fact.effective_confidence, 3),
        "tags": fact.tags or [],
        "is_sensitive": fact.is_sensitive,
        "created_at": fact.created_at.isoformat() if fact.created_at else None,
    }


def _recent_records_summary(db: Session, user_id: int) -> dict[str, Any]:
    today = date.today()
    diet_records = (
        db.query(DietRecord)
        .filter(DietRecord.user_id == user_id, DietRecord.record_date == today)
        .all()
    )
    water_records = (
        db.query(WaterIntake)
        .filter(WaterIntake.user_id == user_id, WaterIntake.record_date == today)
        .all()
    )
    return {
        "date": today.isoformat(),
        "diet": {
            "today_count": len(diet_records),
            "today_calories": round(sum(r.calories or 0 for r in diet_records), 1),
        },
        "water": {
            "today_count": len(water_records),
            "today_total_ml": sum(r.amount_ml or 0 for r in water_records),
        },
    }


def _active_desktop_jobs(db: Session, user_id: int) -> list[dict[str, Any]]:
    jobs = (
        db.query(DesktopJob)
        .filter(
            DesktopJob.user_id == user_id,
            DesktopJob.status.in_(["queued", "running"]),
        )
        .order_by(desc(DesktopJob.created_at))
        .limit(10)
        .all()
    )
    return [job.to_dict() for job in jobs]


@router.get("/bootstrap")
def get_desktop_bootstrap(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the Mac app's launch context for the current user."""

    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == current_user.id)
        .first()
    )
    action_cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == current_user.id,
            ActionCard.status == "active",
            ActionCard.is_visible == True,  # noqa: E712
        )
        .order_by(desc(ActionCard.priority), desc(ActionCard.created_at))
        .limit(20)
        .all()
    )
    memory_facts = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == current_user.id,
            MemoryFact.superseded_at.is_(None),
        )
        .order_by(desc(MemoryFact.last_reinforced_at), desc(MemoryFact.created_at))
        .limit(10)
        .all()
    )

    return {
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
        },
        "model_preference": {
            "llm_model_id": profile.llm_model_id if profile else None,
        },
        "daily_plan": build_daily_operating_plan(db, current_user.id),
        "trajectory": build_health_trajectory_snapshot(db, current_user.id),
        "action_cards": [_action_card_to_dict(card) for card in action_cards],
        "recent_memory": [_memory_fact_to_dict(fact) for fact in memory_facts],
        "recent_records_summary": _recent_records_summary(db, current_user.id),
        "active_jobs": _active_desktop_jobs(db, current_user.id),
    }


@router.post("/import-jobs")
def create_desktop_import_job(
    body: DesktopJobCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a desktop-triggered long-running job.

    P0 stores the job and leaves actual worker wiring to the specific pipeline.
    The job table gives the Mac app a stable status surface immediately.
    """

    job = DesktopJob(
        user_id=current_user.id,
        job_type=body.job_type,
        status="queued",
        progress=0,
        source_kind=body.source_kind,
        source_name=body.source_name,
        source_hash=body.source_hash,
        request_payload=body.request_payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.to_dict()


@router.get("/jobs")
def list_desktop_jobs(
    status: str | None = Query(None, max_length=30),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    q = db.query(DesktopJob).filter(DesktopJob.user_id == current_user.id)
    if status:
        q = q.filter(DesktopJob.status == status)
    rows = q.order_by(desc(DesktopJob.created_at)).limit(limit).all()
    return [row.to_dict() for row in rows]


def _load_desktop_job(db: Session, *, user_id: int, job_id: int) -> DesktopJob:
    job = (
        db.query(DesktopJob)
        .filter(DesktopJob.id == job_id, DesktopJob.user_id == user_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Desktop job 不存在")
    return job


@router.get("/jobs/{job_id}")
def get_desktop_job(
    job_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _load_desktop_job(db, user_id=current_user.id, job_id=job_id).to_dict()


@router.post("/jobs/{job_id}/retry")
def retry_desktop_job(
    job_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = _load_desktop_job(db, user_id=current_user.id, job_id=job_id)
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="只有 failed job 可以重试")

    retry = DesktopJob(
        user_id=current_user.id,
        job_type=job.job_type,
        status="queued",
        progress=0,
        source_kind=job.source_kind,
        source_name=job.source_name,
        source_hash=job.source_hash,
        request_payload=job.request_payload or {},
        retry_of_job_id=job.id,
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    return retry.to_dict()
