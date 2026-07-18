"""Per-tenant, purpose-separated encryption for protected user content.

为什么 per-tenant 而非全局 Fernet:
- 隔离纵深: 即使密文跨租户错读 (RLS+WHERE 双层都漏), 用另一租户密钥也解不出。
- 密钥轮换预留: key_version 列为未来「单租户密钥轮换/失效」预留(当前轮换未实现)。
  注: 真删除靠 delete 端点硬清 ciphertext, 不依赖密钥销毁(故不自称 crypto-shred)。

派生: master key (复用 device/garmin key, 缺则 SECRET_KEY 派生) → HKDF-SHA256
派生 32 字节, info 同时绑定 purpose 与 user_id → urlsafe_b64encode → Fernet。
基因原始数据和短期 AIGC 草稿使用不同 purpose context，避免跨用途解密。

fail-loud: encrypt 失败 raise (绝不明文落库)。lru_cache 缓存 per user_id 避免每次 HKDF。
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

# HKDF salt: 从 master 派生的固定常量 (非密钥, 只需稳定且与其它派生用途区分)。
_SALT_INFO = b"genetic-raw-tenant-salt-v1"
_INFO_PREFIX = b"genetic-raw-v1:"
_AIGC_CONFIRMATION_SALT_INFO = b"aigc-media-confirmation-tenant-salt-v1"
_AIGC_CONFIRMATION_INFO_PREFIX = b"aigc-media-confirmation-v1:"


def _resolve_master_key() -> bytes:
    """复用 device/garmin key, 缺则 SECRET_KEY 派生 (与 _encrypted._resolve_key 一致)。"""
    key = getattr(settings, "device_encryption_key", None) or getattr(
        settings, "garmin_encryption_key", None
    )
    if key:
        return key.encode() if isinstance(key, str) else key
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _master_salt() -> bytes:
    """从 master 派生稳定 salt (确定性, 同 master 永远同 salt)。"""
    return hashlib.sha256(_resolve_master_key() + _SALT_INFO).digest()


def _context_salt(context_salt_info: bytes) -> bytes:
    """Derive a stable salt for one encrypted data purpose."""
    return hashlib.sha256(_resolve_master_key() + context_salt_info).digest()


@lru_cache(maxsize=2048)
def _derive_fernet(user_id: int) -> Fernet:
    """HKDF 从 master 派生 per-tenant 32 字节密钥 → Fernet。lru_cache 缓存。"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_master_salt(),
        info=_INFO_PREFIX + str(int(user_id)).encode(),
    )
    derived = hkdf.derive(_resolve_master_key())
    return Fernet(base64.urlsafe_b64encode(derived))


@lru_cache(maxsize=2048)
def _derive_aigc_confirmation_fernet(user_id: int) -> Fernet:
    """Separate per-user key context for short-lived AIGC prompts."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_context_salt(_AIGC_CONFIRMATION_SALT_INFO),
        info=_AIGC_CONFIRMATION_INFO_PREFIX + str(int(user_id)).encode(),
    )
    derived = hkdf.derive(_resolve_master_key())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_for(user_id: int, plaintext: str) -> str:
    """用 user_id 派生密钥加密。失败 raise (最高隐私级, 绝不明文落库)。"""
    return _derive_fernet(user_id).encrypt(plaintext.encode()).decode()


def decrypt_for(user_id: int, token: str) -> str:
    """用 user_id 派生密钥解密。token 非本租户密钥加密时抛 InvalidToken (fail-loud)。"""
    return _derive_fernet(user_id).decrypt(token.encode()).decode()


def encrypt_aigc_confirmation_for(user_id: int, plaintext: str) -> str:
    """Encrypt a short-lived AIGC draft in its own tenant/key-purpose context."""
    return _derive_aigc_confirmation_fernet(user_id).encrypt(plaintext.encode()).decode()


def decrypt_aigc_confirmation_for(user_id: int, token: str) -> str:
    """Decrypt a short-lived AIGC draft; cross-purpose ciphertext fails loudly."""
    return _derive_aigc_confirmation_fernet(user_id).decrypt(token.encode()).decode()
