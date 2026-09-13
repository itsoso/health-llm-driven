"""Limit tools to the user's active instruction, keeping pasted text as data."""
from typing import Any

from app.services.utterance_intent_classifier import classify_agent_utterance


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
