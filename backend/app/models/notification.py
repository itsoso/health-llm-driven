"""推送通知模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class NotificationChannel(str, enum.Enum):
    """推送渠道"""
    WECHAT = "wechat"  # 微信小程序订阅消息
    IOS_APNS = "ios_apns"  # iOS APNs
    EMAIL = "email"  # 邮件（预留）
    SMS = "sms"  # 短信（预留）


class NotificationType(str, enum.Enum):
    """通知类型"""
    MORNING_BRIEFING = "morning_briefing"  # 早间健康简报
    REMINDER = "reminder"  # 定时提醒（洗鼻、喝水等）
    HEALTH_ALERT = "health_alert"  # 健康异常预警
    AI_ADVICE = "ai_advice"  # AI 建议推送
    GOAL_PROGRESS = "goal_progress"  # 目标进度提醒
    WEEKLY_REPORT = "weekly_report"  # 周报
    WORKOUT_ANALYSIS = "workout_analysis"  # 跑后教练 — Garmin 同步后自动分析 + 推送


class NotificationStatus(str, enum.Enum):
    """推送状态"""
    PENDING = "pending"  # 待发送
    SENT = "sent"  # 已发送
    DELIVERED = "delivered"  # 已送达
    READ = "read"  # 已读
    FAILED = "failed"  # 发送失败


class UserNotificationSetting(Base):
    """用户推送设置"""
    __tablename__ = "user_notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    # 推送开关
    enabled = Column(Boolean, default=True)  # 总开关
    morning_briefing_enabled = Column(Boolean, default=True)  # 早间简报
    reminder_enabled = Column(Boolean, default=True)  # 定时提醒
    health_alert_enabled = Column(Boolean, default=True)  # 健康预警
    ai_advice_enabled = Column(Boolean, default=True)  # AI 建议
    workout_analysis_enabled = Column(Boolean, default=True)  # 跑后教练推送 (W3)

    # 推送时间设置
    morning_briefing_time = Column(String(5), default="07:30")  # 早间简报时间 HH:MM
    quiet_hours_start = Column(String(5), default="22:00")  # 免打扰开始
    quiet_hours_end = Column(String(5), default="08:30")  # 免打扰结束

    # 告警严重度阈值 (H1-B): info/warning/critical
    # 低于此阈值的 health_alert 直接不推 (白天也不推). 默认 warning = 屏蔽 info 级噪音.
    # critical 永远放行, 不受此阈值约束 (配合 critical 穿透 quiet_hours 的既有策略).
    alert_severity_threshold = Column(String(20), default="warning")
    # 已静音的规则 rule_id 列表, 例: ["vitals.sleep_short", "ddi.warfarin_nsaid"]
    # 命中这些 rule_id 的 health_alert 不推. 非 health_alert 不受影响.
    alert_rule_opt_outs = Column(JSON, default=list)
    # L9 (Karpathy partial autonomy): 告警的"反应方式"自治档位
    # 'silent'   只写 alerts tab, 不推送
    # 'notify'   推送, deep_link 跳 trace 详情页 (不开口对话)
    # 'converse' 推送 + voice-chat 主动开口问 follow-up (默认, Agent Native 闭环)
    alert_clarify_mode = Column(String(20), default="converse")

    # 渠道设置
    wechat_enabled = Column(Boolean, default=True)
    ios_push_enabled = Column(Boolean, default=True)

    # 微信小程序设置
    wechat_openid = Column(String(100), nullable=True)  # 微信 OpenID
    wechat_template_ids = Column(JSON, nullable=True)  # 订阅的模板消息ID

    # iOS 推送设置
    ios_device_token = Column(String(200), nullable=True)  # APNs Device Token

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="notification_settings")


class NotificationLog(Base):
    """推送日志"""
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 通知内容
    notification_type = Column(String(50), nullable=False, index=True)
    channel = Column(String(20), nullable=False)  # wechat, ios_apns, email
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)  # 额外数据

    # 状态
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)

    # 时间
    scheduled_at = Column(DateTime(timezone=True), nullable=True)  # 计划发送时间
    sent_at = Column(DateTime(timezone=True), nullable=True)  # 实际发送时间
    delivered_at = Column(DateTime(timezone=True), nullable=True)  # 送达时间
    read_at = Column(DateTime(timezone=True), nullable=True)  # 阅读时间

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User")


class ReminderConfig(Base):
    """用户提醒配置"""
    __tablename__ = "reminder_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 提醒类型
    reminder_type = Column(String(50), nullable=False)  # nasal_wash, drink_water, exercise, medicine, etc.
    name = Column(String(100), nullable=False)  # 自定义名称

    # 提醒时间
    reminder_times = Column(JSON, nullable=False)  # ["07:30", "12:00", "19:00"]
    days_of_week = Column(JSON, default=[1, 2, 3, 4, 5, 6, 7])  # 1=周一, 7=周日

    # 提醒内容
    message = Column(Text, nullable=True)  # 自定义提醒内容

    # 状态
    enabled = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    user = relationship("User")
