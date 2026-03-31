"""Garmin Connect数据收集服务（使用社区库garminconnect）"""
import asyncio
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.schemas.daily_health import GarminDataCreate
import logging

logger = logging.getLogger(__name__)

# Token 缓存有效期（小时）- garth OAuth token 通常有效 24 小时
TOKEN_CACHE_HOURS = 23

try:
    from garminconnect import Garmin
    GARMINCONNECT_AVAILABLE = True
except ImportError:
    GARMINCONNECT_AVAILABLE = False
    logger.warning("garminconnect库未安装，请运行: pip install garminconnect")


class GarminAuthenticationError(Exception):
    """Garmin认证错误，用于标识凭证问题"""
    pass


class GarminLoginLockedError(Exception):
    """Garmin登录被锁定（防止频繁登录）"""
    def __init__(self, message: str, locked_until: datetime):
        super().__init__(message)
        self.locked_until = locked_until


# 登录失败阈值和锁定时间配置
LOGIN_FAIL_THRESHOLD = 2  # 连续失败次数阈值（429 立即触发，其他错误 2 次后锁定）
# 指数退避锁定时间（分钟）：第1次30分钟, 第2次2小时, 第3次8小时, 第4次+24小时
LOGIN_LOCK_MINUTES_SCHEDULE = [30, 120, 480, 1440]


class GarminMFARequiredError(Exception):
    """Garmin需要两步验证"""
    def __init__(self, message: str, client_state: dict):
        super().__init__(message)
        self.client_state = client_state


# 全局 MFA 会话存储（用于跨请求保持 client 对象）
# 格式: {session_id: {"client": Garmin, "client_state": dict, "expires": timestamp}}
_mfa_sessions: Dict[str, Any] = {}

def _cleanup_expired_mfa_sessions():
    """清理过期的 MFA 会话"""
    import time
    current_time = time.time()
    expired_keys = [k for k, v in _mfa_sessions.items() if v.get("expires", 0) < current_time]
    for k in expired_keys:
        del _mfa_sessions[k]

def _generate_mfa_session_id() -> str:
    """生成 MFA 会话 ID"""
    import uuid
    return str(uuid.uuid4())


def _ensure_display_name_for_client(client, email: str) -> bool:
    """
    确保 client 的 display_name 已设置，尝试多种方式获取
    
    这是一个独立函数，用于 verify_mfa_with_session 等场景
    
    Args:
        client: Garmin client 对象
        email: 用户邮箱
        
    Returns:
        bool: 是否成功获取 display_name
    """
    if client.display_name:
        return True
    
    # 方法1: 尝试 userprofile API
    try:
        prof = client.garth.connectapi("/userprofile-service/userprofile/profile")
        if prof and isinstance(prof, dict):
            client.display_name = prof.get("displayName") or prof.get("userName")
            client.full_name = prof.get("fullName")
            if client.display_name:
                logger.info(f"[MFA] 从 userprofile API 获取 display_name: {client.display_name}")
                return True
    except Exception as e:
        logger.debug(f"[MFA] userprofile API 失败: {e}")
    
    # 方法2: 尝试 socialProfile API
    try:
        social = client.garth.connectapi("/userprofile-service/socialProfile")
        if social and isinstance(social, dict):
            client.display_name = social.get("displayName") or social.get("userName")
            client.full_name = social.get("fullName")
            if client.display_name:
                logger.info(f"[MFA] 从 socialProfile API 获取 display_name: {client.display_name}")
                return True
    except Exception as e:
        logger.debug(f"[MFA] socialProfile API 失败: {e}")
    
    # 方法3: 尝试从 garth 的 profile 属性获取
    try:
        if hasattr(client.garth, 'profile') and client.garth.profile:
            profile = client.garth.profile
            client.display_name = getattr(profile, 'display_name', None) or getattr(profile, 'email', None)
            if client.display_name:
                logger.info(f"[MFA] 从 garth.profile 获取 display_name: {client.display_name}")
                return True
    except Exception as e:
        logger.debug(f"[MFA] garth.profile 获取失败: {e}")
    
    # 方法4: 尝试调用 get_full_name()
    try:
        full_name = client.get_full_name()
        if full_name:
            client.display_name = full_name
            logger.info(f"[MFA] 从 get_full_name() 获取 display_name: {client.display_name}")
            return True
    except Exception as e:
        logger.debug(f"[MFA] get_full_name() 失败: {e}")
    
    # 方法5: 从邮箱地址提取用户名作为后备
    try:
        email_username = email.split('@')[0]
        if email_username:
            client.display_name = email_username
            logger.warning(f"[MFA] 使用邮箱用户名作为 display_name: {client.display_name}")
            return True
    except Exception as e:
        logger.debug(f"[MFA] 邮箱提取失败: {e}")
    
    logger.error(f"[MFA] 无法获取 display_name，部分 API 可能无法正常工作")
    return False


