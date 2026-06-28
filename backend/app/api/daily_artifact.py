"""Daily Artifact API: one top action and anti-habituation telemetry."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import daily_artifact_service as service

router = APIRouter(prefix="/daily-artifact", tags=["daily-artifact"])


class DailyArtifactEventIn(BaseModel):
    event_type: str = Field(..., max_length=32)
    artifact_date: date | None = None
    top_action_id: str | None = Field(default=None, max_length=200)
    skip_reason: str | None = Field(default=None, max_length=80)
    delivered_context: dict[str, Any] | None = None

    @field_validator("delivered_context")
    @classmethod
    def _context_size_limit(cls, value: dict[str, Any] | None):
        if value is None:
            return value
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > 4096:
            raise ValueError("delivered_context too large (max 4KB)")
        return value


@router.get("/me")
def get_my_daily_artifact(
    followup_within_days: int = Query(default=7, ge=1, le=14),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return today's compact top-action artifact."""
    return service.build_daily_artifact(
        db,
        current_user.id,
        followup_within_days=followup_within_days,
    )


@router.post("/me/events")
def post_my_daily_artifact_event(
    body: DailyArtifactEventIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Append an interaction event for today's artifact."""
    try:
        return service.record_daily_artifact_event(
            db,
            current_user.id,
            event_type=body.event_type,
            artifact_date=body.artifact_date,
            top_action_id=body.top_action_id,
            skip_reason=body.skip_reason,
            delivered_context=body.delivered_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
