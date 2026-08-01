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

from app.services.clinician_provenance_guard import (
    ClinicianTurnDecision,
    classify_clinician_turn,
)

from app.services.utterance_intent_lexicon import (
    CLINICIAN_FEEDBACK_OBJECT_NOUNS,
    CLINICIAN_PROVIDER_TERMS,
    MEDIA_CREATE_ACTIONS,
    MEDIA_TERMS,
    MUTATE_ACTIONS,
    MUTATION_NEGATION_EXCEPTIONS,
    MUTATION_NEGATIONS,
    PLAN_CREATE_ACTIONS,
    PLAN_TERMS,
    PLAN_UPDATE_ACTIONS,
    QUESTION_SIGNALS,
    READ_ACTIONS,
    RECORD_NOUN_SUFFIXES,
    REMINDER_CREATE_ACTIONS,
    REMINDER_TERMS,
    WRITE_ACTIONS,
    WRITE_COMMAND_PREFIXES,
    WRITE_NEGATION_EXCEPTIONS,
    WRITE_NEGATIONS,
)

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

DIET_RECALCULATE_ACTIONS = ("重新估算", "重新计算", "重新核算", "重算", "重估")
DIET_RECALCULATE_UPDATE_ACTIONS = ("写入", "写回", "更新", "保存", "改写")
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
    "推断",
    "根因",
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
WATER_TERMS = ("喝水", "饮水", "补水")
WATER_QUERY_TERMS = ("多少水", "水喝够", "喝够水", "喝水够")
WATER_INTAKE_OBJECT_TERMS = ("杯水", "瓶水", "点水", "些水", "喝了水", "已喝水")
WATER_NAMED_OBJECT_TERMS = ("温水", "白水", "矿泉水")
WATER_OBJECT_BOUNDARY_CHARS = frozenset(
    "了啦吧呢吗呀啊哦并和共用，。,.、；;！!？?"
)
WATER_OBJECT_FOLLOWUP_TERMS = (
    "然后",
    "准备",
    "接着",
    "之后",
    "同时",
    "并且",
    "马上",
    "现在",
    "再",
    "后",
    "就",
    "喝",
)
WATER_STATUS_TERMS = (
    "水喝少",
    "水喝得少",
    "水喝多",
    "水喝得多",
    "水摄入少",
    "水摄入多",
)
WATER_AMOUNT_UNITS = ("ml", "毫升", "升")
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
    "kg",
    "公斤",
    "千克",
    "斤",
    "高压",
    "低压",
    "收缩压",
    "舒张压",
)
SYMPTOM_TERMS = (
    "症状",
    "疼痛",
    "疼",
    "痛",
    "酸",
    "痒",
    "麻",
    "胀",
    "不适",
    "难受",
    "咳嗽",
    "咳痰",
    "鼻塞",
    "流鼻涕",
    "打喷嚏",
    "喷嚏",
    "皮疹",
    "发热",
    "发烧",
    "头晕",
    "恶心",
    "呕吐",
)
CLINICIAN_RECORD_REFERENCE_TERMS = tuple(
    f"{provider}{noun}记录"
    for provider in CLINICIAN_PROVIDER_TERMS
    for noun in CLINICIAN_FEEDBACK_OBJECT_NOUNS
)
MEAL_TYPES = {
    "breakfast": ("早餐", "早饭", "早上"),
    "lunch": ("午餐", "午饭", "中饭", "中午"),
    "dinner": ("晚餐", "晚饭", "晚上"),
    "snack": ("加餐", "零食", "夜宵", "下午茶"),
}


