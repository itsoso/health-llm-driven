"""Tool preflight gateway for XiaoBa Agent Kernel."""
from __future__ import annotations

import logging

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import CapabilityDecision, ToolExecutionRequest, TurnSnapshot

logger = logging.getLogger(__name__)


class ToolGateway:
    """Apply deterministic policy before a tool dispatch crosses into execution."""

    def __init__(self, snapshot: TurnSnapshot):
        self.snapshot = snapshot

    def preflight(self, request: ToolExecutionRequest) -> CapabilityDecision:
        decision = decide_tool_capability(self.snapshot, request)
        logger.info(
            "[agent_kernel.tool_gateway] action=%s reason=%s tool=%s user=%s channel=%s intent=%s/%s/%s source=%s",
            decision.action,
            decision.reason,
            decision.normalized_tool_name or request.tool_name,
            self.snapshot.context.user_id,
            self.snapshot.context.channel,
            self.snapshot.intent.primary,
            self.snapshot.intent.domain,
            self.snapshot.intent.operation,
            request.source,
        )
        return decision


def blocked_tool_result(decision: CapabilityDecision) -> str:
    tool_name = decision.normalized_tool_name or "unknown"
    return (
        "Error: 工具调用被策略拦截。"
        f"tool={tool_name}; reason={decision.reason}; action={decision.action}"
    )
