"""通用身体症状记录 (eye itch / sore throat / skin rash 等偶发症状)。

设计要点:
- 与 disease_tracking.SymptomLog 不同, 本表不绑 UserDiseaseProfile,
  适合"今天眼睛痒"这种偶发症状的低门槛录入
- LLM 通过 health_record(record_type="symptom") 工具自动写入
- 鼻炎专用打卡仍走 disease_tracking, 双源并存
"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SymptomEntry(Base):
    __tablename__ = "symptom_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # eye / respiratory / skin / digestive / musculoskeletal / head / general / other
    body_part = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    severity = Column(Integer, nullable=True)            # 1-10
    triggers = Column(JSON, default=list)                # ["pollen","dust"] LLM 抽取
    duration_minutes = Column(Integer, nullable=True)
    source = Column(String, default="manual")            # manual / voice / siri
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", backref="symptom_entries")

    __table_args__ = (
        Index('idx_symptom_user_occurred', 'user_id', 'occurred_at'),
    )
