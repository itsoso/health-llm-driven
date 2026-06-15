"""N-of-1 干预效应估计器 (Phase 1, 层级贝叶斯 · 人群先验 + 个人收缩).

设计文档: docs/design-personal-predictive-model.md §3-4 Phase 1.

核心范式 (borrowing strength / James-Stein shrinkage):
  单人干预周期少 → 先用**人群先验**, 再按**个人观测**收缩到个人后验。
  N=0 → 返回先验 (宽 CI, "默认不确定, 未验证");
  N 增大 → 后验收缩到个人均值, CI 收窄。

方法 (闭式共轭 Normal-Normal, **纯 stdlib, 无 PyMC/Stan/numpy 重依赖**):
  - 观测: 个人在该 (metric_code[, cycle_type]) 上每个周期的 OutcomeMetric.delta
    (= latest - baseline)。delta 即"这个干预对该指标的真实改变量"的一次观测。
  - 人群先验  μ₀, τ²: 所有用户同 (metric_code, cycle_type) 的 delta 聚合 (均值/方差)。
    样本不足 (< POP_PRIOR_MIN_OBS) → 退化到保守默认先验 (μ₀=0 "无效应" + 大 τ²)。
  - 个人似然: dᵢ ~ Normal(θ_user, σ²)。σ² = 个人观测方差 (n>=2),
    n<2 时用人群 σ² 兜底, 再兜底 DEFAULT_OBS_VAR。
  - 共轭后验 (精度加权):
        posterior_mean = (μ₀/τ² + n·d̄/σ²) / (1/τ² + n/σ²)
        posterior_var  = 1 / (1/τ² + n/σ²)

方向语义 (对齐 OutcomeMetric.direction):
  - direction="down" (降为好): effect<0 且 CI 整段 < 0 → is_effective。
  - direction="up"   (升为好): effect>0 且 CI 整段 > 0 → is_effective。

隐私 (AGENTS.md §5): 只产**结构化效应 + 区间**, 不外泄原始 baseline/latest 值;
喂 LLM 的 prompt blob 只含 effect/CI/方向/人话结论。

降级: 任何 DB / 数学异常都不抛崩调用方 ——
  - estimate_effect: DB 失败回退到"纯先验" (N=0), 永不 raise。
  - effect_estimate_prompt_blob: 失败静默返回空串 (prompt 注入是旁路)。
"""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 可配参数 ──────────────────────────────────────────────────────────────
POP_PRIOR_MIN_OBS = 3          # 人群观测 < 此 → 退化到默认先验 (无效应 + 大不确定)
DEFAULT_PRIOR_MEAN = 0.0       # 默认先验: 假设无效应
DEFAULT_PRIOR_VAR = 4.0        # 默认先验方差 (大 → 宽 CI, 让个人数据主导)
DEFAULT_OBS_VAR = 1.0          # 个人/人群方差都拿不到时的兜底似然方差
MIN_VAR = 1e-6                 # 方差下限 (防退化序列除零 / 假性确定)
MIN_POP_PRIOR_VAR = 0.25       # 人群先验方差下限 (防同值人群 → 过度自信先验压死个人数据)
CI_Z = 1.2816                  # 80% 双侧可信区间正态分位 (z_{0.90})
CI_LEVEL = 0.80
# 置信度分级: 既看 n 也看 CI 宽度 (宽 → 不确定)。
CONF_HIGH_MIN_N = 3
CONF_HIGH_MAX_WIDTH = 1.0      # CI 宽度 <= 此且 n>=3 → high
CONF_MED_MAX_WIDTH = 2.5       # CI 宽度 <= 此且 n>=1 → medium


@dataclass
class EffectEstimate:
    """单 (metric_code, cycle_type) 的个人化干预效应后验。"""

    metric_code: str
    cycle_type: Optional[str]
    direction: str                 # down(降为好) / up(升为好)
    effect: float                  # 后验均值
    ci_low: float
    ci_high: float
    ci_level: float
    n_observations: int            # 个人 delta 观测数
    n_cycles: int                  # 贡献观测的周期数 (= n_observations, 一周期一 delta)
    prior_mean: float
    prior_var: float
    population_n: int              # 贡献人群先验的观测数 (0 = 用了默认先验)
    confidence: str                # low / medium / high
    is_effective: bool             # CI 在 desirable 方向上排除 0
    unit: Optional[str] = None
    interpretation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("effect", "ci_low", "ci_high", "prior_mean", "prior_var"):
            d[k] = round(d[k], 3)
        return d


