"""健康协议层模型(Reva Personal Health OS 重设计 P1 第一刀)。

HealthProtocol = 用户为某个域「一次设定的最佳实践」(固定容器/预承诺/被动设备/环境默认),
把「量」外包给容器/先验、把「采集」外包给设备,投影出每日待办,完成式确认。

双轨录入(PRD 原则 ⑧):每个协议同时支持
  - 协议轨(protocol):一键 ✓ / 自动观测 / 设备同步
  - 手工轨(manual):逐量录入,始终可用
两轨都写 **同一张 HealthProtocolEvent**(同一事件流),outcome 不区分来源;手工永不被取代。

详见 docs/prd/reva-personal-health-os-prd.md §4.2 / §5。
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text, Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


# 域:覆盖 PRD §5 双轨表的环节
PROTOCOL_DOMAINS = (
    "hydration", "diet", "sleep", "training", "medication",
    "supplement", "measurement", "mood", "activity", "exercise", "checkup",
)
# 机制:量为何隐式
PROTOCOL_MECHANISMS = ("fixed_container", "pre_commit", "passive_device", "environment_default")


class HealthProtocol(Base):
    """用户为某域设定的最佳实践协议。Program 与 Agenda 之间的投影层。"""
    __tablename__ = "health_protocols"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    domain = Column(String(20), nullable=False)        # PROTOCOL_DOMAINS 之一
    name = Column(String(200), nullable=False)         # "2000ml 温水杯"
    mechanism = Column(String(30))                     # PROTOCOL_MECHANISMS 之一
    implied_quantity = Column(JSONB)                   # 协议先验,如 {"water_ml":2000,"temp_c":50}

    cadence = Column(String(20), default="daily")      # daily/weekly/per_meal_slot/event_triggered/quarterly/annual
    time_window = Column(String(20), default="anytime")  # morning/noon/afternoon/evening/bedtime/anytime

    # 完成判定(双轨)
    completion_mode = Column(String(20), default="one_tap")  # one_tap/auto_observed/device_synced(协议轨默认形态)
    can_default_complete = Column(Boolean, default=False)    # R12 边界:饮水可默认完成;用药/测量禁止
    manual_track_allowed = Column(Boolean, default=True)     # 手工轨始终可用(原则 ⑧)

    status = Column(String(20), default="active")      # active/paused/archived
    # 关联(可空):疗程/项目/目标记录表,后续 slice 接 HealthProgram/HealthProblem
    program_id = Column(Integer)
    source_model = Column(String(50))                  # 协议完成落到哪张业务表(water_records / medication_logs / diet_records)
    source_id = Column(Integer)                        # 链接的具体业务记录 id(如 Medication.id),完成时写真实记录

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="health_protocols")
    events = relationship("HealthProtocolEvent", back_populates="protocol", lazy="dynamic")

    __table_args__ = (
        Index("ix_health_protocols_user_status", "user_id", "status"),
        Index("ix_health_protocols_user_domain", "user_id", "domain"),
    )


class HealthProtocolEvent(Base):
    """协议完成/跳过事件 —— 双轨合流的统一事件流(= PRD 主循环的 Execution Event)。"""
    __tablename__ = "health_protocol_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    protocol_id = Column(Integer, ForeignKey("health_protocols.id"), nullable=False)

    event_date = Column(Date, nullable=False)          # 归属哪一天(按 cadence 去重)
    status = Column(String(20), nullable=False)        # completed/skipped/snoozed/auto_observed
    track = Column(String(10), nullable=False, default="protocol")  # protocol/manual
    value = Column(JSONB)                              # 手工轨可带实际量;协议轨多为空(用 implied_quantity)
    skip_reason = Column(String(40))                   # R14:no_time/forgot/no_supply/too_tired/wrong_place/too_hard/unwell/social

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="health_protocol_events")
    protocol = relationship("HealthProtocol", back_populates="events")

    __table_args__ = (
        # 每协议每天一条终态事件(本表语义)。腕上双击 / bridge 重发 / 重试的并发写
        # 由此唯一约束兜底:第二条 (protocol_id, event_date) 撞约束 → IntegrityError,
        # 配合 complete_protocol 的原子 UPDATE 门保证领域记录最多写一次(D1)。
        UniqueConstraint("protocol_id", "event_date", name="uq_hpe_protocol_date"),
        Index("ix_hpe_user_date", "user_id", "event_date"),
    )


# R14 失败原因枚举(供 service 校验 + 前端下拉)
SKIP_REASONS = (
    "no_time", "forgot", "no_supply", "too_tired", "wrong_place", "too_hard", "unwell", "social",
)
