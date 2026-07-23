from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ReportWindow:
    report_date: date
    start_utc: datetime
    end_utc: datetime


def previous_beijing_day(now: datetime) -> ReportWindow:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    report_date = now.astimezone(BEIJING).date() - timedelta(days=1)
    start = datetime.combine(report_date, time.min, BEIJING)
    end = start + timedelta(days=1)
    return ReportWindow(report_date, start.astimezone(timezone.utc), end.astimezone(timezone.utc))