# ── 纯数学核心 (无 DB, 单测直接喂序列) ─────────────────────────────────────

def _mean_var(values: Sequence[float]) -> tuple[float, float]:
    """样本均值 + 样本方差 (n<2 → var=0)。"""
    if not values:
        return 0.0, 0.0
    mean = statistics.fmean(values)
    var = statistics.variance(values) if len(values) >= 2 else 0.0
    return mean, var


def _confidence(n: int, ci_width: float) -> str:
    if n >= CONF_HIGH_MIN_N and ci_width <= CONF_HIGH_MAX_WIDTH:
        return "high"
    if n >= 1 and ci_width <= CONF_MED_MAX_WIDTH:
        return "medium"
    return "low"


def conjugate_posterior(
    personal_deltas: Sequence[float],
    *,
    prior_mean: float,
    prior_var: float,
    obs_var: Optional[float] = None,
    population_var: Optional[float] = None,
) -> tuple[float, float, float]:
    """Normal-Normal 共轭后验 → (posterior_mean, posterior_var, obs_var_used)。

    纯函数: 不碰 DB。
    - N=0 → 直接返回先验 (mean=prior_mean, var=prior_var)。
    - σ² (obs_var): 显式 > 个人方差(n>=2) > 人群方差 > DEFAULT_OBS_VAR。
    """
    prior_var = max(prior_var, MIN_VAR)
    n = len(personal_deltas)
    if n == 0:
        return prior_mean, prior_var, max(obs_var or population_var or DEFAULT_OBS_VAR, MIN_VAR)

    d_bar, personal_var = _mean_var(personal_deltas)

    if obs_var is None:
        if n >= 2 and personal_var > MIN_VAR:
            obs_var = personal_var
        elif population_var is not None and population_var > MIN_VAR:
            obs_var = population_var
        else:
            obs_var = DEFAULT_OBS_VAR
    obs_var = max(obs_var, MIN_VAR)

    prior_precision = 1.0 / prior_var
    data_precision = n / obs_var
    post_var = 1.0 / (prior_precision + data_precision)
    post_mean = (prior_mean * prior_precision + d_bar * data_precision) * post_var
    return post_mean, post_var, obs_var


def _is_effective(effect: float, ci_low: float, ci_high: float, direction: str) -> bool:
    """CI 是否在 desirable 方向上排除 0。

    down(降为好): 整段 CI < 0 (ci_high < 0)。
    up(升为好):   整段 CI > 0 (ci_low > 0)。
    """
    if direction == "up":
        return ci_low > 0
    return ci_high < 0


def estimate_from_deltas(
    metric_code: str,
    personal_deltas: Sequence[float],
    *,
    direction: str = "down",
    cycle_type: Optional[str] = None,
    population_deltas: Optional[Sequence[float]] = None,
    unit: Optional[str] = None,
) -> EffectEstimate:
    """从个人 delta 序列 (+ 可选人群 delta 序列) 算效应后验。纯函数, 不碰 DB。

    人群序列 >= POP_PRIOR_MIN_OBS → 作信息先验; 否则用保守默认先验。
    """
    pop = [float(x) for x in (population_deltas or []) if x is not None]
    if len(pop) >= POP_PRIOR_MIN_OBS:
        prior_mean, prior_var = _mean_var(pop)
        # 同值人群 → 方差≈0 会让先验过度自信压死个人数据; 给一个下限。
        prior_var = max(prior_var, MIN_POP_PRIOR_VAR)
        population_n = len(pop)
    else:
        prior_mean, prior_var = DEFAULT_PRIOR_MEAN, DEFAULT_PRIOR_VAR
        population_n = 0

    population_var = prior_var if population_n else None
    deltas = [float(x) for x in personal_deltas if x is not None]

    post_mean, post_var, _obs = conjugate_posterior(
        deltas,
        prior_mean=prior_mean,
        prior_var=prior_var,
        population_var=population_var,
    )
    half = CI_Z * math.sqrt(post_var)
    ci_low, ci_high = post_mean - half, post_mean + half
    n = len(deltas)
    effective = _is_effective(post_mean, ci_low, ci_high, direction)
    conf = _confidence(n, ci_high - ci_low)

    est = EffectEstimate(
        metric_code=metric_code,
        cycle_type=cycle_type,
        direction=direction or "down",
        effect=post_mean,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_level=CI_LEVEL,
        n_observations=n,
        n_cycles=n,
        prior_mean=prior_mean,
        prior_var=prior_var,
        population_n=population_n,
        confidence=conf,
        is_effective=effective,
        unit=unit,
    )
    est.interpretation = _interpret(est)
    return est


