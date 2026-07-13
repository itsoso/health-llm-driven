"""推送调度器 - 定时发送推送通知"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.notification import UserNotificationSetting, ReminderConfig, NotificationType
from app.services.notification.push_service import (
    PushService,
    PREDEFINED_REMINDERS,
    normalize_morning_sleep_floor_time,
)
from app.services.ai_scheduler import AISchedulerService
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


HEALTH_ALERT_RULES: Dict[str, Dict[str, str]] = {
    "high_heart_rate": {
        "rule_id": "wearable.high_resting_heart_rate",
        "evidence_domain": "vitals_safety",
    },
    "low_heart_rate": {
        "rule_id": "wearable.low_resting_heart_rate",
        "evidence_domain": "vitals_safety",
    },
    "poor_sleep": {
        "rule_id": "wearable.poor_sleep_score",
        "evidence_domain": "sleep_recovery",
    },
    "low_energy": {
        "rule_id": "wearable.low_body_battery",
        "evidence_domain": "sleep_recovery",
    },
    "high_stress": {
        "rule_id": "wearable.high_stress",
        "evidence_domain": "recovery_stress",
    },
}

HEALTH_ALERT_CLAIM_BOUNDARY = (
    "该推送来自可穿戴数据的确定性安全阈值规则，只用于提示复核和采取保守行动，"
    "不替代医生诊断、治疗或用药建议。"
)


def build_health_alert_evidence_contract(alert_type: str) -> Dict[str, Any]:
    """Build KB V2 evidence metadata for deterministic wearable alerts."""
    rule = HEALTH_ALERT_RULES.get(
        alert_type,
        {
            "rule_id": f"wearable.{alert_type or 'unknown'}",
            "evidence_domain": "vitals_safety",
        },
    )
    return {
        "rule_id": rule["rule_id"],
        "rule_source": "push_scheduler.wearable_threshold",
        "evidence_domain": rule["evidence_domain"],
        "evidence_refs": [],
        "evidence_ref_count": 0,
        "support_status": "safety_alert",
        "unsupported": False,
        "unsupported_reason": None,
        "planner_evidence_policy": {
            "blocked": False,
            "kept_reason": "safety_or_data_gap",
        },
        "claim_boundary": HEALTH_ALERT_CLAIM_BOUNDARY,
    }


def build_health_alert_push_data(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Return push payload data with KB V2 policy fields."""
    alert_type = str(alert.get("type") or "unknown")
    severity = str(alert.get("severity") or "warning").lower()
    return {
        "alert_type": alert_type,
        "severity": severity,
        **build_health_alert_evidence_contract(alert_type),
    }


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
                quiet_hours_policy = "drop" if reminder.reminder_type == "sleep" else None
                result = await push_service.send_notification(
                    user_id=user_id,
                    notification_type=NotificationType.REMINDER.value,
                    title=reminder.name,
                    content=message,
                    data={
                        "reminder_id": reminder.id,
                        "reminder_type": reminder.reminder_type
                    },
                    quiet_hours_policy=quiet_hours_policy,
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

        # 查找需要发送早间简报的用户。历史用户可能已存 07:30/08:00;
        # effective time 统一钳到 09:00,避免睡眠窗口内打扰。
        candidate_settings = db.query(UserNotificationSetting).filter(
            UserNotificationSetting.enabled == True,
            UserNotificationSetting.morning_briefing_enabled == True,
        ).all()
        settings = [
            setting
            for setting in candidate_settings
            if normalize_morning_sleep_floor_time(setting.morning_briefing_time)
            == current_time
        ]

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
                        "severity": "high",
                        "title": "⚠️ 心率偏高",
                        "content": f"今日静息心率 {record.resting_heart_rate} bpm，高于正常范围。建议休息并观察。"
                    })
                elif record.resting_heart_rate < 40:
                    alerts.append({
                        "type": "low_heart_rate",
                        "severity": "critical",
                        "title": "⚠️ 心率偏低",
                        "content": f"今日静息心率 {record.resting_heart_rate} bpm，低于正常范围。如有不适请就医。"
                    })

            # 检查睡眠异常
            if record.sleep_score and record.sleep_score < 50:
                alerts.append({
                    "type": "poor_sleep",
                    "severity": "warning",
                    "title": "😴 睡眠质量不佳",
                    "content": f"昨晚睡眠评分 {record.sleep_score}，建议今晚早点休息，改善睡眠环境。"
                })

            # 检查身体电量过低
            body_battery_high = getattr(record, "body_battery_most_charged", None)
            if body_battery_high and body_battery_high < 30:
                alerts.append({
                    "type": "low_energy",
                    "severity": "warning",
                    "title": "🔋 身体电量不足",
                    "content": f"今日身体电量最高只有 {body_battery_high}%，身体需要休息恢复。"
                })

            # 检查压力过高
            stress_avg = getattr(record, "stress_level", None)
            if stress_avg and stress_avg > 70:
                alerts.append({
                    "type": "high_stress",
                    "severity": "warning",
                    "title": "😰 压力水平较高",
                    "content": f"今日平均压力值 {stress_avg}，建议做些放松活动，如深呼吸、冥想。"
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

                    alert_data = build_health_alert_push_data(alert)
                    severity = str(alert.get("severity") or "warning").lower()
                    result = await push_service.send_notification(
                        user_id=record.user_id,
                        notification_type=NotificationType.HEALTH_ALERT.value,
                        title=alert["title"],
                        content=alert["content"],
                        data=alert_data,
                        respect_quiet_hours=True,
                        severity=severity,
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
