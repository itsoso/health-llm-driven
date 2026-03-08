"""智能提醒服务

负责检查到期提醒并通过多通道发送通知。
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.smart_reminder import SmartReminder
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class ReminderService:
    """智能提醒服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_due_reminders(self) -> List[SmartReminder]:
        """获取所有到期但未触发的提醒（1分钟窗口）"""
        now = get_china_now()
        window_start = now - timedelta(minutes=1)

        return self.db.query(SmartReminder).filter(
            SmartReminder.status == "pending",
            SmartReminder.remind_at <= now,
            SmartReminder.remind_at >= window_start,
        ).all()

    async def fire_reminder(self, reminder: SmartReminder):
        """触发单个提醒"""
        from app.services.notification.push_service import PushService

        push = PushService(self.db)
        priority = reminder.priority or "normal"

        # 根据优先级决定是否忽略免打扰
        respect_quiet = priority in ("low",)

        # 发送推送通知
        result = await push.send_notification(
            user_id=reminder.user_id,
            notification_type="reminder",
            title=reminder.title,
            content=reminder.message or reminder.title,
            data={
                "reminder_id": reminder.id,
                "priority": priority,
                "sound": priority != "low",
            },
            respect_quiet_hours=respect_quiet,
        )

        logger.info(
            f"提醒已触发: user={reminder.user_id}, title='{reminder.title}', "
            f"priority={priority}, push_result={result.get('success')}"
        )

        # 更新状态
        reminder.status = "fired"
        reminder.fired_at = get_china_now()
        self.db.commit()

        # 周期性提醒：创建下一次
        if reminder.recurrence:
            self._schedule_next(reminder)

    def _schedule_next(self, reminder: SmartReminder):
        """为周期性提醒创建下一次"""
        recurrence = reminder.recurrence
        remind_at = reminder.remind_at

        if recurrence == "daily":
            next_time = remind_at + timedelta(days=1)
        elif recurrence == "weekdays":
            next_time = remind_at + timedelta(days=1)
            while next_time.weekday() >= 5:  # 跳过周末
                next_time += timedelta(days=1)
        elif recurrence == "weekends":
            next_time = remind_at + timedelta(days=1)
            while next_time.weekday() < 5:  # 跳过工作日
                next_time += timedelta(days=1)
        elif recurrence.startswith("weekly:"):
            # weekly:1,3,5 表示周一三五
            days_str = recurrence.split(":")[1]
            target_days = [int(d) - 1 for d in days_str.split(",")]  # 转为0-6
            next_time = remind_at + timedelta(days=1)
            for _ in range(7):
                if next_time.weekday() in target_days:
                    break
                next_time += timedelta(days=1)
        else:
            return  # 未知周期类型，不创建下一次

        new_reminder = SmartReminder(
            user_id=reminder.user_id,
            title=reminder.title,
            message=reminder.message,
            remind_at=next_time,
            recurrence=reminder.recurrence,
            priority=reminder.priority,
            source=reminder.source,
            extra_data=reminder.extra_data,
            status="pending",
        )
        self.db.add(new_reminder)
        self.db.commit()
        logger.info(f"周期性提醒已安排下一次: {next_time.strftime('%Y-%m-%d %H:%M')}")

    async def fire_all_due(self) -> int:
        """检查并触发所有到期提醒，返回触发数量"""
        due = self.get_due_reminders()
        if not due:
            return 0

        fired = 0
        for reminder in due:
            try:
                await self.fire_reminder(reminder)
                fired += 1
            except Exception as e:
                logger.error(f"触发提醒失败 (id={reminder.id}): {e}")
                reminder.status = "fired"  # 避免反复重试
                reminder.fired_at = get_china_now()
                self.db.commit()

        return fired

    def expire_old_reminders(self):
        """将超过24小时未触发的一次性提醒标记为过期"""
        cutoff = get_china_now() - timedelta(hours=24)
        expired = self.db.query(SmartReminder).filter(
            SmartReminder.status == "pending",
            SmartReminder.recurrence.is_(None),
            SmartReminder.remind_at < cutoff,
        ).all()

        for r in expired:
            r.status = "expired"

        if expired:
            self.db.commit()
            logger.info(f"已标记 {len(expired)} 个过期提醒")
