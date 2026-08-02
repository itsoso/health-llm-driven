"""Admin-only preparation and lifecycle control for registration invitations."""

from __future__ import annotations

from datetime import UTC, datetime
import logging

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
    build_registration_invitation_deep_link,
    create_registration_invitation,
    phone_lookup_hmac,
    rotate_registration_invitation_credentials,
)
from app.services.registration_invitation_sms import (
    FrozenRegistrationInvitationDelivery,
    RegistrationInvitationDeliveryResult,
    apply_registration_invitation_delivery_outcome,
    freeze_registration_invitation_delivery,
    send_frozen_registration_invitation_sms,
)


router = APIRouter(prefix="/admin/registration-invitations", tags=["admin-registration-invitations"])
logger = logging.getLogger(__name__)
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


def _credential_payload_snapshot(
    invitation: RegistrationInvitation,
    manual_code: str,
    link_token: str,
) -> dict:
    return {
        **_safe_payload(invitation),
        "manual_code": manual_code,
        "link_token": link_token,
        "deep_link": build_registration_invitation_deep_link(link_token),
    }


def _delivered_payload(
    invitation: RegistrationInvitation,
    credential_snapshot: dict,
    outcome: RegistrationInvitationDeliveryResult,
) -> dict:
    return {
        **credential_snapshot,
        **_safe_payload(invitation),
        "delivery_status": outcome.delivery_status,
        "delivery_error_code": outcome.error_code,
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


def _phase_two_persistence_error(
    db: Session,
    *,
    invitation_id: int,
    outcome: RegistrationInvitationDeliveryResult,
) -> None:
    db.rollback()
    error_code = (
        "provider_ack_persistence_failed"
        if outcome.delivery_status == "sent"
        else "delivery_outcome_persistence_failed"
    )
    # CRITICAL is the durable operational signal when the database cannot
    # record its own terminal audit. It is intentionally bounded and contains
    # neither provider response details nor delivery credentials.
    logger.critical(
        "registration invitation delivery outcome persistence failed "
        "invitation_id=%s delivery_status=%s error_code=%s",
        invitation_id,
        outcome.delivery_status,
        error_code,
    )
    message = (
        "短信可能已送达，但邀请状态暂时无法确认；请勿立即重试"
        if outcome.delivery_status == "sent"
        else "邀请已保存，但短信投递状态暂时无法确认；请勿立即重试"
    )
    raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, error_code, message) from None


def _persist_delivery_outcome(
    db: Session,
    *,
    delivery_payload: FrozenRegistrationInvitationDelivery,
    actor_id: int,
    credential_snapshot: dict,
    outcome: RegistrationInvitationDeliveryResult,
) -> RegistrationInvitationPrepared:
    try:
        invitation = (
            db.query(RegistrationInvitation)
            .filter(
                RegistrationInvitation.id == delivery_payload.invitation_id,
                RegistrationInvitation.status == "created",
                RegistrationInvitation.code_digest == delivery_payload.expected_code_digest,
                RegistrationInvitation.link_token_digest
                == delivery_payload.expected_link_token_digest,
            )
            .with_for_update()
            .one_or_none()
        )
        if invitation is None:
            db.rollback()
            logger.warning(
                "registration invitation delivery attempt superseded "
                "invitation_id=%s operation=persist_delivery_outcome",
                delivery_payload.invitation_id,
            )
            raise _error(
                status.HTTP_409_CONFLICT,
                "delivery_attempt_superseded",
                "该邀请已被更新，本次短信结果不再适用于当前凭据",
            )
        apply_registration_invitation_delivery_outcome(
            db,
            invitation,
            outcome=outcome,
            actor_id=actor_id,
        )
        db.flush()
        response = RegistrationInvitationPrepared(
            **_delivered_payload(invitation, credential_snapshot, outcome)
        )
        db.commit()
        return response
    except HTTPException:
        raise
    except Exception:
        _phase_two_persistence_error(
            db,
            invitation_id=delivery_payload.invitation_id,
            outcome=outcome,
        )


def _send_after_phase_one(delivery_payload):
    try:
        return send_frozen_registration_invitation_sms(delivery_payload)
    except Exception:
        # The normal transport function converts all provider failures into a
        # bounded outcome. This guard covers unexpected pre-dispatch/runtime
        # faults while preserving the already committed recoverable row.
        logger.critical(
            "registration invitation delivery did not start invitation_id=%s "
            "error_code=registration_invitation_delivery_not_started",
            delivery_payload.invitation_id,
        )
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "registration_invitation_delivery_not_started",
            "邀请已保存，但短信发送尚未开始；请稍后由管理员重发",
        ) from None


@router.post("", response_model=RegistrationInvitationPrepared, status_code=status.HTTP_201_CREATED)
def create_invitation(
    request: RegistrationInvitationCreate,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    actor_id = int(admin.id)
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
        delivery_payload = freeze_registration_invitation_delivery(
            created.invitation,
            manual_code=created.manual_code,
            link_token=created.link_token,
        )
        db.flush()
        credential_snapshot = _credential_payload_snapshot(
            created.invitation,
            created.manual_code,
            created.link_token,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except InvalidPhoneNumber:
        db.rollback()
        raise _error(422, "registration_invitation_phone_invalid", "手机号格式不正确") from None
    except (IntegrityError, SQLAlchemyError) as exc:
        _rollback_and_raise(db, exc)

    # Phase 1 is durable before any provider side effect. Everything below uses
    # frozen plain values because commit expires ORM state by default.
    outcome = _send_after_phase_one(delivery_payload)
    return _persist_delivery_outcome(
        db,
        delivery_payload=delivery_payload,
        actor_id=actor_id,
        credential_snapshot=credential_snapshot,
        outcome=outcome,
    )


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
    actor_id = int(admin.id)
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
        delivery_payload = freeze_registration_invitation_delivery(
            invitation,
            manual_code=rotated.manual_code,
            link_token=rotated.link_token,
        )
        db.flush()
        credential_snapshot = _credential_payload_snapshot(
            invitation,
            rotated.manual_code,
            rotated.link_token,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, SQLAlchemyError) as exc:
        _rollback_and_raise(db, exc)

    outcome = _send_after_phase_one(delivery_payload)
    return _persist_delivery_outcome(
        db,
        delivery_payload=delivery_payload,
        actor_id=actor_id,
        credential_snapshot=credential_snapshot,
        outcome=outcome,
    )


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
