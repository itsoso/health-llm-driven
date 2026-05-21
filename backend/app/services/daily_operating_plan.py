"""Daily Operating Plan v0 deterministic planner."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.daily_operating_plan import DailyOperatingPlan
from app.services.advice_guard import AdviceCandidate, AdviceGuardError, guard_and_record_advice
from app.services.personal_evidence_matrix import (
    build_personal_evidence_matrix,
    compact_personal_evidence_matrix,
)
from app.services.measurement_automation import get_measurement_capability_map
from app.twin import build_twin

logger = logging.getLogger(__name__)

_ACUTE_REST_SUPPRESS_TITLES = (
    "跑步",
    "训练",
    "力量",
    "HIIT",
    "间歇",
    "冲刺",
    "配速",
    "长跑",
    "马拉松",
    "举铁",
    "重量",
    "健身",
    "workout",
    "gym",
    "run",
    "jog",
    "strength",
)


def _bp_text(twin) -> str | None:
    s = twin.labs.blood_pressure_systolic
    d = twin.labs.blood_pressure_diastolic
    if s and d:
        return f"{s}/{d}"
    return None


def _normalize_confidence(evidence_level: str | None) -> str:
    if evidence_level in {"high", "medium", "low"}:
        return evidence_level
    if evidence_level == "medical_grade":
        return "high"
    return "medium"


def _action(
    domain: str,
    title: str,
    why: str,
    *,
    action_key: str | None = None,
    when: str = "today",
    metric_key: str | None = None,
    target_value: str | None = None,
    evidence_level: str = "medium",
    evidence_tier: str = "strong_behavioral",
    confidence: str | None = None,
    claim_boundary: str | None = None,
) -> Dict[str, Any]:
    return {
        "action_key": action_key or f"{domain}.{metric_key or title}",
        "domain": domain,
        "title": title,
        "why": why,
        "when": when,
        "metric_key": metric_key,
        "target_value": target_value,
        "evidence_level": evidence_level,
        "evidence_tier": evidence_tier,
        "confidence": confidence or _normalize_confidence(evidence_level),
        "claim_boundary": claim_boundary or "这是健康管理行动建议, 不替代医生诊断、处方或治疗。",
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
            action_key=f"intervention.card.{c.id}",
            when="in_progress",
            metric_key=c.metric_key,
            target_value=c.target_value,
            evidence_level=c.evidence_level or "medium",
            evidence_tier="strong_behavioral",
            confidence=_normalize_confidence(c.evidence_level),
            claim_boundary="这是已接受的行为干预, 不替代医生诊断、处方或治疗。",
        ) | {"source_card_id": c.id, "check_back_date": c.check_back_date.isoformat() if c.check_back_date else None}
        for c in cards
    ]


def _guard_plan_actions(
    db: Session,
    *,
    user_id: int,
    plan_date: date,
    actions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    guarded: List[Dict[str, Any]] = []
    for index, action in enumerate(actions):
        candidate = AdviceCandidate(
            user_id=user_id,
            source="daily_plan",
            source_id=f"daily_plan:{plan_date.isoformat()}:{index}:{action.get('domain', 'unknown')}",
            domain=str(action.get("domain") or ""),
            title=str(action.get("title") or ""),
            body=str(action.get("why") or action.get("title") or ""),
            metric_key=action.get("metric_key"),
            target_value=action.get("target_value"),
            evidence_tier=action.get("evidence_tier"),
            confidence=action.get("confidence"),
            claim_boundary=action.get("claim_boundary"),
            valid_for_date=plan_date,
        )
        try:
            decision = guard_and_record_advice(db, candidate)
        except AdviceGuardError as exc:
            logger.warning("[daily_plan] action blocked by missing advice contract: %s", exc)
            continue
        except SQLAlchemyError as exc:
            db.rollback()
            logger.warning("[daily_plan] advice ledger unavailable, keeping action: %s", exc)
            guarded.append(action)
            continue

        if decision.allowed:
            guarded.append(action)
        else:
            logger.info(
                "[daily_plan] action blocked by AdviceGuard user=%s reason=%s title=%s",
                user_id,
                decision.reason,
                action.get("title"),
            )
    return guarded


def _apply_acute_rest_arbiter(
    *,
    acute_rest: bool,
    actions: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Arbiter v0: safety > acute illness rest overrides training-like interventions.

    目标是避免出现 "暂停训练" 的同时又展示训练/跑步类 intervention 的产品冲突。
    """
    if not acute_rest:
        return actions, []

    kept: List[Dict[str, Any]] = []
    suppressed_keys: List[str] = []
    for action in actions:
        action_key = str(action.get("action_key") or "")
        title = str(action.get("title") or "")
        is_intervention = action_key.startswith("intervention.card.")
        title_lower = title.lower()
        looks_like_training = any(
            (k.lower() in title_lower) if k.isascii() else (k in title)
            for k in _ACUTE_REST_SUPPRESS_TITLES
        )

        if is_intervention and looks_like_training:
            suppressed_keys.append(action_key)
            continue
        kept.append(action)

    notes: List[Dict[str, Any]] = []
    if suppressed_keys:
        notes.append({
            "kind": "suppressed_actions",
            "reason": "acute_rest_from_training",
            "suppressed_action_keys": suppressed_keys,
        })
    return kept, notes


