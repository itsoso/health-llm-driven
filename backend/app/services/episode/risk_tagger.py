"""Risk Tagger — 确定性规则打 L0-L4 标签, 不依赖 LLM.

v3 原则: Safety as cross-cutting concern, L4 强制熔断到 emergency template.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Literal

RiskLevel = Literal["L0", "L1", "L2", "L3", "L4"]


# L4 红旗 — 任何一条命中直接熔断.
RED_FLAG_SYMPTOMS = {
    "chest_pain", "severe_chest_pain", "syncope", "fainting",
    "severe_dyspnea", "severe_breathlessness",
    "confusion", "stroke_signs", "slurred_speech",
    "severe_headache_sudden",
}


@dataclass
class RiskAssessment:
    level: RiskLevel
    flags: List[str] = field(default_factory=list)
    reason: str = ""


def assess_run_episode(context: Dict[str, Any]) -> RiskAssessment:
    """跑步 Episode 的风险判定.

    输入 context 结构:
      symptoms: list[str]
      weather: {temperature_c, ...}
      sleep_prior_h: float
      acwr: float
      resting_hr_delta: float (相对 baseline)
    """
    flags: List[str] = []

    # L4 — 红旗症状
    reported_symptoms = {s.lower() for s in context.get("symptoms", []) if isinstance(s, str)}
    hit_redflags = reported_symptoms & RED_FLAG_SYMPTOMS
    if hit_redflags:
        return RiskAssessment(
            level="L4",
            flags=[f"redflag:{s}" for s in hit_redflags],
            reason="急性症状 — 熔断到 emergency template",
        )

    # L3 — 中重度信号
    if context.get("chest_discomfort"):
        flags.append("chest_discomfort")
        return RiskAssessment(level="L3", flags=flags, reason="胸部不适 — 建议就医")

    # L2 — 观察型 (疼痛, 但还没到就医)
    pain_score = context.get("pain_score")
    if isinstance(pain_score, (int, float)) and pain_score >= 5:
        flags.append(f"pain_{int(pain_score)}")
        return RiskAssessment(level="L2", flags=flags, reason="中度疼痛 — 仅观察, 不诊断")

    # L1 — 训练负荷偏高 / 睡眠不足 / 高温
    acwr = context.get("acwr")
    if isinstance(acwr, (int, float)) and acwr > 1.5:
        flags.append(f"acwr_{acwr:.2f}")
    sleep_h = context.get("sleep_prior_h")
    if isinstance(sleep_h, (int, float)) and sleep_h < 6.0:
        flags.append(f"sleep_short_{sleep_h:.1f}h")
    temp = (context.get("weather") or {}).get("temperature_c")
    if isinstance(temp, (int, float)) and temp >= 30:
        flags.append(f"heat_{temp:.0f}C")

    if flags:
        return RiskAssessment(level="L1", flags=flags, reason="存在风险标签但仍在 wellness 区")

    return RiskAssessment(level="L0", flags=[], reason="正常恢复场景")
