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
import unicodedata

from app.services.clinician_provenance_guard import (
    ClinicianTurnDecision,
    classify_clinician_turn,
)
from app.services.intake_intent_classifier import classify_intake_intent

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
    WRITE_COMMAND_ACTIONS,
    WRITE_COMMAND_PREFIXES,
)
from app.services.write_intent_scope import (
    has_negated_write_scope,
    is_historical_write_reference,
    is_write_capability_question,
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
MEDIA_SHORTHAND_TERMS = (
    "张图",
    "幅图",
    "新图",
    "旧图",
    "餐图",
    "运动图",
    "人物图",
    "宣传图",
    "配图",
    "插图",
    "效果图",
)
# ``片`` cannot be a free substring signal: it also appears in ``图片`` and
# routes meal-photo recording into medication.  Known medication + dose-unit
# utterances are already resolved by ``parse_medication_intake_batch`` above.
MEDICATION_TERMS = ("药", "服药", "用药", "胃药", "药物", "胶囊")
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

DECLARATIVE_OBSERVATION_ACTIONS = (
    "吃了",
    "喝了",
    "服药",
    "已服用",
    "已吃",
    "已喝",
)
WRITE_REQUEST_HELPERS = (
    "别忘了",
    "我想请你",
    "我想请",
    "我想",
    "麻烦帮我",
    "麻烦你",
    "可不可以",
    "能不能",
    "请你",
    "帮我",
    "帮忙",
    "给我",
    "替我",
    "为我",
    "可以",
    "能否",
    "可否",
    "麻烦",
    "请",
    "能",
)
POLITE_WRITE_PREFIXES = ("可以", "能否", "可否", "可不可以", "能不能", "能")
WRITE_CLAUSE_BOUNDARIES = (
    "然后",
    "再分析",
    "再告诉我",
    "并分析",
    "并告诉我",
    "，",
    ",",
    "。",
    "；",
    ";",
)


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
    media_control_text = _normalize_media_control(raw)
    if not normalized:
        return _intent(raw, normalized, "unknown", "unknown", "none", 0.0, "empty")

    has_read = _has_any(normalized, READ_ACTIONS) or is_historical_write_reference(
        normalized
    )
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
    question_without_write_command = has_question and not has_write_command

    if _is_media_generation_request(media_control_text):
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
        if has_negated_write:
            return _intent(
                raw,
                normalized,
                "advice",
                domain,
                "analyze",
                0.9,
                "negated_write_advice_frame",
                scope,
            )
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

    if has_read and has_write_command and not has_negated_write:
        return _intent(
            raw,
            normalized,
            "write",
            domain,
            "create",
            0.88,
            "compound_write_read_frame",
            scope,
            is_write=True,
            requires_reliable_tool_model=True,
        )

    if has_read or question_without_write_command or (
        _is_data_question(normalized, domain, has_question)
        and not has_write_command
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
        has_write_command
        or _has_any(normalized, DECLARATIVE_OBSERVATION_ACTIONS)
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


def _normalize_media_control(value: str) -> str:
    """Normalize media control text without erasing authorization boundaries."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", str(value or ""))
        if unicodedata.category(character) != "Cf"
    ).strip().lower()


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
    if after.startswith(("过", "了")):
        return False
    if action == "记录" and after.startswith(("一下", "下来", "为", "到")):
        return True
    local_after = _before_first_boundary(after, WRITE_CLAUSE_BOUNDARIES)
    if action == "记录" and start == 0 and _has_question_signal(local_after):
        return False
    clause_left = _after_last_boundary(left_context, WRITE_CLAUSE_BOUNDARIES)
    return start == 0 or not clause_left or left_context.endswith(WRITE_COMMAND_PREFIXES)


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
    return has_negated_write_scope(text)


def _strip_write_request_helper(text: str) -> str:
    return _strip_leading_tokens(text, WRITE_REQUEST_HELPERS)


def _strip_leading_tokens(
    text: str,
    tokens: tuple[str, ...],
    *,
    max_tokens: int = 8,
) -> str:
    """Consume a bounded sequence of request-grammar tokens from the left."""
    remainder = text
    ordered_tokens = tuple(sorted(tokens, key=len, reverse=True))
    for _ in range(max_tokens):
        matched = next(
            (token for token in ordered_tokens if remainder.startswith(token)),
            None,
        )
        if matched is None:
            break
        remainder = remainder[len(matched):]
    return remainder


def _before_first_boundary(text: str, boundaries: tuple[str, ...]) -> str:
    positions = [text.find(boundary) for boundary in boundaries]
    found = [position for position in positions if position >= 0]
    return text if not found else text[:min(found)]


def _after_last_boundary(text: str, boundaries: tuple[str, ...]) -> str:
    end_positions = [
        position + len(boundary)
        for boundary in boundaries
        if (position := text.rfind(boundary)) >= 0
    ]
    return text if not end_positions else text[max(end_positions):]


def _has_explicit_write_command(text: str) -> bool:
    """Distinguish a record command from a record used as evidence or a noun.

    ``记录`` is overloaded in Chinese: "根据 HRV 记录推断" names historical
    evidence, while "记录一下晚餐" asks us to persist data. Advice turns may
    contain either form, so only an imperative frame keeps write capability.
    This stays deliberately lexical and structural rather than falling back to
    a broad regex keyword router.
    """
    if is_write_capability_question(text) or is_historical_write_reference(text):
        return False
    direct_request = _strip_write_request_helper(text)
    if direct_request != text and direct_request.startswith(WRITE_COMMAND_ACTIONS):
        return True
    for prefix in POLITE_WRITE_PREFIXES:
        if not text.startswith(prefix):
            continue
        remainder = _strip_write_request_helper(text[len(prefix):])
        if remainder.startswith(WRITE_COMMAND_ACTIONS):
            return True
    for action in WRITE_COMMAND_ACTIONS:
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


def _has_symptom_signal(text: str) -> bool:
    """Avoid treating common lexical compounds as one-character symptoms."""
    for false_positive in ("麻烦", "酸奶", "心酸", "辛酸", "痛快", "痛点", "疼爱"):
        text = text.replace(false_positive, "")
    return _has_any(text, SYMPTOM_TERMS)


def _infer_domain(text: str) -> str:
    # Generic attachment nouns ("图片" / "图像") are not enough to make a
    # health-recording request an AIGC generation turn.  Preserve AIGC priority
    # only when the user also asks to create media; otherwise let concrete
    # health domains such as 早餐 / 用药 win before the residual media-Q&A case.
    if _is_media_generation_request(text):
        return "aigc_media"
    if _has_any(text, REMINDER_TERMS):
        return "reminder"
    if _has_any(text, CLINICIAN_RECORD_REFERENCE_TERMS):
        return "clinical_context"
    if _has_water_signal(text):
        return "water"
    intake_kind = classify_intake_intent(text).kind
    if intake_kind == "supplement":
        return "supplement"
    if intake_kind == "medication":
        # Suffixes such as “霉素” are useful recall signals but are not a safe
        # medication identity boundary. Only promote a medication-like phrase
        # when the deterministic parser resolves a curated medication name;
        # user-owned medication names are added later at the database boundary.
        from app.services.medication_intake_batch import parse_medication_intake_batch

        if parse_medication_intake_batch(text) is not None:
            return "medication"
    if _has_any(text, MEDICATION_TERMS):
        return "medication"
    if _has_any(text, SUPPLEMENT_TERMS):
        return "supplement"
    if _has_any(text, DIET_TERMS):
        return "diet"
    if _has_any(text, METRIC_TERMS):
        return "metric"
    if _has_symptom_signal(text):
        return "symptom"
    if _has_any(text, PLAN_TERMS):
        return "plan"
    if _has_any(text, MEDIA_TERMS) and not _has_any(text, WRITE_ACTIONS):
        # Keep media Q&A typed, but never interpret any generic write wording
        # (imperative or reported as already done) as permission to create an
        # AIGC draft. Attached-image writes stay on the full tool set so vision
        # can determine their real domain.
        return "aigc_media"
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


def _media_clauses(text: str) -> list[str]:
    """Split instruction-sized clauses without regex or losing order."""
    # Colons intentionally stay inside a clause so attribution such as
    # ``他说：请生成...`` cannot be detached into a first-person command.
    boundaries = frozenset("，。；！？,.!?;")
    clauses: list[str] = []
    start = 0
    for position, character in enumerate(text):
        if character not in boundaries:
            continue
        clause = text[start:position].strip()
        if clause:
            clauses.append(clause)
        start = position + 1
    trailing = text[start:].strip()
    if trailing:
        clauses.append(trailing)
    return clauses


MEDIA_REPORT_SCOPE_TERMS = (
    "原话",
    "工单内容",
    "原问题",
    "聊天记录",
    "邮件正文",
    "通知内容",
    "原文",
    "正文",
)
MEDIA_REPORTING_SIGNALS = (
    *MEDIA_REPORT_SCOPE_TERMS,
    "客服",
    "朋友",
    "对方",
    "文档",
    "消息",
    "邮件",
    "通知",
    "工单",
    "说",
    "问",
    "询问",
    "他说",
    "她说",
    "他们说",
    "系统说",
    "表示",
    "提到",
    "写道",
    "告诉",
    "告知",
    "转告",
    "回复",
    "注明",
    "称",
    "要求",
)
MEDIA_REPORTING_SUFFIXES = (
    "说",
    "问",
    "询问",
    "表示",
    "提到",
    "写道",
    "告诉",
    "告知",
    "转告",
    "回复",
    "答复",
    "注明",
    "称",
    "要求",
    "原话",
    "原话是",
    "内容",
    "内容是",
    "内容为",
    "如下",
    "如下所示",
    "是",
    "为",
)


def _is_report_grouping_quote(text: str, position: int) -> bool:
    """Treat grouping punctuation as quotation only after a report label."""
    prefix = text[:position].rstrip().rstrip("：:").rstrip()
    return prefix.endswith(MEDIA_REPORTING_SUFFIXES)


def _mask_media_quoted_content(text: str) -> str:
    """Remove quoted payload from authorization control while keeping its place."""
    quote_pairs = {
        "“": "”",
        "‘": "’",
        "「": "」",
        "『": "』",
        "《": "》",
        "〈": "〉",
        '"': '"',
        "'": "'",
        "`": "`",
    }
    report_grouping_pairs = {
        "（": "）",
        "(": ")",
        "【": "】",
        "[": "]",
        "〔": "〕",
        "〖": "〗",
        "｛": "｝",
        "{": "}",
    }
    masked: list[str] = []
    expected_close: Optional[str] = None
    for position, character in enumerate(text):
        if expected_close is not None:
            if character == expected_close:
                expected_close = None
            continue
        close = quote_pairs.get(character)
        if close is None and _is_report_grouping_quote(text, position):
            close = report_grouping_pairs.get(character)
        if close is not None:
            expected_close = close
            masked.append("引文")
            continue
        masked.append(character)
    return "".join(masked)


def _has_hard_media_report_scope(text: str) -> bool:
    """Fail closed when a leading ``label:`` frames the media instructions."""
    control_positions = [
        position
        for action in (*MEDIA_CREATE_ACTIONS, "确认", *MEDIA_TRANSFER_ACTIONS)
        for position in _all_phrase_positions(text, action)
    ]
    if not control_positions:
        return False
    first_control = min(control_positions)
    leading_scope = text[:first_control]
    if any(separator in leading_scope for separator in ("：", ":")):
        return True
    if not _has_any(leading_scope, MEDIA_REPORT_SCOPE_TERMS):
        return False
    closing_position = max(
        (text.rfind(anchor) for anchor in ("以上", "上述", "前面", "前述", "上文")),
        default=-1,
    )
    if closing_position <= first_control:
        return False
    closing_scope = text[closing_position:]
    return _has_any(closing_scope, ("是", "为")) and _has_any(
        closing_scope,
        MEDIA_REPORT_SCOPE_TERMS,
    )


def _media_action_occurrences(
    clause: str,
    actions: tuple[str, ...],
) -> list[tuple[int, str]]:
    """Return ordered action spans, preferring the longest phrase per offset."""
    occurrences = sorted(
        (
            (position, action)
            for action in actions
            for position in _all_phrase_positions(clause, action)
        ),
        key=lambda item: (item[0], -len(item[1])),
    )
    deduplicated: list[tuple[int, str]] = []
    seen_positions: set[int] = set()
    for position, action in occurrences:
        if position in seen_positions:
            continue
        seen_positions.add(position)
        deduplicated.append((position, action))
    return deduplicated


MEDIA_PROVIDER_TERMS = ("百炼", "万相", "wan")
MEDIA_MECHANISM_TERMS = (
    *MEDIA_PROVIDER_TERMS,
    "ai",
    "人工智能",
    "生成式",
    "模型",
    "云端",
    "外部服务",
    "第三方",
    "联网",
    "网络",
)
MEDIA_TRANSFER_ACTIONS = ("上传给", "上传到", "发送", "发给", "交给", "授权")


def is_closed_aigc_provider_confirmation(value: str) -> bool:
    """Match only the reviewed current-user provider consent grammar."""
    normalized_value = unicodedata.normalize("NFKC", str(value or ""))
    if any(character.isspace() for character in normalized_value):
        return False
    text = "".join(
        character
        for character in normalized_value
        if unicodedata.category(character) != "Cf"
    ).lower()
    if text.endswith(("。", ".", "!", "！")):
        text = text[:-1]
    for tail in ("即可", "就好", "就行", "吧"):
        if text.endswith(tail):
            text = text[:-len(tail)]
            break

    confirmation_prefixes = {
        "确认",
        "我同意并确认",
        "最后我明确确认",
        "此刻我确认",
        "我在此确认",
        "经过考虑我确认",
        "不过我确认",
        "现在由我确认",
        "我决定确认",
        "重新考虑后我明确确认",
        "经我确认",
        "此次由我确认",
        "随后我确认",
        "之后我明确确认",
    }
    for temporal in ("", "现在", "最终", "这次", "此次"):
        for modifier in ("", "现在", "明确", "亲自", "本人", "再次明确"):
            confirmation_prefixes.add(f"{temporal}我{modifier}确认")
    prefix = next(
        (candidate for candidate in confirmation_prefixes if text.startswith(candidate)),
        None,
    )
    if prefix is None:
        return False
    body = text[len(prefix):]
    outputs = (
        "短视频",
        "这张早餐图片",
        "新图片",
        "新图",
        "图片",
        "图像",
        "海报",
        "封面",
        "视频",
        "图",
    )
    providers = MEDIA_PROVIDER_TERMS
    allowed_bodies = {
        f"{lead}{output}{transfer}{provider}"
        for lead in ("把", "将")
        for output in outputs
        for transfer in ("发送给", "发给", "上传给", "上传到", "交给")
        for provider in providers
    }
    allowed_bodies.update(
        f"{transfer}{output}{destination}{provider}"
        for transfer in ("发送", "上传")
        for output in outputs
        for destination in ("给", "到")
        for provider in providers
    )
    allowed_bodies.update(
        f"{output}交给{provider}"
        for output in outputs
        for provider in providers
    )
    allowed_bodies.update(f"授权{provider}" for provider in providers)
    return body in allowed_bodies
MEDIA_CONTENT_MARKERS = (
    "写着",
    "文字为",
    "文字是",
    "标语为",
    "标语是",
    "标题为",
    "标题是",
    "主题为",
    "主题是",
    "内容为",
    "内容是",
    "文案为",
    "文案是",
    "画面显示",
    "画面为",
    "画面是",
    "口号为",
    "口号是",
    "描述为",
    "描述是",
    "旁白为",
    "旁白是",
    "呈现",
    "字幕为",
    "字幕是",
    "包含文字",
    "配文为",
    "配文是",
    "配文",
    "正文为",
    "正文是",
    "上面显示",
    "上面写着",
    "含有",
    "带有",
    "印有",
    "写上",
    "讲解",
    "介绍",
    "演示",
    "包含",
    "展示",
    "关于",
)
MEDIA_ATTRIBUTION_CONTENT_MARKERS = (
    "文字为",
    "文字是",
    "标语为",
    "标语是",
    "标题为",
    "标题是",
    "主题为",
    "主题是",
    "内容为",
    "内容是",
    "文案为",
    "文案是",
    "口号为",
    "口号是",
    "描述为",
    "描述是",
    "字幕为",
    "字幕是",
    "内容如下",
)
MEDIA_ATTRIBUTION_MARKERS = (
    "引用",
    "引文",
    "例句",
    "示例",
    "示范",
    "不要执行",
    "他说",
    "她说",
    "他们说",
    "系统说",
    "原文",
    "复述",
    "转述",
    "引述",
    "范例",
    "样例",
    "演示",
    "仅供参考",
    "仅供测试",
    "测试文本",
    "测试语句",
    "内容如下",
)

MEDIA_PROVIDER_CONTROL_TRANSITIONS = (
    "但是",
    "不过",
    "可是",
    "然而",
    "另外",
    "同时",
    "此外",
    "但",
    "且",
    "而",
    "并",
)
MEDIA_PROVIDER_CONTROL_TERMS = (
    *MEDIA_MECHANISM_TERMS,
    *MEDIA_TRANSFER_ACTIONS,
    "上传",
    "传输",
    "传给",
    "送往",
    "提交",
    "共享",
    "分享",
    "外传",
    "同步",
    "传",
    "出网",
    "远程",
    "服务器",
    "云接口",
    "调用",
    "设备内",
    "本地",
    "离线",
    "数据",
    "素材",
    "文件",
)


def _media_content_start(clause: str) -> Optional[int]:
    positions = [
        position
        for marker in MEDIA_CONTENT_MARKERS
        for position in _all_phrase_positions(clause, marker)
    ]
    return min(positions) if positions else None


def _media_provider_control_switch_start(
    clause: str,
    payload_start: int,
    payload_end: int,
) -> Optional[int]:
    positions = sorted(
        position
        for marker in MEDIA_PROVIDER_CONTROL_TRANSITIONS
        for position in _all_phrase_positions(clause, marker)
        if payload_start < position < payload_end
    )
    for position in positions:
        control_tail = clause[position:payload_end]
        has_restriction = _has_media_denial_signal(control_tail) or _has_any(
            control_tail,
            ("仅限", "只限", "仅在", "只在"),
        )
        if has_restriction and _has_any(
            control_tail,
            MEDIA_PROVIDER_CONTROL_TERMS,
        ):
            return position
    return None


def _is_nominal_media_action(clause: str, position: int, action: str) -> bool:
    """Reject action substrings embedded in nouns or factual technology labels."""
    suffix = clause[position + len(action):]
    common_nominal_suffixes = (
        "器",
        "方",
        "者",
        "端",
        "部",
        "室",
        "工具",
        "平台",
        "服务",
        "团队",
        "引擎",
        "系统",
        "产品",
        "接口",
        "行业",
        "课程",
        "人员",
        "岗位",
        "按钮",
        "方案",
        "组件",
        "公司",
        "机构",
        "框架",
        "部门",
        "模块",
        "应用",
    )
    nominal_suffixes = {
        "生成": ("式", "模型", "技术", "软件", "功能", "能力", "算法", "器"),
        "制作": ("软件", "工具", "流程", "技术", "功能"),
        "创作": ("软件", "工具", "流程", "技术", "功能"),
    }
    return suffix.startswith(
        (*common_nominal_suffixes, *nominal_suffixes.get(action, ()))
    )


def _is_explicit_provider_confirmation_at(clause: str, position: int) -> bool:
    """Require a command-shaped provider confirmation, not a factual mention."""
    return (
        is_closed_aigc_provider_confirmation(clause)
        and clause.find("确认") == position
    )


def _media_attribution_precedes_control(clause: str) -> bool:
    """Detect quoted/reported instructions before their first control action."""
    if clause.startswith("为了"):
        return False
    if _is_quoted_media_prompt_leadin(clause):
        return False
    attribution_positions = [
        position
        for marker in (*MEDIA_ATTRIBUTION_MARKERS, *MEDIA_REPORT_SCOPE_TERMS)
        for position in _all_phrase_positions(clause, marker)
    ]
    # ``X说`` is an open class (客服/朋友/对方/医生/系统...), so recognize the
    # reporting verb structurally instead of trying to enumerate speakers.
    for reporting_verb in (
        "说",
        "问",
        "询问",
        "表示",
        "提到",
        "写道",
        "告诉",
        "告知",
        "转告",
        "回复",
        "注明",
        "称",
    ):
        attribution_positions.extend(
            _all_phrase_positions(clause, reporting_verb)
        )
    attribution_content_positions = [
        position
        for marker in MEDIA_ATTRIBUTION_CONTENT_MARKERS
        for position in _all_phrase_positions(clause, marker)
    ]
    attribution_positions.extend(attribution_content_positions)
    if not attribution_positions:
        return False
    control_positions = [
        position
        for action in (*MEDIA_CREATE_ACTIONS, "确认", *MEDIA_TRANSFER_ACTIONS)
        for position in _all_phrase_positions(clause, action)
    ]
    return not control_positions or min(attribution_positions) <= min(control_positions)


CURRENT_USER_RECLAIM_SIGNALS = (
    "回到我本人",
    "这次听我的",
    "现在由我要求",
    "我个人决定",
    "按我的要求",
    "以下是我的要求",
    "我的新要求",
    "我的要求",
    "至于我",
)


def _has_current_user_reclaim_signal(text: str) -> bool:
    return _has_any(text, CURRENT_USER_RECLAIM_SIGNALS)


def _is_attribution_override_clause(clause: str) -> bool:
    """Recognize an explicit switch back to the current user's own intent."""
    return _has_current_user_reclaim_signal(clause) or clause.startswith(
        (
            "但请",
            "但我想",
            "但我想要",
            "但我要",
            "不过我想",
            "不过我想要",
            "不过我要",
            "但是我想",
            "但是我想要",
            "但是我要",
            "可是我想",
            "可是我想要",
            "可是我要",
            "然而我想",
            "然而我想要",
            "然而我要",
            "我现在想",
            "我现在想要",
            "我现在要",
            "现在我想",
            "现在我想要",
            "现在我要",
            "不过请帮我",
            "但是请帮我",
            "可是请帮我",
            "但我现在想",
            "但我现在想要",
            "但我现在要",
            "不过我现在想",
            "不过我现在想要",
            "不过我现在要",
            "但是我现在想",
            "但是我现在想要",
            "但是我现在要",
            "可是我现在想",
            "可是我现在想要",
            "可是我现在要",
            "可我想",
            "可我想要",
            "可我要",
            "现在请",
            "换成",
            "我的要求是",
            "我的新要求是",
            "随后请",
            "之后请",
            "然后请",
            "接着请",
            "最终我想",
            "最终我想要",
            "最终我要",
            "最后我想",
            "最后我想要",
            "最后我要",
            "现在改为",
            "现在改成",
            "至于我",
        )
    )


def _is_explicit_provider_confirmation_prefix(prefix: str) -> bool:
    """Accept affirmative first-person modifiers without opening factual prose."""
    if _is_explicit_media_command_prefix(prefix) or prefix == "我":
        return True
    normalized = prefix
    for deliberation in ("经过考虑", "重新考虑后", "考虑后"):
        if normalized.startswith(deliberation):
            normalized = normalized[len(deliberation):]
            break
    for transition in (
        "不过",
        "随后",
        "之后",
        "然后",
        "接着",
        "但是",
        "可是",
        "但",
    ):
        if normalized.startswith(transition):
            normalized = normalized[len(transition):]
            break
    for temporal in ("最终", "最后", "此刻", "现在", "这次", "此次"):
        if normalized.startswith(temporal):
            normalized = normalized[len(temporal):]
            break
    if normalized.startswith("由我"):
        normalized = normalized[len("由"):]
    if normalized.startswith("经我"):
        normalized = normalized[len("经"):]
    if not normalized.startswith("我"):
        return False
    return normalized[len("我"):] in (
        "",
        "在此",
        "本人",
        "亲自",
        "决定",
        "现在",
        "明确",
        "同意",
        "同意并",
        "已",
        "已经",
        "再次",
        "再次明确",
        "正式",
    )


def _is_bare_media_command_target(clause: str, action_end: int) -> bool:
    """Require a bare action to take a compact noun phrase as its object."""
    output_terms = (
        "图片",
        "图像",
        "海报",
        "封面",
        "短视频",
        "视频",
        *MEDIA_SHORTHAND_TERMS,
    )
    output_spans = [
        (position, position + len(term))
        for term in output_terms
        for position in _all_phrase_positions(clause, term)
        if position >= action_end
    ]
    if not output_spans:
        return False
    output_start, output_end = max(output_spans, key=lambda span: span[1])
    if not _has_direct_media_request_tail(clause, output_end):
        return False
    # Whitespace is not an authorization boundary for an explicit creative
    # command (for example, ``生成 5 秒竖屏短视频``). Provider confirmations use
    # the separate closed grammar above and continue to reject any whitespace.
    descriptor = "".join(clause[action_end:output_start].split())
    for quantity in ("一张", "两张", "三张", "几张", "一幅", "一个"):
        if descriptor.startswith(quantity):
            descriptor = descriptor[len(quantity):]
            break
    duration_descriptor = descriptor
    for orientation in ("竖屏", "横屏"):
        if duration_descriptor.endswith(orientation):
            duration_descriptor = duration_descriptor[: -len(orientation)]
            break
    if duration_descriptor.endswith("秒"):
        duration_text = duration_descriptor[:-1]
        if duration_text.isdigit() and 3 <= int(duration_text) <= 15:
            return True
    if not descriptor or "的" in descriptor:
        return True
    # Without an attributive marker, keep the implicit object deliberately
    # short. Complex bare prose must use an explicit directive such as ``请``.
    return len(descriptor) <= 3


def _is_safe_media_leadin(clause: str) -> bool:
    """Permit known user context without treating arbitrary prose as a command."""
    if clause.startswith(("为了", "关于", "不是让你")):
        return True
    if clause == "至于我" or _has_current_user_reclaim_signal(clause):
        return True
    if _is_quoted_media_prompt_leadin(clause):
        return True
    if _has_question_signal(clause) and _has_any(
        clause,
        (*MEDIA_TERMS, *MEDIA_SHORTHAND_TERMS, *MEDIA_CREATE_ACTIONS, "按钮"),
    ):
        return clause.startswith(
            (
                *MEDIA_TERMS,
                *MEDIA_SHORTHAND_TERMS,
                *MEDIA_CREATE_ACTIONS,
                "如何",
                "为什么",
                "怎么",
                "能否",
                "可以",
                "请问",
                "这个按钮",
                "上一张",
            )
        )
    if _has_any(
        clause,
        (
            "图片不错",
            "图像不错",
            "上一张",
            "旧任务",
            "旧方案",
            "没有其他要求",
        ),
    ):
        return True
    has_provider_control = _has_any(
        clause,
        (
            *MEDIA_MECHANISM_TERMS,
            *MEDIA_TRANSFER_ACTIONS,
            "上传",
            "传输",
            "送往",
            "出网",
            "远程",
            "服务器",
            "设备内",
            "本地",
            "离线",
        ),
    )
    return not _has_any(
        clause,
        (
            *MEDIA_ATTRIBUTION_MARKERS,
            *MEDIA_CREATE_ACTIONS,
            *MEDIA_TRANSFER_ACTIONS,
            *MEDIA_PROVIDER_TERMS,
        ),
    ) and not _is_media_report_leadin(clause) and not (
        has_provider_control and _has_media_denial_signal(clause)
    )


def _is_media_report_leadin(clause: str) -> bool:
    normalized = clause.rstrip().rstrip("：:").rstrip()
    return normalized.endswith(MEDIA_REPORTING_SUFFIXES)


def _is_media_payload_clause(clause: str) -> bool:
    return clause.startswith(MEDIA_CONTENT_MARKERS)


def _is_quoted_media_prompt_leadin(clause: str) -> bool:
    """Recognize a quoted prompt supplied by the current user before a command."""
    if "引文" not in clause or _has_any(clause, MEDIA_REPORTING_SIGNALS):
        return False
    return _is_media_payload_clause(clause) or clause.startswith(
        ("请以引文", "用引文", "标题用引文")
    )


def _has_explicit_media_create_frame(clause: str) -> bool:
    return any(
        not _is_nominal_media_action(clause, position, action)
        and _media_create_output_end_if_authorized(clause, position, action)
        is not None
        for position, action in _media_action_occurrences(
            clause,
            MEDIA_CREATE_ACTIONS,
        )
    )


def _media_create_output_end_if_authorized(
    clause: str,
    position: int,
    action: str,
) -> Optional[int]:
    """Return the payload boundary for one complete current-user create frame."""
    action_end = position + len(action)
    prefix = clause[:position]
    output_end = _media_output_end_after(clause, action_end)
    allows_prefix_target = prefix.endswith("也") and _has_any(
        prefix,
        (*MEDIA_TERMS, *MEDIA_SHORTHAND_TERMS),
    )
    if not (output_end is not None or allows_prefix_target):
        return None
    if not _is_explicit_media_command_prefix(prefix):
        return None
    if prefix == "" and not _is_bare_media_command_target(clause, action_end):
        return None
    if output_end is not None:
        return (
            output_end
            if _has_direct_media_request_tail(clause, output_end)
            else None
        )
    if allows_prefix_target and clause[action_end:] in ("一个", "一张", "一幅"):
        return action_end
    return None


def _media_output_end_after(clause: str, action_end: int) -> Optional[int]:
    output_terms = (
        "图片",
        "图像",
        "海报",
        "封面",
        "短视频",
        "视频",
        *MEDIA_SHORTHAND_TERMS,
    )
    ends = [
        position + len(term)
        for term in output_terms
        for position in _all_phrase_positions(clause, term)
        if position >= action_end
    ]
    return max(ends) if ends else None


def _is_media_content_constraint_prefix(prefix: str) -> bool:
    """Allow output requests constrained by color/style/source exclusions."""
    normalized_prefix = prefix
    for lead_in in ("请你", "请", "先"):
        if normalized_prefix.startswith(lead_in):
            normalized_prefix = normalized_prefix[len(lead_in):]
    for marker in ("不要使用", "不使用", "别使用", "不要用", "不用", "别用"):
        if not normalized_prefix.startswith(marker):
            continue
        constraint = normalized_prefix[len(marker):]
        if not constraint:
            return False
        # A deictic existing asset is an object-level denial ("不要用这张图片"),
        # not a harmless style/material constraint such as "不要用红色".
        if _has_any(constraint, MEDIA_TERMS) or _has_any(
            constraint,
            (
                "这张",
                "这幅",
                "这个",
                "该图",
                "当前",
                "上传",
                "我的图片",
                "ai",
                "人工智能",
                "生成式",
                "模型",
                "百炼",
                "万相",
                "wan",
                "算法",
                "云端",
            ),
        ):
            return False
        return True
    return False


def _is_explicit_media_command_prefix(prefix: str) -> bool:
    """Require a current first-person/directive frame before media creation."""
    if _has_any(
        prefix,
        (
            *MEDIA_ATTRIBUTION_MARKERS,
        ),
    ):
        return False
    for temporal in ("最终", "最后", "此刻"):
        if prefix.startswith(temporal):
            prefix = prefix[len(temporal):]
            break
    if _has_current_user_reclaim_signal(prefix):
        return True
    direct_prefixes = frozenset(
        (
            "",
            "请",
            "请你",
            "帮我",
            "请帮我",
            "请给我",
            "麻烦帮我",
            "麻烦",
            "麻烦你",
            "给我",
            "为我",
            "请为我",
            "替我",
            "可以帮我",
            "现在",
            "现在请",
            "立即",
            "马上",
            "重新",
            "再",
            "分别",
            "改为",
            "改成",
            "然后",
            "随后",
            "接着",
            "然后重新",
            "随后重新",
            "接着重新",
            "请重新",
            "帮我重新",
            "请帮我重新",
            "给我重新",
            "不要忘了",
            "不要忘记",
            "别忘了",
            "别忘记",
            "是让你",
            "我想",
            "我想要",
            "我要",
            "我希望",
            "我需要",
            "我打算",
            "我准备",
            "但我想",
            "但我想要",
            "但我要",
            "不过我想",
            "不过我要",
            "但是我想",
            "但是我要",
            "我现在想",
            "我现在想要",
            "我现在要",
            "现在我想",
            "现在我想要",
            "现在我要",
            "不过请帮我",
            "但是请帮我",
            "可是请帮我",
            "但我现在想",
            "但我现在想要",
            "但我现在要",
            "不过我现在想",
            "不过我现在想要",
            "不过我现在要",
            "但是我现在想",
            "但是我现在想要",
            "但是我现在要",
            "可是我现在想",
            "可是我现在想要",
            "可是我现在要",
        )
    )
    if prefix in direct_prefixes:
        return True
    if _is_media_content_constraint_prefix(prefix):
        return True
    if prefix.startswith("用不着"):
        return False
    if prefix.startswith(
        (
            "把",
            "将",
            "请把",
            "请将",
            "帮我把",
            "帮我将",
            "请帮我把",
            "请帮我将",
            "给我把",
            "给我将",
            "麻烦把",
            "麻烦你把",
        )
    ):
        return True
    if prefix.startswith(("基于", "根据")):
        return _has_any(
            prefix,
            ("图片", "图像", "照片", "这张", "该图", "此图"),
        ) and not _has_any(prefix, ("可以", "能够", "会", "用于", "说明"))
    if prefix.startswith(("以这", "以该", "以此", "以照片", "以图片", "以图像")):
        return True
    if (
        prefix.startswith("用")
        and not prefix.startswith(("用户", "用于", "用途", "用不着"))
        and not _has_any(
            prefix,
            (
                "可以",
                "能够",
                "会",
                "适合",
                "非ai",
                "非人工智能",
                "非模型",
                "本地",
                "离线",
            ),
        )
    ):
        return True
    for discourse_prefix in ("然后", "随后", "接着", "再"):
        if prefix.startswith(discourse_prefix) and (
            prefix[len(discourse_prefix):] in direct_prefixes
        ):
            return True
    for transition_prefix in (
        "不过",
        "随后",
        "之后",
        "然后",
        "接着",
        "但是",
        "可是",
        "但",
        "可",
        "现在",
            "换成",
            "我的要求是",
            "我的新要求是",
        ):
        if not prefix.startswith(transition_prefix):
            continue
        remainder = prefix[len(transition_prefix):]
        if remainder in direct_prefixes:
            return True
    if prefix.endswith("也") and _has_any(
        prefix,
        (*MEDIA_TERMS, *MEDIA_SHORTHAND_TERMS),
    ):
        return True
    has_old_action_context = _has_any(
        prefix,
        ("取消", "停止", "撤销", "撤回", "拒绝", "放弃", "不要"),
    ) and _has_any(
        prefix,
        ("旧", "刚才", "之前", "原", "任务", "方案", *MEDIA_CREATE_ACTIONS),
    )
    if has_old_action_context:
        for transition in (
            "改为",
            "改成",
            "转而",
            "而是",
            "然后",
            "随后",
            "后",
            "并",
            "再",
        ):
            transition_position = prefix.rfind(transition)
            if transition_position < 0:
                continue
            recommit_prefix = prefix[transition_position + len(transition):]
            if recommit_prefix in direct_prefixes:
                return True
    return False


def _has_direct_media_request_tail(clause: str, output_end: int) -> bool:
    """A bare leading action must end like a command, not a predicate."""
    tail = clause[output_end:].strip()
    return tail in (
        "",
        "吧",
        "一下",
        "看看",
        "给我",
        "给我看看",
        "就好",
        "就行",
        "即可",
        "好了",
    )


def _has_terminal_media_denial(clause: str, action_end: int) -> bool:
    tail = clause[action_end:].strip()
    terminal_denials = (
        "不是我的意思",
        "我没同意",
        "我未同意",
        "我不同意",
        "我不希望",
        "我没打算",
        "要求取消",
        "我拒绝",
        "取消",
        "停止",
        "撤销",
        "撤回",
        "拒绝",
        "反对",
        "暂停",
        "终止",
        "放弃",
        "不要",
        "算了",
        "算了吧",
        "反悔",
        "反悔了",
        "别弄",
        "别弄了",
        "先别弄",
        "先别弄了",
        "先别发",
        "先别发了",
        "不发了",
        "暂时不要发",
        "暂时别发",
        "暂时别做",
        "先等等",
    )
    if tail.endswith(terminal_denials):
        return True
    denial_objects = (
        "这个要求",
        "这项要求",
        "该要求",
        "此要求",
        "这个操作",
        "这项操作",
        "该操作",
        "此操作",
        "这件事",
        "这样做",
        "这么做",
    )
    denial_signals = (
        "不同意",
        "没同意",
        "未同意",
        "不希望",
        "没打算",
        "拒绝",
        "取消",
    )
    return tail.endswith(denial_objects) and _has_any(tail, denial_signals)


def _has_media_denial_signal(text: str) -> bool:
    """Identify a denial only to revoke an earlier affirmative clause.

    Safety does not depend on this list being exhaustive: a clause without an
    explicit affirmative frame is never authorization in the first place.
    """
    return _has_any(
        text,
        (
            "不",
            "没",
            "未",
            "无须",
            "无需",
            "用不着",
            "别",
            "勿",
            "禁止",
            "严禁",
            "避免",
            "取消",
            "停止",
            "撤销",
            "撤回",
            "拒绝",
            "反对",
            "暂停",
            "终止",
            "放弃",
            "算了",
            "反悔",
        ),
    )


def _is_elliptical_media_cancellation(clause: str) -> bool:
    return _has_terminal_media_denial(clause, 0) or clause.endswith(
        (
            "不要",
            "不要了",
            "算了",
            "算了吧",
            "反悔",
            "反悔了",
            "别弄",
            "别弄了",
            "先别弄",
            "先别弄了",
            "先别发",
            "先别发了",
            "不发了",
            "暂时不要发",
            "暂时别发",
            "暂时别做",
            "先等等",
            "先不要上传",
            "不传了",
            "别传了",
            "不用了",
            "等一下",
            "停下",
            "停下来",
            "作罢",
        )
    )


def _media_clause_decision(clause: str) -> Optional[bool]:
    """Return the clause's latest explicit media authorization decision."""
    decision: Optional[bool] = None
    events: list[tuple[int, str, str]] = [
        (position, "create", action)
        for position, action in _media_action_occurrences(
            clause,
            MEDIA_CREATE_ACTIONS,
        )
    ]
    provider_flow = any(
        _is_explicit_provider_confirmation_at(clause, position)
        for position in _all_phrase_positions(clause, "确认")
    )
    if provider_flow:
        events.extend(
            (position, "confirm", action)
            for position, action in _media_action_occurrences(clause, ("确认",))
        )
    if _has_any(clause, MEDIA_PROVIDER_TERMS):
        events.extend(
            (position, "transfer", action)
            for position, action in _media_action_occurrences(
                clause,
                MEDIA_TRANSFER_ACTIONS,
            )
        )
    events.sort(key=lambda item: item[0])

    last_action_end: Optional[int] = None
    authorized_payload_end: Optional[int] = None
    for position, event_kind, action in events:
        action_end = position + len(action)
        prefix = clause[:position]
        if authorized_payload_end is not None and position < authorized_payload_end:
            continue
        last_action_end = action_end
        if event_kind == "create":
            if _is_nominal_media_action(clause, position, action):
                continue
            output_end = _media_create_output_end_if_authorized(
                clause,
                position,
                action,
            )
            if output_end is not None:
                decision = True
                authorized_payload_end = output_end
            elif _has_media_denial_signal(prefix):
                decision = False
        elif event_kind == "confirm":
            if (
                _is_explicit_provider_confirmation_prefix(prefix)
                and _is_explicit_provider_confirmation_at(clause, position)
            ):
                decision = True
            elif _has_media_denial_signal(prefix):
                decision = False
        elif _has_media_denial_signal(prefix) and not provider_flow:
            decision = False

    if last_action_end is not None and _has_terminal_media_denial(
        clause,
        last_action_end,
    ):
        return False
    if _is_elliptical_media_cancellation(clause):
        return False
    return decision


def _media_provider_clause_decision(clause: str) -> Optional[bool]:
    """Track provider consent separately from the requested creative action."""
    payload_span: Optional[tuple[int, int]] = None
    for position, action in _media_action_occurrences(
        clause,
        MEDIA_CREATE_ACTIONS,
    ):
        if _is_nominal_media_action(clause, position, action):
            continue
        output_end = _media_create_output_end_if_authorized(
            clause,
            position,
            action,
        )
        if output_end is not None:
            content_start = _media_content_start(clause)
            if (
                content_start is not None
                and position + len(action) <= content_start < output_end
            ):
                control_switch = _media_provider_control_switch_start(
                    clause,
                    content_start,
                    output_end,
                )
                payload_span = (
                    content_start,
                    control_switch if control_switch is not None else output_end,
                )
            break
    control_segment = clause
    if payload_span is not None:
        control_segment = (
            clause[:payload_span[0]] + clause[payload_span[1]:]
        )
    has_mechanism = _has_any(control_segment, MEDIA_MECHANISM_TERMS)
    has_transfer_scope = _has_any(
        control_segment,
        MEDIA_PROVIDER_CONTROL_TERMS,
    )
    mechanism_veto = (
        (has_mechanism or has_transfer_scope)
        and _has_media_denial_signal(control_segment)
    ) or (
        has_mechanism
        and _has_any(
            control_segment,
            ("非ai", "非人工智能", "非模型", "本地", "离线"),
        )
    ) or _has_any(
        control_segment,
        (
            "仅限设备内",
            "只限设备内",
            "仅在设备内",
            "只在设备内",
            "本地处理",
            "离线处理",
        ),
    )

    provider_flow = any(
        _is_explicit_provider_confirmation_at(control_segment, position)
        for position in _all_phrase_positions(control_segment, "确认")
    )
    if not has_mechanism and not has_transfer_scope and not provider_flow:
        return None
    events: list[tuple[int, str, str]] = [
        (position, "transfer", action)
        for position, action in _media_action_occurrences(
            clause,
            MEDIA_TRANSFER_ACTIONS,
        )
    ]
    if provider_flow:
        events.extend(
            (position, "confirm", action)
            for position, action in _media_action_occurrences(clause, ("确认",))
        )
    events.sort(key=lambda item: item[0])

    decision: Optional[bool] = False if mechanism_veto else None
    for position, event_kind, action in events:
        if (
            payload_span is not None
            and payload_span[0] <= position < payload_span[1]
        ):
            continue
        prefix = clause[:position]
        if event_kind == "confirm":
            if (
                _is_explicit_provider_confirmation_prefix(prefix)
                and _is_explicit_provider_confirmation_at(clause, position)
            ):
                decision = True
            elif _has_media_denial_signal(prefix):
                decision = False
        elif _has_media_denial_signal(prefix) and not provider_flow:
            decision = False
    return decision


def _is_media_generation_request(text: str) -> bool:
    """Require a current user command/consent frame for external media work."""
    if _has_hard_media_report_scope(text):
        return False
    text = _mask_media_quoted_content(text)
    has_media_target = _has_any(text, MEDIA_TERMS) or (
        _has_any(text, MEDIA_CREATE_ACTIONS)
        and _has_any(text, MEDIA_SHORTHAND_TERMS)
    )
    if not has_media_target:
        return False
    decision: Optional[bool] = None
    provider_decision: Optional[bool] = None
    attribution_context = False
    has_create_authorization = False
    clauses = _media_clauses(text)
    for clause_index, clause in enumerate(clauses):
        previous_provider_decision = provider_decision
        if attribution_context:
            if _is_attribution_override_clause(clause):
                attribution_context = False
            else:
                if previous_provider_decision is True:
                    provider_decision = False
                continue
        if _media_attribution_precedes_control(clause):
            if previous_provider_decision is True:
                provider_decision = False
            attribution_context = True
            continue
        if has_create_authorization and _is_media_payload_clause(clause):
            continue
        clause_provider_decision = _media_provider_clause_decision(clause)
        clause_decision = _media_clause_decision(clause)
        if (
            clause_index < len(clauses) - 1
            and decision is None
            and provider_decision is None
            and clause_provider_decision is None
            and clause_decision is None
            and not _is_safe_media_leadin(clause)
        ):
            attribution_context = True
            continue
        if clause_provider_decision is not None:
            provider_decision = clause_provider_decision
        if provider_decision is not None and _is_elliptical_media_cancellation(
            clause
        ):
            provider_decision = False
        if clause_decision is not None:
            decision = clause_decision
            has_create_authorization = (
                clause_decision is True
                and _has_explicit_media_create_frame(clause)
            )
        # A provider confirmation only survives a following clause when that
        # clause is itself an explicit media command. Any description,
        # condition, deferral, or revocation makes the consent non-current.
        if (
            previous_provider_decision is True
            and clause_provider_decision is None
            and clause_decision is not True
        ):
            provider_decision = False
    return decision is True and provider_decision is not False


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
    return _has_symptom_signal(text)


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
