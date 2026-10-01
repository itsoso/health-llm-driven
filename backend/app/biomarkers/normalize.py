"""Biomarker 归一化 — 纯函数, 把原始体检项归一成标准观测 (PRD P1, G3).

normalize_observation("谷丙转氨酶", 26, "U/L", sex="male") ->
    NormalizedObservation(code="ALT", domain="liver", normalized_value=26.0,
                          normalized_unit="U/L", ref_low=None, ref_high=50, flag="normal", abnormal=False)

纯函数 + 无 DB 依赖 → 易单测。落库由 biomarker_service 负责。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Optional

from app.biomarkers.definitions import (
    REGISTRY,
    BiomarkerDefinition,
    _norm_text,
    _norm_unit,
    _occurs,
    get_definition,
    has_unit,
    name_conflicts_with_code,
    resolve_code,
    to_canonical_unit,
    unit_status,
)


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


def _normalize(
    defn: BiomarkerDefinition, fval: float, unit: Optional[str], sex: Optional[str], age: Optional[int],
    name: Optional[str] = None,
) -> Optional[NormalizedObservation]:
    status = unit_status(defn, unit)
    if status == "incompatible":  # 已识别但量纲不符 (肌酐 ml/min、血红蛋白 pg): 肯定是别的项目
        return None
    if not (status == "ok" and has_unit(unit)):  # 缺单位 / 未识别写法: 只在名字与量级都无歧义时采信
        if defn.unitless_max is not None and fval > defn.unitless_max:
            return None
        if defn.count_qualifiers and not any(q in _norm_text(name) for q in defn.count_qualifiers):
            return None
    if status == "ok" and has_unit(unit):
        # 声明单位下原值离谱 (HbA1c 6.8 "mmol/mol"、LDL 5.2 "mg/dL"): 多是单位写错 —— 读不出 (需核对),
        # 绝不按声明单位硬换算成一个「正常值」(假安心)
        raw_range = defn.unit_plausible.get(_norm_unit(unit))
        if raw_range is not None and not (raw_range[0] <= fval <= raw_range[1]):
            return None
        norm_val, norm_unit = to_canonical_unit(defn, fval, unit)
    else:
        # 缺单位 / 未识别写法 (「-」、mmoI/L 等 OCR 变体): 不确定不等于不是 —— 按 canonical 读 (旧约定),
        # 血红蛋白 14.5 这类小数值是 g/dL 写法。
        norm_val, norm_unit = fval, defn.canonical_unit
        if defn.small_unit is not None and fval < defn.small_unit[0]:
            norm_val = round(fval * defn.small_unit[1], 3)
        elif (mag := next((m for m in defn.magnitude_units if m[0] < fval <= m[1]), None)) is not None:
            norm_val = round(fval * mag[2], 2)  # LDL 200 无单位 = mg/dL
        elif defn.code == "glucose_hba1c" and 20 < fval < 130:  # 缺单位的 IFCC mmol/mol (53 ≈ 7.0%); ≥130 多是 g/L 血红蛋白串项
            norm_val = round(fval / 10.929 + 2.15, 2)

    # 合理区间: 单位相同但量级离谱 (MCHC≈330 g/L 冒充血红蛋白、血红蛋白 160 滑进糖化、尿肌酐冒充血肌酐)
    if defn.plausible is not None and not (defn.plausible[0] <= norm_val <= defn.plausible[1]):
        return None

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

    # 置信度: 未识别单位(按 canonical 假定) → low; 无参考范围 → medium; 否则 high.
    if status == "unknown":
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


def normalize_observation(
    name_or_code: str,
    value,
    unit: Optional[str] = None,
    *,
    sex: Optional[str] = None,
    age: Optional[int] = None,
) -> Optional[NormalizedObservation]:
    """把原始体检项归一化 (落 biomarker_observations 用)。

    None: 项目不认识 / 数值不可解析 / 单位已识别但量纲不符 / 数值不合理 —— 宁可不写也不污染标准序列。
    未识别的单位写法按 canonical 读, confidence=low (旧约定; 未识别只是不确定)。
    """
    defn = get_definition(name_or_code)
    fval = _to_float(value)
    if defn is None or fval is None:
        return None
    return _normalize(defn, fval, unit, sex, age, name_or_code)


def matches_code(name: Optional[str], code: str, keywords: Iterable[str] = ()) -> bool:
    """这一行是不是 code 这个指标 (只看名字): 解析命中 code; 或名字不认识、含调用方旧关键字 (ASCII 词边界)、
    且不与 code 冲突。覆盖只收紧: 别名表没收录的写法不因此漏报, 只有「肯定是别的项目」才排除。"""
    resolved = resolve_code(name or "")
    if resolved == code:
        return True
    if resolved is not None:
        return False
    text = _norm_text(name)
    return any(_occurs(_norm_text(k), text) for k in keywords if k) and not name_conflicts_with_code(name, code)


def matches_row(name: Optional[str], code: str, keywords: Iterable[str] = (), hints: Iterable[str] = ()) -> bool:
    """matches_code + name_en/item_code 提示: 显示名认不出 (None) 且不与 code 冲突时, 提示解析命中 code 也算
    (与写入期 biomarker_service._normalize_item 一致: 英文全称 + OCR 给的 LDL-C / eGFR)。

    提示只能补认, 不能否决显示名: 存量行的 item_code 由旧版 normalize_item_name 从名字派生, 曾把
    「肾小球滤过率(EPI-cr)」编成 CREA —— 让它否决会把真 eGFR 挡掉 (漏报)。显示名认出别的指标或与 code
    冲突 (「UA-PH」+ 派生 code UA) 时, 提示也救不回来。"""
    if matches_code(name, code, keywords):
        return True
    if resolve_code(name or "") is not None or name_conflicts_with_code(name, code):
        return False
    return any(resolve_code(h) == code for h in hints if h)


def value_for_code(value, unit: Optional[str], code: str) -> Optional[float]:
    """按 code 的定义读值 (canonical 单位); 已识别的异量纲单位 / 不合理数值 → None。"""
    defn = REGISTRY.get(code)
    fval = _to_float(value)
    if defn is None or fval is None:
        return None
    norm = _normalize(defn, fval, unit, None, None)
    return norm.normalized_value if norm is not None else None


def reading_for_code(
    name: Optional[str], value, unit: Optional[str], code: str, keywords: Iterable[str] = (),
) -> Optional[float]:
    """名字是 code 这个指标时, 返回 canonical 单位下的值; 否则 None。"""
    return value_for_code(value, unit, code) if matches_code(name, code, keywords) else None


def latest_reading(rows, code: str, keywords: Iterable[str] = (), *, pick=None):
    """rows: [(日期键, 名字, 值, 单位, 原对象[, 提示])], 返回 (对象, 值)。提示 = (name_en, item_code), 见 matches_row。

    最新一次 = 名字属于该指标的行里日期最新的那天 (读不读得出都算); 无日期的行 (合成 twin / 旧缓存)
    保守并入最新组, 绝不因缺日期被丢。只在那一组里挑能读出的行 (pick 为 max/min 时挑风险最高的;
    否则取第一条); 一条都读不出 → (组内第一条, None), 绝不退回更旧的值冒充现值。没有该指标 → (None, None)。
    """
    mine = [r for r in rows if matches_row(r[1], code, keywords, r[5] if len(r) > 5 else ())]
    if not mine:
        return None, None
    newest = max((r[0] for r in mine if r[0]), default=None)
    latest = [r for r in mine if not r[0] or r[0] == newest]
    readable = [(r[4], v) for r in latest if (v := value_for_code(r[2], r[3], code)) is not None]
    if not readable:
        return latest[0][4], None
    return pick(readable, key=lambda hit: hit[1]) if pick else readable[0]


def rejection_reason(name: Optional[str], value, unit: Optional[str]) -> Optional[str]:
    """normalize_observation 拒收的原因 (对账脚本的删除说明用); 能归一则返回 None。"""
    fval = _to_float(value)
    if fval is None:
        return "non-numeric value"
    code = resolve_code(name or "")
    if code is None:
        return "name not recognised"
    defn = REGISTRY[code]
    if unit_status(defn, unit) == "incompatible":
        return f"unit {unit!r} does not fit {code}"
    if _normalize(defn, fval, unit, None, None, name) is None:
        return f"value implausible or ambiguous without unit for {code}"
    return None
