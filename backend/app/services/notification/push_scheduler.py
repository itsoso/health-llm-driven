"""推送调度器 - 定时发送推送通知"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.notification import UserNotificationSetting, ReminderConfig, NotificationType
from app.services.notification.push_service import PushService, PREDEFINED_REMINDERS
from app.services.ai_scheduler import AISchedulerService
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class PushScheduler:
    """
    推送调度器

    负责：
    1. 定时检查并发送提醒
    2. 发送早间健康简报
    3. 发送健康预警
    4. 发送周报
    """

    def __init__(self):
        self._running = False
        self._check_interval = 60  # 检查间隔（秒）

    async def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("推送调度器已在运行")
            return

        self._running = True
        logger.info("📤 推送调度器已启动")

        while self._running:
            try:
                await self._check_and_send()
            except Exception as e:
                logger.error(f"推送调度器执行出错: {e}")

            await asyncio.sleep(self._check_interval)

    def stop(self):
        """停止调度器"""
        self._running = False
        logger.info("📤 推送调度器已停止")

    async def _check_and_send(self):
        """检查并发送推送"""
        db = SessionLocal()
        try:
            push_service = PushService(db)
            now = get_china_now()

            # 1. 检查定时提醒
            await self._send_due_reminders(db, push_service)

            # 2. 检查早间简报（每天早上发送一次）
            await self._send_morning_briefings(db, push_service, now)

            # 3. 检查健康预警（基于最新数据）
            await self._check_health_alerts(db, push_service)

        finally:
            db.close()

    async def _send_due_reminders(self, db: Session, push_service: PushService):
        """发送到期的提醒"""
        due_reminders = push_service.get_due_reminders()

        for item in due_reminders:
            user_id = item["user_id"]
            reminder = item["reminder"]

            # 获取提醒消息
            predefined = PREDEFINED_REMINDERS.get(reminder.reminder_type, {})
            message = reminder.message or predefined.get("message", f"📢 {reminder.name}")

            try:
                result = await push_service.send_notification(
                    user_id=user_id,
                    notification_type=NotificationType.REMINDER.value,
                    title=reminder.name,
                    content=message,
                    data={
                        "reminder_id": reminder.id,
                        "reminder_type": reminder.reminder_type
                    }
                )

                if result.get("success"):
                    logger.info(f"✅ 提醒发送成功: user={user_id}, type={reminder.reminder_type}")
                else:
                    logger.warning(f"⚠️ 提醒发送失败: user={user_id}, reason={result.get('reason')}")

            except Exception as e:
                logger.error(f"发送提醒失败: user={user_id}, error={e}")

    async def _send_morning_briefings(
        self,
        db: Session,
        push_service: PushService,
        now: datetime
    ):
        """发送早间健康简报"""
        current_time = now.strftime("%H:%M")

        # 查找需要发送早间简报的用户
        settings = db.query(UserNotificationSetting).filter(
            UserNotificationSetting.enabled == True,
            UserNotificationSetting.morning_briefing_enabled == True,
            UserNotificationSetting.morning_briefing_time == current_time
        ).all()

        for setting in settings:
            try:
                # 生成早间简报
                ai_scheduler = AISchedulerService(db, setting.user_id)
                briefing = ai_scheduler.get_morning_briefing()

                if not briefing:
                    continue

                # 构建推送内容
                title = briefing.get("greeting", "☀️ 早安！")

                # 提取关键信息
                sections = briefing.get("sections", [])
                content_parts = []
                for section in sections[:3]:  # 最多显示3个部分
                    section_title = section.get("title", "")
                    if section_title:
                        content_parts.append(section_title)

                content = " | ".join(content_parts) if content_parts else "查看今日健康简报"

                # 发送推送
                result = await push_service.send_notification(
                    user_id=setting.user_id,
                    notification_type=NotificationType.MORNING_BRIEFING.value,
                    title=title,
                    content=content,
                    data={"briefing": briefing}
                )

                if result.get("success"):
                    logger.info(f"✅ 早间简报发送成功: user={setting.user_id}")

            except Exception as e:
                logger.error(f"发送早间简报失败: user={setting.user_id}, error={e}")

    async def _check_health_alerts(self, db: Session, push_service: PushService):
        """
        检查健康预警

        基于最新的健康数据检测异常指标
        """
        from app.models.daily_health import GarminData
        from app.utils.timezone import get_china_today

        today = get_china_today()

        # 获取今天有数据的用户
        today_records = db.query(GarminData).filter(
            GarminData.record_date == today
        ).all()

        for record in today_records:
            alerts = []

            # 检查静息心率异常
            if record.resting_heart_rate:
                if record.resting_heart_rate > 100:
                    alerts.append({
                        "type": "high_heart_rate",
                        "title": "⚠️ 心率偏高",
                        "content": f"今日静息心率 {record.resting_heart_rate} bpm，高于正常范围。建议休息并观察。"
                    })
                elif record.resting_heart_rate < 40:
                    alerts.append({
                        "type": "low_heart_rate",
                        "title": "⚠️ 心率偏低",
                        "content": f"今日静息心率 {record.resting_heart_rate} bpm，低于正常范围。如有不适请就医。"
                    })

            # 检查睡眠异常
            if record.sleep_score and record.sleep_score < 50:
                alerts.append({
                    "type": "poor_sleep",
                    "title": "😴 睡眠质量不佳",
                    "content": f"昨晚睡眠评分 {record.sleep_score}，建议今晚早点休息，改善睡眠环境。"
                })

            # 检查身体电量过低
            if record.body_battery_high and record.body_battery_high < 30:
                alerts.append({
                    "type": "low_energy",
                    "title": "🔋 身体电量不足",
                    "content": f"今日身体电量最高只有 {record.body_battery_high}%，身体需要休息恢复。"
                })

            # 检查压力过高
            if record.stress_avg and record.stress_avg > 70:
                alerts.append({
                    "type": "high_stress",
                    "title": "😰 压力水平较高",
                    "content": f"今日平均压力值 {record.stress_avg}，建议做些放松活动，如深呼吸、冥想。"
                })

            # 发送预警
            for alert in alerts:
                try:
                    # 检查是否已经发送过（避免重复）
                    from app.models.notification import NotificationLog
                    existing = db.query(NotificationLog).filter(
                        NotificationLog.user_id == record.user_id,
                        NotificationLog.notification_type == NotificationType.HEALTH_ALERT.value,
                        NotificationLog.data.contains({"alert_type": alert["type"]}),
                        NotificationLog.created_at >= datetime.combine(today, datetime.min.time())
                    ).first()

                    if existing:
                        continue

                    result = await push_service.send_notification(
                        user_id=record.user_id,
                        notification_type=NotificationType.HEALTH_ALERT.value,
                        title=alert["title"],
                        content=alert["content"],
                        data={"alert_type": alert["type"]},
                        respect_quiet_hours=False  # 健康预警不受免打扰限制
                    )

                    if result.get("success"):
                        logger.info(f"✅ 健康预警发送: user={record.user_id}, type={alert['type']}")

                except Exception as e:
                    logger.error(f"发送健康预警失败: user={record.user_id}, error={e}")


# ============ 全局调度器实例 ============

_scheduler: PushScheduler = None


def get_push_scheduler() -> PushScheduler:
    """获取全局推送调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = PushScheduler()
    return _scheduler


async def start_push_scheduler():
    """启动推送调度器（在应用启动时调用）"""
    scheduler = get_push_scheduler()
    asyncio.create_task(scheduler.start())


def stop_push_scheduler():
    """停止推送调度器"""
    if _scheduler:
        _scheduler.stop()
