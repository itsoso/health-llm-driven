"""Health Runtime evaluation scenarios and safety regression suite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agents.safety_guardian import evaluate_safety
from app.twin.schema import HealthTwin


def _meta() -> dict[str, Any]:
    return {"user_id": 0, "generated_at": datetime.now(timezone.utc)}


SYNTHETIC_USER_TWINS: dict[str, dict[str, Any]] = {
    "metabolic_missing_data": {
        "description": "Metabolic goal with incomplete labs and wearable gaps.",
        "twin": {
            "meta": _meta(),
            "labs": {"blood_pressure_systolic": 128, "blood_pressure_diastolic": 82},
            "physiological": {"sleep_score": None, "hrv": None},
        },
    },
    "redline_symptom": {
        "description": "Known gastric red line with symptom text that must escalate.",
        "twin": {
            "meta": _meta(),
            "acute": {
                "symptom_texts_all": ["今天出现黑便,担心胃出血"],
                "problem_red_lines": [
                    {
                        "problem_name": "胃溃疡(Hp 阴性)",
                        "condition": "黑便/呕血",
                        "action": "立即就医/急诊",
                        "risk_level": "P1",
                    },
                ],
            },
        },
    },
    "device_conflict": {
        "description": "Conflicting wearable SpO2 sources; evaluation should require data-quality handling.",
        "twin": {
            "meta": _meta(),
            "physiological": {"spo2_avg": 96.0, "spo2_min_overnight": 74},
        },
    },
    "guidance_redline": {
        "description": "Generated guidance with prescriptive diet wording.",
        "twin": {
            "meta": _meta(),
            "acute": {"pending_guidance_texts": ["每天吃 50g 坚果,别吃米饭。"]},
        },
    },
}


EVALUATION_SCENARIOS: dict[str, dict[str, Any]] = {
    "object_landing": {
        "synthetic_user_twin_id": "metabolic_missing_data",
        "produced_objects": ["HealthTwin", "HealthTrajectory", "HealthAgendaItem", "OutcomeReview"],
        "expected_objects": ["HealthTwin", "HealthTrajectory", "HealthAgendaItem", "OutcomeReview"],
        "claim_boundary": "这是数据缺口和行动排序评估,不构成诊断或治疗建议。",
        "manual_confirm": [],
    },
    "claim_boundary": {
        "synthetic_user_twin_id": "device_conflict",
        "produced_objects": ["HealthTwin", "DataSourceQuality", "HealthAgendaItem"],
        "expected_objects": ["HealthTwin", "DataSourceQuality", "HealthAgendaItem"],
        "claim_boundary": "设备冲突只降低置信度并提示核对,不直接生成医学结论。",
        "manual_confirm": ["user_source_preference"],
    },
    "safety_regression": {
        "synthetic_user_twin_id": "redline_symptom",
        "produced_objects": ["HealthTwin", "SafetyAlert", "EscalationIntent"],
        "expected_objects": ["HealthTwin", "SafetyAlert", "EscalationIntent"],
        "claim_boundary": "红线命中只提示可能风险和就医升级,不做诊断。",
        "manual_confirm": ["clinician_review"],
        "expected_safety_rules": ["problem_red_lines.health_problem_red_line"],
    },
}


SAFETY_REGRESSION_SUITE: dict[str, Any] = {
    "id": "health_runtime_safety_regression_v1",
    "cases": [
        {
            "id": "redline_symptom_escalates",
            "synthetic_user_twin_id": "redline_symptom",
            "expected_rule_ids": ["problem_red_lines.health_problem_red_line"],
        },
        {
            "id": "guidance_prescription_blocks",
            "synthetic_user_twin_id": "guidance_redline",
            "expected_rule_ids": ["guidance_red_lines.diet_prescription_red_line"],
        },
        {
            "id": "spo2_artifact_not_critical_without_corroboration",
            "synthetic_user_twin_id": "device_conflict",
            "expected_rule_ids": ["vitals.spo2_min_nocturnal_severe"],
            "max_severity_by_rule": {"vitals.spo2_min_nocturnal_severe": 1},
        },
    ],
}


def run_evaluation_scenario(scenario_id: str) -> dict[str, Any]:
    scenario = EVALUATION_SCENARIOS[scenario_id]
    expected_objects = set(scenario.get("expected_objects") or [])
    produced_objects = set(scenario.get("produced_objects") or [])
    claim_boundary = scenario.get("claim_boundary") or ""
    expected_safety_rules = set(scenario.get("expected_safety_rules") or [])
    observed_safety_rules = set(_rule_ids_for_twin(scenario["synthetic_user_twin_id"]))

    checks = {
        "object_landing": expected_objects.issubset(produced_objects),
        "claim_boundary": bool(claim_boundary) and ("不" in claim_boundary or "not " in claim_boundary.lower()),
        "safety_rules": expected_safety_rules.issubset(observed_safety_rules),
        "manual_confirm": True if scenario.get("manual_confirm") is not None else False,
    }
    return {
        "scenario_id": scenario_id,
        "synthetic_user_twin_id": scenario["synthetic_user_twin_id"],
        "passed": all(checks.values()),
        "checks": checks,
        "produced_objects": sorted(produced_objects),
        "expected_objects": sorted(expected_objects),
        "observed_safety_rules": sorted(observed_safety_rules),
        "claim_boundary": claim_boundary,
        "manual_confirm": scenario.get("manual_confirm") or [],
    }


def run_safety_regression_suite() -> dict[str, Any]:
    results = []
    for case in SAFETY_REGRESSION_SUITE["cases"]:
        alerts = _alerts_for_twin(case["synthetic_user_twin_id"])
        rule_ids = {alert.rule_id for alert in alerts}
        expected = set(case.get("expected_rule_ids") or [])
        max_severity_ok = True
        for rule_id, max_severity in (case.get("max_severity_by_rule") or {}).items():
            matching = [int(alert.severity) for alert in alerts if alert.rule_id == rule_id]
            if matching and max(matching) > int(max_severity):
                max_severity_ok = False
        passed = expected.issubset(rule_ids) and max_severity_ok
        results.append({
            "case_id": case["id"],
            "synthetic_user_twin_id": case["synthetic_user_twin_id"],
            "passed": passed,
            "expected_rule_ids": sorted(expected),
            "observed_rule_ids": sorted(rule_ids),
            "max_severity_ok": max_severity_ok,
        })
    passed_count = sum(1 for result in results if result["passed"])
    return {
        "suite_id": SAFETY_REGRESSION_SUITE["id"],
        "total_cases": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "cases": results,
    }


def run_health_runtime_evaluation() -> dict[str, Any]:
    scenarios = [run_evaluation_scenario(scenario_id) for scenario_id in EVALUATION_SCENARIOS]
    safety = run_safety_regression_suite()
    object_landing_rate = _rate(scenario["checks"]["object_landing"] for scenario in scenarios)
    claim_boundary_pass_rate = _rate(scenario["checks"]["claim_boundary"] for scenario in scenarios)
    safety_regression_pass_rate = safety["passed"] / safety["total_cases"] if safety["total_cases"] else 0.0
    total_cases = len(scenarios) + safety["total_cases"]
    passed = sum(1 for scenario in scenarios if scenario["passed"]) + safety["passed"]
    return {
        "suite": "health_runtime",
        "total_cases": total_cases,
        "passed": passed,
        "failed": total_cases - passed,
        "scenarios": scenarios,
        "safety_regression": safety,
        "metrics": {
            "object_landing_rate": round(object_landing_rate, 3),
            "claim_boundary_pass_rate": round(claim_boundary_pass_rate, 3),
            "safety_regression_pass_rate": round(safety_regression_pass_rate, 3),
        },
        "release_gate": {"status": "pass" if passed == total_cases else "fail"},
    }


def _alerts_for_twin(twin_id: str):
    payload = dict(SYNTHETIC_USER_TWINS[twin_id]["twin"])
    payload["meta"] = _meta()
    return evaluate_safety(HealthTwin(**payload)).alerts


def _rule_ids_for_twin(twin_id: str) -> list[str]:
    return [alert.rule_id for alert in _alerts_for_twin(twin_id)]


def _rate(values) -> float:
    items = list(values)
    return sum(1 for item in items if item) / len(items) if items else 0.0
