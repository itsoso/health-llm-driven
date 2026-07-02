"""User-facing LLM error normalization.

Provider exceptions can contain quota ids, upstream JSON, model names, or
gateway internals. Chat surfaces must show a short actionable message instead.
"""

from __future__ import annotations

from typing import Any


def _error_text(error: Any) -> str:
    if error is None:
        return ""
    return str(error)


def is_llm_quota_error(error: Any) -> bool:
    text = _error_text(error).lower()
    return any(
        marker in text
        for marker in (
            "insufficient_quota",
            "quota has been exhausted",
            "token-plan quota",
            "billing hard limit",
        )
    )


def is_llm_rate_limit_error(error: Any) -> bool:
    text = _error_text(error).lower()
    return (
        "429" in text
        or "rate limit" in text
        or "too many requests" in text
        or "限流" in text
    )


def safe_llm_error_message(error: Any) -> str:
    """Return an actionable message safe to show and persist in chat history."""

    text = _error_text(error).lower()
    if is_llm_quota_error(error):
        return "当前模型额度已用尽。请切换模型或稍后重试；本轮没有生成可靠健康建议。"
    if is_llm_rate_limit_error(error):
        return "当前模型服务请求过于频繁。请稍后重试；本轮没有生成可靠健康建议。"
    if "timeout" in text or "timed out" in text or "超时" in text:
        return "模型服务响应超时。请稍后重试；本轮没有生成可靠健康建议。"
    return "模型服务暂时不可用。请稍后重试；本轮没有生成可靠健康建议。"
