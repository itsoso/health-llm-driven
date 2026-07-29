"""Client-side UI event — 用于观察期看板判断功能被用户看见 / 点击的比率.

轻量事件 (mount, open, tap). 与 InteractionFeedback 不同: 不绑 message_id.
"""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class ClientEvent(Base):
    __tablename__ = "client_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_name = Column(String(64), nullable=False, index=True)
    event_key = Column(String(64), nullable=True)
    meta = Column(JSONColumn, nullable=True)  # 可选上下文: rule_id / specialist / audit_id
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_client_events_name_created", "event_name", "created_at"),
        Index(
            "uq_client_events_owner_name_key",
            "user_id",
            "event_name",
            "event_key",
            unique=True,
        ),
    )
