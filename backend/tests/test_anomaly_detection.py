"""健康异常检测服务测试"""
import logging
import pytest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.anomaly_alert import AnomalyAlert
from app.models.daily_health import GarminData
from app.models.notification import NotificationLog, NotificationStatus, UserNotificationSetting
from app.models.user import User
from app.services.anomaly_detection_service import AnomalyDetectionService, THRESHOLDS
from app.services.notification import push_service as push_module
from app.services.notification.push_service import PushService
from app.services.notification.push_privacy import lock_screen_privacy_backstop


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


def _create_days(db, user_id, today, rows):
    """辅助函数：rows 按时间正序,最后一行落在 today。"""
    for offset, fields in enumerate(reversed(rows)):
        _create_garmin_data(db, user_id, today - timedelta(days=offset), **fields)


async def _captured_pushes(service, user_id, alerts):
    """send_alerts 交给推送层的 kwargs(PushService 打桩)。"""
    with patch("app.services.notification.push_service.PushService") as MockPush:
        mock_instance = MagicMock()
        mock_instance.send_notification = AsyncMock(return_value={"success": True})
        MockPush.return_value = mock_instance
        await service.send_alerts(user_id, alerts)
    return [c.kwargs for c in mock_instance.send_notification.call_args_list]


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
            data_source="ringconn",  # spo2 走多源合并;garmin 血氧被排除
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


class TestSendAlertsRealPushGating:
    """send_alerts through the real PushService gates (TestSendAlerts mocks PushService
    away — which is how the missing severity= shipped from 2026-05-01 to 2026-09-30)."""

    DAYTIME = datetime(2026, 9, 30, 14, 0)
    NIGHT = datetime(2026, 9, 30, 23, 30)

    def _arrange(self, db, user_id, monkeypatch, now) -> AsyncMock:
        db.add(UserNotificationSetting(
            user_id=user_id, enabled=True, ios_push_enabled=True,
            ios_device_token="fake-token", wechat_enabled=False,
        ))
        db.commit()
        monkeypatch.setattr(push_module, "get_china_now", lambda: now)
        monkeypatch.setattr(PushService, "telegram", property(lambda self: SimpleNamespace(configured=False)))
        ios = AsyncMock(return_value={"success": True})
        monkeypatch.setattr(PushService, "_send_ios", ios)
        return ios

    def _alert(self, db, user_id, today, **fields) -> AnomalyAlert:
        alert = AnomalyAlert(user_id=user_id, detection_date=today, **fields)
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @pytest.mark.asyncio
    async def test_warning_alert_reaches_default_threshold_user(
        self, db, test_user, service, today, monkeypatch, caplog,
    ):
        ios = self._arrange(db, test_user.id, monkeypatch, self.DAYTIME)
        alert = self._alert(
            db, test_user.id, today, alert_type="rhr_spike", severity="warning",
            metric_name="resting_heart_rate", current_value=80.0, message="心率偏高",
        )

        with caplog.at_level(logging.ERROR, logger=push_module.__name__):
            await service.send_alerts(test_user.id, [alert])

        assert ios.await_count == 1
        assert alert.notification_sent is True
        # explicit tier, not PushService's fail-open fallback
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

    @pytest.mark.asyncio
    async def test_critical_anomaly_is_pushed_as_high_and_waits_out_quiet_hours(
        self, db, test_user, service, today, monkeypatch,
    ):
        """Anomaly "critical" (SpO2 daily avg <95%) is not the push emergency tier."""
        ios = self._arrange(db, test_user.id, monkeypatch, self.NIGHT)
        alert = self._alert(
            db, test_user.id, today, alert_type="spo2_low", severity="critical",
            metric_name="spo2_avg", current_value=93.0, message="血氧偏低",
        )

        await service.send_alerts(test_user.id, [alert])

        assert ios.await_count == 0
        (row,) = db.query(NotificationLog).filter(
            NotificationLog.user_id == test_user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        ).all()
        assert row.data["severity"] == "high"


# 按时间正序 d-7 … today;触发全部 8 类会推送的预警(battery_low 为 info,不推)。
_ALL_PUSHABLE_DAYS = [
    *[{"resting_heart_rate": 55, "hrv": 60.0, "sleep_score": 80, "stress_level": 30}] * 4,
    {"resting_heart_rate": 56, "hrv": 55.0, "sleep_score": 80, "stress_level": 30},
    {"resting_heart_rate": 58, "hrv": 50.0, "sleep_score": 70, "stress_level": 50},
    {"resting_heart_rate": 60, "hrv": 45.0, "sleep_score": 60, "stress_level": 80},
    {"resting_heart_rate": 70, "hrv": 30.0, "sleep_score": 45, "stress_level": 85,
     "spo2_avg": 93.0, "data_source": "ringconn"},
]

_EXPECTED_TITLES = {
    "rhr_spike": "健康预警：静息心率",
    "rhr_rising_trend": "健康预警：静息心率",
    "hrv_drop": "健康预警：HRV",
    "hrv_declining_trend": "健康预警：HRV",
    "sleep_low": "健康预警：睡眠评分",
    "stress_high": "健康预警：压力",
    "spo2_low": "健康预警：血氧饱和度",
    "multi_metric_deterioration": "健康预警：睡眠评分、压力、HRV",
}


