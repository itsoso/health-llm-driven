"""Durable, content-free control plane for cloud Agent execution."""
from __future__ import annotations

import hashlib
import re
import threading
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Iterator, Literal, Mapping

from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.agent_runtime import (
    AgentRun,
    AgentRunAttempt,
    AgentRunEvent,
    AgentToolOperation,
)
from app.services.agent_runtime_identity import runtime_hmac_digest


ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})
TERMINAL_RUN_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "reconciliation_required"}
)
COMPLETION_RUN_STATUSES = TERMINAL_RUN_STATUSES | {"waiting_for_user"}

_RUN_TRANSITIONS = {
    "queued": frozenset({"running", "failed", "cancelled"}),
    "running": COMPLETION_RUN_STATUSES,
    "waiting_for_user": frozenset({"succeeded", "failed", "cancelled"}),
    "reconciliation_required": frozenset({"failed"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

_EVENT_NAMES = frozenset(
    {
        "run.created",
        "run.retried",
        "run.started",
        "run.cancel_requested",
        "run.waiting",
        "run.succeeded",
        "run.failed",
        "run.cancelled",
        "run.reconciliation_required",
        "run.reconciled",
        "tool.requested",
        "tool.failed",
        "tool.reconciliation_required",
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
_OPERATION_DISCRIMINATOR_KINDS = frozenset({
    "meal_time",
    "photo_token",
})
_SAFE_EVENT_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
_TOKEN_EVENT_KEYS = frozenset(
    {"status", "completion_status", "error_code", "tool_name", "effect_class"}
)
_CONTRACT_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_CONTRACT_VERSION = "agent-runtime-v1"
_KNOWN_ERROR_CODES = frozenset(
    {
        "cancelled",
        "cancelled_with_unresolved_write",
        "capacity_unavailable",
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
        "worker_lease_expired",
        "worker_lease_expired_write",
        "worker_interrupted",
        "worker_interrupted_write",
        "duplicate_in_flight",
        "deadline_exceeded",
        "missing_receipt",
        "tool_failed",
        "tool_rejected",
        "write_uncertain",
        "write_verified_reply_incomplete",
        "reconciled_no_effect",
        "retry_plan_mismatch",
        "reconciliation_grace_period",
        "unsupported_reconciliation_resource",
        "operation_timestamp_missing",
        "aigc_media_turn_disallows_health_write",
        "ambiguous_intent_requires_clarification",
        "manage_write_without_mutate_intent",
        "write_tool_without_write_intent",
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
_LOCAL_RUNTIME_LOCKS: dict[int, threading.RLock] = {}
_SQLITE_ENGINE_LOCKS: weakref.WeakKeyDictionary[Any, threading.RLock] = (
    weakref.WeakKeyDictionary()
)


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


class StaleRunWorker(AgentRuntimeError):
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
    control_reason: str | None = None


RUNTIME_WRITE_BLOCK_REASONS = frozenset({
    "circuit_paused",
    "circuit_unavailable",
})


def runtime_write_block_reason(context: RunContext) -> str | None:
    """Return the control-plane reason that must fail writes closed."""
    if context.control_reason in RUNTIME_WRITE_BLOCK_REASONS:
        return context.control_reason
    return None


@dataclass(frozen=True, slots=True)
class RuntimeContractSnapshot:
    runtime_contract_version: str
    tool_registry_digest: str
    capability_policy_digest: str

    @classmethod
    def current(cls) -> "RuntimeContractSnapshot":
        from app.services.agent_kernel.capability_policy import (
            capability_policy_digest,
        )
        from app.services.agent_kernel.tool_registry import tool_registry_digest

        return cls(
            runtime_contract_version=_RUNTIME_CONTRACT_VERSION,
            tool_registry_digest=tool_registry_digest(),
            capability_policy_digest=capability_policy_digest(),
        )


@dataclass(frozen=True, slots=True)
class RunAdmission:
    context: RunContext
    resumed: bool
    disposition: Literal["execute", "observe", "replay"]

    @property
    def owns_execution(self) -> bool:
        return self.disposition == "execute"


@dataclass(frozen=True, slots=True)
class ToolOperationAdmission:
    operation_id: str
    disposition: Literal["execute", "replay", "reconcile", "reject"]
    resource_type: str | None = None
    resource_id: str | None = None
    error_code: str | None = None

    @property
    def owns_execution(self) -> bool:
        return self.disposition == "execute"


@dataclass(frozen=True, slots=True)
class RunControlSignal:
    action: Literal["continue", "cancel_requested", "deadline_exceeded"]


@dataclass(frozen=True, slots=True)
class CancelRequestResult:
    run_id: str
    status: str


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    run_id: str
    status: str
    error_code: str | None


@dataclass(frozen=True, slots=True)
class ToolOperationReconciliation:
    operation_id: str
    disposition: Literal["verified_effect", "verified_no_effect", "unknown"]
    reason_code: str
    resource_type: str | None = None
    resource_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunEventView:
    sequence_no: int
    event_name: str
    payload: Mapping[str, Any]
    created_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


@lru_cache(maxsize=1)
def _known_tool_names() -> frozenset[str]:
    from app.services.agent_kernel.tool_registry import list_tool_specs

    return frozenset(spec.name for spec in list_tool_specs())


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
    if outcome.get("category") == "tool_blocked":
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


def _validated_contract_snapshot(
    snapshot: RuntimeContractSnapshot | None,
) -> RuntimeContractSnapshot:
    resolved = snapshot or RuntimeContractSnapshot.current()
    version = _bounded(
        resolved.runtime_contract_version,
        field="runtime_contract_version",
        limit=32,
    )
    if version is None:
        raise ValueError("invalid_runtime_contract_version")
    tool_digest = str(resolved.tool_registry_digest or "").strip()
    policy_digest = str(resolved.capability_policy_digest or "").strip()
    if not _CONTRACT_DIGEST.fullmatch(tool_digest):
        raise ValueError("invalid_tool_registry_digest")
    if not _CONTRACT_DIGEST.fullmatch(policy_digest):
        raise ValueError("invalid_capability_policy_digest")
    return RuntimeContractSnapshot(
        runtime_contract_version=version,
        tool_registry_digest=tool_digest,
        capability_policy_digest=policy_digest,
    )


@contextmanager
def _local_runtime_lock(lock_key: int) -> Iterator[None]:
    with _LOCAL_LOCK_GUARD:
        lock = _LOCAL_RUNTIME_LOCKS.setdefault(lock_key, threading.RLock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


@contextmanager
def _sqlite_runtime_lock(bind: Any) -> Iterator[None]:
    """Serialize a StaticPool engine without leaking locks across fixtures."""
    with _LOCAL_LOCK_GUARD:
        lock = _SQLITE_ENGINE_LOCKS.get(bind)
        if lock is None:
            lock = threading.RLock()
            _SQLITE_ENGINE_LOCKS[bind] = lock
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

    def get_run_by_client_turn(
        self,
        user_id: int,
        client_turn_id: str,
    ) -> AgentRun | None:
        """Return an owner-scoped Run without exposing message content."""
        normalized = _bounded(
            client_turn_id,
            field="client_turn_id",
            limit=112,
        )
        if not normalized:
            return None
        return self.db.query(AgentRun).filter(
            AgentRun.user_id == user_id,
            AgentRun.client_turn_id == normalized,
        ).first()

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
        deadline_at: datetime | None = None,
        contract_snapshot: RuntimeContractSnapshot | None = None,
    ) -> RunAdmission:
        run_id = _bounded(run_id, field="run_id", limit=64) or ""
        attempt_id = _bounded(attempt_id, field="attempt_id", limit=64) or ""
        client_turn_id = _bounded(client_turn_id, field="client_turn_id", limit=112)
        origin = _bounded(origin, field="origin", limit=32) or "unknown"
        origin_device_id = _bounded(origin_device_id, field="origin_device_id", limit=128)
        local_execution_id = _bounded(local_execution_id, field="local_execution_id", limit=128)
        privacy_mode = _bounded(privacy_mode, field="privacy_mode", limit=32) or "cloud"
        contract_snapshot = _validated_contract_snapshot(contract_snapshot)

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
            "deadline_at": deadline_at,
            "runtime_contract_version": (
                contract_snapshot.runtime_contract_version
            ),
            "tool_registry_digest": contract_snapshot.tool_registry_digest,
            "capability_policy_digest": (
                contract_snapshot.capability_policy_digest
            ),
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
                        if conversation_id is not None:
                            self._require_owned_conversation(
                                user_id, conversation_id
                            )
                        return self._admit_locked(**values)
                return self._admit_locked(**values)
        if conversation_id is not None:
            with self._admission_lock(
                user_id, f"conversation:{int(conversation_id)}"
            ):
                self._require_owned_conversation(user_id, conversation_id)
                return self._admit_locked(**values)
        with self._admission_lock(user_id, f"run:{run_id}"):
            return self._admit_locked(**values)

    @contextmanager
    def _admission_lock(self, user_id: int, scope: str) -> Iterator[None]:
        bind = self.db.get_bind()
        lock_key = _runtime_lock_key(user_id, scope)
        if bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :lock_key)"),
                {"namespace": _POSTGRES_ADVISORY_NAMESPACE, "lock_key": lock_key},
            )
            yield
            return
        if bind.dialect.name == "sqlite":
            # Test/local SQLite uses StaticPool and therefore one DB-API
            # connection across sessions. Serialize the whole Runtime access;
            # the RLock keeps nested client-turn -> conversation admission safe.
            with _sqlite_runtime_lock(bind):
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
                    deadline_at=values.get("deadline_at"),
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
        deadline_at: datetime | None = None,
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
                deadline_at=deadline_at,
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
        deadline_at: datetime | None = None,
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
        run.cancel_requested_at = None
        run.deadline_at = deadline_at
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
            runtime_contract_version=values["runtime_contract_version"],
            tool_registry_digest=values["tool_registry_digest"],
            capability_policy_digest=values["capability_policy_digest"],
            deadline_at=values.get("deadline_at"),
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
                        deadline_at=values.get("deadline_at"),
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

    def mark_running(
        self,
        context: RunContext,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 90,
        now: datetime | None = None,
    ) -> None:
        safe_worker_id = _bounded(
            worker_id or context.attempt_id,
            field="worker_id",
            limit=128,
        )
        lease_seconds = self._validate_lease_seconds(lease_seconds)
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status == "running":
                if attempt.status != "running":
                    raise StaleRunAttempt("attempt_not_running")
                if attempt.worker_id is None:
                    current_time = now or _now()
                    attempt.worker_id = safe_worker_id
                    attempt.heartbeat_at = current_time
                    attempt.lease_expires_at = current_time + timedelta(
                        seconds=lease_seconds
                    )
                    self.db.commit()
                    return
                if attempt.worker_id != safe_worker_id:
                    raise StaleRunWorker("worker_mismatch")
                return
            self._transition(run, "running")
            current_time = now or _now()
            run.started_at = run.started_at or current_time
            attempt.status = "running"
            attempt.started_at = attempt.started_at or current_time
            attempt.worker_id = safe_worker_id
            attempt.heartbeat_at = current_time
            attempt.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
            self._append_event(
                run, attempt.attempt_id, "run.started", {"status": "running"}
            )
            self.db.commit()

    def renew_lease(
        self,
        context: RunContext,
        *,
        worker_id: str,
        lease_seconds: int = 90,
        now: datetime | None = None,
    ) -> RunControlSignal:
        safe_worker_id = _bounded(worker_id, field="worker_id", limit=128) or ""
        lease_seconds = self._validate_lease_seconds(lease_seconds)
        current_time = now or _now()
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status not in ACTIVE_RUN_STATUSES or attempt.status != "running":
                raise StaleRunAttempt("attempt_not_running")
            if attempt.worker_id != safe_worker_id:
                raise StaleRunWorker("worker_mismatch")
            if run.cancel_requested_at is not None:
                return RunControlSignal("cancel_requested")
            if run.deadline_at is not None and self._at_or_after(
                current_time, run.deadline_at
            ):
                return RunControlSignal("deadline_exceeded")
            attempt.heartbeat_at = current_time
            attempt.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
            self.db.commit()
            return RunControlSignal("continue")

    def request_cancel(
        self,
        user_id: int,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> CancelRequestResult:
        run = self.get_run(user_id, run_id)
        context = self._context(run)
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status in TERMINAL_RUN_STATUSES:
                return CancelRequestResult(run.run_id, run.status)
            if run.status in {"queued", "waiting_for_user"}:
                self._transition(run, "cancelled")
                current_time = now or _now()
                run.error_code = "cancelled"
                run.retryable = False
                run.finished_at = current_time
                attempt.status = "cancelled"
                attempt.error_code = "cancelled"
                attempt.finished_at = current_time
                attempt.lease_expires_at = None
                self._append_event(
                    run,
                    attempt.attempt_id,
                    "run.cancelled",
                    {"status": "cancelled", "error_code": "cancelled"},
                )
                self.db.commit()
                return CancelRequestResult(run.run_id, "cancelled")
            if run.cancel_requested_at is None:
                run.cancel_requested_at = now or _now()
                self._append_event(
                    run,
                    attempt.attempt_id,
                    "run.cancel_requested",
                    {"status": "running"},
                )
                self.db.commit()
            return CancelRequestResult(run.run_id, "cancellation_requested")

    def settle_control_stop(
        self,
        context: RunContext,
        *,
        action: Literal["cancel_requested", "deadline_exceeded"],
        now: datetime | None = None,
    ) -> None:
        if action not in {"cancel_requested", "deadline_exceeded"}:
            raise ValueError("invalid_control_stop_action")
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status not in ACTIVE_RUN_STATUSES:
                return
            current_time = now or _now()
            self._apply_control_stop_locked(
                run,
                attempt,
                action=action,
                now=current_time,
            )
            self.db.commit()

    def recover_expired_runs(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        unleased_grace_seconds: int = 420,
    ) -> list[RecoveryResult]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("invalid_recovery_limit")
        unleased_grace_seconds = self._validate_unleased_grace_seconds(
            unleased_grace_seconds
        )
        current_time = now or _now()
        unleased_before = current_time - timedelta(
            seconds=unleased_grace_seconds
        )
        with self._recovery_scan_lock():
            recovered: list[RecoveryResult] = []
            for _index in range(limit):
                # Process exactly one locked row per transaction. Settlement
                # commits by design; selecting a whole batch would release the
                # remaining PostgreSQL row locks after the first commit.
                query = self.db.query(AgentRun, AgentRunAttempt).join(
                    AgentRunAttempt,
                    AgentRunAttempt.attempt_id == AgentRun.current_attempt_id,
                ).filter(
                    or_(
                        and_(
                            AgentRun.status == "running",
                            AgentRunAttempt.status == "running",
                            or_(
                                and_(
                                    AgentRunAttempt.lease_expires_at.is_not(None),
                                    AgentRunAttempt.lease_expires_at <= current_time,
                                ),
                                and_(
                                    AgentRunAttempt.lease_expires_at.is_(None),
                                    AgentRunAttempt.started_at.is_not(None),
                                    AgentRunAttempt.started_at <= unleased_before,
                                ),
                            ),
                        ),
                        and_(
                            AgentRun.status == "queued",
                            AgentRunAttempt.status == "queued",
                            AgentRun.deadline_at.is_not(None),
                            AgentRun.deadline_at <= current_time,
                        ),
                    )
                ).order_by(
                    func.coalesce(
                        AgentRunAttempt.lease_expires_at,
                        AgentRun.deadline_at,
                    ).asc()
                )
                if self.db.get_bind().dialect.name == "postgresql":
                    query = query.with_for_update(skip_locked=True)
                stale = query.first()
                if stale is None:
                    break
                run, _attempt = stale
                context = self._context(run)
                if run.status == "queued":
                    self.settle_control_stop(
                        context,
                        action="deadline_exceeded",
                        now=current_time,
                    )
                elif run.cancel_requested_at is not None:
                    self.settle_control_stop(
                        context,
                        action="cancel_requested",
                        now=current_time,
                    )
                elif run.deadline_at is not None and self._at_or_after(
                    current_time, run.deadline_at
                ):
                    self.settle_control_stop(
                        context,
                        action="deadline_exceeded",
                        now=current_time,
                    )
                elif self._has_unresolved_write(run.run_id):
                    self._settle_expired_write(
                        context,
                        now=current_time,
                    )
                else:
                    self.complete(
                        context,
                        status="failed",
                        error_code="worker_lease_expired",
                        retryable=True,
                    )
                self.db.refresh(run)
                recovered.append(
                    RecoveryResult(run.run_id, run.status, run.error_code)
                )
            return recovered

    def reconcile_pending_tool_operations(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        grace_seconds: int = 90,
    ) -> list[ToolOperationReconciliation]:
        """Reconcile supported terminal writes without retrying legacy operations."""
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("invalid_reconciliation_limit")
        if type(grace_seconds) is not int or not 0 <= grace_seconds <= 3600:
            raise ValueError("invalid_reconciliation_grace_seconds")
        from app.services.agent_operation_reconciliation import (
            AUTO_RECONCILIATION_RESOURCE_TYPES,
        )

        operation_ids = [
            row.operation_id
            for row in self.db.query(AgentToolOperation.operation_id).join(
                AgentRun,
                AgentRun.run_id == AgentToolOperation.run_id,
            ).filter(
                AgentRun.status == "reconciliation_required",
                AgentToolOperation.status == "reconciliation_required",
                AgentToolOperation.resource_type.in_(
                    AUTO_RECONCILIATION_RESOURCE_TYPES
                ),
            ).order_by(AgentToolOperation.created_at.asc()).limit(limit).all()
        ]
        return [
            self.reconcile_tool_operation(
                operation_id,
                now=now,
                grace_seconds=grace_seconds,
            )
            for operation_id in operation_ids
        ]

    def list_events_after(
        self,
        user_id: int,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 50,
    ) -> list[RunEventView]:
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("invalid_event_cursor")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("invalid_event_limit")
        run = self.get_run(user_id, run_id)
        events = self.db.query(AgentRunEvent).filter(
            AgentRunEvent.run_id == run.run_id,
            AgentRunEvent.sequence_no > after_sequence,
        ).order_by(AgentRunEvent.sequence_no.asc()).limit(limit).all()
        return [
            RunEventView(
                sequence_no=event.sequence_no,
                event_name=event.event_name,
                payload=dict(event.payload or {}),
                created_at=event.created_at,
            )
            for event in events
        ]

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
            now = _now()
            if self._has_unresolved_write(run.run_id):
                self._apply_unresolved_write_completion_locked(
                    run,
                    attempt,
                    now=now,
                )
                self.db.commit()
                return
            action = self._control_action(run, now=now)
            verified_success = (
                status == "succeeded" and self._has_verified_write(run.run_id)
            )
            if action is not None and not verified_success:
                self._apply_control_stop_locked(
                    run,
                    attempt,
                    action=action,
                    now=now,
                    preserve_verified_write=False,
                )
                self.db.commit()
                return
            self._apply_completion_locked(
                run,
                attempt,
                status=status,
                error_code=safe_error_code,
                retryable=retryable,
                now=now,
            )
            self.db.commit()

    def _apply_unresolved_write_completion_locked(
        self,
        run: AgentRun,
        attempt: AgentRunAttempt,
        *,
        now: datetime,
    ) -> None:
        operations = self.db.query(AgentToolOperation).filter(
            AgentToolOperation.run_id == run.run_id,
            AgentToolOperation.status.in_(
                {"requested", "executing", "reconciliation_required"}
            ),
        ).all()
        for operation in operations:
            if operation.status != "reconciliation_required":
                operation.status = "reconciliation_required"
                operation.error_code = "write_uncertain"
                operation.finished_at = now
        self._apply_completion_locked(
            run,
            attempt,
            status="reconciliation_required",
            error_code="write_uncertain",
            retryable=False,
            now=now,
        )

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

    def interrupt_active(self, context: RunContext) -> None:
        """Settle a task cancellation without pretending the user cancelled."""
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status not in ACTIVE_RUN_STATUSES:
                return
            now = _now()
            action = self._control_action(run, now=now)
            if action is not None:
                self._apply_control_stop_locked(
                    run,
                    attempt,
                    action=action,
                    now=now,
                )
            else:
                self._apply_worker_interruption_locked(run, attempt, now=now)
            self.db.commit()

    def cancel_active(self, context: RunContext, *, error_code: str = "cancelled") -> None:
        run = self.get_run(context.user_id, context.run_id)
        if run.status not in ACTIVE_RUN_STATUSES:
            return
        self.settle_control_stop(context, action="cancel_requested")

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

    def claim_tool_operation(
        self,
        context: RunContext,
        *,
        tool_name: str,
        effect_class: str,
        operation_fingerprint: str,
        expected_resource_type: str | None = None,
        logical_operation_key: str | None = None,
        logical_operation_scope_key: str | None = None,
        logical_operation_discriminator_kind: str | None = None,
        logical_operation_discriminator_key: str | None = None,
    ) -> ToolOperationAdmission:
        """Claim one content-free write operation before business dispatch."""
        fingerprint = str(operation_fingerprint or "").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("invalid_operation_fingerprint")
        logical_key = str(logical_operation_key or "").strip() or None
        if logical_key is not None and not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", logical_key
        ):
            raise ValueError("invalid_logical_operation_key")
        logical_key_hash = (
            runtime_hmac_digest("tool-logical-key", logical_key)
            if logical_key is not None
            else None
        )
        logical_scope_key = (
            str(logical_operation_scope_key or "").strip() or None
        )
        if logical_scope_key is not None and not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", logical_scope_key
        ):
            raise ValueError("invalid_logical_operation_scope_key")
        logical_scope_hash = (
            runtime_hmac_digest("tool-logical-scope", logical_scope_key)
            if logical_scope_key is not None
            else None
        )
        discriminator_kind = (
            str(logical_operation_discriminator_kind or "").strip() or None
        )
        discriminator_key = (
            str(logical_operation_discriminator_key or "").strip() or None
        )
        if (discriminator_kind is None) != (discriminator_key is None):
            raise ValueError("incomplete_logical_operation_discriminator")
        if (
            discriminator_kind is not None
            and discriminator_kind not in _OPERATION_DISCRIMINATOR_KINDS
        ):
            raise ValueError("invalid_logical_operation_discriminator_kind")
        if discriminator_key is not None and not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", discriminator_key
        ):
            raise ValueError("invalid_logical_operation_discriminator_key")
        discriminator_hash = (
            runtime_hmac_digest("tool-logical-discriminator", discriminator_key)
            if discriminator_key is not None
            else None
        )
        normalized_tool = str(tool_name or "").strip()
        if normalized_tool not in _known_tool_names():
            raise AgentRuntimeError("unknown_tool")
        if effect_class != "write":
            raise AgentRuntimeError("tool_operation_requires_write_effect")
        normalized_resource_type = _bounded(
            expected_resource_type,
            field="resource_type",
            limit=80,
        )
        if normalized_resource_type is not None:
            from app.services.agent_kernel.tool_registry import get_tool_spec

            declared_types = {
                resource_type
                for _record_type, resource_type in get_tool_spec(
                    normalized_tool
                ).reconciliation_record_types
            }
            if normalized_resource_type not in declared_types:
                raise AgentRuntimeError("invalid_resource_type")

        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status != "running" or attempt.status != "running":
                raise StaleRunAttempt("attempt_not_running")

            def reject_retry_plan_mismatch() -> ToolOperationAdmission:
                blocked_operation_id = "op_blocked_" + hashlib.sha256(
                    f"{context.run_id}:{logical_key_hash or fingerprint}".encode()
                ).hexdigest()[:40]
                self._append_event(
                    run,
                    context.attempt_id,
                    "tool.failed",
                    {
                        "tool_name": normalized_tool,
                        "effect_class": effect_class,
                        "status": "failed",
                        "error_code": "retry_plan_mismatch",
                    },
                )
                self.db.commit()
                return ToolOperationAdmission(
                    operation_id=blocked_operation_id,
                    disposition="reject",
                    error_code="retry_plan_mismatch",
                )

            exact_query = self.db.query(AgentToolOperation).filter(
                AgentToolOperation.run_id == context.run_id,
                AgentToolOperation.operation_fingerprint == fingerprint,
            )
            if self.db.get_bind().dialect.name == "postgresql":
                exact_query = exact_query.with_for_update()
            operation = exact_query.first()
            if operation is None and logical_key_hash is not None:
                logical_query = self.db.query(AgentToolOperation).filter(
                    AgentToolOperation.run_id == context.run_id,
                    AgentToolOperation.logical_operation_key_hash
                    == logical_key_hash,
                )
                if self.db.get_bind().dialect.name == "postgresql":
                    logical_query = logical_query.with_for_update()
                operation = logical_query.first()
            if operation is not None:
                if (
                    operation.tool_name != normalized_tool
                    or operation.effect_class != effect_class
                    or (
                        normalized_resource_type is not None
                        and operation.resource_type != normalized_resource_type
                    )
                ):
                    raise AgentRuntimeError("tool_operation_identity_mismatch")
                if (
                    logical_key_hash is not None
                    and operation.attempt_id == context.attempt_id
                    and operation.operation_fingerprint != fingerprint
                ):
                    raise AgentRuntimeError("tool_operation_identity_mismatch")
                if operation.status == "succeeded":
                    return ToolOperationAdmission(
                        operation_id=operation.operation_id,
                        disposition="replay",
                        resource_type=operation.resource_type,
                        resource_id=operation.resource_id,
                    )
                if (
                    operation.status == "failed"
                    and operation.error_code
                    in {"tool_rejected", "reconciled_no_effect"}
                ):
                    operation.status = "executing"
                    operation.attempt_id = context.attempt_id
                    operation.error_code = None
                    operation.verified_at = None
                    operation.finished_at = None
                    self._append_event(
                        run,
                        context.attempt_id,
                        "tool.requested",
                        {
                            "tool_name": normalized_tool,
                            "effect_class": effect_class,
                            "status": "executing",
                        },
                    )
                    self.db.commit()
                    return ToolOperationAdmission(
                        operation_id=operation.operation_id,
                        disposition="execute",
                    )
                # The duplicate caller must not mutate the operation owned by the
                # original executor. Otherwise the original cannot persist its
                # verified receipt after a successful business write.
                self._append_event(
                    run,
                    context.attempt_id,
                    "tool.reconciliation_required",
                    {
                        "tool_name": normalized_tool,
                        "effect_class": effect_class,
                        "status": "reconciliation_required",
                        "error_code": "duplicate_in_flight",
                    },
                )
                self.db.commit()
                return ToolOperationAdmission(
                    operation_id=operation.operation_id,
                    disposition="reconcile",
                    error_code="duplicate_in_flight",
                )

            if logical_scope_hash is not None:
                scope_query = self.db.query(AgentToolOperation).filter(
                    AgentToolOperation.run_id == context.run_id,
                    AgentToolOperation.logical_operation_scope_hash
                    == logical_scope_hash,
                )
                if self.db.get_bind().dialect.name == "postgresql":
                    scope_query = scope_query.with_for_update()
                for scoped_operation in scope_query.all():
                    proven_distinct = bool(
                        discriminator_kind
                        and discriminator_hash
                        and scoped_operation.logical_operation_discriminator_kind
                        == discriminator_kind
                        and scoped_operation.logical_operation_discriminator_hash
                        and scoped_operation.logical_operation_discriminator_hash
                        != discriminator_hash
                    )
                    if proven_distinct:
                        continue
                    if attempt.attempt_no > 1:
                        return reject_retry_plan_mismatch()
                    raise AgentRuntimeError("tool_operation_identity_mismatch")

            if attempt.attempt_no > 1:
                prior_operation = self.db.query(AgentToolOperation.operation_id).filter(
                    AgentToolOperation.run_id == context.run_id,
                    or_(
                        AgentToolOperation.created_attempt_no.is_(None),
                        AgentToolOperation.created_attempt_no < attempt.attempt_no,
                    ),
                ).first()
                if prior_operation is not None:
                    return reject_retry_plan_mismatch()

            operation_id = "op_" + hashlib.sha256(
                f"{context.run_id}:{logical_key_hash or fingerprint}".encode()
            ).hexdigest()[:48]
            operation = AgentToolOperation(
                operation_id=operation_id,
                run_id=context.run_id,
                attempt_id=context.attempt_id,
                tool_name=normalized_tool,
                effect_class=effect_class,
                operation_fingerprint=fingerprint,
                logical_operation_key_hash=logical_key_hash,
                logical_operation_scope_hash=logical_scope_hash,
                logical_operation_discriminator_kind=discriminator_kind,
                logical_operation_discriminator_hash=discriminator_hash,
                created_attempt_no=attempt.attempt_no,
                status="executing",
                resource_type=normalized_resource_type,
            )
            self.db.add(operation)
            self._append_event(
                run,
                context.attempt_id,
                "tool.requested",
                {
                    "tool_name": normalized_tool,
                    "effect_class": effect_class,
                    "status": "executing",
                },
            )
            self.db.commit()
            return ToolOperationAdmission(
                operation_id=operation_id,
                disposition="execute",
            )

    def finalize_tool_operation(
        self,
        context: RunContext,
        *,
        operation_id: str,
        status: Literal["succeeded", "failed", "reconciliation_required"],
        resource_type: str | None = None,
        resource_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Finalize an operation from structured receipt facts only."""
        if status not in {"succeeded", "failed", "reconciliation_required"}:
            raise AgentRuntimeError("unsupported_tool_operation_status")
        normalized_operation_id = _bounded(
            operation_id, field="operation_id", limit=96
        )
        normalized_resource_type = _bounded(
            resource_type, field="resource_type", limit=80
        )
        normalized_resource_id = _bounded(
            resource_id, field="resource_id", limit=128
        )
        if status == "succeeded" and not (
            normalized_resource_type and normalized_resource_id
        ):
            raise AgentRuntimeError("verified_resource_required")
        safe_error_code = str(error_code or "").strip() or None
        if status == "failed":
            safe_error_code = (
                safe_error_code
                if safe_error_code in {"tool_failed", "tool_rejected"}
                else "tool_failed"
            )
        elif status == "reconciliation_required":
            safe_error_code = (
                safe_error_code
                if safe_error_code in {
                    "duplicate_in_flight",
                    "missing_receipt",
                    "write_uncertain",
                }
                else "write_uncertain"
            )
        else:
            safe_error_code = None

        with self._lifecycle_lock(context):
            run, _attempt = self._owned_run_and_attempt(context, lock=True)
            query = self.db.query(AgentToolOperation).filter(
                AgentToolOperation.operation_id == normalized_operation_id,
                AgentToolOperation.run_id == context.run_id,
            )
            if self.db.get_bind().dialect.name == "postgresql":
                query = query.with_for_update()
            operation = query.first()
            if operation is None:
                raise AgentRuntimeError("tool_operation_not_found")
            if operation.attempt_id != context.attempt_id:
                raise StaleRunAttempt("stale_tool_operation_attempt")
            if status == "succeeded":
                from app.services.agent_kernel.tool_registry import (
                    is_registered_receipt_resource_type,
                    is_valid_receipt_resource_id,
                )

                if not is_registered_receipt_resource_type(
                    operation.tool_name,
                    normalized_resource_type or "",
                ):
                    raise AgentRuntimeError("invalid_resource_type")
                if not is_valid_receipt_resource_id(
                    operation.tool_name,
                    normalized_resource_id or "",
                ):
                    raise AgentRuntimeError("invalid_resource_id")
                if (
                    operation.resource_type is not None
                    and operation.resource_type != normalized_resource_type
                ):
                    raise AgentRuntimeError("invalid_resource_type")
            if operation.status == "succeeded" and status == "succeeded":
                return
            if operation.status not in {"executing", "requested"}:
                raise AgentRuntimeError(
                    f"invalid_tool_operation_transition:{operation.status}->{status}"
                )

            now = _now()
            operation.status = status
            operation.error_code = safe_error_code
            operation.finished_at = now
            if status == "succeeded":
                operation.resource_type = normalized_resource_type
                operation.resource_id = normalized_resource_id
                operation.verified_at = now
                event_name = "tool.receipt_verified"
                payload = {
                    "tool_name": operation.tool_name,
                    "effect_class": operation.effect_class,
                    "status": "succeeded",
                    "receipt_verified": True,
                }
            elif status == "reconciliation_required":
                event_name = "tool.reconciliation_required"
                payload = {
                    "tool_name": operation.tool_name,
                    "effect_class": operation.effect_class,
                    "status": status,
                    "error_code": safe_error_code,
                }
            else:
                event_name = "tool.failed"
                payload = {
                    "tool_name": operation.tool_name,
                    "effect_class": operation.effect_class,
                    "status": status,
                    "error_code": safe_error_code,
                }
            self._append_event(run, context.attempt_id, event_name, payload)
            self.db.commit()

    def reconcile_tool_operation(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
        grace_seconds: int = 90,
    ) -> ToolOperationReconciliation:
        """Resolve one uncertain write without persisting health content."""
        normalized_operation_id = _bounded(
            operation_id,
            field="operation_id",
            limit=96,
        )
        if type(grace_seconds) is not int or not 0 <= grace_seconds <= 3600:
            raise ValueError("invalid_reconciliation_grace_seconds")
        operation = self.db.query(AgentToolOperation).filter(
            AgentToolOperation.operation_id == normalized_operation_id,
        ).first()
        if operation is None:
            raise AgentRuntimeError("tool_operation_not_found")
        run = self.db.query(AgentRun).filter(
            AgentRun.run_id == operation.run_id,
        ).first()
        if run is None:
            raise AgentRuntimeError("run_not_found")
        context = self._context(run)

        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            query = self.db.query(AgentToolOperation).filter(
                AgentToolOperation.operation_id == normalized_operation_id,
                AgentToolOperation.run_id == run.run_id,
            )
            if self.db.get_bind().dialect.name == "postgresql":
                query = query.with_for_update()
            operation = query.first()
            if operation is None:
                raise AgentRuntimeError("tool_operation_not_found")

            if operation.status == "succeeded":
                return ToolOperationReconciliation(
                    operation_id=operation.operation_id,
                    disposition="verified_effect",
                    reason_code="reconciled_effect_verified",
                    resource_type=operation.resource_type,
                    resource_id=operation.resource_id,
                )
            if (
                operation.status == "failed"
                and operation.error_code == "reconciled_no_effect"
            ):
                return ToolOperationReconciliation(
                    operation_id=operation.operation_id,
                    disposition="verified_no_effect",
                    reason_code="reconciled_no_effect",
                    resource_type=operation.resource_type,
                )
            if operation.status != "reconciliation_required":
                raise AgentRuntimeError("tool_operation_not_reconcilable")
            if run.status != "reconciliation_required":
                raise AgentRuntimeError("run_not_reconcilable")

            from app.services.agent_operation_reconciliation import (
                resolve_tool_operation,
            )

            decision = resolve_tool_operation(
                self.db,
                run=run,
                operation=operation,
                now=now or _now(),
                grace_seconds=grace_seconds,
            )
            result = ToolOperationReconciliation(
                operation_id=operation.operation_id,
                disposition=decision.disposition,
                reason_code=decision.reason_code,
                resource_type=decision.resource_type,
                resource_id=decision.resource_id,
            )
            if decision.disposition == "unknown":
                return result

            settled_at = now or _now()
            operation.finished_at = settled_at
            if decision.disposition == "verified_effect":
                operation.status = "succeeded"
                operation.error_code = None
                operation.resource_type = decision.resource_type
                operation.resource_id = decision.resource_id
                operation.verified_at = settled_at
                self._append_event(
                    run,
                    attempt.attempt_id,
                    "tool.receipt_verified",
                    {
                        "tool_name": operation.tool_name,
                        "effect_class": operation.effect_class,
                        "status": "succeeded",
                        "receipt_verified": True,
                    },
                )
                run_error_code = "write_verified_reply_incomplete"
            else:
                operation.status = "failed"
                operation.error_code = "reconciled_no_effect"
                operation.resource_id = None
                operation.verified_at = None
                self._append_event(
                    run,
                    attempt.attempt_id,
                    "tool.failed",
                    {
                        "tool_name": operation.tool_name,
                        "effect_class": operation.effect_class,
                        "status": "failed",
                        "error_code": "reconciled_no_effect",
                    },
                )
                run_error_code = "reconciled_no_effect"

            self.db.flush()
            if not self._has_unresolved_write(run.run_id):
                self._apply_reconciled_retryable_locked(
                    run,
                    attempt,
                    error_code=run_error_code,
                    now=settled_at,
                )
            self.db.commit()
            return result

    def resolve_tool_operation_manually(
        self,
        operation_id: str,
        *,
        outcome: Literal["verified_effect", "verified_no_effect"],
        resource_type: str | None = None,
        resource_id: str | None = None,
        now: datetime | None = None,
    ) -> ToolOperationReconciliation:
        """Apply an operator-verified outcome to a legacy uncertain write."""
        if outcome not in {"verified_effect", "verified_no_effect"}:
            raise ValueError("invalid_reconciliation_outcome")
        normalized_operation_id = _bounded(
            operation_id,
            field="operation_id",
            limit=96,
        )
        normalized_resource_type = _bounded(
            resource_type,
            field="resource_type",
            limit=80,
        )
        normalized_resource_id = _bounded(
            resource_id,
            field="resource_id",
            limit=128,
        )
        if outcome == "verified_effect" and not (
            normalized_resource_type and normalized_resource_id
        ):
            raise AgentRuntimeError("verified_resource_required")
        if outcome == "verified_no_effect" and (
            normalized_resource_type or normalized_resource_id
        ):
            raise AgentRuntimeError("verified_resource_not_allowed")

        operation = self.db.query(AgentToolOperation).filter(
            AgentToolOperation.operation_id == normalized_operation_id,
        ).first()
        if operation is None:
            raise AgentRuntimeError("tool_operation_not_found")
        run = self.db.query(AgentRun).filter(
            AgentRun.run_id == operation.run_id,
        ).first()
        if run is None:
            raise AgentRuntimeError("run_not_found")
        context = self._context(run)

        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            query = self.db.query(AgentToolOperation).filter(
                AgentToolOperation.operation_id == normalized_operation_id,
                AgentToolOperation.run_id == run.run_id,
            )
            if self.db.get_bind().dialect.name == "postgresql":
                query = query.with_for_update()
            operation = query.first()
            if operation is None:
                raise AgentRuntimeError("tool_operation_not_found")
            if outcome == "verified_effect":
                from app.services.agent_kernel.tool_registry import (
                    is_registered_receipt_resource_type,
                    is_valid_receipt_resource_id,
                )
                from app.services.agent_operation_reconciliation import (
                    verify_resource_owner,
                )

                if not is_registered_receipt_resource_type(
                    operation.tool_name,
                    normalized_resource_type or "",
                ):
                    raise AgentRuntimeError("invalid_resource_type")
                if not is_valid_receipt_resource_id(
                    operation.tool_name,
                    normalized_resource_id or "",
                ):
                    raise AgentRuntimeError("invalid_resource_id")
                if (
                    operation.resource_type is not None
                    and operation.resource_type != normalized_resource_type
                ):
                    raise AgentRuntimeError("invalid_resource_type")
                if (
                    operation.resource_id is not None
                    and operation.resource_id != normalized_resource_id
                ):
                    raise AgentRuntimeError("invalid_resource_id")
                if not verify_resource_owner(
                    self.db,
                    run=run,
                    resource_type=normalized_resource_type or "",
                    resource_id=normalized_resource_id or "",
                ):
                    raise AgentRuntimeError("verified_resource_owner_mismatch")
            if outcome == "verified_effect" and operation.status == "succeeded":
                return ToolOperationReconciliation(
                    operation_id=operation.operation_id,
                    disposition="verified_effect",
                    reason_code="reconciled_effect_verified",
                    resource_type=operation.resource_type,
                    resource_id=operation.resource_id,
                )
            if (
                outcome == "verified_no_effect"
                and operation.status == "failed"
                and operation.error_code == "reconciled_no_effect"
            ):
                return ToolOperationReconciliation(
                    operation_id=operation.operation_id,
                    disposition="verified_no_effect",
                    reason_code="reconciled_no_effect",
                )
            if operation.status != "reconciliation_required":
                raise AgentRuntimeError("tool_operation_not_reconcilable")
            if run.status != "reconciliation_required":
                raise AgentRuntimeError("run_not_reconcilable")

            settled_at = now or _now()
            operation.finished_at = settled_at
            if outcome == "verified_effect":
                operation.status = "succeeded"
                operation.error_code = None
                operation.resource_type = normalized_resource_type
                operation.resource_id = normalized_resource_id
                operation.verified_at = settled_at
                self._append_event(
                    run,
                    attempt.attempt_id,
                    "tool.receipt_verified",
                    {
                        "tool_name": operation.tool_name,
                        "effect_class": operation.effect_class,
                        "status": "succeeded",
                        "receipt_verified": True,
                    },
                )
                run_error_code = "write_verified_reply_incomplete"
                reason_code = "reconciled_effect_verified"
            else:
                operation.status = "failed"
                operation.error_code = "reconciled_no_effect"
                operation.resource_id = None
                operation.verified_at = None
                self._append_event(
                    run,
                    attempt.attempt_id,
                    "tool.failed",
                    {
                        "tool_name": operation.tool_name,
                        "effect_class": operation.effect_class,
                        "status": "failed",
                        "error_code": "reconciled_no_effect",
                    },
                )
                run_error_code = "reconciled_no_effect"
                reason_code = "reconciled_no_effect"

            self.db.flush()
            if not self._has_unresolved_write(run.run_id):
                self._apply_reconciled_retryable_locked(
                    run,
                    attempt,
                    error_code=run_error_code,
                    now=settled_at,
                )
            self.db.commit()
            return ToolOperationReconciliation(
                operation_id=operation.operation_id,
                disposition=outcome,
                reason_code=reason_code,
                resource_type=(
                    normalized_resource_type
                    if outcome == "verified_effect"
                    else None
                ),
                resource_id=(
                    normalized_resource_id
                    if outcome == "verified_effect"
                    else None
                ),
            )

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
        return self.get_run_by_client_turn(user_id, client_turn_id)

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

    def _has_unresolved_write(self, run_id: str) -> bool:
        return self.db.query(AgentToolOperation.operation_id).filter(
            AgentToolOperation.run_id == run_id,
            AgentToolOperation.status.in_(
                {"requested", "executing", "reconciliation_required"}
            ),
        ).first() is not None

    def _has_verified_write(self, run_id: str) -> bool:
        return self.db.query(AgentToolOperation.operation_id).filter(
            AgentToolOperation.run_id == run_id,
            AgentToolOperation.status == "succeeded",
        ).first() is not None

    def _control_action(
        self,
        run: AgentRun,
        *,
        now: datetime,
    ) -> Literal["cancel_requested", "deadline_exceeded"] | None:
        if run.cancel_requested_at is not None:
            return "cancel_requested"
        if run.deadline_at is not None and self._at_or_after(now, run.deadline_at):
            return "deadline_exceeded"
        return None

    def _apply_control_stop_locked(
        self,
        run: AgentRun,
        attempt: AgentRunAttempt,
        *,
        action: Literal["cancel_requested", "deadline_exceeded"],
        now: datetime,
        preserve_verified_write: bool = True,
    ) -> None:
        unresolved = self.db.query(AgentToolOperation).filter(
            AgentToolOperation.run_id == run.run_id,
            AgentToolOperation.status.in_(
                {"requested", "executing", "reconciliation_required"}
            ),
        ).all()
        if unresolved:
            for operation in unresolved:
                if operation.status != "reconciliation_required":
                    operation.status = "reconciliation_required"
                    operation.error_code = (
                        "cancelled"
                        if action == "cancel_requested"
                        else "deadline_exceeded"
                    )
                    operation.finished_at = now
            self._apply_completion_locked(
                run,
                attempt,
                status="reconciliation_required",
                error_code=(
                    "cancelled_with_unresolved_write"
                    if action == "cancel_requested"
                    else "write_uncertain"
                ),
                retryable=False,
                now=now,
            )
            return
        if preserve_verified_write and self._has_verified_write(run.run_id):
            self._apply_completion_locked(
                run,
                attempt,
                status="succeeded",
                error_code=None,
                retryable=False,
                now=now,
            )
            return
        if action == "cancel_requested":
            self._apply_completion_locked(
                run,
                attempt,
                status="cancelled",
                error_code="cancelled",
                retryable=False,
                now=now,
            )
            return
        self._apply_completion_locked(
            run,
            attempt,
            status="failed",
            error_code="deadline_exceeded",
            retryable=True,
            now=now,
        )

    def _apply_completion_locked(
        self,
        run: AgentRun,
        attempt: AgentRunAttempt,
        *,
        status: str,
        error_code: str | None,
        retryable: bool,
        now: datetime,
    ) -> None:
        if status == "reconciliation_required":
            self._record_reconciliation_generation()
        self._transition(run, status)
        run.error_code = error_code
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
        attempt.lease_expires_at = None
        event_name = {
            "waiting_for_user": "run.waiting",
            "reconciliation_required": "run.reconciliation_required",
        }.get(status, f"run.{status}")
        payload = {"status": status}
        if run.error_code:
            payload["error_code"] = run.error_code
        self._append_event(run, attempt.attempt_id, event_name, payload)

    def _apply_reconciled_retryable_locked(
        self,
        run: AgentRun,
        attempt: AgentRunAttempt,
        *,
        error_code: str,
        now: datetime,
    ) -> None:
        """Leave terminal reconciliation in a retryable, audited state."""
        self._transition(run, "failed")
        run.error_code = error_code
        run.retryable = True
        run.finished_at = now
        attempt.status = "failed"
        attempt.error_code = error_code
        attempt.finished_at = now
        attempt.lease_expires_at = None
        self._append_event(
            run,
            attempt.attempt_id,
            "run.reconciled",
            {"status": "failed", "error_code": error_code},
        )

    def _apply_worker_interruption_locked(
        self,
        run: AgentRun,
        attempt: AgentRunAttempt,
        *,
        now: datetime,
    ) -> None:
        unresolved = self.db.query(AgentToolOperation).filter(
            AgentToolOperation.run_id == run.run_id,
            AgentToolOperation.status.in_(
                {"requested", "executing", "reconciliation_required"}
            ),
        ).all()
        if unresolved:
            for operation in unresolved:
                if operation.status != "reconciliation_required":
                    operation.status = "reconciliation_required"
                    operation.error_code = "worker_interrupted"
                    operation.finished_at = now
            self._apply_completion_locked(
                run,
                attempt,
                status="reconciliation_required",
                error_code="worker_interrupted_write",
                retryable=False,
                now=now,
            )
            return
        if self._has_verified_write(run.run_id):
            self._apply_completion_locked(
                run,
                attempt,
                status="succeeded",
                error_code=None,
                retryable=False,
                now=now,
            )
            return
        self._apply_completion_locked(
            run,
            attempt,
            status="failed",
            error_code="worker_interrupted",
            retryable=True,
            now=now,
        )

    def _settle_expired_write(
        self,
        context: RunContext,
        *,
        now: datetime,
    ) -> None:
        with self._lifecycle_lock(context):
            run, attempt = self._owned_run_and_attempt(context, lock=True)
            if run.status not in ACTIVE_RUN_STATUSES:
                return
            operations = self.db.query(AgentToolOperation).filter(
                AgentToolOperation.run_id == run.run_id,
                AgentToolOperation.status.in_(
                    {"requested", "executing", "reconciliation_required"}
                ),
            ).all()
            for operation in operations:
                if operation.status != "reconciliation_required":
                    operation.status = "reconciliation_required"
                    operation.error_code = "worker_lease_expired"
                    operation.finished_at = now
            self._apply_completion_locked(
                run,
                attempt,
                status="reconciliation_required",
                error_code="worker_lease_expired_write",
                retryable=False,
                now=now,
            )
            self.db.commit()

    def _record_reconciliation_generation(self) -> None:
        from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

        AgentRuntimeRolloutService(self.db).record_reconciliation()

    def _require_owned_conversation(self, user_id: int, conversation_id: int) -> None:
        exists = self.db.query(AgentConversation.id).filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        ).first()
        if exists is None:
            raise ConversationAccessError("conversation_not_found")

    @contextmanager
    def _lifecycle_lock(self, context: RunContext) -> Iterator[None]:
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            yield
            return
        if bind.dialect.name == "sqlite":
            with _sqlite_runtime_lock(bind):
                yield
            return
        lock_key = _runtime_lock_key(context.user_id, f"run:{context.run_id}")
        with _local_runtime_lock(lock_key):
            yield

    @contextmanager
    def _recovery_scan_lock(self) -> Iterator[None]:
        bind = self.db.get_bind()
        if bind.dialect.name == "sqlite":
            with _sqlite_runtime_lock(bind):
                yield
            return
        if bind.dialect.name == "postgresql":
            yield
            return
        with _local_runtime_lock(_runtime_lock_key(0, "recovery_scan")):
            yield

    @staticmethod
    def _safe_error_code(value: str | None) -> str | None:
        normalized = _bounded(value, field="error_code", limit=80)
        if normalized is not None and normalized not in _known_error_codes():
            return "unclassified_error"
        return normalized

    @staticmethod
    def _validate_lease_seconds(value: int) -> int:
        if type(value) is not int or not 5 <= value <= 900:
            raise ValueError("invalid_lease_seconds")
        return value

    @staticmethod
    def _validate_unleased_grace_seconds(value: int) -> int:
        if type(value) is not int or not 5 <= value <= 7200:
            raise ValueError("invalid_unleased_grace_seconds")
        return value

    @staticmethod
    def _at_or_after(left: datetime, right: datetime) -> bool:
        if left.tzinfo is None:
            left = left.replace(tzinfo=UTC)
        if right.tzinfo is None:
            right = right.replace(tzinfo=UTC)
        return left >= right

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
