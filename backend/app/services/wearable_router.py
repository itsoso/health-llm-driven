"""Wearable Router v1: metric-level source arbitration and freshness.

This is a thin product contract over existing multi-source wearable utilities:
`GarminData.data_source`, `device_source_priority`, and
`device_comparison_service`. It does not diagnose, prescribe, or replace
SafetyGuardian. It only explains which source won and whether the data is stale
or conflicting enough to surface as a low-friction Agenda data-quality item.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.services.device_comparison_service import compare_sources
from app.services.device_source_priority import (
    WORST_VALUE_METRICS,
    pick_value,
    priority_for,
)
from app.utils.timezone import get_china_today


DEFAULT_ROUTER_METRICS = (
    "hrv",
    "resting_heart_rate",
    "total_sleep_duration",
    "sleep_score",
    "spo2_avg",
    "training_readiness_score",
    "acute_load",
    "steps",
)

METRIC_META: dict[str, dict[str, Any]] = {
    "hrv": {"label": "HRV", "unit": "ms", "max_freshness_hours": 48},
    "resting_heart_rate": {"label": "静息心率", "unit": "bpm", "max_freshness_hours": 48},
    "total_sleep_duration": {"label": "睡眠时长", "unit": "min", "max_freshness_hours": 36},
    "sleep_score": {"label": "睡眠评分", "unit": "", "max_freshness_hours": 36},
    "spo2_avg": {"label": "SpO2", "unit": "%", "max_freshness_hours": 36},
    "training_readiness_score": {"label": "训练准备度", "unit": "", "max_freshness_hours": 36},
    "acute_load": {"label": "急性训练负荷", "unit": "", "max_freshness_hours": 36},
    "steps": {"label": "步数", "unit": "", "max_freshness_hours": 24},
}

_SOURCE_LABELS = {
    "apple-watch": "Apple Watch",
    "garmin": "Garmin",
    "garmin-app": "Garmin",
    "manual": "手动记录",
    "oura": "Oura",
    "ringconn": "RingConn",
    "unknown": "未知来源",
    "withings-app": "Withings",
}

_SOURCE_RELIABILITY = {
    "apple-watch": "high",
    "garmin": "high",
    "garmin-app": "medium",
    "manual": "low",
    "oura": "medium",
    "ringconn": "high",
    "unknown": "low",
    "withings-app": "medium",
}

_CONFLICT_THRESHOLD = 0.75


@dataclass(frozen=True)
class _MetricPick:
    value: Any
    row: Any
    source: str


def _source_label(source: str | None) -> str:
    return _SOURCE_LABELS.get(source or "unknown", str(source or "unknown"))


def _metric_meta(metric: str) -> dict[str, Any]:
    return METRIC_META.get(metric, {
        "label": metric,
        "unit": "",
        "max_freshness_hours": 48,
    })


def _row_value(row: Any, metric: str) -> Any:
    return getattr(row, metric, None)


def _row_source(row: Any) -> str:
    return getattr(row, "data_source", None) or "garmin"


def _latest_rows_by_source(rows: Iterable[Any], metric: str) -> list[Any]:
    latest: dict[str, Any] = {}
    for row in sorted(rows, key=lambda r: r.record_date, reverse=True):
        if _row_value(row, metric) is None:
            continue
        latest.setdefault(_row_source(row), row)
    return list(latest.values())


def _pick_metric(rows: list[Any], metric: str) -> _MetricPick | None:
    latest_rows = _latest_rows_by_source(rows, metric)
    if not latest_rows:
        return None
    value, source = pick_value(latest_rows, metric)
    if value is None or source is None:
        return None
    for row in latest_rows:
        if _row_source(row) == source and _row_value(row, metric) == value:
            return _MetricPick(value=value, row=row, source=source)
    return None


def _agreement_for(metric: str, latest_rows: list[Any]) -> float | None:
    values_by_source = {
        _row_source(row): {metric: float(_row_value(row, metric))}
        for row in latest_rows
        if _row_value(row, metric) is not None
    }
    if len(values_by_source) < 2:
        return None
    for comp in compare_sources(values_by_source):
        if comp.get("metric") == metric:
            return comp.get("agreement")
    return None


def _freshness_hours(row: Any, target_date) -> int:
    return max(0, int((target_date - row.record_date).days) * 24)


def _confidence(
    *,
    reliability: str,
    freshness_hours: int,
    max_freshness_hours: int,
    agreement_score: float | None,
) -> str:
    if freshness_hours > max_freshness_hours:
        return "low"
    if agreement_score is not None and agreement_score < _CONFLICT_THRESHOLD:
        return "low"
    if reliability == "high" and (agreement_score is None or agreement_score >= 0.85):
        return "high"
    if reliability in {"high", "medium"}:
        return "medium"
    return "low"


def build_snapshot(
    db: Session,
    user_id: int,
    *,
    metrics: list[str] | tuple[str, ...] | None = None,
    window_days: int = 14,
    target_date=None,
) -> dict[str, Any]:
    """Build a deterministic wearable-router snapshot for one user."""
    from app.models.daily_health import GarminData

    target_date = target_date or get_china_today()
    metrics = tuple(metrics or DEFAULT_ROUTER_METRICS)
    cutoff = target_date - timedelta(days=window_days)
    rows = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= cutoff,
            GarminData.record_date <= target_date,
        )
        .all()
    )
    if not rows:
        return {
            "target_date": str(target_date),
            "window_days": window_days,
            "metrics": {},
            "sources": [],
            "data_quality_issues": [],
        }

    metric_out: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    sources = sorted({_row_source(row) for row in rows})

    for metric in metrics:
        meta = _metric_meta(metric)
        latest_rows = _latest_rows_by_source(rows, metric)
        picked = _pick_metric(rows, metric)
        if picked is None:
            continue

        source_values = {
            _row_source(row): _row_value(row, metric)
            for row in latest_rows
            if _row_value(row, metric) is not None
        }
        agreement_score = _agreement_for(metric, latest_rows)
        fresh_hours = _freshness_hours(picked.row, target_date)
        max_fresh = int(meta["max_freshness_hours"])
        reliability = _SOURCE_RELIABILITY.get(picked.source, "low")
        confidence = _confidence(
            reliability=reliability,
            freshness_hours=fresh_hours,
            max_freshness_hours=max_fresh,
            agreement_score=agreement_score,
        )
        safety_policy = "worst_value" if metric in WORST_VALUE_METRICS else "normal"
        priority = priority_for(metric)
        source_reason = (
            f"{_source_label(picked.source)} 按 {meta['label']} 来源优先级胜出"
            if picked.source in priority
            else f"{_source_label(picked.source)} 是该指标最近可用来源"
        )

        metric_out[metric] = {
            "metric": metric,
            "label": meta["label"],
            "value": picked.value,
            "unit": meta["unit"],
            "winning_source": picked.source,
            "source_reason": source_reason,
            "freshness_hours": fresh_hours,
            "reliability": reliability,
            "agreement_score": agreement_score,
            "confidence": confidence,
            "safety_policy": safety_policy,
            "source_values": source_values,
        }

        if fresh_hours > max_fresh:
            issues.append({
                "kind": "stale",
                "metric": metric,
                "label": meta["label"],
                "severity": "medium",
                "title": f"{meta['label']} 数据已过期",
                "message": f"{_source_label(picked.source)} 的 {meta['label']} 已约 {fresh_hours} 小时未更新。",
                "stale_hours": fresh_hours,
                "winning_source": picked.source,
            })
        if agreement_score is not None and agreement_score < _CONFLICT_THRESHOLD:
            issues.append({
                "kind": "conflict",
                "metric": metric,
                "label": meta["label"],
                "severity": "medium",
                "title": f"{meta['label']} 多设备差异较大",
                "message": f"{meta['label']} 多源一致性 {agreement_score:.0%}, 先降置信不平均。",
                "agreement_score": agreement_score,
                "source_values": source_values,
                "winning_source": picked.source,
            })

    return {
        "target_date": str(target_date),
        "window_days": window_days,
        "metrics": metric_out,
        "sources": sources,
        "data_quality_issues": issues,
    }


def data_quality_issues(
    db: Session,
    user_id: int,
    *,
    max_items: int = 3,
) -> list[dict[str, Any]]:
    snapshot = build_snapshot(db, user_id)
    return list(snapshot.get("data_quality_issues") or [])[:max_items]
