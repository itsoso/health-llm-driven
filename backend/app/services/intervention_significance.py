"""干预结果显著性 —— 用参考变化值(RCV)给 baseline→latest 变化去噪 + 标置信度(R16 第一刀)。

问题:原 `_metric_status` 把任何非零 delta 都算"改善/恶化",把测量噪声当干预见效。
方法:每个生物标志物有公认的个体内生物学变异 CVi(EFLM/Westgard 数据库)。单次复查的变化
要超过**参考变化值** RCV%(= 1.96 × √2 × CVi ≈ 2.77×CVi,95% 双向)才算"真变化"。
低于 RCV → 落在噪声带内 → status=flat + 低置信(不臆断见效)。

诚实边界:RCV 用人群参考 CVi,非该用户实测方差(无足够时间序列时的稳健近似);
未知指标用保守通用值并把置信度封顶到 moderate。这是去噪护栏,不替代医生判读。
"""
from typing import Optional, Tuple

# 个体内生物学变异 CVi%(近似,来源 EFLM Biological Variation / Westgard)。
# key 用本仓库 canonical biomarker code(见 intervention_cycle_service._DEFAULT_TARGET_RULES),
# 兼收常见别名;rcv_pct 内部 lower() 后匹配。
_CVI_PCT = {
    # canonical codes
    "lipid_ldl": 8.3, "lipid_hdl": 7.5, "lipid_tc": 6.0, "lipid_tg": 20.0,
    "ua": 8.6, "glucose_fasting": 5.7, "glucose_hba1c": 1.9, "alt": 18.0, "ast": 12.0,
    # 常见别名
    "ldl": 8.3, "ldl_c": 8.3, "hdl": 7.5, "hdl_c": 7.5, "total_cholesterol": 6.0,
    "tc": 6.0, "triglycerides": 20.0, "tg": 20.0, "apob": 6.5,
    "hba1c": 1.9, "glucose": 5.7, "fasting_glucose": 5.7, "fpg": 5.7,
    "insulin": 21.0, "homa_ir": 25.0, "ggt": 14.0,
    "creatinine": 5.3, "egfr": 6.5, "uric_acid": 8.6,
    "crp": 42.0, "hs_crp": 42.0, "hscrp": 42.0,
    "weight": 1.5, "bmi": 1.5, "systolic": 6.5, "diastolic": 7.0,
}
_GENERIC_CVI_PCT = 10.0   # 未知指标的保守兜底
_Z = 1.96                 # 95% 双向
_RCV_FACTOR = _Z * (2 ** 0.5)   # ≈ 2.77


def rcv_pct(metric_code: str) -> Tuple[float, bool]:
    """该指标的参考变化值(%)+ 是否有该指标的已知 CVi(未知→保守兜底)。"""
    code = (metric_code or "").lower()
    cvi = _CVI_PCT.get(code)
    known = cvi is not None
    return round(_RCV_FACTOR * (cvi if known else _GENERIC_CVI_PCT), 1), known


def classify_change(delta_pct: Optional[float], metric_code: str) -> Tuple[bool, str]:
    """(变化是否显著超噪声, 置信度 low/moderate/high)。

    |delta%| < RCV → (False, "low");RCV..1.5×RCV → (True, "moderate");≥1.5×RCV → (True, "high")。
    未知 CVi 的指标置信度封顶 moderate(变异未知,不夸大)。delta_pct 缺失 → (False,"low")。
    """
    if delta_pct is None:
        return False, "low"
    rcv, known = rcv_pct(metric_code)
    mag = abs(delta_pct)
    if mag < rcv:
        return False, "low"
    if mag < rcv * 1.5 or not known:
        return True, "moderate"
    return True, "high"
