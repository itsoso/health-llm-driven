"""One durable global decision-service switch; health records are not stored here."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, false, func

from app.database import Base


class DecisionControl(Base):
    __tablename__ = "decision_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_decision_control_singleton"),
        CheckConstraint("revision >= 0", name="ck_decision_control_revision"),
        CheckConstraint("updated_by IS NULL OR updated_by = 3", name="ck_decision_control_owner"),
    )
    id = Column(Integer, primary_key=True, autoincrement=False)
    enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    revision = Column(Integer, nullable=False, default=0, server_default="0")
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
