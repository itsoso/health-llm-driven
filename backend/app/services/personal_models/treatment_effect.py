"""N-of-1 干预效应估计器 (Phase 1, 层级贝叶斯, 纯统计无 LLM/ML 框架).

人群先验 (EffectPrior) + 个人观测 (observed_delta) → 共轭高斯后验
(个人化效应 + 80% CI + 裁决 + 措辞)。见 docs/design-personal-predictive-model.md §Phase 1。

裁决 (verdict) 中性、周期限定 —— 不含"被证明有效"含义:
  - 改善侧 CI 整段越过 +MCID            → improved_in_cycle
  - CI 整段在反方向越过 -MCID (恶化)    → worsened_in_cycle
  - 跨 0 或没越过 MCID                  → inconclusive
  - sigma_obs<=0 退化                   → insufficient_data (守 Rule#1, 不静默假装有结论)

安全裁决 (severe safety review):
  - requires_clinician=True (处方药/激素相关) → 即使统计判改善/恶化, verdict 一律降级
    clinician_review; message 删"个人化效应估计 X"因果归属句, 改描述 + 混杂提示 + 交医生。
    (post_mean/CI 仍留在结构化字段供内部, 不进面向用户 message。)
  - 非处方 + confidence in (low, med) → message 弱化为描述式 ("看起来"/"把握有限"),
    不出确定的"效应估计"裁决句; 确定语气只给 confidence=high 的非处方 improved/worsened。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.personal_models.intervention_priors import EffectPrior, get_prior

logger = logging.getLogger(__name__)

MODEL_VERSION = "phase1-hbayes-v1"
_Z_80 = 1.2816  # 标准正态 90% 分位 → 80% 双侧 CI 半宽系数

# S1: 每个 verdict 的强制 hedge 中文 display_label (前端渲染此字段, 不渲染裸 verdict)。
DISPLAY_LABELS: Dict[str, str] = {
    "improved_in_cycle": "周期内观察到改善",
    "worsened_in_cycle": "周期内观察到变差",
    "clinician_review": "需医生评估",
    "inconclusive": "暂不下结论",
    "insufficient_data": "数据不足",
}

# N1: metric_code → 中文显示名 (message / display 用中文, 不裸大写 code)。
_METRIC_DISPLAY_NAMES: Dict[str, str] = {
    "ldl": "LDL",
    "ldl_c": "LDL",
    "ldlc": "LDL",
    "lipid_ldl": "LDL",
    "apob": "ApoB",
    "hba1c": "糖化血红蛋白",
    "a1c": "糖化血红蛋白",
    "glucose_hba1c": "糖化血红蛋白",
    "weight": "体重",
    "sbp": "收缩压",
    "dbp": "舒张压",
    "bp": "血压",
    "alt": "ALT",
    "ast": "AST",
    "ggt": "GGT",
    "hrv": "HRV",
    "glucose_fasting": "空腹血糖",
    "fasting_glucose": "空腹血糖",
    "testosterone": "睾酮",
    "tsh": "促甲状腺激素",
    "cortisol": "皮质醇",
    # R16: 新门控 / 代谢周期默认靶标的中文名 (clinician_review message 用)。
    "lipid_tc": "总胆固醇",
    "tc": "总胆固醇",
    "total_cholesterol": "总胆固醇",
    "ua": "尿酸",
    "uric_acid": "尿酸",
    "lipid_tg": "甘油三酯",
    "lipid_hdl": "HDL",
}


def metric_display_name(metric_code: str) -> str:
    """metric_code → 中文显示名; 未登记回退原 code (不报错)。"""
    if not metric_code:
        return "该指标"
    return _METRIC_DISPLAY_NAMES.get(metric_code.lower(), metric_code)


@dataclass
class EffectEstimate:
    metric_code: str
    unit: Optional[str]
    observed_delta: Optional[float]
    posterior_effect: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    ci_level: float
    confidence: str            # "high" | "med" | "low"
    # improved_in_cycle | worsened_in_cycle | clinician_review | inconclusive | insufficient_data
    verdict: str
    evidence_tier: str
    requires_clinician: bool
    message: str
    display_label: str = ""    # S1: 强制 hedge 的中文标签 (前端渲染此字段)
    model_version: str = MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.display_label:
            self.display_label = DISPLAY_LABELS.get(self.verdict, self.verdict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_code": self.metric_code,
            "unit": self.unit,
            "observed_delta": self.observed_delta,
            "posterior_effect": self.posterior_effect,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_level": self.ci_level,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "display_label": self.display_label,
            "evidence_tier": self.evidence_tier,
            "requires_clinician": self.requires_clinician,
            "message": self.message,
            "model_version": self.model_version,
        }


def _fmt(x: float) -> str:
    """紧凑数字格式 (避免 -0.0 / 长尾小数)。"""
    if x == 0:
        x = 0.0
    return f"{x:+.1f}" if abs(x) >= 1 or x == 0 else f"{x:+.2f}"


def _insufficient(prior: EffectPrior, metric_code: str, unit: Optional[str],
                  observed_delta: Optional[float]) -> EffectEstimate:
    return EffectEstimate(
        metric_code=metric_code,
        unit=unit,
        observed_delta=observed_delta,
        posterior_effect=None,
        ci_low=None,
        ci_high=None,
        ci_level=0.8,
        confidence="low",
        verdict="insufficient_data",
        evidence_tier=prior.evidence_tier,
        requires_clinician=prior.requires_clinician,
        message="数据/把握不足,暂不下结论,继续观察。相关,非因果,供你与医生参考。"
        + ("涉及处方调整请与医生确认。" if prior.requires_clinician else ""),
    )


def estimate_effect(
    observed_delta: float,
    prior: EffectPrior,
    *,
    metric_code: str = "",
    unit: Optional[str] = None,
) -> EffectEstimate:
    """纯函数: 共轭高斯后验 + 80% CI + 裁决 + 措辞。"""
    sigma_obs = math.sqrt(2.0) * prior.obs_noise  # pre-post 差的测量噪声
    if sigma_obs <= 0 or prior.tau_pop <= 0:
        return _insufficient(prior, metric_code, unit, observed_delta)

    prec_prior = 1.0 / (prior.tau_pop ** 2)
    prec_obs = 1.0 / (sigma_obs ** 2)
    post_mean = (prior.mu_pop * prec_prior + observed_delta * prec_obs) / (prec_prior + prec_obs)
    post_var = 1.0 / (prec_prior + prec_obs)
    half = _Z_80 * math.sqrt(post_var)
    ci_low = post_mean - half
    ci_high = post_mean + half

    # 方向归一: 改善量 (越大越好) + 改善侧 CI
    if prior.direction == "up":
        improvement = post_mean
        imp_low, imp_high = ci_low, ci_high
    else:  # "down": 降为好, 改善 = -delta
        improvement = -post_mean
        imp_low, imp_high = -ci_high, -ci_low  # 翻转后重排序

    mcid = prior.mcid
    if imp_low >= mcid:                 # 改善侧 CI 整段越过 +MCID
        verdict = "improved_in_cycle"
    elif imp_high <= -mcid:             # CI 整段在反方向越过 -MCID
        verdict = "worsened_in_cycle"
    else:
        verdict = "inconclusive"

    # 置信度: CI 全宽相对 MCID。窄 (< MCID) → high; < 2*MCID → med; 否则 low。
    ci_width = ci_high - ci_low
    if ci_width < mcid:
        confidence = "high"
    elif ci_width < 2 * mcid:
        confidence = "med"
    else:
        confidence = "low"

    # D1: 处方/激素指标 → 即使统计判改善/恶化, 一律降级 clinician_review
    # (不在无医生在场时对处方实验下有效性裁决)。inconclusive 维持 inconclusive。
    if prior.requires_clinician and verdict in ("improved_in_cycle", "worsened_in_cycle"):
        verdict = "clinician_review"

    message = _build_message(
        metric_code=metric_code, unit=unit, observed_delta=observed_delta,
        post_mean=post_mean, ci_low=ci_low, ci_high=ci_high,
        verdict=verdict, confidence=confidence,
        requires_clinician=prior.requires_clinician,
    )

    return EffectEstimate(
        metric_code=metric_code,
        unit=unit,
        observed_delta=observed_delta,
        posterior_effect=post_mean,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_level=0.8,
        confidence=confidence,
        verdict=verdict,
        evidence_tier=prior.evidence_tier,
        requires_clinician=prior.requires_clinician,
        message=message,
    )


def _build_message(
    *, metric_code: str, unit: Optional[str], observed_delta: float,
    post_mean: float, ci_low: float, ci_high: float, verdict: str,
    confidence: str, requires_clinician: bool,
) -> str:
    """措辞红线: 永不说'证明/治愈/保证'。

    分支:
      - clinician_review (处方): 描述式 + 明确混杂 + 交医生; 不出"效应估计 X"因果句,
        post_mean/CI 不进面向用户 message。
      - inconclusive: 暂不下结论。
      - improved/worsened + confidence=high (非处方): 确定语气 + "个人化估计 X" + CI。
      - improved/worsened + confidence in (low,med) (非处方): 弱化为"看起来"+"把握有限"+CI,
        不出确定的"效应估计"裁决句。
    """
    label = metric_display_name(metric_code)
    u = unit or ""

    # D1: 处方/激素分支 —— 删因果归属句, 描述 + 混杂 + 交医生。
    if verdict == "clinician_review":
        return (
            f"这个周期里你的 {label} 变化 {_fmt(observed_delta)}{u}"
            f"(同期可能受用药等多重因素影响,本系统不区分)。"
            f"是否有意义、是否需要调整方案,请由医生判断。"
        )

    if verdict == "inconclusive":
        return "数据/把握不足,暂不下结论,继续观察。相关,非因果,供你与医生参考。"

    # 非处方 improved/worsened: 确定语气只给 high; low/med 弱化为描述式。
    if confidence == "high":
        body = (
            f"这个周期里你的 {label} 变化 {_fmt(observed_delta)}{u};"
            f"结合人群先验,对你的个人化估计 {_fmt(post_mean)}{u}"
            f"(80% 区间 {_fmt(ci_low)}~{_fmt(ci_high)})。"
        )
    else:  # low / med —— D2: 描述式, 不下确定裁决
        verb = "有改善" if verdict == "improved_in_cycle" else "变差了"
        body = (
            f"在这个周期里看起来你的 {label} {verb}"
            f"(把握有限,需更多周期确认;80% 区间 {_fmt(ci_low)}~{_fmt(ci_high)}{u})。"
        )
    return body + "相关,非因果,供你参考。"


# ---------------------------------------------------------------------------
# S2: 审计旁路 —— 处方或 improved/worsened/clinician_review 裁决留痕。
# ---------------------------------------------------------------------------
_AUDITED_VERDICTS = ("improved_in_cycle", "worsened_in_cycle", "clinician_review")


def _audit_estimate(
    *, db: Session, user_id: int, cycle_id: int, metric_code: str,
    verdict: str, requires_clinician: bool,
) -> Optional[int]:
    """对处方或有方向裁决的 estimate 写一条 agent audit (留痕: 对谁/什么 cycle/什么裁决)。

    旁路: 失败不影响主流程 (仿现有 audit 用法)。
    """
    from app.agents.audit import _write

    summary = (
        f"treatment-effect {metric_code} cycle={cycle_id} verdict={verdict} "
        f"clinician={requires_clinician}"
    )
    return _write(
        db,
        user_id=user_id,
        agent_type="personal_model",
        action="estimate_cycle_effect",
        result_summary=summary,
        result_detail={
            "metric_code": metric_code,
            "cycle_id": cycle_id,
            "verdict": verdict,
            "requires_clinician": requires_clinician,
        },
    )


# ---------------------------------------------------------------------------
# Service: 取 cycle 的 OutcomeMetrics → 逐个估计 (强制 user_id 隔离)。
# ---------------------------------------------------------------------------
def estimate_cycle_effects(
    db: Session,
    user_id: int,
    cycle_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """估计某 cycle 内每个 OutcomeMetric 的个人化效应。

    cycle_id 指定 → 取该 (id, user_id) 的 cycle; 否则取该 user 最近的 active cycle。
    user_id 隔离: 查询恒带 user_id filter, 跨用户 cycle_id 拿不到 → 返回 []。
    baseline 或 latest 缺 → 产 insufficient 占位 (不静默跳过, 守 Rule#1)。
    """
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    try:
        q = db.query(InterventionCycle).filter(InterventionCycle.user_id == user_id)
        if cycle_id is not None:
            cycle = q.filter(InterventionCycle.id == cycle_id).first()
        else:
            cycle = (
                q.filter(InterventionCycle.status == "active")
                .order_by(InterventionCycle.start_date.desc(), InterventionCycle.id.desc())
                .first()
            )
        if cycle is None:
            return []

        metrics = (
            db.query(OutcomeMetric)
            .filter(OutcomeMetric.cycle_id == cycle.id)
            .order_by(OutcomeMetric.id.asc())
            .all()
        )
    except Exception:
        db.rollback()
        logger.exception("[TreatmentEffect] cycle effects query failed user=%s cycle=%s",
                         user_id, cycle_id)
        raise

    results: List[Dict[str, Any]] = []
    for m in metrics:
        base_prior = get_prior(cycle.cycle_type, m.metric_code)
        direction = m.direction or base_prior.direction
        prior = replace(base_prior, direction=direction)

        if m.baseline_value is None or m.latest_value is None:
            est = _insufficient(prior, m.metric_code, m.unit,
                                None if m.delta is None else float(m.delta))
            results.append(est.to_dict())
            continue

        observed_delta = float(m.latest_value) - float(m.baseline_value)
        est = estimate_effect(observed_delta, prior, metric_code=m.metric_code, unit=m.unit)
        results.append(est.to_dict())

        # S2: 处方或有方向裁决 → 旁路写 audit (失败不影响主流程)。
        if est.requires_clinician or est.verdict in _AUDITED_VERDICTS:
            try:
                _audit_estimate(
                    db=db, user_id=user_id, cycle_id=cycle.id,
                    metric_code=est.metric_code, verdict=est.verdict,
                    requires_clinician=est.requires_clinician,
                )
            except Exception:  # noqa: BLE001
                logger.warning("[TreatmentEffect] audit 旁路写入失败 (跳过) user=%s cycle=%s",
                               user_id, cycle.id)

    return results
