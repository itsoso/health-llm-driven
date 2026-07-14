"""Durable account deletion requests used by the App Store privacy workflow."""

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"

    id = Column(Integer, primary_key=True, index=True)
    # Kept as an audit snapshot after the user row is removed.
    user_id = Column(Integer, nullable=False, index=True)
    # Non-null only while the request is active. The unique constraint makes
    # concurrent duplicate submissions fail closed into one active request.
    active_user_id = Column(Integer, nullable=True, unique=True, index=True)
    status = Column(String(20), nullable=False, default="requested", index=True)
    channel = Column(String(30), nullable=False, default="mobile_app")
    scope = Column(Text, nullable=False, default="account,health_data,device_connections")
    audit_id = Column(Integer, nullable=True, unique=True)
    processing_admin_id = Column(Integer, nullable=True)
    processing_note = Column(Text, nullable=True)
    verification_reference = Column(String(200), nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'processing', 'completed', 'rejected')",
            name="ck_account_deletion_requests_status",
        ),
    )
