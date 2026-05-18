"""Append-only intervention execution events."""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class InterventionEvent(Base):
    """User feedback on a concrete daily-plan intervention/action.

    Events are append-only facts. They describe what the user did with an
    action at a point in time without mutating the source plan.
    """

    __tablename__ = "intervention_events"
    __table_args__ = (
        Index("idx_intervention_events_user_date", "user_id", "plan_date"),
        Index("idx_intervention_events_user_action", "user_id", "action_key"),
        Index("idx_intervention_events_status", "feedback_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("daily_operating_plans.id"), nullable=True, index=True)
    plan_date = Column(Date, nullable=False, index=True)
    action_key = Column(String(160), nullable=False, index=True)
    action_domain = Column(String(40), nullable=True)
    action_title = Column(String(220), nullable=False)
    feedback_status = Column(String(20), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    source = Column(String(40), nullable=False, default="daily_plan")
    action_snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", backref="intervention_events")
    plan = relationship("DailyOperatingPlan", backref="intervention_events")
