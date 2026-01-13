"""
Garmin 会话管理器 - 防止账户锁定的保护机制

功能：
1. OAuth令牌缓存 - 复用已登录的会话，避免每次都重新登录
2. 用户间随机延迟 - 避免同一时间大量请求
3. 指数退避重试 - 遇到限流时智能等待
4. 账户状态监控 - 检测到锁定风险时自动暂停
"""
import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AccountStatus(Enum):
    """账户状态枚举"""
    NORMAL = "normal"          # 正常
    RATE_LIMITED = "rate_limited"  # 被限流
    LOCKED = "locked"          # 被锁定
    MFA_REQUIRED = "mfa_required"  # 需要MFA
    INVALID_CREDENTIALS = "invalid_credentials"  # 凭证无效


@dataclass
class SessionInfo:
    """会话信息"""
    client: Any                # Garmin client对象
    email: str                 # 账号邮箱
    is_cn: bool               # 是否中国区
    created_at: float         # 创建时间戳
    last_used_at: float       # 最后使用时间戳
    expires_at: float         # 过期时间戳
    request_count: int = 0    # 请求计数


@dataclass
class AccountState:
    """账户状态信息"""
    user_id: int
    email: str
    status: AccountStatus = AccountStatus.NORMAL
    last_error: Optional[str] = None
    last_error_at: Optional[float] = None
    consecutive_errors: int = 0
    rate_limit_until: Optional[float] = None  # 限流解除时间
    lock_until: Optional[float] = None        # 锁定解除时间
    total_requests_today: int = 0
    last_request_date: Optional[str] = None


