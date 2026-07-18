"""Small, deterministic recovery rules for one Agent turn.

Retries are deliberately limited to idempotent read tools and transient-looking
failures.  The model must never decide that a write is safe to repeat.
"""
from __future__ import annotations


_RETRYABLE_READ_TOOLS = frozenset(
    {
        "environment_check",
        "health_query",
        "health_query_batch",
        "knowledge_search",
        "query_genetic_profile",
        "query_lab_indicators",
        "realtime_search",
    }
)

_TRANSIENT_FAILURE_MARKERS = (
    "请稍后重试",
    "暂时不可用",
    "暂时失败",
    "网络",
    "连接",
    "超时",
    "timeout",
    "timed out",
    "服务繁忙",
    "服务不可用",
    "upstream",
    "502",
    "503",
    "504",
    "429",
)

_NON_RETRYABLE_FAILURE_MARKERS = (
    "未找到",
    "不存在",
    "参数",
    "权限",
    "不支持",
    "格式错误",
    "需要确认",
)


def should_retry_tool_failure(
    tool_name: str,
    result: str,
    *,
    attempt: int,
    max_retries: int = 1,
) -> bool:
    """Return whether a tool result is safe to retry once.

    ``attempt`` is zero-based and counts completed attempts before the retry.
    This function is intentionally content-free: it only inspects the tool name
    and coarse error markers, never logs or returns health data.
    """
    if attempt >= max_retries or tool_name not in _RETRYABLE_READ_TOOLS:
        return False
    text = str(result or "").strip()
    if not text.startswith("Error:") or "[NEEDS_CONFIRMATION]" in text:
        return False
    if any(marker in text for marker in _NON_RETRYABLE_FAILURE_MARKERS):
        return False
    lowered = text.lower()
    return any(marker in text or marker in lowered for marker in _TRANSIENT_FAILURE_MARKERS)
