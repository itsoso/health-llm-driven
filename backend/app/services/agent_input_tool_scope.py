"""Limit tools to the user's active instruction, keeping pasted text as data."""
from typing import Any

from app.services.agent_kernel.tool_registry import get_tool_spec
from app.services.agent_kernel.types import GoalSpec
from app.services.utterance_intent_classifier import classify_agent_utterance


def scope_tools_for_goal(
    tools: list[dict[str, Any]], goal: GoalSpec | None,
) -> list[dict[str, Any]]:
    """Hide pure write capabilities when the compiled goal forbids every write.

    Mixed tools remain visible because their arguments may describe an allowed
    read.  The argument-level goal guard remains authoritative at dispatch.
    """
    if goal is None or not {"create", "update", "delete"}.issubset(
        set(goal.prohibited_operations)
    ):
        return tools
    scoped: list[dict[str, Any]] = []
    for tool in tools:
        name = str((tool.get("function") or {}).get("name") or "")
        try:
            effect = get_tool_spec(name).effect
        except (KeyError, RuntimeError):
            # Unknown future capabilities receive no model authority in a
            # fully read-only goal.
            continue
        if effect != "write":
            scoped.append(tool)
    return scoped


def scope_tools_for_owned_read(tools: list[dict[str, Any]], scope) -> list[dict[str, Any]]:
    """Expose only bounded adapters for a server-owned multi-domain read.

    Filter the existing set; never re-enable a tool removed by another boundary.
    Single-domain adapters retain their existing compatibility behavior.
    """
    from app.services.agent_kernel.read_task_scope import OWNED_MULTI_READ_TOOL_NAMES

    if scope is None or len(scope.queries) <= 1:
        return tools
    return [tool for tool in tools
            if (tool.get("function") or {}).get("name") in OWNED_MULTI_READ_TOOL_NAMES]


def scope_tools_for_analyzed_material(
    tools: list[dict[str, Any]], message: str,
) -> list[dict[str, Any]]:
    """Pure material analysis may consult reviewed knowledge, not personal data.

    The classifier already separates framed material from explicit outside
    instructions. Reuse that decision rather than treating every analysis or
    every quotation as a reason to suppress a real read/write request.
    """
    if classify_agent_utterance(message).reason != "analyzed_material":
        return tools
    return [tool for tool in tools if (tool.get("function") or {}).get("name") == "knowledge_search"]
