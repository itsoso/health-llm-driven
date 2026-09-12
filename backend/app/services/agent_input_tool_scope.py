"""Limit tools to the user's active instruction, keeping pasted text as data."""
from typing import Any

from app.services.utterance_intent_classifier import classify_agent_utterance


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
