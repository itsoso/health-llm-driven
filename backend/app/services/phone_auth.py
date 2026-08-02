"""Phone-first auth helpers.

The first production slice uses one-time phone codes as the primary mobile
login/register path. Real SMS delivery is intentionally behind a provider seam:
without a configured provider, production fails loud instead of pretending a
message was sent.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import logging
import re
import secrets
from typing import Optional
import urllib.parse
import uuid

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.phone_auth import PhoneAuthCode

logger = logging.getLogger(__name__)

_PHONE_DIGITS_RE = re.compile(r"\D+")


class InvalidPhoneNumber(ValueError):
    """Phone number cannot be normalized."""


class PhoneCodeCooldown(ValueError):
    """A code was requested too recently."""


class PhoneCodeDeliveryNotConfigured(RuntimeError):
    """No production-capable SMS provider is configured."""


class PhoneCodeDeliveryFailed(RuntimeError):
    """SMS provider rejected or failed the delivery request."""


@dataclass(frozen=True)
class IssuedPhoneCode:
    phone: str
    expires_at: datetime
    expires_in_seconds: int
    dev_code: Optional[str] = None


def normalize_phone(raw_phone: str) -> str:
    """Normalize a user-entered phone number into E.164.

    This first product wedge defaults 11-digit mainland China mobile numbers to
    +86 while still accepting already-normalized +<country><number> input.
    """

    value = (raw_phone or "").strip()
    if not value:
        raise InvalidPhoneNumber("请输入手机号")

    if value.startswith("+"):
        digits = _PHONE_DIGITS_RE.sub("", value)
        if 8 <= len(digits) <= 15:
            return f"+{digits}"
        raise InvalidPhoneNumber("手机号格式不正确")

    digits = _PHONE_DIGITS_RE.sub("", value)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+86{digits}"
    if len(digits) == 13 and digits.startswith("86"):
        return f"+{digits}"
    if 8 <= len(digits) <= 15 and not digits.startswith("0"):
        return f"+{digits}"
    raise InvalidPhoneNumber("手机号格式不正确")


def mask_phone(phone: str) -> str:
    digits = _PHONE_DIGITS_RE.sub("", phone)
    if len(digits) <= 6:
        return "***"
    return f"+{digits[:2]} {digits[2:5]}****{digits[-4:]}"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _hash(value: str) -> str:
    key = (settings.secret_key or "phone-auth-dev-secret").encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _hash_code(phone: str, code: str, purpose: str) -> str:
    return _hash(f"{purpose}:{phone}:{code}")


def _hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    return _hash(ip)


def _can_dev_echo() -> bool:
    return bool(
        settings.auth_phone_code_dev_echo
        or (settings.debug and settings.app_env.lower() != "production")
    )


def _aliyun_sms_access_key_id() -> Optional[str]:
    return settings.aliyun_sms_access_key_id or settings.aliyun_access_key_id


def _aliyun_sms_access_key_secret() -> Optional[str]:
    return settings.aliyun_sms_access_key_secret or settings.aliyun_access_key_secret


def _aliyun_sms_configured() -> bool:
    return bool(
        _aliyun_sms_access_key_id()
        and _aliyun_sms_access_key_secret()
        and settings.aliyun_sms_sign_name
        and settings.aliyun_sms_template_code
    )


def _aliyun_sms_phone_number(phone: str) -> str:
    digits = _PHONE_DIGITS_RE.sub("", phone)
    if phone.startswith("+86") and len(digits) == 13:
        return digits[2:]
    return digits


def _aliyun_percent_encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="-_.~")


def _aliyun_signature(params: dict[str, str], access_key_secret: str, http_method: str = "GET") -> str:
    canonical_query = "&".join(
        f"{_aliyun_percent_encode(key)}={_aliyun_percent_encode(params[key])}"
        for key in sorted(params)
    )
    string_to_sign = f"{http_method}&%2F&{_aliyun_percent_encode(canonical_query)}"
    digest = hmac.new(
        f"{access_key_secret}&".encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _send_aliyun_sms(phone: str, code: str) -> None:
    access_key_id = _aliyun_sms_access_key_id()
    access_key_secret = _aliyun_sms_access_key_secret()
    if not access_key_id or not access_key_secret:
        raise PhoneCodeDeliveryNotConfigured("短信通道未配置，请稍后再试")

    params = {
        "AccessKeyId": access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": _aliyun_sms_phone_number(phone),
        "RegionId": settings.aliyun_sms_region_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "SignName": settings.aliyun_sms_sign_name or "",
        "TemplateCode": settings.aliyun_sms_template_code or "",
        "TemplateParam": json.dumps({"code": code}, ensure_ascii=False, separators=(",", ":")),
        "Timestamp": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }
    params["Signature"] = _aliyun_signature(params, access_key_secret)

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get("https://dysmsapi.aliyuncs.com/", params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.error("[phone-auth] Aliyun SMS request failed for %s: %s", mask_phone(phone), str(exc))
        raise PhoneCodeDeliveryFailed("短信发送失败，请稍后再试") from exc

    if payload.get("Code") != "OK":
        logger.error(
            "[phone-auth] Aliyun SMS rejected for %s: code=%s message=%s",
            mask_phone(phone),
            payload.get("Code"),
            payload.get("Message"),
        )
        raise PhoneCodeDeliveryFailed("短信发送失败，请稍后再试")


def _aliyun_pnvs_configured() -> bool:
    return bool(
        _aliyun_sms_access_key_id()
        and _aliyun_sms_access_key_secret()
        and settings.aliyun_pnvs_sign_name
        and settings.aliyun_pnvs_template_code
    )


def _send_aliyun_pnvs_sms(phone: str, code: str) -> None:
    """号码认证服务「短信认证」免资质通道（dypnsapi SendSmsVerifyCode）。

    验证码仍由本服务生成并本地校验，平台只负责投递（TemplateParam 直传 code），
    赠送签名/模板仅支持中国大陆手机号。
    """

    access_key_id = _aliyun_sms_access_key_id()
    access_key_secret = _aliyun_sms_access_key_secret()
    if not access_key_id or not access_key_secret:
        raise PhoneCodeDeliveryNotConfigured("短信通道未配置，请稍后再试")
    if not phone.startswith("+86"):
        logger.error("[phone-auth] PNVS SMS only supports mainland numbers: %s", mask_phone(phone))
        raise PhoneCodeDeliveryFailed("短信发送失败，请稍后再试")

    params = {
        "AccessKeyId": access_key_id,
        "Action": "SendSmsVerifyCode",
        "Format": "JSON",
        "PhoneNumber": _aliyun_sms_phone_number(phone),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "SignName": settings.aliyun_pnvs_sign_name or "",
        "TemplateCode": settings.aliyun_pnvs_template_code or "",
        "TemplateParam": json.dumps(
            {"code": code, "min": str(max(int(settings.auth_phone_code_ttl_minutes), 1))},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "Timestamp": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }
    params["Signature"] = _aliyun_signature(params, access_key_secret, http_method="POST")

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post("https://dypnsapi.aliyuncs.com/", data=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.error("[phone-auth] Aliyun PNVS SMS request failed for %s: %s", mask_phone(phone), str(exc))
        raise PhoneCodeDeliveryFailed("短信发送失败，请稍后再试") from exc

    if payload.get("Code") != "OK":
        logger.error(
            "[phone-auth] Aliyun PNVS SMS rejected for %s: code=%s message=%s",
            mask_phone(phone),
            payload.get("Code"),
            payload.get("Message"),
        )
        raise PhoneCodeDeliveryFailed("短信发送失败，请稍后再试")


def _deliver_code(phone: str, code: str) -> Optional[str]:
    """Deliver code or return dev echo.

    Production sends through a configured SMS provider; development may echo or
    log codes depending on settings.
    """

    if _can_dev_echo():
        logger.warning("[phone-auth] dev code for %s: %s", mask_phone(phone), code)
        return code

    if _aliyun_sms_configured():
        _send_aliyun_sms(phone, code)
        return None

    if _aliyun_pnvs_configured():
        _send_aliyun_pnvs_sms(phone, code)
        return None

    if settings.auth_phone_code_log_delivery and settings.app_env.lower() != "production":
        logger.warning("[phone-auth] log-only code for %s: %s", mask_phone(phone), code)
        return None

    raise PhoneCodeDeliveryNotConfigured("短信通道未配置，请稍后再试")


def issue_phone_code(
    db: Session,
    raw_phone: str,
    *,
    purpose: str = "login",
    request_ip: Optional[str] = None,
) -> IssuedPhoneCode:
    phone = normalize_phone(raw_phone)
    now = _now()
    resend_seconds = max(int(settings.auth_phone_code_resend_seconds), 0)
    if resend_seconds:
        recent = (
            db.query(PhoneAuthCode)
            .filter(
                PhoneAuthCode.phone == phone,
                PhoneAuthCode.purpose == purpose,
            )
            .order_by(PhoneAuthCode.created_at.desc())
            .first()
        )
        if recent and (now - _aware(recent.created_at)).total_seconds() < resend_seconds:
            raise PhoneCodeCooldown("验证码发送太频繁，请稍后再试")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(minutes=max(int(settings.auth_phone_code_ttl_minutes), 1))
    record = PhoneAuthCode(
        phone=phone,
        purpose=purpose,
        code_hash=_hash_code(phone, code, purpose),
        expires_at=expires_at,
        request_ip_hash=_hash_ip(request_ip),
    )

    try:
        db.add(record)
        db.flush()
        dev_code = _deliver_code(phone, code)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return IssuedPhoneCode(
        phone=phone,
        expires_at=expires_at,
        expires_in_seconds=int((expires_at - now).total_seconds()),
        dev_code=dev_code,
    )


def consume_phone_code(
    db: Session,
    raw_phone: str,
    code: str,
    *,
    purpose: str = "login",
    commit: bool = True,
) -> str:
    phone = normalize_phone(raw_phone)
    clean_code = _PHONE_DIGITS_RE.sub("", code or "")
    if len(clean_code) < 4:
        raise ValueError("验证码无效或已过期")

    record = (
        db.query(PhoneAuthCode)
        .filter(
            PhoneAuthCode.phone == phone,
            PhoneAuthCode.purpose == purpose,
            PhoneAuthCode.consumed_at.is_(None),
        )
        .order_by(PhoneAuthCode.created_at.desc())
        .with_for_update()
        .first()
    )
    if not record:
        raise ValueError("验证码无效或已过期")

    now = _now()
    if _aware(record.expires_at) < now:
        raise ValueError("验证码无效或已过期")

    if record.attempt_count >= max(int(settings.auth_phone_code_max_attempts), 1):
        raise ValueError("验证码无效或已过期")

    expected_hash = _hash_code(phone, clean_code, purpose)
    if not hmac.compare_digest(record.code_hash, expected_hash):
        record.attempt_count += 1
        # Failed attempts remain durable even when the caller defers a
        # successful consume into a larger transaction. Otherwise callers that
        # roll back on this ValueError could bypass the attempt limit.
        db.commit()
        raise ValueError("验证码无效或已过期")

    record.consumed_at = now
    if commit:
        db.commit()
    else:
        db.flush()
    return phone
