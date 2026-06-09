"""Fetch one merged GarminData row per date across multiple sources.

Multi-source ingest (Apple Watch + RingConn + Garmin) stores up to one row per
(user, date, data_source). Any service that aggregates GarminData over a window
(``func.avg`` / ``func.sum`` / iterating ``.all()`` and averaging) now sees 2-3
rows per date and double-counts. This helper collapses each date to a single row
via the per-metric source priority (see ``device_source_priority``), so callers
can aggregate over real days.

Returns lightweight ``SimpleNamespace`` rows exposing the same attribute names as
``GarminData`` (``record_date`` + every metric in the priority map), so existing
``r.hrv`` / ``r.sleep_score`` access keeps working unchanged.
"""
from __future__ import annotations

from datetime import date as _date
from types import SimpleNamespace
from typing import Any, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.device_source_priority import METRIC_SOURCE_PRIORITY, merge_daily_by_priority

# 合并后行暴露的指标列 (priority 表里的全部 key).
_MERGE_KEYS: List[str] = list(METRIC_SOURCE_PRIORITY.keys())


def merged_daily_rows(
    db: Session,
    user_id: int,
    *,
    since: Optional[_date] = None,
    until: Optional[_date] = None,
    require_metrics: Optional[Sequence[str]] = None,
    extra_metrics: Optional[Sequence[str]] = None,
    ascending: bool = False,
) -> List[SimpleNamespace]:
    """每个 record_date 一行,跨源按优先级合并。

    since/until: 闭区间日期过滤 (None 不限).
    require_metrics: 仅保留这些指标至少一个非空的日期 (镜像旧 ``.isnot(None)`` 过滤).
    extra_metrics: 额外要暴露的列名 (优先级表外的字段, 按 DEFAULT_PRIORITY 合并).
    ascending: True 按日期升序, 否则降序 (默认最新在前).
    """
    from app.models.daily_health import GarminData

    keys = list(_MERGE_KEYS)
    for m in list(require_metrics or []) + list(extra_metrics or []):
        if m not in keys:
            keys.append(m)

    q = db.query(GarminData).filter(GarminData.user_id == user_id)
    if since is not None:
        q = q.filter(GarminData.record_date >= since)
    if until is not None:
        q = q.filter(GarminData.record_date <= until)
    rows = q.all()

    # 按日期分组
    by_date: dict[_date, list] = {}
    for r in rows:
        by_date.setdefault(r.record_date, []).append(r)

    out: List[SimpleNamespace] = []
    for rd, day_rows in by_date.items():
        merged = merge_daily_by_priority(day_rows, keys)
        if require_metrics and all(merged.get(m) is None for m in require_metrics):
            continue
        ns_kwargs: dict[str, Any] = {k: merged.get(k) for k in keys}
        ns_kwargs["record_date"] = rd
        ns_kwargs["_source_by_metric"] = merged.get("_source_by_metric", {})
        out.append(SimpleNamespace(**ns_kwargs))

    out.sort(key=lambda r: r.record_date, reverse=not ascending)
    return out


def merged_metric_series(
    db: Session,
    user_id: int,
    metric: str,
    *,
    since: Optional[_date] = None,
    until: Optional[_date] = None,
    ascending: bool = True,
) -> List[tuple[_date, Any]]:
    """单指标按日期去重后的 (date, value) 序列 (非空值)。

    用于"读单条指标序列"的服务: 每天按该指标优先级源取一个值, 避免多源重复。
    """
    rows = merged_daily_rows(
        db, user_id, since=since, until=until,
        require_metrics=[metric], extra_metrics=[metric], ascending=ascending,
    )
    return [(r.record_date, getattr(r, metric)) for r in rows if getattr(r, metric) is not None]
