"""Content-free rollout policy and circuit for the cloud Agent Runtime."""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_runtime import (
    AgentRuntimeRolloutEvent,
    AgentRuntimeRolloutState,
    AgentRun,
    AgentRunAttempt,
    AgentToolOperation,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.agent_runtime import RunAdmission

VALID_RUNTIME_MODES = frozenset({"off", "canary", "enforce"})
VALID_ACTORS = frozenset({"system", "admin"})
VALID_REASON_CODES = frozenset(
    {
        "manual_pause",
        "manual_resume",
        "system_failure_rate",
        "reconciliation_detected",
        "stale_lease_detected",
    }
)


class RolloutConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeAdmissionDecision:
    managed: bool
    reason: str


@dataclass(frozen=True)
class RuntimeRunAdmission:
    admission: RunAdmission | None
    reason: str


@dataclass(frozen=True)
class RolloutTransition:
    changed: bool
    status: str
    reason_code: str | None


@dataclass(frozen=True)
class RuntimeIntegritySnapshot:
    window_runs: int
    contract_snapshot_runs: int
    contract_snapshot_coverage_percent: int
    contract_versions: dict[str, int]
    settled_message_linkage_gaps: int
    missing_current_attempt_runs: int
    active_over_deadline_runs: int
    waiting_over_24h_runs: int

    def to_dict(self) -> dict[str, object]:
        return {
            "window_runs": self.window_runs,
            "contract_snapshot_runs": self.contract_snapshot_runs,
            "contract_snapshot_coverage_percent": (
                self.contract_snapshot_coverage_percent
            ),
            "contract_versions": dict(self.contract_versions),
            "settled_message_linkage_gaps": self.settled_message_linkage_gaps,
            "missing_current_attempt_runs": self.missing_current_attempt_runs,
            "active_over_deadline_runs": self.active_over_deadline_runs,
            "waiting_over_24h_runs": self.waiting_over_24h_runs,
        }


@dataclass(frozen=True)
class RolloutSnapshot:
    window_started_at: datetime
    evaluated_at: datetime
    terminal_runs: int
    failed_runs: int
    reconciliation_runs: int
    stale_active_runs: int
    status_counts: dict[str, int]
    tool_status_counts: dict[str, int]
    duration_ms: dict[str, int | None]
    integrity: RuntimeIntegritySnapshot

    def to_dict(self) -> dict[str, object]:
        return {
            "window_started_at": self.window_started_at.isoformat(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "terminal_runs": self.terminal_runs,
            "failed_runs": self.failed_runs,
            "reconciliation_runs": self.reconciliation_runs,
            "stale_active_runs": self.stale_active_runs,
            "status_counts": dict(self.status_counts),
            "tool_status_counts": dict(self.tool_status_counts),
            "duration_ms": dict(self.duration_ms),
            "integrity": self.integrity.to_dict(),
        }


@dataclass(frozen=True)
class RolloutEvaluation:
    snapshot: RolloutSnapshot
    transition: RolloutTransition
    reason_code: str | None


def stable_canary_bucket(user_id: int) -> int:
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("user_id_must_be_positive")
    digest = hashlib.sha256(
        f"agent-runtime-canary-v1:{int(user_id)}".encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big") % 10_000


def runtime_mode() -> str:
    mode = str(getattr(settings, "agent_runtime_mode", "off") or "off").strip().lower()
    if mode not in VALID_RUNTIME_MODES:
        raise RolloutConfigurationError(f"invalid_runtime_mode:{mode}")
    return mode


def runtime_control_enabled() -> bool:
    return runtime_mode() in {"canary", "enforce"}


def rollout_public_configuration() -> dict[str, int | str]:
    return {
        "mode": runtime_mode(),
        "canary_percent": _canary_percent(),
        "allowlist_count": len(_canary_allowlist()),
        "window_minutes": AgentRuntimeRolloutService._window_minutes(None),
        "min_terminal_runs": _rollout_minimum_terminal_runs(),
        "failure_rate_percent": _rollout_failure_rate_percent(),
    }


def _canary_percent() -> int:
    value = int(getattr(settings, "agent_runtime_canary_percent", 0) or 0)
    if not 0 <= value <= 100:
        raise RolloutConfigurationError(f"invalid_canary_percent:{value}")
    return value


def _canary_allowlist() -> frozenset[int]:
    configured = str(
        getattr(settings, "agent_runtime_canary_user_ids", "") or ""
    ).strip()
    if not configured:
        return frozenset()
    parsed: set[int] = set()
    for token in configured.split(","):
        normalized = token.strip()
        if not normalized:
            continue
        if not normalized.isdigit() or int(normalized) <= 0:
            raise RolloutConfigurationError("invalid_canary_user_ids")
        parsed.add(int(normalized))
    return frozenset(parsed)


class AgentRuntimeRolloutService:
    def __init__(self, db: Session):
        self.db = db

    def admission_decision(self, user_id: int) -> RuntimeAdmissionDecision:
        selection = self._selection_decision(user_id)
        if not selection.managed:
            return selection

        try:
            state = self._get_or_create_state()
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.warning(
                "Agent Runtime circuit unavailable; bypassing managed admission: error=%s",
                type(exc).__name__,
            )
            return RuntimeAdmissionDecision(False, "circuit_unavailable")
        if state.status == "paused":
            return RuntimeAdmissionDecision(False, "circuit_paused")
        return selection

    def admit_run(
        self,
        *,
        run_id: str,
        attempt_id: str,
        user_id: int,
        conversation_id: int | None,
        client_turn_id: str | None,
        origin: str,
        deadline_at: datetime | None,
    ) -> RuntimeRunAdmission:
        """Linearize circuit admission with Run creation and preserve old Turns."""
        from app.services.agent_runtime import AgentRuntimeCoordinator

        coordinator = AgentRuntimeCoordinator(self.db)
        values = {
            "run_id": run_id,
            "attempt_id": attempt_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "client_turn_id": client_turn_id,
            "origin": origin,
            "deadline_at": deadline_at,
        }
        # `off` is the hard rollback switch. Validate it before consulting old
        # Run identity so an invalid mode cannot be hidden by a duplicate Turn.
        if runtime_mode() == "off":
            return RuntimeRunAdmission(None, "mode_off")
        if self._managed_client_turn_exists(user_id, client_turn_id):
            return RuntimeRunAdmission(
                coordinator.create_or_resume_run(**values),
                "existing_managed_turn",
            )

        selection = self._selection_decision(user_id)
        if not selection.managed:
            return RuntimeRunAdmission(None, selection.reason)

        try:
            state = self._locked_state()
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.warning(
                "Agent Runtime circuit unavailable; bypassing managed admission: error=%s",
                type(exc).__name__,
            )
            return RuntimeRunAdmission(None, "circuit_unavailable")

        # A same-Turn request may have committed while this request waited for the
        # circuit row. Existing managed identity always wins over a later pause.
        if self._managed_client_turn_exists(user_id, client_turn_id):
            return RuntimeRunAdmission(
                coordinator.create_or_resume_run(**values),
                "existing_managed_turn",
            )
        if state.status == "paused":
            self.db.commit()
            return RuntimeRunAdmission(None, "circuit_paused")

        # create_or_resume_run commits the Run in the same transaction, releasing
        # the circuit row lock only after admission is durable.
        return RuntimeRunAdmission(
            coordinator.create_or_resume_run(**values),
            selection.reason,
        )

    def get_state(self) -> AgentRuntimeRolloutState:
        state = self._get_or_create_state()
        self.db.commit()
        return state

    def snapshot(
        self,
        *,
        now: datetime | None = None,
        window_minutes: int | None = None,
    ) -> RolloutSnapshot:
        evaluated_at = now or datetime.now(UTC)
        window = self._window_minutes(window_minutes)
        window_started_at = evaluated_at - timedelta(minutes=window)
        terminal_statuses = {
            "succeeded",
            "failed",
            "cancelled",
            "reconciliation_required",
        }
        status_rows = (
            self.db.query(AgentRun.status, func.count(AgentRun.run_id))
            .filter(
                AgentRun.finished_at.is_not(None),
                AgentRun.finished_at >= window_started_at,
                AgentRun.finished_at <= evaluated_at,
                AgentRun.status.in_(terminal_statuses),
            )
            .group_by(AgentRun.status)
            .all()
        )
        status_counts = {str(status): int(count) for status, count in status_rows}
        terminal_runs = sum(status_counts.values())
        failed_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(
                AgentRun.finished_at.is_not(None),
                AgentRun.finished_at >= window_started_at,
                AgentRun.finished_at <= evaluated_at,
                AgentRun.status == "failed",
                or_(
                    AgentRun.error_code.is_(None),
                    AgentRun.error_code.notin_(
                        {"cancelled", "user_cancelled", "deadline_exceeded"}
                    ),
                ),
            )
            .scalar()
            or 0
        )
        reconciliation_runs = status_counts.get("reconciliation_required", 0)
        stale_active_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .join(
                AgentRunAttempt,
                AgentRunAttempt.attempt_id == AgentRun.current_attempt_id,
            )
            .filter(
                AgentRun.status.in_({"queued", "running"}),
                AgentRunAttempt.status == "running",
                AgentRunAttempt.lease_expires_at.is_not(None),
                AgentRunAttempt.lease_expires_at < evaluated_at,
            )
            .scalar()
            or 0
        )
        tool_rows = (
            self.db.query(
                AgentToolOperation.status,
                func.count(AgentToolOperation.operation_id),
            )
            .filter(
                AgentToolOperation.created_at >= window_started_at,
                AgentToolOperation.created_at <= evaluated_at,
            )
            .group_by(AgentToolOperation.status)
            .all()
        )
        tool_status_counts = {
            str(status): int(count) for status, count in tool_rows
        }
        duration_rows = (
            self.db.query(AgentRun.started_at, AgentRun.finished_at)
            .filter(
                AgentRun.finished_at.is_not(None),
                AgentRun.finished_at >= window_started_at,
                AgentRun.finished_at <= evaluated_at,
                AgentRun.started_at.is_not(None),
                AgentRun.status.in_(terminal_statuses),
            )
            .order_by(AgentRun.finished_at.desc())
            .limit(5_000)
            .all()
        )
        durations = sorted(
            max(0, int((finished_at - started_at).total_seconds() * 1000))
            for started_at, finished_at in duration_rows
        )
        integrity = self._integrity_snapshot(
            window_started_at=window_started_at,
            evaluated_at=evaluated_at,
        )
        return RolloutSnapshot(
            window_started_at=window_started_at,
            evaluated_at=evaluated_at,
            terminal_runs=terminal_runs,
            failed_runs=failed_runs,
            reconciliation_runs=reconciliation_runs,
            stale_active_runs=stale_active_runs,
            status_counts=status_counts,
            tool_status_counts=tool_status_counts,
            duration_ms={
                "p50": self._percentile(durations, 0.50),
                "p95": self._percentile(durations, 0.95),
            },
            integrity=integrity,
        )

    def _integrity_snapshot(
        self,
        *,
        window_started_at: datetime,
        evaluated_at: datetime,
    ) -> RuntimeIntegritySnapshot:
        window_filter = (
            AgentRun.created_at >= window_started_at,
            AgentRun.created_at <= evaluated_at,
        )
        window_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(*window_filter)
            .scalar()
            or 0
        )
        contract_snapshot_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(
                *window_filter,
                AgentRun.runtime_contract_version.is_not(None),
                AgentRun.tool_registry_digest.is_not(None),
                AgentRun.capability_policy_digest.is_not(None),
            )
            .scalar()
            or 0
        )
        coverage = (
            100
            if window_runs == 0
            else round(contract_snapshot_runs * 100 / window_runs)
        )
        version_rows = (
            self.db.query(
                AgentRun.runtime_contract_version,
                func.count(AgentRun.run_id),
            )
            .filter(
                *window_filter,
                AgentRun.runtime_contract_version.is_not(None),
            )
            .group_by(AgentRun.runtime_contract_version)
            .order_by(func.count(AgentRun.run_id).desc())
            .limit(8)
            .all()
        )
        contract_versions = {
            str(version): int(count) for version, count in version_rows
        }
        settled_message_linkage_gaps = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(
                *window_filter,
                AgentRun.conversation_id.is_not(None),
                AgentRun.status.in_({"succeeded", "waiting_for_user"}),
                or_(
                    AgentRun.source_message_id.is_(None),
                    AgentRun.assistant_message_id.is_(None),
                ),
            )
            .scalar()
            or 0
        )
        missing_current_attempt_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .outerjoin(
                AgentRunAttempt,
                AgentRunAttempt.attempt_id == AgentRun.current_attempt_id,
            )
            .filter(*window_filter, AgentRunAttempt.attempt_id.is_(None))
            .scalar()
            or 0
        )
        active_over_deadline_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(
                AgentRun.status.in_({"queued", "running"}),
                AgentRun.deadline_at.is_not(None),
                AgentRun.deadline_at < evaluated_at,
            )
            .scalar()
            or 0
        )
        waiting_over_24h_runs = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(
                AgentRun.status == "waiting_for_user",
                AgentRun.created_at < evaluated_at - timedelta(hours=24),
            )
            .scalar()
            or 0
        )
        return RuntimeIntegritySnapshot(
            window_runs=window_runs,
            contract_snapshot_runs=contract_snapshot_runs,
            contract_snapshot_coverage_percent=coverage,
            contract_versions=contract_versions,
            settled_message_linkage_gaps=settled_message_linkage_gaps,
            missing_current_attempt_runs=missing_current_attempt_runs,
            active_over_deadline_runs=active_over_deadline_runs,
            waiting_over_24h_runs=waiting_over_24h_runs,
        )

    def evaluate_and_maybe_pause(
        self,
        *,
        now: datetime | None = None,
    ) -> RolloutEvaluation:
        evaluated_at = now or datetime.now(UTC)
        state = self._locked_state()
        snapshot = self.snapshot(now=evaluated_at)
        new_reconciliation_runs = max(
            0,
            int(state.reconciliation_generation)
            - int(state.reconciliation_acknowledged_generation),
        )
        state.window_started_at = snapshot.window_started_at
        state.last_evaluated_at = snapshot.evaluated_at
        self._copy_counts(
            state,
            snapshot.terminal_runs,
            snapshot.failed_runs,
            snapshot.reconciliation_runs,
            snapshot.stale_active_runs,
        )

        reason_code = self._pause_reason(
            snapshot,
            new_reconciliation_runs=new_reconciliation_runs,
        )
        if reason_code is None or state.status == "paused":
            self.db.commit()
            return RolloutEvaluation(
                snapshot=snapshot,
                transition=RolloutTransition(
                    changed=False,
                    status=state.status,
                    reason_code=state.reason_code,
                ),
                reason_code=reason_code,
            )
        transition = self.pause(
            actor_kind="system",
            reason_code=reason_code,
            terminal_runs=snapshot.terminal_runs,
            failed_runs=snapshot.failed_runs,
            reconciliation_runs=snapshot.reconciliation_runs,
            stale_active_runs=snapshot.stale_active_runs,
        )
        return RolloutEvaluation(snapshot, transition, reason_code)

    def pause(
        self,
        *,
        actor_kind: str,
        reason_code: str,
        actor_user_id: int | None = None,
        terminal_runs: int = 0,
        failed_runs: int = 0,
        reconciliation_runs: int = 0,
        stale_active_runs: int = 0,
    ) -> RolloutTransition:
        self._validate_transition(actor_kind, reason_code, actor_user_id)
        self._validate_pause(actor_kind, reason_code)
        state = self._locked_state()
        if state.status == "paused":
            self.db.commit()
            return RolloutTransition(False, state.status, state.reason_code)
        state.status = "paused"
        state.reason_code = reason_code
        state.version += 1
        state.updated_by_user_id = actor_user_id
        if actor_kind == "system":
            self._copy_counts(
                state,
                terminal_runs,
                failed_runs,
                reconciliation_runs,
                stale_active_runs,
            )
        self.db.add(
            AgentRuntimeRolloutEvent(
                action="pause",
                actor_kind=actor_kind,
                reason_code=reason_code,
                actor_user_id=actor_user_id,
                terminal_runs=terminal_runs,
                failed_runs=failed_runs,
                reconciliation_runs=reconciliation_runs,
                stale_active_runs=stale_active_runs,
            )
        )
        self.db.commit()
        logger.warning(
            "Agent Runtime rollout paused: actor=%s reason=%s "
            "terminal=%s failed=%s reconciliation=%s stale=%s",
            actor_kind,
            reason_code,
            terminal_runs,
            failed_runs,
            reconciliation_runs,
            stale_active_runs,
        )
        return RolloutTransition(True, state.status, state.reason_code)

    def resume(
        self,
        *,
        actor_user_id: int,
    ) -> RolloutTransition:
        self._validate_transition("admin", "manual_resume", actor_user_id)
        state = self._locked_state()
        if state.status == "active":
            self.db.commit()
            return RolloutTransition(False, state.status, state.reason_code)
        state.status = "active"
        state.reason_code = None
        state.version += 1
        state.updated_by_user_id = actor_user_id
        state.reconciliation_acknowledged_generation = (
            state.reconciliation_generation
        )
        self.db.add(
            AgentRuntimeRolloutEvent(
                action="resume",
                actor_kind="admin",
                reason_code="manual_resume",
                actor_user_id=actor_user_id,
            )
        )
        self.db.commit()
        logger.info("Agent Runtime rollout resumed by administrator")
        return RolloutTransition(True, state.status, state.reason_code)

    def record_reconciliation(self) -> int:
        """Advance the durable generation in the caller's transaction.

        Run settlement and manual resume lock the same singleton row. This makes
        acknowledgment follow database commit ordering rather than an application
        timestamp that may have been created before a transaction became visible.
        """
        state = self._locked_state()
        state.reconciliation_generation += 1
        self.db.flush()
        return int(state.reconciliation_generation)

    def _get_or_create_state(self) -> AgentRuntimeRolloutState:
        state = self.db.query(AgentRuntimeRolloutState).filter(
            AgentRuntimeRolloutState.id == 1
        ).first()
        if state is not None:
            return state
        self._ensure_state()
        self.db.flush()
        return self.db.query(AgentRuntimeRolloutState).filter(
            AgentRuntimeRolloutState.id == 1
        ).one()

    def _locked_state(self) -> AgentRuntimeRolloutState:
        state = (
            self.db.query(AgentRuntimeRolloutState)
            .filter(AgentRuntimeRolloutState.id == 1)
            .with_for_update()
            .first()
        )
        if state is not None:
            return state
        self._ensure_state()
        self.db.flush()
        return (
            self.db.query(AgentRuntimeRolloutState)
            .filter(AgentRuntimeRolloutState.id == 1)
            .with_for_update()
            .one()
        )

    def _ensure_state(self) -> None:
        reconciliation_generation = int(
            self.db.query(func.count(AgentRun.run_id))
            .filter(AgentRun.status == "reconciliation_required")
            .scalar()
            or 0
        )
        values = {
            "id": 1,
            "status": "active",
            "version": 1,
            "terminal_runs": 0,
            "failed_runs": 0,
            "reconciliation_runs": 0,
            "stale_active_runs": 0,
            "reconciliation_generation": reconciliation_generation,
            "reconciliation_acknowledged_generation": 0,
        }
        dialect = self.db.get_bind().dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise RolloutConfigurationError(
                f"unsupported_rollout_database:{dialect}"
            )
        statement = insert(AgentRuntimeRolloutState).values(**values)
        self.db.execute(
            statement.on_conflict_do_nothing(index_elements=["id"])
        )

    def _managed_client_turn_exists(
        self,
        user_id: int,
        client_turn_id: str | None,
    ) -> bool:
        if not client_turn_id:
            return False
        return (
            self.db.query(AgentRun.run_id)
            .filter(
                AgentRun.user_id == int(user_id),
                AgentRun.client_turn_id == client_turn_id,
            )
            .first()
            is not None
        )

    @staticmethod
    def _selection_decision(user_id: int) -> RuntimeAdmissionDecision:
        mode = runtime_mode()
        if mode == "off":
            return RuntimeAdmissionDecision(False, "mode_off")
        if mode == "enforce":
            return RuntimeAdmissionDecision(True, "mode_enforce")

        allowlist = _canary_allowlist()
        percent = _canary_percent()
        if int(user_id) in allowlist:
            return RuntimeAdmissionDecision(True, "canary_allowlist")
        if stable_canary_bucket(user_id) < percent * 100:
            return RuntimeAdmissionDecision(True, "canary_bucket")
        return RuntimeAdmissionDecision(False, "canary_not_selected")

    @staticmethod
    def _validate_transition(
        actor_kind: str,
        reason_code: str,
        actor_user_id: int | None,
    ) -> None:
        if actor_kind not in VALID_ACTORS:
            raise ValueError("invalid_rollout_actor")
        if reason_code not in VALID_REASON_CODES:
            raise ValueError("invalid_rollout_reason")
        if actor_kind == "admin" and (
            actor_user_id is None or int(actor_user_id) <= 0
        ):
            raise ValueError("admin_actor_user_id_required")
        if actor_kind == "system" and actor_user_id is not None:
            raise ValueError("system_actor_must_not_have_user_id")

    @staticmethod
    def _validate_pause(actor_kind: str, reason_code: str) -> None:
        if actor_kind == "admin" and reason_code != "manual_pause":
            raise ValueError("invalid_pause_reason")
        if actor_kind == "system" and reason_code not in {
            "system_failure_rate",
            "reconciliation_detected",
            "stale_lease_detected",
        }:
            raise ValueError("invalid_pause_reason")

    @staticmethod
    def _copy_counts(
        state: AgentRuntimeRolloutState,
        terminal_runs: int,
        failed_runs: int,
        reconciliation_runs: int,
        stale_active_runs: int,
    ) -> None:
        values: Iterable[int] = (
            terminal_runs,
            failed_runs,
            reconciliation_runs,
            stale_active_runs,
        )
        if any(isinstance(value, bool) or int(value) < 0 for value in values):
            raise ValueError("rollout_counts_must_be_non_negative")
        state.terminal_runs = int(terminal_runs)
        state.failed_runs = int(failed_runs)
        state.reconciliation_runs = int(reconciliation_runs)
        state.stale_active_runs = int(stale_active_runs)

    @staticmethod
    def _window_minutes(override: int | None) -> int:
        configured = (
            override
            if override is not None
            else getattr(settings, "agent_runtime_rollout_window_minutes", 15)
        )
        value = int(15 if configured is None else configured)
        if not 1 <= value <= 1_440:
            raise RolloutConfigurationError("invalid_rollout_window_minutes")
        return value

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int | None:
        if not values:
            return None
        index = max(0, math.ceil(percentile * len(values)) - 1)
        return int(values[index])

    @staticmethod
    def _pause_reason(
        snapshot: RolloutSnapshot,
        *,
        new_reconciliation_runs: int,
    ) -> str | None:
        if new_reconciliation_runs > 0:
            return "reconciliation_detected"
        if snapshot.stale_active_runs > 0:
            return "stale_lease_detected"
        minimum = _rollout_minimum_terminal_runs()
        threshold = _rollout_failure_rate_percent()
        if snapshot.terminal_runs < minimum:
            return None
        if snapshot.failed_runs * 100 >= snapshot.terminal_runs * threshold:
            return "system_failure_rate"
        return None


def _rollout_minimum_terminal_runs() -> int:
    configured = getattr(settings, "agent_runtime_rollout_min_terminal_runs", 20)
    value = int(20 if configured is None else configured)
    if not 1 <= value <= 100_000:
        raise RolloutConfigurationError("invalid_rollout_min_terminal_runs")
    return value


def _rollout_failure_rate_percent() -> int:
    configured = getattr(settings, "agent_runtime_rollout_failure_rate_percent", 10)
    value = int(10 if configured is None else configured)
    if not 1 <= value <= 100:
        raise RolloutConfigurationError("invalid_rollout_failure_rate_percent")
    return value
