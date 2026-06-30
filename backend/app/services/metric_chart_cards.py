"""Metric chart payload builders for chat dynamic cards."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect, text as sql_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricChartConfig:
    key: str
    label: str
    unit: str
    table: str
    value_column: str
    source_column: str
    aliases: str
    normalizer: Callable[[Any], Optional[float]]
    min_points: int = 2


METRIC_CHART_CONFIGS: List[MetricChartConfig] = [
    MetricChartConfig(
        key="hrv",
        label="HRV",
        unit="ms",
        table="garmin_data",
        value_column="hrv",
        source_column="data_source",
        aliases=r"\bhrv\b|恢复变异|心率变异|心率变异性",
        normalizer=lambda value: _normalize_range(value, minimum=5, maximum=250, multiplier_under=2, multiplier=1000),
    ),
    MetricChartConfig(
        key="sleep_score",
        label="睡眠评分",
        unit="分",
        table="garmin_data",
        value_column="sleep_score",
        source_column="data_source",
        aliases=r"睡眠评分|睡眠分|睡眠质量|sleep\s*score",
        normalizer=lambda value: _normalize_range(value, minimum=0, maximum=100),
    ),
    MetricChartConfig(
        key="resting_heart_rate",
        label="静息心率",
        unit="bpm",
        table="garmin_data",
        value_column="resting_heart_rate",
        source_column="data_source",
        aliases=r"静息心率|安静心率|resting\s*heart|rhr\b",
        normalizer=lambda value: _normalize_range(value, minimum=25, maximum=140),
    ),
    MetricChartConfig(
        key="body_battery",
        label="身体电量",
        unit="",
        table="garmin_data",
        value_column="body_battery_most_charged",
        source_column="data_source",
        aliases=r"body\s*battery|身体电量|体能电量|身体能量",
        normalizer=lambda value: _normalize_range(value, minimum=0, maximum=100),
    ),
    MetricChartConfig(
        key="steps",
        label="步数",
        unit="步",
        table="garmin_data",
        value_column="steps",
        source_column="data_source",
        aliases=r"步数|steps|走了多少|走路",
        normalizer=lambda value: _normalize_range(value, minimum=0, maximum=100000, decimals=0),
    ),
    MetricChartConfig(
        key="weight",
        label="体重",
        unit="kg",
        table="weight_records",
        value_column="weight",
        source_column="source",
        aliases=r"体重|weight|减重|减脂",
        normalizer=lambda value: _normalize_range(value, minimum=20, maximum=300),
    ),
]


def build_metric_chart(db: Session, *, user_id: int, query: str) -> Optional[Dict[str, Any]]:
    """Build a compact, read-only metric chart payload for Chat dynamic cards."""
    metric = _detect_metric_chart_config(query)
    if metric is None or not _is_metric_chart_query(query, metric):
        return None

    days = _metric_chart_days(query)
    end = date.today()
    start = end - timedelta(days=days)
    try:
        raw_rows = _metric_rows(db, user_id=user_id, metric=metric, start=start, end=end)
    except Exception as e:
        logger.debug("metric chart card failed: %s", e)
        return None

    rows_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for raw in raw_rows:
        row_date = _iso_date(raw.get("record_date"))
        if not row_date:
            continue
        rows_by_date.setdefault(row_date, []).append({
            metric.value_column: raw.get("metric_value"),
            "metric_value": raw.get("metric_value"),
            "data_source": raw.get("data_source") or "unknown",
            "id": raw.get("id") or 0,
        })

    series: List[Dict[str, Any]] = []
    values: List[float] = []
    for row_date, day_rows in rows_by_date.items():
        raw_value, source = _pick_metric_value(day_rows, metric)
        value = metric.normalizer(raw_value)
        if value is None:
            continue
        values.append(value)
        series.append({"date": row_date, "value": value, "source": source or "unknown"})

    if len(series) < metric.min_points:
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
        "metric": metric.key,
        "label": metric.label,
        "title": _chart_title(days, metric.label),
        "unit": metric.unit,
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
        "boundary": f"{metric.label} 趋势仅用于健康管理参考, 不替代诊断或治疗。",
    }


def _metric_rows(
    db: Session,
    *,
    user_id: int,
    metric: MetricChartConfig,
    start: date,
    end: date,
) -> List[Dict[str, Any]]:
    bind = db.get_bind()
    columns = {col["name"] for col in sa_inspect(bind).get_columns(metric.table)}
    if "record_date" not in columns or metric.value_column not in columns:
        return []
    id_expr = "id" if "id" in columns else "0 AS id"
    source_expr = (
        f"{metric.source_column} AS data_source"
        if metric.source_column in columns
        else f"'{_default_source(metric)}' AS data_source"
    )
    raw_rows = db.execute(
        sql_text(
            f"""
            SELECT {id_expr},
                   record_date,
                   {metric.value_column} AS metric_value,
                   {source_expr}
            FROM {metric.table}
            WHERE user_id = :user_id
              AND record_date >= :start
              AND record_date <= :end
              AND {metric.value_column} IS NOT NULL
            ORDER BY record_date ASC, id ASC
            """
        ),
        {"user_id": user_id, "start": start, "end": end},
    ).mappings().all()
    return [dict(row) for row in raw_rows]


def _pick_metric_value(day_rows: List[Dict[str, Any]], metric: MetricChartConfig) -> tuple[Any, Optional[str]]:
    if metric.table == "garmin_data":
        try:
            from app.services.device_source_priority import pick_value

            return pick_value(day_rows, metric.value_column)
        except Exception as e:
            logger.debug("metric chart source priority fallback: %s", e)

    chosen = sorted(day_rows, key=lambda row: int(row.get("id") or 0))[-1]
    return chosen.get("metric_value"), chosen.get("data_source")


def _detect_metric_chart_config(q: str) -> Optional[MetricChartConfig]:
    ql = q.lower()
    for config in METRIC_CHART_CONFIGS:
        if re.search(config.aliases, ql, flags=re.IGNORECASE):
            return config
    return None


def _is_metric_chart_query(q: str, metric: MetricChartConfig) -> bool:
    if _is_record_intent(q):
        return False
    ql = q.lower()
    has_metric = bool(re.search(metric.aliases, ql, flags=re.IGNORECASE))
    has_chart = bool(
        re.search(
            r"曲线|趋势|走势|走势图|折线|图表|画|绘制|变化|历史|最近|近\d+天|最近半年|半年|6个月|六个月",
            ql,
        )
    )
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


def _chart_title(days: int, label: str) -> str:
    return f"最近半年 {label}" if days >= 180 else f"最近{days}天 {label}"


def _default_source(metric: MetricChartConfig) -> str:
    return "garmin" if metric.table == "garmin_data" else "manual"


def _normalize_range(
    value: Any,
    *,
    minimum: float,
    maximum: float,
    decimals: int = 1,
    multiplier_under: Optional[float] = None,
    multiplier: float = 1.0,
) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if multiplier_under is not None and v < multiplier_under:
        v *= multiplier
    if v < minimum or v > maximum:
        return None
    rounded = round(v, decimals)
    return float(int(rounded)) if decimals == 0 else rounded


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
