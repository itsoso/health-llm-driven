from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, JSON, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from app.database import Base


class PeriodGoal(Base):
    """阶段性健康目标（月度/年度）"""
    __tablename__ = "period_goals"
    __table_args__ = (
        Index('ix_period_goal_user', 'user_id', 'period_type', 'status'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    period_type = Column(String(20), nullable=False)  # "monthly" / "yearly"
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    status = Column(String(20), default="active")  # active / completed / archived

    # AI 生成内容
    focus_areas = Column(JSON, default=list)
    summary = Column(Text, nullable=True)
    ai_model = Column(String(100), nullable=True)

    # 用户反馈
    user_feedback = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    metrics = relationship("PeriodGoalMetric", back_populates="goal", cascade="all, delete-orphan")


class PeriodGoalMetric(Base):
    """目标的具体指标"""
    __tablename__ = "period_goal_metrics"
    __table_args__ = (
        Index('ix_metric_goal', 'goal_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("period_goals.id", ondelete="CASCADE"), nullable=False)

    metric_type = Column(String(50), nullable=False)  # weight / bmi / waist / body_fat / blood_pressure_sys / blood_glucose
    metric_name = Column(String(100), nullable=True)   # 显示名："体重"
    current_value = Column(Float, nullable=True)       # 当前值（生成时快照）
    target_value = Column(Float, nullable=True)        # 目标值
    unit = Column(String(20), nullable=True)           # kg / cm / ...

    # 里程碑
    milestones = Column(JSON, nullable=True)  # [{"week": 1, "target": 79.5, "action": "..."}, ...]

    # 策略
    strategy = Column(Text, nullable=True)  # AI 建议的达成策略

    goal = relationship("PeriodGoal", back_populates="metrics")
