"""Biomarker 归一化 — 纯函数, 把原始体检项归一成标准观测 (PRD P1, G3).

normalize_observation("谷丙转氨酶", 26, "U/L", sex="male") ->
    NormalizedObservation(code="ALT", domain="liver", normalized_value=26.0,
                          normalized_unit="U/L", ref_low=None, ref_high=50, flag="normal", abnormal=False)

纯函数 + 无 DB 依赖 → 易单测。落库由 biomarker_service 负责。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from app.biomarkers.definitions import get_definition, to_canonical_unit


@dataclass
class NormalizedObservation:
    code: str
    display: str
    domain: str
    value: float                 # 原始值
    unit: Optional[str]          # 原始单位
    normalized_value: float
    normalized_unit: str
    ref_low: Optional[float]
    ref_high: Optional[float]
    flag: str                    # low / normal / high / unknown (相对参考范围的位置)
    abnormal: bool               # 是否偏离参考范围
    is_risk: bool                # 偏离方向是否为"风险"(结合 higher_is_risk)
    confidence: str              # high / medium / low

    def as_dict(self) -> dict:
        return asdict(self)


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_observation(
    name_or_code: str,
    value,
    unit: Optional[str] = None,
    *,
    sex: Optional[str] = None,
    age: Optional[int] = None,
) -> Optional[NormalizedObservation]:
    """把原始体检项归一化。无法识别项目或数值 → 返回 None。"""
    defn = get_definition(name_or_code)
    fval = _to_float(value)
    if defn is None or fval is None:
        return None

    norm_val, norm_unit = to_canonical_unit(defn, fval, unit)
    unit_converted_cleanly = norm_unit == defn.canonical_unit

    rng = defn.resolve_range(sex, age)
    ref_low = rng.low if rng else None
    ref_high = rng.high if rng else None

    flag = "unknown"
    abnormal = False
    if rng is not None:
        if ref_high is not None and norm_val > ref_high:
            flag, abnormal = "high", True
        elif ref_low is not None and norm_val < ref_low:
            flag, abnormal = "low", True
        else:
            flag = "normal"

    # 风险方向: higher_is_risk=True 时 high 为风险; False 时 low 为风险.
    is_risk = abnormal and (
        (flag == "high" and defn.higher_is_risk) or (flag == "low" and not defn.higher_is_risk)
    )

    # 置信度: 单位干净换算 + 命中参考范围 → high; 单位未知 → low; 无参考范围 → medium.
    if not unit_converted_cleanly:
        confidence = "low"
    elif rng is None:
        confidence = "medium"
    else:
        confidence = "high"

    return NormalizedObservation(
        code=defn.code,
        display=defn.display,
        domain=defn.domain,
        value=fval,
        unit=unit,
        normalized_value=norm_val,
        normalized_unit=norm_unit,
        ref_low=ref_low,
        ref_high=ref_high,
        flag=flag,
        abnormal=abnormal,
        is_risk=is_risk,
        confidence=confidence,
    )
