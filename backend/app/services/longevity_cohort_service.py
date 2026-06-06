# -*- coding: utf-8 -*-
"""抗衰群体证据聚合(N-of-1 → N-of-many,Phase3 P3-3)。

把所有用户已评分的生物年龄 N-of-1 卡聚合成**去标识**群体证据:
「哪个生物年龄指标、改善率多少、平均年轻几岁」。
- 既是产品决策依据(什么干预对什么人有效),也是退出叙事的数据资产。
- **强制去标识**:输出只含计数/均值,绝不含 user_id;样本量 < MIN_COHORT 的格子
  整体抑制(不出具体数),避免小样本再识别。

注:ActionCard 不携带干净的「干预类型」字段,故按 metric_key 聚合,不强分干预域
(诚实——不编造没有的维度)。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.action_card import ActionCard

# 生物年龄类指标(越低越好的 phenotypic/fitness;越高越好的 vo2max)
BIOAGE_METRICS = ("phenotypic_age", "biological_age", "vo2max", "fitness_age")
# 越低越好的指标(算"年轻了几岁" = baseline - actual)
_LOWER_BETTER = {"phenotypic_age", "biological_age", "fitness_age"}
# 去标识阈值:某 metric 已评分样本 < 此值 → 抑制具体数字
MIN_COHORT = 5


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def cohort_biological_age_outcomes(db: Session) -> dict[str, Any]:
    """跨用户聚合已评分的生物年龄 N-of-1 outcome(去标识)。

    返回 per-metric:n / improved / worsened / unchanged / improvement_rate
    / mean_improvement_years(仅"越低越好"指标的 improved 卡,baseline-actual 均值)。
    小样本(< MIN_COHORT)→ suppressed=True,不出具体数。
    """
    rows = (
        db.query(ActionCard)
        .filter(
            ActionCard.metric_key.in_(BIOAGE_METRICS),
            ActionCard.outcome.isnot(None),  # 已评分
        )
        .all()
    )

    by_metric: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = (r.metric_key or "").lower()
        if m not in BIOAGE_METRICS:
            continue
        b = by_metric.setdefault(m, {"n": 0, "improved": 0, "worsened": 0,
                                     "unchanged": 0, "_impr_years": []})
        b["n"] += 1
        oc = (r.outcome or "").lower()
        if oc in ("improved", "worsened", "unchanged"):
            b[oc] += 1
        # 仅"越低越好"指标算"年轻了几岁"
        if oc == "improved" and m in _LOWER_BETTER:
            base, act = _num(r.baseline_value), _num(r.actual_value)
            if base is not None and act is not None and base > act:
                b["_impr_years"].append(round(base - act, 1))

    metrics_out: dict[str, Any] = {}
    for m, b in by_metric.items():
        n = b["n"]
        if n < MIN_COHORT:
            metrics_out[m] = {"n": n, "suppressed": True,
                              "note": f"样本 < {MIN_COHORT},去标识抑制"}
            continue
        impr_years = b.pop("_impr_years")
        metrics_out[m] = {
            "n": n,
            "improved": b["improved"],
            "worsened": b["worsened"],
            "unchanged": b["unchanged"],
            "improvement_rate": round(b["improved"] / n, 3) if n else None,
            "mean_improvement_years": (
                round(sum(impr_years) / len(impr_years), 1) if impr_years else None
            ),
        }

    return {
        "metrics": metrics_out,
        "min_cohort": MIN_COHORT,
        "evidence_tier": "observational",  # 群体观察,非 RCT;不夸大成疗效
        "claim_boundary": (
            "群体观察性聚合,非随机对照试验;反映已执行 N-of-1 的真实分布,"
            "不构成疗效证明,不替代医学结论。"
        ),
    }
