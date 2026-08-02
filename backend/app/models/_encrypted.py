"""EncryptedString —— SQLAlchemy TypeDecorator 透明 Fernet 加密列 (C 优化, 2026-05-13).

用法:
  from app.models._encrypted import EncryptedString
  class Foo(Base):
      genotype = Column(EncryptedString(200))   # 写入时自动加密, 读取时自动解密

设计:
- 用 GARMIN_ENCRYPTION_KEY (复用现有 Fernet key, 不再新建 .env 项目)
- 旧明文行 graceful fallback: decrypt 失败时返回原值, 让一段过渡期共存
- WHERE filter 不能直接用 (== 'CT' 等会比对加密后字符串). 调用方只能 attribute access
- Fernet 输出 base64, ~140 字符. EncryptedString(N) 的 N 应 ≥ 原值长度 × 3 才稳

迁移流程:
1. 改 model 列类型为 EncryptedString
2. 跑 ORM-load + re-save 脚本把旧明文 → 加密
3. 之后所有写入自动加密
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, Text
from sqlalchemy.exc import DontWrapMixin
from sqlalchemy.types import TypeDecorator

from app.config import settings

logger = logging.getLogger(__name__)


def _resolve_key() -> bytes:
    """复用 GARMIN_ENCRYPTION_KEY, 没配走 SECRET_KEY 派生 (跟 device_credential 一致)."""
    key = getattr(settings, "device_encryption_key", None) or getattr(settings, "garmin_encryption_key", None)
    if key:
        return key.encode() if isinstance(key, str) else key
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_resolve_key())


class StrictEncryptionError(RuntimeError, DontWrapMixin):
    """Sanitized bind failure that SQLAlchemy must not wrap with parameters."""


class EncryptedString(TypeDecorator):
    """透明加解密 String 列. 旧明文行 (decrypt 失败) graceful fallback."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None or value == "":
            return value
        try:
            return _fernet.encrypt(value.encode()).decode()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[encrypted] encrypt 失败, 落回明文: {e}")
            return value

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None or value == "":
            return value
        try:
            return _fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            # 旧明文行 — 没加密过, 直接返回 (过渡期共存)
            return value
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[encrypted] decrypt 失败, 返回原值: {e}")
            return value


class StrictEncryptedString(EncryptedString):
    """Encrypted string that rejects writes when encryption is unavailable.

    This opt-in type is for new high-sensitivity columns where plaintext must
    never be a compatibility fallback.  Existing ``EncryptedString`` columns
    intentionally retain their legacy behavior.
    """

    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None or value == "":
            return value
        try:
            return _fernet.encrypt(value.encode()).decode()
        except Exception:  # noqa: BLE001
            logger.error("[strict-encrypted] encrypt 失败, 拒绝写入")
        # Raise after leaving the except block so the provider exception is not
        # retained as accessible context. DontWrapMixin prevents SQLAlchemy
        # StatementError from attaching all statement parameters, including the
        # sensitive plaintext value.
        raise StrictEncryptionError("sensitive value encryption failed") from None


class EncryptedText(EncryptedString):
    """透明加解密 Text 列 (大字段, 如全量基因型 JSON). 复用 EncryptedString 的 Fernet 逻辑.

    与 EncryptedString 的区别:
    1. 底层用 TEXT 而非 VARCHAR(N), 无长度上限.
    2. **encrypt 失败时 raise, 绝不落回明文** —— 用于最高隐私级数据(基因全量),
       加密失败必须让写入失败而非明文落库(安全评审 required; 不假装成功).
    读取仍 graceful fallback(旧明文行/解密异常返回原值, 不阻断读).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        try:
            return _fernet.encrypt(value.encode()).decode()
        except Exception as e:  # noqa: BLE001
            # 最高隐私级: 加密失败拒绝明文落库, fail-loud 让调用方感知
            logger.error(f"[encrypted-text] encrypt 失败, 拒绝明文落库: {e}")
            raise
