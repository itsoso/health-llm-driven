"""Project an authorized daily oxygen read; never query or infer a wider range."""
from datetime import date, timedelta
import math
import re

from app.services.agent_kernel.health_semantics import (
    resolve_health_read_act,
)
from app.services.agent_query_window import parse_query_window
from app.services.device_source_priority import excluded_sources
from app.utils.number_format import format_card_numbers, format_display_number


def requests_owned_chart(snapshot) -> bool:
    """Presentation intent only. Capability policy still authorizes every read."""
    from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
    scope = resolve_owned_read_scope(snapshot)
    act = resolve_health_read_act(snapshot.envelope.text)
    return (scope is not None and scope.query("spo2") is not None
            and act.status == "active" and bool(re.search(r"绘制|画出", act.active_clause)))


def build_owned_spo2_chart(args: dict, payload: object) -> dict | None:
    if not isinstance(payload, dict) or args.get("dimension") != "spo2":
        return None
    if (payload.get("dimension") != "spo2"
            or payload.get("source_scope") != "owned_daily_spo2_summaries_and_samples"
            or payload.get("date_attribution") != "record_date"
            or payload.get("availability") not in {"partial", "available"}
            or payload.get("success") is False or payload.get("error")):
        return None
    try:
        window = parse_query_window(args)
    except ValueError:
        return None
    if window.period is not None or payload.get("window") != window.as_dict():
        return None
    records = payload.get("records")
    if not isinstance(records, list) or len(records) > (window.end_date - window.start_date).days + 1:
        return None
    values: dict[str, float | int | None] = {}
    sources: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            return None
        day = row.get("record_date")
        try:
            parsed_day = date.fromisoformat(day)
        except (TypeError, ValueError):
            return None
        if day in values or not window.start_date <= parsed_day <= window.end_date:
            return None
        metrics, provenance = row.get("daily_metrics"), row.get("daily_sources")
        if not isinstance(metrics, dict) or not isinstance(provenance, dict):
            return None
        value = metrics.get("spo2_avg")
        if value is not None:
            source = provenance.get("spo2_avg")
            if (type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 100
                    or not isinstance(source, str) or not source.strip()
                    or source.lower() in excluded_sources("spo2_avg")):
                return None
            sources.add(source)
        values[day] = value
    if not any(value is not None for value in values.values()):
        return None
    axis = [(window.start_date + timedelta(days=i)).isoformat()
            for i in range((window.end_date - window.start_date).days + 1)]
    latest_day = max(day for day, value in values.items() if value is not None)
    latest_value = format_display_number(values[latest_day])
    return format_card_numbers({
        "v": 1, "component": "line_chart", "title": "血氧饱和度", "unit": "%",
        "x": axis, "series": [{"name": "日均血氧", "points": [values.get(day) for day in axis]}],
        "annotations": [{"x": latest_day, "label": f"{latest_day} · {latest_value}%", "kind": "latest"}], "source": " / ".join(sorted(sources)),
        "data_note": f"{axis[0]} → {axis[-1]} · {window.timezone} · 按记录日期的日均值；缺失日期留空，不代表睡眠期连续监测。",
    })