class GarminSessionManager:
    """
    Garmin 会话管理器
    
    提供以下功能：
    1. OAuth令牌缓存 - 复用已认证的会话
    2. 用户间随机延迟 - 分散请求时间
    3. 指数退避重试 - 智能处理限流
    4. 账户状态监控 - 自动暂停风险账户
    """
    
    # 配置常量
    SESSION_TTL_HOURS = 12          # 会话有效期（小时）
    MAX_REQUESTS_PER_DAY = 50       # 每日最大请求数（保守值）
    MIN_DELAY_SECONDS = 5           # 用户间最小延迟（秒）
    MAX_DELAY_SECONDS = 30          # 用户间最大延迟（秒）
    MAX_CONSECUTIVE_ERRORS = 3      # 最大连续错误次数
    RATE_LIMIT_DURATION_HOURS = 1   # 限流暂停时间（小时）
    LOCK_DURATION_HOURS = 24        # 锁定暂停时间（小时）
    
    # 指数退避配置
    BASE_RETRY_DELAY = 5            # 基础重试延迟（秒）
    MAX_RETRY_DELAY = 300           # 最大重试延迟（秒）
    RETRY_MULTIPLIER = 2            # 重试延迟乘数
    MAX_RETRIES = 3                 # 最大重试次数
    
    def __init__(self):
        # 会话缓存: {email: SessionInfo}
        self._sessions: Dict[str, SessionInfo] = {}
        # 账户状态: {user_id: AccountState}
        self._account_states: Dict[int, AccountState] = {}
        # 锁，防止并发问题
        self._lock = asyncio.Lock()
        
        logger.info("🛡️ Garmin会话管理器已初始化")
    
    def _get_today_str(self) -> str:
        """获取今天的日期字符串"""
        return datetime.now().strftime("%Y-%m-%d")
    
    def get_cached_session(self, email: str) -> Optional[Any]:
        """
        获取缓存的会话（OAuth令牌复用）
        
        Args:
            email: Garmin账号邮箱
            
        Returns:
            Garmin client对象，如果缓存有效的话
        """
        if email not in self._sessions:
            return None
        
        session = self._sessions[email]
        current_time = time.time()
        
        # 检查是否过期
        if current_time >= session.expires_at:
            logger.info(f"📤 会话已过期: {self._mask_email(email)}")
            del self._sessions[email]
            return None
        
        # 更新最后使用时间
        session.last_used_at = current_time
        session.request_count += 1
        
        logger.info(f"♻️ 复用缓存会话: {self._mask_email(email)} (已用 {session.request_count} 次)")
        return session.client
    
    def cache_session(self, email: str, client: Any, is_cn: bool = False):
        """
        缓存会话（保存OAuth令牌）
        
        Args:
            email: Garmin账号邮箱
            client: 已认证的Garmin client对象
            is_cn: 是否中国区
        """
        current_time = time.time()
        expires_at = current_time + (self.SESSION_TTL_HOURS * 3600)
        
        self._sessions[email] = SessionInfo(
            client=client,
            email=email,
            is_cn=is_cn,
            created_at=current_time,
            last_used_at=current_time,
            expires_at=expires_at,
            request_count=1
        )
        
        logger.info(f"💾 缓存新会话: {self._mask_email(email)} (有效期 {self.SESSION_TTL_HOURS} 小时)")
    
    def invalidate_session(self, email: str):
        """
        使会话失效
        
        Args:
            email: Garmin账号邮箱
        """
        if email in self._sessions:
            del self._sessions[email]
            logger.info(f"🗑️ 已清除会话缓存: {self._mask_email(email)}")
    
    def get_account_state(self, user_id: int, email: str) -> AccountState:
        """
        获取账户状态
        
        Args:
            user_id: 用户ID
            email: Garmin账号邮箱
            
        Returns:
            AccountState对象
        """
        if user_id not in self._account_states:
            self._account_states[user_id] = AccountState(
                user_id=user_id,
                email=email
            )
        return self._account_states[user_id]
    
    def can_sync(self, user_id: int, email: str) -> Tuple[bool, str]:
        """
        检查账户是否可以同步（账户状态监控）
        
        Args:
            user_id: 用户ID
            email: Garmin账号邮箱
            
        Returns:
            (可以同步, 原因说明)
        """
        state = self.get_account_state(user_id, email)
        current_time = time.time()
        today = self._get_today_str()
        
        # 重置每日计数
        if state.last_request_date != today:
            state.total_requests_today = 0
            state.last_request_date = today
        
        # 检查是否被锁定
        if state.status == AccountStatus.LOCKED:
            if state.lock_until and current_time < state.lock_until:
                remaining = int((state.lock_until - current_time) / 60)
                return False, f"账户暂停同步中，剩余 {remaining} 分钟"
            else:
                # 锁定已解除
                state.status = AccountStatus.NORMAL
                state.lock_until = None
                state.consecutive_errors = 0
                logger.info(f"🔓 账户锁定已解除: 用户 {user_id}")
        
        # 检查是否被限流
        if state.status == AccountStatus.RATE_LIMITED:
            if state.rate_limit_until and current_time < state.rate_limit_until:
                remaining = int((state.rate_limit_until - current_time) / 60)
                return False, f"API限流中，剩余 {remaining} 分钟"
            else:
                # 限流已解除
                state.status = AccountStatus.NORMAL
                state.rate_limit_until = None
                logger.info(f"✅ API限流已解除: 用户 {user_id}")
        
        # 检查每日请求限制
        if state.total_requests_today >= self.MAX_REQUESTS_PER_DAY:
            return False, f"已达每日请求上限 ({self.MAX_REQUESTS_PER_DAY})"
        
        # 检查连续错误次数
        if state.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
            # 自动触发限流保护
            self._set_rate_limited(state)
            remaining = int((state.rate_limit_until - current_time) / 60)
            return False, f"连续错误过多，自动暂停 {remaining} 分钟"
        
        return True, "正常"
    
    def record_success(self, user_id: int, email: str):
        """
        记录同步成功
        
        Args:
            user_id: 用户ID
            email: Garmin账号邮箱
        """
        state = self.get_account_state(user_id, email)
        state.status = AccountStatus.NORMAL
        state.consecutive_errors = 0
        state.total_requests_today += 1
        state.last_error = None
        state.last_error_at = None
        
        logger.debug(f"✅ 记录成功: 用户 {user_id} (今日请求 {state.total_requests_today})")
    
    def record_error(self, user_id: int, email: str, error: str) -> Tuple[bool, int]:
        """
        记录同步错误，返回是否应该重试
        
        Args:
            user_id: 用户ID
            email: Garmin账号邮箱
            error: 错误信息
            
        Returns:
            (是否应该重试, 建议等待秒数)
        """
        state = self.get_account_state(user_id, email)
        state.consecutive_errors += 1
        state.last_error = error
        state.last_error_at = time.time()
        state.total_requests_today += 1
        
        error_lower = error.lower()
        
        # 检测账户锁定
        if any(kw in error_lower for kw in ['locked', 'blocked', 'suspended', 'banned']):
            state.status = AccountStatus.LOCKED
            state.lock_until = time.time() + (self.LOCK_DURATION_HOURS * 3600)
            self.invalidate_session(email)
            logger.warning(f"🔒 检测到账户可能被锁定: 用户 {user_id}，暂停 {self.LOCK_DURATION_HOURS} 小时")
            return False, 0
        
        # 检测限流
        if any(kw in error_lower for kw in ['rate limit', 'too many', '429', 'throttl']):
            self._set_rate_limited(state)
            self.invalidate_session(email)
            logger.warning(f"⚡ 检测到API限流: 用户 {user_id}，暂停 {self.RATE_LIMIT_DURATION_HOURS} 小时")
            return False, 0
        
        # 检测认证错误（不重试）
        if any(kw in error_lower for kw in ['401', 'unauthorized', 'invalid credential', 'login failed']):
            state.status = AccountStatus.INVALID_CREDENTIALS
            self.invalidate_session(email)
            logger.warning(f"🔑 认证失败: 用户 {user_id}，不重试")
            return False, 0
        
        # 检测MFA需求（不重试）
        if any(kw in error_lower for kw in ['mfa', 'two-factor', 'verification']):
            state.status = AccountStatus.MFA_REQUIRED
            logger.info(f"🔐 需要MFA: 用户 {user_id}，不重试")
            return False, 0
        
        # 其他错误，使用指数退避重试
        if state.consecutive_errors <= self.MAX_RETRIES:
            delay = min(
                self.BASE_RETRY_DELAY * (self.RETRY_MULTIPLIER ** (state.consecutive_errors - 1)),
                self.MAX_RETRY_DELAY
            )
            logger.info(f"⏳ 第 {state.consecutive_errors} 次错误，{delay} 秒后重试: 用户 {user_id}")
            return True, int(delay)
        
        # 超过最大重试次数
        self._set_rate_limited(state)
        logger.warning(f"❌ 超过最大重试次数: 用户 {user_id}，暂停 {self.RATE_LIMIT_DURATION_HOURS} 小时")
        return False, 0
    
    def _set_rate_limited(self, state: AccountState):
        """设置限流状态"""
        state.status = AccountStatus.RATE_LIMITED
        state.rate_limit_until = time.time() + (self.RATE_LIMIT_DURATION_HOURS * 3600)
    
    async def get_random_delay(self) -> float:
        """
        获取用户间随机延迟（避免同一时间大量请求）
        
        Returns:
            延迟秒数
        """
        delay = random.uniform(self.MIN_DELAY_SECONDS, self.MAX_DELAY_SECONDS)
        logger.debug(f"⏱️ 用户间延迟: {delay:.1f} 秒")
        return delay
    
    async def wait_with_jitter(self, base_seconds: float = 0):
        """
        带抖动的等待（用于分散请求）
        
        Args:
            base_seconds: 基础等待时间
        """
        jitter = random.uniform(0, 5)  # 0-5秒随机抖动
        total_wait = base_seconds + jitter
        if total_wait > 0:
            await asyncio.sleep(total_wait)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计数据字典
        """
        return {
            "cached_sessions": len(self._sessions),
            "monitored_accounts": len(self._account_states),
            "accounts_by_status": {
                status.value: len([s for s in self._account_states.values() if s.status == status])
                for status in AccountStatus
            },
            "session_details": [
                {
                    "email": self._mask_email(s.email),
                    "request_count": s.request_count,
                    "age_hours": (time.time() - s.created_at) / 3600,
                    "ttl_hours": (s.expires_at - time.time()) / 3600
                }
                for s in self._sessions.values()
            ]
        }
    
    def cleanup_expired(self):
        """清理过期的会话和状态"""
        current_time = time.time()
        
        # 清理过期会话
        expired_emails = [
            email for email, session in self._sessions.items()
            if current_time >= session.expires_at
        ]
        for email in expired_emails:
            del self._sessions[email]
            logger.debug(f"🧹 清理过期会话: {self._mask_email(email)}")
        
        if expired_emails:
            logger.info(f"🧹 已清理 {len(expired_emails)} 个过期会话")
    
    def _mask_email(self, email: str) -> str:
        """隐藏邮箱中间部分"""
        parts = email.split('@')
        if len(parts) == 2 and len(parts[0]) > 3:
            return parts[0][:2] + '***@' + parts[1]
        return '***'


# 全局单例
_session_manager: Optional[GarminSessionManager] = None


def get_session_manager() -> GarminSessionManager:
    """获取会话管理器单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = GarminSessionManager()
    return _session_manager
