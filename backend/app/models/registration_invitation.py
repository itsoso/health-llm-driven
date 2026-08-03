"""Durable credentials for invitation-only phone registration."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.sql import func

from app.database import Base
from app.models._encrypted import StrictEncryptedString


_SQLITE_BIGINT = BigInteger().with_variant(Integer, "sqlite")
_ACTIVE_INVITATION_STATUSES = frozenset({"created", "sent", "send_failed"})
_ACTIVE_INVITATION_PREDICATE = "status IN ('created', 'sent', 'send_failed')"


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted and caller timestamps without using local timezone."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RegistrationInvitation(Base):
    """One phone-bound registration invitation.

    Credential plaintext is deliberately absent from the durable model.  The
    normalized phone is encrypted for delivery while its keyed HMAC supports
    equality matching and the masked form is safe for admin display.
    """

    __tablename__ = "registration_invitations"

    id = Column(_SQLITE_BIGINT, primary_key=True)
    code_digest = Column(String(128), nullable=False, unique=True)
    link_token_digest = Column(String(128), nullable=False, unique=True)
    phone_ciphertext = Column(StrictEncryptedString(512), nullable=False)
    phone_hmac = Column(String(128), nullable=False, index=True)
    phone_masked = Column(String(32), nullable=False)
    note = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="created", server_default="created", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    send_attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_send_error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'sent', 'send_failed', 'consumed', 'revoked', 'expired')",
            name="ck_registration_invitations_status",
        ),
        Index(
            "uq_registration_invitations_active_phone_hmac",
            "phone_hmac",
            unique=True,
            postgresql_where=text(_ACTIVE_INVITATION_PREDICATE),
            sqlite_where=text(_ACTIVE_INVITATION_PREDICATE),
        ),
    )

    def is_usable(self, now: datetime) -> bool:
        """Return current usability without mutating persisted lifecycle state."""

        return (
            self.status in _ACTIVE_INVITATION_STATUSES
            and self.consumed_at is None
            and self.expires_at is not None
            and _as_utc(self.expires_at) > _as_utc(now)
        )


class PhoneRegistrationGrant(Base):
    """Short-lived one-time proof that an unknown phone passed OTP verification."""

    __tablename__ = "phone_registration_grants"

    id = Column(_SQLITE_BIGINT, primary_key=True)
    token_digest = Column(String(128), nullable=False, unique=True)
    phone_hmac = Column(String(128), nullable=False, index=True)
    phone_ciphertext = Column(StrictEncryptedString(512), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key_digest = Column(String(128), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RegistrationAuthAttemptAudit(Base):
    """PII-minimized terminal outcome for one invited-registration attempt."""

    __tablename__ = "registration_auth_attempt_audits"

    id = Column(_SQLITE_BIGINT, primary_key=True)
    outcome = Column(String(16), nullable=False, index=True)
    error_code = Column(String(64), nullable=True, index=True)
    invitation_id = Column(
        _SQLITE_BIGINT,
        ForeignKey("registration_invitations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    grant_id = Column(
        _SQLITE_BIGINT,
        ForeignKey("phone_registration_grants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    phone_masked = Column(String(32), nullable=True)
    source_hmac = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'rejected')",
            name="ck_registration_auth_attempt_audits_outcome",
        ),
    )
