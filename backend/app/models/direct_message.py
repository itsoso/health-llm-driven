"""私信消息模型"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DirectMessage(Base):
    """好友私信消息"""
    __tablename__ = "direct_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

    __table_args__ = (
        Index('idx_dm_sender_receiver_time', 'sender_id', 'receiver_id', 'created_at'),
        Index('idx_dm_receiver_read', 'receiver_id', 'is_read'),
        Index('idx_dm_receiver_sender_time', 'receiver_id', 'sender_id', 'created_at'),
    )
