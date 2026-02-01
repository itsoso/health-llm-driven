"""用户 API Key 模型 - 允许外部系统访问用户健康数据"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class UserApiKey(Base):
    """用户 API 密钥 - 用于外部系统读取用户健康数据和写入建议"""
    __tablename__ = "user_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Index defined in __table_args__

    name = Column(String(100), nullable=False)  # 密钥名称 (如: browser-llm-driven)
    api_key = Column(String(64), unique=True, index=True, nullable=False)  # API Key (SHA256 hash)

    # 权限范围
    scopes = Column(String(255), default="read,write")  # read, write

    # 状态
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", backref="api_keys")

    __table_args__ = (
        Index('ix_user_api_keys_user_id', 'user_id'),
    )
