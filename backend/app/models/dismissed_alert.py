"""用户主动忽略/标记已知的安全告警。"""

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class DismissedAlert(Base):
    __tablename__ = "dismissed_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rule_id = Column(String(100), nullable=False, index=True)  # e.g. "labs.liver_enzyme_pattern"
    reason = Column(String(30), default="known")  # known / resolved / false_positive
    note = Column(Text)  # 用户备注（如"25年复查已正常"）
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now())
