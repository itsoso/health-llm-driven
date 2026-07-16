"""GenUI diet_daily_summary 构建器 — 确定性把今日饮食汇总打成结构化 reva-ui 卡片。

汇总类卡结构化 v1(founder 2026-07-16 立项)。北极星 = 恢复总览卡的设计语言。
数据来自 agent_read_tools 今日饮食汇总(DailyDietSummary:meals + 宏量合计);
observations 由本模块**确定性派生**(只读数值 + 常识阈值,factual 陈述、禁命令式 —— 守
R4:builder 绝不自判医学等级、绝不编造个性化处方);actions 沿用既有 route.open。

cap 暗置(genui-diet-summary-v1):composer/renderer 就绪但不点亮,eval 过闸后开。
契约字段与 mobile DietSummaryCard 的 parse* 一字对齐(meal_type/name/detail/
calories/protein/carbs/fat · totals · water.current_ml/target_ml · observations.severity/label/detail)。
"""
from __future__ import annotations

import json
from typing import Any, Optional

DIET_SUMMARY_TYPE = "diet_daily_summary"
GENUI_DIET_SUMMARY_CAP = "genui-diet-summary-v1"  # 客户端能力位(点亮门控)
_VERSION = "v1"

# MealType.value → mobile 期望键(extra=加餐 → snack);未知 → snack。
_MEAL_KEY = {
    "breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner",
    "snack": "snack", "extra": "snack",
}
_MEAL_LABEL = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}
_MEAL_ORDER = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}

_FIBER_TARGET_G = 25.0    # 膳食纤维通用推荐(营养常识阈值,非个性化处方)
_FAT_PCT_CAUTION = 35.0   # 脂肪占总热量上限(常识阈值)
_PROTEIN_GKG_LOW = 1.0    # 蛋白 g/kg 下限(有体重时判偏低)


def _round(v: Any, nd: int = 1) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(round(f)) if nd == 0 else round(f, nd)


def _derive_observations(totals: dict, *, weight_kg: Optional[float] = None) -> list[dict]:
    """确定性派生关键观察 —— 只读数值 + 常识阈值,factual 陈述,severity ∈ normal/caution。

    R4:不写命令式("必须/务必…")、不判医学诊断;只陈述测得值与通用阈值的关系。
    """
    obs: list[dict] = []
    # 健壮性(safety advisory):真实 DailyDietSummary 宏量非负,但入参负数/垃圾会渲染出
    # 无意义串 → 一律钳到 ≥0;非数值视作缺值(None)。
    def _nn(x):
        try:
            f = float(x)
        except (TypeError, ValueError):
            return None
        return max(0.0, f)

    cal = _nn(totals.get("calories")) or 0
    protein = _nn(totals.get("protein"))
    fat = _nn(totals.get("fat"))
    fiber = _nn(totals.get("fiber"))

    if protein is not None:
        if weight_kg and weight_kg > 0:
            gkg = protein / weight_kg
            caution = gkg < _PROTEIN_GKG_LOW
            obs.append({
                "severity": "caution" if caution else "normal",
                "label": "蛋白质偏低" if caution else "蛋白质充足",
                "detail": f"全天 {protein:.0f}g(约 {gkg:.2f}g/kg)。",
            })
        else:
            obs.append({"severity": "normal", "label": "蛋白质",
                        "detail": f"全天 {protein:.0f}g。"})

    if fat is not None and cal and cal > 0:
        pct = (fat * 9.0) / cal * 100.0
        caution = pct > _FAT_PCT_CAUTION
        obs.append({
            "severity": "caution" if caution else "normal",
            "label": "脂肪偏高" if caution else "脂肪适中",
            "detail": f"全天 {fat:.0f}g,占总热量约 {pct:.0f}%。",
        })

    if fiber is not None:
        caution = fiber < _FIBER_TARGET_G
        obs.append({
            "severity": "caution" if caution else "normal",
            "label": "膳食纤维不足" if caution else "膳食纤维充足",
            "detail": f"约 {fiber:.0f}g,一般建议 {int(_FIBER_TARGET_G)}g+。",
        })

    return obs[:4]


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
            "calories": _round(m.get("calories"), 0),
            "protein": _round(m.get("protein")),
            "carbs": _round(m.get("carbs")),
            "fat": _round(m.get("fat")),
        })
    if not meals:
        return None
    meals.sort(key=lambda x: _MEAL_ORDER.get(x["meal_type"], 9))

    totals = {
        "calories": _round(summary.get("total_calories"), 0),
        "protein": _round(summary.get("total_protein")),
        "carbs": _round(summary.get("total_carbs")),
        "fat": _round(summary.get("total_fat")),
        "fiber": _round(summary.get("total_fiber")),
    }

    data: dict[str, Any] = {
        "record_date": (str(summary.get("record_date") or "").strip() or None),
        "meals": meals,
        "totals": totals,
        "observations": _derive_observations(totals, weight_kg=weight_kg),
    }
    if isinstance(water, dict):
        cur = _round(water.get("current_ml"), 0)
        tgt = _round(water.get("target_ml"), 0)
        if cur is not None and tgt is not None and tgt > 0:
            data["water"] = {"current_ml": cur, "target_ml": tgt}

    return {"type": DIET_SUMMARY_TYPE, "v": _VERSION, "data": data}


def render_diet_summary_block(descriptor: dict) -> str:
    """descriptor → ```reva-ui fenced 文本(嵌进 assistant 消息,与 table/chart 同机制)。"""
    payload = json.dumps(descriptor, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"
