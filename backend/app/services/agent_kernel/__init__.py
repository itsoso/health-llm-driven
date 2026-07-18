"""Shared XiaoBa Agent Kernel contracts.

The kernel is the backend boundary between free-form user language and
tool execution. Entry surfaces build envelopes, intent builders produce typed
frames, and capability policy decides whether a tool may execute.
"""

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.context import build_execution_context, build_turn_snapshot, format_turn_time_context_prompt
from app.services.agent_kernel.events import AgentEventBus, AgentKernelEvent
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import (
    AgentEnvelope,
    CapabilityDecision,
    ExecutionContext,
    IntentFrame,
    ToolExecutionRequest,
    ToolExecutionResult,
    TurnSnapshot,
)

__all__ = [
    "AgentEnvelope",
    "AgentEventBus",
    "AgentKernelEvent",
    "CapabilityDecision",
    "ExecutionContext",
    "IntentFrame",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolGateway",
    "TurnSnapshot",
    "build_intent_frame",
    "build_execution_context",
    "build_turn_snapshot",
    "format_turn_time_context_prompt",
]
