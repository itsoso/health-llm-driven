"""R16 Phase 1 —— 结局指标「诚实置信度 + 治理合规」渲染权威(唯一出口)。

**修现网 R4 泄漏**:`api/intervention_cycles._outcome_dict` 与 `daily_operating_plan` 此前给
**处方/激素指标**(LDL/糖化/收缩压 …)直接外吐裸 `status`(improving/worsening/met)+ 裸
`delta_pct`,无置信度、无 display_label、无临床门 —— 对被并行处方药混杂的指标下「类裁决」措辞,
违 R4(见 memory feedback_personalized_effect_no_prescription_verdict)。

本模块是**所有结局读数的单一渲染契约**(后续 R16 去噪/洗脱/交叉/对账各阶段都经此出口,不再各自渲染):
- **门控指标**(`_is_clinician_gated_code`:处方/激素,子串兜底 fail-closed)→ **中和裸裁决**:
  status 置 `clinician_review`、delta/delta_pct/direction 一律 None、`requires_clinician=True`、
  display_label「需医生评估」。绝不让 improving/worsening/met 或变化幅度外吐(防反推效应)。
- **非门控指标**(体重/HRV/ALT 等非处方)→ 保留描述式 status + 复用 producer 写好的 RCV
  置信度(`om.confidence` low/moderate/high)+ DISPLAY_LABELS 描述式 label。
- **每条**带 `confidence_tier` + `attribution='temporal_association_not_causation'`(相关非因果)。

**只降不升**:本层只能中和/降级,绝不把任何指标升成更强裁决(镜像 cross-source caveat 不变量)。
复用既有合规件(不重造):`_is_clinician_gated_code` / `classify_change`(经 om.confidence)/
`DISPLAY_LABELS` / `metric_display_name`。**基因无关**:本模块不 import 任何 genetic/twin.genetic。
"""
from __future__ import annotations

from typing import Any, Dict

from app.services.personal_models.intervention_priors import _is_clinician_gated_code
from app.services.personal_models.treatment_effect import (
    DISPLAY_LABELS,
    metric_display_name,
)

ATTRIBUTION = "temporal_association_not_causation"
# R16 P3:洗脱期内归因待定的描述式 label(非裁决,只说「暂不归因于当前干预」)。
_WASHOUT_LABEL = "归因待定:前序干预洗脱期内,本次变化暂不归因于当前干预"

# 非门控 status(producer _metric_status 产出:pending/improving/worsening/flat/met)→ 描述式 verdict。
_STATUS_TO_VERDICT = {
    "improving": "improved_in_cycle",
    "met": "improved_in_cycle",
    "worsening": "worsened_in_cycle",
    "flat": "inconclusive",
    "pending": "insufficient_data",
}


def render_outcome_metric(om: Any) -> Dict[str, Any]:
    """把一条 OutcomeMetric(或同形 duck-typed 对象)渲染成治理合规读数。

    门控 → 中和裸裁决 + clinician_review;非门控 → 描述式 + RCV 置信度。一律带相关非因果。
    """
    metric_code = getattr(om, "metric_code", None)
    gated = _is_clinician_gated_code(metric_code or "")
    # R16 P3:跨周期洗脱期归因(washout_pending=前序干预残留未清,本次变化暂不归因于当前干预)。
    attribution_state = getattr(om, "attribution_state", None) or "attributable"
    washout = attribution_state == "washout_pending"

    # 原始测量值是事实(用户自己的数据),非裁决 —— 保留;但「变化幅度/方向/裁决」对门控指标中和。
    out: Dict[str, Any] = {
        "metric_code": metric_code,
        "display": metric_display_name(metric_code) if metric_code else None,
        "unit": getattr(om, "unit", None),
        "baseline_value": getattr(om, "baseline_value", None),
        "target_value": getattr(om, "target_value", None),
        "latest_value": getattr(om, "latest_value", None),
        "requires_clinician": gated,
        "attribution": ATTRIBUTION,
        "attribution_state": attribution_state,
    }

    if gated:
        out.update({
            "status": "clinician_review",
            "delta": None,
            "delta_pct": None,
            "direction": None,
            "confidence_tier": "clinician_review",
            "display_label": DISPLAY_LABELS["clinician_review"],
        })
        return out

    status = getattr(om, "status", None) or "pending"
    verdict = _STATUS_TO_VERDICT.get(status, "inconclusive")
    tier = getattr(om, "confidence", None) or "low"
    if verdict == "insufficient_data":
        tier = "low"  # 数据不足绝不给非低置信度
    # P3 demote-only:洗脱期内 → 不把变化自信归因于当前干预(措辞改归因待定 + 置信度封 low)。
    if washout:
        out.update({
            "status": status,
            "delta": getattr(om, "delta", None),
            "delta_pct": getattr(om, "delta_pct", None),
            "direction": getattr(om, "direction", None),
            "confidence_tier": "low",
            "display_label": _WASHOUT_LABEL,
        })
        return out
    out.update({
        "status": status,
        "delta": getattr(om, "delta", None),
        "delta_pct": getattr(om, "delta_pct", None),
        "direction": getattr(om, "direction", None),
        "confidence_tier": tier,
        "display_label": DISPLAY_LABELS[verdict],
    })
    return out
