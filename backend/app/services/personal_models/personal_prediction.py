"""PersonalPrediction contract built from existing auditable personal models.

This module does not introduce a black-box forecaster. It wraps already reviewed
signals (N-of-1 treatment-effect estimates and rolling personal baselines) into
a stable prediction-shaped contract that can be consumed by Trajectory, Agenda,
Review, and evaluators.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.personal_baseline import compute_personal_baselines
from app.services.personal_models.intervention_priors import get_prior
from app.services.personal_models.treatment_effect import MODEL_VERSION as EFFECT_MODEL_VERSION
from app.services.personal_models.treatment_effect import estimate_effect

logger = logging.getLogger(__name__)

MODEL_VERSION = "personal_prediction_v1"
BOUNDARY_TEXT = "这是个人统计预测和复盘辅助, 不替代医生诊断、处方或治疗。"

_METRIC_DOMAIN = {
    "weight": "metabolic_health",
    "waist_cm": "metabolic_health",
    "bmi": "metabolic_health",
    "ldl": "metabolic_health",
    "apob": "metabolic_health",
    "hba1c": "metabolic_health",
    "glucose_fasting": "metabolic_health",
    "fasting_glucose": "metabolic_health",
    "sbp": "metabolic_health",
    "dbp": "metabolic_health",
    "blood_pressure": "metabolic_health",
    "hrv": "recovery_capacity",
    "sleep_score": "recovery_capacity",
    "sleep_total": "recovery_capacity",
    "sleep_deep": "recovery_capacity",
    "resting_heart_rate": "recovery_capacity",
    "body_battery": "recovery_capacity",
    "stress": "recovery_capacity",
    "spo2_avg": "recovery_capacity",
}

_CONFIDENCE_NORMALIZE = {
    "high": "high",
    "med": "medium",
    "medium": "medium",
    "low": "low",
}

_UNCERTAINTY_BY_CONFIDENCE = {
    "high": "medium",
    "medium": "medium",
    "low": "high",
}

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def build_personal_predictions(
    db: Session,
    user_id: int,
    *,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Return stable PersonalPrediction records for one user.

    The output is intentionally conservative: every record carries a model
    version, horizon, uncertainty, evidence tier, source model, and boundary.
    """
    predictions: List[Dict[str, Any]] = []
    predictions.extend(_intervention_cycle_predictions(db, user_id))
    predictions.extend(_baseline_deviation_predictions(db, user_id))
    predictions.sort(key=lambda p: (
        _CONFIDENCE_RANK.get(str(p.get("confidence")), 9),
        int(p.get("horizon_days") or 999),
        str(p.get("metric") or ""),
    ))
    predictions = _filter_predictions_by_user_controls(db, user_id, predictions)
    return predictions[: max(1, int(limit or 8))]


def _intervention_cycle_predictions(db: Session, user_id: int) -> List[Dict[str, Any]]:
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    cycles = (
        db.query(InterventionCycle)
        .filter(InterventionCycle.user_id == user_id, InterventionCycle.status == "active")
        .order_by(InterventionCycle.start_date.desc(), InterventionCycle.id.desc())
        .limit(3)
        .all()
    )
    today = date.today()
    predictions: List[Dict[str, Any]] = []
    for cycle in cycles:
        metrics = (
            db.query(OutcomeMetric)
            .filter(OutcomeMetric.cycle_id == cycle.id)
            .order_by(OutcomeMetric.id.asc())
            .all()
        )
        for metric in metrics:
            prediction = _prediction_from_outcome_metric(cycle, metric, today=today)
            if prediction:
                predictions.append(prediction)
    return predictions


