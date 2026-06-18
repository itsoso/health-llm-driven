"""智能日程 D1(三餐+营养)+ D2(睡眠卫生)—— timing-solver 的「饮食」「睡眠」两域。

把 cut A(锻炼处方)的套路镜像到饮食/睡眠:
  - `nutrition_prescription(db,user_id)` / `sleep_prescription(db,user_id)`:薄 DB 层,build_twin
    + 复用 fuel_strategist 的矩阵函数(蛋白目标/基因 nudge)+ gene_config 咖啡因代谢。fail-soft → None。
  - `meal_items` / `sleep_items`:纯函数,把 ctx + rx → Item[],带 prescription(各端按形态渲染)。
  - `align_post_workout_meal`:纯函数,把离训练最近的餐对齐到「训练结束后 ≤60min」(蛋白/碳水窗),
    就地改 ctx.meals —— **必须在 meds/补剂锚定餐之前调用**(否则餐锚定到旧时点)。

红线(R4 / medical_boundary):饮食项只带 kcal/蛋白「目标」与基因「提示」,绝不出具体医疗剂量,
不下因果裁决;睡眠项只给作息卫生与咖啡因截止,均为对冲措辞。路径无 LLM。fail-soft 全程。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.services.timing_solver import (
    ANCHOR_BEDTIME,
    ANCHOR_WITH_MEAL,
    DayContext,
    Item,
    _to_hhmm,
    _to_min,
)

logger = logging.getLogger(__name__)

# 餐 severity:低于药/补剂的锚点项,高于纯浮动 nudge;三餐都是必达生活锚点(deferrable=False)。
_MEAL_SEVERITY = 45
_MEAL_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}

# 睡眠卫生 severity:wind-down 略高(直接影响入睡),咖啡因截止稍低(预防性)。
_WINDDOWN_SEVERITY = 40
_CAFFEINE_SEVERITY = 35

# CYP1A2 咖啡因半衰期 → 睡前停咖啡的提前量(小时)。慢代谢清除慢 → 提前更久。
_CAFFEINE_CUTOFF_HOURS = {"slow": 9, "normal": 6, "fast": 6}
_DEFAULT_CAFFEINE_CUTOFF_HOURS = 8  # 未知基因型:保守 8h(介于 normal 与 slow)


# ─────────────────────── D1 营养处方(薄 DB 层)────────────────────────
def nutrition_prescription(db, user_id: int) -> Optional[dict]:
    """营养目标(蛋白/kcal/基因)→ 结构化 dict,供 meal_items 用。

    fail-soft:取数/build_twin 任一失败 → None(回退无处方的纯餐项),失败记 warning(不静默吞)。
    复用 fuel_strategist 的 `_protein_target_g` / `_gene_nudges`,不重实现。twin use_cache=True
    (与 workout_prescription / agenda 同源,5min 缓存)。

    返回(全部 optional,缺则不带该键):
      kcal_target / protein_g / protein_per_meal_g / gene_note / carb_timing
    """
    try:
        from app.twin.builder import build_twin
        from app.agents.fuel_strategist.strategist import _gene_nudges, _protein_target_g

        twin = build_twin(db, user_id, use_cache=True)
        body = getattr(twin, "body_composition", None)
        behavioral = getattr(twin, "behavioral", None)
        weight_kg = getattr(body, "weight_kg", None) if body else None
        load_7d = getattr(behavioral, "training_load_7d", None) if behavioral else None
        tdee = getattr(body, "tdee_kcal", None) if body else None

        rx: dict = {}
        if tdee:
            rx["kcal_target"] = round(float(tdee))
        protein_g = _protein_target_g(weight_kg, load_7d)
        if protein_g:
            rx["protein_g"] = round(protein_g)
            rx["protein_per_meal_g"] = round(protein_g / 3)
        nudges = _gene_nudges(twin) or []
        # 基因提示压成一行(取与饮食最相关的前两条),非剂量、非裁决。
        gene_tips = [n.get("tip") for n in nudges if isinstance(n, dict) and n.get("tip")]
        if gene_tips:
            rx["gene_note"] = " ".join(gene_tips[:2])
        # 围训练碳水提示(对冲措辞,不带克数处方)。
        rx["carb_timing"] = "训练前后那一餐适当增加优质碳水,帮助供能与恢复(非硬性指标)"
        return rx or None
    except Exception:
        logger.warning("nutrition_prescription failed for user %s", user_id, exc_info=True)
        return None


# ─────────────────────── D2 睡眠处方(薄 DB 层)────────────────────────
def sleep_prescription(db, user_id: int) -> Optional[dict]:
    """睡眠卫生处方(咖啡因截止提前量 by CYP1A2 + 收尾建议)→ dict,供 sleep_items 用。

    fail-soft:失败 → None(回退默认 8h 截止 + 通用收尾,见 sleep_items 兜底),记 warning。
    咖啡因代谢从 twin.gene_config.caffeine_metabolism 读(fast|normal|slow),复用 gene_config
    既有解析(不重实现 CYP1A2 判定)。

    返回:caffeine_cutoff_hours(必带)/ gene_note(慢代谢时带)。
    """
    try:
        from app.twin.builder import build_twin

        twin = build_twin(db, user_id, use_cache=True)
        gc = getattr(twin, "gene_config", None)
        metab = getattr(gc, "caffeine_metabolism", None) if gc else None
        hours = _CAFFEINE_CUTOFF_HOURS.get(metab or "", _DEFAULT_CAFFEINE_CUTOFF_HOURS)
        rx: dict = {"caffeine_cutoff_hours": hours}
        if metab == "slow":
            rx["gene_note"] = (
                "CYP1A2 咖啡因慢代谢倾向:咖啡因清除较慢,建议把咖啡/茶截止时间提前,"
                "以睡眠反馈为准(非硬性限制)。"
            )
        return rx
    except Exception:
        logger.warning("sleep_prescription failed for user %s", user_id, exc_info=True)
        return None


# ─────────────────────── 围训练餐对齐(纯函数)────────────────────────
def align_post_workout_meal(ctx: DayContext, *, workout_minutes: int = 40) -> None:
    """把离训练最近的「训练后」餐对齐到训练结束后 ≤60min(蛋白/碳水恢复窗)。就地改 ctx.meals。

    **务必在 meds/补剂锚定餐之前调用**(餐锚定项会按 ctx.meals 落桩)。
    - 无 ctx.workout_start → 不动(no-op)。
    - 选「训练结束后最近的一餐」(若训练结束在最后一餐之后,则取晚餐,避免把次日早餐拉过来)。
    - 仅当原餐时点早于「结束+0」或晚于「结束+60」时才移动到「结束+30」(取窗中点);
      已落在 [end, end+60] 内 → 不动(不破坏用户既有合理时点)。
    """
    if not ctx.workout_start:
        return
    end = _to_min(ctx.workout_start) + workout_minutes
    target = end + 30  # 窗中点(end..end+60)
    # 找训练结束后最近的餐;都在结束前 → 取晚餐(当日最后一餐承接恢复)。
    meals_min = {k: _to_min(v) for k, v in ctx.meals.items()}
    after = {k: m for k, m in meals_min.items() if m >= end}
    if after:
        nearest = min(after, key=lambda k: after[k] - end)
    else:
        nearest = max(meals_min, key=lambda k: meals_min[k])  # 最晚那餐
    cur = meals_min[nearest]
    if cur < end or cur > end + 60:
        ctx.meals = {**ctx.meals, nearest: _to_hhmm(target)}


# ─────────────────────── 餐项 / 睡眠项(纯函数)────────────────────────
def meal_items(ctx: DayContext, nutrition_rx: Optional[dict] = None) -> List[Item]:
    """三餐 diet Item(固定在 ctx.meals 时点,必达,带 nutrition 处方)。

    处方挂在每个餐项上(各端渲染 kcal/蛋白目标 chip);R4:只目标不剂量,carb_timing 仅给围训练餐。
    """
    items: List[Item] = []
    for ref in ("breakfast", "lunch", "dinner"):
        t = ctx.meals.get(ref)
        if not t:
            continue
        label = _MEAL_LABELS[ref]
        rx = dict(nutrition_rx) if nutrition_rx else None
        # carb_timing 只对围训练那一餐有意义 → 非围训练餐去掉,避免每餐都喊碳水。
        if rx and ctx.workout_start is not None:
            end = _to_min(ctx.workout_start) + 40
            if not (end <= _to_min(t) <= end + 90):
                rx.pop("carb_timing", None)
        elif rx:
            rx.pop("carb_timing", None)
        items.append(Item(
            id=f"meal:{ref}",
            domain="diet",
            title=label,
            fixed_time=t,
            anchor=ANCHOR_WITH_MEAL,
            anchor_ref=ref,
            deferrable=False,
            severity=_MEAL_SEVERITY,
            prescription=rx or None,
        ))
    return items


def sleep_items(ctx: DayContext, sleep_rx: Optional[dict] = None) -> List[Item]:
    """睡眠卫生项:wind-down(睡前 45min 收尾)+ caffeine cutoff(睡前 N 小时,N by CYP1A2)。

    fail-soft 兜底:sleep_rx=None → 默认 8h 咖啡因截止 + 通用收尾(不漏排睡眠卫生)。
    deferrable:wind-down 必达(锚定睡前,不顺延);caffeine cutoff 可顺延(预防性,落静默窗则提示往前)。
    """
    items: List[Item] = []
    rx = sleep_rx or {}
    # wind-down:睡前 45min,锚 BEDTIME(solver 会落到 sleep-45)。
    items.append(Item(
        id="sleep:winddown",
        domain="sleep",
        title="睡前收尾:调暗灯光 / 收屏 / 放松",
        anchor=ANCHOR_BEDTIME,
        deferrable=False,
        severity=_WINDDOWN_SEVERITY,
        prescription={
            "kind": "winddown",
            "guidance": "睡前 45 分钟调暗灯光、放下屏幕、做放松,帮助更快入睡(作息卫生,非医疗处方)。",
        },
    ))
    # caffeine cutoff:睡前 N 小时(N by CYP1A2,fail-soft 默认 8h)。固定时点,可顺延。
    hours = rx.get("caffeine_cutoff_hours", _DEFAULT_CAFFEINE_CUTOFF_HOURS)
    cutoff_min = _to_min(ctx.sleep) - hours * 60
    cutoff_rx = {"kind": "caffeine_cutoff", "cutoff_hours": hours,
                 "guidance": f"睡前约 {hours} 小时起不再摄入咖啡因(咖啡/茶/功能饮料),减少对入睡的干扰。"}
    if rx.get("gene_note"):
        cutoff_rx["gene_note"] = rx["gene_note"]
    items.append(Item(
        id="sleep:caffeine_cutoff",
        domain="sleep",
        title=f"咖啡因截止(睡前 {hours}h)",
        fixed_time=_to_hhmm(cutoff_min),
        deferrable=True,
        severity=_CAFFEINE_SEVERITY,
        prescription=cutoff_rx,
    ))
    return items
