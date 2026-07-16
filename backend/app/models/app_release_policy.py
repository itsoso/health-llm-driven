"""Versioned Remote Config policy for application delivery."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class AppReleasePolicy(Base):
    """Append-only release policy revisions scoped by platform and channel."""

    __tablename__ = "app_release_policies"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(32), nullable=False, index=True)
    channel = Column(String(64), nullable=False, index=True)
    config_version = Column(Integer, nullable=False)
    ota_enabled = Column(Boolean, nullable=False, default=True)
    rollout_percent = Column(Integer, nullable=False, default=100)
    minimum_native_build = Column(String(32), nullable=True)
    recommended_native_build = Column(String(32), nullable=True)
    native_update_url = Column(String(512), nullable=True)
    forced_update = Column(Boolean, nullable=False, default=False)
    kill_switches = Column(JSONColumn, nullable=False, default=dict)
    rollback_update_id = Column(String(128), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index(
            "ix_app_release_policies_scope_version",
            "platform",
            "channel",
            "config_version",
            unique=True,
        ),
    )
