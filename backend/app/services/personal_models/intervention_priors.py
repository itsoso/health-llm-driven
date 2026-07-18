"""人群先验 registry (Phase 1 N-of-1 干预效应估计).

仿 gene_rules 风格: 纯数据, 无 IO。键 (cycle_type, metric_code) → EffectPrior。
单位均为 OutcomeMetric.delta 的同向原始单位 (post - pre)。

参数为基于附录 A 临床方向 + 标准文献的**保守工程取值, 非附录 A 直引**; 不是医嘱。
证据级: A = 多 RCT/Meta + 强指南 · B = 单 RCT/大样本观察 · C = 机制合理人体证据不足。

obs_noise = 该指标**单次测量**的 σ (生物变异 + 分析变异); pre-post 差的噪声在
estimator 里按 sqrt(2)*obs_noise 放大。mcid = 最小临床意义变化 (改善侧, >0)。
"""
from __future__ import annotations

import re
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
    # ALT: MASLD 减重 7-10% → 转氨酶下降 (统计参数仍据此; 单次 CV 高 ~10-15 U/L, MCID 10 U/L;
    # ref AASLD 2025 MASLD)。R16 安全裁决 (2026-06-26, founder/clinician call): 肝酶**升高**可能
    # 是药物性肝损伤 (DILI), 应交医生; 且 ALT 受多药混杂 → requires_clinician=True, 即使统计判
    # 改善/恶化也降级 clinician_review (post_mean/CI 仍留结构化字段供内部)。原 False 是按纯
    # MASLD 生活方式读出设的, 现按"药物混杂 + DILI 安全信号"上调; 与 _CLINICIAN_GATED_EXACT_CODES 一致。
    ("metabolic_90d", "alt"): EffectPrior(
        mu_pop=-8.0, tau_pop=15.0, obs_noise=10.0, mcid=10.0,
        evidence_tier="B", requires_clinician=True, direction="down",
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
# 注: 这些都是足够长/唯一的子串 (ldl/apob/hba1c/sbp/...), 误伤概率低; 短 code 走下面的精确集。
_CLINICIAN_GATED_KEYWORDS = (
    "ldl", "apob", "hba1c", "a1c", "glucose_fasting", "fasting_glucose",
    "sbp", "dbp", "bp", "blood_pressure",
    "testosterone", "tsh", "ft4", "cortisol",
)

# R16 (2026-06-26): 药物混杂的代谢周期默认靶标 —— 精确 code 集 (含别名), **不**用子串。
# 这些 code 太短, 子串会误伤无关指标 (如 "salt_intake" 命中 "alt"、"watch"/"match" 命中 "tc"、
# "manual"/"annual" 命中 "ua"), 故按精确 code 匹配。临床依据 (founder/clinician call):
#   - TC (总胆固醇): 跟随已门控的 LDL, 他汀混杂 → 门控 LDL 不门控 TC 不一致。
#   - UA (尿酸): 降尿酸药 (别嘌醇/非布司他) 在代谢人群常见且药效主导生活方式。
#   - ALT/AST/GGT (转氨酶/肝酶): 升高可能是药物性肝损伤 (DILI), 应交医生; 且受多药混杂。
#     AST 与 ALT 同为转氨酶, DILI 理由对称, 一并门控 (registry code="AST")。
# 不入此集 (生活方式主导 + 处方低发, 门控会废掉周期合法读出): lipid_tg (甘油三酯)、lipid_hdl。
_CLINICIAN_GATED_EXACT_CODES = frozenset({
    "lipid_tc", "tc", "total_cholesterol",
    "ua", "uric_acid",
    "alt", "ast",
    "ggt",
    "apo_b", "lp_a",
})


def _is_clinician_gated_code(metric_code: str) -> bool:
    code = str(metric_code or "").strip().lower()
    compact = re.sub(r"[\s_-]+", "", code)
    exact_compact = {re.sub(r"[\s_-]+", "", item) for item in _CLINICIAN_GATED_EXACT_CODES}
    if code in _CLINICIAN_GATED_EXACT_CODES or compact in exact_compact:
        return True
    return any(re.sub(r"[\s_-]+", "", kw) in compact for kw in _CLINICIAN_GATED_KEYWORDS)


def is_clinician_gated_metric(metric_code: str) -> bool:
    """公开单一事实源: metric_code 是否属处方/激素/药物混杂指标。

    任何对个体化"干预效应/有效性"下裁决的估计器 (treatment_effect 经 get_prior、
    effect_estimator 直接调本函数) 都共用这同一门控集 —— 防止两个估计器门控集漂移
    (历史教训: 漏路由的高曝光消费端是真正的 R4 泄漏点)。
    """
    return _is_clinician_gated_code(metric_code)


# ── 自由文本门控 ────────────────────────────────────────────────────────────────
# 对话抽取等路径只有自然语言 (用户自陈 / subject / object), 没有 canonical metric_code。
# 用户口语说"转氨酶/收缩压/uric acid"而非 code, 这些 NL 同义词补 code 集没有的说法。
# 放这里 (而非各 producer 本地复制关键词) = 仍是单一事实源: 改门控集只动这一处。
# code 集 (is_clinician_gated_metric 用) 仍是 canonical-code 的权威; 此处只是为自由文本补 NL 层。

# 含非拉丁字符 (中文) 的同义词 —— 对原始小写文本子串匹配。
_CLINICIAN_GATED_TEXT_TERMS_ZH = (
    "转氨酶", "谷丙", "谷草", "肝酶",          # ALT / AST / GGT (DILI 药物混杂)
    "尿酸",                                     # UA (降尿酸药混杂)
    "胆固醇", "低密度脂蛋白", "载脂蛋白",       # TC / LDL / ApoB (他汀混杂)
    "血糖", "糖化",                             # 空腹血糖 / HbA1c (降糖药混杂)
    "血压", "收缩压", "舒张压",                 # BP / SBP / DBP (降压药混杂; 血压≠收缩压子串)
    "睾酮", "皮质醇", "甲状腺",                 # 激素
)

# 纯拉丁 NL 叙述同义词 (code 集没有的英文说法) —— 归一化 (去空格/下划线/连字符) 后子串匹配,
# 故 "blood pressure" / "uric acid" / "apo b" / "liver enzymes" 都能命中。
_CLINICIAN_GATED_TEXT_TERMS_EN = (
    "bloodpressure", "systolic", "diastolic",
    "uricacid", "transaminase", "cholesterol", "liverenzyme",
    "apolipoprotein",  # 拼全的 ApoB (缩写 apob/apo b 与中文载脂蛋白另有覆盖)
)

_ALL_GATED_CODES = _CLINICIAN_GATED_EXACT_CODES | frozenset(_CLINICIAN_GATED_KEYWORDS)

# 短 code/keyword (≤3 字符: alt/ast/ggt/ua/tc/bp/sbp/dbp/a1c/tsh/ft4) 在自由文本里只能
# 按 token 边界匹配 —— 子串会误伤 salt⊃alt / manual⊃ua / watch⊃tc / 60bpm⊃bp。
_GATED_SHORT_TOKENS = frozenset(c for c in _ALL_GATED_CODES if len(c) <= 3)

# 长 code/keyword (>3) 归一化去下划线后并入英文 NL 叙述, 统一对归一化文本子串匹配
# (足够长/唯一, 子串安全)。两套均从上面单一事实源派生, 不复制清单。
_GATED_LONG_NORM = tuple(
    c.replace("_", "") for c in _ALL_GATED_CODES if len(c) > 3
) + _CLINICIAN_GATED_TEXT_TERMS_EN


def _strip_to_latin(text: str) -> str:
    """小写 + 去掉一切非字母数字 (空格/下划线/连字符/标点/中文) → 让 'blood pressure' /
    'blood_pressure' / 'apo b' 归一成同一串, 仅用于长 NL 子串匹配。"""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def gate_text_for_clinician(text: str) -> bool:
    """自由文本 (用户自陈 / subject / object_value) 是否提及处方/激素/药物混杂指标。

    用于对话抽取这类"只有自然语言、无 canonical metric_code"的路径: 命中 → 调用方应把
    因果裁决 (responds_to / does_not_respond_to / partially_responds_to) 降级为描述性
    observed_change, 防止对药物混杂指标 (ALT/尿酸/LDL/HbA1c/血压…) 下"X 有效/无效"的
    R4 efficacy 断言 (混杂的他汀/降尿酸药/降压药才可能是真因)。

    与 is_clinician_gated_metric 共享同一 canonical-code 集 (_CLINICIAN_GATED_EXACT_CODES
    / _CLINICIAN_GATED_KEYWORDS), 自由文本另补中英 NL 同义词。

    R4 保守: 命中即门控。漏判 (under-gate) = 真 R4 泄漏; 误判 (把纯生活方式因果降级) =
    安全侧失败 (故对短 code 之外宁可宽松)。短 code 按 token 边界匹配防 salt/manual/watch/bpm 误伤。
    """
    if not text:
        return False
    low = text.lower()
    if any(term in low for term in _CLINICIAN_GATED_TEXT_TERMS_ZH):
        return True
    norm = _strip_to_latin(low)
    if any(sub in norm for sub in _GATED_LONG_NORM):
        return True
    tokens = set(re.split(r"[^a-z0-9]+", low))
    return bool(tokens & _GATED_SHORT_TOKENS)


def get_prior(cycle_type: str, metric_code: str) -> EffectPrior:
    """查 (cycle_type, metric_code) 的人群先验; 找不到回 DEFAULT_PRIOR (怀疑先验)。

    S3 兜底: metric_code 命中处方/激素关键词 → 强制 requires_clinician=True
    (即便落到 DEFAULT_PRIOR 也不放过), 防止对处方实验下因果有效性裁决。
    """
    prior = PRIORS.get((cycle_type, metric_code), DEFAULT_PRIOR)
    if not prior.requires_clinician and _is_clinician_gated_code(metric_code):
        return replace(prior, requires_clinician=True)
    return prior
