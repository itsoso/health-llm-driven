# -*- coding: utf-8 -*-
"""PhenoAge —— 基于 9 项常规血检 + 实足年龄计算"表型年龄(生物年龄)"。

来源:Levine ME, Lu AT, Quach A, et al. *An epigenetic biomarker of aging for
lifespan and healthspan.* Aging (Albany NY). 2018;10(4):573-591.

抗衰 MVP 的核心抓手(见 docs/design-longevity-mvp.md):一张普通体检报告即可算出
"身体几岁",零硬件、零测序,适合追踪可逆的生理改善。

⚠️ 单位纪律(系数与单位强绑定,错单位 = 结果失真,这是本文件最大的坑)
原文 supplement 与 optimaldx/BioAge 实现使用的单位(本文件采用):
    albumin     g/L            白蛋白
    creatinine  µmol/L         肌酐
    glucose     mmol/L         空腹血糖
    crp         mg/dL          C 反应蛋白(取自然对数;若实验室给 mg/L,需 ÷10)
    lymphocyte  %              淋巴细胞百分比
    mcv         fL             红细胞平均体积
    rdw         %              红细胞分布宽度
    alp         U/L            碱性磷酸酶
    wbc         10⁹/L          白细胞(= 1000 cells/µL)
    age         years          实足年龄
另有 g/dL / mg/dL 的单位说法在网上流传,但与这套系数**不匹配**,已否决。

claim_boundary:PhenoAge 是基于血检的死亡风险代理指标,反映当前生理状态,
不等于真实生物学衰老速度;用于追踪可逆的生理改善,不作疾病诊断。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ── Levine 2018 线性组合系数(xb)──────────────────────────────────────────
_INTERCEPT = -19.907
_COEF = {
    "albumin": -0.0336,
    "creatinine": 0.0095,
    "glucose": 0.1953,
    "ln_crp": 0.0954,       # 作用在 ln(CRP[mg/dL]) 上
    "lymphocyte": -0.0120,
    "mcv": 0.0268,
    "rdw": 0.3306,
    "alp": 0.00188,
    "wbc": 0.0554,
    "age": 0.0804,
}

# ── xb → 死亡风险 → 表型年龄(岁)的转换常数 ───────────────────────────────
_GAMMA = 0.0076927
# 10 年(120 月)累积基线风险项,预计算一次
_SURV_TERM = (math.exp(120.0 * _GAMMA) - 1.0) / _GAMMA
_PA_INTERCEPT = 141.50225
_PA_A = -0.00553
_PA_B = 0.090165

# CRP 取对数前的下限(hs-CRP 检测下限量级,约 0.1 mg/L = 0.01 mg/dL),避免 ln(0)
_CRP_FLOOR_MG_DL = 0.01

EVIDENCE_TIER = "validated"
CLAIM_BOUNDARY = (
    "PhenoAge 是基于血检的死亡风险代理指标,反映当前生理状态,"
    "不等于真实生物学衰老速度;用于追踪可逆的生理改善,不作疾病诊断。"
)


@dataclass(frozen=True)
class PhenoAgeResult:
    phenotypic_age: float            # 表型年龄(岁)
    delta_years: float               # = phenotypic_age - age(正=偏老)
    inputs_complete: bool = True
    evidence_tier: str = EVIDENCE_TIER
    claim_boundary: str = CLAIM_BOUNDARY


def compute_phenoage(
    *,
    albumin_g_per_l: Optional[float],
    creatinine_umol_per_l: Optional[float],
    glucose_mmol_per_l: Optional[float],
    crp_mg_per_dl: Optional[float],
    lymphocyte_pct: Optional[float],
    mcv_fl: Optional[float],
    rdw_pct: Optional[float],
    alp_u_per_l: Optional[float],
    wbc_10e9_per_l: Optional[float],
    age_years: Optional[float],
) -> Optional[PhenoAgeResult]:
    """计算 PhenoAge。任一输入缺失(None)→ 返回 None(不猜算)。

    单位务必对齐模块 docstring;CRP 若为 mg/L 请先 ÷10 转成 mg/dL 再传入。
    """
    vals = {
        "albumin": albumin_g_per_l,
        "creatinine": creatinine_umol_per_l,
        "glucose": glucose_mmol_per_l,
        "crp_raw": crp_mg_per_dl,
        "lymphocyte": lymphocyte_pct,
        "mcv": mcv_fl,
        "rdw": rdw_pct,
        "alp": alp_u_per_l,
        "wbc": wbc_10e9_per_l,
        "age": age_years,
    }
    if any(v is None for v in vals.values()):
        return None

    crp = max(float(vals["crp_raw"]), _CRP_FLOOR_MG_DL)
    ln_crp = math.log(crp)

    xb = (
        _INTERCEPT
        + _COEF["albumin"] * float(vals["albumin"])
        + _COEF["creatinine"] * float(vals["creatinine"])
        + _COEF["glucose"] * float(vals["glucose"])
        + _COEF["ln_crp"] * ln_crp
        + _COEF["lymphocyte"] * float(vals["lymphocyte"])
        + _COEF["mcv"] * float(vals["mcv"])
        + _COEF["rdw"] * float(vals["rdw"])
        + _COEF["alp"] * float(vals["alp"])
        + _COEF["wbc"] * float(vals["wbc"])
        + _COEF["age"] * float(vals["age"])
    )

    # 10 年死亡风险(Gompertz)
    mort_score = 1.0 - math.exp(-math.exp(xb) * _SURV_TERM)
    # 反解成"岁"
    phenotypic_age = _PA_INTERCEPT + math.log(_PA_A * math.log(1.0 - mort_score)) / _PA_B

    age = float(vals["age"])
    return PhenoAgeResult(
        phenotypic_age=round(phenotypic_age, 2),
        delta_years=round(phenotypic_age - age, 2),
    )
