"""Health Runtime governance service layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

from app.models.health_runtime_governance import (
    DataSourceQuality,
    HealthRuntimeControl,
    UserDataSourcePreference,
)

ACTIVE_CONTROL_STATUSES = {"paused", "deleted", "disabled"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def upsert_data_source_quality(
    db: Session,
    *,
    user_id: int,
    source_kind: str,
    source_id: str,
    metric: str,
    quality_score: float,
    confidence: str,
    freshness_seconds: int | None = None,
    status: str = "usable",
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DataSourceQuality:
    row = (
        db.query(DataSourceQuality)
        .filter(
            DataSourceQuality.user_id == user_id,
            DataSourceQuality.source_kind == source_kind,
            DataSourceQuality.source_id == source_id,
            DataSourceQuality.metric == metric,
        )
        .first()
    )
    if row is None:
        row = DataSourceQuality(
            user_id=user_id,
            source_kind=source_kind,
            source_id=source_id,
            metric=metric,
        )
        db.add(row)
    row.quality_score = float(quality_score)
    row.confidence = confidence
    row.freshness_seconds = freshness_seconds
    row.status = status
    row.reason = reason
    row.source_metadata = metadata or {}
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def upsert_source_preference(
    db: Session,
    *,
    user_id: int,
    metric: str,
    preferred_source_kind: str,
    preferred_source_id: str,
    scope: str = "global",
    reason: str | None = None,
) -> UserDataSourcePreference:
    row = (
        db.query(UserDataSourcePreference)
        .filter(
            UserDataSourcePreference.user_id == user_id,
            UserDataSourcePreference.metric == metric,
            UserDataSourcePreference.scope == scope,
        )
        .first()
    )
    if row is None:
        row = UserDataSourcePreference(user_id=user_id, metric=metric, scope=scope)
        db.add(row)
    row.preferred_source_kind = preferred_source_kind
    row.preferred_source_id = preferred_source_id
    row.reason = reason
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def upsert_runtime_control(
    db: Session,
    *,
    user_id: int,
    control_type: str,
    target_key: str,
    status: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> HealthRuntimeControl:
    row = (
        db.query(HealthRuntimeControl)
        .filter(
            HealthRuntimeControl.user_id == user_id,
            HealthRuntimeControl.control_type == control_type,
            HealthRuntimeControl.target_key == target_key,
        )
        .first()
    )
    if row is None:
        row = HealthRuntimeControl(
            user_id=user_id,
            control_type=control_type,
            target_key=target_key,
        )
        db.add(row)
    row.status = status
    row.reason = reason
    row.control_metadata = metadata or {}
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_governance_summary(db: Session, user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    quality = (
        db.query(DataSourceQuality)
        .filter(DataSourceQuality.user_id == user_id)
        .order_by(DataSourceQuality.metric.asc(), DataSourceQuality.source_kind.asc(), DataSourceQuality.source_id.asc())
        .all()
    )
    preferences = (
        db.query(UserDataSourcePreference)
        .filter(UserDataSourcePreference.user_id == user_id)
        .order_by(UserDataSourcePreference.metric.asc(), UserDataSourcePreference.scope.asc())
        .all()
    )
    controls = (
        db.query(HealthRuntimeControl)
        .filter(HealthRuntimeControl.user_id == user_id)
        .order_by(HealthRuntimeControl.control_type.asc(), HealthRuntimeControl.target_key.asc())
        .all()
    )
    return {
        "source_quality": [serialize_data_source_quality(row) for row in quality],
        "source_preferences": [serialize_source_preference(row) for row in preferences],
        "controls": [serialize_runtime_control(row) for row in controls],
    }


def filter_predictions_by_controls(
    db: Session,
    user_id: int,
    predictions: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    controls = active_controls(db, user_id, control_type="prediction_category")
    if not controls:
        return list(predictions)
    blocked = {control.target_key for control in controls}
    return [
        prediction
        for prediction in predictions
        if str(prediction.get("domain") or "") not in blocked
        and str(prediction.get("prediction_type") or "") not in blocked
        and str(prediction.get("metric") or "") not in blocked
    ]


def active_controls(
    db: Session,
    user_id: int,
    *,
    control_type: str | None = None,
) -> List[HealthRuntimeControl]:
    q = db.query(HealthRuntimeControl).filter(
        HealthRuntimeControl.user_id == user_id,
        HealthRuntimeControl.status.in_(ACTIVE_CONTROL_STATUSES),
    )
    if control_type:
        q = q.filter(HealthRuntimeControl.control_type == control_type)
    return q.all()


def serialize_data_source_quality(row: DataSourceQuality) -> Dict[str, Any]:
    return {
        "id": row.id,
        "source_kind": row.source_kind,
        "source_id": row.source_id,
        "metric": row.metric,
        "quality_score": row.quality_score,
        "confidence": row.confidence,
        "freshness_seconds": row.freshness_seconds,
        "status": row.status,
        "reason": row.reason,
        "metadata": row.source_metadata or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def serialize_source_preference(row: UserDataSourcePreference) -> Dict[str, Any]:
    return {
        "id": row.id,
        "metric": row.metric,
        "preferred_source_kind": row.preferred_source_kind,
        "preferred_source_id": row.preferred_source_id,
        "scope": row.scope,
        "reason": row.reason,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def serialize_runtime_control(row: HealthRuntimeControl) -> Dict[str, Any]:
    return {
        "id": row.id,
        "control_type": row.control_type,
        "target_key": row.target_key,
        "status": row.status,
        "reason": row.reason,
        "metadata": row.control_metadata or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