def verify_mfa_with_session(session_id: str, mfa_code: str) -> Dict[str, Any]:
    """
    使用 session_id 和 MFA 验证码完成登录
    
    这是一个模块级函数，用于处理 MFA 验证流程。
    因为 client 对象需要在请求之间保持，所以使用全局 session 存储。
    
    Args:
        session_id: test_connection_with_mfa 返回的 session_id
        mfa_code: 用户输入的 MFA 验证码
        
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "email": str (如果成功),
            "is_cn": bool (如果成功)
        }
    """
    import time
    
    # 清理过期会话
    _cleanup_expired_mfa_sessions()
    
    # 查找会话
    if session_id not in _mfa_sessions:
        logger.warning(f"MFA session not found: {session_id}")
        return {
            "success": False,
            "message": "❌ 验证会话已过期，请重新测试连接。"
        }
    
    session = _mfa_sessions[session_id]
    
    # 检查是否过期
    if session.get("expires", 0) < time.time():
        del _mfa_sessions[session_id]
        return {
            "success": False,
            "message": "❌ 验证会话已过期，请重新测试连接。"
        }
    
    client = session.get("client")
    client_state = session.get("client_state")
    email = session.get("email")
    is_cn = session.get("is_cn")
    
    if not client or not client_state:
        del _mfa_sessions[session_id]
        return {
            "success": False,
            "message": "❌ 会话数据无效，请重新测试连接。"
        }
    
    try:
        # 使用验证码恢复登录
        client.resume_login(client_state, mfa_code)
        
        # 重要：MFA验证后需要手动加载 profile 来获取 display_name
        # 否则后续的 API 调用会因为 display_name 为 None 而失败
        _ensure_display_name_for_client(client, email)
        
        server_type = "中国版" if is_cn else "国际版"
        logger.info(f"[MFA] Garmin {server_type} ({email}) MFA 验证成功, display_name={client.display_name}")
        
        # 不要立即删除会话，标记为已认证，并延长过期时间（10分钟）
        # 这样后续同步可以复用已认证的client
        import time
        _mfa_sessions[session_id] = {
            "client": client,
            "client_state": client_state,
            "email": email,
            "is_cn": is_cn,
            "authenticated": True,  # 标记为已认证
            "expires": time.time() + 600  # 10分钟后过期
        }
        
        return {
            "success": True,
            "message": "✅ 验证成功！Garmin账号连接成功，可以保存凭证了。",
            "email": email,
            "is_cn": is_cn,
            "session_id": session_id  # 返回session_id，以便后续复用
        }
        
    except Exception as e:
        error_msg = str(e).lower()
        
        if 'invalid' in error_msg or 'incorrect' in error_msg or 'wrong' in error_msg:
            # 验证码错误，保留会话供重试
            return {
                "success": False,
                "message": "❌ 验证码错误！请检查并重新输入。"
            }
        
        # 其他错误，清理会话
        del _mfa_sessions[session_id]
        logger.error(f"[MFA] MFA 验证失败: {e}")
        return {
            "success": False,
            "message": f"❌ 验证失败: {str(e)}"
        }


