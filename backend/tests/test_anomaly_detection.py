"""健康异常检测服务测试"""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.anomaly_alert import AnomalyAlert
from app.models.daily_health import GarminData
from app.models.user import User
from app.services.anomaly_detection_service import AnomalyDetectionService, THRESHOLDS


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(name="测试用户", phone="13800138000")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def service(db):
    """创建检测服务实例"""
    return AnomalyDetectionService(db)


@pytest.fixture
def today():
    return date(2026, 3, 1)


def _create_garmin_data(db, user_id, record_date, **kwargs):
    """辅助函数：创建Garmin数据"""
    data = GarminData(user_id=user_id, record_date=record_date, **kwargs)
    db.add(data)
    db.commit()
    return data


def _create_week_garmin(db, user_id, today, days=7, **kwargs):
    """辅助函数：创建连续几天Garmin数据"""
    records = []
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        r = _create_garmin_data(db, user_id, d, **kwargs)
        records.append(r)
    return records


class TestRhrSpike:
    """静息心率飙升检测"""

    def test_rhr_spike_detected(self, db, test_user, service, today):
        """当天RHR显著高于7天均值时应产生预警"""
        # 7天历史：RHR均值60
        _create_week_garmin(db, test_user.id, today, days=7, resting_heart_rate=60)
        # 今天：RHR=72（+20% > 15%阈值）
        _create_garmin_data(db, test_user.id, today, resting_heart_rate=72)

        alerts = service.detect_anomalies(test_user.id, today)
        rhr_alerts = [a for a in alerts if a.alert_type == "rhr_spike"]
        assert len(rhr_alerts) == 1
        assert rhr_alerts[0].severity == "warning"
        assert rhr_alerts[0].current_value == 72
        assert rhr_alerts[0].deviation_pct > 15

    def test_rhr_normal_no_alert(self, db, test_user, service, today):
        """RHR正常时不应产生预警"""
        _create_week_garmin(db, test_user.id, today, days=7, resting_heart_rate=60)
        _create_garmin_data(db, test_user.id, today, resting_heart_rate=63)  # +5%

        alerts = service.detect_anomalies(test_user.id, today)
        rhr_alerts = [a for a in alerts if a.alert_type == "rhr_spike"]
        assert len(rhr_alerts) == 0

    def test_rhr_no_today_data(self, db, test_user, service, today):
        """没有今天数据时不检测RHR"""
        _create_week_garmin(db, test_user.id, today, days=7, resting_heart_rate=60)

        alerts = service.detect_anomalies(test_user.id, today)
        rhr_alerts = [a for a in alerts if a.alert_type == "rhr_spike"]
        assert len(rhr_alerts) == 0

    def test_rhr_insufficient_history(self, db, test_user, service, today):
        """历史数据不足3天时不检测"""
        _create_week_garmin(db, test_user.id, today, days=2, resting_heart_rate=60)
        _create_garmin_data(db, test_user.id, today, resting_heart_rate=80)

        alerts = service.detect_anomalies(test_user.id, today)
        rhr_alerts = [a for a in alerts if a.alert_type == "rhr_spike"]
        assert len(rhr_alerts) == 0


class TestHrvDrop:
    """HRV骤降检测"""

    def test_hrv_drop_detected_by_value(self, db, test_user, service, today):
        """HRV数值低于7天均值20%以上时应预警"""
        _create_week_garmin(db, test_user.id, today, days=7, hrv=50.0)
        _create_garmin_data(db, test_user.id, today, hrv=35.0)  # -30% < -20%

        alerts = service.detect_anomalies(test_user.id, today)
        hrv_alerts = [a for a in alerts if a.alert_type == "hrv_drop"]
        assert len(hrv_alerts) == 1
        assert hrv_alerts[0].deviation_pct > 20

    def test_hrv_drop_detected_by_status(self, db, test_user, service, today):
        """HRV status为low时应预警"""
        _create_garmin_data(db, test_user.id, today, hrv=40.0, hrv_status="low")

        alerts = service.detect_anomalies(test_user.id, today)
        hrv_alerts = [a for a in alerts if a.alert_type == "hrv_drop"]
        assert len(hrv_alerts) == 1

    def test_hrv_normal_no_alert(self, db, test_user, service, today):
        """HRV正常时不预警"""
        _create_week_garmin(db, test_user.id, today, days=7, hrv=50.0)
        _create_garmin_data(db, test_user.id, today, hrv=45.0, hrv_status="balanced")  # -10%

        alerts = service.detect_anomalies(test_user.id, today)
        hrv_alerts = [a for a in alerts if a.alert_type == "hrv_drop"]
        assert len(hrv_alerts) == 0