def _lab_anchor_action(reason: str) -> Dict[str, Any]:
    return _action(
        "measurement",
        "补齐近期关键化验锚点",
        "当前缺少新鲜化验锚点，补齐 HbA1c、血脂、尿酸和肝肾功能后，再提高补剂或代谢建议置信度。",
        action_key="measurement.update_lab_anchor",
        when="this_week",
        metric_key="lab_anchor",
        target_value="fresh_lab_panel",
        evidence_level="high",
        evidence_tier="clinical_guideline",
        confidence="high",
        claim_boundary="化验补齐用于健康管理置信度校准，不替代医生诊断、处方或治疗。",
    ) | {"personal_evidence": {"trigger": reason}}


def _recovery_movement_action(*, trigger: str, guardrail: str | None = None) -> Dict[str, Any]:
    why = guardrail or "个人证据矩阵显示恢复信号偏弱，今天不堆高强度，先保连续性和恢复。"
    return _action(
        "movement",
        "低强度 Zone 2 或主动恢复 30 分钟",
        why,
        action_key="movement.zone2_recovery",
        when="afternoon",
        metric_key="rhr",
        target_value="stable",
        evidence_tier="wearable_proxy",
        confidence="medium",
        claim_boundary="训练准备度和恢复信号是可穿戴代理指标, 不替代医生对疲劳、感染或损伤的诊断。",
    ) | {"personal_evidence": {"trigger": trigger}}


