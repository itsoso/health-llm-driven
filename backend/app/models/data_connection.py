"""Governed external data connection, consent, provenance, and policy objects."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataConnection(Base):
    __tablename__ = "data_connections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(80), nullable=False)
    provider_type = Column(String(40), nullable=False, index=True)
    display_name = Column(String(160), nullable=False)
    connection_status = Column(String(30), nullable=False, default="active", index=True)
    scopes = Column(JSONB, nullable=False, default=list)
    token_status = Column(String(30), nullable=False, default="none")
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    sync_error = Column(Text, nullable=True)
    source_ref = Column(String(200), nullable=True)
    source_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_data_connections_user_provider", "user_id", "provider", unique=True),
    )


class ConsentGrant(Base):
    __tablename__ = "consent_grants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    connection_id = Column(Integer, ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    grantee_type = Column(String(40), nullable=False, index=True)
    grantee_id = Column(String(120), nullable=True)
    scopes = Column(JSONB, nullable=False, default=list)
    purpose = Column(String(240), nullable=False)
    status = Column(String(30), nullable=False, default="active", index=True)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_consent_grants_user_connection", "user_id", "connection_id"),
    )


class ConnectorPolicy(Base):
    __tablename__ = "connector_policies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    connection_id = Column(Integer, ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    scopes = Column(JSONB, nullable=False, default=list)
    rate_limit = Column(String(80), nullable=False, default="provider_default")
    token_status = Column(String(30), nullable=False, default="none")
    degraded_behavior = Column(String(80), nullable=False, default="read_only")
    data_minimization = Column(String(120), nullable=False, default="scoped_fields_only")
    revoke_deletes_derived = Column(Boolean, nullable=False, default=True)
    audit_required = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_connector_policies_user_connection", "user_id", "connection_id", unique=True),
    )


class ProvenanceRecord(Base):
    __tablename__ = "provenance_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    connection_id = Column(Integer, ForeignKey("data_connections.id", ondelete="SET NULL"), nullable=True, index=True)
    source_kind = Column(String(40), nullable=False, index=True)
    source_id = Column(String(160), nullable=False)
    object_type = Column(String(120), nullable=False, index=True)
    object_id = Column(String(160), nullable=False, index=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    transformed_by = Column(String(120), nullable=False)
    confidence = Column(String(30), nullable=False, default="unknown")
    privacy_classification = Column(String(20), nullable=False, default="L3")
    user_correction = Column(JSONB, nullable=False, default=dict)
    raw_hash = Column(String(128), nullable=True)
    source_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_provenance_records_user_object", "user_id", "object_type", "object_id"),
    )
