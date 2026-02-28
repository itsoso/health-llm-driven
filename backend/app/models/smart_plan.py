from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, JSON, ForeignKey, Text, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class WeeklyPlan(Base):
    """AI 生成的周计划"""
    __tablename__ = "weekly_plans"
    __table_args__ = (
        UniqueConstraint('user_id', 'week_start', name='uq_user_week'),
        Index('ix_weekly_plan_user_status', 'user_id', 'status'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    focus_areas = Column(JSON, default=list)
    weekly_summary = Column(Text, nullable=True)
    completion_rate = Column(Float, default=0.0)
    ai_model = Column(String(100), nullable=True)
    user_feedback = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship("PlanItem", back_populates="plan", cascade="all, delete-orphan")


class PlanItem(Base):
    """周计划中的单个行动项"""
    __tablename__ = "plan_items"
    __table_args__ = (
        Index('ix_plan_item_plan_day', 'plan_id', 'day_of_week'),
    )

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    category = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    target_value = Column(Float, nullable=True)
    target_unit = Column(String(20), nullable=True)
    checkin_template_id = Column(Integer, ForeignKey("checkin_templates.id"), nullable=True)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("WeeklyPlan", back_populates="items")
