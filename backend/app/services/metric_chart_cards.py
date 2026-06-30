"""Metric chart payload builders for chat dynamic cards."""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect, text as sql_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_metric_chart(db: Session, *, user_id: int, query: str) -> Optional[Dict[str, Any]]:
    """Build a compact, read-only metric chart payload for Chat dynamic cards."""
    if not _is_metric_chart_query(query):
        return None

    days = _metric_chart_days(query)
    end = date.today()
    start = end - timedelta(days=days)
    try:
        from app.services.device_source_priority import pick_value

        bind = db.get_bind()
        columns = {col["name"] for col in sa_inspect(bind).get_columns("garmin_data")}
        if "record_date" not in columns or "hrv" not in columns:
            return None
        id_expr = "id" if "id" in columns else "0 AS id"
        source_expr = "data_source" if "data_source" in columns else "'garmin' AS data_source"
        raw_rows = db.execute(
            sql_text(
                f"""
                SELECT {id_expr}, record_date, hrv, {source_expr}
                FROM garmin_data
                WHERE user_id = :user_id
                  AND record_date >= :start
                  AND record_date <= :end
                  AND hrv IS NOT NULL
                ORDER BY record_date ASC, id ASC
                """
            ),
            {"user_id": user_id, "start": start, "end": end},
        ).mappings().all()
    except Exception as e:
        logger.debug("metric chart card failed: %s", e)
        return None

    rows_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for raw in raw_rows:
        row_date = _iso_date(raw.get("record_date"))
        if not row_date:
            continue
        rows_by_date.setdefault(row_date, []).append({
            "hrv": raw.get("hrv"),
            "data_source": raw.get("data_source") or "garmin",
        })

    series: List[Dict[str, Any]] = []
    values: List[float] = []
    for row_date, day_rows in rows_by_date.items():
        raw_value, source = pick_value(day_rows, "hrv")
        value = _normalize_hrv_ms(raw_value)
        if value is None:
            continue
        values.append(value)
        series.append({"date": row_date, "value": value, "source": source or "unknown"})

    if len(series) < 2:
        return None

    rolling = _rolling_mean(values, window=7)
    for point, rolling_value in zip(series, rolling):
        if rolling_value is not None:
            point["rolling_7d"] = rolling_value

    latest = series[-1]
    last_7d_avg = _mean(values[-7:])
    last_30d_avg = _mean(values[-30:])
    prev_30d_avg = _mean(values[-60:-30]) if len(values) >= 31 else None
    delta_30 = (
        round(last_30d_avg - prev_30d_avg, 1)
        if last_30d_avg is not None and prev_30d_avg is not None
        else None
    )

    return {
        "metric": "hrv",
        "title": "最近半年 HRV" if days >= 180 else f"最近{days}天 HRV",
        "unit": "ms",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "coverage": {"days_with_data": len(series), "days_in_window": days + 1},
        "latest": {
            "date": latest["date"],
            "value": latest["value"],
            "source": latest.get("source"),
        },
        "summary": {
            "avg": _mean(values),
            "last_7d_avg": last_7d_avg,
            "last_30d_avg": last_30d_avg,
            "prev_30d_avg": prev_30d_avg,
            "last_30_vs_prev_30_delta": delta_30,
        },
        "series": series,
        "boundary": "HRV 趋势仅用于健康管理参考, 不替代诊断或治疗。",
    }


def _is_metric_chart_query(q: str) -> bool:
    if _is_record_intent(q):
        return False
    ql = q.lower()
    has_metric = bool(re.search(r"\bhrv\b|恢复变异|心率变异|心率变异性", ql))
    has_chart = bool(re.search(r"曲线|趋势|走势图|折线|图表|画|绘制|变化|最近半年|半年|6个月|六个月", ql))
    return has_metric and has_chart


def _is_record_intent(q: str) -> bool:
    return bool(re.search(r"记录|打卡|吃了|喝了|服药|刚吃|刚喝", q))


def _metric_chart_days(q: str) -> int:
    ql = q.lower()
    if re.search(r"半年|6个月|六个月|180天|一百八十天", ql):
        return 183
    if re.search(r"90天|九十天|三个月|3个月", ql):
        return 90
    if re.search(r"30天|三十天|一个月|月度|最近一月", ql):
        return 30
    if re.search(r"14天|两周|2周", ql):
        return 14
    if re.search(r"7天|七天|一周|这周", ql):
        return 7
    return 183


def _normalize_hrv_ms(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v < 2:
        v *= 1000.0
    if v < 5 or v > 250:
        return None
    return round(v, 1)


def _mean(values: List[float]) -> Optional[float]:
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 1)


def _rolling_mean(values: List[float], window: int = 7) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for idx in range(len(values)):
        left = max(0, idx - window + 1)
        chunk = values[left:idx + 1]
        out.append(_mean(chunk) if len(chunk) >= min(3, window) else None)
    return out


def _iso_date(value: Any) -> Optional[str]:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return None
