"""Shared XiaoBa Agent Kernel contracts.

The kernel is the backend boundary between free-form user language and
tool execution. Entry surfaces build envelopes, intent builders produce typed
frames, and capability policy decides whether a tool may execute.
"""

from app.services.agent_kernel.intent_frame import build_intent_frame
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
    "CapabilityDecision",
    "ExecutionContext",
    "IntentFrame",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "TurnSnapshot",
    "build_intent_frame",
]
