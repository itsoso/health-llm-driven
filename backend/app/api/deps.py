"""API共享依赖"""
import hashlib
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db, set_current_tenant, reset_current_tenant
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
    2. X-API-Key 头 (用户 API Key，供 Agent Skills / 外部系统使用)
    """
    # 1. 尝试 JWT 认证
    if token:
        token_preview = token[:20] + "..." if len(token) > 20 else token
        logger.debug(f"[Auth] 收到token: {token_preview}")

        payload = auth_service.decode_token(token)
        if payload:
            user_id = payload.get("sub")
            acting_as = payload.get("acting_as")
            original_user = payload.get("original_user")

            if user_id:
                # 家庭代管模式：JWT 包含 acting_as 和 original_user
                if acting_as and original_user:
                    target_user = auth_service.get_user_by_id(db, int(acting_as))
                    if target_user:
                        request.state.original_user_id = int(original_user)
                        request.state.is_proxy_mode = True
                        logger.debug(f"[Auth] 家庭代管模式: 原始用户 {original_user} → 代管 {acting_as} ({target_user.name})")
                        return target_user

                # 正常模式
                user = auth_service.get_user_by_id(db, int(user_id))
                if user:
                    request.state.is_proxy_mode = False
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


def tenant_scope(
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> User:
    """租户作用域依赖 —— 设置 RLS 租户上下文, 请求结束 reset。

    放在 get_current_user_required 之后, 把 user.id 注入 current_tenant_id contextvar;
    database.py 的 after_begin 事件据此为 **commit 后新开的** 事务设置 Postgres app.user_id。

    ⚠ 关键(安全评审 required 修复): get_current_user_required 在本 session 上发的 auth 查询
    已**先于本依赖**开了第一个事务, 那次 after_begin 触发时 contextvar 尚为 None → 未设
    app.user_id。若只靠 after_begin, 端点在首个 commit 之前对 genetic_raw 表的查询会因
    RLS current_setting 为 NULL 而返回 0 行(功能打挂 + 边界形同虚设)。故在此对**当前已开
    事务**用 set_config(local=true) 显式补设一次; after_begin 负责后续事务。两者合一覆盖全程。
    RLS policy 在 DB 层强制行级隔离, 应用层 WHERE user_id 仍保留作双保险。
    """
    token = set_current_tenant(user.id)
    # 主路径:把租户写到 session.info —— after_begin 直接从 session 拿,跨 commit 持续,
    # 不依赖 contextvar 跨 context 传播(生产实测 contextvar 传不到 post-commit 事务的
    # after_begin → audit/raw 写被 RLS 拦 500)。
    db.info["app_user_id"] = int(user.id)
    # 当前已开事务(auth 查询所开,after_begin 当时还没租户)显式补设一次;
    # set_config 可参数化、local=true 同事务有效。后续事务由 after_begin + session.info 接力。
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(int(user.id))})
    try:
        yield user
    finally:
        db.info.pop("app_user_id", None)
        reset_current_tenant(token)