class TestPushCopy:
    """推送文案:锁屏标题只用中文标签,读数走 format_display_number(AGENTS.md §9)。"""

    @pytest.mark.asyncio
    async def test_every_pushed_alert_has_human_title_alerts_screen_and_benign_copy(
        self, db, test_user, service, today
    ):
        """真实检测器产出的每类预警:标题无内部 key、payload 带 screen=alerts(前台也弹横幅)、
        点击仍走 deep_link,且过锁屏隐私 choke point 原样透传(§3 良性文案不被误伤)。"""
        _create_days(db, test_user.id, today, _ALL_PUSHABLE_DAYS)
        alerts = service.detect_anomalies(test_user.id, today)
        pushes = await _captured_pushes(service, test_user.id, alerts)

        assert {p["data"]["type"]: p["title"] for p in pushes} == _EXPECTED_TITLES
        messages = {a.alert_type: a.message for a in alerts}
        for p in pushes:
            assert p["data"]["screen"] == "alerts"
            assert p["data"]["deep_link"]
            assert lock_screen_privacy_backstop(
                notification_type=p["notification_type"],
                title=p["title"], content=p["content"], data=p["data"],
            ) == (p["title"], messages[p["data"]["type"]], False)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("metric_name,expected", [
        ("spo2_avg", "健康预警：血氧饱和度"),
        ("sleep,stress", "健康预警：睡眠评分、压力"),
        ("some_new_metric", "健康预警"),          # 未登记 key:泛化标题,绝不回显
        ("sleep,some_new_metric", "健康预警"),
    ])
    async def test_push_title_never_leaks_internal_metric_key(
        self, db, test_user, service, today, metric_name, expected
    ):
        alert = AnomalyAlert(
            user_id=test_user.id, alert_type="rhr_spike", severity="warning",
            metric_name=metric_name, current_value=1.0, detection_date=today, message="x",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        [push] = await _captured_pushes(service, test_user.id, [alert])
        assert push["title"] == expected

    def test_rhr_spike_message_matches_stored_fields(self, db, test_user, service, today):
        _create_days(db, test_user.id, today,
                     [{"resting_heart_rate": v} for v in (60, 61, 62, 63, 60, 61, 63, 72)])
        [alert] = [a for a in service.detect_anomalies(test_user.id, today) if a.alert_type == "rhr_spike"]
        assert alert.message == "静息心率异常偏高：当前 72 bpm，7天均值 61.4 bpm，偏高 17.2%"
        assert (alert.baseline_value, alert.deviation_pct) == (61.4, 17.2)

    def test_hrv_messages_drop_trailing_zero(self, db, test_user, service, today):
        _create_garmin_data(db, test_user.id, today, hrv=40.0, hrv_status="low")
        [alert] = [a for a in service.detect_anomalies(test_user.id, today) if a.alert_type == "hrv_drop"]
        assert alert.message == "HRV 状态偏低：当前 40 ms，状态为 low"

    def test_hrv_drop_value_message_precision(self, db, test_user, service, today):
        _create_week_garmin(db, test_user.id, today, days=7, hrv=50.5)
        _create_garmin_data(db, test_user.id, today, hrv=35.0)
        [alert] = [a for a in service.detect_anomalies(test_user.id, today) if a.alert_type == "hrv_drop"]
        assert alert.message == "HRV 异常偏低：当前 35 ms，7天均值 50.5 ms，偏低 30.7%"

    def test_sleep_warning_mean_precision(self, db, test_user, service, today):
        _create_days(db, test_user.id, today, [{"sleep_score": s} for s in (56, 55, 58)])
        [alert] = [a for a in service.detect_anomalies(test_user.id, today) if a.alert_type == "sleep_low"]
        assert alert.message == "连续 3 天睡眠评分低于 60，最近均值 56.3 分"
        assert alert.baseline_value == 56.3

    def test_spo2_message_drops_trailing_zero(self, db, test_user, service, today):
        _create_garmin_data(db, test_user.id, today, data_source="ringconn", spo2_avg=93.0)
        [alert] = [a for a in service.detect_anomalies(test_user.id, today) if a.alert_type == "spo2_low"]
        assert alert.message == "血氧饱和度偏低：93%（阈值 95%），请注意"

    def test_hrv_trend_message_drops_trailing_zero(self, db, test_user, service, today):
        _create_days(db, test_user.id, today, [{"hrv": v} for v in (60.0, 54.5, 49.0, 43.5)])
        [alert] = [a for a in service.detect_anomalies(test_user.id, today)
                   if a.alert_type == "hrv_declining_trend"]
        assert alert.message.startswith("HRV 连续 3 天下降：60→43.5 ms，")

    def test_multi_metric_message_precision(self, db, test_user, service, today):
        _create_days(db, test_user.id, today, [
            {"sleep_score": s, "stress_level": st}
            for s, st in zip((80, 81, 80, 81, 70, 69, 70), (30, 31, 30, 31, 40, 41, 40))
        ])
        [alert] = [a for a in service.detect_anomalies(test_user.id, today)
                   if a.alert_type == "multi_metric_deterioration"]
        assert alert.message == (
            "多指标同步恶化（2/3）：睡眠评分下降13.46%(80.5→69.67)；"
            "压力上升32.24%(30.5→40.33)。建议减少训练强度、优先睡眠恢复"
        )