def _prediction_from_outcome_metric(cycle, metric, *, today: date) -> Optional[Dict[str, Any]]:
    if metric.baseline_value is None or metric.latest_value is None:
        return None
    observed_delta = float(metric.latest_value) - float(metric.baseline_value)
    base_prior = get_prior(cycle.cycle_type, metric.metric_code)
    if metric.direction and metric.direction != base_prior.direction:
        from dataclasses import replace

        prior = replace(base_prior, direction=metric.direction)
    else:
        prior = base_prior
    estimate = estimate_effect(
        observed_delta,
        prior,
        metric_code=metric.metric_code,
        unit=metric.unit,
    )
    if estimate.posterior_effect is None:
        return None

    confidence = _normalize_confidence(estimate.confidence)
    horizon_days = _cycle_horizon_days(cycle, today=today)
    expected_delta = round(float(estimate.posterior_effect), 3)
    expected_value = round(float(metric.latest_value) + expected_delta, 3)
    direction = _direction_from_delta(expected_delta)

    return {
        "id": f"personal_prediction:cycle:{cycle.id}:{metric.metric_code}",
        "prediction_type": "intervention_cycle_projection",
        "metric": metric.metric_code,
        "domain": _domain_for_metric(metric.metric_code),
        "horizon_days": horizon_days,
        "baseline": float(metric.latest_value),
        "unit": metric.unit,
        "expected_signal": {
            "metric": metric.metric_code,
            "direction": direction,
            "expected_delta": expected_delta,
            "expected_value": expected_value,
            "ci_low": round(float(estimate.ci_low), 3) if estimate.ci_low is not None else None,
            "ci_high": round(float(estimate.ci_high), 3) if estimate.ci_high is not None else None,
        },
        "confidence": confidence,
        "uncertainty": {
            "level": _UNCERTAINTY_BY_CONFIDENCE.get(confidence, "high"),
            "drivers": _uncertainty_drivers_for_estimate(estimate, cycle),
        },
        "evidence_tier": estimate.evidence_tier,
        "source_model": EFFECT_MODEL_VERSION,
        "model_version": MODEL_VERSION,
        "claim_boundary": BOUNDARY_TEXT,
        "requires_clinician": estimate.requires_clinician,
        "review_hint": "到复测窗口后用实际指标回测, 不能把相关变化解释为因果证明。",
    }


def _baseline_deviation_predictions(db: Session, user_id: int) -> List[Dict[str, Any]]:
    try:
        baselines = compute_personal_baselines(db, user_id)
    except Exception:  # noqa: BLE001
        logger.warning("[PersonalPrediction] personal baseline build failed user=%s", user_id, exc_info=True)
        return []

    predictions: List[Dict[str, Any]] = []
    for baseline in baselines:
        if not baseline.is_deviation or baseline.latest is None:
            continue
        confidence = "low" if baseline.low_confidence else "medium"
        predictions.append({
            "id": f"personal_prediction:baseline:{baseline.key}",
            "prediction_type": "baseline_deviation_projection",
            "metric": baseline.key,
            "domain": _domain_for_metric(baseline.key),
            "horizon_days": 7,
            "baseline": round(float(baseline.latest), 3),
            "unit": baseline.unit,
            "expected_signal": {
                "metric": baseline.key,
                "direction": "persisting_low" if (baseline.z or 0) < 0 else "persisting_high",
                "z": round(float(baseline.z), 3) if baseline.z is not None else None,
                "baseline_mean": round(float(baseline.baseline_mean), 3),
            },
            "confidence": confidence,
            "uncertainty": {
                "level": "high" if baseline.low_confidence else "medium",
                "drivers": ["rolling_baseline_deviation", "wearable_proxy_signal"],
            },
            "evidence_tier": "personal_baseline",
            "source_model": "personal_baseline_v1",
            "model_version": MODEL_VERSION,
            "claim_boundary": BOUNDARY_TEXT,
            "requires_clinician": False,
            "review_hint": "先复核数据来源和近 7 天趋势, 再决定是否调整行动。",
        })
    return predictions


def _cycle_horizon_days(cycle, *, today: date) -> int:
    if cycle.planned_end_date:
        return max(0, (cycle.planned_end_date - today).days)
    return 28


def _normalize_confidence(value: str) -> str:
    return _CONFIDENCE_NORMALIZE.get(str(value or "").lower(), "low")


def _domain_for_metric(metric: str) -> str:
    return _METRIC_DOMAIN.get(str(metric or "").lower(), "general_health")


def _direction_from_delta(delta: float) -> str:
    if delta < 0:
        return "down"
    if delta > 0:
        return "up"
    return "flat"


def _uncertainty_drivers_for_estimate(estimate, cycle) -> List[str]:
    drivers = ["n_of_1_observational_cycle"]
    if estimate.requires_clinician:
        drivers.append("clinician_review_required")
    if not cycle.planned_end_date:
        drivers.append("planned_end_date_missing")
    if estimate.confidence in {"low", "med"}:
        drivers.append("wide_interval_or_short_cycle")
    return sorted(set(drivers))


def _filter_predictions_by_user_controls(
    db: Session,
    user_id: int,
    predictions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    try:
        from app.services.health_runtime_governance import filter_predictions_by_controls

        return filter_predictions_by_controls(db, user_id, predictions)
    except Exception:  # noqa: BLE001
        logger.warning("[PersonalPrediction] governance filter failed user=%s", user_id, exc_info=True)
        return predictions
