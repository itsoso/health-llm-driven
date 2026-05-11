"""对话记忆模型 — 跨会话保留用户关键健康偏好和事实"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ConversationMemory(Base):
    """跨对话持久记忆"""
    __tablename__ = "conversation_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 记忆类型: preference / fact / instruction / allergy / medical
    memory_type = Column(String(30), nullable=False, default="fact")

    # 记忆内容
    content = Column(Text, nullable=False)

    # 来源对话
    source_conversation_id = Column(Integer, ForeignKey("chat_conversations.id"), nullable=True)

    # 相关度评分（用于排序）
    relevance_score = Column(Float, default=1.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # P3-2 (2026-05-11): 冲突解决支持 — 不删旧, 标 superseded
    status = Column(String(20), default="active")  # active / superseded / deleted
    superseded_by = Column(Integer, ForeignKey("conversation_memories.id"), nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="conversation_memories")

    __table_args__ = (
        Index('idx_memory_user_type', 'user_id', 'memory_type'),
    )

    def __repr__(self):
        return f"<ConversationMemory [{self.memory_type}] user={self.user_id}: {self.content[:40]}>"
