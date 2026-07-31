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


@dataclass(frozen=True)
class _ClauseFrame:
    text: str
    source: str
    action: str
    actor: str
    object_kind: str


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
    "看看",
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
    "高不高",
    "正常吗",
    "有问题吗",
    "能否",
    "可否",
    "可不可以",
    "怎么样",
)
WRITE_ACTIONS = (
    "记录",
    "打卡",
    "打个卡",
    "新增",
    "录入",
    "保存",
    "记下",
    "记一下",
    "帮我记一下",
    "写入",
    "存下来",
    "吃了",
    "喝了",
    "服药",
    "已服用",
    "已吃",
    "已喝",
)
MEDIA_TERMS = (
    "aigc",
    "百炼",
    "万相",
    "wan",
    "图片",
    "图像",
    "海报",
    "封面",
    "短视频",
    "视频",
    "图生视频",
    "文生图",
    "文生视频",
)
MEDIA_CREATE_ACTIONS = (
    "生成",
    "制作",
    "做成",
    "做一个",
    "创作",
    "创作一个",
    "渲染",
    "变成",
)
PLAN_TERMS = (
    "计划",
    "计划项",
    "周计划",
    "行动卡",
    "首页计划",
    "干预周期",
)
PLAN_CREATE_ACTIONS = (
    "生成",
    "制定",
    "安排",
    "加入",
    "列入",
    "保存",
)
PLAN_UPDATE_ACTIONS = (
    "完成",
    "标记完成",
    "调整计划",
    "更新计划",
)
REMINDER_TERMS = (
    "提醒",
    "提醒我",
    "定时提醒",
    "闹钟",
    "一次性提醒",
    "循环提醒",
)
REMINDER_CREATE_ACTIONS = (
    "提醒",
    "提醒我",
    "定时提醒",
    "创建",
    "设置",
    "设一个",
    "设个",
    "帮我设",
    "帮我定",
    "定个",
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
    "update": ("修改", "改成", "改为", "改到", "更新", "调整", "更正", "修正"),
    "sync": ("同步", "sync", "拉取最新数据", "刷新一下数据", "刷新数据"),
}
MUTATION_NEGATIONS = (
    "不要",
    "别",
    "不用",
    "无需",
    "不需要",
    "不想",
    "先别",
    "暂不",
    "不能",
    "不可",
    "禁止",
    "避免",
)
MUTATION_NEGATION_EXCEPTIONS = ("别忘了", "不要忘了")
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
CLINICIAN_PROVIDER_TERMS = ("主治医生", "康复师", "医生", "大夫")
CLINICIAN_REPORT_VERBS = (
    "告诉",
    "告知",
    "表示",
    "认为",
    "建议",
    "评估",
    "诊断",
    "判断",
    "说",
)
CLINICIAN_DIAGNOSIS_MARKERS = tuple(
    marker
    for provider in CLINICIAN_PROVIDER_TERMS
    for marker in (f"{provider}诊断", f"{provider}的诊断")
)
CLINICIAN_QUOTED_REPORT_MARKERS = (
    *tuple(
        f"{provider}{verb}"
        for provider in CLINICIAN_PROVIDER_TERMS
        for verb in CLINICIAN_REPORT_VERBS
    ),
    "检查提示",
)
CLINICIAN_ATTRIBUTION_MARKERS = (
    *CLINICIAN_DIAGNOSIS_MARKERS,
    *CLINICIAN_QUOTED_REPORT_MARKERS,
)
CLINICIAN_CONTEXT_WRITE_ACTIONS = (
    "记录",
    "记一下",
    "记下",
    "录入",
    "保存",
    "写入",
    "存下来",
)
CLINICIAN_CONTEXT_CLAUSE_BOUNDARIES = frozenset("，,。；;：:！？!?\n")
CLINICIAN_QUOTED_CONTENT_REFERENCES = (
    "的内容",
    "的意见",
    "的反馈",
    "的结论",
    "的诊断",
    "的话",
)
CLINICIAN_RECORD_TERMS = (
    *CLINICIAN_DIAGNOSIS_MARKERS,
    *tuple(
        f"{provider}{noun}"
        for provider in CLINICIAN_PROVIDER_TERMS
        for noun in ("意见", "反馈", "结论")
    ),
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
    clauses = _split_clauses(raw)
    normalized = _normalize(raw)
    if not normalized:
        return _intent(raw, normalized, "unknown", "unknown", "none", 0.0, "empty")

    domain = _infer_domain(normalized)
    has_read = _has_any(normalized, READ_ACTIONS)
    scope = _build_scope(
        normalized,
        focus=(_read_focus(normalized) if has_read else None),
        reference_now=reference_now,
    )
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

    clause_frames = tuple(_classify_clause(clause) for clause in clauses)
    clinician_intent = _reduce_clinician_clauses(
        raw=raw,
        normalized=normalized,
        frames=clause_frames,
        scope=scope,
    )
    if clinician_intent is not None:
        return clinician_intent

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
        return _intent(raw, normalized, "read", domain, operation, 0.88, "read_frame", scope)

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


def _split_clauses(raw_text: str) -> tuple[str, ...]:
    """Split before normalization so punctuation and newlines stay visible."""
    clauses: list[str] = []
    current: list[str] = []
    for char in str(raw_text or ""):
        if char in CLINICIAN_CONTEXT_CLAUSE_BOUNDARIES:
            clause = "".join(current).strip()
            if clause:
                clauses.append(clause)
            current = []
            continue
        current.append(char)
    clause = "".join(current).strip()
    if clause:
        clauses.append(clause)
    return tuple(clauses)


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase.lower() in text for phrase in phrases)


