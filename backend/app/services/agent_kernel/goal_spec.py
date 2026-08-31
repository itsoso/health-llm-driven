"""Compile a user turn into a deterministic, verifiable task contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import json
import re

from app.services import write_intent_scope as write_intent_scope_module
from app.services.agent_kernel import write_safety as write_safety_module
from app.services.agent_kernel.goal_registry import (
    GoalCompilerRegistry,
    GoalCompilerSpec,
    GoalPromptRegistry,
    GoalPromptSpec,
)
from app.services.agent_kernel.health_semantics import (
    authorization_behavior_digest,
    authorization_grammar_digest,
    authorization_imported_behavior_names,
    authorization_module_behavior_names,
    extract_owned_illness_entity,
    health_read_has_nonself_subject,
    illness_entity_has_medical_semantics as _semantic_illness_entity,
    illness_target_is_unowned_or_referential as _semantic_unowned_target,
    normalize_health_authorization_text,
)
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    GoalSpec,
    IntentFrame,
)
from app.services.agent_kernel.write_safety import is_explicit_write_cancellation
from app.services.write_intent_scope import (
    explicit_whole_record_delete_targets,
    has_explicit_authorizing_update_request,
    has_mixed_write_polarity,
)


MEAL_SIGNALS = {
    "breakfast": ("早餐", "早饭"),
    "lunch": ("午餐", "午饭", "中饭"),
    "dinner": ("晚餐", "晚饭"),
    "snack": ("加餐", "零食", "夜宵"),
}
RECALCULATE_SIGNALS = (
    "重新估算",
    "重新计算",
    "重新核算",
    "重新算",
    "重新估",
    "再算",
    "再估",
    "重算",
    "重估",
)
UPDATE_SIGNALS = (
    "写入",
    "写回",
    "写进去",
    "更新",
    "保存",
    "改写",
    "补回",
    "补上",
)
NEGATION_SIGNALS = ("先不要", "暂不", "不要", "不用", "无需", "先别", "别")
QUESTION_SIGNALS = ("?", "？", "是否", "是不是", "需要", "吗")
REFERENTIAL_SIGNALS = ("上面", "上述", "这两餐", "这些餐")
WATER_SIGNALS = ("喝水", "饮水", "补水", "杯水", "瓶水")
WATER_CONTAINER_AMOUNTS = (
    ("一杯", 250),
    ("两杯", 500),
    ("三杯", 750),
    ("半杯", 125),
    ("一瓶", 500),
    ("半瓶", 250),
)
WATER_AMOUNT_RE = re.compile(
    r"(?:喝水|饮水|补水)"
    r"(?:了)?(?:约|大约|差不多)?"
    r"(?:[^，。！？!?]{0,20}?)"
    r"(?P<amount>\d+(?:\.\d+)?(?:十|百|千|万)?|半|"
    r"[零〇一二两三四五六七八九十百千万点]+)"
    r"(?P<unit>毫升|ml|升|l)",
    re.IGNORECASE,
)
SIMPLE_SYMPTOM_BODY_PARTS = (
    ("respiratory", ("喷嚏", "鼻塞", "流鼻涕", "流涕", "咳嗽", "咳")),
    ("digestive", ("胃痛", "胃疼", "肚子痛", "腹痛", "恶心", "呕吐", "腹泻")),
    ("head", ("头痛", "头疼", "头晕", "眩晕")),
    ("eye", ("眼痛", "眼疼", "眼痒", "眼睛痒")),
    ("skin", ("皮疹", "皮肤痒", "瘙痒")),
    ("musculoskeletal", ("腰痛", "腰疼", "关节痛", "关节疼", "肌肉痛")),
)
SYMPTOM_COMPOUND_TAIL_SIGNALS = (
    "怎么办", "怎么", "如何", "为什么", "建议", "意见", "处理", "缓解",
    "改善", "办法", "注意", "严重", "急诊", "就医", "医院", "原因", "看看",
    "评估", "解释", "判断", "正常", "危险", "过敏", "什么科", "会不会", "需要",
    "是否", "吗", "给",
)
DIET_TRAILING_WRITE_RE = re.compile(
    r"(?:[\s，,。.!！；;：:]*)"
    r"(?:请)?(?:帮我|给我)?"
    r"(?:记录|记下|记一下|保存|录入|加到饮食)(?:一下|下)?"
    r"(?:[\s，,。.!！；;：:]*)$"
)
DIET_TRAILING_ANALYSIS_RE = re.compile(
    r"(?:[\s，,。.!！；;：:]*)"
    r"(?:(?:不需要|不用|无需再?|不要|并|同时|请|帮我|给我|需要|帮忙)\s*)*"
    r"(?:计算|估算|核算|分析|算算|算)(?:一下|下)?"
    r"(?:(?:这|本)(?:餐|顿)(?:的)?|这些食物(?:的)?)?"
    r"(?:总)?"
    r"(?:热量|卡路里|营养成分|营养素|宏量营养素?|蛋白质|"
    r"碳水(?:化合物)?|脂肪|膳食纤维)"
    r"(?:(?:和|及|与|、|，|,|/)"
    r"(?:热量|卡路里|营养成分|营养素|宏量营养素?|蛋白质|"
    r"碳水(?:化合物)?|脂肪|膳食纤维))*"
    r"(?:[\s，,。.!！；;：:]*)$"
)
OTHER_RECORD_SIGNALS = {
    "diet": tuple(signal for signals in MEAL_SIGNALS.values() for signal in signals),
    "weight": ("体重", "称重"),
    "blood_pressure": ("血压", "收缩压", "舒张压"),
    "medication": ("服药", "吃药", "用药"),
    "supplement": ("补剂", "维生素", "益生菌"),
    "exercise": ("运动", "跑步", "训练"),
    "sleep": ("睡觉", "入睡", "起床"),
}
SIMPLE_ILLNESS_CREATE_RE = re.compile(
    r"^(?:请)?(?:(?:帮|替|给)我)?"
    r"(?:记录|记下|记一下|新增|录入|保存|写入)(?:一下)?(?:一条|一个)?"
    r"(?:我的)?疾病(?P<name>.+)$",
    re.IGNORECASE,
)
SIMPLE_ILLNESS_NAME_RE = re.compile(
    r"(?=.{2,80}$)[\w·+./-]+",
    re.IGNORECASE,
)
SIMPLE_ILLNESS_ACRONYMS = frozenset({"sle"})
GOAL_SPEC_CONTRACT_VERSION = "goal-spec-v45"
HEALTH_MANAGE_MUTATION_COMMAND_RE = re.compile(
    r"(?:"
    r"^(?:请(?:你|您)?|麻烦(?:你|您)?|请帮我|帮我|给我|替我)?"
    r"(?:把|将).+(?:改成|改为|修改|更新|更正|修正|调整|删除|删掉|移除|清除)|"
    r"^(?:请(?:你|您)?|麻烦(?:你|您)?|请帮我|帮我|给我|替我)?"
    r"(?:更新|修改|更正|修正|调整|删除|删掉|移除|清除|清掉)"
    r"(?!了(?:吧)?(?:[，,。.!！；;]|$)).+|"
    r"(?:[，,；;]?)(?:请)?(?:更新|修改|更正|修正|调整)(?:一下|下)?"
    r"(?:这条|该条|我的)?(?:疾病)?记录$"
    r")",
    re.IGNORECASE,
)
HEALTH_MANAGE_MUTATION_RECORD_ID_RE = re.compile(
    r"(?P<label>疾病|病历|illness|饮水|喝水|water|体重|weight|饮食|diet|"
    r"症状|symptom|睡眠|sleep|运动|exercise|用药|medication)"
    r"(?:的)?(?:记录|条目)?(?:ID|编号|#|第)?[：:=（(]?\d+",
    re.IGNORECASE,
)
HEALTH_MANAGE_MUTATION_RECORD_TYPES = {
    "疾病": "illness",
    "病历": "illness",
    "illness": "illness",
    "饮水": "water",
    "喝水": "water",
    "water": "water",
    "体重": "weight",
    "weight": "weight",
    "饮食": "diet",
    "diet": "diet",
    "症状": "symptom",
    "symptom": "symptom",
    "睡眠": "sleep",
    "sleep": "sleep",
    "运动": "exercise",
    "exercise": "exercise",
    "用药": "medication",
    "medication": "medication",
}
WATER_MUTATION_RE = re.compile(
    r"(?P<old>\d+(?:\.\d+)?)\s*(?:毫升|ml)"
    r"[^，,。.!！；;]{0,24}(?:改成|改为|修改为|更新为|更正为|调整为)"
    r"\s*(?P<new>\d+(?:\.\d+)?)\s*(?:毫升|ml)",
    re.IGNORECASE,
)


def illness_entity_has_medical_semantics(value: str) -> bool:
    """Compatibility wrapper for the shared semantic entity contract."""
    return _semantic_illness_entity(value)


def illness_target_is_unowned_or_referential(value: str) -> bool:
    """Compatibility wrapper for the shared ownership/reference contract."""
    return _semantic_unowned_target(value)


def illness_read_has_unowned_subject(text: str) -> bool:
    """Compatibility wrapper; ownership now applies to every health domain."""
    return health_read_has_nonself_subject(text)


def compile_goal_spec(
    *,
    envelope: AgentEnvelope,
    context: ExecutionContext,
    intent: IntentFrame,
    actionable_references: Sequence[ActionableReference] = (),
) -> GoalSpec:
    """Create the executor contract without granting authority to visible data."""
    authorization_text = normalize_health_authorization_text(envelope.text)
    text = _normalize(authorization_text)
    if intent.is_write and _explicit_target_date_is_invalid(
        text,
        context.current_time.date(),
    ):
        return GoalSpec(
            kind="clarify",
            domain=intent.domain,
            operation="none",
            target_date=None,
            requires_clarification=True,
            prohibited_operations=("create", "update", "delete"),
            evidence=("invalid_explicit_date",),
        )

    specialized = _GOAL_COMPILER_REGISTRY.compile(
        envelope=replace(envelope, text=authorization_text),
        context=context,
        intent=intent,
        actionable_references=actionable_references,
    )
    if specialized is not None:
        return specialized

    target_meals = _target_meal_types(text, actionable_references)
    target_date = _target_date(text, context, actionable_references)
    return GoalSpec(
        kind=_fallback_kind(intent),
        domain=intent.domain,
        operation=intent.operation,
        target_date=target_date,
        target_meal_types=target_meals,
        prohibited_operations=(
            ("create", "update", "delete")
            if intent.primary in {"read", "advice", "chat", "unknown"}
            else ()
        ),
    )


def _compile_diet_recalculation_goal(
    *,
    envelope: AgentEnvelope,
    context: ExecutionContext,
    intent: IntentFrame,
    actionable_references: Sequence[ActionableReference],
) -> GoalSpec | None:
    text = _normalize(envelope.text)
    target_meals = _target_meal_types(text, actionable_references)
    target_date = _target_date(text, context, actionable_references)
    reference_foods = _reference_foods(
        actionable_references,
        target_meals,
        target_date=target_date,
    )
    is_recalculation = _has_any(text, RECALCULATE_SIGNALS)
    wants_update = _has_any(text, UPDATE_SIGNALS)
    is_negated = _has_any(text, NEGATION_SIGNALS)
    is_question = _has_any(text, QUESTION_SIGNALS) and not wants_update
    has_referent = _has_any(text, REFERENTIAL_SIGNALS)

    if is_negated and (is_recalculation or wants_update):
        return GoalSpec(
            kind="chat",
            domain="diet",
            operation="none",
            target_date=target_date,
            target_meal_types=target_meals,
            prohibited_operations=("create", "update", "delete"),
        )

    if is_question and is_recalculation:
        return GoalSpec(
            kind="answer",
            domain="diet",
            operation="ask",
            target_date=target_date,
            target_meal_types=target_meals,
            prohibited_operations=("create", "update", "delete"),
        )

    if is_recalculation and wants_update:
        if has_referent and not target_meals:
            return GoalSpec(
                kind="clarify",
                domain="diet",
                operation="none",
                target_date=target_date,
                requires_clarification=True,
                prohibited_operations=("create", "update", "delete"),
            )
        if target_meals:
            return GoalSpec(
                kind="diet_recalculate_update",
                domain="diet",
                operation="update",
                target_date=target_date,
                target_meal_types=target_meals,
                reference_foods=reference_foods,
                requires_lookup=True,
                requires_verification=True,
                prohibited_operations=("create", "delete"),
                postconditions=("existing_records_only", "read_back_verified"),
                evidence=("visible_card",) if reference_foods else (),
            )

    return None


def _compile_simple_health_record_goal(
    *,
    envelope: AgentEnvelope,
    context: ExecutionContext,
    intent: IntentFrame,
    actionable_references: Sequence[ActionableReference],
) -> GoalSpec | None:
    """Compile narrow create-only records whose payload is user-owned."""
    del actionable_references
    text = _normalize(envelope.text)
    illness_target = simple_illness_target(envelope.text)
    explicit_illness_label = SIMPLE_ILLNESS_CREATE_RE.fullmatch(
        "".join(str(envelope.text or "").split()).strip("，,。.!！；;：: ")
    )
    common_guard = (
        envelope.media
        or _simple_record_write_is_negated(text)
        or has_mixed_write_polarity(text)
        or _simple_record_is_question(text)
    )
    if illness_target is not None and not common_guard:
        return GoalSpec(
            kind="simple_health_record",
            domain="illness",
            operation="create",
            target_date=_target_date(text, context, ()),
            target_record_type="illness",
            target_values=(("name", illness_target),),
            requires_verification=True,
            prohibited_operations=("update", "delete"),
            postconditions=("verified_receipt",),
            evidence=("current_user_turn",),
        )
    if explicit_illness_label is not None:
        return GoalSpec(
            kind="clarify",
            domain="illness",
            operation="none",
            target_date=_target_date(text, context, ()),
            requires_clarification=True,
            prohibited_operations=("create", "update", "delete"),
            evidence=("illness_target_not_current_user_or_unresolved",),
        )
    if (
        common_guard
        or intent.primary not in {"write", "mutate"}
        or intent.operation != "create"
        or not intent.is_write
        or _is_compound_record_request(text, intent.domain)
    ):
        return None

    target_values: tuple[tuple[str, str], ...] = ()
    goal_domain = intent.domain
    if intent.domain == "water" and _has_any(text, WATER_SIGNALS):
        amount_ml = _water_amount_ml(text)
        if amount_ml is None:
            return None
        record_type = "water"
        target_values = (("amount_ml", str(amount_ml)),)
    elif intent.domain == "symptom":
        symptom_target = _simple_symptom_target(envelope.text)
        if symptom_target is None:
            return None
        record_type = "symptom"
        target_values = tuple(symptom_target.items())
    elif intent.domain == "diet":
        diet_target = _simple_diet_target(
            envelope.text,
            local_hour=context.current_time.hour,
        )
        if diet_target is None:
            return None
        record_type = "diet"
        target_values = tuple(diet_target.items())
    else:
        return None

    target_meal_types = (
        (dict(target_values)["meal_type"],) if record_type == "diet" else ()
    )
    return GoalSpec(
        kind="simple_health_record",
        domain=goal_domain,
        operation="create",
        target_date=_target_date(text, context, ()),
        target_meal_types=target_meal_types,
        target_record_type=record_type,
        target_values=target_values,
        requires_verification=True,
        prohibited_operations=("update", "delete"),
        postconditions=("verified_receipt",),
        evidence=("current_user_turn",),
    )


def _compile_health_manage_mutation_goal(
    *,
    envelope: AgentEnvelope,
    context: ExecutionContext,
    intent: IntentFrame,
    actionable_references: Sequence[ActionableReference],
) -> GoalSpec | None:
    """Compile only an explicit current-turn update/delete needing owner lookup."""
    del actionable_references
    text = "".join(str(envelope.text or "").split()).strip()
    delete_targets = (
        explicit_whole_record_delete_targets(text) if not envelope.media else ()
    )
    mutation_operation = "delete" if delete_targets else intent.operation
    if (
        envelope.media
        or (not delete_targets and intent.primary != "mutate")
        or mutation_operation not in {"update", "delete"}
        or (not delete_targets and not intent.is_write)
        or is_explicit_write_cancellation(text)
        or has_mixed_write_polarity(text)
        or (
            mutation_operation == "update"
            and not has_explicit_authorizing_update_request(text)
        )
        or (mutation_operation == "delete" and not delete_targets)
        or (
            mutation_operation != "delete"
            and HEALTH_MANAGE_MUTATION_COMMAND_RE.search(text) is None
        )
    ):
        return None

    target_record_type: str | None = None
    target_values: list[tuple[str, str]] = []
    if delete_targets:
        target_record_type = delete_targets[0][0]
        target_values.extend(
            ("record_id", str(record_id))
            for _, record_id in delete_targets
        )
    illness_entity = extract_owned_illness_entity(text)
    if illness_entity is not None:
        target_record_type = "illness"
        target_values.append(("name", illness_entity))

    record_id_match = HEALTH_MANAGE_MUTATION_RECORD_ID_RE.search(text)
    if record_id_match is not None:
        labelled_type = HEALTH_MANAGE_MUTATION_RECORD_TYPES.get(
            record_id_match.group("label").casefold()
        )
        if target_record_type is not None and labelled_type != target_record_type:
            return None
        target_record_type = labelled_type
        record_id = re.search(r"\d+", record_id_match.group())
        if record_id is not None:
            target_values.append(("record_id", record_id.group()))
    elif target_record_type == "illness":
        illness_id_match = re.search(
            r"(?:记录|条目)?(?:ID(?:号)?(?:为|是|=|：|:)?|编号|#|第)"
            r"\s*(?P<record_id>\d+)(?:号|个)?",
            text,
            re.IGNORECASE,
        )
        if illness_id_match is not None:
            target_values.append(("record_id", illness_id_match.group("record_id")))

    water_match = WATER_MUTATION_RE.search(text)
    if water_match is not None:
        if target_record_type not in {None, "water"}:
            return None
        target_record_type = "water"
        target_values.extend(
            (
                ("old_amount_ml", water_match.group("old")),
                ("new_amount_ml", water_match.group("new")),
            )
        )

    if target_record_type is None:
        return None
    return GoalSpec(
        kind="health_manage_mutation",
        domain=target_record_type,
        operation=mutation_operation,
        target_date=_target_date(_normalize(text), context, ()),
        target_record_type=target_record_type,
        target_values=tuple(dict.fromkeys(target_values)),
        requires_lookup=True,
        requires_verification=True,
        prohibited_operations=(
            ("create", "delete")
            if mutation_operation == "update"
            else ("create", "update")
        ),
        postconditions=("owner_scoped_lookup", "verified_receipt"),
        evidence=("explicit_current_turn_mutation",),
    )


def simple_illness_target(text: str) -> str | None:
    """Extract one exact user-owned target from an explicit disease label."""
    normalized = "".join(str(text or "").split()).strip("，,。.!！；;：: ")
    match = SIMPLE_ILLNESS_CREATE_RE.fullmatch(normalized)
    if match is None:
        return None
    candidate = match.group("name").strip("的了，,。.!！；;：: ")
    parenthetical = re.fullmatch(
        r"(?P<acronym>[a-z][a-z0-9-]{1,15})"
        r"(?:\([^()（）]{1,80}\)|（[^()（）]{1,80}）)",
        candidate,
        re.IGNORECASE,
    )
    if parenthetical is not None:
        acronym = parenthetical.group("acronym").casefold()
        if acronym not in SIMPLE_ILLNESS_ACRONYMS:
            return None
        return acronym.upper()
    if not 2 <= len(candidate) <= 80:
        return None
    if illness_target_is_unowned_or_referential(candidate):
        return None
    return (
        candidate.upper()
        if candidate.casefold() in SIMPLE_ILLNESS_ACRONYMS
        else candidate
    )


def _is_compound_record_request(text: str, target_domain: str) -> bool:
    """Keep one-target canonicalization away from multi-write turns.

    The simple goal guard is intentionally authoritative: every model write is
    rewritten to its one normalized payload. Applying it to a compound request
    would collapse distinct writes into one record and let idempotency discard
    the rest. Compound turns therefore stay on the normal multi-tool path.
    """
    water_matches = tuple(WATER_AMOUNT_RE.finditer(text))
    if target_domain == "water" and len(water_matches) > 1:
        return True

    symptom_aliases = sorted(
        {
            alias
            for _, aliases in SIMPLE_SYMPTOM_BODY_PARTS
            for alias in aliases
            if alias in text
        },
        key=len,
        reverse=True,
    )
    distinct_symptoms = [
        alias
        for index, alias in enumerate(symptom_aliases)
        if not any(alias in longer for longer in symptom_aliases[:index])
    ]
    if target_domain == "symptom" and len(distinct_symptoms) > 1:
        return True
    if target_domain == "symptom" and distinct_symptoms:
        first_symptom_end = min(
            text.find(alias) + len(alias)
            for alias in distinct_symptoms
            if text.find(alias) >= 0
        )
        if any(
            text.find(signal, first_symptom_end) >= 0
            for signal in SYMPTOM_COMPOUND_TAIL_SIGNALS
        ):
            return True

    detected_domains: set[str] = set()
    if water_matches:
        detected_domains.add("water")
    if distinct_symptoms:
        detected_domains.add("symptom")
    for domain, signals in OTHER_RECORD_SIGNALS.items():
        if _has_any(text, signals):
            detected_domains.add(domain)
    return any(domain != target_domain for domain in detected_domains)


def format_goal_contract_prompt(goal: GoalSpec | None) -> str:
    """Render executor obligations without exposing internal runtime metadata."""
    return _GOAL_PROMPT_REGISTRY.render(goal)


def registered_goal_compiler_names() -> tuple[str, ...]:
    return _GOAL_COMPILER_REGISTRY.names


def registered_goal_prompt_kinds() -> tuple[str, ...]:
    return _GOAL_PROMPT_REGISTRY.kinds


def _format_diet_recalculation_prompt(goal: GoalSpec) -> str:
    meal_labels = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }
    targets = "、".join(
        meal_labels.get(meal_type, meal_type) for meal_type in goal.target_meal_types
    )
    return (
        "## 本轮任务契约（必须完整执行）\n"
        f"- 目标: 重新估算并更新 {goal.target_date} 的 {targets}。\n"
        "- 顺序: 先查询当天现有饮食记录；按餐次匹配唯一记录；重新估算营养；"
        "使用 health_manage update 更新原记录 ID；最后再次查询并核对结果。\n"
        "- 禁止: 使用 health_record 新增饮食记录，或在没有唯一 record_id 时写入。\n"
        "- 完成标准: 每个目标餐次都有可验证更新回执，且读回结果与目标餐次一致。"
    )


def _format_simple_health_record_prompt(goal: GoalSpec) -> str:
    values = dict(goal.target_values)
    diet_estimation = ""
    if goal.target_record_type == "water" and values.get("amount_ml"):
        payload = f"，amount={values['amount_ml']}ml"
    elif goal.target_record_type == "symptom" and values.get("description"):
        payload = f"，description={values['description']}"
    elif goal.target_record_type == "diet" and values.get("food_items"):
        payload = (
            f"，meal_type={values.get('meal_type')}，food_items={values['food_items']}"
        )
        diet_estimation = (
            "- 饮食估算: 根据上述食物和份量给出合理估算，写入时必须同时包含 "
            "calories/protein/carbs/fat/fiber；不得以 0 或缺失营养值冒充完成。\n"
        )
    elif goal.target_record_type == "illness" and values.get("name"):
        payload = f"，name={values['name']}"
    else:
        payload = ""
    return (
        "## 本轮任务契约（必须完整执行）\n"
        f"- 目标: 只创建 1 条 {goal.target_record_type} 健康记录{payload}。\n"
        "- 执行: 必须调用 health_record，且只使用当前用户消息中的明确事实。\n"
        f"{diet_estimation}"
        "- 禁止: 改写、删除其他记录，或仅用文字声称已经记录。\n"
        "- 完成标准: 收到与目标记录类型一致的 verified write receipt 后才能确认成功。"
    )


def _format_health_manage_mutation_prompt(goal: GoalSpec) -> str:
    record_ids = tuple(
        value for key, value in goal.target_values if key == "record_id"
    )
    target_detail = (
        "，目标 ID: " + "、".join(f"#{record_id}" for record_id in record_ids)
        if record_ids
        else ""
    )
    lookup_rule = (
        "先查询本人对应记录并确认上述全部 ID 都存在，再按完整目标集执行变更；"
        "任一 ID 未找到时禁止执行任何删除。"
        if goal.operation == "delete" and len(record_ids) > 1
        else "先查询本人对应记录并确定唯一目标，再执行变更。"
    )
    return (
        "## 本轮任务契约（必须完整执行）\n"
        f"- 目标: 仅对本人 {goal.target_record_type} 记录执行 {goal.operation}"
        f"{target_detail}。\n"
        f"- 顺序: {lookup_rule}\n"
        "- 禁止: 查询其他记录类型、使用未出现在本人查询结果中的 ID，或新增记录。\n"
        "- 完成标准: 每个目标都收到匹配类型的 verified write receipt 后才能确认全部成功。"
    )


def goal_spec_contract_payload() -> dict[str, str]:
    """Return code- and grammar-sensitive goal authorization evidence."""
    content = {
        "version": GOAL_SPEC_CONTRACT_VERSION,
        "grammar_digest": authorization_grammar_digest(globals()),
        "behavior_digest": authorization_behavior_digest(
            globals(),
            tuple(
                sorted(
                    set(authorization_module_behavior_names(globals(), __name__))
                    | set(
                        authorization_imported_behavior_names(globals(), __name__)
                    )
                )
            ),
        ),
        "update_authorization_grammar_digest": authorization_grammar_digest(
            vars(write_intent_scope_module)
        ),
        "update_authorization_behavior_digest": authorization_behavior_digest(
            vars(write_intent_scope_module),
            authorization_module_behavior_names(
                vars(write_intent_scope_module),
                write_intent_scope_module.__name__,
            ),
        ),
        "write_safety_grammar_digest": authorization_grammar_digest(
            vars(write_safety_module)
        ),
        "write_safety_behavior_digest": authorization_behavior_digest(
            vars(write_safety_module),
            authorization_module_behavior_names(
                vars(write_safety_module),
                write_safety_module.__name__,
            ),
        ),
    }
    encoded = json.dumps(
        content,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {**content, "content_digest": hashlib.sha256(encoded).hexdigest()}


def _water_amount_ml(text: str) -> int | None:
    match = WATER_AMOUNT_RE.search(text)
    if match is None:
        normalized = "".join(str(text or "").split())
        return next(
            (
                amount_ml
                for phrase, amount_ml in WATER_CONTAINER_AMOUNTS
                if phrase in normalized
            ),
            None,
        )
    parsed = _parse_number(match.group("amount"))
    if parsed is None:
        return None
    if match.group("unit").lower() in {"升", "l"}:
        parsed *= 1000
    amount_ml = int(round(parsed))
    return amount_ml if 1 <= amount_ml <= 5000 else None


def _parse_number(value: str) -> float | None:
    if value == "半":
        return 0.5
    mixed_unit = re.fullmatch(
        r"(?P<number>\d+(?:\.\d+)?)(?P<unit>十|百|千|万)",
        value,
    )
    if mixed_unit is not None:
        return (
            float(mixed_unit.group("number"))
            * {
                "十": 10,
                "百": 100,
                "千": 1000,
                "万": 10000,
            }[mixed_unit.group("unit")]
        )
    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    if "点" in value:
        integer, fraction = value.split("点", 1)
        integer_value = _parse_chinese_integer(integer)
        fraction_digits = "".join(
            str(_CHINESE_DIGITS.get(char, "")) for char in fraction
        )
        if integer_value is None or not fraction_digits:
            return None
        return float(f"{integer_value}.{fraction_digits}")
    integer_value = _parse_chinese_integer(value)
    return float(integer_value) if integer_value is not None else None


def _simple_symptom_target(text: str) -> dict[str, str] | None:
    """Return only a high-confidence symptom payload owned by this user turn."""
    description = str(text or "").strip("。！？!?；;，, ")
    if not description:
        return None
    normalized = _normalize(description)
    for body_part, markers in SIMPLE_SYMPTOM_BODY_PARTS:
        if any(marker in normalized for marker in markers):
            return {
                "body_part": body_part,
                "description": description[:500],
            }
    if "症状" in normalized or any(
        marker in normalized for marker in ("不适", "难受", "不舒服")
    ):
        return {
            "body_part": "general",
            "description": description[:500],
        }
    return None


def _simple_diet_target(
    text: str,
    *,
    local_hour: int,
) -> dict[str, str] | None:
    """Extract one meal and its user-owned food description.

    An explicit meal label remains authoritative.  When the current turn is
    already an unambiguous ``diet/create`` intent, ordinary phrases such as
    ``记录吃了一个桃子`` may omit that label; reuse the product's established
    local-time meal inference instead of falling back to an unbounded model
    write.
    """
    raw = str(text or "").strip()
    if not raw:
        return None

    meal_matches: list[tuple[int, int, str]] = []
    for meal_type, signals in MEAL_SIGNALS.items():
        for signal in signals:
            start = raw.find(signal)
            if start >= 0:
                meal_matches.append((start, start + len(signal), meal_type))
    if meal_matches:
        meal_types = {match[2] for match in meal_matches}
        if len(meal_types) != 1:
            return None
        _, meal_end, meal_type = min(meal_matches, key=lambda item: item[0])
        foods = raw[meal_end:]
    else:
        match = re.search(
            r"(?:记录(?:一下)?|记下|打卡|帮我记录)?\s*"
            r"(?:我)?\s*(?:(?:刚才|刚刚|已经|今天)\s*)?"
            r"(?:吃了|吃的是|吃|点了)\s*(?P<foods>.+)",
            raw,
        )
        if match is None:
            return None
        foods = match.group("foods")
        from app.services.diet_voice_parser import infer_meal_type

        meal_type = infer_meal_type(raw, local_hour)
    foods = re.sub(
        r"^[\s，,。.!！；;：:]*(?:我)?"
        r"(?:(?:刚才|刚刚|已经)?(?:吃了|吃的是|吃|有)|是)?"
        r"[\s，,。.!！；;：:]*",
        "",
        foods,
        count=1,
    )
    foods = DIET_TRAILING_WRITE_RE.sub("", foods)
    foods = DIET_TRAILING_ANALYSIS_RE.sub("", foods).strip(" \t\r\n，,。.!！；;：:")
    if (
        not foods
        or foods in {"饮食", "一餐", "这餐", "饭", "食物"}
        or not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", foods)
    ):
        return None
    return {
        "meal_type": meal_type,
        "food_items": foods[:1000],
    }


def _simple_record_write_is_negated(text: str) -> bool:
    """Detect cancellation of the write action, not food preferences."""
    return is_explicit_write_cancellation(text)


def _simple_record_is_question(text: str) -> bool:
    """Keep imperative food modifiers such as “需要少盐” on the write path."""
    normalized = str(text or "").strip()
    return bool(
        "?" in normalized
        or "？" in normalized
        or "是否" in normalized
        or "是不是" in normalized
        or re.search(r"(?:吗|么|嘛)[。.!！]*$", normalized)
    )


_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _parse_chinese_integer(value: str) -> int | None:
    if not value:
        return 0
    if all(char in _CHINESE_DIGITS for char in value):
        return int("".join(str(_CHINESE_DIGITS[char]) for char in value))

    result = 0
    section = 0
    digit = 0
    for char in value:
        if char in _CHINESE_DIGITS:
            digit = _CHINESE_DIGITS[char]
            continue
        unit = _CHINESE_UNITS.get(char)
        if unit is None:
            return None
        if unit == 10000:
            section = (section + digit) * unit
            result += section
            section = 0
        else:
            section += (digit or 1) * unit
        digit = 0
    return result + section + digit


def _target_meal_types(
    text: str,
    references: Sequence[ActionableReference],
) -> tuple[str, ...]:
    targets: list[str] = []
    if "早午两餐" in text or "早餐午餐" in text or "早饭午饭" in text:
        targets.extend(("breakfast", "lunch"))
    for meal_type, signals in MEAL_SIGNALS.items():
        if _has_any(text, signals) and meal_type not in targets:
            targets.append(meal_type)
    if targets:
        return tuple(targets)
    if _has_any(text, REFERENTIAL_SIGNALS):
        visible = _visible_meal_types(references)
        if "两餐" in text and len(visible) == 2:
            return visible
        if len(visible) == 1:
            return visible
    return ()


def _visible_meal_types(
    references: Sequence[ActionableReference],
) -> tuple[str, ...]:
    result: list[str] = []
    for reference in references:
        if reference.kind not in {"diet_daily_summary", "diet", "diet_record"}:
            continue
        for meal in reference.data.get("meals") or ():
            meal_type = str(meal.get("meal_type") or "").strip().lower()
            if meal_type in MEAL_SIGNALS and meal_type not in result:
                result.append(meal_type)
    return tuple(result)


def _reference_foods(
    references: Sequence[ActionableReference],
    target_meals: tuple[str, ...],
    *,
    target_date: str,
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for reference in references:
        if reference.kind not in {"diet_daily_summary", "diet", "diet_record"}:
            continue
        reference_date = str(reference.data.get("record_date") or "").strip()[:10]
        if reference_date and reference_date != target_date:
            continue
        for meal in reference.data.get("meals") or ():
            meal_type = str(meal.get("meal_type") or "").strip().lower()
            food_items = str(meal.get("food_items") or "").strip()
            if meal_type in target_meals and food_items:
                result.append((meal_type, food_items[:500]))
    return tuple(result)


def _target_date(
    text: str,
    context: ExecutionContext,
    references: Sequence[ActionableReference],
) -> str:
    explicit = _explicit_target_date(text, context.current_time.date())
    if explicit is not None:
        return explicit
    for reference in references:
        value = str(reference.data.get("record_date") or "").strip()
        if value:
            return value[:10]
    return context.current_time.date().isoformat()


def _explicit_target_date(text: str, today: date) -> str | None:
    """Resolve user-owned date language before consulting visible-card context."""
    _found, resolved = _explicit_target_date_status(text, today)
    return resolved


def _explicit_target_date_is_invalid(text: str, today: date) -> bool:
    found, resolved = _explicit_target_date_status(text, today)
    return found and resolved is None


def _explicit_target_date_status(
    text: str,
    today: date,
) -> tuple[bool, str | None]:
    """Return whether the user supplied a date and its validated value."""
    relative = (
        ("前天", -2),
        ("昨天", -1),
        ("昨日", -1),
        ("今天", 0),
        ("今日", 0),
        ("明天", 1),
        ("明日", 1),
    )
    for signal, offset in relative:
        if signal in text:
            return True, (today + timedelta(days=offset)).isoformat()

    iso_match = re.search(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text)
    if iso_match:
        try:
            return True, date(*(int(value) for value in iso_match.groups())).isoformat()
        except ValueError:
            return True, None

    chinese_match = re.search(
        r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})[日号]?",
        text,
    )
    if chinese_match:
        year, month, day = chinese_match.groups()
        try:
            return True, date(
                int(year or today.year),
                int(month),
                int(day),
            ).isoformat()
        except ValueError:
            return True, None
    return False, None


def _fallback_kind(intent: IntentFrame) -> str:
    if intent.primary in {"read", "advice"}:
        return "answer"
    if intent.primary in {"write", "mutate"}:
        return intent.primary
    return "chat"


def _normalize(value: str) -> str:
    return "".join(str(value or "").lower().split())


def _has_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


_GOAL_COMPILER_REGISTRY = GoalCompilerRegistry(
    (
        GoalCompilerSpec(
            name="diet_recalculation",
            compiler=_compile_diet_recalculation_goal,
        ),
        GoalCompilerSpec(
            name="simple_health_record",
            compiler=_compile_simple_health_record_goal,
        ),
        GoalCompilerSpec(
            name="health_manage_mutation",
            compiler=_compile_health_manage_mutation_goal,
        ),
    )
)

_GOAL_PROMPT_REGISTRY = GoalPromptRegistry(
    (
        GoalPromptSpec(
            kind="diet_recalculate_update",
            renderer=_format_diet_recalculation_prompt,
        ),
        GoalPromptSpec(
            kind="simple_health_record",
            renderer=_format_simple_health_record_prompt,
        ),
        GoalPromptSpec(
            kind="health_manage_mutation",
            renderer=_format_health_manage_mutation_prompt,
        ),
    )
)
