"""C1 周健身计划 —— T2 自治(系统起草,用户一键确认)。

trust_tier 语义沿用 write_intent:系统生成提议(status=proposed),用户确认后才落地排程。
一周一行(UniqueConstraint user_id+week_start),确认幂等靠原子 UPDATE...WHERE status='proposed'
的 rowcount 门(与 write_intent.confirm / 依从写回同模式),确认两次不重复排程。

days 是完整的一周(7 天)结构化 JSON 快照(day_type/workout/rationale),由 service 生成时写定,
确认后排程消费它建 SmartReminder(确认产物)。不在此存因果裁决,不出处方剂量(R4)。
"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class FitnessPlan(Base):
    __tablename__ = "fitness_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    week_start = Column(Date, nullable=False)  # 周一(Asia/Shanghai)

    # proposed → confirmed / dismissed
    status = Column(String(20), nullable=False, default="proposed", index=True)

    goal = Column(String(40), nullable=True)        # 增肌/减脂/心肺/维持
    acwr = Column(Float, nullable=True)             # 生成时快照(可空)
    readiness_note = Column(Text, nullable=True)

    days = Column(JSONColumn, nullable=False)        # 7 天结构化快照(见 service)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # 一周一计划:幂等去重 + 防同周多次提议
        UniqueConstraint("user_id", "week_start", name="uq_fitness_plan_user_week"),
        Index("ix_fitness_plans_user_status", "user_id", "status"),
    )
