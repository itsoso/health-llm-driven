"""Versioned, reviewable HealthProgram templates."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.health_program import HealthProgram
from app.services.health_program_service import serialize_program

CLAIM_BOUNDARY = "ProgramTemplate 是行为和复测框架,不构成诊断或治疗方案。"

PROGRAM_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "metabolic-reset-8w",
        "version": "2026.06",
        "title": "代谢重置 8 周项目",
        "program_type": "metabolic",
        "duration_weeks": 8,
        "primary_metrics": ["weight", "waist_cm", "glucose_fasting"],
        "secondary_metrics": ["sleep_score", "hrv", "systolic_bp"],
        "target": {"weight": "gradual_decrease_if_needed", "waist_cm": "decrease", "glucose_fasting": "stabilize"},
        "eligible_population": ["希望改善体重/腰围/血糖趋势的成人", "无急性红线症状"],
        "exclusion_criteria": ["妊娠期", "进食障碍风险", "近期急性疾病或医生限制运动"],
        "required_data": ["体重或腰围基线", "至少一个代谢相关指标或用户目标"],
        "safety_gates": ["red_flags", "blood_pressure_check", "medication_review"],
        "protocol_refs": ["meal_timing", "zone2_walk", "daily_weight_or_waist"],
        "retest_window": {"week": 8, "metrics": ["weight", "waist_cm", "glucose_fasting"]},
        "exit_conditions": ["红线症状", "用户暂停", "医生建议停止", "连续 2 周无法执行需重设目标"],
        "review_checklist": ["适用人群", "排除条件", "必要数据", "安全门", "复测窗口", "退出条件"],
        "claim_boundary": CLAIM_BOUNDARY,
    },
    {
        "id": "recovery-capacity-8w",
        "version": "2026.06",
        "title": "恢复能力 8 周项目",
        "program_type": "recovery_training",
        "duration_weeks": 8,
        "primary_metrics": ["hrv", "rhr", "sleep_score"],
        "secondary_metrics": ["readiness_score", "training_load"],
        "target": {"hrv": "increase_or_stabilize", "rhr": "stabilize", "sleep_score": "increase"},
        "eligible_population": ["希望改善训练恢复和疲劳管理的成人"],
        "exclusion_criteria": ["胸痛/晕厥等运动红线", "医生限制运动"],
        "required_data": ["可穿戴 HRV/RHR 或睡眠数据", "训练频率目标"],
        "safety_gates": ["red_flags", "training_risk", "overreaching_check"],
        "protocol_refs": ["training_light", "recovery_sleep_window", "deload_week"],
        "retest_window": {"week": 4, "metrics": ["hrv", "rhr", "sleep_score"]},
        "exit_conditions": ["运动红线", "恢复持续恶化", "用户暂停"],
        "review_checklist": ["适用人群", "排除条件", "必要数据", "安全门", "复测窗口", "退出条件"],
        "claim_boundary": CLAIM_BOUNDARY,
    },
    {
        "id": "sleep-foundation-8w",
        "version": "2026.06",
        "title": "睡眠基础 8 周项目",
        "program_type": "sleep",
        "duration_weeks": 8,
        "primary_metrics": ["sleep_score", "hrv", "rhr"],
        "secondary_metrics": ["sleep_duration", "deep_sleep_min"],
        "target": {"sleep_score": "increase", "sleep_duration": "stabilize", "hrv": "increase_or_stabilize"},
        "eligible_population": ["希望改善睡眠规律和恢复感的成人"],
        "exclusion_criteria": ["疑似睡眠呼吸暂停未评估", "严重失眠或精神健康红线"],
        "required_data": ["睡眠时长/评分或主观睡眠记录", "当前作息窗口"],
        "safety_gates": ["red_flags", "sleep_disorder_screen", "medication_review"],
        "protocol_refs": ["fixed_wake_time", "dinner_cutoff", "light_and_caffeine_window"],
        "retest_window": {"week": 4, "metrics": ["sleep_score", "hrv", "rhr"]},
        "exit_conditions": ["红线症状", "疑似睡眠障碍需医生评估", "用户暂停"],
        "review_checklist": ["适用人群", "排除条件", "必要数据", "安全门", "复测窗口", "退出条件"],
        "claim_boundary": CLAIM_BOUNDARY,
    },
)


def list_templates() -> list[dict[str, Any]]:
    return [dict(template) for template in PROGRAM_TEMPLATES]


def get_template(template_id: str) -> dict[str, Any] | None:
    for template in PROGRAM_TEMPLATES:
        if template["id"] == template_id:
            return dict(template)
    return None


def start_template_program(db: Session, *, user_id: int, template_id: str) -> dict[str, Any]:
    template = get_template(template_id)
    if template is None:
        raise LookupError("program template not found")

    name = template["title"].replace("代谢重置", "代谢重置").replace("8 周项目", "8 周项目")
    if template_id == "sleep-foundation-8w":
        name = "睡眠基础 8 周项目"
    elif template_id == "metabolic-reset-8w":
        name = "代谢重置 8 周项目"
    elif template_id == "recovery-capacity-8w":
        name = "恢复能力 8 周项目"

    existing = (
        db.query(HealthProgram)
        .filter(HealthProgram.user_id == user_id, HealthProgram.name == name, HealthProgram.status == "active")
        .first()
    )
    created = False
    if existing is None:
        today = date.today()
        target = dict(template["target"])
        target["template_id"] = template["id"]
        target["version"] = template["version"]
        existing = HealthProgram(
            user_id=user_id,
            name=name,
            program_type=template["program_type"],
            status="active",
            primary_metrics=template["primary_metrics"],
            secondary_metrics=template["secondary_metrics"],
            baseline={},
            target=target,
            latest={},
            started_on=today,
            target_end_on=today + timedelta(weeks=template["duration_weeks"]),
            notes=f"Created from ProgramTemplate {template['id']}@{template['version']}",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        created = True

    return {
        "template": template,
        "program": {**serialize_program(existing), "created": created},
        "template_contract": {
            "eligible_population": template["eligible_population"],
            "exclusion_criteria": template["exclusion_criteria"],
            "required_data": template["required_data"],
            "safety_gates": template["safety_gates"],
            "protocol_refs": template["protocol_refs"],
            "retest_window": template["retest_window"],
            "exit_conditions": template["exit_conditions"],
        },
        "claim_boundary": "从模板创建的 Program 仍需按个人数据和医生建议调整。",
    }
