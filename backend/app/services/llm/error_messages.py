"""User-facing LLM error normalization.

Provider exceptions can contain quota ids, upstream JSON, model names, or
gateway internals. Chat surfaces must show a short actionable message instead.
"""

from __future__ import annotations

from typing import Any


_TOOL_LABELS = {
    "health_query": "健康数据查询",
    "health_query_batch": "健康数据查询",
    "health_record": "健康记录",
    "health_manage": "健康记录",
    "health_analysis": "健康分析",
    "knowledge_search": "知识查询",
    "realtime_search": "实时查询",
    "environment_check": "环境查询",
    "supplement_guide": "补剂建议",
    "manage_plan": "计划管理",
}


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

    budget_reason = getattr(error, "reason", None)
    text = _error_text(error).lower()
    if budget_reason in {"user_monthly_token_limit", "user_monthly_credit_limit"} or any(
        marker in text
        for marker in (
            "user_monthly_token_limit",
            "user_monthly_credit_limit",
            "monthly user token quota exceeded",
            "monthly user tokenplan credit quota exceeded",
        )
    ):
        return (
            "本月 AI 使用额度已达上限，将于下月 1 日恢复。"
            "你已发送的内容已保留；如需立即继续，请联系管理员调整额度。"
        )
    if budget_reason == "user_daily_call_limit" or any(
        marker in text
        for marker in ("user_daily_call_limit", "daily user call quota exceeded")
    ):
        return (
            "今日 AI 使用额度已达上限，将于明日恢复。"
            "你已发送的内容已保留；如需立即继续，请联系管理员调整额度。"
        )
    if budget_reason in {
        "global_monthly_token_limit",
        "global_monthly_credit_limit",
        "global_daily_call_limit",
        "budget_guard_unavailable",
    } or any(
        marker in text
        for marker in (
            "global_monthly_token_limit",
            "global_monthly_credit_limit",
            "global_daily_call_limit",
            "budget_guard_unavailable",
        )
    ):
        return (
            "AI 服务保护暂时生效，运维已收到记录。"
            "你已发送的内容已保留，请稍后重试。"
        )
    if is_llm_quota_error(error):
        return "当前模型额度已用尽。请切换模型或稍后重试；本轮没有生成可靠健康建议。"
    if is_llm_rate_limit_error(error):
        return "当前模型服务请求过于频繁。请稍后重试；本轮没有生成可靠健康建议。"
    if "timeout" in text or "timed out" in text or "超时" in text:
        return "模型服务响应超时。请稍后重试；本轮没有生成可靠健康建议。"
    return "模型服务暂时不可用。请稍后重试；本轮没有生成可靠健康建议。"


def safe_tool_error_message(tool_name: str, error: Any) -> str:
    """Return a short, actionable tool error without exposing upstream details."""

    label = _TOOL_LABELS.get(str(tool_name), "这项操作")
    text = _error_text(error).lower()
    error_type = type(error).__name__.lower()
    if (
        "timeout" in error_type
        or "timeout" in text
        or "timed out" in text
        or "超时" in text
    ):
        return f"{label}处理超时，请稍后重试。"
    if any(marker in text for marker in ("connection", "network", "连接", "网络", "dns")):
        return f"{label}暂时无法连接服务，请检查网络后重试。"
    if "429" in text or "rate limit" in text or "too many requests" in text or "限流" in text:
        return f"{label}服务繁忙，请稍后重试。"
    if "403" in text or "401" in text or "permission" in text or "权限" in text:
        return f"暂时没有权限完成{label}，请检查账号状态后重试。"
    return f"{label}暂时无法完成，请稍后重试。"
