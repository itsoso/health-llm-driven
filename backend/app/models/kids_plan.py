"""Kids每日计划数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class KidsDailyPlan(Base):
    """Kids每日计划 - 一个用户一天一条记录"""
    __tablename__ = "kids_daily_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_date = Column(Date, nullable=False)
    items = Column(JSON, default=list)  # [{id, emoji, text, done, startTime?, endTime?}]
    awarded_tier = Column(Integer, default=0)  # 当天已发放积分的最高阶梯(0-5)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="kids_daily_plans")

    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="uq_kids_plan_user_date"),
    )
