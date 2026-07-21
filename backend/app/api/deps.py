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
from app.services.web_session import (
    WEB_SESSION_AUTH_SENTINEL,
    WEB_SESSION_COOKIE,
    enforce_cookie_request_origin,
)

logger = logging.getLogger(__name__)

API_KEY_ALLOWED_SCOPES = frozenset({"read", "write"})
_API_KEY_ALWAYS_BLOCKED_PATHS = (
    "/api/v1/admin",
    "/api/v1/family",
    "/api/v1/user-api-keys",
    "/api/v1/user-merge",
)
_API_KEY_MUTATION_BLOCKED_PATHS = (
    "/api/v1/auth",
    "/api/v1/family-health/medications",
    "/api/v1/medication",
    "/api/v1/prescriptions",
    "/api/v1/users",
)

# OAuth2 密码流配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def bind_authenticated_tenant(db: Session, user_id: int) -> None:
    """Bind the authenticated tenant to the current and future transactions."""
    uid = int(user_id)
    db.info["app_user_id"] = uid
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT set_config('app.user_id', :uid, true)"),
            {"uid": str(uid)},
        )


def normalize_api_key_scopes(raw_scopes: Optional[str]) -> frozenset[str]:
    """Return the supported, normalized scopes stored on a user API key."""
    if not raw_scopes:
        return frozenset()
    return frozenset(
        scope
        for item in raw_scopes.split(",")
        if (scope := item.strip().lower()) in API_KEY_ALLOWED_SCOPES
    )


def _path_matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _enforce_api_key_request(request: Request, scopes: frozenset[str]) -> None:
    path = request.url.path.rstrip("/") or "/"
    is_mutation = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}

    if any(_path_matches(path, prefix) for prefix in _API_KEY_ALWAYS_BLOCKED_PATHS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该操作不允许使用 API Key",
        )
    if is_mutation and any(
        _path_matches(path, prefix) for prefix in _API_KEY_MUTATION_BLOCKED_PATHS
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该操作不允许使用 API Key",
        )

    required_scope = "write" if is_mutation else "read"
    if required_scope not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API Key 缺少 {required_scope} 权限",
        )


def _resolve_family_proxy_user(
    db: Session,
    *,
    subject: object,
    acting_as: object,
    original_user_id: object,
) -> tuple[User, int]:
    """Revalidate a family proxy grant on every request.

    A proxy JWT is only a short-lived credential, not a durable authorization
    grant. Account status and family membership can change while it is valid.
    """
    from app.models.family import FamilyMember

    try:
        subject_id = int(subject)
        target_user_id = int(acting_as)
        origin_id = int(original_user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="家庭代管授权已失效",
        ) from exc

    if subject_id != target_user_id or origin_id == target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="家庭代管授权已失效",
        )

    original_user = auth_service.get_user_by_id(db, origin_id)
    target_user = auth_service.get_user_by_id(db, target_user_id)
    if (
        not original_user
        or not original_user.is_active
        or not original_user.is_approved
        or not target_user
        or not target_user.is_active
        or not target_user.is_approved
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="家庭代管授权已失效",
        )

    origin_groups = db.query(FamilyMember.family_group_id).filter(
        FamilyMember.user_id == origin_id,
    ).scalar_subquery()
    target_member = db.query(FamilyMember).filter(
        FamilyMember.user_id == target_user_id,
        FamilyMember.family_group_id.in_(origin_groups),
    ).first()
    if not target_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="家庭代管授权已失效",
        )

    origin_member = db.query(FamilyMember).filter(
        FamilyMember.family_group_id == target_member.family_group_id,
        FamilyMember.user_id == origin_id,
    ).first()
    if not origin_member or (
        origin_member.role != "owner" and not target_member.can_edit
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="家庭代管授权已失效",
        )

    return target_user, origin_id


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
    bearer_token = token
    if bearer_token == WEB_SESSION_AUTH_SENTINEL:
        bearer_token = None

    cookie_token = request.cookies.get(WEB_SESSION_COOKIE) if not bearer_token else None
    jwt_token = bearer_token or cookie_token
    is_cookie_auth = bool(cookie_token)
    if is_cookie_auth:
        enforce_cookie_request_origin(request)

    # 1. 尝试 JWT 认证：原生端 Bearer 优先，Web 使用 HttpOnly Cookie。
    if jwt_token:
        logger.debug("[Auth] 收到 JWT 凭证")

        payload = auth_service.decode_token(jwt_token)
        if payload:
            user_id = payload.get("sub")
            acting_as = payload.get("acting_as")
            original_user = payload.get("original_user")

            if user_id:
                # 家庭代管模式：JWT 包含 acting_as 和 original_user
                if acting_as and original_user:
                    target_user, origin_id = _resolve_family_proxy_user(
                        db,
                        subject=user_id,
                        acting_as=acting_as,
                        original_user_id=original_user,
                    )
                    bind_authenticated_tenant(db, target_user.id)
                    request.state.auth_type = "cookie" if is_cookie_auth else "jwt"
                    request.state.api_key_id = None
                    request.state.auth_scopes = frozenset()
                    request.state.original_user_id = origin_id
                    request.state.is_proxy_mode = True
                    logger.debug(
                        "[Auth] 家庭代管认证成功: origin_id=%s target_id=%s",
                        origin_id,
                        target_user.id,
                    )
                    return target_user

                # 正常模式
                user = auth_service.get_user_by_id(db, int(user_id))
                if user:
                    bind_authenticated_tenant(db, user.id)
                    request.state.auth_type = "cookie" if is_cookie_auth else "jwt"
                    request.state.api_key_id = None
                    request.state.auth_scopes = frozenset()
                    request.state.is_proxy_mode = False
                    logger.debug(f"[Auth] JWT认证成功: 用户 {user.id} ({user.username})")
                    return user
                logger.warning(f"[Auth] 用户ID {user_id} 不存在")
            else:
                logger.warning("[Auth] Token中没有用户ID")
        else:
            logger.warning("[Auth] Bearer 凭证解码失败")

    # 2. Fallback: 尝试 API Key 认证 (X-API-Key 头 或 Bearer token 作为 API Key)
    x_api_key = request.headers.get("x-api-key") or (bearer_token if bearer_token else None)
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
                scopes = normalize_api_key_scopes(api_key.scopes)
                _enforce_api_key_request(request, scopes)
                bind_authenticated_tenant(db, user.id)
                request.state.auth_type = "api_key"
                request.state.api_key_id = api_key.id
                request.state.auth_scopes = scopes
                request.state.is_proxy_mode = False
                logger.debug(f"[Auth] API Key认证成功: 用户 {user.id} ({user.username})")
                return user
        logger.warning("[Auth] API Key认证失败")

    if not jwt_token and not x_api_key:
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


def require_self_or_admin(current_user: User, user_id: int, *, resource: str = "用户数据") -> int:
    """Authorize a legacy explicit-user route without trusting its selector.

    New client surfaces should use ``/me`` routes.  Compatibility routes that
    still accept ``user_id`` must call this guard before touching user data.
    """
    target_user_id = int(user_id)
    if target_user_id != int(current_user.id) and not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"无权访问该{resource}",
        )
    return target_user_id


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
    bind_authenticated_tenant(db, user.id)
    # 当前已开事务(auth 查询所开,after_begin 当时还没租户)显式补设一次;
    # set_config 可参数化、local=true 同事务有效。后续事务由 after_begin + session.info 接力。
    try:
        yield user
    finally:
        db.info.pop("app_user_id", None)
        reset_current_tenant(token)
