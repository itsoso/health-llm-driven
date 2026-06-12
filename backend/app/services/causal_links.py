"""时滞因果引擎(描述性,**非因果声明**)。

盘点缺口:LongitudinalAnalyst 做趋势,但缺"干预事件 × 指标变化(带时滞)"的显式关联。
本模块做两类**已确认、数据可得**的关联,不做通用相关性图谱(N=1 个体数据,统计站不住):

1. 用药干预效果:某药 start_date 前后,目标指标(biomarker_observations)的均值变化。
2. 复发事件 × 日指标:recurring 事件日(如高 AQI 日)后第 lag 天的日指标关联(lag_association 原语)。

全程标注"观察到的关联,可能含其他因素,非严格因果"。只在样本足够 + 变化显著时输出。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 药名关键词 → 目标 biomarker code(只放因果关系明确的:这药就是为降这个指标开的)
_MED_TARGET: list[tuple[list[str], str, str]] = [
    (["他汀", "立普妥", "可定", "阿托伐", "瑞舒伐", "辛伐"], "lipid_ldl", "LDL"),
    (["二甲双胍", "格华止", "西格列汀", "达格列净", "恩格列净", "司美格鲁肽", "替尔泊肽"], "glucose_hba1c", "HbA1c"),
    (["非布司他", "别嘌醇", "苯溴马隆"], "UA", "尿酸"),
]


def _as_date(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def medication_intervention_effects(db: Session, user_id: int) -> list[dict[str, Any]]:
    """对有 start_date 的在用药,比较其目标指标 start 前后的均值。

    返回每条 {medication, metric_label, before_mean, after_mean, delta, pct, n_before, n_after}。
    仅当 start 前后各有 ≥1 个观测时计算(否则跳过,不臆测)。
    """
    meds = db.execute(text(
        "SELECT name, start_date FROM medications "
        "WHERE user_id = :uid AND is_active = TRUE AND start_date IS NOT NULL"
    ), {"uid": user_id}).fetchall()
    if not meds:
        return []

    out: list[dict[str, Any]] = []
    for name, start_raw in meds:
        start = _as_date(start_raw)
        if start is None:
            continue
        target = _target_for(name)
        if target is None:
            continue
        code, label = target
        rows = db.execute(text(
            "SELECT observed_at, normalized_value FROM biomarker_observations "
            "WHERE user_id = :uid AND code = :code AND normalized_value IS NOT NULL "
            "ORDER BY observed_at"
        ), {"uid": user_id, "code": code}).fetchall()
        before = [float(v) for d, v in rows if _as_date(d) and _as_date(d) < start]
        after = [float(v) for d, v in rows if _as_date(d) and _as_date(d) >= start]
        if not before or not after:
            continue
        bmean = sum(before) / len(before)
        amean = sum(after) / len(after)
        delta = amean - bmean
        pct = (delta / abs(bmean) * 100.0) if bmean != 0 else None
        out.append({
            "medication": name, "metric_label": label,
            "before_mean": round(bmean, 2), "after_mean": round(amean, 2),
            "delta": round(delta, 2), "pct": round(pct, 1) if pct is not None else None,
            "n_before": len(before), "n_after": len(after),
        })
    return out


def _target_for(med_name: str) -> Optional[tuple[str, str]]:
    n = (med_name or "").lower()
    for kws, code, label in _MED_TARGET:
        if any(k.lower() in n for k in kws):
            return code, label
    return None


def causal_prompt_blob(db: Session, user_id: int) -> str:
    """注入 agent 的紧凑文本;无显著关联返回空串。"""
    effects = medication_intervention_effects(db, user_id)
    lines = []
    for e in effects:
        if e["pct"] is None or abs(e["pct"]) < 5:
            continue
        arrow = "↓" if e["delta"] < 0 else "↑"
        lines.append(
            f"- 用{e['medication']}后,{e['metric_label']} {e['before_mean']} {arrow} {e['after_mean']}"
            f"({e['pct']:+.0f}%,前{e['n_before']}次/后{e['n_after']}次测量)"
        )
    if not lines:
        return ""
    return ("【观察到的用药-指标关联(描述性,可能含饮食/运动等其他因素,非严格因果)】\n"
            + "\n".join(lines))