class TestSleepLow:
    """睡眠评分异常检测"""

    def test_sleep_critical_below_50(self, db, test_user, service, today):
        """单日睡眠评分<50为critical"""
        _create_garmin_data(db, test_user.id, today, sleep_score=35)

        alerts = service.detect_anomalies(test_user.id, today)
        sleep_alerts = [a for a in alerts if a.alert_type == "sleep_low"]
        assert len(sleep_alerts) == 1
        assert sleep_alerts[0].severity == "critical"

    def test_sleep_warning_3_days_below_60(self, db, test_user, service, today):
        """连续3天睡眠评分<60为warning"""
        # 前2天也低
        _create_week_garmin(db, test_user.id, today, days=2, sleep_score=55)
        # 今天也低
        _create_garmin_data(db, test_user.id, today, sleep_score=58)

        alerts = service.detect_anomalies(test_user.id, today)
        sleep_alerts = [a for a in alerts if a.alert_type == "sleep_low"]
        assert len(sleep_alerts) == 1
        assert sleep_alerts[0].severity == "warning"

    def test_sleep_normal_no_alert(self, db, test_user, service, today):
        """睡眠评分正常时不预警"""
        _create_week_garmin(db, test_user.id, today, days=3, sleep_score=75)
        _create_garmin_data(db, test_user.id, today, sleep_score=70)

        alerts = service.detect_anomalies(test_user.id, today)
        sleep_alerts = [a for a in alerts if a.alert_type == "sleep_low"]
        assert len(sleep_alerts) == 0

    def test_sleep_one_bad_day_no_warning(self, db, test_user, service, today):
        """只有1天低于60但>=50，不触发warning"""
        _create_week_garmin(db, test_user.id, today, days=2, sleep_score=75)
        _create_garmin_data(db, test_user.id, today, sleep_score=55)

        alerts = service.detect_anomalies(test_user.id, today)
        sleep_alerts = [a for a in alerts if a.alert_type == "sleep_low"]
        assert len(sleep_alerts) == 0


class TestStressHigh:
    """压力水平检测"""

    def test_stress_high_2_days(self, db, test_user, service, today):
        """连续2天压力>75时预警"""
        _create_garmin_data(db, test_user.id, today - timedelta(days=1), stress_level=80)
        _create_garmin_data(db, test_user.id, today, stress_level=85)

        alerts = service.detect_anomalies(test_user.id, today)
        stress_alerts = [a for a in alerts if a.alert_type == "stress_high"]
        assert len(stress_alerts) == 1

    def test_stress_single_day_no_alert(self, db, test_user, service, today):
        """只有1天高压力不预警"""
        _create_garmin_data(db, test_user.id, today - timedelta(days=1), stress_level=50)
        _create_garmin_data(db, test_user.id, today, stress_level=80)

        alerts = service.detect_anomalies(test_user.id, today)
        stress_alerts = [a for a in alerts if a.alert_type == "stress_high"]
        assert len(stress_alerts) == 0


class TestSpo2Low:
    """血氧饱和度检测"""

    def test_spo2_critical(self, db, test_user, service, today):
        """血氧<95%为critical"""
        _create_garmin_data(db, test_user.id, today, data_source="ringconn", spo2_avg=92.5)

        alerts = service.detect_anomalies(test_user.id, today)
        spo2_alerts = [a for a in alerts if a.alert_type == "spo2_low"]
        assert len(spo2_alerts) == 1
        assert spo2_alerts[0].severity == "critical"

    def test_spo2_normal(self, db, test_user, service, today):
        """血氧>=95%不预警"""
        _create_garmin_data(db, test_user.id, today, data_source="ringconn", spo2_avg=97.0)

        alerts = service.detect_anomalies(test_user.id, today)
        spo2_alerts = [a for a in alerts if a.alert_type == "spo2_low"]
        assert len(spo2_alerts) == 0

    def test_spo2_ignores_excluded_garmin_low_when_ringconn_normal(self, db, test_user, service, today):
        """异常检测必须走多源合并层:Garmin 血氧已排除,不能用假低值触发低氧告警。"""
        _create_garmin_data(db, test_user.id, today, data_source="garmin", spo2_avg=85.0)
        _create_garmin_data(db, test_user.id, today, data_source="ringconn", spo2_avg=97.0)

        alerts = service.detect_anomalies(test_user.id, today)

        assert [a for a in alerts if a.alert_type == "spo2_low"] == []


class TestBatteryLow:
    """Body Battery检测"""

    def test_battery_low_morning(self, db, test_user, service, today):
        """最高充电<30为info"""
        _create_garmin_data(db, test_user.id, today, body_battery_most_charged=22)

        alerts = service.detect_anomalies(test_user.id, today)
        battery_alerts = [a for a in alerts if a.alert_type == "battery_low"]
        assert len(battery_alerts) == 1
        assert battery_alerts[0].severity == "info"

    def test_battery_normal(self, db, test_user, service, today):
        """Body Battery正常不预警"""
        _create_garmin_data(db, test_user.id, today, body_battery_most_charged=65)

        alerts = service.detect_anomalies(test_user.id, today)
        battery_alerts = [a for a in alerts if a.alert_type == "battery_low"]
        assert len(battery_alerts) == 0


