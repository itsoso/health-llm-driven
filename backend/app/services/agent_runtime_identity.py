"""Keyed, content-free identities for the Agent Runtime ledger."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from app.config import settings


_ROOT_CONTEXT = b"reva-agent-runtime-identity-root-v1"


class MissingExternalMessageIdentity(RuntimeError):
    """The provider did not supply a stable delivery identifier."""


def runtime_hmac_digest(purpose: str, *parts: Any) -> str:
    """Return a domain-separated HMAC without persisting source values."""
    normalized_purpose = str(purpose or "").strip()
    if not normalized_purpose:
        raise ValueError("runtime_identity_purpose_required")
    master = str(getattr(settings, "secret_key", "") or "").encode("utf-8")
    if len(master) < 32:
        raise RuntimeError("agent_runtime_identity_key_unavailable")
    root_key = hmac.new(master, _ROOT_CONTEXT, hashlib.sha256).digest()
    purpose_key = hmac.new(
        root_key,
        normalized_purpose.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    payload = json.dumps(
        list(parts),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hmac.new(purpose_key, payload, hashlib.sha256).hexdigest()


def external_client_turn_id(
    prefix: str,
    *,
    channel: str,
    user_id: int | str,
    conversation_id: int | str,
    message_id: int | str | None,
) -> str:
    """Build an opaque external delivery identity bound to its full context."""
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        raise MissingExternalMessageIdentity(
            f"missing_external_message_identity:{str(channel or '').strip().lower()}"
        )
    digest = runtime_hmac_digest(
        "external-client-turn-v1",
        str(channel or "").strip().lower(),
        str(user_id),
        str(conversation_id),
        normalized_message_id,
    )
    return f"{prefix}-{digest[:48]}"
