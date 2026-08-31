"""Small, deterministic recovery rules for one Agent turn.

Retries are deliberately limited to idempotent read tools and transient-looking
failures.  The model must never decide that a write is safe to repeat.
"""
from __future__ import annotations

import re


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

_MODEL_SCOPE_REFUSAL_MARKERS = (
    "只能记录",
    "只能查询",
    "只能帮你记录",
    "无法提供分析",
    "不能提供分析",
    "无法提供建议",
    "不能提供建议",
)

_SAFETY_REFUSAL_MARKERS = (
    "诊断",
    "处方",
    "停药",
    "医生",
    "医疗判断",
)

_DATA_INSUFFICIENCY_MARKERS = (
    "没有足够数据",
    "数据不足",
    "缺少数据",
    "暂无数据",
    "暂无相关记录",
    "没有相关记录",
    "无法判断",
    "无法分析",
)

_DATA_GAP_ACTION_MARKERS = (
    "请补充",
    "建议记录",
    "可以先",
    "我可以",
    "下一步",
    "请提供",
)

_INTERNAL_PROCESS_PHRASES = (
    "i need to",
    "let me",
    "i'll try",
    "i will try",
    "i'll query",
    "i will query",
    "let me reconsider",
    "the sleep query failed",
)

_INTERNAL_TOOL_MARKERS = (
    "health_query",
    "health_analysis",
    "calendar_window_unsupported",
    "tool call",
    "window parameter",
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


def is_model_scope_refusal(text: str) -> bool:
    """Return whether a model incorrectly narrows the Agent to record/query only.

    This is intentionally narrower than the general refusal classifier. Safety
    boundary refusals must remain visible and must never be auto-re-asked.
    """
    normalized = " ".join(str(text or "").split())
    if not normalized or len(normalized) > 600:
        return False
    if not normalized.startswith(("抱歉", "很抱歉")):
        return False
    if is_safety_boundary_refusal(normalized):
        return False
    return any(marker in normalized[:240] for marker in _MODEL_SCOPE_REFUSAL_MARKERS)


def is_safety_boundary_refusal(text: str) -> bool:
    """Return whether a refusal touches a medical safety boundary."""
    normalized = " ".join(str(text or "").split())
    return bool(normalized and any(marker in normalized for marker in _SAFETY_REFUSAL_MARKERS))


def should_buffer_refusal_response(text: str) -> bool:
    """Return whether an apology-prefixed answer should wait for classification."""
    normalized = " ".join(str(text or "").split())
    return bool(normalized.startswith(("抱歉", "很抱歉")) and len(normalized) <= 240)


def is_data_insufficiency_response(text: str) -> bool:
    """Return whether a short answer stops at a recoverable data gap."""
    normalized = " ".join(str(text or "").split())
    if not normalized or len(normalized) > 600:
        return False
    if is_safety_boundary_refusal(normalized):
        return False
    if not any(marker in normalized[:180] for marker in _DATA_INSUFFICIENCY_MARKERS):
        return False
    if any(marker in normalized for marker in _DATA_GAP_ACTION_MARKERS):
        return False
    return normalized.startswith(
        (
            "抱歉",
            "很抱歉",
            "目前",
            "暂时",
            "无法",
            "数据不足",
            "暂无",
            "缺少",
            "没有",
        )
    )


def is_internal_process_response(text: str) -> bool:
    """Detect model self-talk/tool planning that must never be user-visible.

    One ordinary English first-person phrase is not enough. We require either
    an internal tool/error marker plus process narration, or repeated process
    narration, which keeps legitimate English health answers untouched.
    """
    normalized = " ".join(str(text or "").split()).lower()
    if not normalized:
        return False
    process_count = sum(
        len(re.findall(re.escape(phrase), normalized))
        for phrase in _INTERNAL_PROCESS_PHRASES
    )
    has_internal_marker = any(marker in normalized for marker in _INTERNAL_TOOL_MARKERS)
    return bool((process_count >= 1 and has_internal_marker) or process_count >= 3)


def _could_be_internal_process_prefix(text: str) -> bool:
    """Buffer even token-sized prefixes before they can form model self-talk."""
    normalized = " ".join(str(text or "").split()).lower()
    if not normalized:
        return False
    return any(
        phrase.startswith(normalized) or normalized.startswith(phrase)
        for phrase in _INTERNAL_PROCESS_PHRASES
    )


def should_buffer_recovery_response(text: str) -> bool:
    """Return whether a short refusal/data-gap answer should wait for recovery."""
    normalized = " ".join(str(text or "").split())
    if should_buffer_refusal_response(normalized) or is_data_insufficiency_response(normalized):
        return True
    if is_internal_process_response(normalized) or _could_be_internal_process_prefix(
        normalized
    ):
        return True
    # Data-gap wording often arrives over several deltas (e.g. "目前没有" +
    # "足够数据"). Buffer only the short leading prefix so the first fragment
    # cannot leak before the final classifier sees the complete sentence.
    return bool(
        len(normalized) <= 80
        and normalized.startswith(("目前", "暂时", "无法", "数据不足", "暂无", "缺少", "没有"))
    )
