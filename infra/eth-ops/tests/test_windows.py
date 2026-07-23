from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from staking_report.windows import previous_beijing_day  # noqa: E402


def test_previous_beijing_day_uses_local_natural_day() -> None:
    window = previous_beijing_day(datetime(2026, 7, 23, 1, 1, tzinfo=timezone.utc))
    assert window.report_date.isoformat() == "2026-07-22"
    assert window.start_utc.isoformat() == "2026-07-21T16:00:00+00:00"
    assert window.end_utc.isoformat() == "2026-07-22T16:00:00+00:00"
