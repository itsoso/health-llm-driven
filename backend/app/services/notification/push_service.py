"""推送服务主类 - 统一管理各渠道推送"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.models.notification import (
    NotificationLog,
    UserNotificationSetting,
    ReminderConfig,
    NotificationType,
    NotificationChannel,
    NotificationStatus
)
from app.models.user import User
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class PushService:
    """
    推送服务主类

    统一管理微信、iOS、邮件等多渠道推送
    """

    def __init__(self, db: Session):
        self.db = db
        self._wechat_service = None
        self._ios_service = None
        self._telegram_service = None

    @property
    def wechat(self):
        """延迟加载微信推送服务"""
        if self._wechat_service is None:
            from .wechat_push import WeChatPushService
            self._wechat_service = WeChatPushService()
        return self._wechat_service

    @property
    def ios(self):
        """延迟加载 iOS 推送服务"""
        if self._ios_service is None:
            from .ios_push import IOSPushService
            self._ios_service = IOSPushService()
        return self._ios_service

    @property
    def telegram(self):
        """延迟加载 Telegram 推送服务"""
        if self._telegram_service is None:
            from .telegram_push import TelegramPushService
            self._telegram_service = TelegramPushService()
        return self._telegram_service

    def get_user_settings(self, user_id: int) -> Optional[UserNotificationSetting]:
        """获取用户推送设置"""
        return self.db.query(UserNotificationSetting).filter(
            UserNotificationSetting.user_id == user_id
        ).first()

    def create_or_update_settings(
        self,
        user_id: int,
        settings: Dict[str, Any]
    ) -> UserNotificationSetting:
        """创建或更新用户推送设置"""
        existing = self.get_user_settings(user_id)

        if existing:
            for key, value in settings.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            self.db.commit()
            return existing
        else:
            new_settings = UserNotificationSetting(user_id=user_id, **settings)
            self.db.add(new_settings)
            self.db.commit()
            self.db.refresh(new_settings)
            return new_settings

    def is_quiet_hours(self, user_id: int) -> bool:
        """检查当前是否在免打扰时段"""
        settings = self.get_user_settings(user_id)
        if not settings:
            return False

        now = get_china_now()
        current_time = now.strftime("%H:%M")

        start = settings.quiet_hours_start or "22:00"
        end = settings.quiet_hours_end or "07:00"

        # 处理跨越午夜的情况
        if start > end:
            # 例如 22:00 - 07:00
            return current_time >= start or current_time < end
        else:
            # 例如 01:00 - 06:00
            return start <= current_time < end

    def can_send_notification(
        self,
        user_id: int,
        notification_type: str,
        respect_quiet_hours: bool = True
    ) -> bool:
        """检查是否可以发送通知"""
        settings = self.get_user_settings(user_id)

        if not settings or not settings.enabled:
            return False

        # 检查免打扰时段（健康预警除外）
        if respect_quiet_hours and notification_type != NotificationType.HEALTH_ALERT.value:
            if self.is_quiet_hours(user_id):
                logger.info(f"用户 {user_id} 当前在免打扰时段，跳过推送")
                return False

        # 检查具体类型开关
        type_switches = {
            NotificationType.MORNING_BRIEFING.value: settings.morning_briefing_enabled,
            NotificationType.REMINDER.value: settings.reminder_enabled,
            NotificationType.HEALTH_ALERT.value: settings.health_alert_enabled,
            NotificationType.AI_ADVICE.value: settings.ai_advice_enabled,
        }

        return type_switches.get(notification_type, True)

    async def send_notification(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]] = None,
        channels: Optional[List[str]] = None,
        respect_quiet_hours: bool = True
    ) -> Dict[str, Any]:
        """
        发送推送通知

        Args:
            user_id: 用户ID
            notification_type: 通知类型
            title: 标题
            content: 内容
            data: 额外数据
            channels: 指定渠道，None 表示使用用户设置的渠道
            respect_quiet_hours: 是否遵守免打扰时段

        Returns:
            发送结果 {"success": bool, "channels": {...}}
        """
        # 检查是否可以发送
        if not self.can_send_notification(user_id, notification_type, respect_quiet_hours):
            return {
                "success": False,
                "reason": "通知已禁用或在免打扰时段"
            }

        settings = self.get_user_settings(user_id)
        results = {"success": False, "channels": {}}

        # 确定要使用的渠道
        if channels is None:
            channels = []
            if settings:
                if settings.wechat_enabled and settings.wechat_openid:
                    channels.append(NotificationChannel.WECHAT.value)
                if settings.ios_push_enabled and settings.ios_device_token:
                    channels.append(NotificationChannel.IOS_APNS.value)
            # Telegram 作为兜底通道（不依赖用户设置，只要配了 bot token）
            if self.telegram.configured:
                channels.append("telegram")

        if not channels:
            logger.warning(f"用户 {user_id} 没有可用的推送渠道")
            return {
                "success": False,
                "reason": "没有可用的推送渠道"
            }

        # 逐渠道发送
        for channel in channels:
            try:
                if channel == NotificationChannel.WECHAT.value:
                    result = await self._send_wechat(
                        user_id, settings, notification_type, title, content, data
                    )
                elif channel == NotificationChannel.IOS_APNS.value:
                    result = await self._send_ios(
                        user_id, settings, notification_type, title, content, data
                    )
                elif channel == "telegram":
                    result = await self._send_telegram(
                        user_id, notification_type, title, content, data
                    )
                else:
                    result = {"success": False, "error": f"不支持的渠道: {channel}"}

                results["channels"][channel] = result

                # 记录日志
                self._log_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    channel=channel,
                    title=title,
                    content=content,
                    data=data,
                    status=NotificationStatus.SENT.value if result.get("success") else NotificationStatus.FAILED.value,
                    error_message=result.get("error")
                )

                if result.get("success"):
                    results["success"] = True

            except Exception as e:
                logger.error(f"发送推送失败 (user={user_id}, channel={channel}): {e}")
                results["channels"][channel] = {"success": False, "error": str(e)}
                self._log_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    channel=channel,
                    title=title,
                    content=content,
                    data=data,
                    status=NotificationStatus.FAILED.value,
                    error_message=str(e)
                )

        return results

    async def _send_wechat(
        self,
        user_id: int,
        settings: UserNotificationSetting,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """发送微信订阅消息"""
        if not settings or not settings.wechat_openid:
            return {"success": False, "error": "未配置微信 OpenID"}

        return await self.wechat.send_subscription_message(
            openid=settings.wechat_openid,
            template_id=self._get_wechat_template(notification_type, settings),
            title=title,
            content=content,
            data=data
        )

    async def _send_ios(
        self,
        user_id: int,
        settings: UserNotificationSetting,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """发送 iOS APNs 推送"""
        if not settings or not settings.ios_device_token:
            return {"success": False, "error": "未配置 iOS Device Token"}

        return await self.ios.send_push(
            device_token=settings.ios_device_token,
            title=title,
            body=content,
            data=data
        )

    async def _send_telegram(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """发送 Telegram 推送（Agent Native 告警通道）"""
        severity = (data or {}).get("severity", "info")
        return await self.telegram.send_health_alert(
            title=title,
            message=content,
            severity=severity,
        )

    def _get_wechat_template(
        self,
        notification_type: str,
        settings: UserNotificationSetting
    ) -> Optional[str]:
        """获取微信模板消息 ID"""
        if not settings or not settings.wechat_template_ids:
            return None

        templates = settings.wechat_template_ids
        if isinstance(templates, dict):
            return templates.get(notification_type)
        return None

    def _log_notification(
        self,
        user_id: int,
        notification_type: str,
        channel: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]],
        status: str,
        error_message: Optional[str] = None
    ):
        """记录推送日志"""
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            channel=channel,
            title=title,
            content=content,
            data=data,
            status=status,
            error_message=error_message,
            sent_at=get_china_now() if status == NotificationStatus.SENT.value else None
        )
        self.db.add(log)
        self.db.commit()

    def get_notification_logs(
        self,
        user_id: int,
        limit: int = 50,
        notification_type: Optional[str] = None
    ) -> List[NotificationLog]:
        """获取推送日志"""
        query = self.db.query(NotificationLog).filter(
            NotificationLog.user_id == user_id
        )

        if notification_type:
            query = query.filter(NotificationLog.notification_type == notification_type)

        return query.order_by(NotificationLog.created_at.desc()).limit(limit).all()

    # ============ 提醒配置管理 ============

    def get_reminders(self, user_id: int) -> List[ReminderConfig]:
        """获取用户的提醒配置"""
        return self.db.query(ReminderConfig).filter(
            ReminderConfig.user_id == user_id,
            ReminderConfig.enabled == True
        ).all()

    def create_reminder(
        self,
        user_id: int,
        reminder_type: str,
        name: str,
        reminder_times: List[str],
        days_of_week: List[int] = None,
        message: Optional[str] = None
    ) -> ReminderConfig:
        """创建提醒配置"""
        reminder = ReminderConfig(
            user_id=user_id,
            reminder_type=reminder_type,
            name=name,
            reminder_times=reminder_times,
            days_of_week=days_of_week or [1, 2, 3, 4, 5, 6, 7],
            message=message
        )
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def update_reminder(
        self,
        reminder_id: int,
        user_id: int,
        updates: Dict[str, Any]
    ) -> Optional[ReminderConfig]:
        """更新提醒配置"""
        reminder = self.db.query(ReminderConfig).filter(
            ReminderConfig.id == reminder_id,
            ReminderConfig.user_id == user_id
        ).first()

        if not reminder:
            return None

        for key, value in updates.items():
            if hasattr(reminder, key):
                setattr(reminder, key, value)

        self.db.commit()
        return reminder

    def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        """删除提醒配置"""
        reminder = self.db.query(ReminderConfig).filter(
            ReminderConfig.id == reminder_id,
            ReminderConfig.user_id == user_id
        ).first()

        if reminder:
            self.db.delete(reminder)
            self.db.commit()
            return True
        return False

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        """
        获取当前时间应该发送的提醒

        返回格式: [{"user_id": int, "reminder": ReminderConfig}, ...]
        """
        now = get_china_now()
        current_time = now.strftime("%H:%M")
        current_day = now.isoweekday()  # 1=周一, 7=周日

        # 获取所有启用的提醒
        all_reminders = self.db.query(ReminderConfig).filter(
            ReminderConfig.enabled == True
        ).all()

        due_reminders = []
        for reminder in all_reminders:
            # 检查星期
            if current_day not in (reminder.days_of_week or [1, 2, 3, 4, 5, 6, 7]):
                continue

            # 检查时间（允许1分钟误差）
            for reminder_time in (reminder.reminder_times or []):
                if self._time_matches(current_time, reminder_time):
                    due_reminders.append({
                        "user_id": reminder.user_id,
                        "reminder": reminder
                    })
                    break

        return due_reminders

    def _time_matches(self, current: str, target: str, tolerance_minutes: int = 1) -> bool:
        """检查时间是否匹配（允许一定误差）"""
        try:
            current_parts = [int(x) for x in current.split(":")]
            target_parts = [int(x) for x in target.split(":")]

            current_minutes = current_parts[0] * 60 + current_parts[1]
            target_minutes = target_parts[0] * 60 + target_parts[1]

            return abs(current_minutes - target_minutes) <= tolerance_minutes
        except:
            return False


# ============ 预定义提醒类型 ============

PREDEFINED_REMINDERS = {
    "nasal_wash": {
        "name": "洗鼻提醒",
        "default_times": ["07:30", "19:00"],
        "message": "🌊 该用生理盐水洗鼻了！保持鼻腔清洁，预防鼻炎。"
    },
    "drink_water": {
        "name": "喝水提醒",
        "default_times": ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"],
        "message": "💧 记得喝水！保持每日饮水量 2000ml 以上。"
    },
    "exercise": {
        "name": "运动提醒",
        "default_times": ["18:00"],
        "message": "🏃 该运动了！今天的运动目标还没完成哦。"
    },
    "sleep": {
        "name": "睡眠提醒",
        "default_times": ["22:00"],
        "message": "😴 该准备睡觉了！保证 7-8 小时的优质睡眠。"
    },
    "medicine": {
        "name": "服药提醒",
        "default_times": ["08:00", "20:00"],
        "message": "💊 记得按时服药！"
    },
    "supplement": {
        "name": "补剂提醒",
        "default_times": ["08:00"],
        "message": "🍀 记得吃今天的补剂！"
    },
    "posture": {
        "name": "姿势提醒",
        "default_times": ["10:00", "14:00", "16:00"],
        "message": "🧘 注意坐姿！站起来活动一下，做几个深蹲或拉伸。"
    },
    "eye_rest": {
        "name": "护眼提醒",
        "default_times": ["10:00", "12:00", "14:00", "16:00", "18:00"],
        "message": "👀 让眼睛休息一下！远眺 20 秒，做做眼保健操。"
    }
}
