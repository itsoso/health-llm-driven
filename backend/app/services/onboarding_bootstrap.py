"""Onboarding bootstrap for the first Health OS operating loop."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.health_problem import HealthProblem
from app.models.health_program import HealthProgram
from app.models.user_profile import UserProfile
from app.services.daily_operating_plan import build_daily_operating_plan
from app.services.health_problem_service import serialize_problem
from app.services.health_program_service import serialize_program


_GOAL_CONFIG: dict[str, dict[str, Any]] = {
    "sleep": {
        "problem_name": "睡眠与恢复目标",
        "program_name": "睡眠与恢复 8 周项目",
        "program_type": "sleep",
        "primary_metrics": ["sleep_score", "hrv"],
        "target": {"sleep_score": "increase", "hrv": "increase_or_stabilize"},
        "follow_up": {"cadence": "7 天后复盘", "what_to_check": "睡眠评分、HRV、白天精力"},
    },
    "hrv": {
        "problem_name": "恢复能力目标",
        "program_name": "恢复能力 8 周项目",
        "program_type": "recovery_training",
        "primary_metrics": ["hrv", "rhr", "sleep_score"],
        "target": {"hrv": "increase_or_stabilize", "rhr": "stabilize"},
        "follow_up": {"cadence": "7 天后复盘", "what_to_check": "HRV、静息心率、训练 readiness"},
    },
    "blood_pressure": {
        "problem_name": "血压与心代谢目标",
        "program_name": "血压与心代谢 8 周项目",
        "program_type": "metabolic",
        "primary_metrics": ["systolic_bp", "diastolic_bp"],
        "target": {"systolic_bp": "decrease_if_elevated", "diastolic_bp": "decrease_if_elevated"},
        "follow_up": {"cadence": "7 天后复盘", "what_to_check": "家庭血压均值、钠摄入、活动量"},
    },
    "rhinitis": {
        "problem_name": "鼻炎与呼吸舒适目标",
        "program_name": "鼻炎与呼吸 8 周项目",
        "program_type": "checkup",
        "primary_metrics": ["rhinitis_symptom_score", "sleep_score"],
        "target": {"rhinitis_symptom_score": "decrease", "sleep_score": "increase_or_stabilize"},
        "follow_up": {"cadence": "7 天后复盘", "what_to_check": "鼻塞、喷嚏、睡眠受影响程度"},
    },
    "general": {
        "problem_name": "初始健康运行目标",
        "program_name": "初始健康运行 8 周项目",
        "program_type": "metabolic",
        "primary_metrics": ["weight", "waist_cm", "sleep_score"],
        "target": {"weight": "stabilize_or_decrease_if_needed", "sleep_score": "increase_or_stabilize"},
        "follow_up": {"cadence": "7 天后复盘", "what_to_check": "体重、腰围、睡眠和行动完成率"},
    },
}
_GOAL_CONFIG["weight_loss"] = {
    **_GOAL_CONFIG["general"],
    "problem_name": "体重与代谢目标",
    "program_name": "体重与代谢 8 周项目",
    "primary_metrics": ["weight", "waist_cm"],
    "target": {"weight": "decrease_gradually", "waist_cm": "decrease_gradually"},
}
_GOAL_CONFIG["glucose"] = {
    **_GOAL_CONFIG["general"],
    "problem_name": "血糖与代谢目标",
    "program_name": "血糖与代谢 8 周项目",
    "primary_metrics": ["glucose_fasting", "glucose_hba1c", "waist_cm"],
    "target": {"glucose_fasting": "stabilize_or_decrease_if_elevated", "waist_cm": "decrease_if_elevated"},
}


def ensure_initial_health_loop(db: Session, user_id: int) -> dict[str, Any]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    primary_goal = getattr(profile, "primary_goal", None) or "general"
    config = _GOAL_CONFIG.get(primary_goal, _GOAL_CONFIG["general"])
    problem, problem_created = _get_or_create_problem(db, user_id, config)
    program, program_created = _get_or_create_program(db, user_id, problem.id, config)
    plan = build_daily_operating_plan(db, user_id, plan_date=date.today())

    return {
        "primary_goal": primary_goal,
        "problem": {**serialize_problem(problem), "created": problem_created},
        "program": {**serialize_program(program), "created": program_created},
        "daily_plan": {
            "id": plan.get("id"),
            "created": True,
            "plan_date": plan.get("plan_date"),
            "action_count": len(plan.get("actions") or []),
        },
        "claim_boundary": "初始闭环来自用户目标和已有数据,不构成诊断或治疗建议。",
    }


def _get_or_create_problem(
    db: Session,
    user_id: int,
    config: dict[str, Any],
) -> tuple[HealthProblem, bool]:
    existing = (
        db.query(HealthProblem)
        .filter(
            HealthProblem.user_id == user_id,
            HealthProblem.name == config["problem_name"],
            HealthProblem.status != "resolved",
        )
        .first()
    )
    if existing:
        return existing, False

    next_due = date.today() + timedelta(days=7)
    problem = HealthProblem(
        user_id=user_id,
        name=config["problem_name"],
        risk_level="P2",
        status="monitoring",
        diagnosis={"source": "onboarding_primary_goal", "primary_goal": config["problem_name"]},
        red_lines=[],
        follow_up={**config["follow_up"], "next_due": next_due.isoformat()},
        escalation_path="出现红线症状或指标明显异常时,转医生/专科评估。",
        evidence_tier="D",
        notes="Onboarding 生成的初始监测目标,用于启动 Health OS 闭环。",
    )
    db.add(problem)
    db.commit()
    db.refresh(problem)
    return problem, True


def _get_or_create_program(
    db: Session,
    user_id: int,
    problem_id: int,
    config: dict[str, Any],
) -> tuple[HealthProgram, bool]:
    existing = (
        db.query(HealthProgram)
        .filter(
            HealthProgram.user_id == user_id,
            HealthProgram.name == config["program_name"],
            HealthProgram.status == "active",
        )
        .first()
    )
    if existing:
        return existing, False

    today = date.today()
    program = HealthProgram(
        user_id=user_id,
        name=config["program_name"],
        program_type=config["program_type"],
        status="active",
        problem_id=problem_id,
        primary_metrics=config["primary_metrics"],
        secondary_metrics=[],
        baseline={},
        target=config["target"],
        latest={},
        started_on=today,
        target_end_on=today + timedelta(days=56),
        notes="Onboarding 生成的初始项目;后续由 ProgramTemplate 和 Review 细化。",
    )
    db.add(program)
    db.commit()
    db.refresh(program)
    return program, True