def _interpret(est: EffectEstimate) -> str:
    """人话结论, 供 LLM/UI 解读。"""
    from app.biomarkers import get_definition

    defn = get_definition(est.metric_code)
    name = defn.display if defn else est.metric_code
    unit = est.unit or (defn.canonical_unit if defn else "")
    arrow = "↓" if est.effect < 0 else ("↑" if est.effect > 0 else "→")
    eff_s = f"{est.effect:+.2f}{unit}"
    ci_s = f"[{est.ci_low:+.2f}, {est.ci_high:+.2f}]{unit}"
    pct = int(est.ci_level * 100)

    if est.n_observations == 0:
        return (
            f"{name}: 暂无复查观测, 仅人群先验 (effect≈{eff_s}, {pct}% CI {ci_s}) —— "
            f"尚未在你身上验证, 需先跑复查。"
        )

    desirable = "降" if est.direction == "down" else "升"
    if est.is_effective:
        verdict = (
            f"证据支持该干预对你**很可能有效** (80% CI 整段在'{desirable}'方向, 排除 0), "
            f"可建议继续; 非确诊, 重大调整结合医生。"
        )
    elif est.confidence == "low":
        verdict = "观测仍少, 效应不确定, 建议继续积累复查再判断。"
    else:
        verdict = f"CI 仍跨越 0, 未能确认对你有'{desirable}'效应, 可考虑换方案或延长观测。"

    return (
        f"{name}: effect={eff_s} {arrow} ({pct}% CI {ci_s}), "
        f"基于 {est.n_observations} 次复查, 置信度 {est.confidence}。{verdict}"
    )


# ── DB 层 ──────────────────────────────────────────────────────────────────

def _personal_deltas(
    db: Session, user_id: int, metric_code: str, cycle_type: Optional[str],
) -> tuple[List[float], Optional[str], str]:
    """该用户在 (metric_code[, cycle_type]) 上所有周期的 delta + unit + direction。

    一周期一观测 (取该周期最新 delta)。direction 从 OutcomeMetric 取, 缺省 down。
    user_id 隔离; DB 异常向上抛 (调用方处理)。
    """
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    q = (
        db.query(OutcomeMetric, InterventionCycle)
        .join(InterventionCycle, OutcomeMetric.cycle_id == InterventionCycle.id)
        .filter(InterventionCycle.user_id == user_id)
        .filter(OutcomeMetric.metric_code == metric_code)
        .filter(OutcomeMetric.delta.isnot(None))
    )
    if cycle_type is not None:
        q = q.filter(InterventionCycle.cycle_type == cycle_type)

    deltas: List[float] = []
    unit: Optional[str] = None
    direction = "down"
    for om, _cycle in q.all():
        deltas.append(float(om.delta))
        if unit is None and om.unit:
            unit = om.unit
        if om.direction:
            direction = om.direction
    return deltas, unit, direction


