"""Compile a user turn into a deterministic, verifiable task contract."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
import re

from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    GoalSpec,
    IntentFrame,
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


def compile_goal_spec(
    *,
    envelope: AgentEnvelope,
    context: ExecutionContext,
    intent: IntentFrame,
    actionable_references: Sequence[ActionableReference] = (),
) -> GoalSpec:
    """Create the executor contract without granting authority to visible data."""
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


def format_goal_contract_prompt(goal: GoalSpec | None) -> str:
    """Render executor obligations without exposing internal runtime metadata."""
    if goal is None or goal.kind != "diet_recalculate_update":
        return ""
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
            return (today + timedelta(days=offset)).isoformat()

    iso_match = re.search(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text)
    if iso_match:
        try:
            return date(*(int(value) for value in iso_match.groups())).isoformat()
        except ValueError:
            return None

    chinese_match = re.search(
        r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})[日号]?",
        text,
    )
    if chinese_match:
        year, month, day = chinese_match.groups()
        try:
            return date(int(year or today.year), int(month), int(day)).isoformat()
        except ValueError:
            return None
    return None


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
