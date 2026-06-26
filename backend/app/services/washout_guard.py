"""R16 P3 —— 跨周期洗脱期 / 残留效应守卫(归因诚实)。

N-of-1 经典混杂:用户停掉干预 A、不久开干预 B,A 的残留效应仍在 → 把 B 周期内某指标的变化
归因于「B 这次干预」是不诚实的(carryover)。本守卫检测「本周期基线测于前序(跟踪同一指标的)
干预刚结束的洗脱期内」,标 `attribution_state='washout_pending'`,让读数**不把变化自信归因于
当前干预**(只降置信度,不改测得的方向)。

安全不变量(严格 demote-only,镜像 cross-source caveat / P1):
- 只能把归因从 attributable **降**到 washout_pending,绝不反向「升级」成更强因果裁决。
- **无前序周期**(单周期=绝大多数现状)→ attributable,行为与改前**逐字节一致**(纯附加叠加)。
- **fail-closed**:任何异常 → washout_pending(宁可少归因,绝不在出错时默认 attributable)。
- **保守**:未知 cycle_type 用默认洗脱天数(偏长更安全);只按 (user, metric_code, 时间) 判,
  **零 genotype 参数**(基因无关)。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 默认洗脱天数(保守:多数药物/行为干预残留约 2–3 周;demote-only 偏长更安全)。
WASHOUT_DAYS_DEFAULT = 21
# 可按 cycle_type 细化(未列用默认);留扩展点,先不过度配置。
_WASHOUT_DAYS_BY_TYPE: dict[str, int] = {}

ATTRIBUTABLE = "attributable"
WASHOUT_PENDING = "washout_pending"


def _washout_days(cycle_type: Optional[str]) -> int:
    return _WASHOUT_DAYS_BY_TYPE.get(cycle_type or "", WASHOUT_DAYS_DEFAULT)


def _as_date(d) -> Optional[date]:
    if d is None:
        return None
    return d.date() if hasattr(d, "date") else d


def attribution_for_metric(
    db: Session, user_id: int, cycle, metric_code: str, baseline_at,
) -> Tuple[str, Optional[date]]:
    """返回 (attribution_state, washout_until)。

    washout_pending:存在另一个(非本周期、同用户、**跟踪过同一 metric_code**)前序周期,其
    planned_end_date 落在本周期基线日**之前且 ≤ 洗脱天数** → 残留未清。否则 attributable。
    无基线时间 → attributable(无从判,且无基线时本就 pending,不强加)。异常 → fail-closed washout_pending。
    """
    baseline_d = _as_date(baseline_at)
    if baseline_d is None:
        return ATTRIBUTABLE, None
    try:
        from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

        wd = _washout_days(getattr(cycle, "cycle_type", None))
        # 故意**不**按 status 过滤:任何前序(completed/abandoned/active)只要其 planned_end_date 落在
        # 本基线之前且 ≤ 洗脱天数,就视作可能残留污染(end_d<=baseline_d 已天然排除「未结束/未来结束」)。
        # 只降不升,过标也安全。
        priors = (
            db.query(InterventionCycle.planned_end_date)
            .join(OutcomeMetric, OutcomeMetric.cycle_id == InterventionCycle.id)
            .filter(
                InterventionCycle.user_id == user_id,
                InterventionCycle.id != cycle.id,
                OutcomeMetric.metric_code == metric_code,
                InterventionCycle.planned_end_date.isnot(None),
            )
            .all()
        )
        for (end_d,) in priors:
            end_d = _as_date(end_d)
            if end_d is None:
                continue
            # 前序结束在本基线之前、间隔 ≤ 洗脱天数 → 残留期内
            if end_d <= baseline_d and (baseline_d - end_d).days <= wd:
                return WASHOUT_PENDING, end_d + timedelta(days=wd)
        return ATTRIBUTABLE, None
    except Exception as e:  # noqa: BLE001 — 归因判定出错必须 fail-closed,不默认 attributable
        logger.warning(
            "[washout] 归因判定失败,fail-closed washout_pending: metric=%s err=%s", metric_code, e
        )
        return WASHOUT_PENDING, None
