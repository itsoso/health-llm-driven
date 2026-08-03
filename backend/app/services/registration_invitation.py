"""Security primitives for invitation-only phone registration.

Credential plaintext has a deliberately short lifetime: it is returned once
from a creation call and is never copied onto an ORM object. Durable lookups use
purpose-separated keyed HMAC-SHA256 digests; the delivery phone is encrypted by
the model's ``StrictEncryptedString`` column.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
import secrets
from typing import Any, Final

from sqlalchemy.orm import Session

from app.config import settings
from app.models.registration_invitation import (
    PhoneRegistrationGrant,
    RegistrationInvitation,
)
from app.services.phone_auth import InvalidPhoneNumber, mask_phone, normalize_phone


MANUAL_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
REGISTRATION_INVITATION_DEEP_LINK_PREFIX: Final = "health://invite?token="
_DUMMY_DIGEST = "0" * 64
_CODE_PURPOSE = "registration-invitation-code:v1"
_LINK_PURPOSE = "registration-invitation-link:v1"
_PHONE_PURPOSE = "registration-invitation-phone:v1"
_GRANT_PURPOSE = "phone-registration-grant:v1"
_IDEMPOTENCY_PURPOSE = "invited-registration-idempotency:v1"
_SOURCE_PURPOSE = "invited-registration-request-source:v1"
_INVALID_CODE = "<invalid-registration-code>"
_INVALID_LINK_TOKEN = "<invalid-registration-link-token>"
_INVALID_GRANT_TOKEN = "<invalid-phone-registration-grant>"
_INVALID_GENERIC_CREDENTIAL = "<invalid-registration-credential>"
_URL_SAFE_CREDENTIAL_RE = re.compile(r"[A-Za-z0-9_-]{22,128}\Z")
_MANUAL_CODE_RE = re.compile(f"[{MANUAL_CODE_ALPHABET}]{{8}}\\Z")


class InvalidRegistrationCredential(ValueError):
    """A registration credential is absent, expired, mismatched, or replayed."""


@dataclass(frozen=True, repr=False)
class CreatedRegistrationInvitation:
    invitation: RegistrationInvitation
    manual_code: str
    link_token: str

    def __repr__(self) -> str:
        return (
            "CreatedRegistrationInvitation("
            f"invitation_id={self.invitation.id!r}, "
            f"phone={self.invitation.phone_masked!r}, credentials=<redacted>)"
        )


@dataclass(frozen=True, repr=False)
class IssuedPhoneRegistrationGrant:
    grant: PhoneRegistrationGrant
    token: str
    expires_at: datetime

    def __repr__(self) -> str:
        return (
            "IssuedPhoneRegistrationGrant("
            f"grant_id={self.grant.id!r}, expires_at={self.expires_at!r}, "
            "token=<redacted>)"
        )


@dataclass(frozen=True, repr=False)
class RotatedRegistrationInvitationCredentials:
    invitation: RegistrationInvitation
    manual_code: str
    link_token: str

    def __repr__(self) -> str:
        return (
            "RotatedRegistrationInvitationCredentials("
            f"invitation_id={self.invitation.id!r}, credentials=<redacted>)"
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _digest_key() -> bytes:
    configured = (settings.registration_invitation_digest_key or "").strip()
    if configured:
        encoded = configured.encode("utf-8")
        if len(encoded) < 32:
            raise RuntimeError("registration invitation credential protection is unavailable")
        return encoded
    if (
        (settings.app_env or "").strip().lower() == "production"
        and (
            settings.registration_invitation_rollout_enabled
            or settings.registration_invitation_enforcement_enabled
        )
    ):
        raise RuntimeError("registration invitation credential protection is unavailable")
    # Local/test convenience only. Domain separation keeps these values distinct
    # from existing phone OTP and JWT uses of SECRET_KEY.
    return hashlib.sha256(
        b"registration-invitation-dev-key:v1\0" + settings.secret_key.encode("utf-8")
    ).digest()


def _digest(value: str, purpose: str) -> str:
    return hmac.new(
        _digest_key(),
        f"{purpose}\0{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _credential_text(value: Any, *, purpose: str) -> str:
    """Bound and validate public credentials before they reach HMAC input."""

    sentinel = {
        _CODE_PURPOSE: _INVALID_CODE,
        _LINK_PURPOSE: _INVALID_LINK_TOKEN,
        _GRANT_PURPOSE: _INVALID_GRANT_TOKEN,
    }.get(purpose, _INVALID_GENERIC_CREDENTIAL)
    # Do not interpolate an invalid object into an error or sentinel: its repr
    # may itself carry a secret. Invalid values take a fixed-size HMAC path.
    if not isinstance(value, str):
        return sentinel
    clean = value.strip()
    if purpose == _CODE_PURPOSE:
        clean = clean.upper()
        return clean if _MANUAL_CODE_RE.fullmatch(clean) else sentinel
    if purpose in {_LINK_PURPOSE, _GRANT_PURPOSE}:
        return clean if _URL_SAFE_CREDENTIAL_RE.fullmatch(clean) else sentinel
    return sentinel


def build_registration_invitation_deep_link(link_token: Any) -> str:
    """Build the canonical mobile deep link without reflecting invalid credentials."""

    clean_token = _credential_text(link_token, purpose=_LINK_PURPOSE)
    if clean_token == _INVALID_LINK_TOKEN:
        raise InvalidRegistrationCredential("invalid registration invitation link token")
    return f"{REGISTRATION_INVITATION_DEEP_LINK_PREFIX}{clean_token}"


def _constant_time_digest_match(candidate: str, stored: Any) -> bool:
    safe_stored = stored if isinstance(stored, str) and len(stored) == 64 else _DUMMY_DIGEST
    return hmac.compare_digest(candidate, safe_stored)


def credential_digest(value: Any, *, purpose: str) -> str:
    """Return a purpose-separated digest without retaining credential plaintext."""

    return _digest(_credential_text(value, purpose=purpose), purpose)


def credential_matches(value: Any, stored_digest: Any, *, purpose: str) -> bool:
    """Compare credentials through the same HMAC + constant-time path, even if invalid."""

    candidate = credential_digest(value, purpose=purpose)
    return _constant_time_digest_match(candidate, stored_digest)


def phone_lookup_hmac(raw_phone: str) -> str:
    """Normalize a phone once and derive its non-reversible equality key."""

    return _digest(normalize_phone(raw_phone), _PHONE_PURPOSE)


def _manual_code_digest(value: Any) -> str:
    return _digest(_credential_text(value, purpose=_CODE_PURPOSE), _CODE_PURPOSE)


def _link_token_digest(value: Any) -> str:
    return _digest(_credential_text(value, purpose=_LINK_PURPOSE), _LINK_PURPOSE)


def _grant_token_digest(value: Any) -> str:
    return _digest(_credential_text(value, purpose=_GRANT_PURPOSE), _GRANT_PURPOSE)


def registration_idempotency_digest(value: str) -> str:
    """Digest a bounded client retry key in a dedicated credential domain."""

    return _digest(value, _IDEMPOTENCY_PURPOSE)


def registration_source_hmac(value: Any) -> str | None:
    """Return a bounded, purpose-separated request-source HMAC.

    Source attribution is optional observability. Invalid input or key
    unavailability must never change registration behavior.
    """

    if not isinstance(value, str):
        return None
    clean = value.strip()
    if not clean or len(clean) > 256:
        return None
    try:
        return _digest(clean, _SOURCE_PURPOSE)
    except Exception:
        return None


def find_phone_registration_grant_for_update(
    db: Session, token: Any
) -> PhoneRegistrationGrant | None:
    candidate = _grant_token_digest(token)
    grant = (
        db.query(PhoneRegistrationGrant)
        .filter(PhoneRegistrationGrant.token_digest == candidate)
        .with_for_update()
        .one_or_none()
    )
    stored = grant.token_digest if grant is not None else _DUMMY_DIGEST
    return grant if _constant_time_digest_match(candidate, stored) else None


def find_invitation_for_update(
    db: Session,
    *,
    manual_code: Any = None,
    link_token: Any = None,
) -> RegistrationInvitation | None:
    if (manual_code is None) == (link_token is None):
        return None
    if manual_code is not None:
        candidate = _manual_code_digest(manual_code)
        column = RegistrationInvitation.code_digest
    else:
        candidate = _link_token_digest(link_token)
        column = RegistrationInvitation.link_token_digest
    invitation = (
        db.query(RegistrationInvitation)
        .filter(column == candidate)
        .with_for_update()
        .one_or_none()
    )
    stored = getattr(invitation, column.key) if invitation is not None else _DUMMY_DIGEST
    return invitation if _constant_time_digest_match(candidate, stored) else None


def _find_invitation_by_digest(
    db: Session,
    candidate_digest: str,
    digest_column: Any,
) -> RegistrationInvitation | None:
    invitation = (
        db.query(RegistrationInvitation)
        .filter(digest_column == candidate_digest)
        .one_or_none()
    )
    stored_digest = getattr(invitation, digest_column.key) if invitation is not None else _DUMMY_DIGEST
    if not _constant_time_digest_match(candidate_digest, stored_digest):
        return None
    return invitation


def find_invitation_by_code(db: Session, manual_code: Any) -> RegistrationInvitation | None:
    candidate = _manual_code_digest(manual_code)
    return _find_invitation_by_digest(db, candidate, RegistrationInvitation.code_digest)


def find_invitation_by_link_token(db: Session, link_token: Any) -> RegistrationInvitation | None:
    candidate = _link_token_digest(link_token)
    return _find_invitation_by_digest(db, candidate, RegistrationInvitation.link_token_digest)


def create_registration_invitation(
    db: Session,
    raw_phone: str,
    *,
    created_by: int | None = None,
    note: str | None = None,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> CreatedRegistrationInvitation:
    canonical_phone = normalize_phone(raw_phone)
    issued_at = _aware(now or _now())
    manual_code = "".join(secrets.choice(MANUAL_CODE_ALPHABET) for _ in range(8))
    # 24 random bytes = 192 bits, comfortably above the 128-bit minimum.
    link_token = secrets.token_urlsafe(24)
    expiration = expires_at or (
        issued_at + timedelta(days=max(int(settings.registration_invitation_expiry_days), 1))
    )
    invitation = RegistrationInvitation(
        code_digest=_manual_code_digest(manual_code),
        link_token_digest=_link_token_digest(link_token),
        phone_ciphertext=canonical_phone,
        phone_hmac=_digest(canonical_phone, _PHONE_PURPOSE),
        phone_masked=mask_phone(canonical_phone),
        note=note,
        status="created",
        expires_at=_aware(expiration),
        created_by=created_by,
    )
    db.add(invitation)
    db.flush()
    return CreatedRegistrationInvitation(
        invitation=invitation,
        manual_code=manual_code,
        link_token=link_token,
    )


def rotate_registration_invitation_credentials(
    db: Session,
    invitation: RegistrationInvitation,
) -> RotatedRegistrationInvitationCredentials:
    """Replace both credentials in-place and return plaintext exactly once.

    The caller must lock the invitation row and commit the enclosing transaction.
    """

    manual_code = "".join(secrets.choice(MANUAL_CODE_ALPHABET) for _ in range(8))
    link_token = secrets.token_urlsafe(24)
    invitation.code_digest = _manual_code_digest(manual_code)
    invitation.link_token_digest = _link_token_digest(link_token)
    invitation.status = "created"
    invitation.last_send_error_code = None
    db.flush()
    return RotatedRegistrationInvitationCredentials(
        invitation=invitation,
        manual_code=manual_code,
        link_token=link_token,
    )


def create_phone_registration_grant(
    db: Session,
    raw_phone: str,
    *,
    now: datetime | None = None,
) -> IssuedPhoneRegistrationGrant:
    canonical_phone = normalize_phone(raw_phone)
    issued_at = _aware(now or _now())
    expires_at = issued_at + timedelta(
        seconds=max(int(settings.registration_invitation_grant_ttl_seconds), 1)
    )
    # 32 random bytes = 256 bits. Only its digest crosses into persistence.
    token = secrets.token_urlsafe(32)
    grant = PhoneRegistrationGrant(
        token_digest=_grant_token_digest(token),
        phone_hmac=_digest(canonical_phone, _PHONE_PURPOSE),
        phone_ciphertext=canonical_phone,
        expires_at=expires_at,
    )
    db.add(grant)
    db.flush()
    return IssuedPhoneRegistrationGrant(grant=grant, token=token, expires_at=expires_at)


def consume_phone_registration_grant(
    db: Session,
    token: Any,
    raw_phone: Any,
    *,
    now: datetime | None = None,
) -> PhoneRegistrationGrant:
    consumed_at = _aware(now or _now())
    candidate_digest = _grant_token_digest(token)
    grant = (
        db.query(PhoneRegistrationGrant)
        .filter(PhoneRegistrationGrant.token_digest == candidate_digest)
        .with_for_update()
        .one_or_none()
    )
    stored_digest = grant.token_digest if grant is not None else _DUMMY_DIGEST
    token_matches = _constant_time_digest_match(candidate_digest, stored_digest)

    try:
        expected_phone_hmac = phone_lookup_hmac(raw_phone)
    except (InvalidPhoneNumber, TypeError, AttributeError):
        expected_phone_hmac = _DUMMY_DIGEST
    stored_phone_hmac = grant.phone_hmac if grant is not None else _DUMMY_DIGEST
    phone_matches = _constant_time_digest_match(expected_phone_hmac, stored_phone_hmac)

    if (
        not token_matches
        or not phone_matches
        or grant is None
        or grant.consumed_at is not None
        or _aware(grant.expires_at) <= consumed_at
    ):
        raise InvalidRegistrationCredential("registration credential is invalid or expired")

    grant.consumed_at = consumed_at
    db.flush()
    return grant
