"""复查间隔下限硬护栏 —— 不让系统把复查排得比「指标生物下限」或「医嘱」更短(纯函数,无 DB)。

methodology §4.4/§8 缺口:followup 路径原样透传 next_due,无下限保护;若任何上游
(LLM 抽取的 verification_days、用户手动、自适应逻辑)给出过短的复查间隔,会催用户做
「测了也没生物学信息增量」甚至有害的过频复查。本护栏是 timing_solver 之外的第二道安全闸。

两条下限,取更严(更长)者为绑定下限:
  1. 生物下限(biological floor)—— 指标变化的时间常数:短于它复查无信息增量。
     依据 methodology §6 证据×节律库(HbA1c~RBC 寿命、血脂干预后达稳态、TSH 半平衡期…)。
  2. 医嘱下限(clinician floor)—— 医生定的复查间隔:系统绝不自行排得更短(R4)。

红线:本护栏只「不缩短」,不「延长/改写」医嘱;不诊断、不调量。未知指标走保守默认 + 标记需医生确认。
"""
from __future__ import annotations

from typing import Dict, Optional

# 指标关键字 → 生物下限(天)。关键字匹配(大小写不敏感子串),与 open_loop_manager 的 ilike 口径一致。
# 数值是「短于此复查无生物学信息增量」的硬下限,非「推荐复查间隔」(后者通常更长)。
BIOLOGICAL_FLOOR_DAYS: Dict[str, int] = {
    "HBA1C": 84,        # 糖化:RBC 寿命~120d,反映前 8–12 周均值;<12 周无新信息
    "HEMOGLOBIN_A1C": 84,
    "LDL": 42,          # 血脂:他汀/生活方式干预后 4–12 周达新稳态,最早 6 周(42d)
    "HDL": 42,
    "CHOLESTEROL": 42,
    "TG": 42,
    "TRIGLYCERIDE": 42,
    "APOB": 42,
    "ALT": 28,          # 肝酶:新基线约 2–4 周
    "AST": 28,
    "GGT": 28,
    "CREATININE": 14,   # 肾功能:急性变化窗,常规按 CKD 分期(更长)
    "EGFR": 14,
    "URIC_ACID": 14,
    "TSH": 42,          # 甲功:T4 达稳态~5–6 周,调量后 6–8 周查
    "VITAMIN_D": 56,    # 25-OH-D:8–12 周达稳态
    "25-OH-D": 56,
    "25(OH)D": 56,
    "FERRITIN": 56,     # 铁蛋白:储备恢复数月
    "HCY": 42,          # 同型半胱氨酸:甲基化补充 4–8 周响应
    "HOMOCYSTEINE": 42,
    # 行为干预可测响应窗~2 周
    "SYSTOLIC_BP": 14,
    "DIASTOLIC_BP": 14,
    "BLOOD_PRESSURE": 14,
    "WEIGHT": 14,
    "BMI": 14,
    "BODY_FAT": 14,
    "FASTING_GLUCOSE": 14,
    "BLOOD_GLUCOSE": 14,
}

# 未知指标的保守默认下限:不允许任何「不认识的指标」被排到 2 周内复查,且标记需医生确认。
DEFAULT_FLOOR_DAYS = 14


def _biological_floor(metric_code: Optional[str]) -> tuple[int, bool]:
    """返回 (生物下限天数, 是否命中已知指标)。最长子串匹配,防短码误配长码。"""
    if not metric_code:
        return DEFAULT_FLOOR_DAYS, False
    code = metric_code.upper()
    best_key, best_len = None, 0
    for key in BIOLOGICAL_FLOOR_DAYS:
        if key in code and len(key) > best_len:
            best_key, best_len = key, len(key)
    if best_key is None:
        return DEFAULT_FLOOR_DAYS, False
    return BIOLOGICAL_FLOOR_DAYS[best_key], True


def clamp_recheck_interval(
    metric_code: Optional[str],
    proposed_days: Optional[int],
    clinician_days: Optional[int] = None,
) -> Dict[str, object]:
    """把建议复查间隔夹到「不短于生物下限 + 不短于医嘱」。

    返回 dict:
      allowed_days   —— 夹后的可用间隔(绝不短于绑定下限)
      was_clamped    —— 是否被夹短了(建议值过短)
      bound_by       —— 'clinician' / 'biological' / 'none'
      biological_floor / clinician_floor / known_metric / reason
    """
    bio_floor, known = _biological_floor(metric_code)
    clin = clinician_days if (clinician_days and clinician_days > 0) else None

    # 绑定下限 = 两者取更严(更长)。医嘱与生物下限谁更长谁绑定。
    binding = bio_floor
    bound_by = "biological"
    if clin is not None and clin > binding:
        binding, bound_by = clin, "clinician"

    if proposed_days is None:
        # 没给建议值 → 用绑定下限作为最早可复查,不算 clamp(是兜底)
        return {
            "allowed_days": binding, "was_clamped": False, "bound_by": "none",
            "biological_floor": bio_floor, "clinician_floor": clin, "known_metric": known,
            "reason": "未给建议间隔,取绑定下限作为最早可复查日。",
        }

    if proposed_days >= binding:
        return {
            "allowed_days": proposed_days, "was_clamped": False, "bound_by": "none",
            "biological_floor": bio_floor, "clinician_floor": clin, "known_metric": known,
            "reason": "建议间隔不短于下限,放行。",
        }

    # 被夹:建议值过短
    if bound_by == "clinician":
        reason = f"建议 {proposed_days}d 短于医嘱 {clin}d → 夹到医嘱(系统不自行缩短医嘱,R4)。"
    elif known:
        reason = f"建议 {proposed_days}d 短于 {metric_code} 生物下限 {bio_floor}d(短于此无信息增量)→ 夹到下限。"
    else:
        reason = f"未知指标,建议 {proposed_days}d 短于保守默认下限 {DEFAULT_FLOOR_DAYS}d → 夹到下限,建议医生确认。"

    return {
        "allowed_days": binding, "was_clamped": True, "bound_by": bound_by,
        "biological_floor": bio_floor, "clinician_floor": clin, "known_metric": known,
        "reason": reason,
    }
