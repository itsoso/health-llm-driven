"""Garmin Connect 数据收集服务 (使用社区库 garminconnect).

⚠️ 本文件 3294 行, 超过 500 行硬限. 已拆出:
- garmin_errors.py    : 自定义异常 + 锁定常量
- garmin_mfa.py       : MFA 会话 + display_name 兜底
- garmin_sso.py       : SSO 可用性探测

下一阶段拆分目标 (按风险升序):
- garmin_getters.py   : get_user_summary / get_sleep_data / get_heart_rates 等
                        ~360 行, 都是 self.client.* 的瘦封装, 改 mixin 即可
- garmin_parsers.py   : parse_to_garmin_data_create (1060 行 transform 逻辑,
                        只有 2 处 self.client 调用, 抽成 free function 可行)
- garmin_sync.py      : _sync_heart_rate_samples / _sync_spo2_samples / ...
                        700 行 sample 写入, 与 GarminConnectService 解耦后
                        各类 sample 写入可独立测试
"""
import asyncio
import json
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.schemas.daily_health import GarminDataCreate
import logging

logger = logging.getLogger(__name__)

try:
    from garminconnect import Garmin
    GARMINCONNECT_AVAILABLE = True
except ImportError:
    GARMINCONNECT_AVAILABLE = False
    logger.warning("garminconnect库未安装，请运行: pip install garminconnect")
except Exception as _garmin_load_err:  # noqa: BLE001
    # 第三方依赖加载异常不能拖垮整个后端启动。
    Garmin = None  # type: ignore
    GARMINCONNECT_AVAILABLE = False
    logger.warning(
        f"garminconnect 加载失败（将禁用 Garmin 同步）: {_garmin_load_err}"
    )


# 自定义异常 + 登录锁定配置已抽出到 garmin_errors.py.
# 这里 re-export 保持 backward compat (auth.py / heart_rate.py / scheduler.py 等都从本模块 import).
from app.services.data_collection.garmin_errors import (  # noqa: E402,F401
    GarminAuthenticationError,
    GarminLoginLockedError,
    GarminMFARequiredError,
    LOGIN_FAIL_THRESHOLD,
    LOGIN_LOCK_MINUTES_SCHEDULE,
)


# MFA 会话管理 + display_name 兜底获取已抽出到 garmin_mfa.py.
# SSO 探测器抽出到 garmin_sso.py.
# 这里 re-export 名字, 老调用方 (api/auth.py 等) 不破.
from app.services.data_collection.garmin_mfa import (  # noqa: E402,F401
    _mfa_sessions,
    _cleanup_expired_mfa_sessions,
    _generate_mfa_session_id,
    _ensure_display_name_for_client,
    verify_mfa_with_session,
)
from app.services.data_collection.garmin_sso import (  # noqa: E402,F401
    probe_sso_availability,
)


from app.services.data_collection.garmin_getters_mixin import GarminGettersMixin
from app.services.data_collection.garmin_native_auth import (
    GarminNativeTokenError,
    decode_native_token_store,
    dump_native_token_store,
    has_native_token_store,
    is_native_client_authenticated,
    safe_garmin_error_message,
)


