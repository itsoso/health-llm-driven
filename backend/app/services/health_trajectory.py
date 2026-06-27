"""Personal Health Trajectory Agent snapshot.

该服务输出疾病上游轨迹视图: 先天底图、长期反馈、临床锚点、实时状态、
可干预变量、风险轨迹和下一步行动。它不做诊断, 只给上游健康管理排序。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.user import User
from app.services.daily_operating_plan import build_daily_operating_plan
from app.services.epigenetic_report_service import list_epigenetic_reports
from app.services.personal_models.personal_prediction import build_personal_predictions
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


def _uncertainty_contract(level: str, drivers: List[str]) -> Dict[str, Any]:
    return {
        "level": level,
        "drivers": sorted(set(drivers)),
    }


def _verification_window(days: int, signal: str) -> Dict[str, Any]:
    return {
        "days": days,
        "signal": signal,
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


def _epigenetic_feedback(db: Session, user_id: int) -> Dict[str, Any]:
    latest_reports = list_epigenetic_reports(db, user_id, limit=1)
    if not latest_reports:
        return {
            "has_methylation_report": False,
            "status": "missing",
            "evidence_tier": "experimental",
            "confidence": "low",
            "claim_boundary": "甲基化时钟只作为长期代理指标和研究性反馈, 不能证明个体短期干预成效或真实衰老速度改变。",
            "latest_test_date": None,
            "vendor": None,
            "clock_type": None,
            "biological_age": None,
            "biological_age_delta_years": None,
            "pace_of_aging": None,
            "next_step": "接入甲基化报告后, 仅作为长期趋势参考, 不能把短期变化包装成确定性抗衰结果。",
        }

    latest_report = latest_reports[0]
    user_birth_date = db.query(User.birth_date).filter(User.id == user_id).scalar()
    sample_date = _parse_date(latest_report.get("sample_date"))
    biological_age = latest_report.get("biological_age")
    chronological_age = _chronological_age_years(user_birth_date, sample_date)
    biological_age_delta = (
        round(float(biological_age) - chronological_age, 1)
        if biological_age is not None and chronological_age is not None
        else None
    )

    return {
        "has_methylation_report": True,
        "status": "present",
        "evidence_tier": "experimental",
        "confidence": "low",
        "claim_boundary": "甲基化时钟只作为长期代理指标和研究性反馈, 不能证明个体短期干预成效或真实衰老速度改变。",
        "latest_test_date": latest_report.get("sample_date"),
        "vendor": latest_report.get("vendor"),
        "clock_type": latest_report.get("clock_type"),
        "biological_age": biological_age,
        "biological_age_delta_years": biological_age_delta,
        "pace_of_aging": latest_report.get("pace_of_aging"),
        "raw_summary": latest_report.get("raw_summary") or {},
        "next_step": "把甲基化结果作为 8-12 周干预复测的长期代理指标, 不作为短期疗效或抗衰确定性结论。",
    }


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _chronological_age_years(birth_date: date | None, measured_date: date | None) -> float | None:
    if birth_date is None or measured_date is None:
        return None
    return (measured_date - birth_date).days / 365.25


def _epigenetic_present_signals(epigenetic: Dict[str, Any]) -> list[str]:
    signals: list[str] = ["methylation_report_present"]
    pace_of_aging = epigenetic.get("pace_of_aging")
    biological_age_delta = epigenetic.get("biological_age_delta_years")
    if isinstance(pace_of_aging, (int, float)) and pace_of_aging >= 1.05:
        signals.append("epigenetic_pace_elevated")
    if isinstance(biological_age_delta, (int, float)) and biological_age_delta >= 3:
        signals.append("biological_age_delta_elevated")
    return signals


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
    if "waist_central_obesity" in signals or "bmi_overweight" in signals:
        state_variable = "waist_cm"
    elif "bp_elevated" in signals:
        state_variable = "blood_pressure"
    elif any(s in signals for s in {"hba1c_elevated", "triglycerides_elevated", "ldl_elevated"}):
        state_variable = "metabolic_labs"
    else:
        state_variable = "metabolic_health_anchor"
    uncertainty_drivers = []
    if not clinical_signals:
        uncertainty_drivers.append("clinical_anchor_missing_or_sparse")
    if "genetic_disease_risk" in signals:
        uncertainty_drivers.append("genetic_association_not_deterministic")
    if labs.last_exam_date is None:
        uncertainty_drivers.append("lab_recency_unknown")
    if not uncertainty_drivers:
        uncertainty_drivers.append("short_window_observation")
    return {
        "domain": "metabolic_health",
        "level": level,
        "state_variable": state_variable,
        "horizon": "upstream_90d",
        "title": "代谢健康轨迹需要关注" if level != "unknown" else "代谢轨迹数据不足",
        "why": "腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。" if signals else "缺少足够临床锚点判断代谢轨迹。",
        "signals": sorted(set(signals)),
        "primary_action": "围绕腰围、蛋白、每周 150 分钟中等强度活动和睡眠节律执行 7 天计划。",
        "modifiable_levers": ["movement", "nutrition", "diet", "sleep", "measurement"],
        "uncertainty": _uncertainty_contract("medium" if clinical_signals else "high", uncertainty_drivers),
        "verification_window": _verification_window(7, state_variable),
        "verification_window_days": 7,
        "verification_signal": state_variable,
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
    if "training_readiness_low" in signals:
        state_variable = "training_readiness_score"
    elif "sleep_score_low" in signals:
        state_variable = "sleep_score"
    elif "sleep_duration_low" in signals:
        state_variable = "sleep_duration_h"
    elif "hrv_low" in signals:
        state_variable = "hrv_status"
    else:
        state_variable = "recovery_capacity_anchor"
    uncertainty_drivers = []
    if wearable_signals:
        uncertainty_drivers.append("wearable_proxy_signal")
    if any(signal.startswith("genetic_") for signal in signals):
        uncertainty_drivers.append("genetic_association_not_deterministic")
    if not signals:
        uncertainty_drivers.append("wearable_state_missing")
    return {
        "domain": "recovery_capacity",
        "level": "attention" if signals else "unknown",
        "state_variable": state_variable,
        "horizon": "upstream_14d",
        "title": "恢复能力轨迹需要减载" if signals else "恢复轨迹数据不足",
        "why": "睡眠、HRV、训练准备度或恢复相关基因提示今天应优先稳恢复。" if signals else "缺少睡眠/HRV/训练准备度数据。",
        "signals": sorted(set(signals)),
        "primary_action": "今天避免堆高强度, 用 Zone 2、提前晚餐和固定睡眠窗口恢复。",
        "modifiable_levers": ["sleep", "movement", "training", "recovery", "nutrition"],
        "uncertainty": _uncertainty_contract("medium" if wearable_signals else "high", uncertainty_drivers),
        "verification_window": _verification_window(7, state_variable),
        "verification_window_days": 7,
        "verification_signal": state_variable,
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
            "state_variable": "methylation_report",
            "horizon": "upstream_90d",
            "title": "衰老速度缺长期反馈",
            "why": "当前没有甲基化报告, 只能用体检、恢复和行为数据做间接追踪。",
            "signals": ["methylation_missing"],
            "primary_action": "先用 8-12 周代谢和恢复闭环建立基线, 再接入甲基化长期反馈。",
            "modifiable_levers": ["movement", "nutrition", "sleep", "measurement"],
            "uncertainty": _uncertainty_contract("high", ["methylation_report_missing", "uses_indirect_proxy_metrics"]),
            "verification_window": _verification_window(84, "methylation_report"),
            "verification_window_days": 84,
            "verification_signal": "methylation_report",
            **_evidence_contract(
                "experimental",
                "low",
                "甲基化时钟是长期代理指标, 不能证明个体短期干预成效, 不替代医生诊断、处方或治疗。",
            ),
        }
    signals = _epigenetic_present_signals(epigenetic)
    elevated = any(signal in signals for signal in {"epigenetic_pace_elevated", "biological_age_delta_elevated"})
    state_variable = (
        "pace_of_aging"
        if "epigenetic_pace_elevated" in signals
        else "biological_age_delta_years"
        if "biological_age_delta_elevated" in signals
        else "methylation_report"
    )
    return {
        "domain": "aging_pace",
        "level": "attention" if elevated else "ok",
        "state_variable": state_variable,
        "horizon": "upstream_90d",
        "title": "衰老速度长期反馈需要关注" if elevated else "衰老速度有长期反馈",
        "why": "甲基化报告提示长期代理指标偏高, 只能用于复测节奏和生活方式优先级排序。" if elevated else "甲基化报告已接入, 可作为长期趋势代理指标。",
        "signals": signals,
        "primary_action": "用 8-12 周代谢、睡眠和运动闭环后复测趋势, 不把短期变化当作确定性抗衰成效。",
        "modifiable_levers": ["movement", "nutrition", "sleep", "measurement"],
        "uncertainty": _uncertainty_contract("high", ["experimental_proxy_metric", "long_retest_window_required"]),
        "verification_window": _verification_window(84, state_variable),
        "verification_window_days": 84,
        "verification_signal": state_variable,
        **_evidence_contract(
            "experimental",
            "low",
            epigenetic.get("claim_boundary") or "甲基化时钟是长期代理指标, 不能证明个体短期干预成效, 不替代医生诊断、处方或治疗。",
        ),
    }


def _trajectory_risks(twin, genetic: Dict[str, Any], epigenetic: Dict[str, Any]) -> List[Dict[str, Any]]:
    risks = [
        _metabolic_risk(twin, genetic),
        _recovery_risk(twin, genetic),
        _aging_risk(epigenetic, twin),
    ]
    return sorted(risks, key=lambda r: (_level_rank(r["level"]), FOCUS_DOMAINS.index(r["domain"])))


def _prediction_context(prediction: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "id",
        "prediction_type",
        "metric",
        "domain",
        "horizon_days",
        "expected_signal",
        "confidence",
        "uncertainty",
        "evidence_tier",
        "claim_boundary",
        "model_version",
    )
    return {key: prediction[key] for key in keys if key in prediction}


def _enrich_risks_with_predictions(
    risks: List[Dict[str, Any]],
    predictions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    active_predictions = [
        prediction
        for prediction in predictions
        if prediction.get("confidence") != "low"
    ]
    enriched: List[Dict[str, Any]] = []
    for risk in risks:
        out = dict(risk)
        match = next(
            (
                prediction
                for prediction in active_predictions
                if prediction.get("domain") == risk.get("domain")
            ),
            None,
        )
        if match:
            out["personal_prediction_context"] = _prediction_context(match)
        enriched.append(out)
    return enriched


def build_health_trajectory_snapshot(db: Session, user_id: int) -> Dict[str, Any]:
    """构建当前用户疾病上游健康轨迹快照."""
    twin = build_twin(db, user_id, use_cache=False)
    daily_plan = build_daily_operating_plan(db, user_id)
    genetic = _genetic_baseline(db, user_id)
    epigenetic = _epigenetic_feedback(db, user_id)
    predictions = build_personal_predictions(db, user_id)
    risks = _enrich_risks_with_predictions(
        _trajectory_risks(twin, genetic, epigenetic),
        predictions,
    )

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
        "personal_predictions": predictions,
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
