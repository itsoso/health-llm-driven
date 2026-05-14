"""腰围追踪模型."""

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class WaistRecord(Base):
    """腰围记录.

    腰围是代谢综合征和中心性肥胖的关键指标, 不能长期用 BMI 替代.
    """

    __tablename__ = "waist_records"
    __table_args__ = (
        Index("idx_waist_records_user_date", "user_id", "record_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    record_date = Column(Date, nullable=False, index=True)
    waist_cm = Column(Float, nullable=False)
    source = Column(String(50), default="manual")
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="waist_records")
