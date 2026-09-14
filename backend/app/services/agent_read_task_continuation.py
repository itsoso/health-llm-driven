"""Carry a server-bound read task across a short follow-up, without write authority."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

from app.services.agent_kernel.types import ActionableReference
from app.services.agent_query_window import parse_query_window

_VERSION = "owned-read-task.v2"
_DIMENSIONS = frozenset({"diet", "sleep", "workout", "supplements"})
_LIMITATIONS = frozenset(
    {
        "scope_diet_sleep_only",
        "default_recent_7_days",
        "mood_not_queried",
        "work_not_queried",
    }
)
_FOLLOWUP = re.compile(
    r"(?:好了吗|好了没|现在好了没|同步好了吗|同步完了吗|再查一下|再看看|继续分析|继续复盘|继续)[？?。!！\s]*"
)


def is_read_task_followup(text: str) -> bool:
    # Quoted/conditional/cancelled/compound input must never inherit authority.
    return bool(_FOLLOWUP.fullmatch(text.strip()))


def _validated_task(raw, now: datetime) -> dict | None:
    if not isinstance(raw, dict) or raw.get("version") not in (
        _VERSION,
        "owned-read-task.v1",
    ):
        return None
    if set(raw) - {
        "version",
        "created_at",
        "queries",
        "sync_status",
        "limitations",
        "sync_window",
    }:
        return None
    try:
        created_at = datetime.fromisoformat(raw["created_at"])
        if created_at.utcoffset() is None or not timedelta(
            0
        ) <= now - created_at <= timedelta(hours=24):
            return None
        if not isinstance(raw.get("sync_status"), bool):
            return None
        queries = raw.get("queries")
        max_queries = 4 if raw["version"] == _VERSION else 2
        if not isinstance(queries, list) or not 0 <= len(queries) <= max_queries:
            return None
        sync_window = raw.get("sync_window")
        if sync_window is not None:
            if (
                raw["sync_status"] is not True
                or not isinstance(sync_window, dict)
                or set(sync_window) != {"start_date", "end_date", "timezone"}
            ):
                return None
            window = parse_query_window(sync_window)
            if (
                window.start_date != window.end_date
                or window.end_date > now.astimezone(ZoneInfo(window.timezone)).date()
                or sync_window != window.as_dict()
            ):
                return None
            sync_window = window.as_dict()
        if not queries and (raw.get("version") != _VERSION or sync_window is None):
            return None
        canonical = []
        for query in queries:
            if not isinstance(query, dict):
                return None
            keys = {"dimension", "start_date", "end_date", "timezone"}
            if "days" in query and raw["version"] == _VERSION:
                keys.add("days")
            if set(query) != keys:
                return None
            dimension = query["dimension"]
            if not isinstance(dimension, str) or dimension not in _DIMENSIONS:
                return None
            window = parse_query_window(query)
            span = (window.end_date - window.start_date).days + 1
            if window.end_date > now.astimezone(ZoneInfo(window.timezone)).date():
                return None
            canonical_query = {"dimension": dimension, **window.as_dict()}
            if "days" in query:
                if type(query["days"]) is not int or query["days"] != span:
                    return None
                canonical_query["days"] = query["days"]
            elif span != 1 or (raw["version"] != _VERSION and dimension not in {"diet", "sleep"}):
                return None
            if query != canonical_query:
                return None
            canonical.append(canonical_query)
        if len({q["dimension"] for q in canonical}) != len(canonical):
            return None
        limitations = raw.get("limitations", [])
        if not isinstance(limitations, list) or any(
            not isinstance(item, str) or item not in _LIMITATIONS
            for item in limitations
        ):
            return None
        if not queries and limitations:
            return None
        return {
            "version": _VERSION,
            "created_at": created_at.isoformat(),
            "queries": canonical,
            "sync_status": raw["sync_status"],
            "limitations": limitations,
            **({"sync_window": sync_window} if sync_window is not None else {}),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _has_owned_identity(snapshot) -> bool:
    owner = snapshot.context.user_id
    return (
        type(owner) is int
        and owner > 0
        and type(snapshot.envelope.user_id) is int
        and snapshot.envelope.user_id == owner
    )


def resolve_read_task_continuation(snapshot) -> dict | None:
    if not _has_owned_identity(snapshot):
        return None
    if not is_read_task_followup(snapshot.envelope.text):
        return None
    refs = [
        ref for ref in snapshot.actionable_references if ref.kind == "owned_read_task"
    ]
    if len(refs) != 1 or not str(refs[0].source_message_id or "").isdigit():
        return None
    return _validated_task(refs[0].data, snapshot.context.current_time)


def load_read_task_reference(
    db, user_id: int, conversation_id: int, snapshot
) -> ActionableReference | None:
    """Only the latest owned assistant message can continue a task.

    Public message endpoints cannot write assistant metadata. User messages,
    client capabilities and model output are never sources for this reference.
    """
    if not is_read_task_followup(snapshot.envelope.text):
        return None
    if (
        not _has_owned_identity(snapshot)
        or type(user_id) is not int
        or user_id != snapshot.context.user_id
    ):
        return None
    from app.models.agent_conversation import AgentConversation, AgentMessage

    with db.no_autoflush:
        previous = (
            db.query(AgentMessage)
            .join(
                AgentConversation, AgentMessage.conversation_id == AgentConversation.id
            )
            .filter(
                AgentConversation.user_id == user_id,
                AgentConversation.id == conversation_id,
                AgentMessage.role == "assistant",
            )
            .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
            .first()
        )
    if previous is None or not isinstance(previous.meta, dict):
        return None
    task = _validated_task(
        previous.meta.get("read_task"), snapshot.context.current_time
    )
    if task is None:
        return None
    return ActionableReference(
        kind="owned_read_task", source_message_id=str(previous.id), data=task
    )


def read_task_metadata(
    snapshot, scope, *, sync_status: bool, sync_window: dict | None = None
) -> dict | None:
    """Persist only server-bound scope/window, never model arguments or job IDs.

    A sync-only window permits observation of the owned job receipt; it does
    not authorize reading the day's sleep records or resubmitting the job.
    """
    if not _has_owned_identity(snapshot) or (scope is None and sync_window is None):
        return None
    prior = resolve_read_task_continuation(snapshot)
    raw = {
        "version": _VERSION,
        "created_at": prior["created_at"]
        if prior
        else snapshot.context.current_time.isoformat(),
        "queries": [dict(query) for query in scope.queries]
        if scope is not None
        else [],
        "sync_status": sync_status,
        "limitations": list(scope.limitations) if scope is not None else [],
        **({"sync_window": dict(sync_window)} if sync_window is not None else {}),
    }
    return _validated_task(raw, snapshot.context.current_time)


def read_task_continuation_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest,
        authorization_grammar_digest,
        authorization_module_behavior_names,
    )

    return {
        "version": _VERSION,
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)
        ),
    }
