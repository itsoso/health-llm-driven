"""R16 P5 —— L1↔L4 对账(因果账本外环):日粒度快信号 vs 化验慢真值校准。

L1 = 日粒度快信号(穿戴/家用设备,可能有噪声/偏差);L4 = 化验慢真值(ground truth,季度复测)。
对账判某指标的 L1 趋势是否与 L4 化验变化**同向**:
- **concordant**(两边都超各自噪声地板、同向):日粒度代理对该用户**校准良好**,可信(corroborate,封顶 moderate)。
- **discordant**(反向,或一边动一边没动):日粒度代理与化验真值**矛盾** → 别信日粒度(demote,降 low)。
  这正是外环价值——用季度真值校准/否决日常快信号,防「日粒度看着在改善、化验其实没动」的自欺。
- **insufficient**:L4 化验对缺失 或 L1 太稀疏 或 两边都没动。

治理护栏(R16 全程,与 P1-P4 一致):
- **门控指标(处方/激素,单源 `is_clinician_gated_metric`)→ clinician_review**:化验受并行处方药混杂,
  不对其下校准裁决(即便日粒度与化验同向,也可能是药在驱动)。
- **只降不升**:discordant 降 low;concordant 至多 corroborate 到 moderate(封顶,非因果证明)。
- **相关非因果**;**基因无关**(只按 metric_code/delta/direction)。
- 复用 P2 `intervention_denoise.window_mean` 平滑 L1 端点;噪声地板复用 `intervention_priors` 的 mcid/obs_noise。
  P3 洗脱窗排除交叉污染的区间由调用方负责(传干净的 L1 区间)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

ATTRIBUTION = "temporal_association_not_causation"


def _min_effect(metric_code: str, cycle_type: str = "metabolic_90d") -> float:
    """该指标可信变化下限 = max(mcid, √2·obs_noise)。复用 intervention_priors(单源,别复制阈值)。"""
    from app.services.personal_models.intervention_priors import get_prior

    p = get_prior(cycle_type, metric_code)
    return max(p.mcid, (2 ** 0.5) * p.obs_noise)


def classify_movement(
    delta: Optional[float], metric_code: str, direction: str = "down",
) -> Tuple[bool, Optional[bool]]:
    """(moved 是否超噪声地板, improved 是否朝好方向)。delta None / 未动 → (False, None)。"""
    if delta is None:
        return False, None
    if abs(delta) < _min_effect(metric_code):
        return False, None
    lower_better = direction != "up"
    improved = (delta < 0) if lower_better else (delta > 0)
    return True, improved


def _to_dt(t):
    """date → 当天 00:00 UTC datetime;datetime 原样(P2 window_mean 需要带 tzinfo 的 datetime)。"""
    from datetime import date, datetime, time, timezone

    if isinstance(t, datetime):
        return t
    if isinstance(t, date):
        return datetime.combine(t, time.min, tzinfo=timezone.utc)
    return t


def _l1_delta(l1_series: List[Tuple[Any, Optional[float]]]) -> Optional[float]:
    """L1 日粒度系列的去噪 delta(起→末)。太稀疏 → None。

    **走 P2 `denoise_endpoints`(不是裸 window_mean)**:它带短跨度守卫——两锚点间隔 < 2×平滑窗时
    首尾 ±7d 窗会重叠、把真改善压成 0(=P2 当年的 BLOCKING),denoise_endpoints 此时退回**原始端点**。
    裸 window_mean 没这道守卫,会让 <14 天的真改善被误判「没动」→ 把化验确认过的真信号误降为 discordant。
    """
    from app.services import intervention_denoise as dn

    pts = [(_to_dt(t), float(v)) for (t, v) in l1_series if t is not None and v is not None]
    if len(pts) < 2 * dn.MIN_POINTS:
        return None
    pts.sort(key=lambda x: x[0])
    start_anchor, start_raw = pts[0]
    end_anchor, end_raw = pts[-1]
    d = dn.denoise_endpoints(pts, start_anchor, start_raw, end_anchor, end_raw)
    base, latest = d.get("baseline"), d.get("latest")
    if base is None or latest is None:
        return None
    return latest - base


def reconcile_verdict(
    l1_delta: Optional[float],
    l4_delta: Optional[float],
    l4_metric_code: str,
    direction: str = "down",
    l1_metric_code: Optional[str] = None,
) -> Dict[str, Any]:
    """L1 趋势 delta vs L4 化验 delta 的同向对账裁决。

    l1_metric_code 缺省 = l4_metric_code(同指标日粒度 vs 化验,如家用 BP vs 诊室 BP);相关指标
    (如日粒度 glucose vs HbA1c)由调用方传不同 code,各按自身噪声地板判「动没动」。
    """
    from app.services.personal_models.intervention_priors import is_clinician_gated_metric

    l1_code = l1_metric_code or l4_metric_code
    base = {"l1_delta": l1_delta, "l4_delta": l4_delta, "attribution": ATTRIBUTION}

    # 门控:化验受处方混杂 → 不下校准裁决
    if is_clinician_gated_metric(l4_metric_code) or is_clinician_gated_metric(l1_code):
        return {**base, "verdict": "clinician_review", "confidence": "clinician_review", "requires_clinician": True}

    l4_moved, l4_improved = classify_movement(l4_delta, l4_metric_code, direction)
    l1_moved, l1_improved = classify_movement(l1_delta, l1_code, direction)

    if not l4_moved and not l1_moved:
        # 两边都没超噪声 → 无可对账(也不臆造"稳定即一致")
        return {**base, "verdict": "insufficient", "confidence": "low", "requires_clinician": False}

    if l4_moved and l1_moved:
        if l1_improved == l4_improved:
            verdict, conf = "concordant", "moderate"   # 日粒度代理与化验真值同向 → 校准良好(封顶 moderate)
        else:
            verdict, conf = "discordant", "low"        # 反向 → 别信日粒度
    else:
        # 一边动、一边没动 = 快信号未被真值确认 → demote(外环否决)
        verdict, conf = "discordant", "low"
    return {**base, "verdict": verdict, "confidence": conf, "requires_clinician": False}


def reconcile_user_metric(
    db, user_id: int, l4_metric_code: str,
    l1_series: List[Tuple[Any, Optional[float]]],
    direction: str = "down",
    l1_metric_code: Optional[str] = None,
) -> Dict[str, Any]:
    """服务:从 biomarker observations 取该指标最近两次**化验**(L4 真值对),与传入的 L1 日粒度系列对账。

    L4 = `observation_series` 里该 code 最后两条(化验慢真值);L1 由调用方按指标从日粒度源(穿戴/家用
    设备/personal_baseline)取传入。化验不足两条 → l4_delta=None → insufficient/clinician_review 视门控。
    """
    from app.services.biomarker_service import observation_series

    obs = observation_series(db, user_id, l4_metric_code)
    l4_delta = None
    if obs and len(obs) >= 2:
        l4_delta = obs[-1].normalized_value - obs[-2].normalized_value
    l1_delta = _l1_delta(l1_series)
    return reconcile_verdict(l1_delta, l4_delta, l4_metric_code, direction, l1_metric_code)
