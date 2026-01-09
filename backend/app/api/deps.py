"""API共享依赖"""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.services.auth import auth_service

logger = logging.getLogger(__name__)

# OAuth2 密码流配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """获取当前登录用户（可选）"""
    if not token:
        logger.warning("[Auth] 请求没有携带token")
        return None
    
    # 打印token前20个字符用于调试
    token_preview = token[:20] + "..." if len(token) > 20 else token
    logger.debug(f"[Auth] 收到token: {token_preview}")
    
    payload = auth_service.decode_token(token)
    if not payload:
        logger.warning(f"[Auth] Token解码失败: {token_preview}")
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        logger.warning("[Auth] Token中没有用户ID")
        return None
    
    user = auth_service.get_user_by_id(db, int(user_id))
    if user:
        logger.debug(f"[Auth] 认证成功: 用户 {user.id} ({user.username})")
    else:
        logger.warning(f"[Auth] 用户ID {user_id} 不存在")
    return user


async def get_current_user_required(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """获取当前登录用户（必须登录）"""
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
    return current_user


def get_current_user_id(current_user: User = Depends(get_current_user_required)) -> int:
    """获取当前用户ID"""
    return current_user.id

