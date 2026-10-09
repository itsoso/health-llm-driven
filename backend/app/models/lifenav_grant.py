"""Recipient-bound grants; only credential digests are stored."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.database import Base


class LifeNavGrant(Base):
    __tablename__ = 'lifenav_grants'

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    recipient_id = Column(String(100), nullable=False)
    audience = Column(String(20), nullable=False, default='lifenav')
    scope = Column(String(40), nullable=False, default='navigation:generic')
    window_policy = Column(String(40), nullable=False, default='current_trailing7')
    policy_version = Column(String(40), nullable=False)
    redirect_uri = Column(String(500), nullable=False)
    recipient_secret_hash = Column(String(64), nullable=False)
    state_hash = Column(String(64), nullable=False)
    code_challenge = Column(String(43), nullable=False)
    code_hash = Column(String(64), nullable=False, unique=True)
    code_expires_at = Column(DateTime(timezone=True), nullable=False)
    code_used_at = Column(DateTime(timezone=True))
    token_hash = Column(String(64), unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))


class LifeNavAccessAudit(Base):
    __tablename__ = 'lifenav_access_audits'

    id = Column(Integer, primary_key=True)
    grant_id = Column(String(36), ForeignKey('lifenav_grants.id'), nullable=True, index=True)
    request_id = Column(String(36), nullable=False)
    field_category = Column(String(40), nullable=False, default='navigation:generic')
    outcome = Column(String(20), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
