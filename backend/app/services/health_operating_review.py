"""Health Operating Loop window review service."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import GarminData
from app.models.intervention_event import InterventionEvent
from app.models.waist import WaistRecord
from app.models.weight import WeightRecord
from app.services.causal_memory import derive_causal_notes

SUPPORTED_REVIEW_WINDOWS = {7, 30, 90}
COMPLETED_STATUSES = {"completed", "done", "verified"}
LOWER_IS_BETTER_METRICS = {"weight", "waist_cm", "systolic_bp", "diastolic_bp"}
logger = logging.getLogger(__name__)


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
    prediction_backtest = _prediction_backtest(
        window_days=window_days,
        events=events,
        metrics=metrics,
        action_effects=action_effects,
    )
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
        "prediction_backtest": prediction_backtest,
        "prediction_timeline": _prediction_timeline(prediction_backtest, events),
        "causal_memory": _causal_memory_review(db, user_id=user_id, window_days=window_days),
    }


def _causal_memory_review(db: Session, *, user_id: int, window_days: int) -> dict[str, Any]:
    try:
        result = derive_causal_notes(db, user_id=user_id, max_events=3, window_days=window_days)
    except Exception as exc:  # noqa: BLE001
        logger.warning("causal_memory_review_failed user_id=%s error=%s", user_id, str(exc))
        return {
            "notes": [],
            "evidence_tier": "observational",
            "claim_boundary": "个人规律暂不可用;不生成新的健康建议或临床结论。",
        }

    notes = result.get("notes") if isinstance(result, dict) else []
    if not isinstance(notes, list):
        notes = []
    return {
        "notes": notes[:3],
        "evidence_tier": result.get("evidence_tier", "observational") if isinstance(result, dict) else "observational",
        "claim_boundary": (
            result.get("claim_boundary")
            if isinstance(result, dict) and result.get("claim_boundary")
            else "事件先于指标变化的时序相关,非证明因果;不替代医学结论。"
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


def _prediction_backtest(
    *,
    window_days: int,
    events: list[InterventionEvent],
    metrics: dict[str, Any],
    action_effects: list[dict[str, Any]],
) -> dict[str, Any]:
    results = _prediction_backtest_results(events, metrics)
    if not results:
        return _prediction_backtest_placeholder(
            window_days=window_days,
            events=events,
            metrics=metrics,
            action_effects=action_effects,
        )

    summary = Counter(result["verdict"] for result in results)
    confidence_summary = Counter(result["confidence_after"] for result in results)
    return {
        "version": "prediction_backtest_v1",
        "status": "ready",
        "reason": "has_matched_prediction_results",
        "candidate_count": len(results),
        "ready_candidate_count": len(results),
        "window_days": window_days,
        "minimum_window_days": 7,
        "completed_action_count": sum(1 for event in events if event.feedback_status in COMPLETED_STATUSES),
        "eligible_metrics": sorted({result["metric"] for result in results}),
        "requirements": [],
        "summary": {
            "met": summary.get("met", 0),
            "not_met": summary.get("not_met", 0),
            "inconclusive": summary.get("inconclusive", 0),
        },
        "confidence_summary": {
            "high": confidence_summary.get("high", 0),
            "medium": confidence_summary.get("medium", 0),
            "low": confidence_summary.get("low", 0),
        },
        "results": results,
        "boundary": "预测回测只比较预期信号与窗口内实际变化, 属观察性复盘, 不证明单个行动造成指标变化。",
    }


def _prediction_backtest_results(
    events: list[InterventionEvent],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        if event.feedback_status not in COMPLETED_STATUSES:
            continue
        snapshot = event.action_snapshot or {}
        prediction = snapshot.get("prediction") or snapshot.get("prediction_record")
        if not isinstance(prediction, dict):
            continue
        metric = _prediction_metric(prediction, snapshot)
        if not metric or metric not in metrics:
            continue
        change = metrics[metric]
        if change.get("status") != "present" or change.get("delta") is None:
            continue
        prediction_id = str(prediction.get("id") or f"{event.action_key}:{metric}")
        key = (prediction_id, metric)
        if key in seen:
            continue
        seen.add(key)

        observed_delta = change.get("delta")
        expected_signal = _expected_signal(prediction, metric)
        verdict = _prediction_verdict(expected_signal, observed_delta)
        confidence_before = str(prediction.get("confidence") or "low")
        downgrade_reason = _prediction_downgrade_reason(prediction, confidence_before)
        if downgrade_reason:
            verdict = "inconclusive"
        results.append({
            "prediction_id": prediction_id,
            "source": prediction.get("source") or prediction.get("source_model"),
            "source_model": prediction.get("source_model"),
            "prediction_type": prediction.get("prediction_type"),
            "domain": prediction.get("domain"),
            "action_key": event.action_key,
            "action_title": event.action_title,
            "metric": metric,
            "unit": prediction.get("unit"),
            "horizon_days": prediction.get("horizon_days") or expected_signal.get("horizon_days"),
            "baseline": prediction.get("baseline") if prediction.get("baseline") is not None else change.get("first"),
            "baseline_date": change.get("first_date"),
            "expected_signal": expected_signal,
            "uncertainty": prediction.get("uncertainty"),
            "evidence_tier": prediction.get("evidence_tier"),
            "model_version": prediction.get("model_version"),
            "review_hint": prediction.get("review_hint"),
            "requires_clinician": bool(prediction.get("requires_clinician", False)),
            "actual_result": {
                "current": change.get("current"),
                "current_date": change.get("current_date"),
            },
            "observed_delta": observed_delta,
            "verdict": verdict,
            "downgrade_reason": downgrade_reason,
            "confidence_before": confidence_before,
            "confidence_after": _confidence_after(confidence_before, verdict),
            "explanation": _prediction_explanation(verdict),
            "attribution": "prediction_backtest_not_causation",
            "boundary": prediction.get("claim_boundary")
            or "观察性回测, 不证明单个行动造成指标变化。",
        })
    return results


def _prediction_timeline(
    prediction_backtest: dict[str, Any],
    events: list[InterventionEvent],
) -> list[dict[str, Any]]:
    """Turn ready prediction backtests into an observation-only review timeline."""
    if prediction_backtest.get("status") != "ready":
        return []
    results = prediction_backtest.get("results")
    if not isinstance(results, list):
        return []

    events_by_action = {
        event.action_key: event
        for event in events
        if event.feedback_status in COMPLETED_STATUSES
    }
    timeline: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        action_key = str(result.get("action_key") or "")
        event = events_by_action.get(action_key)
        if event is None:
            continue

        prediction_id = str(result.get("prediction_id") or f"{action_key}:{result.get('metric')}")
        metric = str(result.get("metric") or "unknown")
        actual_result = result.get("actual_result") if isinstance(result.get("actual_result"), dict) else {}
        expected_signal = result.get("expected_signal") if isinstance(result.get("expected_signal"), dict) else {}
        horizon_days = result.get("horizon_days") or expected_signal.get("horizon_days")
        direction = expected_signal.get("direction") or "change"
        boundary = (
            result.get("boundary")
            or prediction_backtest.get("boundary")
            or "观察性回测, 不证明单个行动造成指标变化。"
        )

        timeline.extend([
            {
                "id": f"{prediction_id}:prediction",
                "prediction_id": prediction_id,
                "event_type": "prediction_created",
                "occurred_at": result.get("baseline_date") or event.plan_date.isoformat(),
                "title": f"预测: {metric}",
                "summary": _prediction_signal_summary(horizon_days, metric, direction),
                "metric": metric,
                "status": "predicted",
                "confidence": result.get("confidence_before"),
                "boundary": boundary,
            },
            {
                "id": f"{prediction_id}:action",
                "prediction_id": prediction_id,
                "event_type": "action_executed",
                "occurred_at": event.plan_date.isoformat(),
                "title": f"执行: {result.get('action_title') or event.action_title}",
                "summary": f"已完成行动, 等待 {metric} 结果复盘",
                "metric": metric,
                "status": event.feedback_status,
                "confidence": result.get("confidence_before"),
                "boundary": boundary,
            },
            {
                "id": f"{prediction_id}:outcome",
                "prediction_id": prediction_id,
                "event_type": "outcome_observed",
                "occurred_at": actual_result.get("current_date") or result.get("baseline_date") or event.plan_date.isoformat(),
                "title": f"实际: {metric}",
                "summary": f"实际 {metric}: {_display_value(actual_result.get('current'))}, 变化 {_display_value(result.get('observed_delta'))}",
                "metric": metric,
                "status": "observed",
                "confidence": result.get("confidence_after"),
                "boundary": boundary,
            },
            {
                "id": f"{prediction_id}:review",
                "prediction_id": prediction_id,
                "event_type": "review_verdict",
                "occurred_at": actual_result.get("current_date") or event.plan_date.isoformat(),
                "title": f"复盘: {_prediction_verdict_label(str(result.get('verdict') or 'inconclusive'))}",
                "summary": result.get("explanation") or _prediction_explanation(str(result.get("verdict") or "inconclusive")),
                "metric": metric,
                "status": result.get("verdict") or "inconclusive",
                "confidence": result.get("confidence_after"),
                "boundary": boundary,
            },
        ])
    return timeline


def _prediction_signal_summary(horizon_days: Any, metric: str, direction: Any) -> str:
    if horizon_days:
        return f"{horizon_days} 天内观察 {metric} {direction}"
    return f"观察 {metric} {direction}"


def _prediction_verdict_label(verdict: str) -> str:
    return {
        "met": "支持",
        "not_met": "未支持",
        "inconclusive": "数据不足",
    }.get(verdict, "数据不足")


def _display_value(value: Any) -> str:
    return "—" if value is None else str(value)


def _prediction_metric(prediction: dict[str, Any], snapshot: dict[str, Any]) -> str | None:
    expected_signal = prediction.get("expected_signal")
    if isinstance(expected_signal, dict) and expected_signal.get("metric"):
        return str(expected_signal["metric"])
    if prediction.get("metric"):
        return str(prediction["metric"])
    metric = snapshot.get("verification_metric") or snapshot.get("metric_key")
    return str(metric) if metric else None


def _expected_signal(prediction: dict[str, Any], metric: str) -> dict[str, Any]:
    raw = prediction.get("expected_signal")
    if isinstance(raw, dict):
        signal = dict(raw)
    else:
        signal = {}
    signal.setdefault("metric", metric)
    if prediction.get("direction"):
        signal.setdefault("direction", prediction.get("direction"))
    if prediction.get("expected_delta") is not None:
        signal.setdefault("expected_delta", prediction.get("expected_delta"))
    if prediction.get("horizon_days") is not None:
        signal.setdefault("horizon_days", prediction.get("horizon_days"))
    if prediction.get("baseline") is not None:
        signal.setdefault("baseline", prediction.get("baseline"))
    return signal


def _prediction_verdict(expected_signal: dict[str, Any], observed_delta: float | int | None) -> str:
    if observed_delta is None:
        return "inconclusive"
    direction = str(expected_signal.get("direction") or "").lower()
    expected_delta = expected_signal.get("expected_delta")
    if direction == "down":
        if isinstance(expected_delta, (int, float)):
            return "met" if observed_delta <= expected_delta else "not_met"
        return "met" if observed_delta < 0 else "not_met"
    if direction == "up":
        if isinstance(expected_delta, (int, float)):
            return "met" if observed_delta >= expected_delta else "not_met"
        return "met" if observed_delta > 0 else "not_met"
    if direction == "stable":
        tolerance = expected_signal.get("tolerance")
        if isinstance(tolerance, (int, float)):
            return "met" if abs(observed_delta) <= tolerance else "not_met"
        return "met" if observed_delta == 0 else "not_met"
    return "inconclusive"


def _prediction_downgrade_reason(prediction: dict[str, Any], confidence_before: str) -> str | None:
    if confidence_before == "low" or prediction.get("confounders"):
        return "low_confidence_or_confounders"
    return None


def _confidence_after(confidence_before: str, verdict: str) -> str:
    if verdict == "met":
        return confidence_before
    if verdict == "inconclusive":
        return "low"
    return {"high": "medium", "medium": "low", "med": "low"}.get(confidence_before, "low")


def _prediction_explanation(verdict: str) -> str:
    if verdict == "met":
        return "实际变化与预测方向一致, 支持继续当前策略并继续观察。"
    if verdict == "not_met":
        return "实际变化未达到预测信号, 需要复盘执行、混杂因素或调整策略。"
    return "数据不足或预测信号不明确, 暂不判断。"


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
