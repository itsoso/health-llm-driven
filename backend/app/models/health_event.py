"""健康事件流模型 - 统一的事件中间层"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey,
    Text, JSON, Index, Enum as SAEnum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.agent_audit_log import JSONColumn
import enum


class EventStatus(str, enum.Enum):
    """事件状态(事实流摄入确认生命周期)"""
    pending = "pending"              # 待确认
    auto_confirmed = "auto_confirmed"  # 自动确认（高置信度）
    confirmed = "confirmed"          # 用户确认
    corrected = "corrected"          # 用户修正后确认
    dismissed = "dismissed"          # 用户忽略


# 时间线议程项的执行生命周期(与上面的事实流 status 正交,互不覆盖)。
# 一个被调度的全天行动 = 一条 first-class HealthEvent: pending → done | skipped | expired。
AGENDA_STATUSES = ("pending", "done", "skipped", "expired")


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

    # ── 时间线议程生命周期(Reva 首页脊柱 · Increment 1)────────────────
    # 把一个被调度的全天行动变成 first-class HealthEvent。这些列与上面的事实流
    # 摄入字段正交:agenda_status 是「该做/已做/已跳过/已过期」,独立于 status
    # (后者是「待确认/已确认/已忽略」的设备摄入语义)。NULL = 不是议程行动项。
    agenda_status = Column(String(20), index=True)  # AGENDA_STATUSES 之一; NULL=非议程项
    scheduled_for = Column(DateTime(timezone=True))  # 该行动到点的时刻(用于过期/排序)
    action_kind = Column(String(30))                 # med/supplement/movement/eyecare/nasal/diet/sleep/checkup/...
    # 双轨写回引用:{object_type, object_id, track?} —— 完成时按此回写真实 source。
    complete_ref = Column(JSONColumn)
    skip_reason = Column(String(40))                 # status=skipped 时捕获(R14)
    # 结果/洞察类项标记「相关非因果」(R4/R9);行动项默认 False。
    association_only = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True))   # agenda_status 翻成 done/skipped 的时刻

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
        # 首页脊柱按 (user, agenda_status, scheduled_for) 拉今日议程项
        Index("idx_health_events_user_agenda", "user_id", "agenda_status", "scheduled_for"),
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
