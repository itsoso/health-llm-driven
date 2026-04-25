"""Garmin MFA 会话管理 + display_name 兜底获取.

从 garmin_connect.py 抽出. 这部分是模块级状态 (全局 _mfa_sessions dict),
不依赖 GarminConnectService 实例, 自然适合独立模块.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)


# 全局 MFA 会话存储 (用于跨请求保持 client 对象)
# 格式: {session_id: {"client": Garmin, "client_state": dict, "expires": timestamp, ...}}
_mfa_sessions: Dict[str, Any] = {}


def _cleanup_expired_mfa_sessions() -> None:
    """清理过期的 MFA 会话"""
    current_time = time.time()
    expired_keys = [k for k, v in _mfa_sessions.items() if v.get("expires", 0) < current_time]
    for k in expired_keys:
        del _mfa_sessions[k]


def _generate_mfa_session_id() -> str:
    """生成 MFA 会话 ID"""
    return str(uuid.uuid4())


def _ensure_display_name_for_client(client, email: str) -> bool:
    """确保 client 的 display_name 已设置, 尝试多种方式获取.

    用于 verify_mfa_with_session 等场景: MFA 验证完成后, garth 客户端可能还
    没有加载 profile, 后续 API 调用会因 display_name=None 而失败.

    Args:
        client: Garmin client 对象
        email: 用户邮箱 (作为兜底)

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
            client.display_name = (
                getattr(profile, 'display_name', None) or getattr(profile, 'email', None)
            )
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

    logger.error("[MFA] 无法获取 display_name, 部分 API 可能无法正常工作")
    return False


def verify_mfa_with_session(session_id: str, mfa_code: str) -> Dict[str, Any]:
    """使用 session_id 和 MFA 验证码完成登录.

    模块级函数, 用于处理 MFA 验证流程. client 对象需要在请求之间保持,
    所以使用全局 session 存储.

    Args:
        session_id: test_connection_with_mfa 返回的 session_id
        mfa_code: 用户输入的 MFA 验证码

    Returns:
        dict: {
            "success": bool,
            "message": str,
            "email": str (如果成功),
            "is_cn": bool (如果成功),
            "session_id": str (如果成功, 给后续同步复用)
        }
    """
    # 清理过期会话
    _cleanup_expired_mfa_sessions()

    # 查找会话
    if session_id not in _mfa_sessions:
        logger.warning(f"MFA session not found: {session_id}")
        return {"success": False, "message": "❌ 验证会话已过期, 请重新测试连接."}

    session = _mfa_sessions[session_id]

    # 检查是否过期
    if session.get("expires", 0) < time.time():
        del _mfa_sessions[session_id]
        return {"success": False, "message": "❌ 验证会话已过期, 请重新测试连接."}

    client = session.get("client")
    client_state = session.get("client_state")
    email = session.get("email")
    is_cn = session.get("is_cn")

    if not client or not client_state:
        del _mfa_sessions[session_id]
        return {"success": False, "message": "❌ 会话数据无效, 请重新测试连接."}

    try:
        # 使用验证码恢复登录
        client.resume_login(client_state, mfa_code)

        # 重要: MFA 验证后需要手动加载 profile 来获取 display_name
        # 否则后续的 API 调用会因为 display_name 为 None 而失败
        _ensure_display_name_for_client(client, email)

        server_type = "中国版" if is_cn else "国际版"
        logger.info(
            f"[MFA] Garmin {server_type} ({email}) MFA 验证成功, "
            f"display_name={client.display_name}"
        )

        # 不要立即删除会话, 标记为已认证, 并延长过期时间 (10 分钟)
        # 这样后续同步可以复用已认证的 client
        _mfa_sessions[session_id] = {
            "client": client,
            "client_state": client_state,
            "email": email,
            "is_cn": is_cn,
            "authenticated": True,
            "expires": time.time() + 600,
        }

        return {
            "success": True,
            "message": "✅ 验证成功! Garmin 账号连接成功, 可以保存凭证了.",
            "email": email,
            "is_cn": is_cn,
            "session_id": session_id,
        }

    except Exception as e:
        error_msg = str(e).lower()

        if 'invalid' in error_msg or 'incorrect' in error_msg or 'wrong' in error_msg:
            # 验证码错误, 保留会话供重试
            return {"success": False, "message": "❌ 验证码错误! 请检查并重新输入."}

        # 其他错误, 清理会话
        del _mfa_sessions[session_id]
        logger.error(f"[MFA] MFA 验证失败: {e}")
        return {"success": False, "message": f"❌ 验证失败: {str(e)}"}
