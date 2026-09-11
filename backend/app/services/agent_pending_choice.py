"""Resolve short numbered replies against an owned, recent clarification.

Numbers can select only closed read-query templates. Mutating or confirmation
options return to their existing confirmation workflow, never to a reconstructed
write command. This module does not call tools, save records or commit sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Literal
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.agent_conversation import AgentConversation, AgentMessage


SCHEMA_VERSION = "agent-pending-choice.v1"
MAX_TTL_SECONDS = 600
_READ_LABELS = {
    "查看昨晚睡眠": "last_night_sleep",
    "分析昨晚睡眠": "last_night_sleep",
    "查看昨天饮食": "yesterday_diet",
    "查看今天饮食": "today_diet",
}
_ORIGINAL_FLOW = re.compile(r"确认|记录|保存|删除|修改|更改|加量|减量|停药|服药|用药|吃药|提醒|取消")
_NUMBERED_LINE = re.compile(r"^\s*([1-5])[.、)]\s*(.+?)\s*$")
_SELECTION_HEADER = re.compile(
    r"(?:(?:请)?(?:选择|选)(?:一项|一个)?"
    r"(?:[,，]\s*(?:请)?回复(?:选项)?编号)?"
    r"|(?:请)?回复(?:一个)?(?:选项)?编号)[：:。.!?？]?"
)


@dataclass(frozen=True)
class PendingChoiceResolution:
    status: Literal["resolved", "requires_original_confirmation"]
    source_message_id: int
    query: str | None = None


def _aware(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _require_aware(now: datetime) -> None:
    if not _aware(now):
        raise ValueError("pending choice requires an explicit timezone-aware server clock")


def _number(reply: Any) -> int | None:
    if not isinstance(reply, str):
        return None
    text = unicodedata.normalize("NFKC", reply).strip()
    return int(text) if re.fullmatch(r"[1-5]", text) else None


def _final_assistant(message: Any) -> bool:
    if message.role != "assistant":
        return False
    meta = message.meta if isinstance(message.meta, dict) else {}
    completion = meta.get("completion_status")
    return (
        meta.get("client_turn_finalized") is not False
        and completion in (None, "complete")
    )


def _options(content: str) -> list[dict[str, Any]] | None:
    if not isinstance(content, str) or len(content) > 4000 or "```" in content:
        return None
    text = unicodedata.normalize("NFKC", content)
    lines = text.splitlines()
    # The existing medical boundary adds a fixed provenance label. It is not
    # an instruction or authority source; only the closed read options below
    # can authorize a continuation. The hash still binds the entire body.
    if lines and lines[0] in {
        unicodedata.normalize("NFKC", label) for label in (
            "信息来源：用户陈述、模型推断。",
            "信息来源：用户陈述、已检索证据（未逐句核验）、模型推断。",
        )
    }:
        lines = lines[1:]
    options = []
    headers = []
    for line in lines:
        match = _NUMBERED_LINE.fullmatch(line)
        if match is None:
            if re.match(r"\s*\d+[.、)]", line):
                return None
            if line.strip():
                headers.append(line.strip())
            continue
        number, label = int(match.group(1)), match.group(2).strip()
        if len(label) > 80:
            return None
        if label in _READ_LABELS:
            kind, key = "read_query", _READ_LABELS[label]
        elif _ORIGINAL_FLOW.search(label):
            kind, key = "original_confirmation", None
        else:
            return None
        options.append({"number": number, "label": label, "kind": kind, "query_key": key})
    if not 2 <= len(options) <= 5:
        return None
    if [item["number"] for item in options] != list(range(1, len(options) + 1)):
        return None
    header = "\n".join(headers)
    if not _SELECTION_HEADER.fullmatch(header):
        return None
    return options


def _fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_pending_choice(
    message: AgentMessage,
    *,
    now: datetime,
    timezone_name: str = "Asia/Shanghai",
    ttl_seconds: int = MAX_TTL_SECONDS,
) -> dict[str, Any] | None:
    """Build server metadata after an assistant row has a persistent ID.

    The caller must use the authenticated conversation's row and persist the
    returned metadata with the final message. No naive database timestamp is
    interpreted as UTC or local time.
    """
    _require_aware(now)
    ZoneInfo(timezone_name)
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError("pending choice TTL must be between 1 and 600 seconds")
    if type(message.id) is not int or message.id <= 0 or not _final_assistant(message):
        return None
    options = _options(message.content)
    if options is None:
        return None
    issued = now.astimezone(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_message_id": message.id,
        "conversation_id": message.conversation_id,
        "body_sha256": _fingerprint(message.content),
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "timezone": timezone_name,
        "options": options,
    }


def attach_pending_choice(message: AgentMessage, *, now: datetime,
                          timezone_name: str = "Asia/Shanghai") -> bool:
    """Attach eligible server-owned metadata; leave commit to the caller."""
    pending = build_pending_choice(message, now=now, timezone_name=timezone_name)
    if pending is None:
        return False
    message.meta = {**(message.meta if isinstance(message.meta, dict) else {}),
                    "pending_choice": pending}
    return True


def _bound_query(key: str, issued: datetime, timezone_name: str) -> str:
    day = issued.astimezone(ZoneInfo(timezone_name)).date()
    if key == "last_night_sleep":
        dimension = "睡眠"
    elif key == "yesterday_diet":
        day -= timedelta(days=1)
        dimension = "饮食"
    elif key == "today_diet":
        dimension = "饮食"
    else:
        raise ValueError("unsupported read choice")
    return f"查询{day.isoformat()}的{dimension}"


def resolve_message_choice(message: AgentMessage, reply: str, *, now: datetime,
                           timezone_name: str = "Asia/Shanghai") -> PendingChoiceResolution | None:
    """Resolve one already-scoped message; use resolve_pending_choice for DB reads."""
    _require_aware(now)
    number = _number(reply)
    if number is None or not _final_assistant(message):
        return None
    options = _options(message.content)
    if options is None:
        return None
    meta = message.meta if isinstance(message.meta, dict) else {}
    if "pending_choice" in meta:
        pending = meta["pending_choice"]
    else:
        # Legacy timestamps have historically mixed UTC and Beijing wall time.
        # Missing timezone means unknown age and must never reactivate a choice.
        if not _aware(message.created_at):
            return None
        pending = build_pending_choice(message, now=message.created_at,
                                       timezone_name=timezone_name)
    if not isinstance(pending, dict) or pending.get("schema_version") != SCHEMA_VERSION:
        return None
    if (
        type(pending.get("source_message_id")) is not int
        or pending["source_message_id"] != message.id
        or pending.get("conversation_id") != message.conversation_id
        or pending.get("body_sha256") != _fingerprint(message.content)
        or pending.get("options") != options
    ):
        return None
    try:
        issued = datetime.fromisoformat(pending["issued_at"])
        expires = datetime.fromisoformat(pending["expires_at"])
        if not _aware(issued) or not _aware(expires):
            return None
        if not timedelta(0) < expires - issued <= timedelta(seconds=MAX_TTL_SECONDS):
            return None
        if not issued <= now < expires:
            return None
        timezone_name = pending["timezone"]
        ZoneInfo(timezone_name)
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        return None
    selected = next((item for item in pending["options"] if item["number"] == number), None)
    if selected is None:
        return None
    if selected["kind"] == "original_confirmation":
        return PendingChoiceResolution("requires_original_confirmation", message.id)
    return PendingChoiceResolution("resolved", message.id,
                                   _bound_query(selected["query_key"], issued, timezone_name))


def resolve_pending_choice(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    reply: str,
    now: datetime,
    current_user_message_id: int | None = None,
    timezone_name: str = "Asia/Shanghai",
) -> PendingChoiceResolution | None:
    """Use only the latest message of an authenticated user's conversation.

    If the caller already persisted this numeric reply, it must supply its exact
    ID. Only that newest row with identical numeric content can be skipped.
    A newer topic or assistant response invalidates all older pending choices.
    """
    _require_aware(now)
    if _number(reply) is None or type(user_id) is not int or type(conversation_id) is not int:
        return None
    messages = (
        db.query(AgentMessage)
        .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
        .filter(AgentConversation.user_id == user_id,
                AgentConversation.id == conversation_id,
                AgentMessage.conversation_id == conversation_id)
        .order_by(AgentMessage.id.desc())
        .limit(2)
        .all()
    )
    if not messages:
        return None
    latest = messages[0]
    if current_user_message_id is not None:
        if (
            latest.id != current_user_message_id or latest.role != "user"
            or _number(latest.content) != _number(reply) or len(messages) < 2
        ):
            return None
        latest = messages[1]
    return resolve_message_choice(latest, reply, now=now, timezone_name=timezone_name)
