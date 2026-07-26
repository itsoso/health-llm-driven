"""Compile a user turn into a deterministic, verifiable task contract."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
import re

from app.services.agent_kernel.goal_registry import (
    GoalCompilerRegistry,
    GoalCompilerSpec,
    GoalPromptRegistry,
    GoalPromptSpec,
)
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    GoalSpec,
    IntentFrame,
)
from app.services.agent_kernel.write_safety import is_explicit_write_cancellation


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
WATER_SIGNALS = ("喝水", "饮水", "补水")
WATER_AMOUNT_RE = re.compile(
    r"(?:喝水|饮水|补水)"
    r"(?:了)?(?:约|大约|差不多)?"
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
DIET_TRAILING_WRITE_RE = re.compile(
    r"(?:[\s，,。.!！；;：:]*)"
    r"(?:请)?(?:帮我|给我)?"
    r"(?:记录|记下|记一下|保存|录入|加到饮食)(?:一下|下)?"
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


def compile_goal_spec(
    *,
    envelope: AgentEnvelope,
    context: ExecutionContext,
    intent: IntentFrame,
    actionable_references: Sequence[ActionableReference] = (),
) -> GoalSpec:
    """Create the executor contract without granting authority to visible data."""
    text = _normalize(envelope.text)
    if (
        intent.is_write
        and _explicit_target_date_is_invalid(
            text,
            context.current_time.date(),
        )
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
        envelope=envelope,
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
            ("create", "update")
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
            prohibited_operations=("create", "update"),
        )

    if is_question and is_recalculation:
        return GoalSpec(
            kind="answer",
            domain="diet",
            operation="ask",
            target_date=target_date,
            target_meal_types=target_meals,
            prohibited_operations=("create", "update"),
        )

    if is_recalculation and wants_update:
        if has_referent and not target_meals:
            return GoalSpec(
                kind="clarify",
                domain="diet",
                operation="none",
                target_date=target_date,
                requires_clarification=True,
                prohibited_operations=("create", "update"),
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
                prohibited_operations=("create",),
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
    if (
        envelope.media
        or intent.primary not in {"write", "mutate"}
        or intent.operation != "create"
        or not intent.is_write
        or _simple_record_write_is_negated(text)
        or _simple_record_is_question(text)
        or _is_compound_record_request(text, intent.domain)
    ):
        return None

    target_values: tuple[tuple[str, str], ...] = ()
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
        diet_target = _simple_diet_target(envelope.text)
        if diet_target is None:
            return None
        record_type = "diet"
        target_values = tuple(diet_target.items())
    else:
        return None

    target_meal_types = (
        (dict(target_values)["meal_type"],)
        if record_type == "diet"
        else ()
    )
    return GoalSpec(
        kind="simple_health_record",
        domain=intent.domain,
        operation="create",
        target_date=(
            _target_date(text, context, ())
            if record_type == "diet"
            else context.current_time.date().isoformat()
        ),
        target_meal_types=target_meal_types,
        target_record_type=record_type,
        target_values=target_values,
        requires_verification=True,
        prohibited_operations=("update", "delete"),
        postconditions=("verified_receipt",),
        evidence=("current_user_turn",),
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
        meal_labels.get(meal_type, meal_type)
        for meal_type in goal.target_meal_types
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
    if goal.target_record_type == "water" and values.get("amount_ml"):
        payload = f"，amount={values['amount_ml']}ml"
    elif goal.target_record_type == "symptom" and values.get("description"):
        payload = f"，description={values['description']}"
    elif goal.target_record_type == "diet" and values.get("food_items"):
        payload = (
            f"，meal_type={values.get('meal_type')}，"
            f"food_items={values['food_items']}"
        )
    else:
        payload = ""
    return (
        "## 本轮任务契约（必须完整执行）\n"
        f"- 目标: 只创建 1 条 {goal.target_record_type} 健康记录{payload}。\n"
        "- 执行: 必须调用 health_record，且只使用当前用户消息中的明确事实。\n"
        "- 禁止: 改写、删除其他记录，或仅用文字声称已经记录。\n"
        "- 完成标准: 收到与目标记录类型一致的 verified write receipt 后才能确认成功。"
    )


def _water_amount_ml(text: str) -> int | None:
    match = WATER_AMOUNT_RE.search(text)
    if match is None:
        return None
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
        return float(mixed_unit.group("number")) * {
            "十": 10,
            "百": 100,
            "千": 1000,
            "万": 10000,
        }[mixed_unit.group("unit")]
    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    if "点" in value:
        integer, fraction = value.split("点", 1)
        integer_value = _parse_chinese_integer(integer)
        fraction_digits = "".join(
            str(_CHINESE_DIGITS.get(char, ""))
            for char in fraction
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


def _simple_diet_target(text: str) -> dict[str, str] | None:
    """Extract one explicit meal and its user-owned food description."""
    raw = str(text or "").strip()
    if not raw:
        return None

    meal_matches: list[tuple[int, int, str]] = []
    for meal_type, signals in MEAL_SIGNALS.items():
        for signal in signals:
            start = raw.find(signal)
            if start >= 0:
                meal_matches.append((start, start + len(signal), meal_type))
    if not meal_matches:
        return None

    meal_types = {match[2] for match in meal_matches}
    if len(meal_types) != 1:
        return None

    _, meal_end, meal_type = min(meal_matches, key=lambda item: item[0])
    foods = raw[meal_end:]
    foods = re.sub(
        r"^[\s，,。.!！；;：:]*(?:我)?"
        r"(?:(?:刚才|刚刚|已经)?(?:吃了|吃的是|吃|有)|是)?"
        r"[\s，,。.!！；;：:]*",
        "",
        foods,
        count=1,
    )
    foods = DIET_TRAILING_WRITE_RE.sub("", foods).strip(
        " \t\r\n，,。.!！；;：:"
    )
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
            return True, date(
                *(int(value) for value in iso_match.groups())
            ).isoformat()
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
    )
)