def probe_sso_availability(is_cn: bool = False, timeout: int = 10) -> bool:
    """
    轻量级探测 Garmin SSO 是否可用（GET 请求，不会触发登录）

    用于在调度器中，当 DB 锁定到期后，先探测 SSO 是否还在限流，
    避免直接尝试登录导致再次触发 429 并延长锁定。

    Args:
        is_cn: 是否探测中国版 SSO
        timeout: 请求超时秒数

    Returns:
        True 表示 SSO 可用（返回 200），False 表示仍在限流或不可达
    """
    import requests

    sso_url = "https://sso.garmin.cn/sso/signin" if is_cn else "https://sso.garmin.com/sso/signin"

    try:
        resp = requests.get(sso_url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 429:
            logger.info(f"🔍 SSO 探测: {sso_url} 返回 429，仍在限流中")
            return False
        logger.info(f"🔍 SSO 探测: {sso_url} 返回 {resp.status_code}，SSO 可用")
        return True
    except Exception as e:
        logger.warning(f"🔍 SSO 探测失败 ({sso_url}): {e}")
        return False


class GarminConnectService:
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
    
    def _save_session_to_db(self, db: Session) -> bool:
        """
        保存 garth session 到数据库，避免频繁登录
        
        Args:
            db: 数据库会话
            
        Returns:
            bool: 是否保存成功
        """
        if not self.user_id or not self.client or not hasattr(self.client, 'garth'):
            return False
        
        prefix = self._log_prefix()
        
        try:
            from app.models.user import GarminCredential
            
            # 使用 garth 的 dumps 方法序列化 session
            with tempfile.TemporaryDirectory() as tmpdir:
                self.client.garth.dump(tmpdir)
                
                # 读取所有 token 文件
                session_data = {}
                for filename in ['oauth1_token.json', 'oauth2_token.json']:
                    filepath = os.path.join(tmpdir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, 'r') as f:
                            session_data[filename] = json.load(f)
                
                if not session_data:
                    logger.warning(f"{prefix} garth session 数据为空，无法保存")
                    return False
                
                # 保存到数据库
                cred = db.query(GarminCredential).filter(
                    GarminCredential.user_id == self.user_id
                ).first()
                
                if cred:
                    cred.garth_session = json.dumps(session_data)
                    cred.session_expires_at = datetime.utcnow() + timedelta(hours=TOKEN_CACHE_HOURS)
                    db.commit()
                    logger.info(f"{prefix} ✅ garth session 已缓存到数据库")
                    return True
                    
        except Exception as e:
            logger.warning(f"{prefix} 保存 garth session 失败: {e}")
            db.rollback()
        
        return False
    
    def _load_session_from_db(self, db: Session) -> bool:
        """
        从数据库加载缓存的 garth session
        
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
                logger.debug(f"{prefix} 数据库中无缓存的 garth session")
                return False
            
            # 检查是否过期（兼容 timezone-aware 和 naive datetime）
            if cred.session_expires_at:
                exp = cred.session_expires_at
                if hasattr(exp, 'tzinfo') and exp.tzinfo is not None:
                    exp = exp.replace(tzinfo=None)
                if exp < datetime.utcnow():
                    logger.info(f"{prefix} 缓存的 garth session 已过期")
                    return False
            
            # 解析 session 数据
            session_data = json.loads(cred.garth_session)
            
            # 使用 garth 恢复 session
            with tempfile.TemporaryDirectory() as tmpdir:
                # 写入 token 文件
                for filename, data in session_data.items():
                    filepath = os.path.join(tmpdir, filename)
                    with open(filepath, 'w') as f:
                        json.dump(data, f)
                
                # 创建 Garmin 客户端并恢复 session
                self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
                self.client.garth.load(tmpdir)
                
                # 验证 session 是否有效：检查 token 过期时间而非调用已废弃的 API
                if self.client.garth.oauth2_token:
                    try:
                        token = self.client.garth.oauth2_token
                        # 检查 token 是否过期（garth token 有 expires_at 属性）
                        token_expired = False
                        if hasattr(token, 'expires_at') and token.expires_at:
                            exp_at = token.expires_at
                            if isinstance(exp_at, (int, float)):
                                # Unix timestamp
                                import time
                                token_expired = time.time() >= exp_at
                            elif hasattr(exp_at, 'tzinfo'):
                                now = datetime.now(tz=exp_at.tzinfo) if exp_at.tzinfo else datetime.now()
                                token_expired = now >= exp_at
                            else:
                                token_expired = False

                        if token_expired:
                            logger.info(f"{prefix} oauth2_token 已过期，尝试用 oauth1 refresh...")
                            try:
                                self.client.garth.refresh_oauth2()
                                logger.info(f"{prefix} ✅ oauth2_token refresh 成功，无需重新登录")
                                # refresh 成功后重新保存到 DB
                                self._save_session_to_db(db)
                            except Exception as refresh_err:
                                logger.warning(f"{prefix} oauth2 refresh 失败: {refresh_err}")
                                self._authenticated = False
                                return False

                        # token 有效或已 refresh，验证连通性
                        self.client.garth.connectapi("/usersummary-service/usersummary/daily/" +
                                                      date.today().isoformat())
                        self._ensure_display_name()
                        self._authenticated = True
                        logger.info(f"{prefix} ✅ 从数据库加载 garth session 成功，无需重新登录")
                        return True
                    except Exception as e:
                        logger.warning(f"{prefix} 缓存的 session 无效: {e}")
                        self._authenticated = False
                        return False
                        
        except Exception as e:
            logger.warning(f"{prefix} 加载 garth session 失败: {e}")
        
        return False
    
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
                logger.info(f"{self._log_prefix()} 已清除缓存的 garth session")
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
                now = datetime.utcnow()
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

                is_rate_limited = '429' in (error_msg or '') or 'Too Many Requests' in (error_msg or '')
                is_cloudflare = 'cloudflare' in (error_msg or '').lower() or 'challenge' in (error_msg or '').lower()

                if is_rate_limited or is_cloudflare:
                    # Cloudflare/429: 短锁定但不累加 error_count（不是密码错误）
                    lock_minutes = 30
                    lock_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
                    cred.login_locked_until = lock_until
                    # 保持 credentials_valid=True（密码没错，只是被限流）
                    logger.warning(
                        f"{prefix} ⚠️ Cloudflare/429 限流，锁定 {lock_minutes} 分钟（不累加错误计数）"
                    )
                else:
                    # 真正的登录失败（密码错、账号问题等）
                    cred.error_count = (cred.error_count or 0) + 1
                    cred.credentials_valid = False
                    if cred.error_count >= LOGIN_FAIL_THRESHOLD:
                        lock_index = min(cred.error_count - 1, len(LOGIN_LOCK_MINUTES_SCHEDULE) - 1)
                        lock_minutes = LOGIN_LOCK_MINUTES_SCHEDULE[lock_index]
                        lock_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
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
        """
        确保 display_name 已设置，尝试多种方式获取
        
        Returns:
            bool: 是否成功获取 display_name
        """
        prefix = self._log_prefix()
        
        if self.client.display_name:
            return True
        
        # 方法1: 尝试 userprofile API
        try:
            prof = self.client.garth.connectapi("/userprofile-service/userprofile/profile")
            if prof and isinstance(prof, dict):
                self.client.display_name = prof.get("displayName") or prof.get("userName")
                self.client.full_name = prof.get("fullName")
                if self.client.display_name:
                    logger.info(f"{prefix} 从 userprofile API 获取 display_name: {self.client.display_name}")
                    return True
        except Exception as e:
            logger.debug(f"{prefix} userprofile API 失败: {e}")
        
        # 方法2: 尝试 socialProfile API
        try:
            social = self.client.garth.connectapi("/userprofile-service/socialProfile")
            if social and isinstance(social, dict):
                self.client.display_name = social.get("displayName") or social.get("userName")
                self.client.full_name = social.get("fullName")
                if self.client.display_name:
                    logger.info(f"{prefix} 从 socialProfile API 获取 display_name: {self.client.display_name}")
                    return True
        except Exception as e:
            logger.debug(f"{prefix} socialProfile API 失败: {e}")
        
        # 方法3: 尝试从 garth 的 profile 属性获取
        try:
            if hasattr(self.client.garth, 'profile') and self.client.garth.profile:
                profile = self.client.garth.profile
                self.client.display_name = getattr(profile, 'display_name', None) or getattr(profile, 'email', None)
                if self.client.display_name:
                    logger.info(f"{prefix} 从 garth.profile 获取 display_name: {self.client.display_name}")
                    return True
        except Exception as e:
            logger.debug(f"{prefix} garth.profile 获取失败: {e}")
        
        # 方法4: 尝试调用 get_full_name()
        try:
            full_name = self.client.get_full_name()
            if full_name:
                self.client.display_name = full_name
                logger.info(f"{prefix} 从 get_full_name() 获取 display_name: {self.client.display_name}")
                return True
        except Exception as e:
            logger.debug(f"{prefix} get_full_name() 失败: {e}")
        
        # 方法5: 从邮箱地址提取用户名作为后备
        try:
            email_username = self.email.split('@')[0]
            if email_username:
                self.client.display_name = email_username
                logger.warning(f"{prefix} 使用邮箱用户名作为 display_name: {self.client.display_name}")
                return True
        except Exception as e:
            logger.debug(f"{prefix} 邮箱提取失败: {e}")
        
        logger.error(f"{prefix} 无法获取 display_name，部分 API 可能无法正常工作")
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

        # 1. 优先尝试从数据库加载缓存的 session（即使被锁定也能用 session）
        if db and self.user_id and not self._authenticated:
            if self._load_session_from_db(db):
                logger.info(f"{prefix} ✅ 使用缓存的 OAuth Token，避免重新登录")
                return

        # 0. 检查是否被锁定（仅在没有缓存 session、需要 SSO 登录时才阻止）
        if db and self.user_id:
            locked_until = self._check_login_lock(db)
            if locked_until:
                locked_naive = locked_until.replace(tzinfo=None) if locked_until.tzinfo else locked_until
                remaining_minutes = int((locked_naive - datetime.utcnow()).total_seconds() / 60) + 1
                error_msg = f"⏳ 登录已被暂停，请 {remaining_minutes} 分钟后再试。连续登录失败会导致 Garmin 账号被锁定，请先确认密码正确。"
                logger.warning(f"{prefix} {error_msg}")
                raise GarminLoginLockedError(error_msg, locked_until)
        
        # 2. 如果有MFA会话ID，尝试复用已认证的client
        if self._mfa_session_id and not self._authenticated:
            _cleanup_expired_mfa_sessions()
            logger.info(f"{prefix} 尝试复用MFA会话: {self._mfa_session_id}")
            if self._mfa_session_id in _mfa_sessions:
                session = _mfa_sessions[self._mfa_session_id]
                logger.info(f"{prefix} 找到MFA会话: authenticated={session.get('authenticated')}, email={session.get('email')}, 当前email={self.email}")
                if session.get("authenticated") and session.get("email") == self.email:
                    # 复用已认证的client
                    self.client = session.get("client")
                    if self.client and hasattr(self.client, 'garth') and self.client.garth.oauth2_token:
                        # 确保 display_name 已设置
                        self._ensure_display_name()
                        
                        self._authenticated = True
                        server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                        logger.info(f"{prefix} ✅ 成功复用已认证的Garmin会话 - {server_type}, display_name={self.client.display_name}")
                        
                        # 保存 session 到数据库
                        if db:
                            self._save_session_to_db(db)
                        return
                    else:
                        logger.warning(f"{prefix} MFA会话中的client无效或没有oauth2_token")
                else:
                    logger.warning(f"{prefix} MFA会话未认证或email不匹配")
            else:
                logger.warning(f"{prefix} MFA会话不存在或已过期: {self._mfa_session_id}")
        
        # 3. 重新登录
        if not self._authenticated or self.client is None:
            try:
                # 创建支持 MFA 提前返回的客户端
                self.client = Garmin(
                    self.email, 
                    self.password, 
                    is_cn=self.is_cn,
                    return_on_mfa=True  # 需要 MFA 时提前返回
                )
                
                result = self.client.login()
                
                # 检查是否需要 MFA
                if result and isinstance(result, tuple) and len(result) >= 2:
                    first_element = result[0]
                    second_element = result[1]
                    
                    # 检查是否是 MFA 需要的返回格式
                    if first_element == "needs_mfa" and isinstance(second_element, dict):
                        import time
                        
                        # 清理过期会话
                        _cleanup_expired_mfa_sessions()
                        
                        # 生成会话 ID 并存储 client 和 client_state
                        session_id = _generate_mfa_session_id()
                        _mfa_sessions[session_id] = {
                            "client": self.client,
                            "client_state": second_element,
                            "email": self.email,
                            "is_cn": self.is_cn,
                            "expires": time.time() + 300  # 5分钟过期
                        }
                        
                        self._mfa_client_state = second_element
                        server_type = "中国版" if self.is_cn else "国际版"
                        logger.warning(f"{prefix} Garmin {server_type} 需要两步验证，session_id: {session_id}")
                        raise GarminMFARequiredError(
                            f"🔐 Garmin账号需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。会话ID: {session_id}",
                            {"session_id": session_id, "client_state": second_element}
                        )
                    
                    # 正常登录成功返回 (oauth1_token, oauth2_token)
                    if self.client.garth.oauth2_token:
                        # 确保 display_name 已设置（使用 return_on_mfa=True 时可能未加载 profile）
                        self._ensure_display_name()

                        self._authenticated = True
                        server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                        logger.info(f"{prefix} Garmin Connect登录成功 - {server_type}, display_name={self.client.display_name}")

                        # 🔑 登录成功后缓存 session 到数据库，避免下次重新登录
                        if db:
                            self._save_session_to_db(db)
                            self._reset_login_failure(db)  # 重置失败计数
                        return

                # 如果没有返回tuple，可能是旧版本的库，使用原来的方式
                if not self._authenticated:
                    # 如果没有oauth2_token，尝试重新登录
                    if not hasattr(self.client, 'garth') or not self.client.garth.oauth2_token:
                        self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
                        self.client.login()
                    self._authenticated = True
                    server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                    logger.info(f"{prefix} Garmin Connect登录成功 - {server_type}")

                    # 🔑 登录成功后缓存 session 到数据库
                    if db:
                        self._save_session_to_db(db)
                        self._reset_login_failure(db)  # 重置失败计数

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
                if db:
                    self._record_login_failure(db, str(e))

                # 将登录失败转换为明确的认证错误
                if any(kw in error_msg for kw in ['login', 'auth', '401', 'unauthorized', 'credential', 'password', 'oauth', 'ticket']):
                    logger.error(f"{prefix} Garmin登录失败: {e}")
                    raise GarminAuthenticationError(f"Garmin登录失败: {e}") from e
                logger.error(f"{prefix} Garmin认证异常: {e}")
                raise
    
    def test_connection_with_mfa(self) -> Dict[str, Any]:
        """
        测试连接，支持两步验证（MFA）
        
        Returns:
            dict: {
                "success": bool,
                "mfa_required": bool,  # 是否需要 MFA
                "client_state": dict,  # 如果需要 MFA，返回客户端状态用于恢复登录
                "message": str
            }
        """
        prefix = self._log_prefix()
        
        # 先尝试复用已认证的会话
        if self._mfa_session_id:
            _cleanup_expired_mfa_sessions()
            logger.info(f"{prefix} test_connection_with_mfa: 尝试复用MFA会话: {self._mfa_session_id}")
            if self._mfa_session_id in _mfa_sessions:
                session = _mfa_sessions[self._mfa_session_id]
                if session.get("authenticated") and session.get("email") == self.email:
                    # 复用已认证的client
                    self.client = session.get("client")
                    if self.client and hasattr(self.client, 'garth') and self.client.garth.oauth2_token:
                        self._authenticated = True
                        server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                        logger.info(f"{prefix} test_connection_with_mfa: ✅ 成功复用已认证的Garmin会话 - {server_type}")
                        return {
                            "success": True,
                            "mfa_required": False,
                            "message": "✅ 已复用认证会话，连接成功"
                        }
                    else:
                        logger.warning(f"{prefix} test_connection_with_mfa: MFA会话中的client无效或没有oauth2_token")
                else:
                    logger.warning(f"{prefix} test_connection_with_mfa: MFA会话未认证或email不匹配")
            else:
                logger.warning(f"{prefix} test_connection_with_mfa: MFA会话不存在或已过期: {self._mfa_session_id}")
        
        try:
            # 创建支持 MFA 提前返回的客户端
            self.client = Garmin(
                self.email, 
                self.password, 
                is_cn=self.is_cn,
                return_on_mfa=True  # 需要 MFA 时提前返回
            )
            
            result = self.client.login()
            
            logger.debug(f"{prefix} Garmin login() 返回结果: type={type(result)}, value={result}")
            
            # 检查是否需要 MFA
            # garth 库在需要 MFA 时返回 ("needs_mfa", {client_state})
            if result and isinstance(result, tuple) and len(result) >= 2:
                first_element = result[0]
                second_element = result[1]
                
                # 检查是否是 MFA 需要的返回格式
                if first_element == "needs_mfa" and isinstance(second_element, dict):
                    import time
                    
                    # 清理过期会话
                    _cleanup_expired_mfa_sessions()
                    
                    # 生成会话 ID 并存储 client 和 client_state
                    session_id = _generate_mfa_session_id()
                    _mfa_sessions[session_id] = {
                        "client": self.client,
                        "client_state": second_element,
                        "email": self.email,
                        "is_cn": self.is_cn,
                        "expires": time.time() + 300  # 5分钟过期
                    }
                    
                    self._mfa_client_state = second_element
                    server_type = "中国版" if self.is_cn else "国际版"
                    logger.info(f"{prefix} Garmin {server_type} 需要两步验证，session_id: {session_id}")
                    return {
                        "success": False,
                        "mfa_required": True,
                        "mfa_session_id": session_id,  # 返回 session_id 而不是 client_state
                        "message": "🔐 需要两步验证！请输入您 Garmin 账号绑定的验证器应用中的验证码。"
                    }
                
                # 正常登录成功返回 (oauth1_token, oauth2_token)
                if self.client.garth.oauth2_token:
                    self._authenticated = True
                    server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                    logger.info(f"{prefix} Garmin Connect {server_type} 登录成功")
                    return {
                        "success": True,
                        "mfa_required": False,
                        "message": "✅ 密码正确！Garmin账号连接成功，可以保存凭证了。"
                    }
                else:
                    # 没有 oauth2_token，可能是其他情况
                    logger.warning(f"{prefix} 登录返回了 tuple 但没有 oauth2_token")
                    return {
                        "success": False,
                        "mfa_required": False,
                        "message": "❌ 登录异常，请重试"
                    }
            
            # 其他情况：登录成功（某些情况下可能不返回 tuple）
            if self.client.garth.oauth2_token:
                self._authenticated = True
                server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                logger.info(f"{prefix} Garmin Connect {server_type} 登录成功")
                return {
                    "success": True,
                    "mfa_required": False,
                    "message": "✅ 密码正确！Garmin账号连接成功，可以保存凭证了。"
                }
            
            # 无法确定状态
            logger.warning(f"{prefix} 登录结果不明确: {result}")
            return {
                "success": False,
                "mfa_required": False,
                "message": "❌ 登录状态不明确，请重试"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            logger.debug(f"{prefix} 登录异常: {e}")
            
            # 检查是否需要 MFA（某些版本的库可能通过异常表示需要 MFA）
            if 'mfa' in error_msg or 'two-factor' in error_msg or 'verification' in error_msg:
                # 获取 client_state
                client_state = None
                if self.client and hasattr(self.client, 'garth'):
                    client_state = getattr(self.client.garth, '_client_state', None)
                
                if client_state:
                    self._mfa_client_state = client_state
                    return {
                        "success": False,
                        "mfa_required": True,
                        "client_state": client_state,
                        "message": "🔐 需要两步验证！请输入验证码。"
                    }
            
            # 检查是否需要设置密码
            if 'set password' in error_msg or 'unexpected title' in error_msg:
                return {
                    "success": False,
                    "mfa_required": False,
                    "message": "⚠️ Garmin账号需要设置密码！请先访问 connect.garmin.com 登录并完成密码设置。"
                }
            
            # 认证错误
            if any(kw in error_msg for kw in ['401', 'unauthorized', 'credential', 'password', 'login', 'auth']):
                return {
                    "success": False,
                    "mfa_required": False,
                    "message": "❌ 密码错误或账号无效！请检查邮箱和密码是否正确。"
                }
            
            logger.error(f"{prefix} 测试连接失败: {e}")
            return {
                "success": False,
                "mfa_required": False,
                "message": f"❌ 连接失败: {str(e)}"
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
                # 如果客户端不存在，需要重新创建
                self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
            
            # 使用验证码恢复登录
            self.client.resume_login(client_state, mfa_code)
            self._authenticated = True
            
            server_type = "中国版" if self.is_cn else "国际版"
            logger.info(f"{prefix} Garmin {server_type} MFA 验证成功")
            
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
            
            logger.error(f"{prefix} MFA 验证失败: {e}")
            return {
                "success": False,
                "message": f"❌ 验证失败: {str(e)}"
            }


    def get_user_summary(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取指定日期的每日摘要数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            包含所有健康数据的字典，如果失败返回None
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            
            # 使用get_user_summary获取每日摘要（garminconnect库的实际方法名）
            summary = self.client.get_user_summary(target_date.isoformat())
            
            if summary:
                logger.info(f"{prefix} 成功获取 {target_date} 的Garmin数据")
                return summary
            else:
                logger.warning(f"{prefix} 未找到 {target_date} 的数据")
                return None
                
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取Garmin数据失败: {str(e)}")
            return None
    
    def get_sleep_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取睡眠数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            睡眠数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            sleep_data = self.client.get_sleep_data(target_date.isoformat())
            if sleep_data:
                logger.info(f"{prefix} 获取 {target_date} 的睡眠数据成功，类型: {type(sleep_data).__name__}")
            else:
                logger.warning(f"{prefix} 获取 {target_date} 的睡眠数据为空")
            return sleep_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取睡眠数据失败: {str(e)}")
            return None
    
    def get_heart_rates(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取心率数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            心率数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            hr_data = self.client.get_heart_rates(target_date.isoformat())
            return hr_data
        except GarminAuthenticationError:
            # 认证错误需要传递出去
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取心率数据失败: {str(e)}")
            return None
    
    def get_body_battery(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取身体电量数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            身体电量数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            battery_data = self.client.get_body_battery(target_date.isoformat())
            return battery_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取身体电量数据失败: {str(e)}")
            return None
    
    def get_spo2_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取血氧饱和度数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            血氧数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            spo2_data = self.client.get_spo2_data(target_date.isoformat())
            if spo2_data:
                logger.info(f"{prefix} 获取 {target_date} 的血氧数据成功，类型: {type(spo2_data).__name__}")
                if isinstance(spo2_data, dict):
                    logger.debug(f"{prefix} 血氧数据键: {list(spo2_data.keys())}")
            else:
                logger.debug(f"{prefix} 获取 {target_date} 的血氧数据为空")
            return spo2_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取血氧数据失败: {str(e)}")
            return None
    
    def get_respiration_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取呼吸数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            呼吸数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            resp_data = self.client.get_respiration_data(target_date.isoformat())
            if resp_data:
                logger.info(f"{prefix} 获取 {target_date} 的呼吸数据成功，类型: {type(resp_data).__name__}")
                if isinstance(resp_data, dict):
                    logger.debug(f"{prefix} 呼吸数据键: {list(resp_data.keys())}")
            else:
                logger.debug(f"{prefix} 获取 {target_date} 的呼吸数据为空")
            return resp_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取呼吸数据失败: {str(e)}")
            return None
    
    def get_max_metrics(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取最大摄氧量(VO2Max)和健身年龄等指标
        
        Args:
            target_date: 目标日期
            
        Returns:
            最大指标数据字典，包含 vo2MaxRunning, vo2MaxCycling, fitnessAge 等
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            max_metrics = self.client.get_max_metrics(target_date.isoformat())
            if max_metrics:
                logger.info(f"{prefix} 获取 {target_date} 的最大摄氧量数据成功，类型: {type(max_metrics).__name__}")
                if isinstance(max_metrics, dict):
                    # 记录关键字段
                    vo2max = max_metrics.get('generic', {}).get('vo2MaxPreciseValue') or max_metrics.get('vo2MaxValue')
                    fitness_age = max_metrics.get('generic', {}).get('fitnessAge')
                    logger.info(f"{prefix} VO2Max={vo2max}, 健身年龄={fitness_age}")
            else:
                logger.debug(f"{prefix} 获取 {target_date} 的最大摄氧量数据为空")
            return max_metrics
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取最大摄氧量数据失败: {str(e)}")
            return None
    
    def get_stress_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取压力数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            压力数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            # 使用get_all_day_stress获取压力数据（garminconnect库的实际方法名）
            stress_data = self.client.get_all_day_stress(target_date.isoformat())
            return stress_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取压力数据失败: {str(e)}")
            return None
    
    def get_all_daily_data(self, target_date: date) -> Dict[str, Any]:
        """
        获取指定日期的所有数据（汇总）
        
        Args:
            target_date: 目标日期
            
        Returns:
            包含所有数据的字典
        """
        result = {}
        
        # 获取用户摘要（包含大部分数据）
        summary = self.get_user_summary(target_date)
        if summary:
            if isinstance(summary, dict):
                result.update(summary)
                logger.debug(f"从get_user_summary获取的数据键: {list(summary.keys())[:20]}")
            else:
                logger.warning(f"get_user_summary返回的不是字典类型: {type(summary)}")
        else:
            logger.warning(f"[用户 {self.user_id}] get_user_summary返回空，将依赖其他API和活动数据")
        
        # 获取睡眠数据（优先使用独立API，数据更详细）
        sleep_data = self.get_sleep_data(target_date)
        if sleep_data:
            result['sleep'] = sleep_data
            if isinstance(sleep_data, dict):
                logger.debug(f"从get_sleep_data获取的数据键: {list(sleep_data.keys())[:20]}")
            elif isinstance(sleep_data, list):
                logger.debug(f"从get_sleep_data获取的是列表，长度: {len(sleep_data)}")
            else:
                logger.debug(f"从get_sleep_data获取的数据类型: {type(sleep_data)}")
        elif isinstance(summary, dict) and ('sleepScore' in summary or 'sleepScores' in summary):
            # 如果独立API没有数据，但summary中有睡眠数据，使用summary的
            logger.info("使用summary中的睡眠数据")
        
        # 获取心率数据（优先使用独立API）
        hr_data = self.get_heart_rates(target_date)
        if hr_data:
            result['heart_rate'] = hr_data
            if isinstance(hr_data, dict):
                logger.debug(f"从get_heart_rates获取的数据键: {list(hr_data.keys())[:20]}")
            elif isinstance(hr_data, list):
                logger.debug(f"从get_heart_rates获取的是列表，长度: {len(hr_data)}")
            else:
                logger.debug(f"从get_heart_rates获取的数据类型: {type(hr_data)}")
        elif isinstance(summary, dict) and ('averageHeartRate' in summary or 'avgHeartRate' in summary):
            # 如果独立API没有数据，但summary中有心率数据，使用summary的
            logger.info("使用summary中的心率数据")
        
        # 获取身体电量
        battery_data = self.get_body_battery(target_date)
        if battery_data:
            result['body_battery'] = battery_data
            if isinstance(battery_data, list):
                logger.debug(f"从get_body_battery获取的是列表，长度: {len(battery_data)}")
            elif isinstance(battery_data, dict):
                logger.debug(f"从get_body_battery获取的数据键: {list(battery_data.keys())[:20]}")
        
        # 获取压力数据
        stress_data = self.get_stress_data(target_date)
        if stress_data:
            result['stress'] = stress_data
            if isinstance(stress_data, list):
                logger.debug(f"从get_stress_data获取的是列表，长度: {len(stress_data)}")
            elif isinstance(stress_data, dict):
                logger.debug(f"从get_stress_data获取的数据键: {list(stress_data.keys())[:20]}")
        
        # 获取血氧数据
        spo2_data = self.get_spo2_data(target_date)
        if spo2_data:
            result['spo2'] = spo2_data
            if isinstance(spo2_data, list):
                logger.debug(f"从get_spo2_data获取的是列表，长度: {len(spo2_data)}")
            elif isinstance(spo2_data, dict):
                logger.debug(f"从get_spo2_data获取的数据键: {list(spo2_data.keys())[:20]}")
        
        # 获取呼吸数据
        resp_data = self.get_respiration_data(target_date)
        if resp_data:
            result['respiration'] = resp_data
            if isinstance(resp_data, list):
                logger.debug(f"从get_respiration_data获取的是列表，长度: {len(resp_data)}")
            elif isinstance(resp_data, dict):
                logger.debug(f"从get_respiration_data获取的数据键: {list(resp_data.keys())[:20]}")
        
        # 获取最大摄氧量和健康年龄数据
        max_metrics = self.get_max_metrics(target_date)
        if max_metrics:
            result['max_metrics'] = max_metrics
            if isinstance(max_metrics, dict):
                logger.info(f"从get_max_metrics获取的数据键: {list(max_metrics.keys())}")
        
        return result
    
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
                hrv_resp = self.client.connectapi(f"/hrv-service/hrv/{target_date}")
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
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"{prefix} 同步Garmin数据失败: {str(e)}")
            logger.error(f"{prefix} 详细错误: {traceback.format_exc()}")
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

