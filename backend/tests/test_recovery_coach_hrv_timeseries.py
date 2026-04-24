"""P2 RecoveryCoach HRV 时序评分测试。"""
from unittest.mock import MagicMock
from app.agents.recovery_coach.coach import (
    _hrv_component_from_series,
    compute_readiness,
)
from app.twin.schema import HealthTwin, PhysiologicalState, BehavioralState, TwinMeta
from datetime import datetime


def _twin_with_hrv_series(series):
    return HealthTwin(
        meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()),
        physiological=PhysiologicalState(
            hrv_nightly_series=series,
            sleep_score_latest=80,
            sleep_duration_h_latest=7.5,
            body_battery_current=70,
            stress_level_avg_24h=30,
        ),
        behavioral=BehavioralState(),
    )


class TestHrvComponentFromSeries:
    def test_need_min_4_nights(self):
        assert _hrv_component_from_series([]) is None
        assert _hrv_component_from_series([
            {"date": "2026-04-20", "hrv_avg": 50, "count": 10},
            {"date": "2026-04-21", "hrv_avg": 52, "count": 10},
            {"date": "2026-04-22", "hrv_avg": 48, "count": 10},
        ]) is None

    def test_stable_night_returns_baseline_zone(self):
        """今晚 HRV 接近基线 → score 应在 0.85 左右。"""
        series = [
            {"date": f"2026-04-{20+i}", "hrv_avg": 50, "count": 10}
            for i in range(5)
        ]
        score = _hrv_component_from_series(series)
        assert score is not None
        assert 0.80 <= score <= 0.90

    def test_higher_than_baseline_boosts(self):
        """今晚显著高于基线 → score > 0.9。"""
        series = [
            {"date": "2026-04-20", "hrv_avg": 45, "count": 10},
            {"date": "2026-04-21", "hrv_avg": 46, "count": 10},
            {"date": "2026-04-22", "hrv_avg": 47, "count": 10},
            {"date": "2026-04-23", "hrv_avg": 48, "count": 10},
            {"date": "2026-04-24", "hrv_avg": 60, "count": 10},  # 今晚暴涨
        ]
        score = _hrv_component_from_series(series)
        assert score is not None
        assert score >= 0.95

    def test_lower_than_baseline_drops(self):
        """今晚显著低于基线 → score < 0.5。"""
        series = [
            {"date": "2026-04-20", "hrv_avg": 55, "count": 10},
            {"date": "2026-04-21", "hrv_avg": 54, "count": 10},
            {"date": "2026-04-22", "hrv_avg": 56, "count": 10},
            {"date": "2026-04-23", "hrv_avg": 55, "count": 10},
            {"date": "2026-04-24", "hrv_avg": 30, "count": 10},  # 今晚暴跌
        ]
        score = _hrv_component_from_series(series)
        assert score is not None
        assert score < 0.5


class TestReadinessIntegration:
    def test_timeseries_path_used_when_available(self):
        """当有 nightly_series 时应用时序算法。"""
        series = [
            {"date": f"2026-04-{20+i}", "hrv_avg": 50 + i, "count": 10}
            for i in range(6)
        ]
        twin = _twin_with_hrv_series(series)
        br = compute_readiness(twin)
        assert br.components["hrv"] is not None
        # 上升趋势 → hrv score 应 >= 0.85
        assert br.components["hrv"] >= 0.85

    def test_fallback_when_no_timeseries(self):
        """无时序 → 回退到 hrv_latest + hrv_7d_avg。"""
        twin = HealthTwin(
            meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()),
            physiological=PhysiologicalState(
                hrv_nightly_series=[],
                hrv_latest=60,
                hrv_7d_avg=50,
                sleep_score_latest=80,
                sleep_duration_h_latest=7.5,
                body_battery_current=70,
                stress_level_avg_24h=30,
            ),
            behavioral=BehavioralState(),
        )
        br = compute_readiness(twin)
        assert br.components["hrv"] is not None
        assert br.components["hrv"] >= 0.85  # 60/50=1.2 ratio
