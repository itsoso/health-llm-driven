"""Deterministic, content-free quality gates for Agent answers."""
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_AGENT_PERSISTENCE_MAX_CHARS = 50_000
_TRUNCATION_NOTICE = "\n\n> 回答超过显示上限，已按段落截断。你可以继续追问具体部分。"


@dataclass(frozen=True, slots=True)
class AgentOutputQualityResult:
    text: str
    flags: tuple[str, ...]
    original_length: int
    persisted_length: int


def needs_input_clarification(message: str) -> bool:
    normalized = "".join(str(message or "").split())
    return 0 < len(normalized) <= 1


def clarification_reply() -> str:
    return "我还不确定你想查询、分析还是记录什么。请再补充一句完整需求。"


def enforce_agent_output_quality(
    value: str,
    *,
    max_chars: int = DEFAULT_AGENT_PERSISTENCE_MAX_CHARS,
) -> AgentOutputQualityResult:
    text = str(value or "")
    limit = max(256, int(max_chars))
    if len(text) <= limit:
        flags = () if text.strip() else ("empty_content",)
        return AgentOutputQualityResult(text, flags, len(text), len(text))

    body_limit = max(1, limit - len(_TRUNCATION_NOTICE))
    prefix = text[:body_limit]
    paragraph_boundary = prefix.rfind("\n\n")
    if paragraph_boundary >= max(1, body_limit // 2):
        prefix = prefix[:paragraph_boundary]
    bounded = f"{prefix.rstrip()}{_TRUNCATION_NOTICE}"
    return AgentOutputQualityResult(
        bounded,
        ("persistence_budget_truncated",),
        len(text),
        len(bounded),
    )
