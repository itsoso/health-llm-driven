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
    recovery_guidance = {
        "write_tool_without_write_intent": "先澄清用户是要查询、记录还是修改，未明确保存意图前不要写入。",
        "manage_write_without_mutate_intent": "先确认用户要修改或删除哪条记录，再执行变更。",
        "unknown_intervention_action": "先向用户说明该干预动作暂不支持，不要猜测 action。",
        "unknown_tool": "不要猜测工具名称，改用已注册能力或直接说明暂时无法完成。",
    }.get(
        decision.reason,
        "请换用明确且已注册的操作，必要时先向用户澄清目标。",
    )
    return (
        "Error: 工具调用被策略拦截。"
        f"tool={tool_name}; reason={decision.reason}; action={decision.action}; "
        f"下一步={recovery_guidance}"
    )
