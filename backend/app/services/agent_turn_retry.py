"""Durable, content-minimal recovery binding for failed Agent write turns.

The Runtime control plane intentionally does not persist health arguments.
This module stores only a source message id on the failed assistant response,
then rehydrates the owner-scoped source message for an immediate explicit
retry.  Any ambiguous write checkpoint remains fail-closed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_conversation import AgentConversation, AgentMessage


RETRY_SOURCE_ACTION_TYPE = "retry_source_turn"
RETRY_SOURCE_ACTION_VERSION = 1

_RETRY_CONFIRMATIONS = frozenset(
    {
        "重试",
        "再试",
        "再试一次",
        "重新试",
        "重新试一次",
        "需要",
        "好",
        "好的",
        "可以",
        "确认重试",
        "现在重试",
        "帮我重试",
        "继续重试",
    }
)
_SAFE_PRE_DISPATCH_WRITE_STATUSES = frozenset({"planned", "rejected", "failed"})
_UNSAFE_WRITE_STATUSES = frozenset({"in_flight", "uncertain", "verified"})
_ATTACHMENT_MARKER_RE = re.compile(
    r"(?:\n|^)\[(?:附图:\s*\d+张|附件:\s*[^\]\n]+)\]\s*$"
)


@dataclass(frozen=True)
class RetryableTurnRecovery:
    source_message_id: int
    root_source_message_id: int
    action_source_message_id: int
    trigger_assistant_message_id: int
    conversation_id: int
    message: str
    image_urls: tuple[str, ...]

    def user_message_meta(self) -> dict[str, Any]:
        """Return the content-free binding persisted on the retry user turn."""
        return {
            "version": RETRY_SOURCE_ACTION_VERSION,
            "type": RETRY_SOURCE_ACTION_TYPE,
            "source_message_id": self.source_message_id,
            "root_source_message_id": self.root_source_message_id,
            "trigger_assistant_message_id": self.trigger_assistant_message_id,
        }


def is_retry_confirmation(text: Any) -> bool:
    normalized = "".join(str(text or "").strip().split())
    return normalized in _RETRY_CONFIRMATIONS


def build_retry_source_action(
    *,
    source_message_id: int,
    root_source_message_id: int | None = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    source_id = int(source_message_id)
    root_id = int(root_source_message_id or source_id)
    action: dict[str, Any] = {
        "version": RETRY_SOURCE_ACTION_VERSION,
        "type": RETRY_SOURCE_ACTION_TYPE,
        "status": "active",
        "source_message_id": source_id,
        "root_source_message_id": root_id,
    }
    normalized_reason = str(reason_code or "").strip()
    if normalized_reason:
        action["reason_code"] = normalized_reason
    return action


def _write_checkpoint_is_safe_to_retry(meta: Any) -> bool:
    """Return True only when every durable write fact proves no side effect."""
    if meta is None:
        return True
    if not isinstance(meta, dict):
        return False
    if "write_receipts" in meta:
        write_receipts = meta.get("write_receipts")
        if not isinstance(write_receipts, list) or write_receipts:
            return False

    write_state = meta.get("write_state")
    if write_state is not None:
        if not isinstance(write_state, dict):
            return False
        write_status = str(write_state.get("status") or "")
        if (
            write_status in _UNSAFE_WRITE_STATUSES
            or write_status not in _SAFE_PRE_DISPATCH_WRITE_STATUSES
        ):
            return False

    operations = meta.get("write_operations")
    if operations is not None:
        if not isinstance(operations, dict):
            return False
        for operation in operations.values():
            if not isinstance(operation, dict):
                return False
            status = str(operation.get("status") or "")
            if status not in _SAFE_PRE_DISPATCH_WRITE_STATUSES:
                return False

    write_plan = meta.get("write_plan")
    if write_plan is not None:
        if not isinstance(write_plan, dict):
            return False
        fingerprints = write_plan.get("fingerprints") or []
        if not isinstance(fingerprints, list):
            return False
        if write_plan.get("sealed") is True:
            if not fingerprints or not isinstance(operations, dict):
                return False
            if any(
                str(fingerprint) not in operations
                for fingerprint in fingerprints
            ):
                return False
    return True


def build_retry_source_action_if_safe(
    *,
    source_message: Any,
    turn_outcome: Any,
    write_receipts: Any,
    health_write_requested: bool,
    root_source_message_id: int | None = None,
) -> dict[str, Any] | None:
    """Create an explicit retry action only for a proven no-write failure."""
    if not health_write_requested:
        return None
    if write_receipts:
        return None
    if not isinstance(turn_outcome, dict) or turn_outcome.get("retryable") is not True:
        return None
    if turn_outcome.get("category") not in {
        "tool_failed",
        "execution_error",
        "no_answer",
        "action_not_executed",
    }:
        return None
    source_id = getattr(source_message, "id", None)
    if source_id is None or not _write_checkpoint_is_safe_to_retry(
        getattr(source_message, "meta", None)
    ):
        return None
    return build_retry_source_action(
        source_message_id=int(source_id),
        root_source_message_id=root_source_message_id,
        reason_code=turn_outcome.get("reason_code"),
    )


def _parse_image_urls(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed = raw
    values = parsed if isinstance(parsed, list) else [parsed]
    return tuple(
        str(value)
        for value in values
        if isinstance(value, str) and value.strip()
    )


def materialize_retryable_turn_images(
    recovery: RetryableTurnRecovery,
    *,
    user_id: int,
) -> list[dict[str, str]]:
    """Load persisted owner-scoped images for a retry without re-uploading."""
    from app.services.chat_utils import read_owned_chat_image_data_uri

    images: list[dict[str, str]] = []
    for image_url in recovery.image_urls:
        data_uri = read_owned_chat_image_data_uri(image_url, int(user_id))
        match = re.match(r"^data:image/([a-zA-Z0-9.+-]+);base64,", data_uri)
        if match is None:
            raise ValueError("retry_source_image_invalid")
        image_type = match.group(1).lower()
        if image_type == "jpg":
            image_type = "jpeg"
        images.append({"base64": data_uri, "type": image_type})
    return images


def _owned_user_message(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    message_id: int,
) -> AgentMessage | None:
    return (
        db.query(AgentMessage)
        .join(
            AgentConversation,
            AgentConversation.id == AgentMessage.conversation_id,
        )
        .filter(
            AgentMessage.id == int(message_id),
            AgentMessage.conversation_id == int(conversation_id),
            AgentMessage.role == "user",
            AgentConversation.user_id == int(user_id),
        )
        .one_or_none()
    )


def _source_message_from_binding(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    binding: Any,
    trigger_assistant_message_id: int,
) -> RetryableTurnRecovery | None:
    if not isinstance(binding, dict):
        return None
    if (
        binding.get("version") != RETRY_SOURCE_ACTION_VERSION
        or binding.get("type") != RETRY_SOURCE_ACTION_TYPE
    ):
        return None
    try:
        source_message_id = int(binding["source_message_id"])
        root_source_message_id = int(
            binding.get("root_source_message_id") or source_message_id
        )
    except (KeyError, TypeError, ValueError):
        return None

    action_source = _owned_user_message(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=source_message_id,
    )
    if action_source is None or not _write_checkpoint_is_safe_to_retry(
        action_source.meta
    ):
        return None
    if action_source.id >= int(trigger_assistant_message_id):
        return None

    source = action_source
    retry_binding = (
        action_source.meta.get("retry_source")
        if isinstance(action_source.meta, dict)
        else None
    )
    if retry_binding is not None:
        if (
            not isinstance(retry_binding, dict)
            or retry_binding.get("version") != RETRY_SOURCE_ACTION_VERSION
            or retry_binding.get("type") != RETRY_SOURCE_ACTION_TYPE
        ):
            return None
        try:
            replay_source_id = int(retry_binding["source_message_id"])
            retry_root_id = int(
                retry_binding.get("root_source_message_id") or replay_source_id
            )
        except (KeyError, TypeError, ValueError):
            return None
        if retry_root_id != root_source_message_id:
            return None
        source = _owned_user_message(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=replay_source_id,
        )
        if (
            source is None
            or source.id >= action_source.id
            or not _write_checkpoint_is_safe_to_retry(source.meta)
        ):
            return None

    message = _ATTACHMENT_MARKER_RE.sub("", str(source.content or "")).strip()
    if not message:
        return None
    return RetryableTurnRecovery(
        source_message_id=int(source.id),
        root_source_message_id=root_source_message_id,
        action_source_message_id=int(action_source.id),
        trigger_assistant_message_id=int(trigger_assistant_message_id),
        conversation_id=int(conversation_id),
        message=message,
        image_urls=_parse_image_urls(source.image_url),
    )


def resolve_retryable_turn_recovery(
    db: Session,
    *,
    user_id: int,
    conversation_id: int | None,
    confirmation_text: Any,
) -> RetryableTurnRecovery | None:
    """Resolve only an immediately preceding active recovery action."""
    if conversation_id is None or not is_retry_confirmation(confirmation_text):
        return None
    latest = (
        db.query(AgentMessage)
        .join(
            AgentConversation,
            AgentConversation.id == AgentMessage.conversation_id,
        )
        .filter(
            AgentMessage.conversation_id == int(conversation_id),
            AgentConversation.user_id == int(user_id),
        )
        .order_by(AgentMessage.id.desc())
        .first()
    )
    if (
        latest is None
        or latest.role != "assistant"
        or not isinstance(latest.meta, dict)
        or latest.meta.get("client_turn_finalized") is not True
    ):
        return None
    action = latest.meta.get("recovery_action")
    if not isinstance(action, dict) or action.get("status") != "active":
        return None
    recovery = _source_message_from_binding(
        db,
        user_id=user_id,
        conversation_id=int(conversation_id),
        binding=action,
        trigger_assistant_message_id=int(latest.id),
    )
    if recovery is None:
        return None
    intervening = (
        db.query(AgentMessage.id)
        .filter(
            AgentMessage.conversation_id == int(conversation_id),
            AgentMessage.id > recovery.action_source_message_id,
            AgentMessage.id < latest.id,
        )
        .first()
    )
    return None if intervening is not None else recovery


def restore_retryable_turn_recovery(
    db: Session,
    *,
    user_id: int,
    user_message: Any,
) -> RetryableTurnRecovery | None:
    """Restore a binding already persisted on an idempotent retry user turn."""
    if (
        user_message is None
        or getattr(user_message, "role", None) != "user"
        or not is_retry_confirmation(getattr(user_message, "content", None))
    ):
        return None
    meta = getattr(user_message, "meta", None)
    if not isinstance(meta, dict):
        return None
    binding = meta.get("retry_source")
    if not isinstance(binding, dict):
        return None
    try:
        trigger_id = int(binding["trigger_assistant_message_id"])
        conversation_id = int(user_message.conversation_id)
    except (KeyError, TypeError, ValueError):
        return None
    trigger = (
        db.query(AgentMessage)
        .join(
            AgentConversation,
            AgentConversation.id == AgentMessage.conversation_id,
        )
        .filter(
            AgentMessage.id == trigger_id,
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.role == "assistant",
            AgentConversation.user_id == int(user_id),
        )
        .one_or_none()
    )
    if trigger is None or int(trigger.id) >= int(user_message.id):
        return None
    trigger_meta = trigger.meta if isinstance(trigger.meta, dict) else {}
    trigger_action = trigger_meta.get("recovery_action")
    if (
        trigger_meta.get("client_turn_finalized") is not True
        or not isinstance(trigger_action, dict)
        or trigger_action.get("status") != "active"
        or trigger_action.get("version") != RETRY_SOURCE_ACTION_VERSION
        or trigger_action.get("type") != RETRY_SOURCE_ACTION_TYPE
    ):
        return None
    try:
        binding_source_id = int(binding["source_message_id"])
        binding_root_id = int(
            binding.get("root_source_message_id") or binding_source_id
        )
        trigger_source_id = int(trigger_action["source_message_id"])
        trigger_root_id = int(
            trigger_action.get("root_source_message_id") or trigger_source_id
        )
    except (KeyError, TypeError, ValueError):
        return None
    if (
        trigger_source_id != binding_source_id
        or trigger_root_id != binding_root_id
    ):
        return None
    latest_message_id = (
        db.query(AgentMessage.id)
        .filter(AgentMessage.conversation_id == conversation_id)
        .order_by(AgentMessage.id.desc())
        .limit(1)
        .scalar()
    )
    if latest_message_id != int(user_message.id):
        return None
    intervening = (
        db.query(AgentMessage.id)
        .filter(
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.id > int(trigger.id),
            AgentMessage.id < int(user_message.id),
        )
        .first()
    )
    if intervening is not None:
        return None
    if not _write_checkpoint_is_safe_to_retry(getattr(user_message, "meta", None)):
        return None
    recovery = _source_message_from_binding(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        binding=binding,
        trigger_assistant_message_id=trigger_id,
    )
    if recovery is None:
        return None
    return replace(
        recovery,
        action_source_message_id=int(user_message.id),
    )
