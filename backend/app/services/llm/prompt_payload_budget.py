"""Content-free size accounting for the actual provider-bound payload.

These character counts and legacy chars/4 estimates are not provider token
truth. In particular serialized multimodal sizes cannot estimate vision tokens.
No prompt content, tool arguments, hashes, or URLs leave this pure helper.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _stringify_message_content(content: Any) -> str:
    """把一条消息的 content 稳定序列化成字符串 (字符串原样;list/dict → 排序 JSON)。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        return str(content)


def prompt_payload_budget(
    messages: List[Dict],
    tools: Optional[List[Dict]] = None,
) -> Dict[str, int]:
    """Return content-free per-block prompt size telemetry.

    The accounting deliberately contains only lengths/counts. It is safe for
    health logs because neither prompt text nor tool descriptions are emitted.
    ``// 4`` matches the existing token-ish prefix metric, so before/after
    dashboards remain comparable until provider-reported token blocks exist.
    """
    last_user_idx = -1
    for index, message in enumerate(messages):
        if message.get("role") == "user":
            last_user_idx = index

    system_chars = 0
    history_chars = 0
    turn_chars = 0
    tool_result_chars = 0
    tool_call_chars = 0
    for index, message in enumerate(messages):
        size = len(_stringify_message_content(message.get("content")))
        if message.get("role") == "tool":
            tool_result_chars += size
        if message.get("tool_calls"):
            tool_call_chars += len(json.dumps(
                message["tool_calls"], ensure_ascii=False, separators=(",", ":"), default=str,
            ))
        if message.get("role") == "system":
            system_chars += size
        elif index == last_user_idx:
            turn_chars += size
        else:
            history_chars += size

    tool_payload = json.dumps(
        tools or [],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    tool_schema_chars = len(tool_payload) if tools else 0
    message_chars = system_chars + history_chars + turn_chars
    return {
        "system_chars": system_chars,
        "system_approx_tokens": system_chars // 4,
        "history_chars": history_chars,
        "history_approx_tokens": history_chars // 4,
        "dialogue_chars": history_chars - tool_result_chars,
        "tool_result_chars": tool_result_chars,
        "tool_call_chars": tool_call_chars,
        "turn_chars": turn_chars,
        "turn_approx_tokens": turn_chars // 4,
        "tool_schema_chars": tool_schema_chars,
        "tool_schema_approx_tokens": tool_schema_chars // 4,
        "tool_count": len(tools or []),
        "message_approx_tokens": message_chars // 4,
        "total_approx_tokens": (message_chars + tool_schema_chars) // 4,
        # Keep legacy metrics comparable; this estimate also counts calls.
        "input_approx_tokens": (message_chars + tool_schema_chars + tool_call_chars) // 4,
    }

