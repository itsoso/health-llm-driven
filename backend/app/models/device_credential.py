"""
统一设备凭证模型

支持多种设备的认证信息存储：
- Garmin: 账号密码
- 华为: OAuth Token
- Apple: 无需凭证（文件导入）
- Fitbit: OAuth Token
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import json
import os
from cryptography.fernet import Fernet

# 加密密钥
ENCRYPTION_KEY = os.getenv("DEVICE_ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # 使用默认密钥（生产环境应该从环境变量获取）
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production-123456789")
    import hashlib
    import base64
    key = hashlib.sha256(SECRET_KEY.encode()).digest()
    ENCRYPTION_KEY = base64.urlsafe_b64encode(key)

fernet = Fernet(ENCRYPTION_KEY)


class DeviceCredential(Base):
    """
    统一设备凭证表
    
    存储用户绑定的各种智能设备的认证信息
    """
    __tablename__ = "device_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # 设备类型: garmin, huawei, apple, xiaomi, fitbit
    device_type = Column(String(50), nullable=False, index=True)
    
    # 认证类型: password, oauth2, token, file
    auth_type = Column(String(20), nullable=False, default="password")
    
    # ===== 账号密码认证 (Garmin) =====
    # 加密存储的凭证 JSON: {"email": "...", "password": "..."}
    encrypted_credentials = Column(Text)
    
    # ===== OAuth 2.0 认证 (华为、Fitbit) =====
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime(timezone=True))
    oauth_scope = Column(String(500))  # 授权范围
    
    # ===== 设备特定配置 =====
    # JSON 格式: {"is_cn": true, "region": "CN", "device_id": "..."}
    config = Column(Text)
    
    # ===== 状态 =====
    is_valid = Column(Boolean, default=True)  # 凭证是否有效
    sync_enabled = Column(Boolean, default=True)  # 是否启用同步
    last_sync_at = Column(DateTime(timezone=True))  # 上次同步时间
    last_error = Column(Text)  # 上次错误信息
    error_count = Column(Integer, default=0)  # 连续错误次数
    
    # ===== 时间戳 =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关联
    user = relationship("User", backref="device_credentials")
    
    def set_credentials(self, credentials: dict):
        """
        加密并设置凭证
        
        Args:
            credentials: 凭证字典，如 {"email": "...", "password": "..."}
        """
        json_str = json.dumps(credentials)
        self.encrypted_credentials = fernet.encrypt(json_str.encode()).decode()
    
    def get_credentials(self) -> dict:
        """
        解密并获取凭证
        
        Returns:
            凭证字典
        """
        if not self.encrypted_credentials:
            return {}
        try:
            decrypted = fernet.decrypt(self.encrypted_credentials.encode())
            return json.loads(decrypted.decode())
        except Exception:
            return {}
    
    def set_config(self, config: dict):
        """设置配置"""
        self.config = json.dumps(config)
    
    def get_config(self) -> dict:
        """获取配置"""
        if not self.config:
            return {}
        try:
            return json.loads(self.config)
        except Exception:
            return {}
    
    def mark_invalid(self, error_message: str = None):
        """标记凭证无效"""
        self.is_valid = False
        self.error_count += 1
        if error_message:
            self.last_error = error_message
    
    def mark_valid(self):
        """标记凭证有效"""
        self.is_valid = True
        self.error_count = 0
        self.last_error = None
    
    def update_sync_time(self):
        """更新同步时间"""
        from datetime import datetime
        self.last_sync_at = datetime.now()
    
    def set_oauth_tokens(
        self, 
        access_token: str, 
        refresh_token: str = None, 
        expires_at: 'datetime' = None,
        scope: str = None
    ):
        """
        设置 OAuth Token
        
        Args:
            access_token: 访问令牌
            refresh_token: 刷新令牌（可选）
            expires_at: 过期时间（可选）
            scope: 授权范围（可选）
        """
        # 加密存储 access_token
        self.access_token = fernet.encrypt(access_token.encode()).decode()
        if refresh_token:
            self.refresh_token = fernet.encrypt(refresh_token.encode()).decode()
        if expires_at:
            self.token_expires_at = expires_at
        if scope:
            self.oauth_scope = scope
    
    def get_access_token(self) -> str:
        """获取解密的 access_token"""
        if not self.access_token:
            return None
        try:
            return fernet.decrypt(self.access_token.encode()).decode()
        except Exception:
            return None
    
    def get_refresh_token(self) -> str:
        """获取解密的 refresh_token"""
        if not self.refresh_token:
            return None
        try:
            return fernet.decrypt(self.refresh_token.encode()).decode()
        except Exception:
            return None
    
    def is_token_expired(self) -> bool:
        """检查 Token 是否过期"""
        if not self.token_expires_at:
            return False
        from datetime import datetime
        return datetime.now() > self.token_expires_at
    
    def to_response_dict(self) -> dict:
        """转换为响应字典（不包含敏感信息）"""
        config = self.get_config()
        return {
            "id": self.id,
            "device_type": self.device_type,
            "auth_type": self.auth_type,
            "is_valid": self.is_valid,
            "sync_enabled": self.sync_enabled,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_error": self.last_error,
            "config": config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
