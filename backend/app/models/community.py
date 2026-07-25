"""Privacy-minimized peer support models.

Community posts are explicit projections of owned records. They never contain
the original photo, notes, diagnosis, medication, location, or weight context.
"""
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class CommunityPost(Base):
    __tablename__ = "community_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_type = Column(String(40), nullable=False)
    source_id = Column(Integer, nullable=False)
    snapshot = Column(JSONColumn, nullable=False)
    caption = Column(Text, nullable=True)
    idempotency_key = Column(String(160), nullable=False)
    status = Column(String(24), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_community_posts_user_idempotency"),
        Index(
            "uq_community_posts_active_source",
            "user_id",
            "source_type",
            "source_id",
            unique=True,
            postgresql_where=sql_text("status <> 'deleted'"),
            sqlite_where=sql_text("status <> 'deleted'"),
        ),
        Index("ix_community_posts_status_created", "status", "created_at"),
    )


class CommunityReaction(Base):
    __tablename__ = "community_reactions"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(
        Integer,
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reaction = Column(String(24), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_community_reactions_post_user"),
    )


class CommunityReport(Base):
    __tablename__ = "community_reports"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(
        Integer,
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reason = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_community_reports_post_user"),
    )
