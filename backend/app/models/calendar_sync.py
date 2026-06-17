"""CalDAV 日历同步:加密凭据 + 当日忙碌块。时点求解器据忙碌块避让(只读外部日历)。

安全:① 凭据(URL/账号/应用专用密码)加密存(复用 device_credential 同一把 Fernet 密钥);
② 事件标题加密存(用户选了「也存标题」)—— 标题/凭据均绝不进 LLM、绝不外发;
③ 只读外部日历(不写回);④ user_id 一律按 token 过滤。
"""
import base64
import hashlib
import json
from datetime import datetime

from cryptography.fernet import Fernet
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.config import settings
from app.database import Base

# 复用与 device_credential 同一把密钥(device/garmin encryption key,缺则从 secret_key 派生)。
ENCRYPTION_KEY = getattr(settings, "device_encryption_key", None) or getattr(settings, "garmin_encryption_key", None)
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
_fernet = Fernet(ENCRYPTION_KEY)


class CalendarCredential(Base):
    """用户的 CalDAV 凭据(每用户一条,加密)。"""
    __tablename__ = "calendar_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    provider = Column(String(40), nullable=False, default="caldav")
    # 加密 JSON: {"url","username","password"}
    encrypted_credentials = Column(Text, nullable=False)
    sync_enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def set_credentials(self, creds: dict) -> None:
        self.encrypted_credentials = _fernet.encrypt(json.dumps(creds).encode()).decode()

    def get_credentials(self) -> dict:
        if not self.encrypted_credentials:
            return {}
        try:
            return json.loads(_fernet.decrypt(self.encrypted_credentials.encode()).decode())
        except Exception:
            return {}


class CalendarBusyBlock(Base):
    """从 CalDAV 同步来的当日忙碌块(时间块 + 加密标题)。重同步按 (user,date,uid) 幂等。"""
    __tablename__ = "calendar_busy_blocks"
    __table_args__ = (
        UniqueConstraint("user_id", "event_date", "external_uid", name="uq_calbusy_user_date_uid"),
        Index("ix_calbusy_user_date", "user_id", "event_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_date = Column(Date, nullable=False)
    start_time = Column(String(5), nullable=False)  # "HH:MM"(北京日历日内)
    end_time = Column(String(5), nullable=False)
    encrypted_title = Column(Text)  # 加密事件标题(绝不进 LLM)
    external_uid = Column(String(255))  # CalDAV 事件 UID(幂等键)
    source = Column(String(20), nullable=False, default="caldav")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def set_title(self, title: str) -> None:
        self.encrypted_title = _fernet.encrypt(title.encode()).decode() if title else None

    def get_title(self) -> str:
        if not self.encrypted_title:
            return ""
        try:
            return _fernet.decrypt(self.encrypted_title.encode()).decode()
        except Exception:
            return ""
