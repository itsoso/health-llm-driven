"""通知任务单元测试"""
import pytest
from datetime import date
import sys
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_celery():
    """Mock celery if not installed"""
    celery_mock = MagicMock()

    # celery_app.task should act as a passthrough decorator
    def task_decorator(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        def wrapper(fn):
            return fn
        return wrapper

    celery_mock.task = task_decorator

    needs_mock = "celery" not in sys.modules
    if needs_mock:
        sys.modules["celery"] = MagicMock()

    # Ensure app.celery_app module has a proper celery_app with task decorator
    with patch.dict(sys.modules, {
        "app.celery_app": MagicMock(celery_app=celery_mock),
    }):
        # Force reimport of notifications module with mocked celery
        if "app.tasks.notifications" in sys.modules:
            del sys.modules["app.tasks.notifications"]
        yield

    # Clean up
    if "app.tasks.notifications" in sys.modules:
        del sys.modules["app.tasks.notifications"]


class TestSendSleepReminders:
    """测试 send_sleep_reminders 任务"""

    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    @patch("app.tasks.notifications.run_async")
    def test_returns_sent_count(self, mock_run_async, mock_push_cls, mock_session_cls):
        """应返回包含 sent_count 的 dict"""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.all.return_value = []

        from app.tasks.notifications import send_sleep_reminders
        result = send_sleep_reminders()

        assert isinstance(result, dict)
        assert "sent_count" in result
        assert result["sent_count"] == 0

    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    @patch("app.tasks.notifications.run_async")
    def test_sends_for_enabled_users(self, mock_run_async, mock_push_cls, mock_session_cls):
        """有启用提醒的用户时应发送通知"""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        setting1 = MagicMock(user_id=1)
        setting2 = MagicMock(user_id=2)
        mock_db.query.return_value.filter.return_value.all.return_value = [setting1, setting2]

        from app.tasks.notifications import send_sleep_reminders
        result = send_sleep_reminders()

        assert result["sent_count"] == 2
        assert mock_run_async.call_count == 2


class TestSendPlanMorningReminder:
    """测试 send_plan_morning_reminder 任务"""

    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    def test_returns_dict(self, mock_push_cls, mock_session_cls):
        """应返回包含 sent_count 的 dict"""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.all.return_value = []

        from app.tasks.notifications import send_plan_morning_reminder
        result = send_plan_morning_reminder()

        assert isinstance(result, dict)
        assert "sent_count" in result
        assert result["sent_count"] == 0

    @patch("app.tasks.notifications._today_weather_text", return_value="")
    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    @patch("app.tasks.notifications.run_async")
    def test_uses_send_notification_content_argument(
        self,
        mock_run_async,
        mock_push_cls,
        mock_session_cls,
        mock_weather,
    ):
        """今日计划提醒必须走 run_async + content 参数, 不能用旧 body 参数."""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_item = MagicMock(
            day_of_week=date.today().weekday() + 1,
            is_completed=False,
            title="晨起记录体重和腰围",
            weather_condition_tag=None,
        )
        mock_plan = MagicMock(
            user_id=3,
            items=[mock_item],
        )
        mock_db.query.return_value.options.return_value.filter.return_value.all.return_value = [mock_plan]
        mock_push = mock_push_cls.return_value
        mock_push.send_notification.return_value = "awaitable"

        from app.tasks.notifications import send_plan_morning_reminder
        result = send_plan_morning_reminder()

        assert result["sent_count"] == 1
        mock_push.send_notification.assert_called_once()
        kwargs = mock_push.send_notification.call_args.kwargs
        assert kwargs["notification_type"] == "reminder"
        assert kwargs["title"] == "📋 今日计划"
        assert "content" in kwargs
        assert "body" not in kwargs
        mock_run_async.assert_called_once_with("awaitable")


class TestSendPlanEveningSummary:
    """测试 send_plan_evening_summary 任务"""

    @patch("app.tasks.notifications._today_weather_text", return_value="")
    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    @patch("app.tasks.notifications.run_async")
    def test_uses_send_notification_content_argument(
        self,
        mock_run_async,
        mock_push_cls,
        mock_session_cls,
        mock_weather,
    ):
        """晚间进度总结必须走 run_async + content 参数, 不能用旧 body 参数."""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_item = MagicMock(
            day_of_week=date.today().weekday() + 1,
            is_completed=False,
            title="晨起记录体重和腰围",
            weather_condition_tag=None,
        )
        mock_plan = MagicMock(
            user_id=3,
            items=[mock_item],
            completion_rate=50,
        )
        mock_db.query.return_value.options.return_value.filter.return_value.all.return_value = [mock_plan]
        mock_push = mock_push_cls.return_value
        mock_push.send_notification.return_value = "awaitable"

        from app.tasks.notifications import send_plan_evening_summary
        result = send_plan_evening_summary()

        assert result["sent_count"] == 1
        mock_push.send_notification.assert_called_once()
        kwargs = mock_push.send_notification.call_args.kwargs
        assert kwargs["notification_type"] == "reminder"
        assert kwargs["title"] == "📊 今日进度"
        assert "content" in kwargs
        assert "body" not in kwargs
        mock_run_async.assert_called_once_with("awaitable")


class TestTasksUseGarminCredential:
    """验证异常检测和趋势分析任务使用 GarminCredential（通过源码检查）"""

    def test_daily_anomaly_check_uses_garmin_credential(self):
        """daily_anomaly_check 应使用 GarminCredential，不使用 DeviceCredential"""
        import inspect
        from app.tasks.notifications import daily_anomaly_check
        source = inspect.getsource(daily_anomaly_check)
        assert "GarminCredential" in source
        assert "DeviceCredential" not in source

    def test_daily_trend_analysis_uses_garmin_credential(self):
        """daily_trend_analysis 应使用 GarminCredential"""
        import inspect
        from app.tasks.notifications import daily_trend_analysis
        source = inspect.getsource(daily_trend_analysis)
        assert "GarminCredential" in source
        assert "DeviceCredential" not in source

    def test_send_morning_health_summary_uses_garmin_credential(self):
        """send_morning_health_summary 应使用 GarminCredential"""
        import inspect
        from app.tasks.notifications import send_morning_health_summary
        source = inspect.getsource(send_morning_health_summary)
        assert "GarminCredential" in source
        assert "DeviceCredential" not in source


class TestNotificationEvidencePayloads:
    """验证通知任务写入 KB V2 evidence metadata."""

    def test_morning_briefing_payload_is_data_summary(self):
        from app.tasks.notifications import _morning_briefing_push_data

        data = _morning_briefing_push_data()

        assert data["deep_link"] == "/voice-chat?intent=briefing"
        assert data["kind"] == "morning_briefing"
        assert data["support_status"] == "data_summary"
        assert data["unsupported"] is False
        assert data["evidence_refs"] == []
        assert data["notification_evidence_source"] == "notifications.send_morning_health_summary"
