"""Semantic utterance classifier for Agent routing.

This module is the stable boundary between free-form user language and
write/read/tool-routing decisions.  The public classifier intentionally avoids
regular expressions; it builds a small semantic frame from action, target,
question, negation and contrast signals, then routes by the frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

BJ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class AgentUtteranceIntent:
    raw: str
    normalized: str
    primary: str
    domain: str
    operation: str
    confidence: float
    reason: str
    scope: dict[str, str] = field(default_factory=dict)
    is_write: bool = False
    requires_reliable_tool_model: bool = False


READ_ACTIONS = (
    "重新列出",
    "列出",
    "列表",
    "列个表格",
    "列一下表格",
    "列成表格",
    "整理成表格",
    "表格",
    "查询",
    "查看",
    "看一下",
    "查一下",
    "显示",
    "告诉我",
    "汇总",
)
QUESTION_SIGNALS = (
    "?",
    "？",
    "多少",
    "什么",
    "啥",
    "哪些",
    "几",
    "有没有",
    "是不是",
    "是否",
    "吗",
    "呢",
    "如何",
    "怎么",
    "为什么",
    "多高",
    "多重",
    "多久",
)
WRITE_ACTIONS = (
    "记录",
    "打卡",
    "打个卡",
    "新增",
    "录入",
    "保存",
    "记下",
    "写入",
    "存下来",
    "吃了",
    "喝了",
    "服药",
    "已服用",
    "已吃",
    "已喝",
)
WRITE_NEGATIONS = (
    "别记录",
    "不要记录",
    "不用记录",
    "无需记录",
    "勿记录",
    "甭记录",
    "别记",
    "不要记",
    "不用记",
    "无需记",
    "记在心里",
    "记到心里",
)
WRITE_NEGATION_EXCEPTIONS = (
    "别忘了记录",
    "不要记错",
    "别记错",
    "别记成",
    "别记录错",
    "别记录成",
)
MUTATE_ACTIONS = {
    "delete": ("删除", "删掉", "删了", "移除", "去掉", "撤销", "清掉"),
    "update": ("修改", "改成", "改为", "改到", "更新", "调整", "更正"),
    "sync": ("同步", "sync", "拉取最新数据", "刷新一下数据", "刷新数据"),
}
ADVICE_ACTIONS = (
    "分析",
    "解读",
    "建议",
    "方案",
    "风险",
    "评估",
    "为什么",
    "怎么",
    "如何",
    "基于",
    "结合",
    "复盘",
    "综合",
    "趋势",
    "规划",
    "计划安排",
    "该不该",
    "要不要",
    "意味着",
    "说明什么",
    "冲突",
    "相互作用",
    "禁忌",
)
DIET_TERMS = (
    "饮食",
    "吃",
    "餐",
    "早餐",
    "早饭",
    "午餐",
    "午饭",
    "晚餐",
    "晚饭",
    "加餐",
    "零食",
    "夜宵",
    "热量",
    "卡路里",
    "蛋白",
    "牛肉面",
    "米饭",
    "粥",
    "菜",
    "饭",
)
WATER_TERMS = ("水", "喝水", "饮水", "温水", "白水", "矿泉水")
MEDICATION_TERMS = ("药", "服药", "用药", "胃药", "药物", "胶囊", "片")
SUPPLEMENT_TERMS = ("补剂", "维生素", "鱼油", "益生菌", "镁", "magnesium", "nac", "d3")
METRIC_TERMS = (
    "体重",
    "血压",
    "血糖",
    "睡眠",
    "步数",
    "走了",
    "几步",
    "跑步",
    "训练",
    "运动",
    "腰围",
    "心率",
    "hrv",
)
MEAL_TYPES = {
    "breakfast": ("早餐", "早饭", "早上"),
    "lunch": ("午餐", "午饭", "中饭", "中午"),
    "dinner": ("晚餐", "晚饭", "晚上"),
    "snack": ("加餐", "零食", "夜宵", "下午茶"),
}


def classify_agent_utterance(message: Any) -> AgentUtteranceIntent:
    raw = "" if message is None else str(message).strip()
    normalized = _normalize(raw)
    if not normalized:
        return _intent(raw, normalized, "unknown", "unknown", "none", 0.0, "empty")

    domain = _infer_domain(normalized)
    has_read = _has_any(normalized, READ_ACTIONS)
    scope = _build_scope(normalized, focus=(_read_focus(normalized) if has_read else None))
    has_question = _has_question_signal(normalized)
    has_write = _has_any(normalized, WRITE_ACTIONS)
    has_negated_write = _has_negated_write(normalized)
    mutation = _mutation_operation(normalized)
    has_advice = _has_any(normalized, ADVICE_ACTIONS)

    if mutation and has_question and not has_advice:
        return _intent(raw, normalized, "read", domain, "ask", 0.82, "mutation_question", scope)

    if mutation in {"delete", "sync"}:
        return _intent(
            raw,
            normalized,
            "mutate",
            domain,
            mutation,
            0.9,
            "mutation_command",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if has_advice:
        return _intent(raw, normalized, "advice", domain, "analyze", 0.86, "advice_frame", scope)

    if mutation and has_question:
        return _intent(raw, normalized, "read", domain, "ask", 0.82, "mutation_question", scope)

    if mutation:
        return _intent(
            raw,
            normalized,
            "mutate",
            domain,
            mutation,
            0.9,
            "mutation_command",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if has_read or _is_data_question(normalized, domain, has_question):
        operation = "list" if has_read and not has_question else "ask"
        if _wants_table_or_list(normalized):
            operation = "list"
        return _intent(raw, normalized, "read", domain, operation, 0.88, "read_frame", scope)

    if has_negated_write:
        return _intent(raw, normalized, "chat", domain, "none", 0.78, "negated_write", scope)

    if has_write:
        return _intent(
            raw,
            normalized,
            "write",
            domain,
            "create",
            0.84,
            "write_frame",
            scope,
            is_write=True,
        )

    if has_question:
        return _intent(raw, normalized, "read", domain, "ask", 0.55, "question_frame", scope)

    return _intent(raw, normalized, "unknown", domain, "none", 0.35, "ambiguous", scope)


def _intent(
    raw: str,
    normalized: str,
    primary: str,
    domain: str,
    operation: str,
    confidence: float,
    reason: str,
    scope: Optional[dict[str, str]] = None,
    *,
    is_write: bool = False,
    requires_reliable_tool_model: bool = False,
) -> AgentUtteranceIntent:
    return AgentUtteranceIntent(
        raw=raw,
        normalized=normalized,
        primary=primary,
        domain=domain,
        operation=operation,
        confidence=confidence,
        reason=reason,
        scope=dict(scope or {}),
        is_write=is_write,
        requires_reliable_tool_model=requires_reliable_tool_model,
    )


def _normalize(value: str) -> str:
    return "".join(str(value or "").split()).lower()


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase.lower() in text for phrase in phrases)


def _has_question_signal(text: str) -> bool:
    return _has_any(text, QUESTION_SIGNALS)


def _wants_table_or_list(text: str) -> bool:
    return _has_any(text, ("列出", "列表", "表格", "汇总", "显示"))


def _has_negated_write(text: str) -> bool:
    if _has_any(text, WRITE_NEGATION_EXCEPTIONS):
        return False
    return _has_any(text, WRITE_NEGATIONS)


def _mutation_operation(text: str) -> Optional[str]:
    for operation, phrases in MUTATE_ACTIONS.items():
        if _has_any(text, phrases):
            return operation
    return None


def _infer_domain(text: str) -> str:
    if _has_any(text, WATER_TERMS):
        return "water"
    if _has_any(text, MEDICATION_TERMS):
        return "medication"
    if _has_any(text, SUPPLEMENT_TERMS):
        return "supplement"
    if _has_any(text, DIET_TERMS):
        return "diet"
    if _has_any(text, METRIC_TERMS):
        return "metric"
    return "unknown"


def _is_data_question(text: str, domain: str, has_question: bool) -> bool:
    if has_question and domain != "unknown":
        return True
    if domain == "unknown":
        return False
    return _has_any(text, ("今天", "昨天", "本周", "这周", "最近", "昨晚", "数据", "情况", "状态"))


def _read_focus(text: str) -> str:
    last_end = -1
    for phrase in READ_ACTIONS:
        idx = text.rfind(phrase.lower())
        if idx >= 0:
            last_end = max(last_end, idx + len(phrase))
    return text[last_end:] if last_end >= 0 else text


def _build_scope(text: str, *, focus: Optional[str] = None) -> dict[str, str]:
    scope_text = focus if focus is not None else text
    scope: dict[str, str] = {}
    date_value = _relative_date(scope_text) or (None if focus is None else _relative_date(text))
    if date_value:
        scope["date"] = date_value
    meal_type = _meal_type(scope_text)
    if meal_type:
        scope["meal_type"] = meal_type
    return scope


def _relative_date(text: str) -> Optional[str]:
    today = datetime.now(BJ).date()
    candidates: list[tuple[int, str]] = []
    for label, value in (
        ("前天", (today - timedelta(days=2)).isoformat()),
        ("昨天", (today - timedelta(days=1)).isoformat()),
        ("昨日", (today - timedelta(days=1)).isoformat()),
        ("今天", today.isoformat()),
        ("今日", today.isoformat()),
        ("明天", (today + timedelta(days=1)).isoformat()),
    ):
        idx = text.rfind(label)
        if idx >= 0:
            candidates.append((idx, value))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return None


def _meal_type(text: str) -> Optional[str]:
    for meal_type, labels in MEAL_TYPES.items():
        if _has_any(text, labels):
            return meal_type
    return None
