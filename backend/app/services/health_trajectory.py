"""Personal Health Trajectory Agent snapshot.

该服务输出疾病上游轨迹视图: 先天底图、长期反馈、临床锚点、实时状态、
可干预变量、风险轨迹和下一步行动。它不做诊断, 只给上游健康管理排序。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services.daily_operating_plan import build_daily_operating_plan
from app.twin import build_twin


FOCUS_DOMAINS = ["metabolic_health", "recovery_capacity", "aging_pace"]

BOUNDARY_TEXT = "本条用于疾病上游健康管理和复查排序, 不替代医生诊断、处方或治疗。"


def _bp_text(twin) -> str | None:
    s = twin.labs.blood_pressure_systolic
    d = twin.labs.blood_pressure_diastolic
    if s and d:
        return f"{s}/{d}"
    return None


def _level_rank(level: str) -> int:
    return {"high": 0, "attention": 1, "unknown": 2, "ok": 3}.get(level, 9)


def _evidence_contract(evidence_tier: str, confidence: str, claim_boundary: str = BOUNDARY_TEXT) -> Dict[str, str]:
    return {
        "evidence_tier": evidence_tier,
        "confidence": confidence,
        "claim_boundary": claim_boundary,
    }


def _genetic_baseline(db: Session, user_id: int) -> Dict[str, Any]:
    has_profile = db.query(GeneticProfile.id).filter(GeneticProfile.user_id == user_id).first() is not None
    variants = db.query(GeneticVariant).filter(GeneticVariant.user_id == user_id).all()
    categories: Dict[str, Dict[str, int]] = {}
    signals: List[Dict[str, Any]] = []
    for v in variants:
        cat = v.category or "other"
        categories.setdefault(cat, {"total": 0, "high": 0, "medium": 0})
        categories[cat]["total"] += 1
        if v.risk_level in ("high", "medium"):
            categories[cat][v.risk_level] += 1
            signals.append({
                "category": cat,
                "gene": v.gene_name,
                "risk_level": v.risk_level,
                "variant_nature": v.variant_nature,
                "result": v.result_label,
            })

    return {
        "has_genetic_profile": has_profile,
        "total_variants": len(variants),
        "high_risk_count": sum(1 for v in variants if v.risk_level == "high"),
        "medium_risk_count": sum(1 for v in variants if v.risk_level == "medium"),
        "categories": categories,
        "signals": sorted(signals, key=lambda s: (0 if s["risk_level"] == "high" else 1, s["category"]))[:8],
    }


def _epigenetic_feedback() -> Dict[str, Any]:
    return {
        "has_methylation_report": False,
        "status": "missing",
        "evidence_tier": "experimental",
        "confidence": "low",
        "claim_boundary": "甲基化时钟只作为长期代理指标和研究性反馈, 不能证明个体短期干预成效或真实衰老速度改变。",
        "latest_test_date": None,
        "biological_age_delta_years": None,
        "pace_of_aging": None,
        "next_step": "接入甲基化报告后, 仅作为长期趋势参考, 不能把短期变化包装成确定性抗衰结果。",
    }


def _data_gaps(twin, genetic: Dict[str, Any], epigenetic: Dict[str, Any]) -> List[Dict[str, str]]:
    gaps: List[Dict[str, str]] = []
    if not genetic["has_genetic_profile"]:
        gaps.append({"code": "genetic_profile_missing", "label": "缺基因底图", "next_step": "上传基因报告"})
    if not epigenetic["has_methylation_report"]:
        gaps.append({"code": "methylation_report_missing", "label": "缺甲基化轨迹反馈", "next_step": "接入甲基化检测结果"})
    if twin.labs.last_exam_date is None and not twin.labs.flagged_abnormal:
        gaps.append({"code": "clinical_anchor_missing", "label": "缺近期体检锚点", "next_step": "上传最近一次体检报告"})
    if twin.body_composition.waist_cm is None:
        gaps.append({"code": "waist_missing", "label": "缺腰围", "next_step": "晨起记录腰围"})
    if twin.physiological.training_readiness_score is None and twin.physiological.sleep_score_latest is None:
        gaps.append({"code": "wearable_state_missing", "label": "缺实时恢复状态", "next_step": "同步可穿戴睡眠/HRV 数据"})
    return gaps


def _metabolic_risk(twin, genetic: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[str] = []
    clinical_signals: List[str] = []
    body = twin.body_composition
    labs = twin.labs
    if body.central_obesity_flag:
        signals.append("waist_central_obesity")
        clinical_signals.append("waist_central_obesity")
    if body.bmi is not None and body.bmi >= 24:
        signals.append("bmi_overweight")
        clinical_signals.append("bmi_overweight")
    if labs.blood_pressure_systolic is not None and labs.blood_pressure_systolic >= 130:
        signals.append("bp_elevated")
        clinical_signals.append("bp_elevated")
    if labs.blood_pressure_diastolic is not None and labs.blood_pressure_diastolic >= 85:
        signals.append("bp_elevated")
        clinical_signals.append("bp_elevated")
    if labs.hba1c is not None and labs.hba1c >= 5.7:
        signals.append("hba1c_elevated")
        clinical_signals.append("hba1c_elevated")
    if labs.triglycerides is not None and labs.triglycerides >= 1.7:
        signals.append("triglycerides_elevated")
        clinical_signals.append("triglycerides_elevated")
    if labs.ldl is not None and labs.ldl >= 3.4:
        signals.append("ldl_elevated")
        clinical_signals.append("ldl_elevated")
    if any(s["category"] == "disease_risk" and s["risk_level"] == "high" for s in genetic["signals"]):
        signals.append("genetic_disease_risk")

    high = labs.blood_pressure_systolic is not None and labs.blood_pressure_systolic >= 160
    level = "high" if high else "attention" if signals else "unknown"
    evidence_tier = "clinical_guideline" if clinical_signals else "genetic_association" if signals else "clinical_guideline"
    confidence = "high" if clinical_signals else "low"
    return {
        "domain": "metabolic_health",
        "level": level,
        "title": "代谢健康轨迹需要关注" if level != "unknown" else "代谢轨迹数据不足",
        "why": "腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。" if signals else "缺少足够临床锚点判断代谢轨迹。",
        "signals": sorted(set(signals)),
        "primary_action": "围绕腰围、蛋白、每周 150 分钟中等强度活动和睡眠节律执行 7 天计划。",
        **_evidence_contract(evidence_tier, confidence),
    }


def _recovery_risk(twin, genetic: Dict[str, Any]) -> Dict[str, Any]:
    phys = twin.physiological
    signals: List[str] = []
    wearable_signals: List[str] = []
    if phys.training_readiness_score is not None and phys.training_readiness_score < 50:
        signals.append("training_readiness_low")
        wearable_signals.append("training_readiness_low")
    if phys.sleep_duration_h_latest is not None and phys.sleep_duration_h_latest < 6.5:
        signals.append("sleep_duration_low")
        wearable_signals.append("sleep_duration_low")
    if phys.sleep_score_latest is not None and phys.sleep_score_latest < 70:
        signals.append("sleep_score_low")
        wearable_signals.append("sleep_score_low")
    if (phys.hrv_status or "").lower() in {"low", "偏低", "unbalanced"}:
        signals.append("hrv_low")
        wearable_signals.append("hrv_low")
    if any(s["category"] == "recovery" and s["risk_level"] in ("high", "medium") for s in genetic["signals"]):
        signals.append("genetic_recovery_sensitivity")

    evidence_tier = "wearable_proxy" if wearable_signals or not signals else "genetic_association"
    confidence = "medium" if wearable_signals else "low"
    return {
        "domain": "recovery_capacity",
        "level": "attention" if signals else "unknown",
        "title": "恢复能力轨迹需要减载" if signals else "恢复轨迹数据不足",
        "why": "睡眠、HRV、训练准备度或恢复相关基因提示今天应优先稳恢复。" if signals else "缺少睡眠/HRV/训练准备度数据。",
        "signals": sorted(set(signals)),
        "primary_action": "今天避免堆高强度, 用 Zone 2、提前晚餐和固定睡眠窗口恢复。",
        **_evidence_contract(
            evidence_tier,
            confidence,
            "可穿戴恢复指标和恢复相关基因只用于训练/睡眠管理排序, 不替代医生诊断、处方或治疗。",
        ),
    }


def _aging_risk(epigenetic: Dict[str, Any], twin) -> Dict[str, Any]:
    if not epigenetic["has_methylation_report"]:
        return {
            "domain": "aging_pace",
            "level": "unknown",
            "title": "衰老速度缺长期反馈",
            "why": "当前没有甲基化报告, 只能用体检、恢复和行为数据做间接追踪。",
            "signals": ["methylation_missing"],
            "primary_action": "先用 8-12 周代谢和恢复闭环建立基线, 再接入甲基化长期反馈。",
            **_evidence_contract(
                "experimental",
                "low",
                "甲基化时钟是长期代理指标, 不能证明个体短期干预成效, 不替代医生诊断、处方或治疗。",
            ),
        }
    return {
        "domain": "aging_pace",
        "level": "ok",
        "title": "衰老速度有长期反馈",
        "why": "甲基化报告已接入。",
        "signals": [],
        "primary_action": "按甲基化反馈调整长期干预。",
        **_evidence_contract(
            "experimental",
            "low",
            "甲基化时钟是长期代理指标, 不能证明个体短期干预成效, 不替代医生诊断、处方或治疗。",
        ),
    }


def _trajectory_risks(twin, genetic: Dict[str, Any], epigenetic: Dict[str, Any]) -> List[Dict[str, Any]]:
    risks = [
        _metabolic_risk(twin, genetic),
        _recovery_risk(twin, genetic),
        _aging_risk(epigenetic, twin),
    ]
    return sorted(risks, key=lambda r: (_level_rank(r["level"]), FOCUS_DOMAINS.index(r["domain"])))


def build_health_trajectory_snapshot(db: Session, user_id: int) -> Dict[str, Any]:
    """构建当前用户疾病上游健康轨迹快照."""
    twin = build_twin(db, user_id, use_cache=False)
    daily_plan = build_daily_operating_plan(db, user_id)
    genetic = _genetic_baseline(db, user_id)
    epigenetic = _epigenetic_feedback()
    risks = _trajectory_risks(twin, genetic, epigenetic)

    return {
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": "upstream_90d",
        "focus_domains": FOCUS_DOMAINS,
        "congenital_baseline": genetic,
        "epigenetic_feedback": epigenetic,
        "clinical_anchors": {
            "weight_kg": twin.body_composition.weight_kg,
            "waist_cm": twin.body_composition.waist_cm,
            "bmi": twin.body_composition.bmi,
            "central_obesity_flag": twin.body_composition.central_obesity_flag,
            "blood_pressure": _bp_text(twin),
            "hba1c": twin.labs.hba1c,
            "ldl": twin.labs.ldl,
            "triglycerides": twin.labs.triglycerides,
            "last_exam_date": twin.labs.last_exam_date.isoformat() if twin.labs.last_exam_date else None,
            "abnormal_count": len(twin.labs.flagged_abnormal or []),
        },
        "realtime_state": {
            "training_readiness_score": twin.physiological.training_readiness_score,
            "training_readiness_level": twin.physiological.training_readiness_level,
            "sleep_score": twin.physiological.sleep_score_latest,
            "sleep_duration_h": twin.physiological.sleep_duration_h_latest,
            "hrv_latest": twin.physiological.hrv_latest,
            "hrv_status": twin.physiological.hrv_status,
            "resting_hr": twin.physiological.resting_hr,
            "vo2max_running": twin.physiological.vo2max_running,
            "data_sources": twin.meta.data_sources,
        },
        "modifiable_levers": {
            "nutrition": {
                "calories_today": twin.behavioral.diet_calories_today,
                "protein_g_today": twin.behavioral.diet_protein_g_today,
                "meals_logged_today": twin.behavioral.meals_logged_today,
            },
            "movement": {
                "workouts_this_week": twin.behavioral.workouts_this_week,
                "acute_chronic_ratio": twin.behavioral.acute_chronic_ratio,
                "steps_today": twin.physiological.steps_today,
            },
            "sleep": {
                "sleep_score": twin.physiological.sleep_score_latest,
                "sleep_duration_h": twin.physiological.sleep_duration_h_latest,
            },
            "environment": {
                "aqi": twin.environment.aqi,
                "outdoor_exercise_suitability": twin.environment.outdoor_exercise_suitability,
            },
        },
        "trajectory_risks": risks,
        "next_actions": (daily_plan.get("actions") or [])[:3],
        "doctor_escalation": daily_plan.get("doctor_escalation") or {"needed": False},
        "data_gaps": _data_gaps(twin, genetic, epigenetic),
        "safety_boundary": "本快照用于疾病上游风险轨迹识别和生活方式管理, 不替代医生诊断、处方或治疗。",
    }
