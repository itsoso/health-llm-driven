"""Display complete attested records without delegating factual copy to a model."""

from __future__ import annotations

import html
import json
import math
import re

from app.services.agent_composed_read_completion import ComposedReadCompletion
from app.utils.number_format import format_display_number


def _quoted(value: str) -> str:
    # Preserve free text as a quoted data value, not HTML, Markdown links/cards,
    # or extra lines. Never interpret stored text as instructions or authority.
    text = json.dumps(value, ensure_ascii=False)
    return re.sub(r"([\\`*_\[\]])", r"\\\1", html.escape(text, quote=False))


def _number(value) -> str | None:
    if type(value) not in {int, float, str}:
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return str(format_display_number(number))


def render_verified_diet_lookup(query: dict, completion: ComposedReadCompletion) -> str | None:
    """The caller binds owner/date and verifies the read; this only formats it.

    Fail back to the normal answer path on unsupported evidence. No grouping,
    deduplication, omitted rows, inferred meals, or missing-number substitution.
    """
    evidence = completion.verified_evidence
    if (not completion.complete or not completion.trusted_fact_summary
            or not evidence or query.get("dimension") != "diet"
            or not query.get("start_date") or query.get("start_date") != query.get("end_date")):
        return None
    queries = evidence.get("queries", [])
    if len(queries) != 1 or queries[0].get("query") != query:
        return None
    data = queries[0]
    records = data.get("records")
    if not isinstance(records, list) or data.get("record_count") != len(records):
        return None
    lines = [completion.trusted_fact_summary]
    meals = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}
    for index, record in enumerate(records, 1):
        known = record.get("known_fields", {})
        if known.get("record_date") != query["start_date"]:
            return None
        # Unsupported free text/numbers must not be silently discarded.
        if "unsupported_value" in record.get("unknown_fields", {}).values():
            return None
        parts = [query["start_date"]]
        meal = known.get("meal_type")
        parts.append(meals.get(meal, _quoted(meal)) if meal else "餐次未知")
        for field, label in (("meal_time", "时间"), ("food_name", "食物"), ("food_items", "食物明细")):
            if field in known:
                parts.append(label + "：" + _quoted(known[field]))
        if "food_name" not in known and "food_items" not in known:
            parts.append("食物名称未知")
        if "quantity" in known:
            amount = _number(known["quantity"])
            if amount is None:
                return None
            parts.append("份量：" + amount + (" " + _quoted(known["unit"]) if "unit" in known else "（单位未知）"))
        for field, label, unit in (("calories", "热量", "kcal"), ("protein", "蛋白质", "g"),
                                   ("carbs", "碳水", "g"), ("fat", "脂肪", "g"), ("fiber", "膳食纤维", "g")):
            if field not in known:
                parts.append(label + "未知")
                continue
            number = _number(known[field])
            if number is None:
                return None
            parts.append(f"{label} {number} {unit}")
        lines.append(f"{index}. " + "；".join(parts))
    if records:
        lines.append("以上仅为本次返回的记录；未知字段不代表零，未返回记录不代表未进食。")
    return "\n\n".join(lines)
