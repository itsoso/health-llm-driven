"""Native authentication helpers for ``garminconnect`` 0.3.x.

The database column that stores this value keeps its legacy name for schema
compatibility, but its contents are a versioned Fernet-encrypted native token
store.  Callers must never persist or log the decoded payload.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

from app.services.auth import garmin_credential_service

TOKEN_STORE_VERSION = 2
TOKEN_STORE_FORMAT = "garmin_di_oauth"


class GarminNativeTokenError(ValueError):
    """Stored Garmin native token state is absent, legacy, or invalid."""


class _TokenPayloadFilter(logging.Filter):
    """Remove one decoded token payload from third-party log records."""

    def __init__(self, payload: str) -> None:
        super().__init__()
        self.payload = payload

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        if self.payload in rendered:
            record.msg = rendered.replace(self.payload, "[REDACTED GARMIN TOKEN]")
            record.args = ()
        return True


@contextmanager
def garmin_token_log_redaction(payload: str) -> Iterator[None]:
    """Redact a decoded token while ``garminconnect`` loads or refreshes it."""
    third_party_logger = logging.getLogger("garminconnect")
    payload_filter = _TokenPayloadFilter(payload)
    third_party_logger.addFilter(payload_filter)
    try:
        yield
    finally:
        third_party_logger.removeFilter(payload_filter)


def encode_native_token_store(payload: str) -> str:
    """Encrypt a native ``Client.dumps()`` payload in a versioned envelope."""
    if not isinstance(payload, str) or not payload:
        raise GarminNativeTokenError("Garmin token payload is empty")
    ciphertext = garmin_credential_service.encrypt_secret(payload)
    return json.dumps(
        {
            "version": TOKEN_STORE_VERSION,
            "format": TOKEN_STORE_FORMAT,
            "ciphertext": ciphertext,
        },
        separators=(",", ":"),
    )


def decode_native_token_store(envelope: str) -> str:
    """Validate and decrypt a native token envelope, failing closed."""
    try:
        data = json.loads(envelope)
    except (TypeError, json.JSONDecodeError) as exc:
        raise GarminNativeTokenError("Garmin token envelope is invalid") from exc

    if not isinstance(data, dict):
        raise GarminNativeTokenError("Garmin token envelope must be an object")
    if data.get("version") != TOKEN_STORE_VERSION or data.get("format") != TOKEN_STORE_FORMAT:
        raise GarminNativeTokenError("Garmin token envelope is legacy or unsupported")

    ciphertext = data.get("ciphertext")
    if not isinstance(ciphertext, str) or not ciphertext:
        raise GarminNativeTokenError("Garmin token ciphertext is missing")
    try:
        payload = garmin_credential_service.decrypt_secret(ciphertext)
    except Exception as exc:  # Fernet intentionally exposes no recovery detail.
        raise GarminNativeTokenError("Garmin token ciphertext is invalid") from exc
    if not payload:
        raise GarminNativeTokenError("Garmin token payload is empty")
    return payload


def has_native_token_store(envelope: str | None) -> bool:
    """Return whether a stored value is a valid, decryptable native envelope."""
    if not envelope:
        return False
    try:
        decode_native_token_store(envelope)
    except GarminNativeTokenError:
        return False
    return True


def credential_can_sync(credential: Any) -> bool:
    """Allow a valid native token to override stale legacy status flags."""
    if not credential or not bool(getattr(credential, "sync_enabled", False)):
        return False
    if has_native_token_store(getattr(credential, "garth_session", None)):
        return True
    return bool(getattr(credential, "credentials_valid", False)) and not bool(
        getattr(credential, "requires_mfa", False)
    )


def get_native_client(client: Any) -> Any | None:
    """Return the 0.3.x native client without accepting the removed garth API."""
    return getattr(client, "client", None)


def is_native_client_authenticated(client: Any) -> bool:
    native = get_native_client(client)
    return bool(native is not None and getattr(native, "is_authenticated", False))


def dump_native_token_store(client: Any) -> str:
    """Serialize and encrypt an authenticated native client."""
    native = get_native_client(client)
    if native is None or not getattr(native, "is_authenticated", False):
        raise GarminNativeTokenError("Garmin native client is not authenticated")
    payload = native.dumps()
    return encode_native_token_store(payload)


def safe_garmin_error_message(error: Exception) -> str:
    """Map upstream failures to actionable text without echoing secret detail."""
    error_text = str(error).lower()
    if "mfa" in error_text or "two-factor" in error_text or "verification" in error_text:
        return "Garmin 需要两步验证，请完成验证码确认"
    if "429" in error_text or "too many" in error_text or "rate limit" in error_text:
        return "Garmin 登录尝试过多，请稍后再试"
    if "locked" in error_text or "登录已被暂停" in error_text:
        return "Garmin 登录暂时锁定，请稍后再试"
    if any(
        marker in error_text
        for marker in ("401", "unauthorized", "credential", "password", "authentication")
    ):
        return "Garmin 账号或密码无效，请重新连接"
    return "Garmin 服务暂时不可用，请稍后再试"
