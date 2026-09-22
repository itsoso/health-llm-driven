"""User-confirmed city annotations; never a precise location history."""
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index, func
from app.database import Base
from app.models._encrypted import StrictEncryptedString


class JourneyPlace(Base):
    __tablename__ = "journey_places"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    diet_record_id = Column(Integer, ForeignKey("diet_records.id", ondelete="CASCADE"))
    life_event_id = Column(Integer, ForeignKey("health_episodes.id", ondelete="CASCADE"))
    chat_message_id = Column(Integer, ForeignKey("agent_messages.id", ondelete="CASCADE"))
    city = Column(StrictEncryptedString(1024), nullable=False)
    local_date = Column(Date, nullable=False)
    timezone = Column(String(64), nullable=False)
    location_source = Column(String(8), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("(CASE WHEN diet_record_id IS NULL THEN 0 ELSE 1 END + CASE WHEN life_event_id IS NULL THEN 0 ELSE 1 END + CASE WHEN chat_message_id IS NULL THEN 0 ELSE 1 END) = 1", name="ck_journey_one_source"),
        CheckConstraint("location_source IN ('manual', 'device')", name="ck_journey_location_source"),
        CheckConstraint("version > 0", name="ck_journey_version"),
        UniqueConstraint("user_id", "diet_record_id", name="uq_journey_owner_diet"),
        UniqueConstraint("user_id", "life_event_id", name="uq_journey_owner_life"),
        UniqueConstraint("user_id", "chat_message_id", name="uq_journey_owner_chat"),
        Index("ix_journey_owner_date_id", "user_id", "local_date", "id"),
    )
