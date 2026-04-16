"""对话分享模型 — 生成公网可访问的对话快照"""
import secrets
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Boolean
from app.database import Base


class SharedConversation(Base):
    """分享的对话快照"""
    __tablename__ = "shared_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 分享 token（URL 标识）
    share_token = Column(String(32), unique=True, nullable=False, index=True,
                         default=lambda: secrets.token_hex(16))

    # 来源对话
    source_type = Column(String(20), nullable=False, default="health")  # health / openclaw
    source_conversation_id = Column(Integer, nullable=False)

    # 快照数据（JSON 存储消息列表）
    title = Column(String(200), nullable=False, default="分享的对话")
    messages_snapshot = Column(JSON, nullable=False)  # [{role, content, created_at}]

    # 分享人信息（脱敏后的显示名）
    sharer_name = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=True)  # None = 永不过期
    view_count = Column(Integer, default=0)
