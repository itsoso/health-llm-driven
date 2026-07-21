"""Content-free leases used to bound concurrent Agent execution."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class AgentCapacityLease(Base):
    __tablename__ = "agent_capacity_leases"

    lease_id = Column(String(64), primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    origin = Column(String(32), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_agent_capacity_active_user_expiry",
            "user_id",
            "released_at",
            "expires_at",
        ),
    )
