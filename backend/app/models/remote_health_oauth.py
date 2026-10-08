"""Revocable, per-user OAuth grants. Credentials are stored only as SHA-256 hashes."""
from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class RemoteHealthGrant(Base):
    __tablename__ = "remote_health_grants"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(200), nullable=False)
    scope = Column(String(32), nullable=False)
    resource = Column(String(500), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    expires_at = Column(BigInteger, nullable=False)
    revoked_at = Column(BigInteger)


class RemoteHealthCredential(Base):
    __tablename__ = "remote_health_credentials"
    digest = Column(String(64), primary_key=True)
    kind = Column(String(16), nullable=False)
    grant_id = Column(String(36), ForeignKey("remote_health_grants.id", ondelete="CASCADE"), index=True)
    expires_at = Column(BigInteger, nullable=False, index=True)
    used_at = Column(BigInteger)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict)


class RemoteHealthRateBucket(Base):
    __tablename__ = "remote_health_rate_buckets"
    key = Column(String(80), primary_key=True)
    window = Column(BigInteger, primary_key=True)
    count = Column(Integer, nullable=False)
    __table_args__ = (Index("ix_remote_health_rate_window", "window"),)
