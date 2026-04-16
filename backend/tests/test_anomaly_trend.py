"""Agent Native Phase 1: 趋势检测器测试"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services.anomaly_detection_service import AnomalyDetectionService
from app.models.daily_health import GarminData
from app.models.user import User


@pytest.fixture
def test_user(db):
    user = User(name="趋势测试", birth_date=date(1985, 1, 1), gender="男", is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_garmin(db, user_id: int, record_date: date, **kwargs) -> GarminData:
    """创建 Garmin 每日数据"""
    g = GarminData(user_id=user_id, record_date=record_date, **kwargs)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


class TestRhrTrend:
    """静息心率连续上升趋势检测"""

    def test_3_day_rising_triggers_alert(self, db, test_user):
        """连续3天RHR每天上升≥2bpm → 应报警"""
        today = date(2026, 4, 16)
        _make_garmin(db, test_user.id, today - timedelta(days=3), resting_heart_rate=58)
        _make_garmin(db, test_user.id, today - timedelta(days=2), resting_heart_rate=60)
        _make_garmin(db, test_user.id, today - timedelta(days=1), resting_heart_rate=63)
        _make_garmin(db, test_user.id, today, resting_heart_rate=66)

        svc = AnomalyDetectionService(db)
        alert = svc._check_rhr_trend(test_user.id, today)

        assert alert is not None
        assert alert.alert_type == "rhr_rising_trend"
        assert alert.severity == "warning"
        assert "连续" in alert.message
        assert "58" in alert.message
        assert "66" in alert.message

    def test_stable_rhr_no_alert(self, db, test_user):
        """RHR稳定不变 → 不应报警"""
        today = date(2026, 4, 16)
        for i in range(4):
            _make_garmin(db, test_user.id, today - timedelta(days=3 - i), resting_heart_rate=60)

        svc = AnomalyDetectionService(db)
        alert = svc._check_rhr_trend(test_user.id, today)
        assert alert is None

    def test_small_increase_no_alert(self, db, test_user):
        """每天只升1bpm（<2阈值）→ 不应报警"""
        today = date(2026, 4, 16)
        _make_garmin(db, test_user.id, today - timedelta(days=3), resting_heart_rate=58)
        _make_garmin(db, test_user.id, today - timedelta(days=2), resting_heart_rate=59)
        _make_garmin(db, test_user.id, today - timedelta(days=1), resting_heart_rate=60)
        _make_garmin(db, test_user.id, today, resting_heart_rate=61)

        svc = AnomalyDetectionService(db)
        alert = svc._check_rhr_trend(test_user.id, today)
        assert alert is None

    def test_interrupted_trend_no_alert(self, db, test_user):
        """中间一天下降打断连续性 → 不应报警"""
        today = date(2026, 4, 16)
        _make_garmin(db, test_user.id, today - timedelta(days=3), resting_heart_rate=58)
        _make_garmin(db, test_user.id, today - timedelta(days=2), resting_heart_rate=61)
        _make_garmin(db, test_user.id, today - timedelta(days=1), resting_heart_rate=59)  # 下降
        _make_garmin(db, test_user.id, today, resting_heart_rate=62)

        svc = AnomalyDetectionService(db)
        alert = svc._check_rhr_trend(test_user.id, today)
        assert alert is None


class TestHrvTrend:
    """HRV连续下降趋势检测"""

    def test_3_day_declining_triggers_alert(self, db, test_user):
        """连续3天HRV每天下降≥5ms → 应报警"""
        today = date(2026, 4, 16)
        _make_garmin(db, test_user.id, today - timedelta(days=3), hrv=55)
        _make_garmin(db, test_user.id, today - timedelta(days=2), hrv=49)
        _make_garmin(db, test_user.id, today - timedelta(days=1), hrv=43)
        _make_garmin(db, test_user.id, today, hrv=37)

        svc = AnomalyDetectionService(db)
        alert = svc._check_hrv_trend(test_user.id, today)

        assert alert is not None
        assert alert.alert_type == "hrv_declining_trend"
        assert "55" in alert.message
        assert "37" in alert.message

    def test_stable_hrv_no_alert(self, db, test_user):
        """HRV稳定 → 不应报警"""
        today = date(2026, 4, 16)
        for i in range(4):
            _make_garmin(db, test_user.id, today - timedelta(days=3 - i), hrv=50)

        svc = AnomalyDetectionService(db)
        alert = svc._check_hrv_trend(test_user.id, today)
        assert alert is None

    def test_insufficient_data_no_alert(self, db, test_user):
        """数据不足 → 不应报警"""
        today = date(2026, 4, 16)
        _make_garmin(db, test_user.id, today, hrv=40)

        svc = AnomalyDetectionService(db)
        alert = svc._check_hrv_trend(test_user.id, today)
        assert alert is None


class TestMultiMetricDeterioration:
    """多指标同时恶化检测"""

    def test_2_of_3_metrics_trigger(self, db, test_user):
        """sleep下降+HRV下降（2/3命中）→ 应报警"""
        today = date(2026, 4, 16)
        # Baseline: 前4天
        for i in range(4, 7):
            _make_garmin(db, test_user.id, today - timedelta(days=i),
                         sleep_score=80, stress_level=30, hrv=55)
        # Recent: 后3天 - sleep 和 HRV 恶化
        for i in range(3):
            _make_garmin(db, test_user.id, today - timedelta(days=2 - i),
                         sleep_score=60, stress_level=33, hrv=40)

        svc = AnomalyDetectionService(db)
        alert = svc._check_multi_metric_deterioration(test_user.id, today)

        assert alert is not None
        assert alert.alert_type == "multi_metric_deterioration"
        assert alert.current_value >= 2

    def test_only_1_metric_no_alert(self, db, test_user):
        """只有1个指标恶化 → 不应报警"""
        today = date(2026, 4, 16)
        for i in range(4, 7):
            _make_garmin(db, test_user.id, today - timedelta(days=i),
                         sleep_score=80, stress_level=30, hrv=50)
        # 只有 sleep 恶化
        for i in range(3):
            _make_garmin(db, test_user.id, today - timedelta(days=2 - i),
                         sleep_score=65, stress_level=30, hrv=48)

        svc = AnomalyDetectionService(db)
        alert = svc._check_multi_metric_deterioration(test_user.id, today)
        assert alert is None

    def test_all_3_metrics_trigger(self, db, test_user):
        """3个指标全部恶化 → 应报警，且 current_value=3"""
        today = date(2026, 4, 16)
        for i in range(4, 7):
            _make_garmin(db, test_user.id, today - timedelta(days=i),
                         sleep_score=85, stress_level=25, hrv=60)
        for i in range(3):
            _make_garmin(db, test_user.id, today - timedelta(days=2 - i),
                         sleep_score=60, stress_level=50, hrv=40)

        svc = AnomalyDetectionService(db)
        alert = svc._check_multi_metric_deterioration(test_user.id, today)

        assert alert is not None
        assert alert.current_value == 3


class TestDetectAnomaliesIntegration:
    """detect_anomalies 端到端测试"""

    def test_trend_checkers_included(self, db, test_user):
        """趋势检测器应被包含在 detect_anomalies 中"""
        svc = AnomalyDetectionService(db)
        checker_names = [c.__name__ for c in [
            svc._check_rhr_spike, svc._check_hrv_drop, svc._check_sleep_low,
            svc._check_stress_high, svc._check_spo2_low, svc._check_battery_low,
            svc._check_rhr_trend, svc._check_hrv_trend, svc._check_multi_metric_deterioration,
        ]]
        assert "_check_rhr_trend" in checker_names
        assert "_check_hrv_trend" in checker_names
        assert "_check_multi_metric_deterioration" in checker_names

    def test_detect_returns_trend_alerts(self, db, test_user):
        """detect_anomalies 应能返回趋势告警"""
        today = date(2026, 4, 16)
        _make_garmin(db, test_user.id, today - timedelta(days=3), resting_heart_rate=55, hrv=60, sleep_score=80, stress_level=25)
        _make_garmin(db, test_user.id, today - timedelta(days=2), resting_heart_rate=58, hrv=54, sleep_score=78, stress_level=28)
        _make_garmin(db, test_user.id, today - timedelta(days=1), resting_heart_rate=61, hrv=48, sleep_score=75, stress_level=30)
        _make_garmin(db, test_user.id, today, resting_heart_rate=64, hrv=42, sleep_score=72, stress_level=32)

        svc = AnomalyDetectionService(db)
        alerts = svc.detect_anomalies(test_user.id, check_date=today)

        alert_types = [a.alert_type for a in alerts]
        assert "rhr_rising_trend" in alert_types
        assert "hrv_declining_trend" in alert_types
