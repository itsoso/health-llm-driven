"""Admin-only preparation and lifecycle control for registration invitations."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import RegistrationInvitation
from app.models.user import User
from app.schemas.registration_invitation import (
    RegistrationInvitationCreate,
    RegistrationInvitationList,
    RegistrationInvitationPrepared,
    RegistrationInvitationSafe,
)
from app.services.phone_auth import InvalidPhoneNumber
from app.services.registration_invitation import (
    create_registration_invitation,
    phone_lookup_hmac,
    rotate_registration_invitation_credentials,
)


router = APIRouter(prefix="/admin/registration-invitations", tags=["admin-registration-invitations"])
_DEEP_LINK_PREFIX = "reva://register?invite="
_ACTIVE_STATUSES = ("created", "sent", "send_failed")
_MAX_PHONE_INPUT_LENGTH = 32


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_active(invitation: RegistrationInvitation, now: datetime) -> bool:
    return (
        invitation.status in _ACTIVE_STATUSES
        and invitation.consumed_at is None
        and _aware(invitation.expires_at) > now
    )


def _safe_payload(invitation: RegistrationInvitation) -> dict:
    return {
        "id": invitation.id,
        "phone_masked": invitation.phone_masked,
        "note": invitation.note,
        "status": invitation.status,
        "expires_at": _aware(invitation.expires_at),
        "created_at": _aware(invitation.created_at),
        "updated_at": _aware(invitation.updated_at),
        "prepared_for_delivery": invitation.status == "created",
    }


def _prepared_payload(invitation: RegistrationInvitation, manual_code: str, link_token: str) -> dict:
    return {
        **_safe_payload(invitation),
        "manual_code": manual_code,
        "link_token": link_token,
        "deep_link": f"{_DEEP_LINK_PREFIX}{link_token}",
    }


def _audit(admin: User, invitation: RegistrationInvitation, *, event: str, action: str) -> AgentAuditLog:
    return AgentAuditLog(
        user_id=admin.id,
        agent_type="registration_access_control",
        action=event,
        result_summary="管理员更新了注册邀请生命周期",
        result_detail={
            "invitation_id": invitation.id,
            "status": invitation.status,
            "action": action,
            "actor_id": admin.id,
        },
    )


def _expiry_replacement_audit(admin: User, invitation: RegistrationInvitation) -> AgentAuditLog:
    return AgentAuditLog(
        user_id=admin.id,
        agent_type="registration_access_control",
        action="registration_invitation_expired",
        result_summary="已过期注册邀请在创建替代邀请时关闭",
        result_detail={
            "invitation_id": invitation.id,
            "status": "expired",
            "action": "expire_for_replacement",
            "actor_id": admin.id,
            "reason": "time_expired",
        },
    )


def _is_active_phone_integrity_conflict(db: Session, exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == "uq_registration_invitations_active_phone_hmac":
        return True
    return (
        db.get_bind().dialect.name == "sqlite"
        and str(exc.orig).strip()
        == "UNIQUE constraint failed: registration_invitations.phone_hmac"
    )


def _rollback_and_raise(db: Session, exc: Exception) -> None:
    db.rollback()
    if isinstance(exc, IntegrityError) and _is_active_phone_integrity_conflict(db, exc):
        raise _error(
            status.HTTP_409_CONFLICT,
            "active_registration_invitation_conflict",
            "该手机号当前无法创建新邀请",
        ) from None
    raise _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "registration_invitation_persistence_failed",
        "注册邀请暂时无法保存，请稍后重试",
    ) from None


@router.post("", response_model=RegistrationInvitationPrepared, status_code=status.HTTP_201_CREATED)
def create_invitation(
    request: RegistrationInvitationCreate,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    if request.expires_at is not None and _aware(request.expires_at) <= now:
        raise _error(422, "registration_invitation_expiry_invalid", "邀请有效期必须晚于当前时间")
    try:
        if (
            not isinstance(request.phone, str)
            or not request.phone.strip()
            or len(request.phone) > _MAX_PHONE_INPUT_LENGTH
        ):
            raise InvalidPhoneNumber("invalid bounded phone input")
        phone_hmac = phone_lookup_hmac(request.phone)
        existing = (
            db.query(RegistrationInvitation)
            .filter(
                RegistrationInvitation.phone_hmac == phone_hmac,
                RegistrationInvitation.status.in_(_ACTIVE_STATUSES),
            )
            .with_for_update()
            .first()
        )
        if existing is not None and _is_active(existing, now):
            raise _error(
                status.HTTP_409_CONFLICT,
                "active_registration_invitation_conflict",
                "该手机号当前无法创建新邀请",
            )
        replaced_expired: RegistrationInvitation | None = None
        if existing is not None:
            existing.status = "expired"
            db.flush()
            replaced_expired = existing
        created = create_registration_invitation(
            db,
            request.phone,
            created_by=admin.id,
            note=request.note,
            expires_at=request.expires_at,
            now=now,
        )
        if replaced_expired is not None:
            db.add(_expiry_replacement_audit(admin, replaced_expired))
        db.add(
            _audit(
                admin,
                created.invitation,
                event="registration_invitation_created",
                action="create",
            )
        )
        db.flush()
        response = RegistrationInvitationPrepared(
            **_prepared_payload(
                created.invitation,
                created.manual_code,
                created.link_token,
            )
        )
        db.commit()
        return response
    except HTTPException:
        db.rollback()
        raise
    except InvalidPhoneNumber:
        db.rollback()
        raise _error(422, "registration_invitation_phone_invalid", "手机号格式不正确") from None
    except (IntegrityError, SQLAlchemyError) as exc:
        _rollback_and_raise(db, exc)


@router.get("", response_model=RegistrationInvitationList)
def list_invitations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    del admin
    query = db.query(RegistrationInvitation)
    total = query.count()
    rows = (
        query.order_by(desc(RegistrationInvitation.created_at), desc(RegistrationInvitation.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [_safe_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def _locked_invitation(db: Session, invitation_id: int) -> RegistrationInvitation:
    invitation = (
        db.query(RegistrationInvitation)
        .filter(RegistrationInvitation.id == invitation_id)
        .with_for_update()
        .one_or_none()
    )
    if invitation is None:
        raise _error(404, "registration_invitation_not_found", "注册邀请不存在")
    if not _is_active(invitation, datetime.now(UTC)):
        raise _error(409, "registration_invitation_not_active", "注册邀请当前不可操作")
    return invitation


@router.post("/{invitation_id}/resend", response_model=RegistrationInvitationPrepared)
def prepare_resend(
    invitation_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        invitation = _locked_invitation(db, invitation_id)
        rotated = rotate_registration_invitation_credentials(db, invitation)
        db.add(
            _audit(
                admin,
                invitation,
                event="registration_invitation_credentials_rotated",
                action="resend_prepare",
            )
        )
        db.flush()
        response = RegistrationInvitationPrepared(
            **_prepared_payload(
                invitation,
                rotated.manual_code,
                rotated.link_token,
            )
        )
        db.commit()
        return response
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, SQLAlchemyError) as exc:
        _rollback_and_raise(db, exc)


@router.post("/{invitation_id}/revoke", response_model=RegistrationInvitationSafe)
def revoke_invitation(
    invitation_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        invitation = _locked_invitation(db, invitation_id)
        invitation.status = "revoked"
        db.flush()
        db.add(
            _audit(
                admin,
                invitation,
                event="registration_invitation_revoked",
                action="revoke",
            )
        )
        db.flush()
        response = RegistrationInvitationSafe(**_safe_payload(invitation))
        db.commit()
        return response
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, SQLAlchemyError) as exc:
        _rollback_and_raise(db, exc)
