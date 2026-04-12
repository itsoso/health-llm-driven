"""
Specialist 接口 + 内置 specialist 实现。

每个 specialist 实现两个方法：
- applies_to(intent, twin) -> bool    决定是否参与本次调度
- run(twin, context) -> SpecialistFinding   产生结构化输出
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Protocol

from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# ─────────────────────────── 协议 ───────────────────────────


class Specialist(Protocol):
    """每个专家 agent 需要满足这个接口。"""

    name: str
    category: str

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        ...

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        ...


# ─────────────────────────── SafetyGuardian Adapter ─────────


class SafetyGuardianSpecialist:
    """把 Safety Guardian 包装为 Orchestrator 可调用的 specialist。"""

    name = "safety_guardian"
    category = "safety"

    # 涉及安全/用药/基因/化验的查询时触发
    TRIGGER_KEYWORDS = {
        "药", "药物", "相互作用", "能吃", "要不要停",
        "补剂", "能不能", "风险", "安全",
        "化验", "血压", "血糖", "hrv", "spo2",
        "基因", "cyp", "mthfr", "aldh2",
        "告警", "警报", "分析",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        # 1. 显式分类命中
        if "safety" in intent.categories:
            return True
        # 2. 关键字匹配
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 3. 如果 Twin 上已经有高风险信号（BP/Glu/药物/基因），兜底参与
        if twin.labs.blood_pressure_systolic and twin.labs.blood_pressure_systolic >= 140:
            return True
        if twin.medication.has_any and twin.genetic.has_profile:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            from app.agents.safety_guardian import evaluate_safety

            report = evaluate_safety(twin)

            findings: List[Dict[str, Any]] = []
            for a in report.alerts:
                findings.append(
                    {
                        "rule_id": a.rule_id,
                        "category": a.category,
                        "severity": int(a.severity),
                        "severity_label": a.severity.label_zh,
                        "title": a.title,
                        "message": a.message,
                        "action": a.action,
                        "requires_medical_attention": a.requires_medical_attention,
                    }
                )

            # 概括
            if report.critical_count:
                summary = f"{report.critical_count} 条紧急告警，需要立即关注"
            elif report.high_count:
                summary = f"{report.high_count} 条警告级告警"
            elif report.medium_count:
                summary = f"{report.medium_count} 条中等关注项"
            elif findings:
                summary = f"{len(findings)} 条一般提示，无紧急问题"
            else:
                summary = "当前无安全告警"

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "total": len(findings),
                    "critical": report.critical_count,
                    "high": report.high_count,
                    "medium": report.medium_count,
                    "rules_evaluated": report.total_rules_evaluated,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[specialist.safety_guardian] 执行失败: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"安全检查失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


# ─────────────────────────── Registry ────────────────────────

# Lazy import 避免循环依赖（specialists 包里的 agent 也可能引用 orchestrator.schema）
def _build_registry() -> List[Specialist]:
    from app.agents.chronic_specialists import (
        HypertensionSpecialist,
        MetabolicSpecialist,
        RhinitisSpecialist,
    )
    from app.agents.fuel_strategist import FuelStrategistSpecialist
    from app.agents.knowledge_librarian.librarian import KnowledgeLibrarianSpecialist
    from app.agents.longitudinal_analyst.analyst import LongitudinalAnalystSpecialist
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist
    from app.agents.movement_coach import MovementCoachSpecialist
    from app.agents.recovery_coach import RecoveryCoachSpecialist

    return [
        SafetyGuardianSpecialist(),            # 安全优先
        RecoveryCoachSpecialist(),             # 在 MovementCoach 之前
        FuelStrategistSpecialist(),
        MovementCoachSpecialist(),             # 从 context 读 readiness_zone
        MentalHealthCompanionSpecialist(),     # Tier 5 隐私
        # 慢病专科
        HypertensionSpecialist(),
        MetabolicSpecialist(),
        RhinitisSpecialist(),
        # 知识 + 长期分析
        KnowledgeLibrarianSpecialist(),
        LongitudinalAnalystSpecialist(),
    ]


_SPECIALISTS: List[Specialist] = _build_registry()


def all_specialists() -> List[Specialist]:
    return list(_SPECIALISTS)


def get_specialist(name: str) -> Specialist | None:
    for s in _SPECIALISTS:
        if s.name == name:
            return s
    return None
