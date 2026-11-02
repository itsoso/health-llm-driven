"""Display complete attested records without delegating factual copy to a model."""

from __future__ import annotations

import html
import json
import math
import re
from datetime import date

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


def _valid_window(query: dict) -> bool:
    try:
        start, end = (date.fromisoformat(query[key]) for key in ('start_date', 'end_date'))
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= (end - start).days < 31


def render_verified_diet_lookup(query: dict, completion: ComposedReadCompletion) -> str | None:
    """The caller binds owner/date and verifies the read; this only formats it.

    Fail back to the normal answer path on unsupported evidence. No grouping,
    deduplication, omitted rows, inferred meals, or missing-number substitution.
    """
    evidence = completion.verified_evidence
    if (not completion.complete or not completion.trusted_fact_summary
            or not evidence or query.get("dimension") != "diet"
            or not _valid_window(query)):
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
        if not isinstance(known.get("record_date"), str) or not query["start_date"] <= known["record_date"] <= query["end_date"]:
            return None
        # Unsupported free text/numbers must not be silently discarded.
        if "unsupported_value" in record.get("unknown_fields", {}).values():
            return None
        parts = [known["record_date"]]
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


def render_verified_sleep_lookup(query: dict, completion: ComposedReadCompletion) -> str | None:
    """Show each verified wake date; never invent an aggregate or score label."""
    evidence = completion.verified_evidence
    if (not completion.complete or not completion.trusted_fact_summary or not evidence
            or query.get('dimension') != 'sleep' or not _valid_window(query)):
        return None
    queries = evidence.get('queries', [])
    if len(queries) != 1 or queries[0].get('query') != query:
        return None
    records = queries[0].get('records')
    if not isinstance(records, list) or queries[0].get('record_count') != len(records):
        return None
    lines = [completion.trusted_fact_summary]
    fields = (('total_sleep_duration', '睡眠时长', '分钟'), ('sleep_score', '评分', '分'),
              ('deep_sleep_duration', '深睡', '分钟'), ('rem_sleep_duration', 'REM', '分钟'),
              ('light_sleep_duration', '浅睡', '分钟'), ('awake_duration', '清醒', '分钟'))
    for row in records:
        known = row.get('known_fields', {})
        day = known.get('record_date')
        if (not isinstance(day, str) or not query['start_date'] <= day <= query['end_date']
                or 'unsupported_value' in row.get('unknown_fields', {}).values()):
            return None
        parts = [day]
        for field, label, unit in fields:
            if field not in known:
                parts.append(label + '未知')
                continue
            value = _number(known[field])
            if value is None:
                return None
            parts.append(label + ' ' + value + ' ' + unit)
        for field, label in (('sleep_start_time', '入睡时间'), ('sleep_end_time', '醒来时间')):
            parts.append(label + '：' + _quoted(known[field]) if field in known else label + '未知')
        lines.append('；'.join(parts))
    return '\n\n'.join(lines)
