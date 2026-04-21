"""SpO2 血氧时间序列模块测试"""
import pytest
from app.api.spo2 import _compute_desaturation_events, _build_night_summary
from app.schemas.spo2 import SpO2NightSummary
from datetime import date


class TestDesaturationEvents:
    def test_no_events_stable(self):
        values = [96, 96, 95, 96, 96, 95, 96]
        assert _compute_desaturation_events(values) == 0

    def test_single_drop(self):
        values = [96, 96, 93, 96, 96]
        assert _compute_desaturation_events(values) == 1

    def test_multiple_drops(self):
        values = [96, 93, 96, 92, 96, 91, 96]
        assert _compute_desaturation_events(values) >= 2

    def test_empty_list(self):
        assert _compute_desaturation_events([]) == 0

    def test_single_value(self):
        assert _compute_desaturation_events([95]) == 0

    def test_gradual_decline_no_event(self):
        values = [96, 95, 94, 93, 92]
        assert _compute_desaturation_events(values) == 0

    def test_deep_drop(self):
        values = [96, 96, 88, 96, 96]
        assert _compute_desaturation_events(values) == 1


class TestBuildNightSummary:
    def test_empty_samples(self):
        summary = _build_night_summary(date(2026, 4, 20), [])
        assert summary.data_points == 0
        assert summary.avg_spo2 is None

    def test_with_mock_samples(self):
        class MockSample:
            def __init__(self, v):
                self.spo2_value = v
        samples = [MockSample(v) for v in [96, 94, 92, 88, 95, 97]]
        summary = _build_night_summary(date(2026, 4, 20), samples, sleep_hours=7.0)
        assert summary.data_points == 6
        assert summary.min_spo2 == 88
        assert summary.max_spo2 == 97
        assert summary.below_90_count == 1
        assert summary.avg_spo2 is not None
        assert summary.odi is not None

    def test_all_normal(self):
        class MockSample:
            def __init__(self, v):
                self.spo2_value = v
        samples = [MockSample(96)] * 100
        summary = _build_night_summary(date(2026, 4, 20), samples, sleep_hours=7.0)
        assert summary.below_90_count == 0
        assert summary.desaturation_events == 0
        assert summary.odi == 0.0


class TestSpO2Schema:
    def test_night_summary_defaults(self):
        s = SpO2NightSummary(record_date=date(2026, 4, 20))
        assert s.below_90_count == 0
        assert s.desaturation_events == 0
        assert s.odi is None
