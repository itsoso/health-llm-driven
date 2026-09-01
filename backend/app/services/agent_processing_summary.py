"""Deterministic, privacy-minimized summaries for agent tool processing."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping


_SOURCE_LABELS = {
    "health_query": "健康记录",
    "health_record": "健康记录",
    "get_health_data": "健康记录",
    "get_sleep_data": "睡眠记录",
    "get_medications": "用药记录",
    "search_knowledge": "健康知识库",
    "web_search": "公开资料",
}
_DATE_KEYS = ("start_date", "end_date", "date", "record_date", "from", "to")


def _bounded_scalar(value: Any) -> str | None:
    if not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    if not text or len(text) > 32:
        return None
    return text


def _time_range(args: Mapping[str, Any]) -> str:
    values = [value for key in _DATE_KEYS if (value := _bounded_scalar(args.get(key)))]
    if len(values) >= 2:
        return f"{values[0]} 至 {values[1]}"
    if values:
        return values[0]
    days = args.get("days")
    if isinstance(days, int) and 0 < days <= 3650:
        return f"最近 {days} 天"
    return "本次请求范围"


def _row_count(result: str) -> int | None:
    try:
        payload = json.loads(result)
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("items", "records", "data", "results"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
        for key in ("count", "total", "row_count"):
            value = payload.get(key)
            if isinstance(value, int) and value >= 0:
                return value
    match = re.search(r"(?:共|找到|获取到)\s*(\d+)\s*(?:条|项|个)", result or "")
    return int(match.group(1)) if match else None


def build_processing_summary(
    tool_name: str,
    args: Mapping[str, Any] | None,
    result: str,
    *,
    success: bool,
) -> dict[str, Any]:
    """Return evidence density without copying raw tool output or arguments."""
    rows = _row_count(result) if success else None
    available = bool(success and (rows is None or rows > 0))
    failure_reason = None
    if not success:
        lowered = (result or "").lower()
        if "timeout" in lowered or "超时" in lowered:
            failure_reason = "数据源响应超时"
        elif "unauthorized" in lowered or "认证" in lowered or "权限" in lowered:
            failure_reason = "数据源授权不可用"
        else:
            failure_reason = "数据源暂时不可用"
    elif rows == 0:
        failure_reason = "该范围内暂无可用记录"

    if not success:
        next_action = "继续使用已验证的信息回答，并说明数据缺口"
    elif rows == 0:
        next_action = "说明暂无记录，并提示可补充的数据"
    else:
        next_action = "基于已取得的证据继续分析"

    return {
        "source": _SOURCE_LABELS.get(tool_name, "已授权数据源"),
        "time_range": _time_range(args or {}),
        "row_count": rows,
        "availability": "available" if available else "unavailable",
        "failure_reason": failure_reason,
        "next_action": next_action,
    }
