"""Dedicated SMS delivery for phone-bound registration invitations.

The provider call and database transaction cannot be atomic.  This module
therefore performs exactly one provider attempt, records a bounded terminal
outcome on the invitation transaction, and never retries automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from typing import Final
import uuid

import httpx
from httpx import TimeoutException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import RegistrationInvitation
from app.services import phone_auth
from app.services.registration_invitation import build_registration_invitation_deep_link


logger = logging.getLogger(__name__)

_ERROR_NOT_CONFIGURED: Final = "sms_not_configured"
_ERROR_PROVIDER_REJECTED: Final = "provider_rejected"
_ERROR_PROVIDER_INVALID_ACK: Final = "provider_invalid_ack"
_ERROR_PROVIDER_TIMEOUT: Final = "provider_timeout"
_ERROR_TRANSPORT_FAILED: Final = "transport_failed"


@dataclass(frozen=True)
class RegistrationInvitationDeliveryResult:
    delivery_status: str
    error_code: str | None


@dataclass(frozen=True, repr=False)
class FrozenRegistrationInvitationDelivery:
    invitation_id: int
    expected_code_digest: str
    expected_link_token_digest: str
    phone: str
    manual_code: str
    link_token: str
    expires_at: datetime

    def __repr__(self) -> str:
        return (
            "FrozenRegistrationInvitationDelivery("
            f"invitation_id={self.invitation_id!r}, delivery=<redacted>)"
        )


class _InviteSmsNotConfigured(RuntimeError):
    pass


class _InviteSmsProviderRejected(RuntimeError):
    pass


class _InviteSmsInvalidAck(RuntimeError):
    pass


def _delivery_config(config=settings) -> tuple[str, str, str, str]:
    try:
        access_key_id, access_key_secret, sign_name, template_code = (
            config.registration_invitation_sms_delivery_config
        )
    except ValueError as exc:
        raise _InviteSmsNotConfigured(
            "registration invitation SMS is not configured"
        ) from exc
    if not access_key_id or not access_key_secret or not sign_name or not template_code:
        raise _InviteSmsNotConfigured("registration invitation SMS is not configured")
    return access_key_id, access_key_secret, sign_name, template_code


def validate_registration_invitation_sms_config(config=settings) -> None:
    """Fail explicitly when an enabled runtime lacks its dedicated template."""

    _delivery_config(config)


def freeze_registration_invitation_delivery(
    invitation: RegistrationInvitation,
    *,
    manual_code: str,
    link_token: str,
) -> FrozenRegistrationInvitationDelivery:
    return FrozenRegistrationInvitationDelivery(
        invitation_id=int(invitation.id),
        expected_code_digest=str(invitation.code_digest),
        expected_link_token_digest=str(invitation.link_token_digest),
        phone=str(invitation.phone_ciphertext),
        manual_code=manual_code,
        link_token=link_token,
        expires_at=invitation.expires_at,
    )


def _template_params(payload: FrozenRegistrationInvitationDelivery) -> dict[str, str]:
    expires_at = payload.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    else:
        expires_at = expires_at.astimezone(UTC)
    # This allowlist is deliberately narrow. Notes, health context, phone and
    # durable credential material must never become template variables.
    return {
        "code": payload.manual_code,
        "link": build_registration_invitation_deep_link(payload.link_token),
        "expires": expires_at.strftime("%Y-%m-%d %H:%M UTC"),
    }


def build_aliyun_invitation_sms_params(
    payload: FrozenRegistrationInvitationDelivery,
    *,
    access_key_id: str,
    access_key_secret: str,
    sign_name: str,
    template_code: str,
    nonce: str,
    timestamp: str,
) -> dict[str, str]:
    params = {
        "AccessKeyId": access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        # Destination is transport metadata, not a template variable.
        "PhoneNumbers": phone_auth._aliyun_sms_phone_number(payload.phone),
        "RegionId": settings.aliyun_sms_region_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": nonce,
        "SignatureVersion": "1.0",
        "SignName": sign_name,
        "TemplateCode": template_code,
        "TemplateParam": json.dumps(
            _template_params(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "Timestamp": timestamp,
        "Version": "2017-05-25",
    }
    params["Signature"] = phone_auth._aliyun_signature(
        params,
        access_key_secret,
        http_method="POST",
    )
    return params


def _reasonable_ack_id(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value.strip()) <= 256


def _send_once(payload: FrozenRegistrationInvitationDelivery) -> None:
    access_key_id, access_key_secret, sign_name, template_code = _delivery_config()
    params = build_aliyun_invitation_sms_params(
        payload,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        sign_name=sign_name,
        template_code=template_code,
        nonce=uuid.uuid4().hex,
        timestamp=phone_auth._now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    with httpx.Client(timeout=8.0) as client:
        response = client.post("https://dysmsapi.aliyuncs.com/", data=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or payload.get("Code") != "OK":
        raise _InviteSmsProviderRejected("provider did not acknowledge invitation SMS")
    if not _reasonable_ack_id(payload.get("RequestId")) or not _reasonable_ack_id(
        payload.get("BizId")
    ):
        raise _InviteSmsInvalidAck("provider acknowledgement is incomplete")


def _terminal_audit(
    invitation: RegistrationInvitation,
    *,
    actor_id: int,
    error_code: str | None,
) -> AgentAuditLog:
    return AgentAuditLog(
        user_id=actor_id,
        agent_type="registration_access_control",
        action="registration_invitation_send_terminal",
        result_summary="注册邀请短信投递已结束",
        result_detail={
            "invitation_id": invitation.id,
            "status": invitation.status,
            "error_code": error_code,
            "attempt": invitation.send_attempt_count,
            "actor_id": actor_id,
        },
    )


def deliver_registration_invitation_sms(
    db: Session,
    invitation: RegistrationInvitation,
    *,
    manual_code: str,
    link_token: str,
    actor_id: int,
) -> RegistrationInvitationDeliveryResult:
    """Attempt delivery once and stage its terminal state in ``db``.

    The caller owns commit/rollback.  In particular, it must not retry after a
    commit failure because the provider may already have acknowledged delivery.
    """

    payload = freeze_registration_invitation_delivery(
        invitation,
        manual_code=manual_code,
        link_token=link_token,
    )
    outcome = send_frozen_registration_invitation_sms(payload)
    return apply_registration_invitation_delivery_outcome(
        db,
        invitation,
        outcome=outcome,
        actor_id=actor_id,
    )


def send_frozen_registration_invitation_sms(
    payload: FrozenRegistrationInvitationDelivery,
) -> RegistrationInvitationDeliveryResult:
    """Perform exactly one provider attempt without touching database state."""

    error_code: str | None = None
    try:
        _send_once(payload)
    except _InviteSmsNotConfigured:
        error_code = _ERROR_NOT_CONFIGURED
    except _InviteSmsProviderRejected:
        error_code = _ERROR_PROVIDER_REJECTED
    except _InviteSmsInvalidAck:
        error_code = _ERROR_PROVIDER_INVALID_ACK
    except TimeoutException:
        error_code = _ERROR_PROVIDER_TIMEOUT
    except Exception:
        # Provider/network exception text is intentionally not logged: it can
        # contain a full request URL or response body with credentials.
        error_code = _ERROR_TRANSPORT_FAILED

    return RegistrationInvitationDeliveryResult(
        delivery_status="sent" if error_code is None else "send_failed",
        error_code=error_code,
    )


def apply_registration_invitation_delivery_outcome(
    db: Session,
    invitation: RegistrationInvitation,
    *,
    outcome: RegistrationInvitationDeliveryResult,
    actor_id: int,
) -> RegistrationInvitationDeliveryResult:
    """Stage a provider outcome in the caller's independent phase-two transaction."""

    invitation.send_attempt_count = int(invitation.send_attempt_count or 0) + 1
    invitation.status = outcome.delivery_status
    invitation.last_send_error_code = outcome.error_code
    db.add(
        _terminal_audit(
            invitation,
            actor_id=actor_id,
            error_code=outcome.error_code,
        )
    )
    # Do not flush here. The caller first snapshots the provider acknowledgement
    # and then flushes all invitation/audit mutations together. If that flush
    # fails, it can distinguish "provider ack, persistence unknown" and avoid a
    # dangerous automatic resend.
    logger.info(
        "registration invitation SMS terminal invitation_id=%s status=%s error_code=%s attempt=%s",
        invitation.id,
        invitation.status,
        outcome.error_code,
        invitation.send_attempt_count,
    )
    return outcome
