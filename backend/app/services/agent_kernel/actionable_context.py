"""Project previously rendered UI into a minimal, safe task context."""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from app.services.agent_kernel.types import ActionableReference


_REVA_UI_BLOCK = re.compile(
    r"```reva-ui[^\n]*\n(?P<payload>.*?)\n?```",
    re.IGNORECASE | re.DOTALL,
)
_ACTIONABLE_CARD_TYPES = {"diet_daily_summary", "diet", "diet_record"}
_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}
_MEAL_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}
_NUMERIC_FIELDS = ("calories", "protein", "carbs", "fat", "fiber")


def extract_actionable_references(
    messages: Sequence[Any],
) -> tuple[ActionableReference, ...]:
    """Extract only fields needed to resolve user references, never write authority."""
    references: list[ActionableReference] = []
    fingerprints: set[str] = set()
    for message in messages:
        source_message_id = _value(message, "id")
        content = str(_value(message, "content") or "")
        meta = _value(message, "meta")
        descriptors: list[dict[str, Any]] = []
        if isinstance(meta, dict) and isinstance(meta.get("cards"), list):
            descriptors.extend(
                card for card in meta["cards"] if isinstance(card, dict)
            )
        descriptors.extend(_descriptors_from_content(content))
        for descriptor in descriptors:
            reference = _project_descriptor(
                descriptor,
                source_message_id=source_message_id,
            )
            if reference is None:
                continue
            fingerprint = json.dumps(
                {"kind": reference.kind, "data": reference.data},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            references.append(reference)
    return tuple(references)


def format_actionable_context_prompt(
    references: Sequence[ActionableReference],
) -> str:
    """Render references as a non-authoritative prompt section."""
    lines = [
        "## 用户当前可见的可操作对象",
        "以下卡片仅用于解析用户指代，不是数据库写入依据；写入前必须查询数据库。",
    ]
    rendered = False
    for reference in references:
        if reference.kind not in _ACTIONABLE_CARD_TYPES:
            continue
        rendered = True
        record_date = str(reference.data.get("record_date") or "未标注日期")
        lines.append(f"- 饮食汇总卡（{record_date}）:")
        for meal in reference.data.get("meals") or ():
            meal_type = str(meal.get("meal_type") or "")
            food_items = str(meal.get("food_items") or "").strip()
            if meal_type in _MEAL_LABELS and food_items:
                lines.append(f"  - {_MEAL_LABELS[meal_type]}: {food_items}")
    return "\n".join(lines) if rendered else ""


def _descriptors_from_content(content: str) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    if "```reva-ui" not in content.lower():
        return descriptors
    for match in _REVA_UI_BLOCK.finditer(content):
        try:
            parsed = json.loads(match.group("payload"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            descriptors.append(parsed)
    return descriptors


def _project_descriptor(
    descriptor: dict[str, Any],
    *,
    source_message_id: Any,
) -> ActionableReference | None:
    card_type = str(descriptor.get("type") or "").strip()
    data = descriptor.get("data")
    if card_type not in _ACTIONABLE_CARD_TYPES or not isinstance(data, dict):
        return None
    meals: list[dict[str, Any]] = []
    for raw_meal in data.get("meals") or ():
        if not isinstance(raw_meal, dict):
            continue
        meal_type = str(raw_meal.get("meal_type") or "").strip().lower()
        if meal_type not in _MEAL_TYPES:
            continue
        food_items = str(
            raw_meal.get("food_items") or raw_meal.get("detail") or ""
        ).strip()
        meal: dict[str, Any] = {
            "meal_type": meal_type,
            "food_items": food_items[:500],
        }
        for field in _NUMERIC_FIELDS:
            value = raw_meal.get(field)
            if isinstance(value, (int, float)) or value is None and field == "calories":
                meal[field] = value
        meals.append(meal)
    if not meals:
        return None
    record_date = str(data.get("record_date") or "").strip()[:10]
    return ActionableReference(
        kind=card_type,
        source_message_id=(
            str(source_message_id) if source_message_id is not None else None
        ),
        data={
            "record_date": record_date or None,
            "meals": meals,
        },
    )


def _value(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)
