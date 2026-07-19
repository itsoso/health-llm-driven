"""Durable, content-free control plane for cloud Agent execution."""
from __future__ import annotations

import hashlib
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Iterator, Literal, Mapping

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.agent_runtime import AgentRun, AgentRunAttempt, AgentRunEvent


ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})
TERMINAL_RUN_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "reconciliation_required"}
)
COMPLETION_RUN_STATUSES = TERMINAL_RUN_STATUSES | {"waiting_for_user"}

_RUN_TRANSITIONS = {
    "queued": frozenset({"running", "failed", "cancelled"}),
    "running": COMPLETION_RUN_STATUSES,
    "waiting_for_user": frozenset({"succeeded", "failed", "cancelled"}),
    "reconciliation_required": frozenset(),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

_EVENT_NAMES = frozenset(
    {
        "run.created",
        "run.retried",
        "run.started",
        "run.waiting",
        "run.succeeded",
        "run.failed",
        "run.cancelled",
        "run.reconciliation_required",
        "tool.requested",
        "tool.receipt_verified",
    }
)
_EVENT_PAYLOAD_KEYS = frozenset(
    {
        "status",
        "completion_status",
        "error_code",
        "tool_name",
        "effect_class",
        "receipt_verified",
        "replayed",
        "input_seq",
    }
)
_MAX_EVENT_STRING_LENGTH = 128
_SAFE_EVENT_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
_TOKEN_EVENT_KEYS = frozenset(
    {"status", "completion_status", "error_code", "tool_name", "effect_class"}
)
_KNOWN_ERROR_CODES = frozenset(
    {
        "cancelled",
        "completed",
        "completion_error",
        "confirmation_required",
        "empty_final_text",
        "executor_exception",
        "executor_missing_done",
        "model_scope",
        "mutation_without_tool",
        "provider_timeout",
        "request_not_persisted",
        "safety_boundary",
        "shortcut_finalize_failed",
        "unclassified_error",
        "verified_write",
        "write_checkpoint_partially_verified",
        "write_checkpoint_uncertain",
        "write_without_tool",
    }
)
_KNOWN_STATUS_VALUES = frozenset(
    {
        "cancelled",
        "executing",
        "failed",
        "queued",
        "reconciliation_required",
        "requested",
        "running",
        "succeeded",
        "verified",
        "waiting_for_user",
    }
)
_KNOWN_COMPLETION_VALUES = frozenset({"complete", "error", "interrupted"})
_KNOWN_EFFECT_CLASSES = frozenset({"none", "read", "read_only", "write"})
_POSTGRES_ADVISORY_NAMESPACE = 1_724_663_251
_LOCAL_LOCK_GUARD = threading.Lock()
_LOCAL_CONVERSATION_LOCKS: dict[int, threading.Lock] = {}


class AgentRuntimeError(RuntimeError):
    """Base Runtime control-plane error."""


class RunBusyError(AgentRuntimeError):
    def __init__(self, active_run_id: str):
        super().__init__("conversation_has_active_run")
        self.active_run_id = active_run_id


class ConversationAccessError(AgentRuntimeError):
    pass


class InvalidRunTransition(AgentRuntimeError):
    pass


class UnsafeRunEventPayload(AgentRuntimeError):
    pass


class StaleRunAttempt(AgentRuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    attempt_id: str
    user_id: int
    conversation_id: int | None
    client_turn_id: str | None
    input_seq: int | None
    origin: str
    origin_device_id: str | None = None
    local_execution_id: str | None = None
    privacy_mode: str = "cloud"


@dataclass(frozen=True, slots=True)
class RunAdmission:
    context: RunContext
    resumed: bool
    disposition: Literal["execute", "observe", "replay"]

    @property
    def owns_execution(self) -> bool:
        return self.disposition == "execute"


def _now() -> datetime:
    return datetime.now(UTC)


@lru_cache(maxsize=1)
def _known_tool_names() -> frozenset[str]:
    from app.services.tool_schema_registry import get_tool_names

    return frozenset(get_tool_names())


def _known_error_codes() -> frozenset[str]:
    return _KNOWN_ERROR_CODES | _known_tool_names()


def runtime_outcome_from_done(
    done_data: Mapping[str, Any],
) -> tuple[str, str | None, bool]:
    """Map existing content-free Executor facts to one durable Run outcome."""
    if done_data.get("request_persisted") is False:
        return "failed", "request_not_persisted", True

    write_recovery = str(done_data.get("write_recovery") or "").strip()
    if write_recovery in {
        "write_checkpoint_uncertain",
        "write_checkpoint_partially_verified",
    }:
        return "reconciliation_required", write_recovery, False

    turn_outcome = done_data.get("turn_outcome")
    outcome = turn_outcome if isinstance(turn_outcome, dict) else {}
    reason_code = str(outcome.get("reason_code") or "").strip() or None
    if outcome.get("category") == "confirmation_required" or outcome.get(
        "confirmation_required"
    ) is True:
        return "waiting_for_user", reason_code or "confirmation_required", False

    completion_status = str(done_data.get("completion_status") or "complete").strip()
    if completion_status == "complete" and outcome.get("category") not in {
        "tool_blocked",
        "tool_failed",
        "action_not_executed",
        "execution_error",
        "no_answer",
    }:
        return "succeeded", None, False
    return (
        "failed",
        reason_code or completion_status or "executor_failed",
        outcome.get("retryable") is True,
    )


def _bounded(value: str | None, *, field: str, limit: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > limit:
        raise ValueError(f"invalid_{field}")
    return normalized


def _runtime_lock_key(user_id: int, scope: str) -> int:
    raw = f"{int(user_id)}:{scope}".encode()
    return int.from_bytes(hashlib.blake2b(raw, digest_size=4).digest(), "big", signed=True)


@contextmanager
def _local_runtime_lock(lock_key: int) -> Iterator[None]:
    with _LOCAL_LOCK_GUARD:
        lock = _LOCAL_CONVERSATION_LOCKS.setdefault(lock_key, threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


class AgentRuntimeCoordinator:
    """Owns Run identity, admission and lifecycle without health content."""

    def __init__(self, db: Session):
        self.db = db

    def get_run(self, user_id: int, run_id: str, *, lock: bool = False) -> AgentRun:
        query = self.db.query(AgentRun).filter(
            AgentRun.run_id == run_id,
            AgentRun.user_id == user_id,
        )
        if lock and self.db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        run = query.first()
        if run is None:
            raise AgentRuntimeError("run_not_found")
        return run

    def create_or_resume_run(
        self,
        *,
        run_id: str,
        attempt_id: str,
        user_id: int,
        conversation_id: int | None,
        client_turn_id: str | None,
        origin: str,
        origin_device_id: str | None = None,
        local_execution_id: str | None = None,
        privacy_mode: str = "cloud",
    ) -> RunAdmission:
        run_id = _bounded(run_id, field="run_id", limit=64) or ""
        attempt_id = _bounded(attempt_id, field="attempt_id", limit=64) or ""
        client_turn_id = _bounded(client_turn_id, field="client_turn_id", limit=112)
        origin = _bounded(origin, field="origin", limit=32) or "unknown"
        origin_device_id = _bounded(origin_device_id, field="origin_device_id", limit=128)
        local_execution_id = _bounded(local_execution_id, field="local_execution_id", limit=128)
        privacy_mode = _bounded(privacy_mode, field="privacy_mode", limit=32) or "cloud"

        if conversation_id is not None:
            self._require_owned_conversation(user_id, conversation_id)

        values = {
            "run_id": run_id,
            "attempt_id": attempt_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "client_turn_id": client_turn_id,
            "origin": origin,
            "origin_device_id": origin_device_id,
            "local_execution_id": local_execution_id,
            "privacy_mode": privacy_mode,
        }
        if client_turn_id:
            with self._admission_lock(user_id, f"client_turn:{client_turn_id}"):
                existing = self._find_client_turn(user_id, client_turn_id)
                lock_conversation_id = conversation_id
                if lock_conversation_id is None and existing is not None:
                    lock_conversation_id = existing.conversation_id
                if lock_conversation_id is not None:
                    with self._admission_lock(
                        user_id, f"conversation:{int(lock_conversation_id)}"
                    ):
                        return self._admit_locked(**values)
                return self._admit_locked(**values)
        if conversation_id is not None:
            with self._admission_lock(
                user_id, f"conversation:{int(conversation_id)}"
            ):
                return self._admit_locked(**values)
        with self._admission_lock(user_id, f"run:{run_id}"):
            return self._admit_locked(**values)

    @contextmanager
    def _admission_lock(self, user_id: int, scope: str) -> Iterator[None]:
        lock_key = _runtime_lock_key(user_id, scope)
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :lock_key)"),
                {"namespace": _POSTGRES_ADVISORY_NAMESPACE, "lock_key": lock_key},
            )
            yield
            return
        with _local_runtime_lock(lock_key):
            yield

    def _admit_locked(self, **values: Any) -> RunAdmission:
        user_id = int(values["user_id"])
        conversation_id = (
            int(values["conversation_id"])
            if values.get("conversation_id") is not None
            else None
        )
        client_turn_id = values.get("client_turn_id")
        if client_turn_id:
            existing = self._find_client_turn(user_id, client_turn_id)
            if existing is not None:
                requested_conversation_id = values.get("conversation_id")
                if (
                    requested_conversation_id is not None
                    and existing.conversation_id not in {None, requested_conversation_id}
                ):
                    raise AgentRuntimeError("conversation_mismatch")
                return self._admit_existing(
                    existing,
                    values["attempt_id"],
                    conversation_id=requested_conversation_id,
                )

        if values.get("conversation_id") is None:
            return self._create_run(input_seq=None, **values)

        active = self._active_conversation_run(user_id, conversation_id)
        if active is not None:
            raise RunBusyError(active.run_id)
        latest_seq = self.db.query(func.max(AgentRun.input_seq)).filter(
            AgentRun.user_id == user_id,
            AgentRun.conversation_id == conversation_id,
        ).scalar()
        return self._create_run(input_seq=int(latest_seq or 0) + 1, **values)

    def _admit_existing(
        self,
        run: AgentRun,
        attempt_id: str,
        *,
        conversation_id: int | None,
    ) -> RunAdmission:
        if run.status in ACTIVE_RUN_STATUSES:
            return RunAdmission(
                self._context(run),
                resumed=True,
                disposition="observe",
            )
        if run.status == "failed" and run.retryable is True:
            return self._retry_run(
                run,
                attempt_id,
                conversation_id=conversation_id,
            )
        return RunAdmission(
            self._context(run),
            resumed=True,
            disposition="replay",
        )

    def _retry_run(
        self,
        run: AgentRun,
        attempt_id: str,
        *,
        conversation_id: int | None,
    ) -> RunAdmission:
        target_conversation_id = run.conversation_id or conversation_id
        if target_conversation_id is not None:
            active = self._active_conversation_run(
                run.user_id,
                target_conversation_id,
                exclude_run_id=run.run_id,
            )
            if active is not None:
                raise RunBusyError(active.run_id)
        if run.conversation_id is None and target_conversation_id is not None:
            latest_seq = self.db.query(func.max(AgentRun.input_seq)).filter(
                AgentRun.user_id == run.user_id,
                AgentRun.conversation_id == target_conversation_id,
            ).scalar()
            run.conversation_id = target_conversation_id
            run.input_seq = int(latest_seq or 0) + 1

        latest_attempt_no = self.db.query(func.max(AgentRunAttempt.attempt_no)).filter(
            AgentRunAttempt.run_id == run.run_id,
        ).scalar()
        attempt = AgentRunAttempt(
            attempt_id=attempt_id,
            run_id=run.run_id,
            attempt_no=int(latest_attempt_no or 0) + 1,
            status="queued",
        )
        run.status = "queued"
        run.current_attempt_id = attempt_id
        run.retryable = False
        run.error_code = None
        run.finished_at = None
        self.db.add(attempt)
        self.db.flush()
        self._append_event(run, attempt_id, "run.retried", {"status": "queued"})
        self.db.commit()
        return RunAdmission(
            self._context(run),
            resumed=True,
            disposition="execute",
        )

    def _create_run(self, *, input_seq: int | None, **values: Any) -> RunAdmission:
        run = AgentRun(
            run_id=values["run_id"],
            user_id=values["user_id"],
            conversation_id=values["conversation_id"],
            client_turn_id=values.get("client_turn_id"),
            input_seq=input_seq,
            status="queued",
            current_attempt_id=values["attempt_id"],
            retryable=False,
            origin=values["origin"],
            origin_device_id=values.get("origin_device_id"),
            local_execution_id=values.get("local_execution_id"),
            privacy_mode=values["privacy_mode"],
        )
        attempt = AgentRunAttempt(
            attempt_id=values["attempt_id"],
            run_id=values["run_id"],
            attempt_no=1,
            status="queued",
        )
        self.db.add_all([run, attempt])
        try:
            self.db.flush()
            self._append_event(
                run,
                attempt.attempt_id,
                "run.created",
                {"status": "queued", **({"input_seq": input_seq} if input_seq else {})},
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            client_turn_id = values.get("client_turn_id")
            if client_turn_id:
                existing = self._find_client_turn(values["user_id"], client_turn_id)
                if existing is not None:
                    return self._admit_existing(
                        existing,
                        values["attempt_id"],
                        conversation_id=values.get("conversation_id"),
                    )
            if values["conversation_id"] is not None:
                active = self.db.query(AgentRun).filter(
                    AgentRun.user_id == values["user_id"],
                    AgentRun.conversation_id == values["conversation_id"],
                    AgentRun.status.in_(ACTIVE_RUN_STATUSES),
                ).first()
                if active is not None:
                    raise RunBusyError(active.run_id)
            raise
        return RunAdmission(
            self._context(run),
            resumed=False,
            disposition="execute",
        )

    def mark_running(self, context: RunContext) -> None:
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status == "running":
                return
            self._transition(run, "running")
            now = _now()
            run.started_at = run.started_at or now
            attempt.status = "running"
            attempt.started_at = attempt.started_at or now
            self._append_event(
                run, attempt.attempt_id, "run.started", {"status": "running"}
            )
            self.db.commit()

    def bind_messages(
        self,
        context: RunContext,
        *,
        conversation_id: int,
        source_message_id: int | None,
        assistant_message_id: int | None,
    ) -> None:
        conversation = self.db.query(AgentConversation).filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == context.user_id,
        ).first()
        if conversation is None:
            raise AgentRuntimeError("conversation_not_found")
        for message_id in (source_message_id, assistant_message_id):
            if message_id is None:
                continue
            exists = self.db.query(AgentMessage.id).filter(
                AgentMessage.id == message_id,
                AgentMessage.conversation_id == conversation_id,
            ).first()
            if exists is None:
                raise AgentRuntimeError("message_not_found")
        with self._admission_lock(
            context.user_id, f"conversation:{int(conversation_id)}"
        ):
            with self._lifecycle_lock(context):
                run, _attempt = self._owned_run_and_attempt(context, lock=True)
                if run.conversation_id is None:
                    active = self._active_conversation_run(
                        context.user_id,
                        conversation_id,
                        exclude_run_id=run.run_id,
                    )
                    if active is not None:
                        raise RunBusyError(active.run_id)
                    latest_seq = self.db.query(func.max(AgentRun.input_seq)).filter(
                        AgentRun.user_id == context.user_id,
                        AgentRun.conversation_id == conversation_id,
                        AgentRun.run_id != run.run_id,
                    ).scalar()
                    run.conversation_id = conversation_id
                    run.input_seq = int(latest_seq or 0) + 1
                elif run.conversation_id != conversation_id:
                    raise AgentRuntimeError("conversation_mismatch")
                run.source_message_id = source_message_id
                run.assistant_message_id = assistant_message_id
                self.db.commit()

    def complete(
        self,
        context: RunContext,
        *,
        status: str,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        if status not in COMPLETION_RUN_STATUSES:
            raise InvalidRunTransition(f"unsupported_completion_status:{status}")
        safe_error_code = self._safe_error_code(error_code)
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status == status:
                return
            self._transition(run, status)
            now = _now()
            run.error_code = safe_error_code
            run.retryable = bool(retryable) if status == "failed" else False
            run.finished_at = None if status == "waiting_for_user" else now
            if status in {"succeeded", "waiting_for_user"}:
                attempt.status = "succeeded"
            elif status == "cancelled":
                attempt.status = "cancelled"
            else:
                attempt.status = "failed"
            attempt.error_code = run.error_code
            attempt.finished_at = now
            event_name = {
                "waiting_for_user": "run.waiting",
                "reconciliation_required": "run.reconciliation_required",
            }.get(status, f"run.{status}")
            payload = {"status": status}
            if run.error_code:
                payload["error_code"] = run.error_code
            self._append_event(run, attempt.attempt_id, event_name, payload)
            self.db.commit()

    def finalize_executor_done(
        self,
        context: RunContext,
        done_data: Mapping[str, Any],
        *,
        source_message_id: int | None = None,
    ) -> None:
        conversation_id = done_data.get("conversation_id")
        assistant_message_id = done_data.get("message_id")
        if isinstance(conversation_id, int):
            self.bind_messages(
                context,
                conversation_id=conversation_id,
                source_message_id=(
                    source_message_id if isinstance(source_message_id, int) else None
                ),
                assistant_message_id=(
                    assistant_message_id if isinstance(assistant_message_id, int) else None
                ),
            )
        status, error_code, retryable = runtime_outcome_from_done(done_data)
        self.complete(
            context,
            status=status,
            error_code=error_code,
            retryable=retryable,
        )

    def fail_active(self, context: RunContext, *, error_code: str) -> None:
        run = self.get_run(context.user_id, context.run_id)
        if run.status not in ACTIVE_RUN_STATUSES:
            return
        self.complete(context, status="failed", error_code=error_code)

    def cancel_active(self, context: RunContext, *, error_code: str = "cancelled") -> None:
        run = self.get_run(context.user_id, context.run_id)
        if run.status not in ACTIVE_RUN_STATUSES:
            return
        self.complete(context, status="cancelled", error_code=error_code)

    def record_event(
        self,
        context: RunContext,
        event_name: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lifecycle_lock(context):
            run, _attempt = self._owned_run_and_attempt(context, lock=True)
            self._validate_event(event_name, payload or {})
            self._append_event(run, context.attempt_id, event_name, dict(payload or {}))
            self.db.commit()

    def _transition(self, run: AgentRun, target: str) -> None:
        if run.status == target:
            return
        if target not in _RUN_TRANSITIONS.get(run.status, frozenset()):
            raise InvalidRunTransition(f"{run.status}->{target}")
        run.status = target

    def _owned_run_and_attempt(
        self, context: RunContext, *, lock: bool = False
    ) -> tuple[AgentRun, AgentRunAttempt]:
        run = self.get_run(context.user_id, context.run_id, lock=lock)
        if run.current_attempt_id != context.attempt_id:
            raise StaleRunAttempt("stale_run_attempt")
        attempt = self.db.query(AgentRunAttempt).filter(
            AgentRunAttempt.attempt_id == context.attempt_id,
            AgentRunAttempt.run_id == context.run_id,
        ).first()
        if attempt is None:
            raise AgentRuntimeError("attempt_not_found")
        return run, attempt

    def _find_client_turn(self, user_id: int, client_turn_id: str) -> AgentRun | None:
        return self.db.query(AgentRun).filter(
            AgentRun.user_id == user_id,
            AgentRun.client_turn_id == client_turn_id,
        ).first()

    def _active_conversation_run(
        self,
        user_id: int,
        conversation_id: int,
        *,
        exclude_run_id: str | None = None,
    ) -> AgentRun | None:
        query = self.db.query(AgentRun).filter(
            AgentRun.user_id == user_id,
            AgentRun.conversation_id == conversation_id,
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        if exclude_run_id is not None:
            query = query.filter(AgentRun.run_id != exclude_run_id)
        return query.first()

    def _require_owned_conversation(self, user_id: int, conversation_id: int) -> None:
        exists = self.db.query(AgentConversation.id).filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        ).first()
        if exists is None:
            raise ConversationAccessError("conversation_not_found")

    @contextmanager
    def _lifecycle_lock(self, context: RunContext) -> Iterator[None]:
        if self.db.get_bind().dialect.name == "postgresql":
            yield
            return
        lock_key = _runtime_lock_key(context.user_id, f"run:{context.run_id}")
        with _local_runtime_lock(lock_key):
            yield

    @staticmethod
    def _safe_error_code(value: str | None) -> str | None:
        normalized = _bounded(value, field="error_code", limit=80)
        if normalized is not None and normalized not in _known_error_codes():
            return "unclassified_error"
        return normalized

    def _context(self, run: AgentRun) -> RunContext:
        attempt = self.db.query(AgentRunAttempt).filter(
            AgentRunAttempt.run_id == run.run_id,
            AgentRunAttempt.attempt_id == run.current_attempt_id,
        ).first()
        if attempt is None:
            raise AgentRuntimeError("attempt_not_found")
        return RunContext(
            run_id=run.run_id,
            attempt_id=attempt.attempt_id,
            user_id=run.user_id,
            conversation_id=run.conversation_id,
            client_turn_id=run.client_turn_id,
            input_seq=run.input_seq,
            origin=run.origin,
            origin_device_id=run.origin_device_id,
            local_execution_id=run.local_execution_id,
            privacy_mode=run.privacy_mode,
        )

    def _append_event(
        self,
        run: AgentRun,
        attempt_id: str | None,
        event_name: str,
        payload: Mapping[str, Any],
    ) -> None:
        self._validate_event(event_name, payload)
        latest = self.db.query(func.max(AgentRunEvent.sequence_no)).filter(
            AgentRunEvent.run_id == run.run_id,
        ).scalar()
        self.db.add(AgentRunEvent(
            run_id=run.run_id,
            attempt_id=attempt_id,
            sequence_no=int(latest or 0) + 1,
            event_name=event_name,
            payload=dict(payload) or None,
        ))

    @staticmethod
    def _validate_event(event_name: str, payload: Mapping[str, Any]) -> None:
        if event_name not in _EVENT_NAMES:
            raise UnsafeRunEventPayload("event_name_not_allowlisted")
        for key, value in payload.items():
            if key not in _EVENT_PAYLOAD_KEYS:
                raise UnsafeRunEventPayload(f"event_key_not_allowlisted:{key}")
            if isinstance(value, str) and len(value) > _MAX_EVENT_STRING_LENGTH:
                raise UnsafeRunEventPayload(f"event_value_too_long:{key}")
            if (
                key in _TOKEN_EVENT_KEYS
                and isinstance(value, str)
                and not _SAFE_EVENT_TOKEN.fullmatch(value)
            ):
                raise UnsafeRunEventPayload(f"event_value_not_token:{key}")
            if key == "status" and value not in _KNOWN_STATUS_VALUES:
                raise UnsafeRunEventPayload("event_status_not_allowlisted")
            if key == "completion_status" and value not in _KNOWN_COMPLETION_VALUES:
                raise UnsafeRunEventPayload("event_completion_not_allowlisted")
            if key == "error_code" and value not in _known_error_codes():
                raise UnsafeRunEventPayload("event_error_code_not_allowlisted")
            if key == "tool_name" and value not in _known_tool_names():
                raise UnsafeRunEventPayload("event_tool_not_registered")
            if key == "effect_class" and value not in _KNOWN_EFFECT_CLASSES:
                raise UnsafeRunEventPayload("event_effect_class_not_allowlisted")
            if key == "replayed" and type(value) is not bool:
                raise UnsafeRunEventPayload("event_replayed_not_bool")
            if key == "receipt_verified" and type(value) is not bool:
                raise UnsafeRunEventPayload("event_receipt_not_bool")
            if key == "input_seq" and (
                type(value) is not int or value <= 0
            ):
                raise UnsafeRunEventPayload("event_input_seq_not_positive_int")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise UnsafeRunEventPayload(f"event_value_not_scalar:{key}")
