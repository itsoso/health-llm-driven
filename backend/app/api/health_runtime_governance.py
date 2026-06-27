"""Health Runtime governance controls API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.health_runtime_governance import (
    list_governance_summary,
    serialize_data_source_quality,
    serialize_runtime_control,
    serialize_source_preference,
    upsert_data_source_quality,
    upsert_runtime_control,
    upsert_source_preference,
)

router = APIRouter(prefix="/health-runtime-governance", tags=["health-runtime-governance"])


class DataSourceQualityUpsert(BaseModel):
    source_kind: str = Field(..., max_length=40)
    source_id: str = Field(..., max_length=160)
    metric: str = Field(..., max_length=80)
    quality_score: float = Field(..., ge=0.0, le=1.0)
    confidence: str = "unknown"
    freshness_seconds: Optional[int] = Field(None, ge=0)
    status: str = "usable"
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourcePreferenceUpsert(BaseModel):
    metric: str = Field(..., max_length=80)
    preferred_source_kind: str = Field(..., max_length=40)
    preferred_source_id: str = Field(..., max_length=160)
    scope: str = Field("global", max_length=80)
    reason: Optional[str] = None


class RuntimeControlUpsert(BaseModel):
    control_type: str = Field(..., max_length=40)
    target_key: str = Field(..., max_length=120)
    status: str = Field(..., max_length=30)
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("/me")
def get_my_governance_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return list_governance_summary(db, current_user.id)


@router.post("/source-quality")
def upsert_my_source_quality(
    payload: DataSourceQualityUpsert,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    row = upsert_data_source_quality(
        db,
        user_id=current_user.id,
        source_kind=payload.source_kind,
        source_id=payload.source_id,
        metric=payload.metric,
        quality_score=payload.quality_score,
        confidence=payload.confidence,
        freshness_seconds=payload.freshness_seconds,
        status=payload.status,
        reason=payload.reason,
        metadata=payload.metadata,
    )
    return serialize_data_source_quality(row)


@router.post("/source-preferences")
def upsert_my_source_preference(
    payload: SourcePreferenceUpsert,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    row = upsert_source_preference(
        db,
        user_id=current_user.id,
        metric=payload.metric,
        preferred_source_kind=payload.preferred_source_kind,
        preferred_source_id=payload.preferred_source_id,
        scope=payload.scope,
        reason=payload.reason,
    )
    return serialize_source_preference(row)


@router.post("/controls")
def upsert_my_runtime_control(
    payload: RuntimeControlUpsert,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    row = upsert_runtime_control(
        db,
        user_id=current_user.id,
        control_type=payload.control_type,
        target_key=payload.target_key,
        status=payload.status,
        reason=payload.reason,
        metadata=payload.metadata,
    )
    return serialize_runtime_control(row)
