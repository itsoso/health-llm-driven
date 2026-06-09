"""Multi-source field merger for GarminData rows (thin wrapper).

The actual per-metric source priority policy lives in ``device_source_priority``
(single source of truth, pure/testable). This module keeps the historical
``merge_field`` / ``merge_rows`` API used by ``multi_source_integration_service``
but delegates all priority decisions to that module — there is exactly ONE
priority table in the codebase.

After Apple HealthKit ingest, the same (user_id, record_date) can have multiple
GarminData rows (one per data_source). ``merge_rows`` picks, per field, the value
from the highest-priority source that has a non-null value.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from app.services.device_source_priority import pick_value


def merge_field(rows: Sequence[Any], field: str) -> tuple[Any, Optional[str]]:
    """单字段按优先级挑值. 返回 (value, winning_source) — 都 None 则两个 None."""
    return pick_value(rows, field)


def merge_rows(rows: Sequence[Any], fields: Sequence[str]) -> Dict[str, Any]:
    """对多行 GarminData 同 (user, date) 按字段独立 source 优先级合成.

    返回:
      {
        "values": {field: value},
        "sources": {field: data_source},  # 哪个源中标
      }
    """
    out_vals: Dict[str, Any] = {}
    out_srcs: Dict[str, str] = {}
    for field in fields:
        v, s = merge_field(rows, field)
        out_vals[field] = v
        if s is not None:
            out_srcs[field] = s
    return {"values": out_vals, "sources": out_srcs}