def _diagnosis_marker_is_attribution(
    text: str,
    marker: str,
    marker_end: int,
) -> bool:
    if marker not in CLINICIAN_DIAGNOSIS_MARKERS:
        return True
    suffix = text[marker_end:]
    if not suffix or suffix.startswith(("记录", "的记录")):
        return False
    return not suffix.startswith(
        (
            "请",
            "帮我",
            "给我",
            "麻烦",
            "记一下",
            "记下",
            "记录",
            "录入",
            "保存",
            "写入",
            "存下来",
            "查看",
            "删除",
            "调整",
            "修改",
            "更新",
            "同步",
        )
    )


def _find_clinician_attribution(text: str) -> Optional[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for marker in CLINICIAN_ATTRIBUTION_MARKERS:
        for start in _all_phrase_positions(text, marker):
            end = start + len(marker)
            if _diagnosis_marker_is_attribution(text, marker, end):
                candidates.append((start, end))
    if not candidates:
        return None
    return min(candidates, key=lambda span: (span[0], -span[1]))


def _first_clause_action(text: str, object_kind: str) -> tuple[str, int]:
    candidates: list[tuple[int, int, str]] = []

    for phrase in READ_ACTIONS:
        for start in _all_phrase_positions(text, phrase):
            candidates.append((start, 1, "read"))

    has_explicit_save = _has_explicit_write_command(text)
    for phrase in CLINICIAN_CONTEXT_WRITE_ACTIONS:
        for start in _all_phrase_positions(text, phrase):
            if has_explicit_save or "把" in text[:start]:
                candidates.append((start, 0, "save"))

    for operation, phrases in MUTATE_ACTIONS.items():
        for phrase in phrases:
            for start in _all_phrase_positions(text, phrase):
                candidates.append((start, 0, operation))

    for phrase in ADVICE_ACTIONS:
        for start in _all_phrase_positions(text, phrase):
            candidates.append((start, 2, "analyze"))

    if candidates:
        start, _, action = min(candidates, key=lambda item: (item[0], item[1]))
        return action, start
    if _has_question_signal(text):
        return ("read" if object_kind == "clinician_record" else "analyze"), 0
    return "none", -1


def _has_quoted_content_reference(text: str) -> bool:
    return _has_any(text, CLINICIAN_QUOTED_CONTENT_REFERENCES)


def _clause_object_kind(
    text: str,
    *,
    has_attribution: bool,
) -> str:
    if has_attribution:
        return "clinician_content"
    if _has_quoted_content_reference(text):
        return "clinician_content"
    if _has_any(text, CLINICIAN_RECORD_TERMS):
        return "clinician_record"

    domain = _infer_domain(text)
    if domain == "medication":
        return "medication"
    if domain != "unknown":
        return "health_record"
    if _has_any(text, ("健康数据", "健康记录", "用药记录", "记录数据")):
        return "health_record"
    return "unknown"


def _quoted_content_is_user_object(
    text: str,
    attribution_start: int,
    attribution_end: int,
    action_start: int,
) -> bool:
    return (
        "把" in text[:attribution_start]
        and _has_quoted_content_reference(text[attribution_end:action_start])
    )


def _classify_clause(text: str) -> _ClauseFrame:
    normalized = _normalize(text)
    attribution = _find_clinician_attribution(normalized)
    object_kind = _clause_object_kind(
        normalized,
        has_attribution=attribution is not None,
    )
    action, action_start = _first_clause_action(normalized, object_kind)
    source = "clinician_quote" if attribution is not None else "user"

    if attribution is None or action_start < 0:
        actor = "clinician" if attribution is not None else "user"
    else:
        attribution_start, attribution_end = attribution
        if action_start < attribution_start:
            actor = "user"
        elif _quoted_content_is_user_object(
            normalized,
            attribution_start,
            attribution_end,
            action_start,
        ):
            actor = "user"
        else:
            actor = "clinician"

    return _ClauseFrame(
        text=normalized,
        source=source,
        action=action,
        actor=actor,
        object_kind=object_kind,
    )


def _reduce_clinician_clauses(
    *,
    raw: str,
    normalized: str,
    frames: tuple[_ClauseFrame, ...],
    scope: dict[str, str],
) -> Optional[AgentUtteranceIntent]:
    clinician_objects = {"clinician_content", "clinician_record"}
    has_clinician_source = any(
        frame.source == "clinician_quote" for frame in frames
    )
    has_clinician_object = any(
        frame.object_kind in clinician_objects for frame in frames
    )
    if not has_clinician_source and not has_clinician_object:
        return None

    if not _has_negated_write(normalized):
        for index, frame in enumerate(frames):
            if frame.actor != "user" or frame.action != "save":
                continue
            same_clause_object = frame.object_kind in clinician_objects
            adjacent_clinician_object = (
                frame.object_kind == "unknown"
                and index > 0
                and frames[index - 1].object_kind in clinician_objects
            )
            if same_clause_object or adjacent_clinician_object:
                return _intent(
                    raw,
                    normalized,
                    "write",
                    "clinical_context",
                    "create",
                    0.96,
                    "user_clinician_context_save",
                    scope,
                    is_write=True,
                    requires_reliable_tool_model=True,
                )

    for frame in frames:
        if frame.actor != "user" or frame.object_kind == "unknown":
            continue
        if frame.action == "read":
            domain = (
                "clinical_context"
                if frame.object_kind in clinician_objects
                else _infer_domain(frame.text)
            )
            operation = "ask" if _has_question_signal(frame.text) else "list"
            return _intent(
                raw,
                normalized,
                "read",
                domain,
                operation,
                0.9,
                "user_explicit_record_read",
                scope,
                requires_reliable_tool_model=domain == "clinical_context",
            )
        if frame.action in {"update", "delete", "sync"}:
            if _has_negated_mutation(frame.text, frame.action):
                continue
            domain = (
                "clinical_context"
                if frame.object_kind in clinician_objects
                else _infer_domain(frame.text)
            )
            return _intent(
                raw,
                normalized,
                "mutate",
                domain,
                frame.action,
                0.94,
                "user_explicit_record_mutation",
                scope,
                is_write=True,
                requires_reliable_tool_model=True,
            )

    if has_clinician_source:
        if any(
            frame.actor == "user" and frame.action == "analyze"
            for frame in frames
        ):
            return _intent(
                raw,
                normalized,
                "advice",
                "clinical_context",
                "analyze",
                0.92,
                "clinician_context_advice",
                scope,
                requires_reliable_tool_model=True,
            )
        return _intent(
            raw,
            normalized,
            "chat",
            "clinical_context",
            "acknowledge",
            0.96,
            "clinician_provenance_fail_closed",
            scope,
            requires_reliable_tool_model=True,
        )

    return _intent(
        raw,
        normalized,
        "unknown",
        "unknown",
        "none",
        0.72,
        "clinician_record_noun",
        scope,
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
    command_prefixes = (
        "帮我",
        "请",
        "给我",
        "麻烦",
        "先",
        "再",
        "然后",
        "并",
        "顺便",
        "要",
        "把",
        "我想",
        "想",
        "希望",
        "需要",
    )
    record_noun_suffixes = (
        "出发",
        "显示",
        "表明",
        "提示",
        "证明",
        "分析",
        "推断",
        "里",
        "中",
        "上",
        "的",
    )

    for action in command_actions:
        start = text.find(action)
        while start >= 0:
            left_context = text[:start]
            after = text[start + len(action):]
            if action == "记录" and after.startswith(record_noun_suffixes):
                start = text.find(action, start + len(action))
                continue
            if (
                start == 0
                or left_context.endswith(command_prefixes)
                or (action == "记录" and after.startswith(("一下", "下来", "为", "到")))
            ):
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