class TestDeduplication:
    """预警去重"""

    def test_duplicate_alert_not_created(self, db, test_user, service, today):
        """同一天同类型预警不重复创建"""
        _create_garmin_data(db, test_user.id, today, data_source="ringconn", spo2_avg=90.0)

        # 第一次检测
        alerts1 = service.detect_anomalies(test_user.id, today)
        assert len([a for a in alerts1 if a.alert_type == "spo2_low"]) == 1

        # 第二次检测 - 不应重复
        alerts2 = service.detect_anomalies(test_user.id, today)
        assert len([a for a in alerts2 if a.alert_type == "spo2_low"]) == 0

        # DB中只有1条
        total = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == test_user.id,
            AnomalyAlert.alert_type == "spo2_low",
            AnomalyAlert.detection_date == today,
        ).count()
        assert total == 1


class TestEdgeCases:
    """边界情况"""

    def test_no_data_no_alerts(self, db, test_user, service, today):
        """完全没有Garmin数据不应报错或产生预警"""
        alerts = service.detect_anomalies(test_user.id, today)
        assert len(alerts) == 0

    def test_multiple_alerts_same_day(self, db, test_user, service, today):
        """同一天可以产生多种类型预警"""
        _create_week_garmin(db, test_user.id, today, days=7, resting_heart_rate=60, hrv=50.0)
        # 今天：RHR飙升 + HRV骤降 + 血氧低 + body battery低
        _create_garmin_data(
            db, test_user.id, today,
            data_source="ringconn",  # spo2 走多源合并;garmin 血氧被排除,用 ringconn
            resting_heart_rate=75,  # +25%
            hrv=30.0,               # -40%
            spo2_avg=93.0,          # <95%
            body_battery_most_charged=20,  # <30
        )

        alerts = service.detect_anomalies(test_user.id, today)
        alert_types = {a.alert_type for a in alerts}
        assert "rhr_spike" in alert_types
        assert "hrv_drop" in alert_types
        assert "spo2_low" in alert_types
        assert "battery_low" in alert_types

    def test_alert_persisted_to_db(self, db, test_user, service, today):
        """预警应持久化到数据库"""
        _create_garmin_data(db, test_user.id, today, data_source="ringconn", spo2_avg=90.0)

        service.detect_anomalies(test_user.id, today)

        db_alert = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == test_user.id,
        ).first()
        assert db_alert is not None
        assert db_alert.alert_type == "spo2_low"
        assert db_alert.severity == "critical"
        assert db_alert.detection_date == today


class TestSendAlerts:
    """通知发送测试"""

    @pytest.mark.asyncio
    async def test_send_alerts_calls_push_service(self, db, test_user, service, today):
        """send_alerts应调用PushService"""
        alert = AnomalyAlert(
            user_id=test_user.id,
            alert_type="spo2_low",
            severity="critical",
            metric_name="spo2_avg",
            current_value=90.0,
            detection_date=today,
            message="血氧偏低",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        with patch("app.services.notification.push_service.PushService") as MockPush:
            mock_instance = MagicMock()
            mock_instance.send_notification = AsyncMock(return_value={"success": True})
            MockPush.return_value = mock_instance

            await service.send_alerts(test_user.id, [alert])

            mock_instance.send_notification.assert_called_once()
            call_kwargs = mock_instance.send_notification.call_args
            assert call_kwargs[1]["respect_quiet_hours"] is False  # critical bypasses quiet hours

    @pytest.mark.asyncio
    async def test_critical_bypasses_quiet_hours(self, db, test_user, service, today):
        """critical级别预警应绕过静默时段"""
        critical_alert = AnomalyAlert(
            user_id=test_user.id, alert_type="spo2_low", severity="critical",
            metric_name="spo2_avg", current_value=90.0, detection_date=today,
            message="血氧偏低",
        )
        warning_alert = AnomalyAlert(
            user_id=test_user.id, alert_type="rhr_spike", severity="warning",
            metric_name="resting_heart_rate", current_value=80.0, detection_date=today,
            message="心率偏高",
        )
        db.add_all([critical_alert, warning_alert])
        db.commit()
        db.refresh(critical_alert)
        db.refresh(warning_alert)

        with patch("app.services.notification.push_service.PushService") as MockPush:
            mock_instance = MagicMock()
            mock_instance.send_notification = AsyncMock(return_value={"success": True})
            MockPush.return_value = mock_instance

            await service.send_alerts(test_user.id, [critical_alert, warning_alert])

            calls = mock_instance.send_notification.call_args_list
            assert len(calls) == 2
            # critical: respect_quiet_hours=False
            assert calls[0][1]["respect_quiet_hours"] is False
            # warning: respect_quiet_hours=True
            assert calls[1][1]["respect_quiet_hours"] is True
