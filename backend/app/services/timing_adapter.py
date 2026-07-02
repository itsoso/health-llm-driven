"""medication/supplement(均存于 medications 表,category 区分)→ timing_solver.Item 归一化 adapter。

把用户在服的药/补剂(Medication 行)映射成 timing_solver 的 Item:
- timing_relation/meal_anchor → 锚点 + 餐次(词表与 models.medication._TIMING_LABELS 对齐)
- reminder_times → 固定时点(处方时点优先于锚点启发式)
- 按名称关键字补螯合/间隔约束(operationalize methodology §5:钙×铁≥2h、左甲状腺素×钙铁≥4h…)
- 处方药 deferrable=False(医嘱必达)、补剂 deferrable=True(timing 是优化)

纯函数:接收 model 对象(duck-typed via getattr),不查 DB。DB 查询 + 安全(DDI/DSI 的
hard_forbidden 判定)在上层 service(下一刀),保持本层可单测、零 DB、与 Twin 解耦。
"""
from typing import Dict, List, Optional

from app.services.timing_solver import (
    ANCHOR_AFTER_MEAL,
    ANCHOR_ANYTIME,
    ANCHOR_BEDTIME,
    ANCHOR_BEFORE_MEAL_30,
    ANCHOR_EMPTY_STOMACH,
    ANCHOR_WITH_MEAL,
    Item,
)

# timing_relation(models.medication._TIMING_LABELS 的键)→ solver 锚点
_RELATION_TO_ANCHOR = {
    "empty_stomach": ANCHOR_EMPTY_STOMACH,
    "before_meal_30": ANCHOR_BEFORE_MEAL_30,
    "before_meal": ANCHOR_BEFORE_MEAL_30,   # 「饭前」按饭前30min 处理
    "with_meal": ANCHOR_WITH_MEAL,
    "after_meal": ANCHOR_AFTER_MEAL,
    "bedtime": ANCHOR_BEDTIME,
    "anytime": ANCHOR_ANYTIME,
}

# category 判定为「补剂」的取值(其余视为药物)
_SUPPLEMENT_CATEGORIES = {"supplement", "补剂", "保健品", "膳食补充剂"}

# 螯合/间隔对:(名称关键字组 A, 名称关键字组 B, 最小间隔小时)。methodology §5。
_INTERVAL_PAIRS = [
    (("钙", "calcium"), ("铁", "iron"), 2.0),
    (("钙", "calcium"), ("锌", "zinc"), 2.0),
    (("左甲状腺素", "优甲乐", "levothyroxine"), ("钙", "calcium", "铁", "iron"), 4.0),
    (("益生菌", "probiotic"), ("抗生素", "antibiotic", "阿莫西林", "克拉霉素"), 2.0),
]


def _domain(med) -> str:
    raw = (getattr(med, "category", None) or "").strip()
    if raw.lower() in {"supplement"} or raw in _SUPPLEMENT_CATEGORIES:
        return "supplement"
    return "medication"


def medication_to_item(med, *, forbidden_reason: Optional[str] = None) -> Item:
    """单条 Medication → Item(纯映射)。forbidden_reason 非空 → 标硬禁忌(由上层安全层算出)。"""
    domain = _domain(med)
    relation = getattr(med, "timing_relation", None) or "anytime"
    anchor = _RELATION_TO_ANCHOR.get(relation, ANCHOR_ANYTIME)
    times = getattr(med, "reminder_times", None)
    fixed = times[0] if isinstance(times, list) and times else None
    return Item(
        id=f"med:{getattr(med, 'id', '?')}",
        domain=domain,
        title=getattr(med, "name", "") or "",
        anchor=anchor,
        anchor_ref=getattr(med, "meal_anchor", None) or None,
        severity=50 if domain == "supplement" else 70,
        deferrable=(domain == "supplement"),   # 处方药必达;补剂可顺延
        fixed_time=fixed,
        hard_forbidden=bool(forbidden_reason),
        forbidden_reason=forbidden_reason,
    )


def _matches(name: str, keywords) -> bool:
    low = (name or "").lower()
    return any(k.lower() in low for k in keywords)


def medications_to_items(meds, *, forbidden_reasons: Optional[Dict] = None) -> List[Item]:
    """一组 Medication → Items,并按名称关键字补螯合间隔约束。

    forbidden_reasons: {medication_id: reason} —— 由上层安全层(DDI/DSI)算出的硬禁忌。
    """
    forbidden_reasons = forbidden_reasons or {}
    meds = list(meds)
    items = [
        medication_to_item(m, forbidden_reason=forbidden_reasons.get(getattr(m, "id", None)))
        for m in meds
    ]
    # (item, 原始名)索引,用于关键字匹配
    idx = {it.id: (it, getattr(m, "name", "") or "") for it, m in zip(items, meds)}

    for kw_a, kw_b, gap in _INTERVAL_PAIRS:
        a_ids = [iid for iid, (_, nm) in idx.items() if _matches(nm, kw_a)]
        b_ids = [iid for iid, (_, nm) in idx.items() if _matches(nm, kw_b)]
        for aid in a_ids:
            it = idx[aid][0]
            for bid in b_ids:
                if aid == bid:
                    continue
                if (bid, gap) not in it.interval_constraints:
                    it.interval_constraints.append((bid, gap))
    return items