def classify_agent_utterance(
    message: Any,
    *,
    reference_now: Optional[datetime] = None,
) -> AgentUtteranceIntent:
    raw = "" if message is None else str(message).strip()
    clinician_decision = classify_clinician_turn(raw)
    if clinician_decision.kind != "none":
        return _clinician_intent(raw, clinician_decision)

    normalized = _normalize(raw)
    if not normalized:
        return _intent(raw, normalized, "unknown", "unknown", "none", 0.0, "empty")

    has_read = _has_any(normalized, READ_ACTIONS)
    scope = _build_scope(
        normalized,
        focus=(_read_focus(normalized) if has_read else None),
        reference_now=reference_now,
    )
    domain = _infer_domain(normalized)
    has_question = _has_question_signal(normalized)
    has_write = _has_any(normalized, WRITE_ACTIONS)
    has_write_command = _has_explicit_write_command(normalized)
    has_negated_write = _has_negated_write(normalized)
    mutation = _mutation_operation(normalized)
    implicit_diet_correction = _is_diet_quantity_correction(
        normalized,
        domain=domain,
        has_question=has_question,
    )
    if mutation is None and implicit_diet_correction:
        mutation = "update"
    has_negated_mutation = _has_negated_mutation(normalized, mutation)
    has_advice = _has_any(normalized, ADVICE_ACTIONS)

    if _is_media_generation_request(normalized):
        return _intent(
            raw,
            normalized,
            "write",
            "aigc_media",
            "create",
            0.92,
            "media_generation_request",
            is_write=True,
            requires_reliable_tool_model=True,
        )

    is_diet_recalculate_update = (
        domain == "diet"
        and _has_any(normalized, DIET_RECALCULATE_ACTIONS)
        and _has_any(normalized, DIET_RECALCULATE_UPDATE_ACTIONS)
    )
    if is_diet_recalculate_update:
        if _has_any(normalized, MUTATION_NEGATIONS):
            return _intent(
                raw,
                normalized,
                "chat",
                "diet",
                "none",
                0.94,
                "negated_diet_recalculate_update",
                scope,
            )
        return _intent(
            raw,
            normalized,
            "mutate",
            "diet",
            "update",
            0.96,
            "diet_recalculate_update",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    plan_operation = _plan_operation(normalized, domain, has_question)

    if plan_operation == "update":
        return _intent(
            raw,
            normalized,
            "mutate",
            domain,
            "update",
            0.88,
            "plan_item_mutation",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if plan_operation == "create":
        return _intent(
            raw,
            normalized,
            "write",
            domain,
            "create",
            0.88,
            "plan_write_frame",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if _reminder_operation(normalized, domain, has_question, has_read) == "create":
        return _intent(
            raw,
            normalized,
            "write",
            "reminder",
            "create",
            0.88,
            "reminder_write_frame",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if has_negated_mutation:
        return _intent(raw, normalized, "chat", domain, "none", 0.82, "negated_mutation", scope)

    if mutation and has_question:
        if has_advice:
            return _intent(raw, normalized, "advice", domain, "analyze", 0.86, "mutation_advice", scope)
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

    if mutation:
        return _intent(
            raw,
            normalized,
            "mutate",
            domain,
            mutation,
            0.9,
            (
                "diet_quantity_correction"
                if implicit_diet_correction
                else "mutation_command"
            ),
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if has_advice:
        # 复合请求必须保留明确的写入能力。否则模型虽然理解了“记录后分析”，
        # 但 ToolGateway 会把 health_record 当成 advice 回合的越权写入而拦掉，
        # 用户最终只看到拒答。带问号的“吃了某药有什么副作用”仍是纯问答，
        # 不应因为“吃了”这个观察词而误记一笔健康记录。
        if has_write_command:
            return _intent(
                raw,
                normalized,
                "write",
                domain,
                "create",
                0.84,
                "compound_write_advice_frame",
                scope,
                is_write=True,
                requires_reliable_tool_model=True,
            )
        return _intent(raw, normalized, "advice", domain, "analyze", 0.86, "advice_frame", scope)

    if has_read or (
        _is_data_question(normalized, domain, has_question)
        and not _looks_like_observation_statement(normalized, domain, has_question)
        and not (
            domain == "symptom"
            and not has_question
            and _has_explicit_symptom_observation(normalized, domain, has_question)
        )
        and (not has_write or has_question)
    ):
        operation = "list" if has_read and not has_question else "ask"
        if _wants_table_or_list(normalized):
            operation = "list"
        return _intent(
            raw,
            normalized,
            "read",
            domain,
            operation,
            0.88,
            "read_frame",
            scope,
            requires_reliable_tool_model=domain == "clinical_context",
        )

    if has_negated_write:
        return _intent(raw, normalized, "chat", domain, "none", 0.78, "negated_write", scope)

    if (
        has_write
        or _has_explicit_observation_write(normalized, domain)
        or _has_explicit_symptom_observation(normalized, domain, has_question)
        or _has_explicit_event_write(normalized)
    ):
        return _intent(
            raw,
            normalized,
            "write",
            domain,
            "create",
            0.84,
            "write_frame" if has_write else "observed_measurement_frame",
            scope,
            is_write=True,
        )

    if has_question:
        return _intent(raw, normalized, "read", domain, "ask", 0.55, "question_frame", scope)

    return _intent(raw, normalized, "unknown", domain, "none", 0.35, "ambiguous", scope)


def _clinician_intent(
    raw: str,
    decision: ClinicianTurnDecision,
) -> AgentUtteranceIntent:
    frames = {
        "clinician_context": ("chat", "acknowledge", False, 0.96),
        "clinician_advice": ("advice", "analyze", False, 0.96),
        "explicit_doctor_feedback_write": ("write", "create", True, 0.99),
        "ambiguous_clinician_action": ("chat", "acknowledge", False, 0.98),
    }
    primary, operation, is_write, confidence = frames[decision.kind]
    return _intent(
        raw,
        _normalize(raw),
        primary,
        "clinical_context",
        operation,
        confidence,
        decision.reason_code,
        is_write=is_write,
        requires_reliable_tool_model=True,
    )


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


def _is_explicit_write_action_at(
    text: str,
    action: str,
    start: int,
) -> bool:
    left_context = text[:start]
    after = text[start + len(action):]
    if action == "记录" and after.startswith(RECORD_NOUN_SUFFIXES):
        return False
    return (
        start == 0
        or left_context.endswith(WRITE_COMMAND_PREFIXES)
        or (
            action == "记录"
            and after.startswith(("一下", "下来", "为", "到"))
        )
    )


def _has_bounded_water_marker(
    text: str,
    markers: tuple[str, ...],
) -> bool:
    """Match a complete water object, not an open-ended ``水*`` compound."""
    for marker in markers:
        start = text.find(marker)
        while start >= 0:
            after = text[start + len(marker):]
            if (
                not after
                or after[0] in WATER_OBJECT_BOUNDARY_CHARS
                or after[0].isdigit()
                or after.startswith(WATER_OBJECT_FOLLOWUP_TERMS)
            ):
                return True
            start = text.find(marker, start + len(marker))
    return False


def _has_water_signal(text: str) -> bool:
    """Match water intake without treating 碳水/水饺 as hydration."""
    if (
        _has_any(text, WATER_TERMS)
        or _has_any(text, WATER_QUERY_TERMS)
        or _has_any(text, WATER_STATUS_TERMS)
    ):
        return True
    if (
        _has_any(text, ("喝", "饮"))
        and (
            _has_bounded_water_marker(text, WATER_INTAKE_OBJECT_TERMS)
            or _has_bounded_water_marker(text, WATER_NAMED_OBJECT_TERMS)
        )
    ):
        return True
    if _has_explicit_write_command(text):
        if (
            _has_bounded_water_marker(text, WATER_INTAKE_OBJECT_TERMS)
            or _has_bounded_water_marker(text, WATER_NAMED_OBJECT_TERMS)
        ):
            return True
        if _has_bounded_water_marker(
            text,
            tuple(f"{unit}水" for unit in WATER_AMOUNT_UNITS),
        ):
            return True
    return (
        "水" in text
        and _has_any(text, ("喝了", "已喝"))
        and _has_any(text, WATER_AMOUNT_UNITS)
    )


def _has_question_signal(text: str) -> bool:
    return _has_any(text, QUESTION_SIGNALS)


def _wants_table_or_list(text: str) -> bool:
    return _has_any(text, ("列出", "列表", "表格", "汇总", "显示"))


def _has_negated_write(text: str) -> bool:
    if _has_any(text, WRITE_NEGATION_EXCEPTIONS):
        return False
    return _has_any(text, WRITE_NEGATIONS)


def _has_explicit_write_command(text: str) -> bool:
    """Distinguish a record command from a record used as evidence or a noun.

    ``记录`` is overloaded in Chinese: "根据 HRV 记录推断" names historical
    evidence, while "记录一下晚餐" asks us to persist data. Advice turns may
    contain either form, so only an imperative frame keeps write capability.
    This stays deliberately lexical and structural rather than falling back to
    a broad regex keyword router.
    """
    command_actions = (
        "记录",
        "记一下",
        "记下",
        "打个卡",
        "打卡",
        "新增",
        "录入",
        "保存",
        "写入",
        "存下来",
    )
    for action in command_actions:
        start = text.find(action)
        while start >= 0:
            if _is_explicit_write_action_at(text, action, start):
                return True
            start = text.find(action, start + len(action))
    return False


def _mutation_operation(text: str) -> Optional[str]:
    for operation, phrases in MUTATE_ACTIONS.items():
        if _has_any(text, phrases):
            return operation
    return None


def _is_diet_quantity_correction(
    text: str,
    *,
    domain: str,
    has_question: bool,
) -> bool:
    """Recognize a factual partial-meal correction without treating advice as a write."""
    if domain != "diet" or has_question or _meal_type(text) is None:
        return False
    correction_signals = (
        "实际",
        "没吃那么多",
        "没有吃那么多",
        "没全吃",
        "没有全吃",
        "没吃完",
        "没有吃完",
        "只吃",
        "只有吃",
    )
    partial_amount_signals = (
        "一半",
        "半份",
        "四分之一",
        "三分之一",
        "三分之二",
        "五分之一",
        "五分之二",
        "五分之三",
        "五分之四",
    )
    return _has_any(text, correction_signals) and _has_any(
        text, partial_amount_signals
    )


def _all_phrase_positions(text: str, phrase: str) -> list[int]:
    positions: list[int] = []
    start = text.find(phrase)
    while start >= 0:
        positions.append(start)
        start = text.find(phrase, start + len(phrase))
    return positions


def _has_negated_mutation(text: str, operation: Optional[str]) -> bool:
    if not operation or _has_any(text, MUTATION_NEGATION_EXCEPTIONS):
        return False
    action_positions = [
        position
        for phrase in MUTATE_ACTIONS[operation]
        for position in _all_phrase_positions(text, phrase.lower())
    ]
    if not action_positions:
        return False
    negation_positions = [
        position
        for negation in MUTATION_NEGATIONS
        for position in _all_phrase_positions(text, negation)
    ]
    return any(
        0 <= action_position - negation_position <= 12
        for action_position in action_positions
        for negation_position in negation_positions
    )


def _infer_domain(text: str) -> str:
    if _has_any(text, MEDIA_TERMS):
        return "aigc_media"
    if _has_any(text, REMINDER_TERMS):
        return "reminder"
    if _has_any(text, CLINICIAN_RECORD_REFERENCE_TERMS):
        return "clinical_context"
    if _has_water_signal(text):
        return "water"
    if _has_any(text, MEDICATION_TERMS):
        return "medication"
    if _has_any(text, SUPPLEMENT_TERMS):
        return "supplement"
    if _has_any(text, DIET_TERMS):
        return "diet"
    if _has_any(text, METRIC_TERMS):
        return "metric"
    if _has_any(text, SYMPTOM_TERMS):
        return "symptom"
    if _has_any(text, PLAN_TERMS):
        return "plan"
    return "unknown"


def _plan_operation(text: str, domain: str, has_question: bool) -> Optional[str]:
    """Recognize explicit plan actions without turning plan advice into writes."""
    if domain != "plan" or has_question:
        return None
    if _has_any(text, PLAN_UPDATE_ACTIONS):
        return "update"
    if _has_any(text, PLAN_CREATE_ACTIONS):
        return "create"
    return None


def _reminder_operation(
    text: str,
    domain: str,
    has_question: bool,
    has_read: bool,
) -> Optional[str]:
    """Recognize reminder creation before embedded targets like water or meds.

    In phrases such as "提醒我喝水", the health target is the reminder content,
    not an immediate water/medication record.
    """
    if domain != "reminder" or has_question or has_read:
        return None
    if _has_any(text, REMINDER_CREATE_ACTIONS):
        return "create"
    return None


def _is_media_generation_request(text: str) -> bool:
    """Recognize an explicit creative request without making media Q&A a write.

    This follows the semantic-frame approach used for health intents: an
    external media target plus a creation action is required.  A question such
    as "AIGC 短视频怎么做" remains advice/read unless the user also supplies an
    affirmative provider disclosure for the requested generation.
    """
    if not _has_any(text, MEDIA_TERMS):
        return False
    has_confirmation = (
        "确认" in text
        and ("发送" in text or "交给" in text or "授权" in text)
        and ("百炼" in text or "万相" in text or "wan" in text)
    )
    if _has_question_signal(text) and not has_confirmation:
        return False
    return has_confirmation or _has_any(text, MEDIA_CREATE_ACTIONS)


def _is_data_question(text: str, domain: str, has_question: bool) -> bool:
    if has_question and domain != "unknown":
        return True
    if domain == "unknown":
        return False
    return _has_any(text, ("今天", "昨天", "本周", "这周", "最近", "昨晚", "数据", "情况", "状态"))


def _looks_like_observation_statement(text: str, domain: str, has_question: bool) -> bool:
    """Keep a bare health observation out of the read route.

    Temporal words such as ``昨晚`` are useful query scope, but they also occur
    in statements like ``昨晚睡了十个小时``. Without this guard the classifier
    turns an observation into an implicit query, and a downstream model may try
    to write it with incomplete fields or answer the wrong question.
    """
    if has_question or domain != "metric":
        return False
    return _has_any(
        text,
        (
            "睡了",
            "睡得",
            "睡眠很好",
            "睡眠不错",
            "睡眠不好",
            "醒了",
            "跑了",
            "走了",
            "训练了",
            "运动了",
            "锻炼了",
        ),
    )


def _has_explicit_observation_write(text: str, domain: str) -> bool:
    """Recognize a stated observation without promoting a query into a write.

    This composes domain, observation and quantity signals.  It is deliberately
    not a command regular-expression router: capability policy remains the
    authority for whether a resulting tool request may run.
    """
    has_ascii_number = any(char.isdigit() for char in text)
    if domain == "water":
        has_drink_action = any(token in text for token in ("喝", "饮"))
        has_amount = has_ascii_number or any(
            phrase in text for phrase in ("一杯", "两杯", "三杯", "半杯", "一瓶", "半瓶")
        )
        return has_drink_action and has_amount
    if domain != "metric" or not has_ascii_number:
        return False
    return any(
        marker in text
        for marker in ("体重", "kg", "公斤", "千克", "斤", "血压", "高压", "低压", "收缩压", "舒张压")
    )


def _has_explicit_symptom_observation(
    text: str,
    domain: str,
    has_question: bool,
) -> bool:
    """Recognize a declarative symptom without turning a symptom question into a write."""
    if domain != "symptom" or has_question:
        return False
    return _has_any(text, SYMPTOM_TERMS)


def _has_explicit_event_write(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "准备开始睡觉",
            "准备入睡",
            "开始睡眠",
            "开始入睡",
            "上床睡觉",
        )
    )


def _read_focus(text: str) -> str:
    last_end = -1
    for phrase in READ_ACTIONS:
        idx = text.rfind(phrase.lower())
        if idx >= 0:
            last_end = max(last_end, idx + len(phrase))
    return text[last_end:] if last_end >= 0 else text


def _build_scope(
    text: str,
    *,
    focus: Optional[str] = None,
    reference_now: Optional[datetime] = None,
) -> dict[str, str]:
    scope_text = focus if focus is not None else text
    scope: dict[str, str] = {}
    date_value = _relative_date(scope_text, reference_now=reference_now) or (
        None if focus is None else _relative_date(text, reference_now=reference_now)
    )
    if date_value:
        scope["date"] = date_value
    meal_type = _meal_type(scope_text)
    if meal_type:
        scope["meal_type"] = meal_type
    return scope


def _relative_date(
    text: str,
    *,
    reference_now: Optional[datetime] = None,
) -> Optional[str]:
    today = (reference_now or datetime.now(BJ)).date()
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
