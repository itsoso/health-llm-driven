"""Typed contracts for XiaoBa Agent Kernel routing and tool policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BJ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class AgentEnvelope:
    """Surface-normalized user input before LLM/provider conversion."""

    user_id: Optional[int]
    channel: str
    text: str = ""
    media: tuple[dict[str, Any], ...] = ()
    source_message_id: Optional[str] = None
    client_capabilities: dict[str, Any] = field(default_factory=dict)
    client_time_context: dict[str, Any] = field(default_factory=dict)
    client_turn_id: Optional[str] = None


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable execution parameters for one turn."""

    current_time: datetime
    timezone: str
    user_id: Optional[int]
    channel: str
    run_id: str = ""
    turn_id: str = ""
    safety_level: str = "l3_health"
    autonomy_tier: str = "manual_confirm"

    @property
    def current_time_iso(self) -> str:
        return self.current_time.isoformat()

    @classmethod
    def now(
        cls,
        *,
        user_id: Optional[int],
        channel: str,
        timezone_name: str = "Asia/Shanghai",
        now_utc: Optional[datetime] = None,
        run_id: str = "",
        turn_id: str = "",
    ) -> "ExecutionContext":
        generated_utc = now_utc or datetime.now(timezone.utc)
        if generated_utc.tzinfo is None:
            generated_utc = generated_utc.replace(tzinfo=timezone.utc)
        try:
            user_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            user_timezone = BJ
            timezone_name = "Asia/Shanghai"
        return cls(
            current_time=generated_utc.astimezone(user_timezone),
            timezone=timezone_name,
            user_id=user_id,
            channel=channel,
            run_id=run_id,
            turn_id=turn_id,
        )

    @classmethod
    def for_test(
        cls,
        *,
        user_id: Optional[int],
        channel: str,
        timezone_name: str = "Asia/Shanghai",
        run_id: str = "",
        turn_id: str = "",
    ) -> "ExecutionContext":
        try:
            user_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            user_timezone = BJ
            timezone_name = "Asia/Shanghai"
        frozen_utc = datetime(2026, 7, 17, 4, 0, tzinfo=timezone.utc)
        return cls(
            current_time=frozen_utc.astimezone(user_timezone),
            timezone=timezone_name,
            user_id=user_id,
            channel=channel,
            run_id=run_id,
            turn_id=turn_id,
        )


@dataclass(frozen=True)
class IntentFrame:
    """Semantic intent frame used by all surfaces before tool execution."""

    raw: str
    normalized: str
    primary: str
    domain: str
    operation: str
    confidence: float
    evidence: tuple[str, ...] = ()
    ambiguity: tuple[str, ...] = ()
    scope: dict[str, str] = field(default_factory=dict)
    is_write: bool = False
    requires_reliable_tool_model: bool = False


@dataclass(frozen=True)
class ActionableReference:
    """Minimal structured state from a previously rendered actionable object."""

    kind: str
    source_message_id: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GoalSpec:
    """Deterministic task contract that the executor must satisfy."""

    kind: str
    domain: str
    operation: str
    target_date: Optional[str] = None
    target_meal_types: tuple[str, ...] = ()
    target_record_type: Optional[str] = None
    target_values: tuple[tuple[str, str], ...] = ()
    reference_foods: tuple[tuple[str, str], ...] = ()
    requires_lookup: bool = False
    requires_verification: bool = False
    requires_clarification: bool = False
    prohibited_operations: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnSnapshot:
    """The stable routing state for one provider/tool boundary."""

    envelope: AgentEnvelope
    context: ExecutionContext
    intent: IntentFrame
    policy_mode: str = "enforce"
    actionable_references: tuple[ActionableReference, ...] = ()
    goal: Optional[GoalSpec] = None


@dataclass(frozen=True)
class ToolExecutionRequest:
    """Normalized tool request before capability policy."""

    tool_name: str
    arguments: Any = field(default_factory=dict)
    source: str = "structured"
    tool_call_id: Optional[str] = None


@dataclass(frozen=True)
class CapabilityDecision:
    """Tool execution policy result."""

    action: str
    reason: str
    normalized_tool_name: Optional[str] = None
    normalized_args: dict[str, Any] = field(default_factory=dict)
    receipt_required: bool = False


@dataclass(frozen=True)
class ToolExecutionResult:
    """Post-tool result shape for the future ToolGateway."""

    tool_name: str
    content: Any
    receipt: Optional[dict[str, Any]] = None
    decision: Optional[CapabilityDecision] = None
