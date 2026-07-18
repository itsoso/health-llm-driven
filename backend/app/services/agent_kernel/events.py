"""Privacy-preserving lifecycle events for XiaoBa Agent Kernel turns."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any, Optional

from app.services.agent_kernel.types import ToolExecutionRequest, TurnSnapshot


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentKernelEvent:
    name: str
    occurred_at: str
    run_id: str
    turn_id: str
    user_id: Optional[int]
    channel: str
    policy_mode: str
    data: dict[str, Any]


class AgentEventBus:
    """Emit compact structured logs without placing health content in telemetry."""

    def __init__(self, snapshot: TurnSnapshot):
        self.snapshot = snapshot
        self.events: list[AgentKernelEvent] = []

    def emit(self, name: str, **data: Any) -> AgentKernelEvent:
        context = self.snapshot.context
        event = AgentKernelEvent(
            name=name,
            occurred_at=datetime.now(UTC).isoformat(timespec="seconds"),
            run_id=context.run_id,
            turn_id=context.turn_id,
            user_id=context.user_id,
            channel=context.channel,
            policy_mode=self.snapshot.policy_mode,
            data=data,
        )
        self.events.append(event)
        logger.info(
            "[agent_kernel.event] name=%s run_id=%s turn_id=%s user=%s channel=%s policy=%s data=%s",
            event.name,
            event.run_id,
            event.turn_id,
            event.user_id,
            event.channel,
            event.policy_mode,
            event.data,
        )
        return event

    def turn_started(self) -> AgentKernelEvent:
        return self.emit("agent.turn_start")

    def intent_decided(self) -> AgentKernelEvent:
        intent = self.snapshot.intent
        return self.emit(
            "agent.intent_decided",
            primary=intent.primary,
            domain=intent.domain,
            operation=intent.operation,
            confidence=intent.confidence,
            ambiguity=list(intent.ambiguity),
        )

    def rebind_snapshot(self, snapshot: TurnSnapshot, *, reason: str) -> AgentKernelEvent:
        """Retain trace history while a deterministic continuation refines intent."""
        self.snapshot = snapshot
        intent = snapshot.intent
        return self.emit(
            "agent.intent_refined",
            primary=intent.primary,
            domain=intent.domain,
            operation=intent.operation,
            confidence=intent.confidence,
            reason=reason,
        )

    def tool_requested(self, request: ToolExecutionRequest) -> AgentKernelEvent:
        return self.emit(
            "agent.tool_requested",
            tool_name=request.tool_name,
            source=request.source,
        )

    def capability_decided(self, *, tool_name: str, action: str, reason: str) -> None:
        self.emit(
            "agent.capability_decided",
            tool_name=tool_name,
            action=action,
            reason=reason,
        )
        self.emit(
            "agent.tool_blocked" if action == "block" else "agent.tool_allowed",
            tool_name=tool_name,
            reason=reason,
        )

    def tool_result(
        self,
        *,
        tool_name: str,
        success: bool,
        receipt: Optional[dict[str, Any]] = None,
    ) -> None:
        self.emit("agent.tool_result", tool_name=tool_name, success=success)
        if receipt:
            self.emit(
                "agent.write_receipt_verified",
                tool_name=tool_name,
                operation_id=receipt.get("operation_id"),
                resource_id=receipt.get("resource_id"),
                executed_ref=receipt.get("executed_ref"),
            )

    def turn_ended(self, *, status: str) -> AgentKernelEvent:
        return self.emit("agent.turn_end", status=status)
