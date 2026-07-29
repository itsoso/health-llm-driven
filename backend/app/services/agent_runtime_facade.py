"""Unified cloud entrypoint for one durable Agent Runtime turn.

This module owns only control-plane lifecycle. It never stores prompt, response,
tool arguments, or health values in the Runtime ledger.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.services.agent_runtime import (
    AgentRuntimeCoordinator,
    RunContext,
    runtime_write_block_reason,
)
from app.services.agent_runtime_rollout import (
    AgentRuntimeRolloutService,
    runtime_mode,
)
from app.services.agent_runtime_lease import (
    start_agent_runtime_heartbeat,
    stop_agent_runtime_heartbeat,
)

logger = logging.getLogger(__name__)
_CHANNEL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class RuntimeExecutionInProgress(RuntimeError):
    pass


class RuntimeReplayUnavailable(RuntimeError):
    pass


class RuntimeExecutorDidNotFinish(RuntimeError):
    pass


def get_or_create_channel_conversation(
    db: Session,
    *,
    user_id: int,
    channel: str,
    title: str,
) -> int:
    """Return one durable first-party Agent conversation per user/channel."""
    normalized_channel = str(channel or "").strip().lower()
    if not _CHANNEL_NAME_RE.fullmatch(normalized_channel):
        raise ValueError("invalid_agent_channel")

    from app.models.agent_conversation import AgentConversation
    from app.models.user import User

    session_key = f"external-{normalized_channel}-{user_id}"
    # Serialize first-conversation creation across API workers. Without this row
    # lock, two simultaneous first messages could create separate histories and
    # defeat conversation-level Runtime ordering.
    user_exists = (
        db.query(User.id)
        .filter(User.id == user_id)
        .with_for_update()
        .one_or_none()
    )
    if user_exists is None:
        raise ValueError("agent_channel_user_not_found")
    conversation = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user_id,
            AgentConversation.session_key == session_key,
        )
        .order_by(AgentConversation.id.asc())
        .first()
    )
    if conversation is None:
        conversation = AgentConversation(
            user_id=user_id,
            title=title[:200],
            session_key=session_key,
        )
        db.add(conversation)
        try:
            db.commit()
            db.refresh(conversation)
        except IntegrityError:
            db.rollback()
            conversation = (
                db.query(AgentConversation)
                .filter(
                    AgentConversation.user_id == user_id,
                    AgentConversation.session_key == session_key,
                )
                .one()
            )
    return conversation.id


def admit_agent_runtime(
    db: Session,
    *,
    run_id: str,
    attempt_id: str,
    user_id: int,
    conversation_id: int | None,
    client_turn_id: str | None,
    origin: str,
) -> tuple[RunContext, bool, str]:
    """Return canonical identity, lifecycle ownership, and disposition."""
    if runtime_mode() == "off":
        return (
            RunContext(
                run_id=run_id,
                attempt_id=attempt_id,
                user_id=user_id,
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                input_seq=None,
                origin=origin,
                control_reason="mode_off",
            ),
            False,
            "execute",
        )
    deadline_seconds = int(
        getattr(settings, "agent_runtime_deadline_seconds", 300) or 300
    )
    if not 30 <= deadline_seconds <= 3_600:
        raise RuntimeError("invalid_agent_runtime_deadline_seconds")
    managed = AgentRuntimeRolloutService(db).admit_run(
        run_id=run_id,
        attempt_id=attempt_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_turn_id=client_turn_id,
        origin=origin,
        deadline_at=datetime.now(UTC) + timedelta(seconds=deadline_seconds),
    )
    admission = managed.admission
    if admission is None:
        return (
            RunContext(
                run_id=run_id,
                attempt_id=attempt_id,
                user_id=user_id,
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                input_seq=None,
                origin=origin,
                control_reason=managed.reason,
            ),
            False,
            "execute",
        )
    return (
        RunContext(
            run_id=admission.context.run_id,
            attempt_id=admission.context.attempt_id,
            user_id=admission.context.user_id,
            conversation_id=admission.context.conversation_id,
            client_turn_id=admission.context.client_turn_id,
            input_seq=admission.context.input_seq,
            origin=admission.context.origin,
            origin_device_id=admission.context.origin_device_id,
            local_execution_id=admission.context.local_execution_id,
            privacy_mode=admission.context.privacy_mode,
            control_reason=managed.reason,
        ),
        admission.owns_execution,
        admission.disposition,
    )


class CloudAgentRuntimeFacade:
    """Execute first-party cloud channels through one Runtime lifecycle."""

    def __init__(
        self,
        db: Session,
        *,
        executor_factory: Callable[[Session], Any] | None = None,
    ):
        self.db = db
        self._executor_factory = executor_factory

    async def run_stream(
        self,
        *,
        user_id: int,
        message: str,
        origin: str,
        conversation_id: int | None = None,
        client_turn_id: str | None = None,
        **executor_kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = f"run_{uuid.uuid4().hex[:24]}"
        attempt_id = f"attempt_{uuid.uuid4().hex[:24]}"
        context, managed, disposition = admit_agent_runtime(
            self.db,
            run_id=run_id,
            attempt_id=attempt_id,
            user_id=user_id,
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            origin=origin,
        )
        if disposition == "observe":
            raise RuntimeExecutionInProgress("runtime_execution_in_progress")
        if disposition == "replay":
            replay = self._replay_events(context)
            if replay is None:
                raise RuntimeReplayUnavailable("runtime_replay_unavailable")
            for event in replay:
                yield event
            return

        runtime = AgentRuntimeCoordinator(self.db) if managed else None
        source_message_id: int | None = None
        done_seen = False
        heartbeat_task: asyncio.Task | None = None
        if runtime is not None:
            lease_seconds = int(
                getattr(settings, "agent_runtime_lease_seconds", 90) or 90
            )
            lease_started = time.monotonic()
            runtime.mark_running(
                context,
                worker_id=context.attempt_id,
                lease_seconds=lease_seconds,
            )
            heartbeat_task = start_agent_runtime_heartbeat(
                context=context,
                managed=True,
                worker_id=context.attempt_id,
                initial_lease_deadline=lease_started + lease_seconds,
            )

        executor = self._make_executor()
        try:
            async for event in executor.run_stream(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                run_id=context.run_id if managed else None,
                attempt_id=context.attempt_id if managed else None,
                runtime_managed=managed,
                runtime_write_block_reason=runtime_write_block_reason(context),
                **executor_kwargs,
            ):
                normalized = self._attach_identity(event, context) if managed else event
                data = normalized.get("data")
                if (
                    runtime is not None
                    and normalized.get("event") == "request_persisted"
                    and isinstance(data, dict)
                    and isinstance(data.get("user_message_id"), int)
                ):
                    source_message_id = data["user_message_id"]
                    if isinstance(data.get("conversation_id"), int):
                        runtime.bind_messages(
                            context,
                            conversation_id=data["conversation_id"],
                            source_message_id=source_message_id,
                            assistant_message_id=None,
                        )
                if (
                    runtime is not None
                    and normalized.get("event") == "done"
                    and isinstance(data, dict)
                ):
                    runtime.finalize_executor_done(
                        context,
                        data,
                        source_message_id=source_message_id,
                    )
                    done_seen = True
                elif normalized.get("event") == "done":
                    done_seen = True
                yield normalized
            if not done_seen:
                if runtime is not None:
                    runtime.complete(
                        context,
                        status="failed",
                        error_code="executor_missing_done",
                        retryable=True,
                    )
                raise RuntimeExecutorDidNotFinish("executor_missing_done")
        except asyncio.CancelledError:
            if runtime is not None:
                runtime.interrupt_active(context)
            raise
        except Exception:
            if runtime is not None:
                run = runtime.get_run(context.user_id, context.run_id)
                if run.status in {"queued", "running"}:
                    runtime.complete(
                        context,
                        status="failed",
                        error_code="executor_exception",
                        retryable=True,
                    )
            raise
        finally:
            if heartbeat_task is not None:
                await stop_agent_runtime_heartbeat(
                    heartbeat_task,
                    run_id=context.run_id,
                )

    async def execute_tool(
        self,
        *,
        user_id: int,
        message: str,
        origin: str,
        channel: str,
        tool_name: str,
        arguments: dict[str, Any],
        user_auth_token: str | None = None,
        client_turn_id: str | None = None,
        run_id: str | None = None,
        executor: Any | None = None,
        source: str = "runtime_facade",
    ) -> str:
        """Execute one policy-checked tool with durable write idempotency."""
        canonical_run_id = run_id or f"run_{uuid.uuid4().hex[:24]}"
        attempt_id = f"attempt_{uuid.uuid4().hex[:24]}"
        context, managed, disposition = admit_agent_runtime(
            self.db,
            run_id=canonical_run_id,
            attempt_id=attempt_id,
            user_id=user_id,
            conversation_id=None,
            client_turn_id=client_turn_id,
            origin=origin,
        )
        if disposition == "observe":
            return self._structured_tool_status(
                "uncertain",
                "duplicate_in_flight",
                dispatch_started=None,
            )
        if disposition == "replay":
            return self._replay_tool_result(context)
        write_block_reason = runtime_write_block_reason(context)
        if write_block_reason:
            from app.services.agent_kernel.tool_registry import classify_tool_effect

            try:
                effect = classify_tool_effect(tool_name, arguments)
            except Exception:
                logger.exception(
                    "Runtime control unavailable and tool effect classification failed: "
                    "tool=%s reason=%s",
                    tool_name,
                    write_block_reason,
                )
                return self._structured_tool_status(
                    "failed",
                    "runtime_control_unavailable",
                    dispatch_started=False,
                )
            if effect == "write":
                logger.warning(
                    "Runtime control unavailable; blocked write before dispatch: "
                    "tool=%s reason=%s",
                    tool_name,
                    write_block_reason,
                )
                return self._structured_tool_status(
                    "failed",
                    "runtime_control_unavailable",
                    dispatch_started=False,
                )

        runtime = AgentRuntimeCoordinator(self.db) if managed else None
        heartbeat_task: asyncio.Task | None = None
        if runtime is not None:
            lease_seconds = int(
                getattr(settings, "agent_runtime_lease_seconds", 90) or 90
            )
            lease_started = time.monotonic()
            runtime.mark_running(
                context,
                worker_id=context.attempt_id,
                lease_seconds=lease_seconds,
            )
            heartbeat_task = start_agent_runtime_heartbeat(
                context=context,
                managed=True,
                worker_id=context.attempt_id,
                initial_lease_deadline=lease_started + lease_seconds,
            )
        active_executor = executor or self._make_executor()
        active_executor._runtime_run_id = context.run_id if managed else None
        active_executor._runtime_attempt_id = (
            context.attempt_id if managed else None
        )
        active_executor._runtime_managed = managed
        active_executor._runtime_write_block_reason = write_block_reason
        active_executor._current_user_id = user_id
        active_executor._current_turn_user_message = message
        active_executor._turn_channel = channel
        if getattr(active_executor, "_agent_kernel_snapshot", None) is None:
            active_executor._start_agent_kernel_turn(
                user_id=user_id,
                message=message,
                channel=channel,
                client_turn_id=client_turn_id,
                run_id=context.run_id if managed else None,
            )
        try:
            result = await active_executor._execute_tool(
                tool_name,
                arguments,
                user_auth_token,
                source=source,
            )
            if runtime is not None:
                self._settle_tool_run(
                    runtime,
                    context,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                )
            return result
        except asyncio.CancelledError:
            if runtime is not None:
                runtime.interrupt_active(context)
            raise
        except Exception:
            if runtime is not None:
                run = runtime.get_run(context.user_id, context.run_id)
                if run.status in {"queued", "running"}:
                    runtime.complete(
                        context,
                        status="failed",
                        error_code="executor_exception",
                        retryable=True,
                    )
            raise
        finally:
            if heartbeat_task is not None:
                await stop_agent_runtime_heartbeat(
                    heartbeat_task,
                    run_id=context.run_id,
                )

    def _make_executor(self):
        if self._executor_factory is not None:
            return self._executor_factory(self.db)
        from app.services.agent_executor import AgentExecutor

        return AgentExecutor(self.db)

    @staticmethod
    def _settle_tool_run(
        runtime: AgentRuntimeCoordinator,
        context: RunContext,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
    ) -> None:
        from app.services.agent_executor import _write_receipt_from_tool_result
        from app.services.agent_write_outcome import classify_write_execution

        if str(result).startswith("[NEEDS_CONFIRMATION]"):
            runtime.complete(
                context,
                status="waiting_for_user",
                error_code="confirmation_required",
            )
            return
        receipt = _write_receipt_from_tool_result(
            tool_name,
            arguments,
            result,
        )
        outcome = classify_write_execution(result, receipt=receipt)
        if outcome.status == "verified":
            runtime.complete(context, status="succeeded")
            return
        if outcome.status == "uncertain":
            runtime.complete(
                context,
                status="failed",
                error_code="write_uncertain",
                retryable=False,
            )
            return
        runtime.complete(
            context,
            status="failed",
            error_code="tool_rejected",
            retryable=False,
        )

    def _replay_tool_result(self, context: RunContext) -> str:
        from app.models.agent_runtime import AgentToolOperation

        run = AgentRuntimeCoordinator(self.db).get_run(
            context.user_id,
            context.run_id,
        )
        operation = (
            self.db.query(AgentToolOperation)
            .filter(AgentToolOperation.run_id == run.run_id)
            .order_by(AgentToolOperation.created_at.desc())
            .first()
        )
        if operation is not None and operation.status == "succeeded":
            import json

            return json.dumps({
                "status": "verified",
                "success": True,
                "operation_id": operation.operation_id,
                "resource_type": operation.resource_type,
                "resource_id": operation.resource_id,
                "replayed": True,
            }, ensure_ascii=False)
        if (
            operation is not None
            and operation.status == "reconciliation_required"
        ):
            return self._structured_tool_status(
                "uncertain",
                operation.error_code or "write_uncertain",
                dispatch_started=True,
            )
        if run.status == "waiting_for_user":
            return "[NEEDS_CONFIRMATION] 已识别这条记录，请确认后写入。"
        return self._structured_tool_status(
            "failed",
            run.error_code or "tool_failed",
            dispatch_started=False,
        )

    @staticmethod
    def _structured_tool_status(
        status: str,
        error_code: str,
        *,
        dispatch_started: bool | None,
    ) -> str:
        import json

        return json.dumps({
            "status": status,
            "success": False,
            "error_code": error_code,
            "dispatch_started": dispatch_started,
        }, ensure_ascii=False)

    @staticmethod
    def _attach_identity(
        event: dict[str, Any],
        context: RunContext,
    ) -> dict[str, Any]:
        if event.get("event") not in {"request_persisted", "done"}:
            return event
        data = event.setdefault("data", {})
        if isinstance(data, dict):
            data.setdefault("run_id", context.run_id)
            data.setdefault("attempt_id", context.attempt_id)
        return event

    def _replay_events(self, context: RunContext) -> list[dict[str, Any]] | None:
        from app.models.agent_conversation import AgentConversation, AgentMessage

        run = AgentRuntimeCoordinator(self.db).get_run(
            context.user_id,
            context.run_id,
        )
        if run.assistant_message_id is None:
            return None
        assistant = (
            self.db.query(AgentMessage)
            .join(
                AgentConversation,
                AgentConversation.id == AgentMessage.conversation_id,
            )
            .filter(
                AgentMessage.id == run.assistant_message_id,
                AgentConversation.user_id == context.user_id,
            )
            .first()
        )
        if assistant is None:
            return None
        source = None
        if run.source_message_id is not None:
            source = (
                self.db.query(AgentMessage)
                .join(
                    AgentConversation,
                    AgentConversation.id == AgentMessage.conversation_id,
                )
                .filter(
                    AgentMessage.id == run.source_message_id,
                    AgentConversation.user_id == context.user_id,
                )
                .first()
            )
        from app.services.health_evidence.delivery import (
            project_persisted_health_messages,
        )

        delivery = project_persisted_health_messages(
            (source, assistant) if source is not None else (assistant,)
        )[-1]
        events: list[dict[str, Any]] = []
        if source is not None:
            events.append({
                "event": "request_persisted",
                "data": {
                    "conversation_id": source.conversation_id,
                    "user_message_id": source.id,
                    "client_turn_id": context.client_turn_id,
                    "replayed": True,
                    "run_id": context.run_id,
                    "attempt_id": context.attempt_id,
                },
            })
        if delivery.content:
            events.append({
                "event": "token",
                "data": {"content": delivery.content},
            })
        done_data = delivery.meta
        done_data.update({
            "conversation_id": assistant.conversation_id,
            "message_id": assistant.id,
            "completion_status": (
                done_data.get("completion_status") or "complete"
            ),
            "client_turn_id": context.client_turn_id,
            "replayed": True,
            "run_id": context.run_id,
            "attempt_id": context.attempt_id,
        })
        events.append({"event": "done", "data": done_data})
        return events
