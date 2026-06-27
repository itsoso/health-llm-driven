"""Health Operating Loop window review service."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import GarminData
from app.models.intervention_event import InterventionEvent
from app.models.waist import WaistRecord
from app.models.weight import WeightRecord

SUPPORTED_REVIEW_WINDOWS = {7, 30, 90}
COMPLETED_STATUSES = {"completed", "done", "verified"}
LOWER_IS_BETTER_METRICS = {"weight", "waist_cm", "systolic_bp", "diastolic_bp"}


def build_health_operating_review(
    db: Session,
    *,
    user_id: int,
    window_days: int,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Build a user-scoped execution and outcome review for a fixed window."""

    if window_days not in SUPPORTED_REVIEW_WINDOWS:
        raise ValueError("window_days must be one of 7, 30, 90")

    end = end_date or date.today()
    start = end - timedelta(days=window_days - 1)
    events = (
        db.query(InterventionEvent)
        .filter(
            InterventionEvent.user_id == user_id,
            InterventionEvent.plan_date >= start,
            InterventionEvent.plan_date <= end,
        )
        .order_by(InterventionEvent.plan_date.asc(), InterventionEvent.id.asc())
        .all()
    )

    metrics = _metric_summary(db, user_id=user_id, start=start, end=end)
    action_effects = _action_effects(events, metrics)
    return {
        "window_days": window_days,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "execution": _execution_summary(events),
        "metrics": metrics,
        "completed_action_keys": [
            event.action_key for event in events if event.feedback_status in COMPLETED_STATUSES
        ],
        "action_effects": action_effects,
        "prediction_backtest": _prediction_backtest_placeholder(
            window_days=window_days,
            events=events,
            metrics=metrics,
            action_effects=action_effects,
        ),
    }


def _execution_summary(events: list[InterventionEvent]) -> dict[str, Any]:
    by_status = Counter(event.feedback_status for event in events)
    by_domain = Counter((event.action_domain or "unknown") for event in events)
    completed = sum(by_status.get(status, 0) for status in COMPLETED_STATUSES)
    total = len(events)
    return {
        "total_events": total,
        "completed_events": completed,
        "completion_rate": round(completed / total, 2) if total else 0,
        "by_status": dict(sorted(by_status.items())),
        "by_domain": dict(sorted(by_domain.items())),
    }


def _metric_summary(db: Session, *, user_id: int, start: date, end: date) -> dict[str, Any]:
    return {
        "weight": _numeric_change(_query_weight(db, user_id, start, end), precision=1),
        "waist_cm": _numeric_change(_query_waist(db, user_id, start, end), precision=1),
        "systolic_bp": _numeric_change(_query_bp(db, user_id, start, end, "systolic"), precision=0),
        "diastolic_bp": _numeric_change(_query_bp(db, user_id, start, end, "diastolic"), precision=0),
        "sleep_score": _numeric_change(_query_garmin(db, user_id, start, end, "sleep_score"), precision=0),
        "hrv": _numeric_change(_query_garmin(db, user_id, start, end, "hrv"), precision=0),
    }


def _action_effects(events: list[InterventionEvent], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Link completed actions to their verification metric without overstating causality."""
    effects: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        if event.feedback_status not in COMPLETED_STATUSES:
            continue
        snapshot = event.action_snapshot or {}
        metric = snapshot.get("verification_metric") or snapshot.get("metric_key")
        if not metric or metric not in metrics:
            continue
        metric_change = metrics[metric]
        delta = metric_change.get("delta")
        if metric_change.get("status") != "present" or delta is None:
            continue
        key = (event.action_key, metric)
        if key in seen:
            continue
        seen.add(key)

        improved = delta < 0 if metric in LOWER_IS_BETTER_METRICS else delta > 0
        effects.append({
            "action_key": event.action_key,
            "action_title": event.action_title,
            "metric": metric,
            "metric_delta": delta,
            "direction": "improved" if improved else "worsened" if delta else "flat",
            "confidence": "medium" if improved else "low",
            "attribution": "temporal_association_not_causation",
        })
    return effects


def _prediction_backtest_placeholder(
    *,
    window_days: int,
    events: list[InterventionEvent],
    metrics: dict[str, Any],
    action_effects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Expose the future backtest slot without pretending a model exists."""
    eligible_metrics = sorted(
        metric
        for metric, change in metrics.items()
        if change.get("status") == "present" and change.get("delta") is not None
    )
    completed_count = sum(1 for event in events if event.feedback_status in COMPLETED_STATUSES)
    return {
        "version": "prediction_backtest_placeholder_v1",
        "status": "not_ready",
        "reason": "requires_prediction_output_history",
        "candidate_count": len(action_effects),
        "ready_candidate_count": 0,
        "window_days": window_days,
        "minimum_window_days": 30,
        "completed_action_count": completed_count,
        "eligible_metrics": eligible_metrics,
        "requirements": [
            "prediction_output_history",
            "matched_outcome_window",
            "confounder_review",
            "safety_boundary_review",
        ],
        "boundary": "当前仅预留后续回测槽位, 不评估预测准确性, 不生成新的健康建议或临床结论。",
    }


def _numeric_change(points: Iterable[tuple[date, float | int | None]], *, precision: int) -> dict[str, Any]:
    values = [(observed_at, float(value)) for observed_at, value in points if value is not None]
    if not values:
        return {"status": "missing", "count": 0, "current": None, "delta": None}

    first_date, first = values[0]
    last_date, last = values[-1]
    delta = last - first if len(values) >= 2 else None
    return {
        "status": "present",
        "count": len(values),
        "first": _round(first, precision),
        "first_date": first_date.isoformat(),
        "current": _round(last, precision),
        "current_date": last_date.isoformat(),
        "delta": _round(delta, precision) if delta is not None else None,
    }


def _round(value: float, precision: int) -> float | int:
    rounded = round(value, precision)
    if precision == 0:
        return int(rounded)
    return rounded


def _query_weight(db: Session, user_id: int, start: date, end: date):
    rows = (
        db.query(WeightRecord)
        .filter(WeightRecord.user_id == user_id, WeightRecord.record_date >= start, WeightRecord.record_date <= end)
        .order_by(WeightRecord.record_date.asc(), WeightRecord.id.asc())
        .all()
    )
    return [(row.record_date, row.weight) for row in rows]


def _query_waist(db: Session, user_id: int, start: date, end: date):
    rows = (
        db.query(WaistRecord)
        .filter(WaistRecord.user_id == user_id, WaistRecord.record_date >= start, WaistRecord.record_date <= end)
        .order_by(WaistRecord.record_date.asc(), WaistRecord.id.asc())
        .all()
    )
    return [(row.record_date, row.waist_cm) for row in rows]


def _query_bp(db: Session, user_id: int, start: date, end: date, field: str):
    rows = (
        db.query(BloodPressureRecord)
        .filter(
            BloodPressureRecord.user_id == user_id,
            BloodPressureRecord.record_date >= start,
            BloodPressureRecord.record_date <= end,
        )
        .order_by(BloodPressureRecord.record_date.asc(), BloodPressureRecord.id.asc())
        .all()
    )
    return [(row.record_date, getattr(row, field)) for row in rows]


def _query_garmin(db: Session, user_id: int, start: date, end: date, field: str):
    # 单指标按日去重: 多源同一天多行,按该指标优先级源取一个值 (含 None 占位以保留天)
    from app.services.garmin_daily_merged import merged_daily_rows
    rows = merged_daily_rows(db, user_id, since=start, until=end, ascending=True)
    return [(row.record_date, getattr(row, field, None)) for row in rows]
