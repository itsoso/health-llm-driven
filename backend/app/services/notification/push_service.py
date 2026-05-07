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


# H1-B: severity 排序 (低 → 高). 其他字面量默认 0.
_SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "warning": 2,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _severity_rank(s: Optional[str]) -> int:
    return _SEVERITY_ORDER.get((s or "info").lower(), 0)


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
        """检查当前是否在免打扰时段。默认 22:00–08:30（跨午夜）。"""
        settings = self.get_user_settings(user_id)
        if not settings:
            return False

        now = get_china_now()
        current_time = now.strftime("%H:%M")

        start = settings.quiet_hours_start or "22:00"
        end = settings.quiet_hours_end or "08:30"

        # 处理跨越午夜的情况
        if start > end:
            # 例如 22:00 - 08:30
            return current_time >= start or current_time < end
        else:
            # 例如 01:00 - 06:00
            return start <= current_time < end

    def can_send_notification(
        self,
        user_id: int,
        notification_type: str,
        respect_quiet_hours: bool = True,
        severity: str = "info",
        rule_id: Optional[str] = None,
    ) -> bool:
        """
        检查是否可以发送通知。

        H1-B 增强 (按影响顺序):
          1. 总开关 / 类型开关
          2. (仅 health_alert) rule_id 在用户的 alert_rule_opt_outs 里 → 不推
          3. (仅 health_alert) severity < alert_severity_threshold → 不推
          4. 免打扰时段 (critical 穿透)
        """
        settings = self.get_user_settings(user_id)

        if not settings or not settings.enabled:
            return False

        # H1-B: health_alert 的 rule 级 opt-out
        if (
            notification_type == NotificationType.HEALTH_ALERT.value
            and rule_id
        ):
            opt_outs = settings.alert_rule_opt_outs or []
            if rule_id in opt_outs:
                logger.info(f"[push] 用户 {user_id} 已 mute rule_id={rule_id}, 跳过")
                return False

        # H1-B: health_alert 的 severity 阈值
        if notification_type == NotificationType.HEALTH_ALERT.value:
            threshold = (settings.alert_severity_threshold or "warning").lower()
            if _severity_rank(severity) < _severity_rank(threshold):
                logger.info(
                    f"[push] 用户 {user_id} severity={severity} < threshold={threshold}, 跳过"
                )
                return False

        # 免打扰时段：只有 critical 级别放行
        if respect_quiet_hours and severity != "critical":
            if self.is_quiet_hours(user_id):
                logger.info(
                    f"用户 {user_id} 当前在免打扰时段，severity={severity} 跳过推送"
                )
                return False

        # 检查具体类型开关
        type_switches = {
            NotificationType.MORNING_BRIEFING.value: settings.morning_briefing_enabled,
            NotificationType.REMINDER.value: settings.reminder_enabled,
            NotificationType.HEALTH_ALERT.value: settings.health_alert_enabled,
            NotificationType.AI_ADVICE.value: settings.ai_advice_enabled,
            NotificationType.WORKOUT_ANALYSIS.value: getattr(settings, "workout_analysis_enabled", True),
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
        respect_quiet_hours: bool = True,
        severity: str = "info",
        dedup_window_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        发送推送通知

        Args:
            user_id: 用户ID
            notification_type: 通知类型
            title: 标题
            content: 内容
            data: 额外数据. data["rule_id"] 若存在 → 参与 rule 级 opt-out 检查, 并成为 dedup key
            channels: 指定渠道，None 表示使用用户设置的渠道
            respect_quiet_hours: 是否遵守免打扰时段
            severity: 严重程度 ("info"|"low"|"warning"|"medium"|"high"|"critical")；
                      只有 "critical" 在免打扰时段放行.
                      < 用户 alert_severity_threshold 的 health_alert 也会被过滤 (H1-B).
            dedup_window_hours: 去重窗口（小时）。
                                有 rule_id 时按 (user_id, notification_type, rule_id) 去重;
                                否则按 (user_id, notification_type, title) 去重.
                                传 0 或负数则禁用去重。

        Returns:
            发送结果 {"success": bool, "channels": {...}}
        """
        rule_id = (data or {}).get("rule_id") if data else None

        # 检查是否可以发送
        if not self.can_send_notification(
            user_id, notification_type, respect_quiet_hours,
            severity=severity, rule_id=rule_id,
        ):
            return {
                "success": False,
                "reason": "通知已禁用/在免打扰/低于阈值/规则已静音",
            }

        # 去重检查: 有 rule_id 时按 rule_id 去重 (同一规则窗口内只推一次),
        # 否则退化到按 title 去重 (老路径).
        # 注: 同时认 SENT 和 FAILED — 窗口内尝试过就不重试. 避免同一 alert 因
        # 多 channel (ios/telegram/wechat) 并发写 log, 每条都独立走 dedup 漏掉.
        if dedup_window_hours and dedup_window_hours > 0:
            window_start = get_china_now() - timedelta(hours=dedup_window_hours)
            dedup_q = self.db.query(NotificationLog).filter(
                NotificationLog.user_id == user_id,
                NotificationLog.notification_type == notification_type,
                NotificationLog.status.in_([
                    NotificationStatus.SENT.value,
                    NotificationStatus.FAILED.value,
                ]),
                NotificationLog.created_at >= window_start,
            )
            if rule_id:
                # PG JSONB ->> 提取 rule_id; SQLite 用字符串 LIKE 作为降级
                from sqlalchemy import text
                try:
                    existing = dedup_q.filter(
                        text("data::jsonb ->> 'rule_id' = :rid").bindparams(rid=rule_id)
                    ).first()
                except Exception:
                    # SQLite fallback
                    existing = dedup_q.filter(
                        NotificationLog.data.like(f'%"rule_id": "{rule_id}"%')
                    ).first()
            else:
                existing = dedup_q.filter(NotificationLog.title == title).first()
            if existing:
                key = f"rule_id={rule_id}" if rule_id else f"title={title!r}"
                logger.info(
                    f"用户 {user_id} 相同推送 {notification_type}/{key} "
                    f"在 {dedup_window_hours}h 窗口内已发送过 (log_id={existing.id})，跳过"
                )
                return {"success": False, "reason": "dedup"}

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

        # 逐渠道发送 — 收集各通道结果, 最后写 1 行汇总 log (2026-05-07 重构)
        channels_log: list[dict] = []
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

                # 记录到合并 log
                channels_log.append({
                    "name": channel,
                    "status": NotificationStatus.SENT.value if result.get("success") else NotificationStatus.FAILED.value,
                    "error": (result.get("error") or None) if not result.get("success") else None,
                })

                if result.get("success"):
                    results["success"] = True

            except Exception as e:
                logger.error(f"发送推送失败 (user={user_id}, channel={channel}): {e}")
                results["channels"][channel] = {"success": False, "error": str(e)}
                channels_log.append({
                    "name": channel,
                    "status": NotificationStatus.FAILED.value,
                    "error": str(e),
                })

        # 汇总写 1 行 log. 整体 status: 任一通道 sent → sent, 全败 → failed.
        # channel 列用 "multi" 表示这是新结构 log (mobile UI 可识别).
        overall_status = (
            NotificationStatus.SENT.value
            if any(c["status"] == NotificationStatus.SENT.value for c in channels_log)
            else NotificationStatus.FAILED.value
        )
        overall_err = None
        if overall_status == NotificationStatus.FAILED.value:
            # 整体 failed 时把第一个 error 放 error_message 做 quick glance
            overall_err = next((c.get("error") for c in channels_log if c.get("error")), None)
        self._log_notification_multi(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            content=content,
            data=data,
            status=overall_status,
            channels=channels_log,
            error_message=overall_err,
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

        # 从 data 里抽出 APNs category（如 MEDICATION_REMINDER），其余字段作为 custom data 下发
        category = None
        if data and "category" in data:
            data = {**data}  # shallow copy 避免改外部引用
            category = data.pop("category")

        return await self.ios.send_push(
            device_token=settings.ios_device_token,
            title=title,
            body=content,
            data=data,
            category=category,
            # 用户绑定 token 时上报的 bundle (variant 可能是 .dev / 正式),
            # APNs topic 必须匹配 token 的 bundle, 否则返 DeviceTokenNotForTopic
            bundle_id_override=getattr(settings, "ios_bundle_id", None),
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
        """记录推送日志 (legacy: 单 channel)"""
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

    def _log_notification_multi(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]],
        status: str,
        channels: list[dict],
        error_message: Optional[str] = None,
    ):
        """记录推送日志 (new: 单 row 汇总所有通道).

        channel 列存 'multi', channels JSON 存各通道状态.
        旧查询 / 旧 row 仍兼容 (channel 列还在, 值不同而已).
        """
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            channel="multi",
            title=title,
            content=content,
            data=data,
            status=status,
            error_message=error_message,
            channels=channels,
            sent_at=get_china_now() if status == NotificationStatus.SENT.value else None,
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
