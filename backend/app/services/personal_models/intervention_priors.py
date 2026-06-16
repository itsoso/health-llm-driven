"""人群先验 registry (Phase 1 N-of-1 干预效应估计).

仿 gene_rules 风格: 纯数据, 无 IO。键 (cycle_type, metric_code) → EffectPrior。
单位均为 OutcomeMetric.delta 的同向原始单位 (post - pre)。

参数为基于附录 A 临床方向 + 标准文献的**保守工程取值, 非附录 A 直引**; 不是医嘱。
证据级: A = 多 RCT/Meta + 强指南 · B = 单 RCT/大样本观察 · C = 机制合理人体证据不足。

obs_noise = 该指标**单次测量**的 σ (生物变异 + 分析变异); pre-post 差的噪声在
estimator 里按 sqrt(2)*obs_noise 放大。mcid = 最小临床意义变化 (改善侧, >0)。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Tuple


@dataclass(frozen=True)
class EffectPrior:
    """单个 (干预类型, 指标) 的人群效应先验 + 测量噪声 + 临床阈值."""

    mu_pop: float           # 人群平均效应 (delta 同向单位, 改善方向取决于 direction)
    tau_pop: float          # 人群间个体差异 std (>0): 越大越信个人数据
    obs_noise: float        # 单次测量 σ (生物 + 分析变异, >0)
    mcid: float             # 最小临床意义变化 (>0, 改善幅度阈值)
    evidence_tier: str = "C"          # "A" | "B" | "C"
    requires_clinician: bool = False  # 处方药/激素相关指标 → True
    direction: str = "down"           # "down"=降为好 / "up"=升为好


# 键: (cycle_type, metric_code) —— metric_code 用 canonical biomarker code。
# 数值保守取自 PRD 附录 A + 标准临床文献; 个体化永远 > 通用先验。
PRIORS: Dict[Tuple[str, str], EffectPrior] = {
    # LDL-C: 强化生活方式 ~−0.3~−0.5 mmol/L (低于他汀); 生物+分析 CV~7-9% on ~3 mmol/L≈0.3;
    # MCID 取 0.3 mmol/L (≈ 检测显著变化下限)。处方降脂药领域 → requires_clinician。
    # ref: ACC/AHA 2018 lipid guideline; NCEP 生活方式 LDL 应答区间。
    ("metabolic_90d", "ldl"): EffectPrior(
        mu_pop=-0.4, tau_pop=0.5, obs_noise=0.3, mcid=0.3,
        evidence_tier="B", requires_clinician=True, direction="down",
    ),
    # ALT: MASLD 减重 7-10% → 转氨酶下降, 个体差异大; 单次 ALT CV 高 (~10-15 U/L);
    # MCID 取 10 U/L。ref: AASLD 2025 MASLD; 减重→MASH 缓解。
    ("metabolic_90d", "alt"): EffectPrior(
        mu_pop=-8.0, tau_pop=15.0, obs_noise=10.0, mcid=10.0,
        evidence_tier="B", requires_clinician=False, direction="down",
    ),
    # 体重: 90 天结构化生活方式 ~−3~−5 kg; 体重秤 + 昼夜波动 σ≈0.5 kg; MCID 取 2 kg
    # (保守, 低于 5% 临床缓解阈值但越过测量噪声)。ref: DPP/LookAHEAD 生活方式减重。
    ("metabolic_90d", "weight"): EffectPrior(
        mu_pop=-3.0, tau_pop=3.0, obs_noise=0.5, mcid=2.0,
        evidence_tier="A", requires_clinician=False, direction="down",
    ),
    # HbA1c: 糖前/代谢干预 ~−0.3%; 分析 CV~2% on 6%≈0.15, 生物变异叠加取 0.2; MCID 0.5%
    # (ADA 临床显著差异)。涉及降糖药调整 → requires_clinician。ref: ADA Standards of Care。
    ("metabolic_90d", "hba1c"): EffectPrior(
        mu_pop=-0.3, tau_pop=0.4, obs_noise=0.2, mcid=0.5,
        evidence_tier="A", requires_clinician=True, direction="down",
    ),
    # ApoB (g/L): 降脂干预方向同 LDL; 单次 CV~6-8% on ~0.9 g/L≈0.07; MCID 取 0.1 g/L。
    # 处方降脂药领域 → requires_clinician。ref: ACC/AHA 2018; EAS/ESC ApoB 二级靶点。
    ("metabolic_90d", "apob"): EffectPrior(
        mu_pop=-0.1, tau_pop=0.12, obs_noise=0.07, mcid=0.1,
        evidence_tier="B", requires_clinician=True, direction="down",
    ),
    # 收缩压 SBP (mmHg): 生活方式 (DASH/减重/限钠) ~−5 mmHg, 个体差异大; 单次诊室血压
    # σ≈5 mmHg; MCID 取 5 mmHg。处方降压药领域 → requires_clinician。ref: ACC/AHA 2017 BP。
    ("metabolic_90d", "sbp"): EffectPrior(
        mu_pop=-5.0, tau_pop=8.0, obs_noise=5.0, mcid=5.0,
        evidence_tier="B", requires_clinician=True, direction="down",
    ),
    # 舒张压 DBP (mmHg): 生活方式 ~−3 mmHg; 单次 σ≈4 mmHg; MCID 取 5 mmHg。
    # 处方降压药领域 → requires_clinician。ref: ACC/AHA 2017 BP。
    ("metabolic_90d", "dbp"): EffectPrior(
        mu_pop=-3.0, tau_pop=6.0, obs_noise=4.0, mcid=5.0,
        evidence_tier="B", requires_clinician=True, direction="down",
    ),
    # HRV (rMSSD, ms): 睡眠/恢复干预 8 周 ~+4 ms, 个体差异大; 夜间 HRV CV 大, 单次 σ≈1.5 ms;
    # MCID 取 3 ms。direction="up" (升为好)。ref: HRV biofeedback / 睡眠干预 meta。
    ("sleep_8w", "hrv"): EffectPrior(
        mu_pop=4.0, tau_pop=8.0, obs_noise=1.5, mcid=3.0,
        evidence_tier="B", requires_clinician=False, direction="up",
    ),
}


# 怀疑先验 (skeptical): 未登记的 (cycle_type, metric) 默认**不假设有效** (mu_pop=0)。
# tau_pop 中等 (信号弱时不过度收缩, 让个人数据说话但需较强证据才判 effective);
# obs_noise / mcid 保守, evidence_tier="C"。
DEFAULT_PRIOR = EffectPrior(
    mu_pop=0.0, tau_pop=1.0, obs_noise=1.0, mcid=0.5,
    evidence_tier="C", requires_clinician=False, direction="down",
)


# 处方药 / 激素相关指标关键词 (S3 安全兜底)。即使未登记 (走 DEFAULT_PRIOR), metric_code
# 命中任一 (子串匹配) → 强制 requires_clinician=True, 防止对处方实验下"有效性裁决"。
_CLINICIAN_GATED_KEYWORDS = (
    "ldl", "apob", "hba1c", "a1c", "glucose_fasting", "fasting_glucose",
    "sbp", "dbp", "bp", "blood_pressure",
    "testosterone", "tsh", "ft4", "cortisol",
)


def _is_clinician_gated_code(metric_code: str) -> bool:
    code = (metric_code or "").lower()
    return any(kw in code for kw in _CLINICIAN_GATED_KEYWORDS)


def get_prior(cycle_type: str, metric_code: str) -> EffectPrior:
    """查 (cycle_type, metric_code) 的人群先验; 找不到回 DEFAULT_PRIOR (怀疑先验)。

    S3 兜底: metric_code 命中处方/激素关键词 → 强制 requires_clinician=True
    (即便落到 DEFAULT_PRIOR 也不放过), 防止对处方实验下因果有效性裁决。
    """
    prior = PRIORS.get((cycle_type, metric_code), DEFAULT_PRIOR)
    if not prior.requires_clinician and _is_clinician_gated_code(metric_code):
        return replace(prior, requires_clinician=True)
    return prior
