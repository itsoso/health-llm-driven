"""Bounded calendar reads; authorization stays in the capability policy.

Dates are inclusive business dates, not upload timestamps. Sleep daily rows use
wake-date attribution: last night means today's row, never the latest old row.
The daily schema retains clock times rather than full episode timestamps, so it
cannot prove sleep episode completeness or reattribute travel across timezones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
import json
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Shanghai"
MAX_CALENDAR_DAYS = 31
MAX_CALENDAR_ROWS = 256
MAX_CALENDAR_RESULT_CHARS = 24000
SUPPORTED_CALENDAR_DIMENSIONS = frozenset({"diet", "sleep"})
_DATE_RE = re.compile(r"(?<!\d)(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})(?:日|号)?(?!\d)")
_RELATIVE_RE = re.compile(r"前天|昨天|昨日|今天|今日|昨晚|昨夜")
_WEEKDAY_RE = re.compile(r"(本周|这周|上周)([一二三四五六日天])")


@dataclass(frozen=True)
class QueryWindow:
    start_date: date
    end_date: date
    timezone: str = DEFAULT_TIMEZONE

    def as_dict(self) -> dict[str, str]:
        return {"start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(), "timezone": self.timezone}


def parse_query_window(args: Mapping[str, Any]) -> QueryWindow:
    """Validate explicit bounds. No partial dates or rolling-window fallback."""
    try:
        start = date.fromisoformat(str(args["start_date"]))
        end = date.fromisoformat(str(args["end_date"]))
        zone = str(args.get("timezone") or DEFAULT_TIMEZONE)
        ZoneInfo(zone)
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("calendar_query_window_invalid") from exc
    if not 0 <= (end - start).days < MAX_CALENDAR_DAYS:
        raise ValueError("calendar_query_window_out_of_bounds")
    return QueryWindow(start, end, zone)


def resolve_calendar_query_window(
    text: str, reference_now: datetime, dimension: str,
    *, timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, str] | None:
    """Resolve an explicit day or bounded interval; leave ambiguity blocked.

    This function supplies dates only, never read authorization or dimension
    selection. The caller must still validate subject, cancellation and intent.
    """
    if dimension not in SUPPORTED_CALENDAR_DIMENSIONS:
        return None
    local = (reference_now.replace(tzinfo=ZoneInfo(timezone_name))
             if reference_now.tzinfo is None else reference_now.astimezone(ZoneInfo(timezone_name)))
    absolute = list(_DATE_RE.finditer(text))
    relative = list(_RELATIVE_RE.finditer(text))
    weekdays = list(_WEEKDAY_RE.finditer(text))
    remainder = _WEEKDAY_RE.sub("", _RELATIVE_RE.sub("", _DATE_RE.sub("", text)))
    if re.search(r"明天|后天|\d{1,2}月|\d{1,2}[-/]\d{1,2}|(?:周|星期)[一二三四五六日天]", remainder):
        return None
    if re.search(r"下周|上个月|本月|去年|今年|至今|以来|之前|以前|之后|以后|截至|截止|最近|过去|开始|前后", text):
        return None
    # Only an explicit inclusive interval is accepted; comparisons are separate
    # tasks and must not read intervening days without authorization.
    if len(absolute) == 2 and not relative and not weekdays:
        first, last = absolute
        if not re.fullmatch(r"\s*(?:到|至|~|～)\s*", text[first.end():last.start()]):
            return None
        if re.search(r"上周|本周|这周|晚|夜", text):
            return None
        try:
            start = date(*(int(part) for part in first.groups()))
            end = date(*(int(part) for part in last.groups()))
            window = parse_query_window(QueryWindow(start, end, timezone_name).as_dict())
        except ValueError:
            return None
        return window.as_dict() if end <= local.date() else None
    if len(absolute) + len(relative) + len(weekdays) != 1:
        return None
    if weekdays:
        hit = weekdays[0]
        week, weekday = hit.groups()
        offset = "一二三四五六日".index(weekday.replace("天", "日"))
        target = local.date() - timedelta(days=local.weekday()) + timedelta(days=offset)
        if week == "上周":
            target -= timedelta(days=7)
    elif re.search(r"上周|本周|这周", text):
        return None
    elif absolute:
        hit = absolute[0]
        try:
            target = date(*(int(part) for part in hit.groups()))
        except ValueError:
            return None
    else:
        hit = relative[0]
        word = hit.group()
        offsets = {"前天": -2, "昨天": -1, "昨日": -1, "今天": 0, "今日": 0,
                   "昨晚": -1, "昨夜": -1}
        target = local.date() + timedelta(days=offsets[word])
    if dimension == "sleep" and (
        hit.group() in {"昨晚", "昨夜"} or re.match(r"(?:的)?(?:晚上|夜晚|晚间|夜间|晚|夜)", text[hit.end():])
    ):
        target += timedelta(days=1)
    if target > local.date():
        return None
    return QueryWindow(target, target, timezone_name).as_dict()


def read_calendar_health_query(
    db, user_id: int, dimension: str, window: QueryWindow,
) -> dict[str, Any]:
    """Read only owned rows in exactly this window; DB failures propagate.

    No remote sync is initiated and no absence is converted to a zero score.
    The returned timestamps are row update times, not device-sync guarantees.
    """
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("calendar_query_owner_required")
    # A dataclass constructed by a caller must not bypass bound validation.
    window = parse_query_window(window.as_dict())
    if dimension not in SUPPORTED_CALENDAR_DIMENSIONS:
        raise ValueError("calendar_query_dimension_unsupported")
    from app.models.daily_health import DietRecord, GarminData

    model = DietRecord if dimension == "diet" else GarminData
    rows = (db.query(model).filter(model.user_id == user_id,
                                  model.record_date >= window.start_date,
                                  model.record_date <= window.end_date)
            .order_by(model.record_date, model.id).limit(MAX_CALENDAR_ROWS + 1).all())
    if len(rows) > MAX_CALENDAR_ROWS:
        raise ValueError("calendar_query_result_limit_exceeded: 记录较多，请缩小查询日期范围。")
    result: dict[str, Any] = {
        "dimension": dimension, "window": window.as_dict(), "records": [],
        "availability": "no_data", "limitations": [],
    }
    if dimension == "diet":
        keys = ("id", "record_date", "meal_type", "meal_time", "food_name", "food_items",
                "quantity", "unit", "calories", "protein", "carbs", "fat", "fiber")
        result["records"] = [{key: _serial(getattr(row, key)) for key in keys} for row in rows]
        if rows:
            result["availability"] = "available"
        return _bounded_result(result)

    from app.services.multi_source_merger import merge_rows
    keys = ("sleep_score", "total_sleep_duration", "deep_sleep_duration",
            "rem_sleep_duration", "light_sleep_duration", "awake_duration",
            "sleep_start_time", "sleep_end_time")
    result["date_attribution"] = "wake_date"
    result["sync_status"] = "unknown"
    result["limitations"] = ["sync_status_unknown", "daily_rows_not_full_episode_timestamps",
                             "missing_metric_is_unknown_not_abnormal"]
    by_day: dict[date, list[Any]] = {}
    for row in rows:
        by_day.setdefault(row.record_date, []).append(row)
    for day, candidates in sorted(by_day.items()):
        merged = merge_rows(candidates, keys)
        values = merged["values"]
        if all(values.get(key) is None for key in keys[:6]):
            continue
        row = {key: _serial(value) for key, value in values.items()}
        row.update({"record_date": day.isoformat(), "sources": merged["sources"],
                    "source_row_updates": [{"source": candidate.data_source,
                                            "updated_at": _serial(candidate.updated_at)}
                                           for candidate in candidates]})
        result["records"].append(row)
    if result["records"]:
        missing = any(row.get(key) is None for row in result["records"] for key in keys)
        expected_days = (window.end_date - window.start_date).days + 1
        result["availability"] = "partial" if missing or len(result["records"]) < expected_days else "available"
    return _bounded_result(result)


def _bounded_result(result: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(result, ensure_ascii=False)) > MAX_CALENDAR_RESULT_CHARS:
        raise ValueError("calendar_query_result_limit_exceeded: 内容较多，请缩小查询日期范围。")
    return result


def _serial(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value
