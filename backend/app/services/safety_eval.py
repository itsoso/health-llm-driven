# -*- coding: utf-8 -*-
"""安全 eval —— red-team 安全规则层覆盖(Next Horizon Tier 3)。

51 条确定性规则是已知风险的护栏。本模块用一组**对抗性危险场景**做端到端回归 gate:
危险 Twin 状态 → evaluate_rules 必须命中预期严重度的告警。任一漏网 = 覆盖回归。

确定性、CI 友好(无 LLM)。注:这 red-team 的是**规则层**;LLM 合成层自由文本的
对抗 eval 需 LLM 评测,属未来工作(不在此假装覆盖)。
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.safety_guardian.engine import evaluate_rules_with_status
from app.agents.safety_guardian.schema import Severity
from app.twin.schema import HealthTwin, LabsContext, PhysiologicalState, TwinMeta


def _twin(**kw) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    if "labs" in kw:
        t.labs = kw["labs"]
    if "physiological" in kw:
        t.physiological = kw["physiological"]
    return t


# 每个场景:危险态 + 期望最低严重度(规则必须至少报到这个级别)
# 阈值与 rules/vitals.py 对齐(BP≥180/120=HIGH 的单次严重读数,140/90=HIGH,spo2 低=CRITICAL)
_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "severe_bp_reading",
        "twin": lambda: _twin(labs=LabsContext(blood_pressure_systolic=185, blood_pressure_diastolic=125)),
        "min_severity": Severity.HIGH,
        "desc": "单次血压严重升高 BP≥180/120 必须触发 HIGH 复测与症状分流",
    },
    {
        "name": "stage2_hypertension",
        "twin": lambda: _twin(labs=LabsContext(blood_pressure_systolic=155, blood_pressure_diastolic=95)),
        "min_severity": Severity.HIGH,
        "desc": "2 级高血压 140-179/90-119 必须 ≥HIGH",
    },
    {
        "name": "severe_hypoxia",
        "twin": lambda: _twin(physiological=PhysiologicalState(spo2_avg=85.0)),
        "min_severity": Severity.HIGH,
        "desc": "严重低氧 SpO2 85 必须 ≥HIGH",
    },
]


def run_safety_eval() -> dict[str, Any]:
    """跑对抗场景集,返回 red-team 结果(全过=规则覆盖无回归)。"""
    results = []
    for sc in _SCENARIOS:
        twin = sc["twin"]()
        alerts, failed = evaluate_rules_with_status(twin)
        max_sev = max((int(a.severity) for a in alerts), default=-1)
        # fail-loud:规则崩了被 per-rule try/except 跳过 → 期望告警可能缺失。该场景必须算
        # **未通过**(failed>0 视为覆盖回归),绝不让某条规则崩成「漏报却 pass」假绿灯。
        passed = max_sev >= int(sc["min_severity"]) and failed == 0
        results.append({
            "name": sc["name"],
            "desc": sc["desc"],
            "passed": passed,
            "expected_min_severity": int(sc["min_severity"]),
            "max_severity_found": max_sev,
            "failed_rule_count": failed,
            "alerts": [a.rule_id for a in alerts],
        })
    passed_n = sum(1 for r in results if r["passed"])
    total = len(results)
    return {
        "scenarios": results,
        "passed": passed_n,
        "total": total,
        "pass_rate": round(passed_n / total, 3) if total else None,
        "note": "red-team 确定性规则层覆盖;LLM 合成层 red-team 需 LLM 评测(未覆盖)。",
    }
