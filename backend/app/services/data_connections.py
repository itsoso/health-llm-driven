"""Data connection governance service.

This layer owns connection status, user consent, provenance, and connector policy
metadata. It deliberately does not store raw provider tokens.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.data_connection import (
    ConsentGrant,
    ConnectorPolicy,
    DataConnection,
    ProvenanceRecord,
)

ALLOWED_PROVIDER_TYPES = {
    "wearable",
    "device",
    "report",
    "fhir_bundle",
    "healthkit",
    "manual",
    "lab",
}
ACTIVE_GRANT_STATUS = "active"


def upsert_data_connection(
    db: Session,
    *,
    user_id: int,
    provider: str,
    provider_type: str,
    display_name: str,
    scopes: list[str],
    token_status: str = "none",
    source_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DataConnection:
    provider_type = _normalize_provider_type(provider_type)
    connection = (
        db.query(DataConnection)
        .filter(DataConnection.user_id == user_id, DataConnection.provider == provider)
        .first()
    )
    if connection is None:
        connection = DataConnection(user_id=user_id, provider=provider)
        db.add(connection)

    connection.provider_type = provider_type
    connection.display_name = display_name
    connection.connection_status = "active"
    connection.scopes = _dedupe_scopes(scopes)
    connection.token_status = token_status
    connection.source_ref = source_ref
    connection.source_metadata = metadata or {}
    connection.sync_error = None
    db.flush()
    _ensure_policy(db, connection)
    db.commit()
    db.refresh(connection)
    return connection


def list_connection_summaries(db: Session, *, user_id: int) -> list[dict[str, Any]]:
    connections = (
        db.query(DataConnection)
        .filter(DataConnection.user_id == user_id)
        .order_by(DataConnection.provider.asc(), DataConnection.id.asc())
        .all()
    )
    return [serialize_data_connection(db, connection) for connection in connections]


def serialize_data_connection(db: Session, connection: DataConnection) -> dict[str, Any]:
    grants = (
        db.query(ConsentGrant)
        .filter(
            ConsentGrant.user_id == connection.user_id,
            ConsentGrant.connection_id == connection.id,
            ConsentGrant.status == ACTIVE_GRANT_STATUS,
        )
        .order_by(ConsentGrant.granted_at.desc(), ConsentGrant.id.desc())
        .all()
    )
    policy = (
        db.query(ConnectorPolicy)
        .filter(ConnectorPolicy.user_id == connection.user_id, ConnectorPolicy.connection_id == connection.id)
        .first()
    )
    return {
        "id": connection.id,
        "provider": connection.provider,
        "provider_type": connection.provider_type,
        "display_name": connection.display_name,
        "connection_status": connection.connection_status,
        "scopes": connection.scopes or [],
        "token_status": connection.token_status,
        "last_success_at": _iso(connection.last_success_at),
        "last_attempt_at": _iso(connection.last_attempt_at),
        "sync_error": connection.sync_error,
        "source_ref": connection.source_ref,
        "metadata": connection.source_metadata or {},
        "active_consents": [serialize_consent_grant(grant) for grant in grants],
        "policy": serialize_connector_policy(policy) if policy else None,
    }


def create_consent_grant(
    db: Session,
    *,
    user_id: int,
    connection_id: int,
    grantee_type: str,
    grantee_id: str | None,
    scopes: list[str],
    purpose: str,
    expires_at: datetime | None = None,
) -> ConsentGrant:
    connection = _get_user_connection(db, user_id=user_id, connection_id=connection_id)
    allowed_scopes = set(connection.scopes or [])
    requested_scopes = _dedupe_scopes(scopes)
    if not requested_scopes or any(scope not in allowed_scopes for scope in requested_scopes):
        raise ValueError("consent scopes must be a non-empty subset of connection scopes")
    grant = ConsentGrant(
        user_id=user_id,
        connection_id=connection_id,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        scopes=requested_scopes,
        purpose=purpose,
        expires_at=expires_at,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def serialize_consent_grant(grant: ConsentGrant) -> dict[str, Any]:
    return {
        "id": grant.id,
        "connection_id": grant.connection_id,
        "grantee_type": grant.grantee_type,
        "grantee_id": grant.grantee_id,
        "scopes": grant.scopes or [],
        "purpose": grant.purpose,
        "status": grant.status,
        "granted_at": _iso(grant.granted_at),
        "revoked_at": _iso(grant.revoked_at),
        "expires_at": _iso(grant.expires_at),
    }


def revoke_data_connection(db: Session, *, user_id: int, connection_id: int) -> DataConnection:
    connection = _get_user_connection(db, user_id=user_id, connection_id=connection_id)
    now = _now()
    connection.connection_status = "revoked"
    connection.token_status = "revoked"
    connection.sync_error = None
    grants = (
        db.query(ConsentGrant)
        .filter(
            ConsentGrant.user_id == user_id,
            ConsentGrant.connection_id == connection_id,
            ConsentGrant.status == ACTIVE_GRANT_STATUS,
        )
        .all()
    )
    for grant in grants:
        grant.status = "revoked"
        grant.revoked_at = now
    policy = (
        db.query(ConnectorPolicy)
        .filter(ConnectorPolicy.user_id == user_id, ConnectorPolicy.connection_id == connection_id)
        .first()
    )
    if policy:
        policy.token_status = "revoked"
    db.commit()
    db.refresh(connection)
    return connection


def record_sync_result(
    db: Session,
    *,
    user_id: int,
    connection_id: int,
    success: bool,
    error_message: str | None = None,
    is_auth_error: bool = False,
) -> DataConnection:
    connection = _get_user_connection(db, user_id=user_id, connection_id=connection_id)
    now = _now()
    connection.last_attempt_at = now
    if success:
        connection.connection_status = "active"
        connection.last_success_at = now
        connection.sync_error = None
        if connection.token_status in {"expired", "revoked"}:
            connection.token_status = "valid"
    else:
        connection.connection_status = "degraded"
        connection.sync_error = error_message
        if is_auth_error:
            connection.token_status = "expired"
    policy = (
        db.query(ConnectorPolicy)
        .filter(ConnectorPolicy.user_id == user_id, ConnectorPolicy.connection_id == connection_id)
        .first()
    )
    if policy:
        policy.token_status = connection.token_status
    db.commit()
    db.refresh(connection)
    return connection


def create_provenance_record(
    db: Session,
    *,
    user_id: int,
    connection_id: int | None,
    source_kind: str,
    source_id: str,
    object_type: str,
    object_id: str,
    transformed_by: str,
    observed_at: datetime | None = None,
    received_at: datetime | None = None,
    confidence: str = "unknown",
    privacy_classification: str = "L3",
    user_correction: dict[str, Any] | None = None,
    raw_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProvenanceRecord:
    if connection_id is not None:
        _get_user_connection(db, user_id=user_id, connection_id=connection_id)
    record = ProvenanceRecord(
        user_id=user_id,
        connection_id=connection_id,
        source_kind=source_kind,
        source_id=source_id,
        object_type=object_type,
        object_id=object_id,
        observed_at=observed_at,
        received_at=received_at or _now(),
        transformed_by=transformed_by,
        confidence=confidence,
        privacy_classification=privacy_classification,
        user_correction=user_correction or {},
        raw_hash=raw_hash,
        source_metadata=metadata or {},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def serialize_provenance_record(record: ProvenanceRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "connection_id": record.connection_id,
        "source_kind": record.source_kind,
        "source_id": record.source_id,
        "object_type": record.object_type,
        "object_id": record.object_id,
        "observed_at": _iso(record.observed_at),
        "received_at": _iso(record.received_at),
        "transformed_by": record.transformed_by,
        "confidence": record.confidence,
        "privacy_classification": record.privacy_classification,
        "user_correction": record.user_correction or {},
        "raw_hash": record.raw_hash,
        "metadata": record.source_metadata or {},
    }


def serialize_connector_policy(policy: ConnectorPolicy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "connection_id": policy.connection_id,
        "scopes": policy.scopes or [],
        "rate_limit": policy.rate_limit,
        "token_status": policy.token_status,
        "degraded_behavior": policy.degraded_behavior,
        "data_minimization": policy.data_minimization,
        "revoke_deletes_derived": policy.revoke_deletes_derived,
        "audit_required": policy.audit_required,
    }


def _ensure_policy(db: Session, connection: DataConnection) -> ConnectorPolicy:
    policy = (
        db.query(ConnectorPolicy)
        .filter(ConnectorPolicy.user_id == connection.user_id, ConnectorPolicy.connection_id == connection.id)
        .first()
    )
    if policy is None:
        policy = ConnectorPolicy(user_id=connection.user_id, connection_id=connection.id)
        db.add(policy)
    policy.scopes = connection.scopes or []
    policy.token_status = connection.token_status
    return policy


def _get_user_connection(db: Session, *, user_id: int, connection_id: int) -> DataConnection:
    connection = (
        db.query(DataConnection)
        .filter(DataConnection.user_id == user_id, DataConnection.id == connection_id)
        .first()
    )
    if connection is None:
        raise LookupError("data connection not found")
    return connection


def _normalize_provider_type(provider_type: str) -> str:
    normalized = provider_type.strip().lower()
    if normalized not in ALLOWED_PROVIDER_TYPES:
        raise ValueError(f"unsupported provider_type: {provider_type}")
    return normalized


def _dedupe_scopes(scopes: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for scope in scopes:
        normalized = scope.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
