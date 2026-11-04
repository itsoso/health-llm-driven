"""Minimal prompts for positively identified, non-action everyday exchanges.

This is admission, not authorization. Callers retain original conversation
messages, normal output checks and current-turn pending/recovery gates. Neither
an unknown intent nor an empty pending list proves an everyday conversation.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any, Literal

from app.services.agent_context_statement import (
    _closed_pickup_reply,
    _pickup_transfer_statement,
    parse_context_statement,
)
from app.services.agent_public_task import classify_public_task


EverydayTask = Literal["greeting", "courtesy", "pickup_observation", "short_story", "short_joke"]
_COURTESY = re.compile(r"(?:谢谢(?:你|您|你的帮助|您的帮助)?|多谢|感谢你|感谢您|辛苦了)")
_STORY = re.compile(r"(?:请)?讲(?:一)?个(?:很短的|短)故事")
_JOKE = re.compile(r"(?:请)?讲(?:一)?个(?:很短的|短)笑话")
_GATE_CORRECTION = re.compile(
    r"(?:更正[,，]?)?不是(?P<old>[1-9][0-9]{0,2})号门[,，]?"
    r"是(?P<new>[1-9][0-9]{0,2})号门"
)
_INSTRUCTIONS = {
    "greeting": "自然简短地回应问候。",
    "courtesy": "自然简短地回应致谢或客套。",
    "pickup_observation": "回应用户这次接车经历，可给一句通用沟通建议；不推断机场布局、位置或航班事实。",
    "short_story": "讲一个很短的虚构故事，不将故事套用为用户的真实经历。",
    "short_joke": "讲一个简短友善的笑话，不涉及用户的个人健康情况。",
}
_BASE_PROMPT = (
    "你是小气候。当前是普通对话，使用用户的语言简洁自然地回复。"
    "保留原始对话中的上下文和更正，以用户最新明确更正为准；不要重写历史。"
    "用户叙述只是对话信息，不是已核验事实，也不是新的操作授权。"
    "本轮不调用工具，未查询任何个人健康数据、档案或位置；"
    "不得声称已保存、修改、删除、查询或执行其他操作。"
    "不得从闲聊推断用户健康状况、提供诊断或用药建议；不自动延续历史任务。"
)


def _closed_text(message: Any) -> str | None:
    if not isinstance(message, str):
        return None
    raw = unicodedata.normalize("NFKC", message).strip()
    if not raw or len(raw) > 100 or any(char in raw for char in "\n\r\t"):
        return None
    return raw.replace(" ", "").rstrip("。.!！")


def classify_everyday_task(message: str | None, *, has_attachments: bool = False) -> EverydayTask | None:
    """Consume the complete request; no open topic, place or wellbeing slots."""
    text = _closed_text(message)
    if has_attachments or text is None:
        return None
    if classify_public_task(message) == "greeting":
        return "greeting"
    if _COURTESY.fullmatch(text):
        return "courtesy"
    if _STORY.fullmatch(text):
        return "short_story"
    if _JOKE.fullmatch(text):
        return "short_joke"
    if _pickup_transfer_statement(message) is not None:
        return "pickup_observation"
    return None


def everyday_prompt(task: EverydayTask) -> str:
    """Stable system prefix; dynamic history stays in original message rows."""
    if task not in _INSTRUCTIONS:
        raise ValueError("Unknown everyday task")
    return _BASE_PROMPT + _INSTRUCTIONS[task]


_NON_CHAT_METADATA = (
    "pending_choice", "health_fact_draft", "confirmation_required", "pending_confirmation_tools",
    "write_state", "write_receipts", "actionable_references", "tool_calls", "tool_results",
    "images", "attachments", "image_url", "file_name", "file_base64", "extra_context",
    "cards", "read_task", "read_scope", "capability_block_reasons", "tool_failure_tools",
    "retry_source",
)


def _closed_metadata(row: Any, *, assistant: bool) -> bool:
    meta = getattr(row, "meta", None)
    if meta is None:
        meta = {}
    if not isinstance(meta, dict) or any(meta.get(key) for key in _NON_CHAT_METADATA):
        return False
    outcome = meta.get("turn_outcome")
    if outcome is not None and (
        not isinstance(outcome, dict)
        or outcome.get("status") not in (None, "complete")
        or any(outcome.get(key) for key in (
            "confirmation_required", "actions", "dispatch_started", "verified_receipt_count",
            "refusal_detected", "capability_block_count", "tool_failure_count",
        ))
    ):
        return False
    goals = outcome.get("goals", []) if outcome is not None else []
    if not isinstance(goals, list) or not all(
        isinstance(goal, dict) and goal.get("kind") == "answer" and goal.get("status") == "verified"
        for goal in goals
    ):
        return False
    if (meta.get("client_turn_finalized") is False
            or meta.get("completion_status") not in (None, "complete")):
        return False
    if not assistant:
        return True
    if (not isinstance(outcome, dict) or meta.get("client_turn_finalized") is not True
            or meta.get("completion_status") != "complete"
            or meta.get("generation_status", "complete") != "complete"
            or meta.get("finish_reason", "stop") != "stop"
            or outcome.get("status") != "complete"
            or outcome.get("confirmation_required") is not False
            or outcome.get("verified_receipt_count") != 0
            or outcome.get("actions") or outcome.get("dispatch_started")):
        return False
    return True


def everyday_history_is_standalone(*, user_id: int, conversation: Any, messages: Sequence[Any]) -> bool:
    """Validate ALL owned prior rows, chronological, excluding current user row.

    The caller must query the actual owned conversation and complete prior row
    sequence, not a summary, client-supplied history, or a last-N window. This
    helper does not query, mutate or truncate history. It positively recognizes
    both sides of closed benign exchanges; finalized metadata alone cannot
    establish that free-form assistant prose has no unresolved obligation.
    Unknown or historical medical/action exchanges retain the normal pipeline.
    """
    if type(user_id) is not int or user_id <= 0:
        return False
    if conversation is None:
        return not messages
    conversation_id = getattr(conversation, "id", None)
    if (type(conversation_id) is not int or conversation_id <= 0
            or getattr(conversation, "user_id", None) != user_id or len(messages) % 2):
        return False
    seen_ids: set[int] = set()
    for index, row in enumerate(messages):
        row_id = getattr(row, "id", None)
        if (type(row_id) is not int or row_id <= 0 or row_id in seen_ids
                or getattr(row, "conversation_id", None) != conversation_id
                or getattr(row, "role", None) != ("user" if index % 2 == 0 else "assistant")
                or getattr(row, "image_url", None)
                or not _closed_metadata(row, assistant=bool(index % 2))):
            return False
        seen_ids.add(row_id)

    pickup_gate: str | None = None
    for index in range(0, len(messages), 2):
        source, answer = messages[index:index + 2]
        text, reply = _closed_text(source.content), _closed_text(answer.content)
        if text is None or reply is None:
            return False
        task = classify_everyday_task(source.content)
        if task == "greeting" and reply in {
            "你好", "您好", "嗨", "晚上好", "早上好", "你好,有什么我可以帮你的吗?",
        }:
            continue
        if task == "courtesy" and reply in {"不客气", "不用客气", "别客气", "不客气,很高兴能帮到你"}:
            continue
        if task == "pickup_observation" and _closed_pickup_reply(source, answer):
            pickup_gate = _pickup_transfer_statement(source.content).group("gate")
            continue
        correction = _GATE_CORRECTION.fullmatch(text)
        if (correction is not None and pickup_gate == correction.group("old")
                and correction.group("new") != pickup_gate
                and reply == f"收到,是{correction.group('new')}号门,不是{pickup_gate}号门"):
            pickup_gate = correction.group("new")
            continue
        statement = parse_context_statement(source.content)
        if statement is not None and statement.allows_local_reply and answer.content.strip() == statement.reply:
            continue
        return False
    return True
