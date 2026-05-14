"""Daily Operating Plan 模型."""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DailyOperatingPlan(Base):
    """每天的健康操作计划快照.

    v0 由 deterministic planner 生成, 后续可替换为 strict schema LLM planner.
    """

    __tablename__ = "daily_operating_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="uq_daily_operating_plans_user_date"),
        Index("idx_daily_operating_plans_user_date", "user_id", "plan_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_date = Column(Date, nullable=False, index=True)
    primary_goal = Column(String(80), default="metabolic_health")
    status = Column(String(20), default="active", index=True)
    state_summary = Column(JSON, default=dict)
    actions = Column(JSON, default=list)
    nutrition_targets = Column(JSON, default=dict)
    movement_targets = Column(JSON, default=dict)
    sleep_targets = Column(JSON, default=dict)
    measurements = Column(JSON, default=dict)
    doctor_escalation = Column(JSON, default=dict)
    verification = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="daily_operating_plans")
