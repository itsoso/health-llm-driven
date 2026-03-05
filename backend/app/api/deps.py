"""API共享依赖"""
import hashlib
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.services.auth import auth_service

logger = logging.getLogger(__name__)

# OAuth2 密码流配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """获取当前登录用户（可选）

    认证优先级：
    1. JWT Bearer Token (Authorization: Bearer <jwt>)
    2. X-API-Key 头 (用户 API Key，供 OpenClaw Skills / 外部系统使用)
    """
    # 1. 尝试 JWT 认证
    if token:
        token_preview = token[:20] + "..." if len(token) > 20 else token
        logger.debug(f"[Auth] 收到token: {token_preview}")

        payload = auth_service.decode_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                user = auth_service.get_user_by_id(db, int(user_id))
                if user:
                    logger.debug(f"[Auth] JWT认证成功: 用户 {user.id} ({user.username})")
                    return user
                logger.warning(f"[Auth] 用户ID {user_id} 不存在")
            else:
                logger.warning("[Auth] Token中没有用户ID")
        else:
            logger.warning(f"[Auth] Token解码失败: {token_preview}")

    # 2. Fallback: 尝试 API Key 认证 (X-API-Key 头 或 Bearer token 作为 API Key)
    x_api_key = request.headers.get("x-api-key") or (token if token else None)
    if x_api_key:
        from app.models.user_api_key import UserApiKey
        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        api_key = db.query(UserApiKey).filter(
            UserApiKey.api_key == key_hash,
            UserApiKey.is_active == True
        ).first()
        if api_key:
            user = auth_service.get_user_by_id(db, api_key.user_id)
            if user:
                logger.debug(f"[Auth] API Key认证成功: 用户 {user.id} ({user.username})")
                return user
        key_preview = x_api_key[:8] + "..." if len(x_api_key) > 8 else x_api_key
        logger.warning(f"[Auth] API Key认证失败: {key_preview}")

    if not token and not x_api_key:
        logger.warning("[Auth] 请求没有携带token或API Key")
    return None


async def get_current_user_required(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """获取当前登录用户（必须登录且已审核）"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )
    if not current_user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户尚未通过管理员审核，请等待审核"
        )
    return current_user


def get_current_user_id(current_user: User = Depends(get_current_user_required)) -> int:
    """获取当前用户ID"""
    return current_user.id