def _population_deltas(
    db: Session, metric_code: str, cycle_type: Optional[str], exclude_user_id: Optional[int],
) -> List[float]:
    """所有(其他)用户同 (metric_code, cycle_type) 的 delta, 作人群先验。

    cycle_type=None 时跨所有类型聚合。exclude_user_id 排除当前用户 (避免自证)。
    """
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    q = (
        db.query(OutcomeMetric.delta)
        .join(InterventionCycle, OutcomeMetric.cycle_id == InterventionCycle.id)
        .filter(OutcomeMetric.metric_code == metric_code)
        .filter(OutcomeMetric.delta.isnot(None))
    )
    if cycle_type is not None:
        q = q.filter(InterventionCycle.cycle_type == cycle_type)
    if exclude_user_id is not None:
        q = q.filter(InterventionCycle.user_id != exclude_user_id)
    return [float(d) for (d,) in q.all() if d is not None]


def estimate_effect(
    db: Session,
    user_id: int,
    metric_code: str,
    cycle_type: Optional[str] = None,
) -> Dict[str, Any]:
    """估计某 (user, metric_code[, cycle_type]) 的个人化干预效应。

    返回 EffectEstimate.to_dict()。降级: DB 异常 → rollback + 回退纯先验 (N=0), 不抛。
    """
    try:
        personal, unit, direction = _personal_deltas(db, user_id, metric_code, cycle_type)
        population = _population_deltas(db, metric_code, cycle_type, exclude_user_id=user_id)
    except Exception:  # noqa: BLE001 — 估计器不应崩调用方; 降级到纯先验
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.exception(
            "[effect_estimator] load failed user=%s metric=%s — falling back to prior",
            user_id, metric_code,
        )
        personal, population, unit, direction = [], [], None, "down"

    est = estimate_from_deltas(
        metric_code,
        personal,
        direction=direction,
        cycle_type=cycle_type,
        population_deltas=population,
        unit=unit,
    )
    return est.to_dict()


def effect_estimates_for_user(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """汇总当前/最近周期所有目标指标的效应估计。

    取该用户 active 周期 (无则最近一个周期) 的 OutcomeMetric.metric_code 去重,
    逐个 estimate_effect。降级: 无周期/异常 → 返回空列表 (不抛)。
    """
    try:
        from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

        cycle = (
            db.query(InterventionCycle)
            .filter(InterventionCycle.user_id == user_id)
            .order_by(
                (InterventionCycle.status == "active").desc(),
                InterventionCycle.start_date.desc(),
            )
            .first()
        )
        if cycle is None:
            return []

        codes = [
            c for (c,) in db.query(OutcomeMetric.metric_code)
            .filter(OutcomeMetric.cycle_id == cycle.id)
            .distinct().all()
        ]
    except Exception:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.exception("[effect_estimator] summary load failed user=%s", user_id)
        return []

    return [
        estimate_effect(db, user_id, code, cycle_type=cycle.cycle_type)
        for code in codes
    ]


def effect_estimate_prompt_blob(db: Session, user_id: int) -> str:
    """紧凑 LLM 文本: 当前周期各目标指标的个人化效应 + "值得继续/换方案"。

    供 agent / SupplementAdvisor 说"这个干预对你 effect=… 值得继续"。
    风格对齐 intervention_proposal_prompt_blob。**只读**, 失败静默返回空串
    (system prompt 注入是旁路, 不应影响主链路)。只产效应结论, 不外泄原始值。
    """
    try:
        estimates = effect_estimates_for_user(db, user_id)
        if not estimates:
            return ""

        lines = [
            "## 干预效应估计 (个人化, 人群先验 + 你的复查收缩)",
            "- 以下是当前/最近干预周期各目标指标对**你**的效应后验估计 (越多复查越准):",
        ]
        for e in estimates:
            lines.append(f"  - {e['interpretation']}")
        lines.append(
            "- 解读: is_effective=有效 (区间在好的方向排除 0) → 可建议继续; "
            "未确认且置信度够 → 可提议换方案; 置信度低 → 提示继续复查积累, 别下定论。"
        )
        lines.append("- 措辞: 这是自我管理实验结论, 非医疗诊断; 重大调整结合医生。")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — prompt 注入旁路, 失败不应影响对话
        logger.exception("[effect_estimator] prompt_blob failed user=%s", user_id)
        return ""
