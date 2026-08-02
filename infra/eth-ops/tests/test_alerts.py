from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from staking_report.alerts import should_send  # noqa: E402


def test_alert_cooldown() -> None:
    now = datetime.now(timezone.utc)
    assert should_send(None, now) is True
    assert should_send(now - timedelta(minutes=29), now) is False
    assert should_send(now - timedelta(minutes=31), now) is True
