"""通知任务单元测试"""
import pytest
import sys
from unittest.mock import patch, MagicMock, AsyncMock


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
