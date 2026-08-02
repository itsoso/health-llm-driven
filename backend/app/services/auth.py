"""用户认证服务"""
from datetime import UTC, datetime, timedelta
from typing import Optional
import jwt
import bcrypt
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from app.models.user import User, GarminCredential
from app.config import settings
from app.services.phone_auth import InvalidPhoneNumber, normalize_phone
import logging
import base64
import hashlib

logger = logging.getLogger(__name__)

# JWT配置
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365 * 2  # 2年

# Garmin密码加密密钥（必须独立配置，不从SECRET_KEY派生）
GARMIN_ENCRYPTION_KEY = settings.garmin_encryption_key
if not GARMIN_ENCRYPTION_KEY:
    raise ValueError(
        "GARMIN_ENCRYPTION_KEY must be set independently. "
        "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )

# 确保密钥是字节类型
if isinstance(GARMIN_ENCRYPTION_KEY, str):
    GARMIN_ENCRYPTION_KEY = GARMIN_ENCRYPTION_KEY.encode()

fernet = Fernet(GARMIN_ENCRYPTION_KEY)


class AuthService:
    """认证服务"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        try:
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"密码验证失败: {e}")
            return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        """获取密码哈希"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """创建JWT访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        """解码JWT令牌"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("[Auth] Token已过期")
            return None
        except jwt.PyJWTError as e:
            logger.warning(f"[Auth] JWT错误: {e}")
            return None
        except Exception as e:
            logger.warning(f"[Auth] Token解码异常: {e}")
            return None

    @staticmethod
    def authenticate_user(db: Session, username_or_email: str, password: str) -> Optional[User]:
        """验证用户登录"""
        identifier = (username_or_email or "").strip()
        # 尝试通过用户名查找
        user = db.query(User).filter(User.username == identifier).first()
        if not user:
            # 尝试通过邮箱查找
            user = db.query(User).filter(User.email == identifier).first()
        if not user:
            try:
                phone = normalize_phone(identifier)
            except InvalidPhoneNumber:
                phone = None
            if phone:
                user = db.query(User).filter(User.phone == phone).first()

        if not user:
            return None
        if not user.hashed_password:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def create_user(db: Session, username: str, email: str, password: str, name: str) -> User:
        """创建新用户"""
        hashed_password = AuthService.get_password_hash(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            name=name,
            is_active=True,
            birth_date=None,
            gender=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """通过ID获取用户"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """通过邮箱获取用户"""
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_user_by_phone(db: Session, phone: str) -> Optional[User]:
        """通过规范化手机号获取用户"""
        return db.query(User).filter(User.phone == phone).first()


class GarminCredentialService:
    """Garmin凭证管理服务"""

    @staticmethod
    def encrypt_secret(value: str) -> str:
        """使用 Garmin 专用密钥加密私密值。"""
        return fernet.encrypt(value.encode()).decode()

    @staticmethod
    def decrypt_secret(encrypted_value: str) -> str:
        """使用 Garmin 专用密钥解密私密值。"""
        return fernet.decrypt(encrypted_value.encode()).decode()

    @staticmethod
    def encrypt_password(password: str) -> str:
        """加密Garmin密码"""
        return GarminCredentialService.encrypt_secret(password)

    @staticmethod
    def decrypt_password(encrypted_password: str) -> str:
        """解密Garmin密码"""
        return GarminCredentialService.decrypt_secret(encrypted_password)

    @staticmethod
    def save_credentials(db: Session, user_id: int, garmin_email: str, garmin_password: str, is_cn: bool = False, requires_mfa: bool = False) -> GarminCredential:
        """保存或更新Garmin凭证"""
        encrypted_password = GarminCredentialService.encrypt_password(garmin_password)

        # 查找现有凭证
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()

        if credential:
            # 更新现有凭证
            credential.garmin_email = garmin_email
            credential.encrypted_password = encrypted_password
            credential.is_cn = is_cn
            credential.credentials_valid = True  # 重置凭证状态
            credential.requires_mfa = requires_mfa  # 更新MFA标志
            credential.error_count = 0
            credential.last_error = None
            credential.login_locked_until = None
            credential.garth_session = None
            credential.session_expires_at = None
            credential.updated_at = datetime.now(UTC)
        else:
            # 创建新凭证
            credential = GarminCredential(
                user_id=user_id,
                garmin_email=garmin_email,
                encrypted_password=encrypted_password,
                is_cn=is_cn,
                requires_mfa=requires_mfa
            )
            db.add(credential)

        db.commit()
        db.refresh(credential)
        from app.services.data_collection.garmin_mfa import invalidate_mfa_sessions_for_user

        invalidate_mfa_sessions_for_user(user_id)
        return credential

    @staticmethod
    def save_connected_credentials(
        db: Session,
        user_id: int,
        garmin_email: str,
        encrypted_password: str,
        is_cn: bool,
        native_token_store: str,
    ) -> GarminCredential:
        """Atomically install a fully authenticated Garmin connection."""
        credential = db.query(GarminCredential).filter(
            GarminCredential.user_id == user_id
        ).first()
        if credential is None:
            credential = GarminCredential(user_id=user_id)
            db.add(credential)

        credential.garmin_email = garmin_email
        credential.encrypted_password = encrypted_password
        credential.is_cn = is_cn
        credential.garth_session = native_token_store
        credential.session_expires_at = None
        credential.credentials_valid = True
        credential.requires_mfa = False
        credential.sync_enabled = True
        credential.error_count = 0
        credential.last_error = None
        credential.login_locked_until = None
        credential.updated_at = datetime.now(UTC)
        try:
            db.commit()
            db.refresh(credential)
        except Exception:
            db.rollback()
            raise

        from app.services.data_collection.garmin_mfa import invalidate_mfa_sessions_for_user

        invalidate_mfa_sessions_for_user(user_id)
        return credential

    @staticmethod
    def get_credentials(db: Session, user_id: int) -> Optional[GarminCredential]:
        """获取用户的Garmin凭证"""
        return db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()

    @staticmethod
    def get_decrypted_credentials(db: Session, user_id: int) -> Optional[dict]:
        """获取解密后的Garmin凭证"""
        credential = GarminCredentialService.get_credentials(db, user_id)
        if not credential:
            return None

        try:
            decrypted_password = GarminCredentialService.decrypt_password(credential.encrypted_password)
            return {
                "email": credential.garmin_email,
                "password": decrypted_password,
                "is_cn": getattr(credential, 'is_cn', False),
                "last_sync_at": credential.last_sync_at,
                "sync_enabled": credential.sync_enabled,
                "credentials_valid": getattr(credential, 'credentials_valid', True),
                "last_error": getattr(credential, 'last_error', None),
                "error_count": getattr(credential, 'error_count', 0),
            }
        except Exception as e:
            logger.error("解密Garmin密码失败 (%s): %r", type(e).__name__, e, exc_info=True)
            return None

    @staticmethod
    def update_mfa_status(db: Session, user_id: int, requires_mfa: bool) -> bool:
        """更新 MFA 状态"""
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if credential:
            credential.requires_mfa = requires_mfa
            db.commit()
            return True
        return False

    @staticmethod
    def delete_credentials(db: Session, user_id: int) -> bool:
        """删除Garmin凭证"""
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if credential:
            db.delete(credential)
            db.commit()
            from app.services.data_collection.garmin_mfa import invalidate_mfa_sessions_for_user

            invalidate_mfa_sessions_for_user(user_id)
            return True
        return False

    @staticmethod
    def update_sync_status(db: Session, user_id: int, last_sync_at: datetime = None) -> bool:
        """更新同步状态（同步成功时调用）"""
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if credential:
            credential.last_sync_at = last_sync_at or datetime.now(UTC)
            credential.credentials_valid = True  # 同步成功表示凭证有效
            credential.error_count = 0  # 重置错误计数
            credential.last_error = None
            db.commit()
            return True
        return False

    @staticmethod
    def update_sync_error(db: Session, user_id: int, error_message: str, is_auth_error: bool = False) -> bool:
        """更新同步错误状态"""
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if credential:
            credential.last_error = error_message
            credential.error_count = (credential.error_count or 0) + 1

            # 如果是认证错误（401），标记凭证为无效
            if is_auth_error:
                credential.credentials_valid = False
                logger.warning(f"用户 {user_id} 的Garmin凭证已失效: {error_message}")

            # 如果连续失败3次以上，也标记为无效
            if credential.error_count >= 3:
                credential.credentials_valid = False
                logger.warning(f"用户 {user_id} 连续同步失败 {credential.error_count} 次，已标记凭证无效")

            db.commit()
            return True
        return False

    @staticmethod
    def reset_credential_status(db: Session, user_id: int) -> bool:
        """重置凭证状态（用户重新保存凭证时调用）"""
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if credential:
            credential.credentials_valid = True
            credential.error_count = 0
            credential.last_error = None
            db.commit()
            return True
        return False

    @staticmethod
    def toggle_sync_enabled(db: Session, user_id: int, enabled: bool) -> bool:
        """切换同步开关状态"""
        credential = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if credential:
            credential.sync_enabled = enabled
            db.commit()
            logger.info(f"用户 {user_id} Garmin同步状态已{'启用' if enabled else '禁用'}")
            return True
        return False


# 创建服务实例
auth_service = AuthService()
garmin_credential_service = GarminCredentialService()