class GarminConnectService(GarminGettersMixin):
    """
    Garmin Connect数据收集服务

    使用社区库 garminconnect (https://github.com/cyberjunky/python-garminconnect)
    这个库通过模拟浏览器登录Garmin Connect来获取数据，不需要官方API密钥

    安装: pip install garminconnect

    支持:
    - 国际版: connect.garmin.com (is_cn=False)
    - 中国版: connect.garmin.cn (is_cn=True)
    """

    def __init__(self, email: str, password: str, is_cn: bool = False, user_id: int = None, mfa_session_id: str = None):
        """
        初始化Garmin Connect服务

        Args:
            email: Garmin Connect账号邮箱
            password: Garmin Connect账号密码
            is_cn: 是否使用中国服务器 (garmin.cn)，默认False使用国际版
            user_id: 用户ID，用于日志记录
            mfa_session_id: MFA会话ID（如果已完成MFA验证，可以传入以复用认证状态）
        """
        if not GARMINCONNECT_AVAILABLE:
            raise ImportError(
                "garminconnect库未安装。请运行: pip install garminconnect\n"
                "GitHub: https://github.com/cyberjunky/python-garminconnect"
            )

        self.email = email
        self.password = password
        self.is_cn = is_cn
        self.user_id = user_id
        self.client: Optional[Garmin] = None
        self._authenticated = False
        self._mfa_client_state = None  # 用于存储 MFA 状态
        self._mfa_session_id = mfa_session_id  # 存储MFA会话ID

    def _log_prefix(self) -> str:
        """生成日志前缀，包含用户信息"""
        if self.user_id:
            return f"[用户 {self.user_id}]"
        # 隐藏邮箱中间部分
        email_parts = self.email.split('@')
        if len(email_parts) == 2 and len(email_parts[0]) > 3:
            masked_email = email_parts[0][:2] + '***' + '@' + email_parts[1]
        else:
            masked_email = '***'
        return f"[{masked_email}]"

    def _create_client(self, **kwargs) -> Garmin:
        """创建 ``garminconnect`` 0.3.x 原生客户端。"""
        return Garmin(self.email, self.password, is_cn=self.is_cn, **kwargs)

    def _save_session_to_db(self, db: Session) -> bool:
        """
        保存加密的原生 token store 到数据库，避免频繁登录

        Args:
            db: 数据库会话

        Returns:
            bool: 是否保存成功
        """
        if not self.user_id or not is_native_client_authenticated(self.client):
            return False

        prefix = self._log_prefix()

        try:
            from app.models.user import GarminCredential

            cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == self.user_id
            ).first()

            if cred:
                cred.garth_session = dump_native_token_store(self.client)
                cred.session_expires_at = None
                cred.requires_mfa = False
                cred.credentials_valid = True
                cred.error_count = 0
                cred.last_error = None
                db.commit()
                logger.info(f"{prefix} Garmin 原生 token 已加密缓存")
                return True

        except Exception as e:
            logger.warning(f"{prefix} 保存 Garmin token 失败 ({type(e).__name__})")
            db.rollback()

        return False

    def _load_session_from_db(self, db: Session) -> bool:
        """
        从数据库加载加密的原生 token store

        Args:
            db: 数据库会话

        Returns:
            bool: 是否加载成功且 session 有效
        """
        if not self.user_id:
            return False

        prefix = self._log_prefix()

        try:
            from app.models.user import GarminCredential

            cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == self.user_id
            ).first()

            if not cred or not cred.garth_session:
                logger.debug(f"{prefix} 数据库中无 Garmin token 缓存")
                return False
            try:
                token_payload = decode_native_token_store(cred.garth_session)
            except GarminNativeTokenError:
                logger.info(f"{prefix} 检测到旧版或无效 Garmin token，将重新认证")
                return False

            self.client = self._create_client(return_on_mfa=True)
            result = self.client.login(token_payload)
            if result and result[0] == "needs_mfa":
                session_id = self._store_mfa_session(result[1] if len(result) > 1 else None)
                cred.requires_mfa = True
                cred.last_error = "Garmin 需要两步验证，请完成验证码确认"
                db.commit()
                raise GarminMFARequiredError(
                    "Garmin 需要两步验证，请完成验证码确认",
                    {"session_id": session_id},
                )

            if not is_native_client_authenticated(self.client):
                logger.warning(f"{prefix} Garmin token 恢复后未认证")
                return False

            self._ensure_display_name()
            self._authenticated = True
            self._save_session_to_db(db)
            logger.info(f"{prefix} 已恢复 Garmin 原生 token")
            return True

        except GarminMFARequiredError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 加载 Garmin token 失败 ({type(e).__name__})")
            self._authenticated = False

        return False

    def _store_mfa_session(self, client_state: Any) -> str:
        """保存短时、用户绑定的原生 MFA 挑战。"""
        import time

        _cleanup_expired_mfa_sessions()
        session_id = _generate_mfa_session_id()
        _mfa_sessions[session_id] = {
            "client": self.client,
            "client_state": client_state,
            "email": self.email,
            "is_cn": self.is_cn,
            "user_id": self.user_id,
            "authenticated": False,
            "expires": time.time() + 300,
        }
        self._mfa_client_state = client_state
        return session_id

    def _clear_session_from_db(self, db: Session):
        """清除数据库中缓存的 session"""
        if not self.user_id:
            return

        try:
            from app.models.user import GarminCredential

            cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == self.user_id
            ).first()

            if cred:
                cred.garth_session = None
                cred.session_expires_at = None
                db.commit()
                logger.info(f"{self._log_prefix()} 已清除缓存的 Garmin token")
        except Exception as e:
            logger.warning(f"{self._log_prefix()} 清除 session 失败: {e}")

    def _check_login_lock(self, db: Session) -> Optional[datetime]:
        """
        检查是否被锁定，返回锁定截止时间（如果被锁定）

        Returns:
            Optional[datetime]: 锁定截止时间，如果未锁定返回 None
        """
        if not self.user_id or not db:
            return None

        try:
            from app.models.user import GarminCredential

            cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == self.user_id
            ).first()

            if cred and cred.login_locked_until:
                now = datetime.now(UTC)
                locked_until = cred.login_locked_until
                # 统一为 naive datetime 比较，避免 offset-naive vs offset-aware 错误
                if locked_until.tzinfo is not None:
                    locked_until = locked_until.replace(tzinfo=None)
                if locked_until > now:
                    return cred.login_locked_until
                else:
                    # 锁定已过期，清除锁定状态（但保留 error_count 用于指数退避计算）
                    cred.login_locked_until = None
                    db.commit()
        except Exception as e:
            logger.warning(f"{self._log_prefix()} 检查登录锁定失败: {e}")

        return None

    def _record_login_failure(self, db: Session, error_msg: str):
        """
        记录登录失败，累加失败计数，超过阈值则锁定

        Args:
            db: 数据库会话
            error_msg: 错误信息
        """
        if not self.user_id or not db:
            return

        prefix = self._log_prefix()

        try:
            from app.models.user import GarminCredential

            cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == self.user_id
            ).first()

            if cred:
                cred.last_error = error_msg[:500] if error_msg else None

                # 有可解密的原生 token 时不因 SSO 错误锁定。
                has_valid_session = has_native_token_store(cred.garth_session)

                is_rate_limited = (
                    '429' in (error_msg or '')
                    or 'too many requests' in (error_msg or '').lower()
                    or '尝试过多' in (error_msg or '')
                )
                is_cloudflare = 'cloudflare' in (error_msg or '').lower() or 'challenge' in (error_msg or '').lower()

                if is_rate_limited or is_cloudflare:
                    if has_valid_session:
                        # 有 session 时不锁定，下次同步会直接用 session
                        logger.info(f"{prefix} Cloudflare/429 但有有效 session，不设锁定")
                    else:
                        lock_minutes = 30
                        lock_until = datetime.now(UTC) + timedelta(minutes=lock_minutes)
                        cred.login_locked_until = lock_until
                        logger.warning(
                            f"{prefix} ⚠️ Cloudflare/429 限流且无 session，锁定 {lock_minutes} 分钟"
                        )
                else:
                    # 真正的登录失败（密码错、账号问题等）
                    cred.error_count = (cred.error_count or 0) + 1
                    cred.credentials_valid = False
                    if cred.error_count >= LOGIN_FAIL_THRESHOLD:
                        lock_index = min(cred.error_count - 1, len(LOGIN_LOCK_MINUTES_SCHEDULE) - 1)
                        lock_minutes = LOGIN_LOCK_MINUTES_SCHEDULE[lock_index]
                        lock_until = datetime.now(UTC) + timedelta(minutes=lock_minutes)
                        cred.login_locked_until = lock_until
                        logger.warning(
                            f"{prefix} ⚠️ 登录失败，累计 {cred.error_count} 次，锁定 {lock_minutes} 分钟"
                        )
                    else:
                        logger.info(f"{prefix} 登录失败，当前失败次数: {cred.error_count}/{LOGIN_FAIL_THRESHOLD}")

                db.commit()
        except Exception as e:
            logger.warning(f"{prefix} 记录登录失败状态时出错: {e}")
            db.rollback()

    def _reset_login_failure(self, db: Session):
        """
        登录成功时重置失败计数

        Args:
            db: 数据库会话
        """
        if not self.user_id or not db:
            return

        try:
            from app.models.user import GarminCredential

            cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == self.user_id
            ).first()

            if cred and (cred.error_count > 0 or cred.login_locked_until):
                cred.error_count = 0
                cred.login_locked_until = None
                cred.credentials_valid = True
                cred.last_error = None
                db.commit()
                logger.info(f"{self._log_prefix()} ✅ 登录成功，已重置失败计数")
        except Exception as e:
            logger.warning(f"{self._log_prefix()} 重置登录失败状态时出错: {e}")

    def _ensure_display_name(self) -> bool:
        """确保资料字段可供 Garmin getter 使用，不记录身份信息。"""
        if not self.client:
            return False
        if self.client.display_name:
            return True

        native = getattr(self.client, "client", None)
        if native:
            for path in (
                "/userprofile-service/userprofile/profile",
                "/userprofile-service/socialProfile",
            ):
                try:
                    profile = native.connectapi(path)
                    if isinstance(profile, dict):
                        self.client.display_name = profile.get("displayName") or profile.get("userName")
                        self.client.full_name = profile.get("fullName")
                        if self.client.display_name:
                            return True
                except Exception:
                    logger.debug(
                        "%s Garmin profile lookup failed (%s)",
                        self._log_prefix(),
                        path,
                    )

        full_name = getattr(self.client, "full_name", None)
        if full_name:
            self.client.display_name = full_name
            return True

        email_username = self.email.split("@", 1)[0]
        if email_username:
            self.client.display_name = email_username
            logger.warning(f"{self._log_prefix()} Garmin profile 缺失，使用账号标识兜底")
            return True

        logger.error(f"{self._log_prefix()} 无法初始化 Garmin profile")
        return False

    def _ensure_authenticated(self, db: Session = None):
        """
        确保已认证，认证失败时抛出异常

        优先尝试以下方式（按顺序）：
        0. 检查是否被锁定（防止频繁登录导致 Garmin 账号被封）
        1. 从数据库加载缓存的 OAuth Token（避免频繁登录导致账号锁定）
        2. 从 MFA 会话复用已认证的 client
        3. 重新登录并缓存 Token

        Args:
            db: 数据库会话（可选，用于 token 缓存）
        """
        prefix = self._log_prefix()

        if self._authenticated and is_native_client_authenticated(self.client):
            return

        # 1. 优先尝试从数据库加载原生 token（即使被锁定也能用 token）
        if db and self.user_id:
            if self._load_session_from_db(db):
                logger.info(f"{prefix} 使用缓存的 Garmin token")
                return

        # 0. 检查是否被锁定（仅在没有缓存 session、需要 SSO 登录时才阻止）
        if db and self.user_id:
            locked_until = self._check_login_lock(db)
            if locked_until:
                locked_naive = locked_until.replace(tzinfo=None) if locked_until.tzinfo else locked_until
                remaining_minutes = int((locked_naive - datetime.now(UTC)).total_seconds() / 60) + 1
                error_msg = f"⏳ 登录已被暂停，请 {remaining_minutes} 分钟后再试。连续登录失败会导致 Garmin 账号被锁定，请先确认密码正确。"
                logger.warning(f"{prefix} {error_msg}")
                raise GarminLoginLockedError(error_msg, locked_until)

        # 2. 如果有MFA会话ID，尝试复用已认证的client
        if self._mfa_session_id and not self._authenticated:
            _cleanup_expired_mfa_sessions()
            logger.info(f"{prefix} 尝试复用MFA会话: {self._mfa_session_id}")
            if self._mfa_session_id in _mfa_sessions:
                session = _mfa_sessions[self._mfa_session_id]
                from app.utils.redact import mask_email
                logger.info(f"{prefix} 找到MFA会话: authenticated={session.get('authenticated')}, email={mask_email(session.get('email'))}, 当前email={mask_email(self.email)}")
                if session.get("authenticated") and session.get("email") == self.email:
                    # 复用已认证的原生 client
                    self.client = session.get("client")
                    if (
                        session.get("user_id") == self.user_id
                        and is_native_client_authenticated(self.client)
                    ):
                        self._ensure_display_name()
                        self._authenticated = True
                        logger.info(f"{prefix} 已复用认证后的 Garmin MFA 会话")
                        if db:
                            self._save_session_to_db(db)
                        return
                    else:
                        logger.warning(f"{prefix} Garmin MFA 会话无效或所有者不匹配")
                else:
                    logger.warning(f"{prefix} Garmin MFA 会话未认证或账号不匹配")
            else:
                logger.warning(f"{prefix} Garmin MFA 会话不存在或已过期")

        # 3. 重新登录
        if not self._authenticated or self.client is None:
            try:
                self.client = self._create_client(return_on_mfa=True)

                result = self.client.login()

                if result and result[0] == "needs_mfa":
                    client_state = result[1] if len(result) > 1 else None
                    session_id = self._store_mfa_session(client_state)
                    if db and self.user_id:
                        from app.models.user import GarminCredential

                        cred = db.query(GarminCredential).filter(
                            GarminCredential.user_id == self.user_id
                        ).first()
                        if cred:
                            cred.requires_mfa = True
                            cred.last_error = "Garmin 需要两步验证，请完成验证码确认"
                            db.commit()
                    logger.warning(f"{prefix} Garmin 需要两步验证")
                    raise GarminMFARequiredError(
                        "Garmin 需要两步验证，请完成验证码确认",
                        {"session_id": session_id},
                    )

                if not is_native_client_authenticated(self.client):
                    raise GarminAuthenticationError("Garmin 认证未完成，请重新连接")

                self._ensure_display_name()
                self._authenticated = True
                logger.info(f"{prefix} Garmin Connect 登录成功")
                if db:
                    self._save_session_to_db(db)
                    self._reset_login_failure(db)
                return

            except GarminMFARequiredError:
                # MFA错误直接抛出（不计入失败次数）
                raise
            except GarminLoginLockedError:
                # 锁定错误直接抛出
                raise
            except Exception as e:
                self._authenticated = False
                error_msg = str(e).lower()

                # 检查是否需要设置密码（不计入失败次数）
                if 'set password' in error_msg or 'unexpected title' in error_msg:
                    logger.warning(f"{prefix} Garmin账号需要设置密码")
                    raise GarminAuthenticationError(
                        "Garmin账号需要设置密码！请先访问 https://connect.garmin.com 登录并按提示完成密码设置，然后再尝试同步。"
                    ) from e

                # 检查是否需要MFA（不计入失败次数）
                if 'mfa' in error_msg or 'two-factor' in error_msg or 'verification' in error_msg:
                    logger.warning(f"{prefix} Garmin账号需要两步验证")
                    raise GarminMFARequiredError(
                        "🔐 Garmin账号需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。",
                        {}
                    ) from e

                # 登录失败 - 记录失败次数
                safe_message = safe_garmin_error_message(e)
                if db:
                    self._record_login_failure(db, safe_message)

                # 将登录失败转换为明确的认证错误
                if any(kw in error_msg for kw in ['login', 'auth', '401', 'unauthorized', 'credential', 'password', 'oauth', 'ticket']):
                    logger.warning(f"{prefix} Garmin 登录失败 ({type(e).__name__})")
                    raise GarminAuthenticationError(safe_message) from e
                logger.warning(f"{prefix} Garmin 连接失败 ({type(e).__name__})")
                raise GarminAuthenticationError(safe_message) from e

    def test_connection_with_mfa(self, db: Session = None) -> Dict[str, Any]:
        """测试连接，只向调用方返回应用生成的 MFA session id。"""
        prefix = self._log_prefix()

        if self._mfa_session_id:
            _cleanup_expired_mfa_sessions()
            session = _mfa_sessions.get(self._mfa_session_id)
            if (
                session
                and session.get("authenticated")
                and session.get("email") == self.email
                and session.get("user_id") == self.user_id
                and is_native_client_authenticated(session.get("client"))
            ):
                self.client = session["client"]
                self._authenticated = True
                if db:
                    self._save_session_to_db(db)
                return {
                    "success": True,
                    "mfa_required": False,
                    "message": "Garmin 已连接",
                }

        try:
            self.client = self._create_client(return_on_mfa=True)
            result = self.client.login()
            if result and result[0] == "needs_mfa":
                client_state = result[1] if len(result) > 1 else None
                session_id = self._store_mfa_session(client_state)
                if db and self.user_id:
                    from app.services.auth import garmin_credential_service

                    garmin_credential_service.update_mfa_status(db, self.user_id, True)
                return {
                    "success": False,
                    "mfa_required": True,
                    "mfa_session_id": session_id,
                    "message": "Garmin 需要两步验证，请输入验证码",
                }

            if not is_native_client_authenticated(self.client):
                raise GarminAuthenticationError("Garmin 认证未完成，请重新连接")

            self._ensure_display_name()
            self._authenticated = True
            if db:
                self._save_session_to_db(db)
                self._reset_login_failure(db)
            logger.info(f"{prefix} Garmin 连接测试成功")
            return {
                "success": True,
                "mfa_required": False,
                "message": "Garmin 账号连接成功",
            }

        except Exception as e:
            logger.warning(f"{prefix} Garmin 连接测试失败 ({type(e).__name__})")
            return {
                "success": False,
                "mfa_required": False,
                "message": safe_garmin_error_message(e),
            }

    def resume_login_with_mfa(self, client_state: Dict[str, Any], mfa_code: str) -> Dict[str, Any]:
        """
        使用 MFA 验证码恢复登录

        Args:
            client_state: test_connection_with_mfa 返回的客户端状态
            mfa_code: 用户输入的 MFA 验证码

        Returns:
            dict: {
                "success": bool,
                "message": str
            }
        """
        prefix = self._log_prefix()
        try:
            if self.client is None:
                self.client = self._create_client()

            # 使用验证码恢复登录
            self.client.resume_login(client_state, mfa_code)
            self._authenticated = is_native_client_authenticated(self.client)
            if not self._authenticated:
                raise GarminAuthenticationError("Garmin MFA 认证未完成")

            logger.info(f"{prefix} Garmin MFA 验证成功")

            return {
                "success": True,
                "message": "✅ 验证成功！Garmin账号连接成功，可以保存凭证了。"
            }

        except Exception as e:
            error_msg = str(e).lower()

            if 'invalid' in error_msg or 'incorrect' in error_msg or 'wrong' in error_msg:
                return {
                    "success": False,
                    "message": "❌ 验证码错误！请检查并重新输入。"
                }

            logger.warning(f"{prefix} Garmin MFA 验证失败 ({type(e).__name__})")
            return {
                "success": False,
                "message": "Garmin 验证失败，请重新获取验证码",
            }


    def parse_to_garmin_data_create(
        self,
        raw_data: Dict[str, Any],
        user_id: int,
        record_date: date
    ) -> GarminDataCreate:
        """
        将Garmin Connect返回的原始数据解析为GarminDataCreate

        Args:
            raw_data: Garmin Connect返回的原始数据（可能包含summary、sleep、heart_rate等）
            user_id: 用户ID
            record_date: 记录日期

        Returns:
            GarminDataCreate对象
        """
        # 调试：打印原始数据结构（仅前1000字符）
        import json
        raw_data_str = json.dumps(raw_data, indent=2, default=str)[:2000]
        logger.debug(f"解析Garmin数据，原始数据结构（前2000字符）:\n{raw_data_str}")

        # 从get_user_summary获取的数据在根级别
        # 注意：raw_data包含sleep、body_battery等，但summary数据可能为空
        # 需要单独提取summary部分，而不是整个raw_data
        summary = {}
        if isinstance(raw_data, dict):
            # 排除sleep、body_battery、heart_rate、stress等独立API的数据
            # 只保留来自get_user_summary的字段
            exclude_keys = {'sleep', 'body_battery', 'heart_rate', 'stress'}
            summary = {k: v for k, v in raw_data.items() if k not in exclude_keys}
            logger.debug(f"提取summary数据，排除独立API数据后的键: {list(summary.keys())[:20]}")

        # 处理睡眠数据（可能来自get_sleep_data或summary）
        sleep_data_raw = raw_data.get('sleep') if isinstance(raw_data, dict) else None

        # 如果sleep_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(sleep_data_raw, list) and sleep_data_raw:
            sleep_data = sleep_data_raw[0] if isinstance(sleep_data_raw[0], dict) else {}
        elif isinstance(sleep_data_raw, dict):
            sleep_data = sleep_data_raw
        else:
            sleep_data = {}

        # 辅助函数：安全获取嵌套字典值（支持多层嵌套）
        def safe_get_nested(data, *keys, default=None):
            """安全获取多层嵌套字典值"""
            if not isinstance(data, dict):
                return default
            for key in keys:
                if not isinstance(data, dict):
                    return default
                data = data.get(key)
                if data is None:
                    return default
            return data if data is not None else default

        # 尝试多种方式获取睡眠分数
        sleep_score = None
        sleep_duration_seconds = 0
        deep_sleep_seconds = 0
        rem_sleep_seconds = 0
        light_sleep_seconds = 0
        awake_seconds = 0
        nap_seconds = 0
        avg_heart_rate_during_sleep = None
        hrv = None  # HRV数据，优先从睡眠数据获取
        sleep_start_time = None  # 睡眠开始时间
        sleep_end_time = None    # 睡眠结束时间

        if isinstance(sleep_data, dict) and sleep_data:
            # Garmin睡眠数据结构:
            # sleep_data = {
            #   'dailySleepDTO': {
            #     'sleepTimeSeconds': 29280,
            #     'sleepScores': {'overall': {'value': 87}},
            #     'deepSleepSeconds': 3720,
            #     ...
            #   },
            #   'restingHeartRate': 51,
            #   ...
            # }

            # 打印睡眠数据的顶层键
            logger.info(f"睡眠数据顶层键: {list(sleep_data.keys())}")

            # 获取 dailySleepDTO
            daily_sleep_dto = sleep_data.get('dailySleepDTO', {})
            if not isinstance(daily_sleep_dto, dict):
                daily_sleep_dto = {}

            # 打印 dailySleepDTO 的键和睡眠分数相关字段
            if daily_sleep_dto:
                logger.info(f"dailySleepDTO 键: {list(daily_sleep_dto.keys())}")
                sleep_scores = daily_sleep_dto.get('sleepScores')
                if sleep_scores:
                    logger.info(f"sleepScores 内容: {sleep_scores}")
            else:
                logger.info("dailySleepDTO 为空")

            # 获取睡眠分数 - 正确的路径是 dailySleepDTO.sleepScores.overall.value
            sleep_score = (
                safe_get_nested(daily_sleep_dto, 'sleepScores', 'overall', 'value') or
                safe_get_nested(sleep_data, 'sleepScores', 'overall', 'value') or
                daily_sleep_dto.get('sleepScore') or
                sleep_data.get('sleepScore') or
                safe_get_nested(daily_sleep_dto, 'sleepScores', 'overall') or
                sleep_data.get('overallSleepScore')
            )

            # 如果sleep_score是字典（如 {'value': 87, 'qualifierKey': 'GOOD'}），提取value
            if isinstance(sleep_score, dict):
                sleep_score = sleep_score.get('value')

            logger.debug(f"提取的睡眠分数: {sleep_score}")

            # 睡眠时长（秒）- 从 dailySleepDTO 获取
            sleep_duration_seconds = (
                daily_sleep_dto.get('sleepTimeSeconds') or
                sleep_data.get('sleepTimeSeconds') or
                0
            )

            # 睡眠阶段数据 - 从 dailySleepDTO 获取
            deep_sleep_seconds = daily_sleep_dto.get('deepSleepSeconds', 0) or 0
            rem_sleep_seconds = daily_sleep_dto.get('remSleepSeconds', 0) or 0
            light_sleep_seconds = daily_sleep_dto.get('lightSleepSeconds', 0) or 0
            awake_seconds = daily_sleep_dto.get('awakeSleepSeconds', 0) or 0

            # 小睡时长（秒）- 从 dailySleepDTO 获取
            nap_seconds = daily_sleep_dto.get('napTimeSeconds', 0) or 0

            # 睡眠期间平均心率
            avg_heart_rate_during_sleep = (
                daily_sleep_dto.get('avgHeartRate') or
                sleep_data.get('restingHeartRate')
            )

            # HRV数据 - 从睡眠数据中获取
            # avgOvernightHrv 是夜间平均HRV值
            if hrv is None:
                hrv = sleep_data.get('avgOvernightHrv')

            # 睡眠开始和结束时间（从GMT时间戳转换为北京时间）
            # 优先使用GMT时间戳，然后转换为北京时间（UTC+8）
            sleep_start_ts = daily_sleep_dto.get('sleepStartTimestampGMT') or daily_sleep_dto.get('sleepStartTimestampLocal')
            sleep_end_ts = daily_sleep_dto.get('sleepEndTimestampGMT') or daily_sleep_dto.get('sleepEndTimestampLocal')

            # 将毫秒时间戳转换为北京时间
            from datetime import datetime as dt, time as dt_time, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))  # 北京时间 UTC+8

            if sleep_start_ts:
                try:
                    # 从GMT时间戳转换为UTC时间，再转为北京时间
                    sleep_start_utc = dt.fromtimestamp(sleep_start_ts / 1000, tz=timezone.utc)
                    sleep_start_beijing = sleep_start_utc.astimezone(beijing_tz)
                    sleep_start_time = sleep_start_beijing.time()
                except Exception as e:
                    logger.warning(f"解析睡眠开始时间失败: {e}")
            if sleep_end_ts:
                try:
                    # 从GMT时间戳转换为UTC时间，再转为北京时间
                    sleep_end_utc = dt.fromtimestamp(sleep_end_ts / 1000, tz=timezone.utc)
                    sleep_end_beijing = sleep_end_utc.astimezone(beijing_tz)
                    sleep_end_time = sleep_end_beijing.time()
                except Exception as e:
                    logger.warning(f"解析睡眠结束时间失败: {e}")

            logger.info(f"解析睡眠数据: 分数={sleep_score}, 时长秒={sleep_duration_seconds}, 深睡={deep_sleep_seconds}, REM={rem_sleep_seconds}, HRV={hrv}, 开始时间={sleep_start_time}, 结束时间={sleep_end_time}")
        else:
            logger.warning(f"睡眠数据为空或格式不正确: type={type(sleep_data)}, 值={sleep_data}")

        # 如果从sleep_data没有获取到，尝试从summary获取
        if isinstance(summary, dict):
            if sleep_score is None:
                score_val = (
                    summary.get('sleepScore') or
                    safe_get_nested(summary, 'sleepScores', 'overall', 'value') or
                    safe_get_nested(summary, 'sleepScores', 'overall') or
                    summary.get('overallSleepScore') or
                    summary.get('sleepQualityScore')
                )
                # 如果是字典，提取value
                if isinstance(score_val, dict):
                    sleep_score = score_val.get('value')
                else:
                    sleep_score = score_val
            if sleep_duration_seconds == 0:
                sleep_millis = summary.get('sleepTimeMillis')
                sleep_duration_seconds = (
                    summary.get('sleepTimeSeconds') or
                    summary.get('sleepDurationSeconds') or
                    summary.get('sleepingSeconds') or
                    (sleep_millis / 1000 if sleep_millis else 0) or
                    summary.get('totalSleepTimeSeconds') or
                    0
                )
            if deep_sleep_seconds == 0:
                deep_sleep_seconds = summary.get('deepSleepSeconds', 0) or summary.get('deepSleepSecondsOvernight', 0) or 0
            if rem_sleep_seconds == 0:
                rem_sleep_seconds = summary.get('remSleepSeconds', 0) or summary.get('remSleepSecondsOvernight', 0) or 0
            if light_sleep_seconds == 0:
                light_sleep_seconds = summary.get('lightSleepSeconds', 0) or summary.get('lightSleepSecondsOvernight', 0) or 0
            if awake_seconds == 0:
                awake_seconds = summary.get('awakeSleepSeconds', 0) or summary.get('awakeSleepSecondsOvernight', 0) or 0

        # 处理心率数据（可能来自get_heart_rates或summary）
        hr_data_raw = None
        if isinstance(raw_data, dict):
            hr_data_raw = raw_data.get('heart_rate') or raw_data.get('heartRates')

        # 如果hr_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(hr_data_raw, list) and hr_data_raw:
            hr_data = hr_data_raw[0] if isinstance(hr_data_raw[0], dict) else {}
        elif isinstance(hr_data_raw, dict):
            hr_data = hr_data_raw
        else:
            hr_data = {}

        avg_hr = None
        resting_hr = None
        max_hr = None
        min_hr = None

        if isinstance(hr_data, dict) and hr_data:
            # 从独立的heart_rate数据中提取
            hr_values = hr_data.get('heartRateValues')
            first_hr_value = None
            if isinstance(hr_values, list) and hr_values and isinstance(hr_values[0], dict):
                first_hr_value = hr_values[0].get('value')

            avg_hr = (
                hr_data.get('averageHeartRate') or
                hr_data.get('avg') or
                hr_data.get('avgHeartRate') or
                hr_data.get('average') or
                first_hr_value
            )
            resting_hr = (
                hr_data.get('restingHeartRate') or
                hr_data.get('resting') or
                hr_data.get('restingHeartRateValue')
            )
            max_hr = hr_data.get('maxHeartRate') or hr_data.get('max')
            min_hr = hr_data.get('minHeartRate') or hr_data.get('min')

        # 如果从hr_data没有获取到，尝试从summary获取
        if isinstance(summary, dict):
            if avg_hr is None:
                avg_hr = (
                    summary.get('averageHeartRate') or
                    summary.get('avgHeartRate') or
                    summary.get('avg') or
                    summary.get('average') or
                    summary.get('heartRateAverage')
                )
            if resting_hr is None:
                resting_hr = (
                    summary.get('restingHeartRate') or
                    summary.get('resting') or
                    summary.get('restingHeartRateValue')
                )
            if max_hr is None:
                max_hr = summary.get('maxHeartRate') or summary.get('max')
            if min_hr is None:
                min_hr = summary.get('minHeartRate') or summary.get('min')

        # 如果还没有获取到静息心率，尝试从睡眠数据获取
        if resting_hr is None and isinstance(sleep_data, dict):
            resting_hr = sleep_data.get('restingHeartRate')
            if resting_hr:
                logger.info(f"从睡眠数据获取静息心率: {resting_hr}")

        # 如果还没有获取到平均心率，尝试从睡眠数据获取
        if avg_hr is None and isinstance(sleep_data, dict):
            daily_sleep_dto = sleep_data.get('dailySleepDTO', {})
            if isinstance(daily_sleep_dto, dict):
                avg_hr = daily_sleep_dto.get('avgHeartRate')
                if avg_hr:
                    logger.info(f"从睡眠数据获取平均心率: {avg_hr}")

        # HRV数据 - 如果从睡眠数据没有获取到，尝试从summary获取
        if hrv is None and isinstance(summary, dict):
            hrv = summary.get('hrv') or safe_get_nested(summary, 'hrvStatus', 'hrv') or summary.get('avgOvernightHrv')

        # HRV数据 - 最后兜底：从 HRV 专用 API 获取
        if hrv is None:
            try:
                hrv_date = record_date.isoformat() if hasattr(record_date, 'isoformat') else str(record_date)
                hrv_resp = self.client.connectapi(f"/hrv-service/hrv/{hrv_date}")
                if hrv_resp and isinstance(hrv_resp, dict):
                    hrv_summary = hrv_resp.get("hrvSummary", {})
                    hrv = hrv_summary.get("lastNightAvg") or hrv_summary.get("weeklyAvg")
                    hrv_status_val = hrv_summary.get("status")
                    if hrv:
                        logger.info(f"从 HRV API 获取: hrv={hrv}, status={hrv_status_val}")
            except Exception as e:
                logger.debug(f"HRV API 调用失败(非致命): {e}")

        logger.debug(f"最终HRV值: {hrv}")

        # 身体电量数据（可能来自get_body_battery或summary）
        battery_data_raw = None
        if isinstance(raw_data, dict):
            battery_data_raw = raw_data.get('body_battery') or raw_data.get('bodyBattery')

        logger.info(f"身体电量原始数据类型: {type(battery_data_raw)}")
        if battery_data_raw:
            if isinstance(battery_data_raw, list):
                logger.info(f"身体电量原始数据(列表)长度: {len(battery_data_raw)}")
                if battery_data_raw:
                    sample = battery_data_raw[0] if len(battery_data_raw) > 0 else None
                    logger.info(f"身体电量第一个元素: {sample}")
            elif isinstance(battery_data_raw, dict):
                logger.info(f"身体电量原始数据(字典)键: {list(battery_data_raw.keys())}")

        # 如果battery_data是列表，可能需要从中提取统计值
        battery_data = {}
        charged = None
        drained = None
        most_charged = None
        lowest = None
        current_battery = None  # 当前实时电量

        if isinstance(battery_data_raw, list) and battery_data_raw:
            # Garmin返回的是一个时间序列列表，每个元素包含 bodyBatteryLevel 等
            # 需要遍历找到 charged/drained 或计算 most_charged/lowest
            # 重要：过滤掉不属于目标日期的数据点
            battery_levels = []
            battery_with_timestamps = []  # 记录电量和时间戳用于调试

            # 计算目标日期的时间范围（使用本地时区）
            target_date_start = datetime.combine(record_date, datetime.min.time())
            target_date_end = datetime.combine(record_date + timedelta(days=1), datetime.min.time())

            for item in battery_data_raw:
                if isinstance(item, dict):
                    level = item.get('bodyBatteryLevel') or item.get('level') or item.get('value')
                    if level is not None:
                        # 获取时间戳并过滤
                        timestamp = item.get('startTimestampGMT') or item.get('timestampGMT') or item.get('timestamp')

                        # 检查时间戳是否属于目标日期
                        is_valid_date = True
                        if timestamp:
                            try:
                                if isinstance(timestamp, (int, float)):
                                    # 毫秒时间戳
                                    if timestamp > 1000000000000:
                                        ts_datetime = datetime.fromtimestamp(timestamp / 1000)
                                    else:
                                        ts_datetime = datetime.fromtimestamp(timestamp)
                                    is_valid_date = target_date_start <= ts_datetime < target_date_end
                            except Exception:
                                pass  # 如果解析失败，保留数据点

                        if is_valid_date:
                            battery_levels.append(level)
                            battery_with_timestamps.append((level, timestamp))
                    # 有些格式直接包含统计数据
                    if item.get('charged') is not None:
                        charged = item.get('charged')
                    if item.get('drained') is not None:
                        drained = item.get('drained')

            # 记录过滤情况
            original_count = len(battery_data_raw)
            filtered_count = len(battery_levels)
            if original_count != filtered_count:
                logger.info(f"电量数据过滤: 原始{original_count}条 -> 目标日期({record_date}){filtered_count}条")

            if battery_levels:
                most_charged = max(battery_levels)
                lowest = min(battery_levels)
                current_battery = battery_levels[-1]  # 最后一个值是当前电量
                # 估算充电和消耗（简化计算）
                if charged is None and len(battery_levels) >= 2:
                    # 计算总充电量（上升的部分之和）
                    total_charged = 0
                    total_drained = 0
                    for i in range(1, len(battery_levels)):
                        diff = battery_levels[i] - battery_levels[i-1]
                        if diff > 0:
                            total_charged += diff
                        else:
                            total_drained += abs(diff)
                    charged = total_charged if total_charged > 0 else None
                    drained = total_drained if total_drained > 0 else None

            # 调试：打印时间范围和最高值的时间点
            if battery_with_timestamps:
                first_ts = battery_with_timestamps[0][1]
                last_ts = battery_with_timestamps[-1][1]
                max_entry = max(battery_with_timestamps, key=lambda x: x[0] if x[0] else 0)
                min_entry = min(battery_with_timestamps, key=lambda x: x[0] if x[0] else 999)

                # 转换时间戳为可读格式
                def ts_to_str(ts):
                    if ts:
                        try:
                            if isinstance(ts, (int, float)) and ts > 1000000000000:
                                return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                            elif isinstance(ts, (int, float)):
                                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                            return str(ts)
                        except Exception:
                            return str(ts)
                    return 'N/A'

                logger.info(f"电量列表时间范围: {ts_to_str(first_ts)} - {ts_to_str(last_ts)}, "
                           f"最高值={max_entry[0]}@{ts_to_str(max_entry[1])}, "
                           f"最低值={min_entry[0]}@{ts_to_str(min_entry[1])}")

            logger.info(f"从列表计算: most_charged={most_charged}, lowest={lowest}, current={current_battery}, charged={charged}, drained={drained}")

        elif isinstance(battery_data_raw, dict):
            battery_data = battery_data_raw
            charged = battery_data.get('charged') or battery_data.get('bodyBatteryCharged') or battery_data.get('chargedValue')
            drained = battery_data.get('drained') or battery_data.get('bodyBatteryDrained') or battery_data.get('drainedValue')
            # 优先使用最高值字段，而不是最近值
            most_charged = battery_data.get('bodyBatteryHighestValue') or battery_data.get('mostCharged') or battery_data.get('bodyBatteryMostCharged') or battery_data.get('mostChargedValue')
            lowest = battery_data.get('lowest') or battery_data.get('bodyBatteryLowest') or battery_data.get('lowestValue')
            # 当前实时电量
            current_battery = battery_data.get('bodyBatteryMostRecentValue') or battery_data.get('currentValue') or battery_data.get('current')

        # 从 summary 获取补充数据
        if isinstance(summary, dict):
            # 充电/消耗量
            charged = charged or summary.get('bodyBatteryChargedValue') or summary.get('bodyBatteryCharged')
            drained = drained or summary.get('bodyBatteryDrainedValue') or summary.get('bodyBatteryDrained')

            # 最高值：使用所有来源中的最大值（修复：之前只在most_charged为None时才从summary获取）
            summary_highest = summary.get('bodyBatteryHighestValue') or summary.get('bodyBatteryMostCharged')
            if summary_highest is not None:
                if most_charged is None:
                    most_charged = summary_highest
                else:
                    most_charged = max(most_charged, summary_highest)
                logger.debug(f"从summary获取bodyBatteryHighestValue: {summary_highest}, 更新后most_charged: {most_charged}")

            # 最低值
            summary_lowest = summary.get('bodyBatteryLowestValue') or summary.get('bodyBatteryLowest')
            if summary_lowest is not None:
                if lowest is None:
                    lowest = summary_lowest
                else:
                    lowest = min(lowest, summary_lowest)

        # 如果还没有当前电量，从 summary 获取
        if current_battery is None and isinstance(summary, dict):
            current_battery = summary.get('bodyBatteryMostRecentValue') or summary.get('bodyBatteryCurrentValue')

        logger.info(f"最终身体电量: charged={charged}, drained={drained}, most_charged={most_charged}, lowest={lowest}, current={current_battery}")

        # 调试：打印 summary 中所有 bodyBattery 相关字段
        if isinstance(summary, dict):
            bb_fields = {k: v for k, v in summary.items() if 'bodyBattery' in k or 'battery' in k.lower()}
            if bb_fields:
                logger.debug(f"Summary中的电量相关字段: {bb_fields}")

        # 压力数据（可能来自get_all_day_stress或summary）
        stress_data_raw = None
        if isinstance(raw_data, dict):
            stress_data_raw = raw_data.get('stress')

        stress_level = None
        if isinstance(stress_data_raw, list) and stress_data_raw:
            # get_all_day_stress返回的是数组，需要计算平均值
            stress_values = [s.get('stressLevelValue', s.get('value', 0)) for s in stress_data_raw if isinstance(s, dict)]
            stress_level = sum(stress_values) / len(stress_values) if stress_values else None
        elif isinstance(stress_data_raw, dict) and stress_data_raw:
            # get_all_day_stress返回字典，包含avgStressLevel和maxStressLevel
            stress_level = (
                stress_data_raw.get('avgStressLevel') or
                stress_data_raw.get('averageStressLevel') or
                stress_data_raw.get('stressLevel') or
                stress_data_raw.get('value') or
                stress_data_raw.get('stressLevelValue')
            )

        # 如果从stress数据中没有获取到，尝试从summary获取
        if stress_level is None and isinstance(summary, dict):
            stress_level = (
                summary.get('averageStressLevel') or
                summary.get('avgStressLevel') or
                summary.get('stressLevel') or
                summary.get('stress')
            )

        logger.debug(f"提取的压力水平: {stress_level} (来源: {'stress数据' if stress_data_raw else 'summary' if isinstance(summary, dict) else '无'})")

        # 活动数据（从summary获取，如果失败则从活动数据获取）
        steps = None
        calories = None
        active_minutes = None
        distance = None
        floors = None
        moderate_mins = None
        vigorous_mins = None

        # 检查summary是否有效（不是None且不是空字典）
        # 注意：summary可能包含其他API的数据（sleep、heart_rate等），需要检查是否有基础活动数据
        has_valid_summary = isinstance(summary, dict) and len(summary) > 0
        has_activity_data = has_valid_summary and any(key in summary for key in ['totalSteps', 'steps', 'totalCalories', 'calories', 'distance'])

        if has_valid_summary:
            # 步数：优先使用totalSteps
            steps = (
                summary.get('totalSteps') or
                summary.get('steps') or
                safe_get_nested(summary, 'stepGoal', 'steps')
            )
            logger.debug(f"从summary获取步数: {steps}")

            # 卡路里：优先使用totalKilocalories
            calories = (
                summary.get('totalKilocalories') or
                summary.get('activeKilocalories') or
                summary.get('calories') or
                summary.get('caloriesBurned') or
                summary.get('totalCalories') or
                safe_get_nested(summary, 'netCalorieGoal', 'calories')
            )

            # 距离和楼层
            distance = summary.get('totalDistanceMeters') or summary.get('distanceInMeters')
            floors = summary.get('floorsAscended') or summary.get('floorsClimbed')

            moderate_mins = summary.get('moderateIntensityMinutes') or summary.get('moderateActivityMinutes') or 0
            vigorous_mins = summary.get('vigorousIntensityMinutes') or summary.get('vigorousActivityMinutes') or 0
            highly_active_seconds = summary.get('highlyActiveSeconds') or 0
            active_minutes = summary.get('activeMinutes') or (highly_active_seconds // 60 if highly_active_seconds else 0) or ((moderate_mins or 0) + (vigorous_mins or 0)) or 0
        else:
            logger.info(f"summary无效或为空，将从活动数据获取所有指标")

        # 如果summary中没有活动数据，或者关键指标缺失，尝试从活动数据API中获取
        # 注意：即使值为0，也可能是有效数据，但如果summary中没有这些字段，应该从活动数据获取
        needs_activity_data = (
            not has_activity_data or
            steps is None or
            calories is None or
            distance is None or
            floors is None
        )
        if needs_activity_data:
            logger.info(f"触发活动数据查询: has_activity_data={has_activity_data}, steps={steps}, calories={calories}, distance={distance}, floors={floors}")
            try:
                # get_activities_by_date 需要字符串格式的日期
                date_str = record_date.isoformat() if hasattr(record_date, 'isoformat') else str(record_date)
                logger.info(f"正在调用 get_activities_by_date({date_str}, {date_str})")
                activities = self.client.get_activities_by_date(date_str, date_str)
                logger.info(f"get_activities_by_date 返回: type={type(activities)}, len={len(activities) if isinstance(activities, list) else 'N/A'}")
                if activities and isinstance(activities, list):
                    # 计算当天所有活动的汇总数据
                    total_steps = 0
                    total_calories = 0
                    total_distance = 0
                    total_floors = 0
                    total_moderate_mins = 0
                    total_vigorous_mins = 0

                    for activity in activities:
                        if isinstance(activity, dict):
                            # 步数
                            activity_steps = activity.get('steps') or activity.get('totalSteps') or 0
                            if activity_steps:
                                total_steps += int(activity_steps)

                            # 卡路里
                            activity_calories = activity.get('calories') or activity.get('totalCalories') or 0
                            if activity_calories:
                                total_calories += int(activity_calories)

                            # 距离（米）
                            activity_distance = activity.get('distance') or activity.get('distanceInMeters') or 0
                            if activity_distance:
                                total_distance += float(activity_distance)

                            # 楼层
                            activity_floors = activity.get('elevationGain') or activity.get('floorsAscended') or 0
                            if activity_floors:
                                total_floors += int(activity_floors)

                            # 强度活动时间（从活动数据获取）
                            activity_moderate = activity.get('moderateIntensityMinutes') or activity.get('moderateActivityMinutes') or 0
                            activity_vigorous = activity.get('vigorousIntensityMinutes') or activity.get('vigorousActivityMinutes') or 0

                            # 如果没有直接的强度时间，尝试从活动时长和类型推断
                            if not activity_moderate and not activity_vigorous:
                                duration_seconds = activity.get('duration') or activity.get('elapsedDuration') or 0
                                if duration_seconds:
                                    duration_minutes = duration_seconds / 60
                                    activity_type = activity.get('activityType', {}).get('typeKey', '').lower() if isinstance(activity.get('activityType'), dict) else str(activity.get('activityType', '')).lower()

                                    # 根据活动类型判断强度
                                    # 高强度活动类型（扩展列表）
                                    vigorous_types = [
                                        'running', 'cycling', 'swimming', 'rowing', 'elliptical', 'strength_training',
                                        'hiit', 'interval_training', 'cardio', 'indoor_cardio', 'treadmill',
                                        'stair_climbing', 'jump_rope', 'boxing', 'kickboxing', 'martial_arts',
                                        'cross_training', 'crossfit', 'aerobics', 'spinning', 'circuit_training',
                                        'boot_camp', 'fitness_equipment', 'gym', 'workout', 'sport', 'basketball',
                                        'soccer', 'tennis', 'badminton', 'squash', 'racquet', 'football',
                                        'hockey', 'lacrosse', 'rugby', 'volleyball', 'handball',
                                        'ski', 'snowboard', 'mountaineering', 'climb', 'bouldering',
                                        'surfing', 'water_ski', 'wakeboard', 'paddl', 'kayak', 'canoe'
                                    ]
                                    # 中等强度活动类型（扩展列表）
                                    moderate_types = [
                                        'walking', 'hiking', 'yoga', 'pilates', 'stretching',
                                        'golf', 'bowling', 'fishing', 'hunting', 'sailing',
                                        'horseback', 'dancing', 'tai_chi', 'qigong', 'meditation',
                                        'gardening', 'cleaning', 'other'
                                    ]

                                    if any(vt in activity_type for vt in vigorous_types):
                                        total_vigorous_mins += duration_minutes
                                        logger.debug(f"活动类型 '{activity_type}' 归类为高强度，时长: {duration_minutes}分钟")
                                    elif any(mt in activity_type for mt in moderate_types):
                                        total_moderate_mins += duration_minutes
                                        logger.debug(f"活动类型 '{activity_type}' 归类为中等强度，时长: {duration_minutes}分钟")
                                    elif duration_minutes >= 10:
                                        # 未知活动类型但有足够时长，默认归类为中等强度
                                        total_moderate_mins += duration_minutes
                                        logger.info(f"未识别的活动类型 '{activity_type}'，默认归类为中等强度，时长: {duration_minutes}分钟")
                            else:
                                if activity_moderate:
                                    total_moderate_mins += int(activity_moderate)
                                if activity_vigorous:
                                    total_vigorous_mins += int(activity_vigorous)

                    # 更新数据（如果之前没有获取到，或者值为0但活动数据中有值）
                    # 修复：如果活动数据的步数大于summary的步数，应该使用活动数据（更准确）
                    logger.info(f"步数对比 - summary步数: {steps}, 活动数据总步数: {total_steps}")
                    if steps is None or (steps == 0 and total_steps > 0) or (total_steps > steps):
                        old_steps = steps
                        steps = total_steps if total_steps > 0 else steps
                        logger.info(f"从活动数据更新步数: {old_steps} -> {steps}")
                    if calories is None or (calories == 0 and total_calories > 0):
                        calories = total_calories if total_calories > 0 else calories
                        logger.info(f"从活动数据获取卡路里: {calories}")
                    if distance is None or (distance == 0 and total_distance > 0):
                        distance = total_distance if total_distance > 0 else distance
                        logger.info(f"从活动数据获取距离: {distance}米")
                    if floors is None or (floors == 0 and total_floors > 0):
                        floors = total_floors if total_floors > 0 else floors
                        logger.info(f"从活动数据获取楼层: {floors}")
                    # 更新强度活动时间（如果之前没有获取到或为0）
                    if (moderate_mins is None or moderate_mins == 0) and total_moderate_mins > 0:
                        moderate_mins = total_moderate_mins
                        logger.info(f"从活动数据获取中等强度活动时间: {moderate_mins}分钟")
                    if (vigorous_mins is None or vigorous_mins == 0) and total_vigorous_mins > 0:
                        vigorous_mins = total_vigorous_mins
                        logger.info(f"从活动数据获取高强度活动时间: {vigorous_mins}分钟")
            except Exception as e:
                logger.error(f"从活动数据获取活动指标失败: {e}")

        # 安全的数值转换函数
        def safe_int(value):
            """安全地将值转换为整数，如果是字典或列表则返回None"""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    return None
            # 如果是字典或列表，尝试提取数值
            if isinstance(value, dict):
                # 尝试常见的数值字段名
                for key in ['value', 'amount', 'count', 'total', 'average', 'avg']:
                    if key in value and isinstance(value[key], (int, float)):
                        return int(value[key])
                return None
            return None

        def safe_float(value):
            """安全地将值转换为浮点数，如果是字典或列表则返回None"""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            if isinstance(value, dict):
                for key in ['value', 'amount', 'average', 'avg']:
                    if key in value and isinstance(value[key], (int, float)):
                        return float(value[key])
                return None
            return None

        # 睡眠时间转换（秒转分钟，处理毫秒）
        def seconds_to_minutes(value):
            if not value:
                return None
            if isinstance(value, (int, float)):
                # 如果是毫秒，先转换为秒
                if value > 86400:  # 如果大于一天的秒数，可能是毫秒
                    value = value / 1000
                return int(value // 60)
            return None

        # 解析新增字段
        # HRV状态
        hrv_status = None
        hrv_7day_avg = None
        if isinstance(sleep_data, dict):
            hrv_status = sleep_data.get('hrvStatus')
            if isinstance(hrv_status, dict):
                hrv_status = hrv_status.get('status') or hrv_status.get('hrvStatus')
            # 7天平均HRV - 从weeklyAverages或直接值
            hrv_7day_avg = safe_get_nested(sleep_data, 'hrvData', 'weeklyAvg') or sleep_data.get('hrvWeeklyAverage')

        # 强度活动时间（优先从summary获取，如果为0或None则使用从活动数据获取的值）
        moderate_intensity_mins = 0
        vigorous_intensity_mins = 0
        intensity_goal = None
        if isinstance(summary, dict):
            moderate_intensity_mins = summary.get('moderateIntensityMinutes', 0) or 0
            vigorous_intensity_mins = summary.get('vigorousIntensityMinutes', 0) or 0
            intensity_goal = summary.get('intensityMinutesGoal') or summary.get('weeklyIntensityMinutesGoal')

        # 如果summary中的强度活动时间为0或None，使用从活动数据获取的值
        if (moderate_intensity_mins == 0 and vigorous_intensity_mins == 0) and (moderate_mins is not None or vigorous_mins is not None):
            if moderate_mins is not None and moderate_mins > 0:
                moderate_intensity_mins = moderate_mins
            if vigorous_mins is not None and vigorous_mins > 0:
                vigorous_intensity_mins = vigorous_mins
            logger.info(f"使用从活动数据获取的强度活动时间: moderate={moderate_intensity_mins}, vigorous={vigorous_intensity_mins}")

        # 卡路里详细分类
        active_cals = None
        bmr_cals = None
        if isinstance(summary, dict):
            active_cals = summary.get('activeKilocalories') or summary.get('activeCalories')
            bmr_cals = summary.get('bmrKilocalories') or summary.get('restingCalories') or summary.get('bmrCalories')

        # 呼吸数据（优先从get_respiration_data获取，否则从sleep_data和summary获取）
        avg_resp_awake = None
        avg_resp_sleep = None
        lowest_resp = None
        highest_resp = None

        # 从呼吸独立API获取
        resp_data_raw = raw_data.get('respiration') if isinstance(raw_data, dict) else None
        if resp_data_raw:
            logger.info(f"处理呼吸数据，原始类型: {type(resp_data_raw)}")
            if isinstance(resp_data_raw, dict):
                # 尝试多种可能的字段名
                avg_resp_awake = (resp_data_raw.get('avgWakingRespirationValue') or
                                 resp_data_raw.get('averageWakingRespirationValue') or
                                 resp_data_raw.get('avgAwakeRespirationValue'))
                avg_resp_sleep = (resp_data_raw.get('avgSleepingRespirationValue') or
                                 resp_data_raw.get('averageSleepingRespirationValue') or
                                 resp_data_raw.get('avgSleepRespirationValue'))
                lowest_resp = (resp_data_raw.get('lowestRespirationValue') or
                              resp_data_raw.get('minRespirationValue') or
                              resp_data_raw.get('lowest'))
                highest_resp = (resp_data_raw.get('highestRespirationValue') or
                               resp_data_raw.get('maxRespirationValue') or
                               resp_data_raw.get('highest'))
                logger.info(f"从respiration API获取呼吸数据: awake={avg_resp_awake}, sleep={avg_resp_sleep}, low={lowest_resp}, high={highest_resp}")
                logger.debug(f"respiration数据键: {list(resp_data_raw.keys())}")
            elif isinstance(resp_data_raw, list) and resp_data_raw:
                # 如果是列表，尝试计算
                values = []
                for item in resp_data_raw:
                    if isinstance(item, dict):
                        val = item.get('respirationValue') or item.get('value')
                        if val is not None:
                            values.append(val)
                    elif isinstance(item, (int, float)):
                        values.append(item)
                if values:
                    avg_resp_awake = sum(values) / len(values)
                    lowest_resp = min(values)
                    highest_resp = max(values)
                    logger.info(f"从respiration列表计算呼吸数据: avg={avg_resp_awake}, low={lowest_resp}, high={highest_resp}, 样本数={len(values)}")

        # 如果独立API没有数据，从sleep_data获取
        if avg_resp_sleep is None and isinstance(sleep_data, dict):
            daily_dto = sleep_data.get('dailySleepDTO', {})
            if isinstance(daily_dto, dict):
                avg_resp_sleep = daily_dto.get('avgRespirationValue') or daily_dto.get('averageRespirationValue')
                if lowest_resp is None:
                    lowest_resp = daily_dto.get('lowestRespirationValue')
                if highest_resp is None:
                    highest_resp = daily_dto.get('highestRespirationValue')
                if avg_resp_sleep:
                    logger.info(f"从sleep_data获取呼吸数据: sleep={avg_resp_sleep}, low={lowest_resp}, high={highest_resp}")

        # 如果还没有数据，从summary获取
        if avg_resp_awake is None and isinstance(summary, dict):
            avg_resp_awake = summary.get('avgWakingRespirationValue') or summary.get('averageRespirationValue')
            if avg_resp_awake:
                logger.info(f"从summary获取清醒呼吸数据: awake={avg_resp_awake}")
        if lowest_resp is None and isinstance(summary, dict):
            lowest_resp = summary.get('lowestRespirationValue')
        if highest_resp is None and isinstance(summary, dict):
            highest_resp = summary.get('highestRespirationValue')

        # 血氧数据（优先从get_spo2_data获取，否则从summary获取）
        spo2_avg = None
        spo2_min = None
        spo2_max = None

        # 从spo2独立API获取
        spo2_data_raw = raw_data.get('spo2') if isinstance(raw_data, dict) else None
        if spo2_data_raw:
            logger.info(f"处理血氧数据，原始类型: {type(spo2_data_raw)}")
            if isinstance(spo2_data_raw, dict):
                # 尝试多种可能的字段名
                spo2_avg = (spo2_data_raw.get('avgOxygenPercentage') or
                           spo2_data_raw.get('averageSpO2') or
                           spo2_data_raw.get('avgSpO2') or
                           spo2_data_raw.get('average'))
                spo2_min = (spo2_data_raw.get('lowestOxygenPercentage') or
                           spo2_data_raw.get('lowestSpO2') or
                           spo2_data_raw.get('minSpO2') or
                           spo2_data_raw.get('lowest') or
                           spo2_data_raw.get('minimum'))
                spo2_max = (spo2_data_raw.get('highestOxygenPercentage') or
                           spo2_data_raw.get('highestSpO2') or
                           spo2_data_raw.get('maxSpO2') or
                           spo2_data_raw.get('highest') or
                           spo2_data_raw.get('maximum'))
                logger.info(f"从spo2 API获取血氧数据: avg={spo2_avg}, min={spo2_min}, max={spo2_max}")
                logger.debug(f"spo2数据键: {list(spo2_data_raw.keys())}")
            elif isinstance(spo2_data_raw, list) and spo2_data_raw:
                # 如果是列表，尝试计算平均值等
                values = []
                for item in spo2_data_raw:
                    if isinstance(item, dict):
                        val = item.get('oxygenPercentage') or item.get('spo2') or item.get('value')
                        if val is not None:
                            values.append(val)
                    elif isinstance(item, (int, float)):
                        values.append(item)
                if values:
                    spo2_avg = sum(values) / len(values)
                    spo2_min = min(values)
                    spo2_max = max(values)
                    logger.info(f"从spo2列表计算血氧数据: avg={spo2_avg}, min={spo2_min}, max={spo2_max}, 样本数={len(values)}")

        # 如果spo2独立API没有数据，尝试从summary获取
        if spo2_avg is None and isinstance(summary, dict):
            spo2_avg = summary.get('averageSpO2') or summary.get('avgSpO2')
            spo2_min = summary.get('lowestSpO2') or summary.get('minSpO2')
            spo2_max = summary.get('highestSpO2') or summary.get('maxSpO2')
            if spo2_avg:
                logger.info(f"从summary获取血氧数据: avg={spo2_avg}, min={spo2_min}, max={spo2_max}")

        # VO2 Max - 优先从 max_metrics 获取
        vo2max_run = None
        vo2max_cycle = None
        max_metrics = raw_data.get('max_metrics')
        if isinstance(max_metrics, dict):
            # max_metrics 结构可能是: {generic: {vo2MaxPreciseValue, fitnessAge}, running: {...}, cycling: {...}}
            generic = max_metrics.get('generic', {})
            running = max_metrics.get('running', {})
            cycling = max_metrics.get('cycling', {})

            # 尝试多种可能的字段名
            vo2max_run = (
                generic.get('vo2MaxPreciseValue') or
                generic.get('vo2MaxValue') or
                running.get('vo2MaxPreciseValue') or
                running.get('vo2MaxValue') or
                max_metrics.get('vo2MaxPreciseValue') or
                max_metrics.get('vo2MaxValue')
            )
            vo2max_cycle = (
                cycling.get('vo2MaxPreciseValue') or
                cycling.get('vo2MaxValue')
            )
            if vo2max_run:
                logger.info(f"从max_metrics获取VO2Max: running={vo2max_run}, cycling={vo2max_cycle}")

        # 如果 max_metrics 没有，回退到 summary
        if vo2max_run is None and isinstance(summary, dict):
            vo2max_run = summary.get('vo2MaxRunning') or summary.get('vo2Max')
            vo2max_cycle = summary.get('vo2MaxCycling')
            if vo2max_run:
                logger.info(f"从summary获取VO2Max: running={vo2max_run}, cycling={vo2max_cycle}")

        # 楼层和距离（如果之前没有从活动数据获取到，再从summary获取）
        floors_goal_val = None
        if (floors is None or floors == 0) and isinstance(summary, dict):
            floors_from_summary = summary.get('floorsAscended') or summary.get('floorsClimbed')
            if floors_from_summary:
                floors = floors_from_summary
            floors_goal_val = summary.get('floorsAscendedGoal') or summary.get('floorsGoal')
        if (distance is None or distance == 0) and isinstance(summary, dict):
            distance_from_summary = summary.get('totalDistanceMeters') or summary.get('distanceInMeters')
            if distance_from_summary:
                distance = distance_from_summary

        # 记录解析结果用于调试
        logger.info(f"解析结果 - 睡眠分数: {sleep_score}, 睡眠时长(秒): {sleep_duration_seconds}, 静息心率: {resting_hr}, 平均心率: {avg_hr}, 步数: {steps}")

        # --- P1a: 解析 Training Readiness / Status / 其他指标 ---
        tr = raw_data.get('training_readiness') if isinstance(raw_data, dict) else None
        training_readiness_score = None
        training_readiness_level = None
        training_readiness_factors = None
        if isinstance(tr, dict):
            training_readiness_score = safe_int(tr.get('score'))
            training_readiness_level = tr.get('level') or tr.get('feedbackShort')
            factor_keys = ('sleepScore', 'sleepHistory', 'hrvWeeklyAverage', 'recoveryTime',
                           'acuteLoad', 'stressHistory', 'sleepBreakdown', 'feedbackLong', 'feedbackShort')
            factors = {k: tr.get(k) for k in factor_keys if tr.get(k) is not None}
            training_readiness_factors = factors or None

        ts = raw_data.get('training_status') if isinstance(raw_data, dict) else None
        training_status_val = None
        training_status_feedback = None
        acute_load_val = None
        load_ratio_val = None
        if isinstance(ts, dict):
            # 取最新 latest payload
            latest = ts.get('mostRecentTrainingStatus') or {}
            if isinstance(latest, dict):
                latest_dto = latest.get('latestTrainingStatusData') or {}
                if isinstance(latest_dto, dict):
                    # latest_dto 是 {device_id: {...}} 的字典，取第一个
                    first_entry = next(iter(latest_dto.values()), {}) if isinstance(latest_dto, dict) else {}
                    if isinstance(first_entry, dict):
                        # trainingStatusKey 是字符串 ('productive' 等)，trainingStatus 是整数枚举
                        training_status_val = (
                            first_entry.get('trainingStatusKey')
                            or (str(first_entry['trainingStatus']) if first_entry.get('trainingStatus') is not None else None)
                        )
                        training_status_feedback = first_entry.get('trainingStatusFeedbackPhrase')
                        acute_load_val = safe_float(first_entry.get('acuteTrainingLoadDTO', {}).get('acwrLowerBound') if isinstance(first_entry.get('acuteTrainingLoadDTO'), dict) else first_entry.get('acuteLoad'))
                        load_ratio_val = safe_float(first_entry.get('acwrStatus') if isinstance(first_entry.get('acwrStatus'), (int, float)) else None)
            # fallback（顶层也可能有）
            if training_status_val is None:
                fallback = ts.get('trainingStatusKey') or ts.get('trainingStatus')
                if fallback is not None:
                    training_status_val = str(fallback) if not isinstance(fallback, str) else fallback
            if acute_load_val is None:
                acute_load_val = safe_float(ts.get('acuteLoad'))
            if load_ratio_val is None:
                load_ratio_val = safe_float(ts.get('loadRatio') or ts.get('acwr'))

        endurance_raw = raw_data.get('endurance_score') if isinstance(raw_data, dict) else None
        endurance_score_val = None
        if isinstance(endurance_raw, dict):
            endurance_score_val = safe_int(endurance_raw.get('overallScore') or endurance_raw.get('score'))

        hill_raw = raw_data.get('hill_score') if isinstance(raw_data, dict) else None
        hill_score_val = None
        if isinstance(hill_raw, dict):
            hill_score_val = safe_int(hill_raw.get('overallScore') or hill_raw.get('score'))

        hydration_raw = raw_data.get('hydration') if isinstance(raw_data, dict) else None
        hydration_ml_val = None
        if isinstance(hydration_raw, dict):
            hydration_ml_val = safe_int(hydration_raw.get('valueInML') or hydration_raw.get('hydration'))

        race_pred_raw = raw_data.get('race_predictions') if isinstance(raw_data, dict) else None
        race_predictions_val = None
        if isinstance(race_pred_raw, dict):
            race_predictions_val = {
                '5k': race_pred_raw.get('time5K'),
                '10k': race_pred_raw.get('time10K'),
                'half_marathon': race_pred_raw.get('timeHalfMarathon'),
                'marathon': race_pred_raw.get('timeMarathon'),
            }
            # 去空
            race_predictions_val = {k: v for k, v in race_predictions_val.items() if v is not None}
            if not race_predictions_val:
                race_predictions_val = None

        # vo2max_fitness_age 从 max_metrics 抽
        vo2max_fitness_age_val = None
        max_metrics_raw = raw_data.get('max_metrics') if isinstance(raw_data, dict) else None
        if isinstance(max_metrics_raw, dict):
            generic = max_metrics_raw.get('generic') if isinstance(max_metrics_raw.get('generic'), dict) else max_metrics_raw
            vo2max_fitness_age_val = safe_int(generic.get('fitnessAge'))

        # HRV 日均（raw_data 里 hrv_raw 覆盖了 hrv_data）
        hrv_raw_dict = raw_data.get('hrv_raw') if isinstance(raw_data, dict) else None
        if isinstance(hrv_raw_dict, dict):
            hrv_summary = hrv_raw_dict.get('hrvSummary') or {}
            if isinstance(hrv_summary, dict):
                if hrv is None:
                    hrv = safe_float(hrv_summary.get('lastNightAvg'))
                if not hrv_status:
                    hrv_status = hrv_summary.get('status')
                if hrv_7day_avg is None:
                    hrv_7day_avg = safe_float(hrv_summary.get('weeklyAvg'))

        result = GarminDataCreate(
            user_id=user_id,
            record_date=record_date,
            avg_heart_rate=safe_int(avg_hr),
            max_heart_rate=safe_int(max_hr),
            min_heart_rate=safe_int(min_hr),
            resting_heart_rate=safe_int(resting_hr),
            hrv=safe_float(hrv),
            hrv_status=hrv_status,
            hrv_7day_avg=safe_float(hrv_7day_avg),
            sleep_score=safe_int(sleep_score),
            total_sleep_duration=seconds_to_minutes(sleep_duration_seconds),
            deep_sleep_duration=seconds_to_minutes(deep_sleep_seconds),
            rem_sleep_duration=seconds_to_minutes(rem_sleep_seconds),
            light_sleep_duration=seconds_to_minutes(light_sleep_seconds),
            awake_duration=seconds_to_minutes(awake_seconds),
            nap_duration=seconds_to_minutes(nap_seconds),
            sleep_start_time=sleep_start_time,
            sleep_end_time=sleep_end_time,
            body_battery_charged=safe_int(charged),
            body_battery_drained=safe_int(drained),
            body_battery_most_charged=safe_int(most_charged),
            body_battery_lowest=safe_int(lowest),
            body_battery_current=safe_int(current_battery),
            stress_level=safe_int(stress_level),
            steps=safe_int(steps),
            calories_burned=safe_int(calories),
            active_calories=safe_int(active_cals),
            bmr_calories=safe_int(bmr_cals),
            active_minutes=safe_int(active_minutes),
            intensity_minutes_goal=safe_int(intensity_goal),
            moderate_intensity_minutes=safe_int(moderate_intensity_mins),
            vigorous_intensity_minutes=safe_int(vigorous_intensity_mins),
            avg_respiration_awake=safe_float(avg_resp_awake),
            avg_respiration_sleep=safe_float(avg_resp_sleep),
            lowest_respiration=safe_float(lowest_resp),
            highest_respiration=safe_float(highest_resp),
            spo2_avg=safe_float(spo2_avg),
            spo2_min=safe_float(spo2_min),
            spo2_max=safe_float(spo2_max),
            vo2max_running=safe_float(vo2max_run),
            vo2max_cycling=safe_float(vo2max_cycle),
            floors_climbed=safe_int(floors),
            floors_goal=safe_int(floors_goal_val),
            distance_meters=safe_float(distance),
            # P1a: Training Readiness / Status
            training_readiness_score=training_readiness_score,
            training_readiness_level=training_readiness_level,
            training_readiness_factors=training_readiness_factors,
            training_status=training_status_val,
            training_status_feedback=training_status_feedback,
            acute_load=acute_load_val,
            load_ratio=load_ratio_val,
            # P1a: 其他指标
            endurance_score=endurance_score_val,
            hill_score=hill_score_val,
            race_predictions=race_predictions_val,
            hydration_ml=hydration_ml_val,
            vo2max_fitness_age=vo2max_fitness_age_val,
        )

        return result

    def sync_daily_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[GarminData]:
        """
        同步指定日期的数据到数据库

        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期

        Returns:
            保存的GarminData对象，如果失败返回None
        """
        prefix = self._log_prefix()
        try:
            # 🔑 优先使用缓存的 token 进行认证，避免频繁登录触发账号锁定
            self._ensure_authenticated(db)

            # 获取所有数据（减少日志输出，使用debug级别）
            logger.debug(f"{prefix} 开始获取 {target_date} 的数据...")
            raw_data = self.get_all_daily_data(target_date)

            if not raw_data:
                logger.debug(f"{prefix} 未获取到 {target_date} 的数据（raw_data为空）")
                return None

            logger.debug(f"{prefix} 获取到 {target_date} 的原始数据，键数量: {len(raw_data) if isinstance(raw_data, dict) else 'N/A'}")

            # 解析数据
            logger.debug(f"{prefix} 开始解析 {target_date} 的数据...")
            garmin_data = self.parse_to_garmin_data_create(raw_data, user_id, target_date)

            logger.debug(f"{prefix} 解析完成，步数: {garmin_data.steps}, 心率: {garmin_data.resting_heart_rate}")

            # 保存到数据库
            logger.debug(f"{prefix} 开始保存 {target_date} 的数据到数据库...")
            from app.services.data_collection.garmin_service import GarminService
            garmin_service = GarminService()
            result = garmin_service.save_garmin_data(db, garmin_data)

            logger.info(f"{prefix} ✅ 成功同步 {target_date}，ID: {result.id}")

            # 同步心率采样数据
            self._sync_heart_rate_samples(db, user_id, target_date)

            # 同步血氧采样数据
            self._sync_spo2_samples(db, user_id, target_date, raw_data)

            # 同步睡眠阶段时间线
            self._sync_sleep_level_intervals(db, user_id, target_date, raw_data)

            # P1a: 新增时序/设备同步
            self._sync_respiration_samples(db, user_id, target_date, raw_data)
            self._sync_hrv_readings(db, user_id, target_date, raw_data)
            self._sync_stress_samples(db, user_id, target_date, raw_data)
            self._sync_body_composition(db, user_id, target_date)
            self._sync_devices(db, user_id)

            return result

        except Exception as e:
            logger.error(
                "%s 同步 Garmin 数据失败 - error_type=%s, reason=%s",
                prefix,
                type(e).__name__,
                safe_garmin_error_message(e),
            )
            return None

    def _sync_heart_rate_samples(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> int:
        """
        同步心率采样数据（每15分钟一个点）

        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期

        Returns:
            保存的采样点数量
        """
        prefix = self._log_prefix()
        try:
            # 获取心率时间序列数据
            hr_data = self.get_heart_rates(target_date)

            if not hr_data:
                logger.debug(f"{prefix} 未获取到 {target_date} 的心率时间序列数据")
                return 0

            # 解析心率数据
            hr_values = hr_data.get("heartRateValues") or []
            if not hr_values:
                logger.debug(f"{prefix} {target_date} 的心率时间序列数据为空")
                return 0

            from app.models.daily_health import HeartRateSample
            from datetime import time as dt_time

            # 按15分钟间隔采样
            samples_by_slot = {}  # key: "HH:MM" (每15分钟一个slot)

            for item in hr_values:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        timestamp_ms = item[0]
                        hr_value = item[1]

                        if hr_value is None or hr_value <= 0:
                            continue

                        # 转换时间戳
                        dt = datetime.fromtimestamp(timestamp_ms / 1000)

                        # 计算15分钟时间槽
                        slot_minute = (dt.minute // 15) * 15
                        slot_key = f"{dt.hour:02d}:{slot_minute:02d}"

                        # 每个时间槽只保留第一个值
                        if slot_key not in samples_by_slot:
                            samples_by_slot[slot_key] = {
                                "time": dt_time(dt.hour, slot_minute),
                                "value": int(hr_value)
                            }
                except (ValueError, TypeError, IndexError):
                    continue

            if not samples_by_slot:
                return 0

            # 删除该日期已有的采样数据
            db.query(HeartRateSample).filter(
                HeartRateSample.user_id == user_id,
                HeartRateSample.record_date == target_date
            ).delete()

            # 批量插入新数据
            samples_to_insert = []
            for slot_key, data in sorted(samples_by_slot.items()):
                samples_to_insert.append(HeartRateSample(
                    user_id=user_id,
                    record_date=target_date,
                    sample_time=data["time"],
                    heart_rate=data["value"],
                    source="garmin"
                ))

            db.bulk_save_objects(samples_to_insert)
            db.commit()

            logger.info(f"{prefix} 保存了 {target_date} 的 {len(samples_to_insert)} 个心率采样点")
            return len(samples_to_insert)

        except Exception as e:
            logger.warning(f"{prefix} 同步心率采样数据失败: {e}")
            return 0

    def _sync_spo2_samples(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        raw_data: Dict[str, Any]
    ) -> int:
        """同步血氧采样数据（睡眠期间每分钟一个点）"""
        prefix = self._log_prefix()
        try:
            if not isinstance(raw_data, dict):
                return 0

            from app.models.daily_health import SpO2Sample
            from datetime import time as dt_time, timedelta

            samples = []

            # Strategy 1: sleep data 中的 wellnessEpochSPO2DataDTOList（最完整的逐分钟数据）
            sleep_raw = raw_data.get('sleep')
            if isinstance(sleep_raw, dict):
                epoch_spo2_list = sleep_raw.get('wellnessEpochSPO2DataDTOList', [])
                if isinstance(epoch_spo2_list, list) and epoch_spo2_list:
                    logger.info(f"{prefix} 从 sleep.wellnessEpochSPO2DataDTOList 解析 SpO2，共 {len(epoch_spo2_list)} 条")
                    if epoch_spo2_list[0] and isinstance(epoch_spo2_list[0], dict):
                        logger.info(f"{prefix} SpO2 epoch 条目示例 keys: {list(epoch_spo2_list[0].keys())}, values: {epoch_spo2_list[0]}")
                    for item in epoch_spo2_list:
                        try:
                            if not isinstance(item, dict):
                                continue
                            epoch_ts = item.get('epochTimestamp') or item.get('startTimestampGMT')
                            spo2_val = (
                                item.get('spo2Reading')
                                or item.get('spo2Value')
                                or item.get('deviceSpo2Value')
                                or item.get('value')
                                or item.get('spo2')
                            )
                            if epoch_ts is None or spo2_val is None:
                                continue
                            if isinstance(epoch_ts, str):
                                try:
                                    # Garmin 给的 ISO 字符串如 "2026-05-03T16:09:00.0" 是 GMT
                                    # 时间, 必须强制 UTC 时区. 否则 fromisoformat 返 naive
                                    # datetime, .timestamp() 会按服务器本地 TZ 解释, 导致
                                    # 整段时序偏移 ±服务器UTC偏移 (CST 服务器偏 -8h).
                                    parsed = datetime.fromisoformat(epoch_ts.rstrip('Z'))
                                    if parsed.tzinfo is None:
                                        parsed = parsed.replace(tzinfo=UTC)
                                    epoch_ts = int(parsed.timestamp() * 1000)
                                except (ValueError, TypeError):
                                    continue
                            epoch_ts = int(epoch_ts)
                            spo2_int = int(spo2_val)
                            if not (50 <= spo2_int <= 100):
                                continue
                            # 显式转 CST: 服务器 TZ 可能漂移, 不依赖默认本地时区
                            sample_dt = datetime.fromtimestamp(epoch_ts / 1000, timezone(timedelta(hours=8)))
                            samples.append({
                                "time": dt_time(sample_dt.hour, sample_dt.minute),
                                "value": spo2_int,
                                "epoch_ms": epoch_ts,
                            })
                        except (ValueError, TypeError, OSError):
                            continue

            # Strategy 2: spo2 API 的 timeOffsetSleepSpo2
            spo2_raw = raw_data.get('spo2') if not samples else None
            if spo2_raw and isinstance(spo2_raw, dict):
                time_offset_data = spo2_raw.get('timeOffsetSleepSpo2')
                # 优先 GMT 字段, 否则降级 Local. 两者都按 ISO 字符串处理.
                gmt_str = spo2_raw.get('startTimestampGMT')
                local_str = spo2_raw.get('startTimestampLocal')
                start_ts_str = gmt_str or local_str
                start_is_gmt = bool(gmt_str)

                if time_offset_data and isinstance(time_offset_data, dict) and start_ts_str:
                    try:
                        parsed = datetime.fromisoformat(start_ts_str.rstrip('Z').replace('.0', ''))
                        if parsed.tzinfo is None:
                            # GMT 字段强 UTC; Local 字段按 CST 解
                            parsed = parsed.replace(tzinfo=UTC if start_is_gmt else timezone(timedelta(hours=8)))
                        start_ts = parsed
                    except (ValueError, TypeError):
                        start_ts = None

                    if start_ts:
                        for offset_ms_str, spo2_val in time_offset_data.items():
                            try:
                                offset_ms = int(offset_ms_str)
                                if spo2_val is None or not (50 <= int(spo2_val) <= 100):
                                    continue
                                sample_dt = start_ts + timedelta(milliseconds=offset_ms)
                                # 转 CST 取本地 HH:MM (服务器 TZ 也是 CST 但保险显式转)
                                cst_dt = sample_dt.astimezone(timezone(timedelta(hours=8)))
                                samples.append({
                                    "time": dt_time(cst_dt.hour, cst_dt.minute),
                                    "value": int(spo2_val),
                                    "epoch_ms": int(start_ts.timestamp() * 1000) + offset_ms,
                                })
                            except (ValueError, TypeError):
                                continue

            # Strategy 3: spo2 API 的 sleepMeasurement
            if not samples:
                spo2_raw = raw_data.get('spo2')
                if spo2_raw and isinstance(spo2_raw, dict):
                    sleep_measurements = spo2_raw.get('sleepMeasurement', [])
                    if isinstance(sleep_measurements, list):
                        for item in sleep_measurements:
                            try:
                                epoch_ts = item.get('epochTimestamp')
                                spo2_val = item.get('spo2Value') or item.get('value')
                                if epoch_ts and spo2_val and 50 <= int(spo2_val) <= 100:
                                    # epoch_ts 假设为 UTC ms 数值, 显式转 CST
                                    sample_dt = datetime.fromtimestamp(epoch_ts / 1000, timezone(timedelta(hours=8)))
                                    samples.append({
                                        "time": dt_time(sample_dt.hour, sample_dt.minute),
                                        "value": int(spo2_val),
                                        "epoch_ms": int(epoch_ts),
                                    })
                            except (ValueError, TypeError):
                                continue

            if not samples:
                logger.debug(f"{prefix} {target_date} 无 SpO2 采样数据（sleep/spo2 API 均无逐分钟数据）")
                return 0

            logger.info(f"{prefix} {target_date} 解析到 {len(samples)} 个原始 SpO2 采样点，去重后…")

            seen_minutes: Dict[str, dict] = {}
            for s in samples:
                key = f"{s['time'].hour:02d}:{s['time'].minute:02d}"
                if key not in seen_minutes:
                    seen_minutes[key] = s

            logger.info(f"{prefix} {target_date} 去重后 {len(seen_minutes)} 个，准备写入 DB…")
            for s in samples:
                key = f"{s['time'].hour:02d}:{s['time'].minute:02d}"
                if key not in seen_minutes:
                    seen_minutes[key] = s

            db.query(SpO2Sample).filter(
                SpO2Sample.user_id == user_id,
                SpO2Sample.record_date == target_date
            ).delete()

            objects = [
                SpO2Sample(
                    user_id=user_id,
                    record_date=target_date,
                    sample_time=data["time"],
                    spo2_value=data["value"],
                    epoch_ms=data.get("epoch_ms"),
                    source="garmin"
                )
                for data in sorted(seen_minutes.values(), key=lambda x: x.get("epoch_ms", 0))
            ]

            db.bulk_save_objects(objects)
            db.commit()

            logger.info(f"{prefix} 保存了 {target_date} 的 {len(objects)} 个血氧采样点")
            return len(objects)

        except Exception as e:
            logger.warning(f"{prefix} 同步血氧采样数据失败: {e}")
            import traceback
            logger.warning(f"{prefix} SpO2 同步详细错误: {traceback.format_exc()}")
            return 0

    def _sync_sleep_level_intervals(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        raw_data: Dict[str, Any]
    ) -> int:
        """同步睡眠阶段时间段（deep/light/rem/awake）"""
        prefix = self._log_prefix()
        try:
            if not isinstance(raw_data, dict):
                return 0

            sleep_raw = raw_data.get('sleep')
            if not isinstance(sleep_raw, dict):
                return 0

            sleep_levels = sleep_raw.get('sleepLevels')
            if not isinstance(sleep_levels, list) or not sleep_levels:
                daily_dto = sleep_raw.get('dailySleepDTO', {})
                if isinstance(daily_dto, dict):
                    sleep_levels = daily_dto.get('sleepLevels', [])

            if not isinstance(sleep_levels, list) or not sleep_levels:
                return 0

            from app.models.daily_health import SleepLevelInterval

            # Garmin sleepLevels.activityLevel 可能是：
            #   - 数字编码（浮点）: 0.0=deep, 1.0=light, 2.0=rem, 3.0=awake, -1=unmeasurable
            #   - 字符串: 'deep'/'light'/'rem'/'awake'/'DEEP'/...（取决于账户版本）
            STR_LEVEL_MAP = {
                'deep': 'deep', 'DEEP': 'deep',
                'light': 'light', 'LIGHT': 'light',
                'rem': 'rem', 'REM': 'rem',
                'awake': 'awake', 'AWAKE': 'awake',
                'unmeasurable': 'awake', 'UNMEASURABLE': 'awake',
            }
            NUM_LEVEL_MAP = {
                0: 'deep',
                1: 'light',
                2: 'rem',
                3: 'awake',
                -1: 'awake',  # unmeasurable 当 awake 处理
            }

            def _map_level(raw):
                if raw is None:
                    return None
                if isinstance(raw, (int, float)):
                    return NUM_LEVEL_MAP.get(int(raw))
                return STR_LEVEL_MAP.get(str(raw).strip())

            intervals = []
            for item in sleep_levels:
                if not isinstance(item, dict):
                    continue
                start_gmt = item.get('startGMT') or item.get('startTimestampGMT')
                end_gmt = item.get('endGMT') or item.get('endTimestampGMT')
                level = item.get('activityLevel') or item.get('level') or item.get('sleepLevel')

                if not start_gmt or not end_gmt or not level:
                    continue

                mapped_level = _map_level(level)
                if not mapped_level:
                    continue

                try:
                    if isinstance(start_gmt, (int, float)):
                        start_ms = int(start_gmt)
                    else:
                        # ISO 字符串如 "2026-05-03T16:08:00.0" 是 GMT 时间, 必须强制 UTC
                        # tzinfo 否则 .timestamp() 按服务器本地 TZ 解释 (CST 偏 -8h)
                        parsed = datetime.fromisoformat(str(start_gmt).rstrip('Z'))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=UTC)
                        start_ms = int(parsed.timestamp() * 1000)
                    if isinstance(end_gmt, (int, float)):
                        end_ms = int(end_gmt)
                    else:
                        parsed_end = datetime.fromisoformat(str(end_gmt).rstrip('Z'))
                        if parsed_end.tzinfo is None:
                            parsed_end = parsed_end.replace(tzinfo=UTC)
                        end_ms = int(parsed_end.timestamp() * 1000)
                except (ValueError, TypeError, OSError):
                    continue

                intervals.append({
                    "start_epoch_ms": start_ms,
                    "end_epoch_ms": end_ms,
                    "activity_level": mapped_level,
                })

            if not intervals:
                return 0

            db.query(SleepLevelInterval).filter(
                SleepLevelInterval.user_id == user_id,
                SleepLevelInterval.record_date == target_date
            ).delete()

            objects = [
                SleepLevelInterval(
                    user_id=user_id,
                    record_date=target_date,
                    start_epoch_ms=iv["start_epoch_ms"],
                    end_epoch_ms=iv["end_epoch_ms"],
                    activity_level=iv["activity_level"],
                    source="garmin"
                )
                for iv in sorted(intervals, key=lambda x: x["start_epoch_ms"])
            ]

            db.bulk_save_objects(objects)
            db.commit()

            logger.info(f"{prefix} 保存了 {target_date} 的 {len(objects)} 个睡眠阶段时间段")
            return len(objects)

        except Exception as e:
            logger.warning(f"{prefix} 同步睡眠阶段数据失败: {e}")
            return 0

    # ------------------------------------------------------------------
    # P1a: 新增时序/设备同步助手
    # ------------------------------------------------------------------

    def _sync_respiration_samples(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        raw_data: Dict[str, Any]
    ) -> int:
        """呼吸频率逐分钟采样 → respiration_samples。

        garminconnect.get_respiration_data() 的 respirationValuesArray 格式:
        [[epochMs, brpm], [epochMs, brpm], ...]
        """
        prefix = self._log_prefix()
        try:
            if not isinstance(raw_data, dict):
                return 0
            resp_raw = raw_data.get('respiration')
            if not isinstance(resp_raw, dict):
                return 0
            values = resp_raw.get('respirationValuesArray') or resp_raw.get('respirationValueDescriptorsDTOList') or []
            if not isinstance(values, list) or not values:
                return 0

            from app.models.garmin_timeseries import RespirationSample
            from datetime import time as dt_time

            seen: Dict[str, dict] = {}
            for item in values:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        ts_ms = int(item[0])
                        rate = item[1]
                    elif isinstance(item, dict):
                        ts_ms = int(item.get('epochMillis') or item.get('startTimeGMT') or 0)
                        rate = item.get('respirationValue') or item.get('value')
                    else:
                        continue

                    if rate is None:
                        continue
                    rate_f = float(rate)
                    # Garmin 用 -1/-2 表示无效数据
                    if rate_f < 4 or rate_f > 60:
                        continue

                    dt = datetime.fromtimestamp(ts_ms / 1000)
                    key = f"{dt.hour:02d}:{dt.minute:02d}"
                    if key not in seen:
                        seen[key] = {
                            "time": dt_time(dt.hour, dt.minute),
                            "value": rate_f,
                            "epoch_ms": ts_ms,
                        }
                except (ValueError, TypeError, OSError):
                    continue

            if not seen:
                return 0

            db.query(RespirationSample).filter(
                RespirationSample.user_id == user_id,
                RespirationSample.record_date == target_date
            ).delete()

            objects = [
                RespirationSample(
                    user_id=user_id,
                    record_date=target_date,
                    sample_time=data["time"],
                    respiration_rate=data["value"],
                    epoch_ms=data.get("epoch_ms"),
                    source="garmin"
                )
                for data in sorted(seen.values(), key=lambda x: x.get("epoch_ms", 0))
            ]
            db.bulk_save_objects(objects)
            db.commit()
            logger.info(f"{prefix} 保存了 {target_date} 的 {len(objects)} 个呼吸采样点")
            return len(objects)

        except Exception as e:
            logger.warning(f"{prefix} 同步呼吸采样失败: {e}")
            return 0

    def _sync_hrv_readings(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        raw_data: Dict[str, Any]
    ) -> int:
        """HRV 时序 → hrv_readings。

        garminconnect.get_hrv_data() 的 hrvReadings 格式:
        [{"readingTimeGMT": ..., "readingTimeLocal": ..., "hrvValue": int}, ...]
        """
        prefix = self._log_prefix()
        try:
            if not isinstance(raw_data, dict):
                return 0
            hrv_raw = raw_data.get('hrv_raw')
            if not isinstance(hrv_raw, dict):
                return 0
            readings = hrv_raw.get('hrvReadings') or []
            if not isinstance(readings, list) or not readings:
                return 0

            from app.models.garmin_timeseries import HrvReading
            from datetime import time as dt_time

            seen: Dict[str, dict] = {}
            for item in readings:
                if not isinstance(item, dict):
                    continue
                try:
                    ts_str = item.get('readingTimeLocal') or item.get('readingTimeGMT')
                    hrv_val = item.get('hrvValue') or item.get('value')
                    if not ts_str or hrv_val is None:
                        continue
                    dt = datetime.fromisoformat(str(ts_str).rstrip('Z').split('.')[0])
                    key = f"{dt.hour:02d}:{dt.minute:02d}"
                    if key not in seen:
                        seen[key] = {
                            "time": dt_time(dt.hour, dt.minute),
                            "value": float(hrv_val),
                            "epoch_ms": int(dt.timestamp() * 1000),
                            "type": "5min_avg",
                        }
                except (ValueError, TypeError, OSError):
                    continue

            # Also store nightly avg if present (from hrvSummary)
            summary = hrv_raw.get('hrvSummary') or {}
            nightly_avg = summary.get('lastNightAvg')
            nightly_5min_high = summary.get('lastNight5MinHigh')
            if nightly_avg is not None:
                # 单独存一条 nightly 类型（用 record_date 午夜作为 reading_time placeholder）
                pass  # 不重复存，hrvReadings 已够；可选以后加

            if not seen:
                return 0

            db.query(HrvReading).filter(
                HrvReading.user_id == user_id,
                HrvReading.record_date == target_date
            ).delete()

            objects = [
                HrvReading(
                    user_id=user_id,
                    record_date=target_date,
                    reading_time=data["time"],
                    hrv_value=data["value"],
                    reading_type=data["type"],
                    epoch_ms=data.get("epoch_ms"),
                    source="garmin"
                )
                for data in sorted(seen.values(), key=lambda x: x.get("epoch_ms", 0))
            ]
            db.bulk_save_objects(objects)
            db.commit()
            logger.info(f"{prefix} 保存了 {target_date} 的 {len(objects)} 条 HRV 读数")
            return len(objects)

        except Exception as e:
            logger.warning(f"{prefix} 同步 HRV 读数失败: {e}")
            return 0

    def _sync_stress_samples(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        raw_data: Dict[str, Any]
    ) -> int:
        """压力逐分钟采样 → stress_samples。

        garminconnect.get_all_day_stress() 的 stressValuesArray 格式:
        [[epochMs, stressValue], ...]
        """
        prefix = self._log_prefix()
        try:
            if not isinstance(raw_data, dict):
                return 0
            stress_raw = raw_data.get('stress')
            if not isinstance(stress_raw, dict):
                return 0
            values = stress_raw.get('stressValuesArray') or []
            if not isinstance(values, list) or not values:
                return 0

            from app.models.garmin_timeseries import StressSample
            from datetime import time as dt_time

            seen: Dict[str, dict] = {}
            for item in values:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        ts_ms = int(item[0])
                        val = int(item[1])
                    else:
                        continue
                    # -1/-2 是 Garmin 的"无数据"标记，仍保留方便后续分析
                    dt = datetime.fromtimestamp(ts_ms / 1000)
                    key = f"{dt.hour:02d}:{dt.minute:02d}"
                    if key not in seen:
                        seen[key] = {
                            "time": dt_time(dt.hour, dt.minute),
                            "value": val,
                            "epoch_ms": ts_ms,
                        }
                except (ValueError, TypeError, OSError):
                    continue

            if not seen:
                return 0

            db.query(StressSample).filter(
                StressSample.user_id == user_id,
                StressSample.record_date == target_date
            ).delete()

            objects = [
                StressSample(
                    user_id=user_id,
                    record_date=target_date,
                    sample_time=data["time"],
                    stress_value=data["value"],
                    epoch_ms=data.get("epoch_ms"),
                    source="garmin"
                )
                for data in sorted(seen.values(), key=lambda x: x.get("epoch_ms", 0))
            ]
            db.bulk_save_objects(objects)
            db.commit()
            logger.info(f"{prefix} 保存了 {target_date} 的 {len(objects)} 条压力读数")
            return len(objects)

        except Exception as e:
            logger.warning(f"{prefix} 同步压力读数失败: {e}")
            return 0

    def _sync_devices(self, db: Session, user_id: int) -> int:
        """同步用户 Garmin 设备（电量/最后同步/佩戴时长）→ garmin_devices。"""
        prefix = self._log_prefix()
        try:
            devices = self.get_devices()
            if not devices:
                return 0

            from app.models.garmin_device import GarminDevice

            saved = 0
            for d in devices:
                if not isinstance(d, dict):
                    continue
                device_id = str(d.get('deviceId') or d.get('unitId') or d.get('productNumber') or '')
                if not device_id:
                    continue

                existing = db.query(GarminDevice).filter(
                    GarminDevice.user_id == user_id,
                    GarminDevice.device_id == device_id
                ).first()

                def _parse_ts(s):
                    if not s:
                        return None
                    try:
                        return datetime.fromisoformat(str(s).rstrip('Z').split('.')[0])
                    except (ValueError, TypeError):
                        return None

                fields = dict(
                    unit_id=str(d.get('unitId')) if d.get('unitId') else None,
                    product_number=d.get('productNumber'),
                    model=d.get('displayName') or d.get('model'),
                    display_name=d.get('displayName'),
                    image_url=d.get('imageUrl'),
                    last_sync_time=_parse_ts(d.get('lastSyncTime') or d.get('lastSyncTimestamp')),
                    last_used_time=_parse_ts(d.get('lastUsedTime') or d.get('lastUsedTimestamp')),
                    battery_level=d.get('batteryLevel') if isinstance(d.get('batteryLevel'), int) else None,
                    battery_status=d.get('batteryStatus'),
                    firmware_version=d.get('firmwareVersion') or d.get('swVersion'),
                    is_primary=bool(d.get('primaryUsage') or d.get('isPrimary')),
                    raw_payload=d,
                )

                if existing:
                    for k, v in fields.items():
                        if v is not None:
                            setattr(existing, k, v)
                else:
                    db.add(GarminDevice(user_id=user_id, device_id=device_id, **fields))
                saved += 1

            db.commit()
            logger.info(f"{prefix} 同步了 {saved} 个 Garmin 设备")
            return saved

        except Exception as e:
            logger.warning(f"{prefix} 同步设备失败: {e}")
            return 0

    def _sync_body_composition(self, db: Session, user_id: int, target_date: date) -> int:
        """体成分（Garmin Index 秤）→ 写入现有 weight_records。

        Garmin Index 可能一天多次测量，这里用最近一次。
        """
        prefix = self._log_prefix()
        try:
            bc = self.get_body_composition(target_date)
            if not isinstance(bc, dict):
                return 0
            total_avg = bc.get('totalAverage') or {}
            if not isinstance(total_avg, dict):
                return 0

            weight_kg = total_avg.get('weight')
            if weight_kg is None:
                return 0
            weight_kg = float(weight_kg) / 1000.0 if weight_kg > 1000 else float(weight_kg)

            from app.models.weight import WeightRecord

            existing = db.query(WeightRecord).filter(
                WeightRecord.user_id == user_id,
                WeightRecord.record_date == target_date,
            ).first()

            fields = dict(
                weight=weight_kg,
                body_fat_percentage=total_avg.get('bodyFat'),
                muscle_mass_kg=total_avg.get('muscleMass'),
                bone_mass_kg=total_avg.get('boneMass'),
                water_percentage=total_avg.get('bodyWater'),
                visceral_fat=int(total_avg.get('visceralFat')) if total_avg.get('visceralFat') is not None else None,
                bmi=total_avg.get('bmi'),
                metabolic_age=int(total_avg.get('metabolicAge')) if total_avg.get('metabolicAge') is not None else None,
                source='garmin_index',
            )
            fields = {k: v for k, v in fields.items() if v is not None}

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                db.add(WeightRecord(user_id=user_id, record_date=target_date, **fields))
            db.commit()
            logger.info(f"{prefix} 保存体成分 {target_date}: {weight_kg}kg")
            return 1

        except Exception as e:
            logger.warning(f"{prefix} 同步体成分失败: {e}")
            return 0

    def _sync_workout_hr_zones(self, db: Session, workout_id: int, garmin_activity_id: int) -> int:
        """单次训练的心率区间分布 → workout_hr_zones。"""
        prefix = self._log_prefix()
        try:
            zones = self.get_activity_hr_in_timezones(garmin_activity_id)
            if not zones:
                return 0

            from app.models.workout_hr_zone import WorkoutHrZone

            db.query(WorkoutHrZone).filter(WorkoutHrZone.workout_id == workout_id).delete()

            objects = []
            for idx, z in enumerate(zones):
                if not isinstance(z, dict):
                    continue
                objects.append(WorkoutHrZone(
                    workout_id=workout_id,
                    zone_index=z.get('zoneNumber') or (idx + 1),
                    zone_name=z.get('zoneName') or f"Zone {idx + 1}",
                    lower_bpm=int(z['zoneLowBoundary']) if z.get('zoneLowBoundary') is not None else None,
                    upper_bpm=int(z['zoneHighBoundary']) if z.get('zoneHighBoundary') is not None else None,
                    seconds_in_zone=int(z.get('secsInZone', 0) or 0),
                ))
            if not objects:
                return 0
            db.bulk_save_objects(objects)
            db.commit()
            logger.info(f"{prefix} workout_id={workout_id} 保存 {len(objects)} 个 HR zones")
            return len(objects)

        except Exception as e:
            logger.warning(f"{prefix} 同步 workout HR zones 失败 (id={garmin_activity_id}): {e}")
            return 0

    def sync_date_range(
        self,
        db: Session,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        批量同步日期范围的数据

        Args:
            db: 数据库会话
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            同步结果统计
        """
        results = []
        errors = []
        current_date = start_date

        while current_date <= end_date:
            try:
                result = self.sync_daily_data(db, user_id, current_date)
                if result:
                    results.append({
                        "date": current_date.isoformat(),
                        "status": "success",
                        "data_id": result.id
                    })
                else:
                    errors.append({
                        "date": current_date.isoformat(),
                        "status": "no_data"
                    })
            except GarminAuthenticationError:
                # 认证错误需要向上传递，让调用者处理
                raise
            except Exception as e:
                errors.append({
                    "date": current_date.isoformat(),
                    "status": "error",
                    "error": str(e)
                })

            current_date += timedelta(days=1)

            # 避免请求过快，添加小延迟（注意：这是同步函数，不能使用asyncio.sleep）
            import time
            time.sleep(0.5)  # 减少延迟时间，提高同步速度

        return {
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors
        }
