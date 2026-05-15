"""User-visible health advice ledger."""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class AdviceLedger(Base):
    __tablename__ = "advice_ledger"
    __table_args__ = (
        UniqueConstraint("user_id", "advice_key", name="uq_advice_ledger_user_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    advice_key = Column(String(64), nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)
    source_id = Column(String(120), nullable=False)
    domain = Column(String(50), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    metric_key = Column(String(80), nullable=True)
    target_value = Column(String(120), nullable=True)

    evidence_tier = Column(String(50), nullable=False)
    confidence = Column(String(20), nullable=False)
    claim_boundary = Column(Text, nullable=False)

    decision = Column(String(20), nullable=False, default="allowed", index=True)
    reason = Column(String(50), nullable=False, default="allowed")
    conflicts_with_id = Column(Integer, nullable=True)
    valid_for_date = Column(Date, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
