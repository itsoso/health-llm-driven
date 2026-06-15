"""心律筛查规则 —— Apple Watch ECG 房颤分类。

来源:
- Apple Watch ECG app 是 FDA 510(k) 清除的**单导联**心电图, 给出节律分类
  (SinusRhythm / AtrialFibrillation / Inconclusive*), 是**筛查工具非诊断设备**.
- 房颤 (AFib) 是"沉默杀手": 常无症状, 但显著升高卒中风险 (CHA2DS2-VASc).
  Apple Heart Study (Perez et al., NEJM 2019) 证明可穿戴可有效筛出无症状房颤.

设计原则 (本规则会过医疗安全评审):
- **筛查信号非诊断, 非处方**. 只给"尽快就医做正式诊断"的就医动作.
- 只对**明确**的 "AtrialFibrillation" 分类 (或 afib_event_count>=1) 告警.
- SinusRhythm / Inconclusive* / Unrecognized / 缺失 → **不告警** (不误报, 不制造恐慌).
- 多次/反复出现 → 升级措辞 (CRITICAL), 但仍非诊断。
"""

from typing import Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin


_AFIB_CLASSIFICATION = "AtrialFibrillation"


@register
def ecg_atrial_fibrillation(twin: HealthTwin) -> Optional[Alert]:
    """Apple Watch ECG 记录到房颤分类 → 提示尽快就医做正式诊断 (筛查非诊断)。

    - 单次房颤分类 → HIGH。
    - 多次 (afib_event_count >= 2) → CRITICAL (升级措辞, 仍非诊断)。
    - SinusRhythm / Inconclusive / 缺失 → 不告警。
    """
    p = twin.physiological
    classification = p.ecg_classification
    afib_count = p.afib_event_count or 0

    # 只认明确的房颤: 分类字符串命中, 或窗口内房颤计数 >=1.
    is_afib = classification == _AFIB_CLASSIFICATION or afib_count >= 1
    if not is_afib:
        return None

    # 计数缺失但分类命中时, 至少按 1 次表述.
    shown_count = afib_count if afib_count >= 1 else 1
    recurring = afib_count >= 2

    if recurring:
        severity = Severity.CRITICAL
        title = "Apple Watch 多次记录到房颤分类"
        message = (
            f"你的 Apple Watch ECG 在近期**多次**（{shown_count} 次）记录到"
            "心房颤动（AtrialFibrillation）分类。这是**筛查提示，不是诊断**——"
            "Apple Watch 的单导联心电图无法替代医生和正式 12 导联心电图。"
            "反复出现的房颤会明显增加卒中风险，需要尽快由医生评估。"
        )
        action = (
            "请尽快前往心血管内科（心内科）就诊，携带 Apple Watch 上保存的 ECG 记录"
            "（健康 App 可导出 PDF）供医生参考；若同时出现胸痛、严重心悸、气促、"
            "晕厥或一侧肢体无力/言语不清，立即就医或拨打急救电话。"
        )
    else:
        severity = Severity.HIGH
        title = "Apple Watch 记录到房颤分类"
        message = (
            f"你的 Apple Watch ECG 记录到心房颤动（AtrialFibrillation）分类"
            f"（{shown_count} 次）。这是**筛查提示，不是诊断**——单导联心电图只能提示，"
            "不能确诊。房颤会增加卒中风险，建议尽快由医生做正式诊断。"
        )
        action = (
            "建议尽快前往心血管内科（心内科）做正式诊断，携带 Apple Watch 上保存的"
            "ECG 记录（健康 App 可导出 PDF）；若出现胸痛、严重心悸、气促或晕厥，立即就医。"
        )

    return Alert(
        rule_id="cardiac.ecg_atrial_fibrillation",
        category="cardiac",
        severity=severity,
        title=title,
        message=message,
        action=action,
        data_citation={
            "ecg_classification": classification,
            "afib_event_count": afib_count,
            "ecg_recorded_at": str(p.ecg_recorded_at) if p.ecg_recorded_at else None,
        },
        references=[
            "https://www.nejm.org/doi/full/10.1056/NEJMoa1901183",  # Apple Heart Study
        ],
        requires_medical_attention=True,
    )
