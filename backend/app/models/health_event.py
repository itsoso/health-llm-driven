"""健康事件流模型 - 统一的事件中间层"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Text, JSON, Index, Enum as SAEnum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class EventStatus(str, enum.Enum):
    """事件状态"""
    pending = "pending"              # 待确认
    auto_confirmed = "auto_confirmed"  # 自动确认（高置信度）
    confirmed = "confirmed"          # 用户确认
    corrected = "corrected"          # 用户修正后确认
    dismissed = "dismissed"          # 用户忽略


class HealthEvent(Base):
    """健康事件 - 统一的事件流表"""
    __tablename__ = "health_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 事件类型：weight, blood_pressure, water, excretion, supplement, exercise, diet, sleep, mood
    event_type = Column(String(50), nullable=False, index=True)

    # 来源：nfc_tag, bluetooth_scale, voice, photo, garmin_sync, manual, api
    source = Column(String(50), nullable=False)
    source_device_id = Column(String(100))  # 关联 EventSource

    # 原始数据（来自传感器/设备的未处理数据）
    raw_data = Column(JSON)

    # AI 推理结果（从原始数据推断出的结构化数据）
    ai_inference = Column(JSON)

    # 置信度 0.0-1.0
    confidence = Column(Float, default=0.0)

    # 状态
    status = Column(
        SAEnum(EventStatus, values_callable=lambda x: [e.value for e in x]),
        default=EventStatus.pending,
        nullable=False,
        index=True,
    )

    # 最终确认的数据（用户确认/修正后的结构化数据）
    confirmed_data = Column(JSON)

    # 关联到目标记录表
    target_record_type = Column(String(50))  # weight_records, blood_pressure_records, ...
    target_record_id = Column(Integer)       # 写入后的记录 ID

    # 时间戳
    event_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True))

    # 关系
    user = relationship("User", backref="health_events")

    __table_args__ = (
        Index("idx_health_events_user_status", "user_id", "status"),
        Index("idx_health_events_user_type", "user_id", "event_type"),
        Index("idx_health_events_event_time", "user_id", "event_time"),
    )


class EventSource(Base):
    """事件来源 - 设备/传感器注册表"""
    __tablename__ = "event_sources"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 来源类型：nfc_tag, bluetooth_scale, bluetooth_bp, api_webhook
    source_type = Column(String(50), nullable=False)

    # 设备标识（NFC tag UID, BLE MAC 地址等）
    device_id = Column(String(100), nullable=False)

    # 显示名称
    name = Column(String(100), nullable=False)

    # 绑定的事件类型
    event_type = Column(String(50), nullable=False)

    # 设备配置（JSON，如 NFC tag 对应的动作参数）
    config = Column(JSON, default=dict)

    # 自动确认阈值（置信度超过此值自动确认，0 表示永不自动确认）
    auto_confirm_threshold = Column(Float, default=0.8)

    # 是否启用
    is_active = Column(String(10), default="true")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    user = relationship("User", backref="event_sources")

    __table_args__ = (
        Index("idx_event_sources_user", "user_id"),
        Index("idx_event_sources_device", "device_id"),
    )
