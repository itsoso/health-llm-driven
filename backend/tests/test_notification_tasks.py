"""通知任务单元测试"""
import pytest
from datetime import date, datetime
import sys
from unittest.mock import AsyncMock, patch, MagicMock


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

    orig_celery = sys.modules.get("celery")
    needs_mock = orig_celery is None
    if needs_mock:
        sys.modules["celery"] = MagicMock()

    # 保存原 module 对象:结束时必须"放回原对象"而不是删掉。
    # 只 del 的话,下一个 import 会造出全新 module dict,但 @celery_app.task
    # 按名字返回 registry 里缓存的旧 task 对象——其 run.__globals__ 仍指向
    # 这里被孤儿化的旧 dict,于是后续测试 patch("app.tasks.notifications.X")
    # 全部打空(曾让 test_push_privacy 的任务打到真 Postgres)。
    orig_notifications = sys.modules.get("app.tasks.notifications")
    tasks_package = sys.modules.get("app.tasks")
    missing = object()
    orig_package_notification = (
        getattr(tasks_package, "notifications", missing)
        if tasks_package is not None
        else missing
    )

    # Ensure app.celery_app module has a proper celery_app with task decorator
    with patch.dict(sys.modules, {
        "app.celery_app": MagicMock(celery_app=celery_mock),
    }):
        # Force reimport of notifications module with mocked celery
        if "app.tasks.notifications" in sys.modules:
            del sys.modules["app.tasks.notifications"]
        yield

    # Clean up: 恢复原 module 对象(如本来就没加载过,则清掉本 fixture 期间的临时导入)
    if orig_notifications is not None:
        sys.modules["app.tasks.notifications"] = orig_notifications
    elif "app.tasks.notifications" in sys.modules:
        del sys.modules["app.tasks.notifications"]

    # importlib also caches child modules as attributes on their parent package.
    # Restoring only sys.modules leaves app.tasks.notifications pointing at the
    # temporary fake module, so `from app.tasks import notifications` can still
    # bypass the restored real module in later tests.
    if tasks_package is not None:
        if orig_package_notification is missing:
            if hasattr(tasks_package, "notifications"):
                delattr(tasks_package, "notifications")
        else:
            setattr(tasks_package, "notifications", orig_package_notification)

    # The fake Celery module is process-global.  Leaving it behind makes the
    # next test import `celery.schedules` from a MagicMock and turns Celery
    # task objects into plain functions with no `.run` entrypoint.
    if orig_celery is not None:
        sys.modules["celery"] = orig_celery
    elif "celery" in sys.modules:
        del sys.modules["celery"]


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

    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    @patch("app.tasks.notifications.run_async")
    def test_sleep_reminder_drops_during_quiet_hours(self, mock_run_async, mock_push_cls, mock_session_cls):
        """睡眠提醒命中 quiet hours 时不穿透 Apple Watch, 也不延迟到第二天早上补发."""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        setting = MagicMock(user_id=1)
        mock_db.query.return_value.filter.return_value.all.return_value = [setting]

        from app.tasks.notifications import send_sleep_reminders
        send_sleep_reminders()

        send_fn = mock_push_cls.return_value.send_notification
        assert send_fn.call_count == 1
        _, kwargs = send_fn.call_args
        assert kwargs.get("quiet_hours_policy") == "drop"

    def test_sleep_reminder_copy_uses_profile_bedtime_and_stress_sensitive_trait(self, db):
        """睡眠提醒文案应基于真实作息和压力敏感特质, 不硬编码错误睡觉时间."""
        from app.models.genetic_data import GeneticProfile, GeneticVariant
        from app.models.user import User
        from app.models.user_profile import UserProfile
        from app.tasks.notifications import _sleep_reminder_content

        user = User(
            username="sleep_trait_user",
            email="sleep_trait@example.com",
            hashed_password="x",
            name="Sleep Trait User",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(UserProfile(user_id=user.id, usual_sleep_time="23:30", target_sleep_hours=7.5))
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="manual",
            test_date=date.today(),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        db.add(GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs4680",
            category="nutrition",
            gene_name="COMT",
            genotype="AA",
            result_label="压力敏感/焦虑倾向(忧虑型)",
            risk_level="medium",
        ))
        db.commit()

        content = _sleep_reminder_content(db, user.id)

        assert "23:30" in content
        assert "压力敏感" in content
        assert "明天有重要事" in content
        assert "8:30" not in content
        assert "08:30" not in content


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


class TestDueReminderPolicy:
    @patch("app.services.notification.push_scheduler.PushService")
    def test_due_sleep_reminder_drops_during_quiet_hours(self, mock_push_cls):
        """用户配置的 sleep reminder 命中静默时段时不穿透 Apple Watch, 也不补发到早上."""
        from app.services.notification.push_scheduler import PushScheduler

        reminder = MagicMock(
            id=10,
            user_id=3,
            reminder_type="sleep",
            name="💤 睡眠提醒",
            message="",
        )
        push = mock_push_cls.return_value
        push.get_due_reminders.return_value = [{"user_id": 3, "reminder": reminder}]
        push.send_notification = AsyncMock(return_value={"success": True})

        scheduler = PushScheduler()
        import asyncio
        asyncio.run(scheduler._send_due_reminders(MagicMock(), push))

        kwargs = push.send_notification.call_args.kwargs
        assert kwargs["quiet_hours_policy"] == "drop"


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


class TestSendPlanItemReminders:
    """测试分时计划提醒任务"""

    @patch("app.tasks.notifications.llm_push_backstop", side_effect=lambda _title, body, generic_content: (None, body, False))
    @patch("app.tasks.notifications._get_user_city", return_value=None)
    @patch("app.tasks.notifications._today_weather_text", return_value="")
    @patch("app.tasks.notifications.get_china_now", return_value=datetime(2026, 7, 13, 7, 30, 0))
    @patch("app.tasks.notifications.SessionLocal")
    @patch("app.tasks.notifications.PushService")
    @patch("app.tasks.notifications.run_async", return_value={
        "success": False,
        "reason": "delayed_for_quiet_hours",
        "scheduled_at": "2026-07-13T09:00:00",
    })
    def test_does_not_count_morning_quiet_delayed_push_as_sent(
        self,
        mock_run_async,
        mock_push_cls,
        mock_session_cls,
        mock_now,
        mock_weather,
        mock_city,
        mock_backstop,
    ):
        """07:30/08:00 命中静默延迟时,任务结果不能误报已发送。"""
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_item = MagicMock(
            day_of_week=date.today().weekday() + 1,
            is_completed=False,
            category="diet",
            title="早餐打卡",
            weather_condition_tag=None,
        )
        mock_plan = MagicMock(user_id=3, items=[mock_item])
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_plan]
        mock_push_cls.return_value.send_notification.return_value = "awaitable"

        from app.tasks.notifications import send_plan_item_reminders
        result = send_plan_item_reminders()

        assert result["matched_categories"] == ["diet"]
        assert result["sent_count"] == 0
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