def build_daily_operating_plan(db: Session, user_id: int, plan_date: date | None = None) -> Dict[str, Any]:
    """构建并缓存当天 Daily Operating Plan.

    v0 使用 deterministic 规则, 先把产品对象稳定下来; 后续可在同一响应合同下接 LLM planner.
    """
    plan_date = plan_date or date.today()
    twin = build_twin(db, user_id, use_cache=False)
    personal_matrix = build_personal_evidence_matrix(twin)
    compact_matrix = compact_personal_evidence_matrix(personal_matrix)
    planner_flags = set(compact_matrix["planner_flags"])
    body = twin.body_composition
    bp = _bp_text(twin)
    acute = getattr(twin, "acute", None)
    acute_rest = bool(getattr(acute, "should_rest_from_training", False))
    acute_guardrail = getattr(acute, "training_guardrail", None) or "当前有急性不适/生病状态，今天不要求完成运动目标，优先休息、补水和睡眠。"

    protein_target = round((body.weight_kg or 70) * 1.6)
    actions: List[Dict[str, Any]] = []

    actions.append(_action(
        "measurement",
        "晨起记录体重和腰围",
        "体重 + 腰围比单看 BMI 更能反映代谢改善, 同一时间测量噪声更低。",
        action_key="measurement.weight_waist_morning",
        when="morning",
        metric_key="waist_cm",
        target_value="trend_down",
        evidence_level="high",
        evidence_tier="clinical_guideline",
        confidence="high",
        claim_boundary="体重和腰围用于代谢趋势追踪, 不替代医生诊断或影像/实验室检查。",
    ))

    if "lab_anchor_missing" in planner_flags:
        actions.append(_lab_anchor_action("lab_anchor_missing"))
    elif "lab_anchor_stale" in planner_flags:
        actions.append(_lab_anchor_action("lab_anchor_stale"))

    actions.append(_action(
        "nutrition",
        f"今天蛋白质目标 {protein_target}g",
        "减重阶段先保住蛋白和肌肉量, 再看热量缺口。",
        action_key="nutrition.protein_target",
        when="meals",
        metric_key="calories_intake",
        target_value=str(protein_target),
        evidence_tier="strong_behavioral",
        confidence="medium",
        claim_boundary="蛋白目标按体重估算, 不替代医生或营养师针对肾病、孕产等特殊情况的建议。",
    ))

    readiness = twin.physiological.training_readiness_score
    if acute_rest:
        actions.append(_action(
            "movement",
            "暂停训练，优先恢复",
            acute_guardrail,
            action_key="movement.pause_training_acute",
            when="today",
            metric_key="symptom",
            target_value="recover",
            evidence_level="high",
            evidence_tier="safety_guardrail",
            confidence="high",
            claim_boundary="急性病或疑似感染期的活动建议用于健康管理安全兜底；如有发热、胸痛、气促或症状加重，应及时就医。",
        ))
    elif readiness is not None and readiness < 50:
        actions.append(_recovery_movement_action(trigger="training_readiness_score"))
    elif "poor_recovery_matrix" in planner_flags:
        actions.append(_recovery_movement_action(trigger="poor_recovery_matrix"))
    else:
        actions.append(_action(
            "movement",
            "累计 35-45 分钟中等强度活动",
            "对齐每周 150 分钟中等强度活动的代谢健康目标。",
            action_key="movement.moderate_activity",
            when="daytime",
            metric_key="custom",
            target_value="150min_weekly",
            evidence_level="high",
            evidence_tier="strong_behavioral",
            confidence="high",
            claim_boundary="活动目标用于健康管理, 不替代医生对运动禁忌或心血管风险的评估。",
        ))

    actions.append(_action(
        "sleep",
        "睡前 3 小时停止正餐",
        "晚餐过晚会干扰睡眠和第二天恢复, 也会影响体重趋势判断。",
        action_key="sleep.dinner_cutoff",
        when="evening",
        metric_key="sleep_score",
        target_value="trend_up",
        evidence_tier="strong_behavioral",
        confidence="medium",
        claim_boundary="睡眠行为建议用于恢复管理, 不替代睡眠障碍诊断或治疗。",
    ))

    actions.extend(_active_interventions(db, user_id))
    actions, arbitration_notes = _apply_acute_rest_arbiter(acute_rest=acute_rest, actions=actions)
    actions = _guard_plan_actions(db, user_id=user_id, plan_date=plan_date, actions=actions)[:5]

    state_summary = {
        "weight_kg": body.weight_kg,
        "waist_cm": body.waist_cm,
        "bmi": body.bmi,
        "central_obesity_flag": body.central_obesity_flag,
        "blood_pressure": bp,
        "sleep_score": twin.physiological.sleep_score_latest,
        "training_readiness_score": readiness,
        "acute": {
            "has_active_illness": bool(getattr(acute, "has_active_illness", False)),
            "illness_names": list(getattr(acute, "illness_names", []) or []),
            "suspected_cold": bool(getattr(acute, "suspected_cold", False)),
            "fever_reported": bool(getattr(acute, "fever_reported", False)),
            "should_rest_from_training": acute_rest,
            "training_guardrail": acute_guardrail if acute_rest else None,
        },
        **({"arbitration_notes": arbitration_notes} if arbitration_notes else {}),
        "data_sources": twin.meta.data_sources,
        "personal_evidence_matrix": compact_matrix,
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
            "weekly_moderate_minutes": 0 if acute_rest else 150,
            "strength_days": 0 if acute_rest else 2,
            **({"status": "paused_for_acute_illness", "resume_rule": "退热且感冒/呼吸道症状明显缓解后，从低强度活动恢复。"} if acute_rest else {}),
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
        "measurement_automation": get_measurement_capability_map(),
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
