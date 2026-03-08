"""智能提醒模型

支持 AI 对话创建的一次性/周期性提醒，按优先级分通道通知。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SmartReminder(Base):
    """智能提醒"""
    __tablename__ = "smart_reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 内容
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)

    # 时间
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # 周期性（null=一次性）
    # 格式: "daily", "weekly:1,3,5"(周一三五), "weekdays", "weekends"
    recurrence = Column(String(50), nullable=True)

    # 优先级: low / normal / high / urgent
    # low: 静默推送
    # normal: 推送 + 声音
    # high: 推送 + 声音 + 持续提醒
    # urgent: 推送 + 声音 + 电话
    priority = Column(String(20), default="normal")

    # 状态: pending / fired / cancelled / expired
    status = Column(String(20), default="pending", index=True)
    fired_at = Column(DateTime(timezone=True), nullable=True)

    # 来源
    source = Column(String(50), default="health_assistant")  # health_assistant / openclaw / manual

    # 额外数据（如位置、关联事件等）
    extra_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    user = relationship("User")
