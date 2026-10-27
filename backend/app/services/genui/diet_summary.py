"""GenUI diet_daily_summary 构建器 — 确定性把今日饮食汇总打成结构化 reva-ui 卡片。

汇总类卡结构化 v1(founder 2026-07-16 立项)。北极星 = 恢复总览卡的设计语言。
数据来自 agent_read_tools 今日饮食汇总(DailyDietSummary:meals + 宏量合计);
仅对逐条已知值求小计；缺值不作零。已记录餐次不证明全天完整，故不推断营养充足或不足。

cap 暗置(genui-diet-summary-v1):composer/renderer 就绪但不点亮,eval 过闸后开。
契约字段与 mobile DietSummaryCard 的 parse* 一字对齐(meal_type/name/detail/
calories/protein/carbs/fat · totals · water.current_ml/target_ml · observations.severity/label/detail)。
"""
from __future__ import annotations

import json
import math
from typing import Any, Optional

from app.utils.number_format import format_display_number

DIET_SUMMARY_TYPE = "diet_daily_summary"
GENUI_DIET_SUMMARY_CAP = "genui-diet-summary-v1"  # 客户端能力位(点亮门控)
# reva-ui 信封版本 = 整数 1(与 metric_table/charts 同一契约;移动端 fence parser 校验 v===1)。
# 注意:cap token 用 "genui-diet-summary-v1" 字符串,但**块内 v 是整数**,别混。
_VERSION = 1

# MealType.value → mobile 期望键(extra=加餐 → snack);未知 → snack。
_MEAL_KEY = {
    "breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner",
    "snack": "snack", "extra": "snack",
}
_MEAL_LABEL = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}
_MEAL_ORDER = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}

_NUTRIENTS = ("calories", "protein", "carbs", "fat", "fiber")


def _nutrient(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _round(value: Any) -> Optional[float]:
    number = _nutrient(value)
    return format_display_number(number) if number is not None else None


def build_diet_daily_summary(
    summary: dict,
    *,
    water: Optional[dict] = None,
    weight_kg: Optional[float] = None,
) -> Optional[dict]:
    """DailyDietSummary dict → diet_daily_summary descriptor。无餐次 → None(fail-open,回退 markdown)。"""
    if not isinstance(summary, dict):
        return None
    raw_meals = summary.get("meals")
    if not isinstance(raw_meals, list) or not raw_meals:
        return None

    meals: list[dict] = []
    for m in raw_meals:
        if not isinstance(m, dict):
            continue
        mt = str(m.get("meal_type") or "").strip().lower()
        key = _MEAL_KEY.get(mt, "snack")
        meals.append({
            "meal_type": key,
            "name": _MEAL_LABEL[key],
            "detail": (str(m.get("food_items") or "").strip() or None),
            "calories": _round(m.get("calories")),
            "protein": _round(m.get("protein")),
            "carbs": _round(m.get("carbs")),
            "fat": _round(m.get("fat")),
        })
    if not meals:
        return None
    meals.sort(key=lambda x: _MEAL_ORDER.get(x["meal_type"], 9))

    # Upstream sums use `or 0`; rebuild from individual raw values so unknown
    # stays unknown, and sum before applying display precision.
    rows = [{key: _nutrient(m.get(key)) for key in _NUTRIENTS}
            for m in raw_meals if isinstance(m, dict)]
    totals = {}
    for key in _NUTRIENTS:
        known = [row[key] for row in rows if row[key] is not None]
        totals[key] = _round(sum(known)) if known else None
    coverage = {
        "version": 1,
        "record_count": len(rows),
        "incomplete_records": sum(any(row[key] is None for key in _NUTRIENTS[:4]) for row in rows),
        "missing_by_nutrient": {key: sum(row[key] is None for row in rows) for key in _NUTRIENTS},
    }

    data: dict[str, Any] = {
        "record_date": (str(summary.get("record_date") or "").strip() or None),
        "meals": meals,
        "totals": totals,
        "nutrition_coverage": coverage,
        "observations": [],
    }
    if isinstance(water, dict):
        cur = _round(water.get("current_ml"))
        tgt = _round(water.get("target_ml"))
        if cur is not None and tgt is not None and tgt > 0:
            data["water"] = {"current_ml": cur, "target_ml": tgt}

    return {"type": DIET_SUMMARY_TYPE, "v": _VERSION, "data": data}


def render_diet_summary_block(descriptor: dict) -> str:
    """descriptor → ```reva-ui fenced 文本(嵌进 assistant 消息,与 table/chart 同机制)。"""
    payload = json.dumps(descriptor, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"
