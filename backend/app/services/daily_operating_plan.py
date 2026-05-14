"""Daily Operating Plan v0 deterministic planner."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.daily_operating_plan import DailyOperatingPlan
from app.twin import build_twin


def _bp_text(twin) -> str | None:
    s = twin.labs.blood_pressure_systolic
    d = twin.labs.blood_pressure_diastolic
    if s and d:
        return f"{s}/{d}"
    return None


def _action(domain: str, title: str, why: str, *, when: str = "today",
            metric_key: str | None = None, target_value: str | None = None,
            evidence_level: str = "medium") -> Dict[str, Any]:
    return {
        "domain": domain,
        "title": title,
        "why": why,
        "when": when,
        "metric_key": metric_key,
        "target_value": target_value,
        "evidence_level": evidence_level,
    }


def _active_interventions(db: Session, user_id: int) -> List[Dict[str, Any]]:
    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.status == "active",
            ActionCard.user_decision.in_(["accepted", "adjusted"]),
        )
        .order_by(desc(ActionCard.priority), desc(ActionCard.created_at))
        .limit(3)
        .all()
    )
    return [
        _action(
            "intervention",
            c.title,
            "这是你已接受的行动, Daily Plan 会优先保留并等待验证。",
            when="in_progress",
            metric_key=c.metric_key,
            target_value=c.target_value,
            evidence_level=c.evidence_level or "medium",
        ) | {"source_card_id": c.id, "check_back_date": c.check_back_date.isoformat() if c.check_back_date else None}
        for c in cards
    ]


def build_daily_operating_plan(db: Session, user_id: int, plan_date: date | None = None) -> Dict[str, Any]:
    """构建并缓存当天 Daily Operating Plan.

    v0 使用 deterministic 规则, 先把产品对象稳定下来; 后续可在同一响应合同下接 LLM planner.
    """
    plan_date = plan_date or date.today()
    twin = build_twin(db, user_id, use_cache=False)
    body = twin.body_composition
    bp = _bp_text(twin)

    protein_target = round((body.weight_kg or 70) * 1.6)
    actions: List[Dict[str, Any]] = []

    actions.append(_action(
        "measurement",
        "晨起记录体重和腰围",
        "体重 + 腰围比单看 BMI 更能反映代谢改善, 同一时间测量噪声更低。",
        when="morning",
        metric_key="waist_cm",
        target_value="trend_down",
        evidence_level="high",
    ))
    actions.append(_action(
        "nutrition",
        f"今天蛋白质目标 {protein_target}g",
        "减重阶段先保住蛋白和肌肉量, 再看热量缺口。",
        when="meals",
        metric_key="calories_intake",
        target_value=str(protein_target),
    ))

    readiness = twin.physiological.training_readiness_score
    if readiness is not None and readiness < 50:
        actions.append(_action(
            "movement",
            "低强度 Zone 2 或主动恢复 30 分钟",
            "训练准备度偏低时不堆高强度, 先保连续性和恢复。",
            when="afternoon",
            metric_key="rhr",
            target_value="stable",
        ))
    else:
        actions.append(_action(
            "movement",
            "累计 35-45 分钟中等强度活动",
            "对齐每周 150 分钟中等强度活动的代谢健康目标。",
            when="daytime",
            metric_key="custom",
            target_value="150min_weekly",
            evidence_level="high",
        ))

    actions.append(_action(
        "sleep",
        "睡前 3 小时停止正餐",
        "晚餐过晚会干扰睡眠和第二天恢复, 也会影响体重趋势判断。",
        when="evening",
        metric_key="sleep_score",
        target_value="trend_up",
    ))

    actions.extend(_active_interventions(db, user_id))
    actions = actions[:5]

    state_summary = {
        "weight_kg": body.weight_kg,
        "waist_cm": body.waist_cm,
        "bmi": body.bmi,
        "central_obesity_flag": body.central_obesity_flag,
        "blood_pressure": bp,
        "sleep_score": twin.physiological.sleep_score_latest,
        "training_readiness_score": readiness,
        "data_sources": twin.meta.data_sources,
    }
    verification_metrics = [
        m for m in ["weight", "waist_cm", "systolic_bp", "sleep_score"]
        if (
            (m == "weight" and body.weight_kg is not None)
            or (m == "waist_cm" and body.waist_cm is not None)
            or (m == "systolic_bp" and twin.labs.blood_pressure_systolic is not None)
            or (m == "sleep_score" and twin.physiological.sleep_score_latest is not None)
        )
    ]
    payload = {
        "id": None,
        "user_id": user_id,
        "plan_date": plan_date.isoformat(),
        "primary_goal": "metabolic_health",
        "status": "active",
        "state_summary": state_summary,
        "actions": actions,
        "nutrition_targets": {
            "protein_g": protein_target,
            "meal_timing": "finish_dinner_3h_before_bed",
        },
        "movement_targets": {
            "weekly_moderate_minutes": 150,
            "strength_days": 2,
        },
        "sleep_targets": {
            "duration_hours": 7,
            "dinner_cutoff_hours_before_bed": 3,
        },
        "measurements": {
            "weight": "daily_morning",
            "waist": "daily_morning",
            "bp": "if_available_morning_evening",
        },
        "doctor_escalation": {
            "needed": bool(twin.labs.blood_pressure_systolic and twin.labs.blood_pressure_systolic >= 160),
            "reason": "血压达到高风险阈值" if twin.labs.blood_pressure_systolic and twin.labs.blood_pressure_systolic >= 160 else None,
            "suggested_specialty": "心内科" if twin.labs.blood_pressure_systolic and twin.labs.blood_pressure_systolic >= 160 else None,
        },
        "verification": {
            "window_days": 7,
            "metrics": verification_metrics or ["weight", "waist_cm"],
            "check_back_date": (plan_date + timedelta(days=7)).isoformat(),
        },
    }

    existing = (
        db.query(DailyOperatingPlan)
        .filter(DailyOperatingPlan.user_id == user_id, DailyOperatingPlan.plan_date == plan_date)
        .first()
    )
    if existing:
        existing.state_summary = payload["state_summary"]
        existing.actions = payload["actions"]
        existing.nutrition_targets = payload["nutrition_targets"]
        existing.movement_targets = payload["movement_targets"]
        existing.sleep_targets = payload["sleep_targets"]
        existing.measurements = payload["measurements"]
        existing.doctor_escalation = payload["doctor_escalation"]
        existing.verification = payload["verification"]
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        payload["id"] = existing.id
        return payload

    row = DailyOperatingPlan(
        user_id=user_id,
        plan_date=plan_date,
        primary_goal=payload["primary_goal"],
        status=payload["status"],
        state_summary=payload["state_summary"],
        actions=payload["actions"],
        nutrition_targets=payload["nutrition_targets"],
        movement_targets=payload["movement_targets"],
        sleep_targets=payload["sleep_targets"],
        measurements=payload["measurements"],
        doctor_escalation=payload["doctor_escalation"],
        verification=payload["verification"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    payload["id"] = row.id
    return payload
