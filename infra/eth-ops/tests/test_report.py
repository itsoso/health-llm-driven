from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from staking_report.report import DailyReport, render_telegram  # noqa: E402


def test_incomplete_values_are_not_rendered_as_zero() -> None:
    report = DailyReport("2026-07-22", Decimal("0.001"), Decimal("0.0002"), None, None, "healthy", False)
    text = render_telegram(report)
    assert "MEV: 未确认" in text
    assert "人民币: 暂不可用" in text
    assert "数据完整性: incomplete" in text


def test_first_day_reports_baseline_building() -> None:
    report = DailyReport("2026-07-22", None, None, None, None, "healthy", False)
    assert "基线建立中" in render_telegram(report)
