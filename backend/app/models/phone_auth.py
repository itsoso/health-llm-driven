"""手机号登录验证码模型."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class PhoneAuthCode(Base):
    """One-time phone code for login/register/password recovery flows."""

    __tablename__ = "auth_phone_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(32), nullable=False, index=True)
    purpose = Column(String(32), nullable=False, default="login")
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    request_ip_hash = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_auth_phone_codes_phone_purpose_created", "phone", "purpose", "created_at"),
    )


class RegistrationAdminNotification(Base):
    """Durable Telegram delivery event, committed with the new account."""

    __tablename__ = "registration_admin_notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_registration_admin_notifications_due", "status", "next_attempt_at"),
    )
