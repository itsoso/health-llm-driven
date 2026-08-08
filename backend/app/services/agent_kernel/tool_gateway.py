"""Tool preflight gateway for XiaoBa Agent Kernel."""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import (
    CapabilityDecision,
    ToolExecutionRequest,
    ToolExecutionResult,
    TurnSnapshot,
)

logger = logging.getLogger(__name__)


class ToolPreflightError(RuntimeError):
    """A tool failed before its dispatch boundary was crossed."""


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

    async def execute(
        self,
        request: ToolExecutionRequest,
        dispatch: Callable[[ToolExecutionRequest], Awaitable[object]],
        *,
        on_decision: Callable[[CapabilityDecision], None] | None = None,
    ) -> ToolExecutionResult:
        """Apply policy and invoke the supplied adapter at most once."""
        try:
            decision = self.preflight(request)
            if on_decision is not None:
                on_decision(decision)
        except Exception as exc:  # noqa: BLE001 - preserve the dispatch boundary
            raise ToolPreflightError("tool_preflight_failed") from exc
        if decision.action == "block" and self.snapshot.policy_mode == "enforce":
            return ToolExecutionResult(
                tool_name=decision.normalized_tool_name or request.tool_name,
                content=blocked_tool_result(decision),
                decision=decision,
            )
        normalized_request = ToolExecutionRequest(
            tool_name=decision.normalized_tool_name or request.tool_name,
            arguments=decision.normalized_args,
            source=request.source,
            tool_call_id=request.tool_call_id,
        )
        content = await dispatch(normalized_request)
        return ToolExecutionResult(
            tool_name=normalized_request.tool_name,
            content=content,
            decision=decision,
        )


def blocked_tool_result(decision: CapabilityDecision) -> str:
    tool_name = decision.normalized_tool_name or "unknown"
    recovery_guidance = {
        "write_tool_without_write_intent": "先澄清用户是要查询、记录还是修改，未明确保存意图前不要写入。",
        "manage_write_without_mutate_intent": "先确认用户要修改或删除哪条记录，再执行变更。",
        "manage_operation_mismatch": "保留现有记录，仅重试用户明确要求的操作，不要改用其他变更方式。",
        "delete_requires_explicit_whole_record_intent": "保留整条记录；如用户只要去掉备注等字段，仅移除字段，否则先请用户明确是否删除整条记录。",
        "unknown_intervention_action": "先向用户说明该干预动作暂不支持，不要猜测 action。",
        "unknown_tool": "不要猜测工具名称，改用已注册能力或直接说明暂时无法完成。",
    }.get(
        decision.reason,
        "请换用明确且已注册的操作，必要时先向用户澄清目标。",
    )
    return json.dumps(
        {
            "status": "rejected",
            "error_code": decision.reason,
            "dispatch_started": False,
            "tool": tool_name,
            "message": "[NEEDS_CLARIFICATION] 工具调用未执行。",
            "recovery_guidance": recovery_guidance,
        },
        ensure_ascii=False,
    )
