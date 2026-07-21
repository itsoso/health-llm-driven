"""用户认证API"""
from datetime import datetime, timedelta, date, timezone
from typing import Optional, AsyncGenerator
import json
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app.models.user import User, GarminCredential
from app.models.agent_audit_log import AgentAuditLog
from app.models.account_deletion_request import AccountDeletionRequest
from app.schemas.auth import (
    UserRegister, UserLogin, Token, UserResponse, UserUpdate,
    PhoneCodeRequest, PhoneCodeResponse, PhoneCodeLogin, PhoneLoginToken,
    PasswordChange, PasswordSet, BindWebLogin, GarminCredentialCreate, GarminCredentialResponse,
    GarminSyncRequest, GarminSyncResponse,
    GarminTestConnectionResponse, GarminMFAVerifyRequest, GarminMFAVerifyResponse
)
from app.services.auth import auth_service, garmin_credential_service, AuthService
from app.services.phone_auth import (
    InvalidPhoneNumber,
    PhoneCodeCooldown,
    PhoneCodeDeliveryFailed,
    PhoneCodeDeliveryNotConfigured,
    consume_phone_code,
    issue_phone_code,
    mask_phone,
    normalize_phone,
)
from app.api.deps import get_current_user, get_current_user_required
from app.services.web_session import (
    WEB_SESSION_AUTH_SENTINEL,
    clear_web_session_cookie,
    set_web_session_cookie,
    wants_web_session,
)
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

# 配置限流器
limiter = Limiter(key_func=get_remote_address)


def user_to_response(user: User, db: Session) -> UserResponse:
    """将User模型转换为响应"""
    has_garmin = db.query(GarminCredential).filter(GarminCredential.user_id == user.id).first() is not None
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        birth_date=user.birth_date,
        gender=user.gender,
        is_active=user.is_active if user.is_active is not None else True,
        is_admin=getattr(user, 'is_admin', False) or False,
        is_approved=getattr(user, 'is_approved', False) or False,
        created_at=user.created_at,
        has_garmin_credentials=has_garmin,
        avatar_url=getattr(user, 'avatar_url', None),
        onboarding_completed=getattr(user, 'onboarding_completed', False) or False,
        phone=getattr(user, 'phone', None),
        phone_verified_at=getattr(user, 'phone_verified_at', None),
        has_password=bool(getattr(user, 'hashed_password', None)),
    )


def _issue_token_response(user: User, db: Session) -> Token:
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_to_response(user, db)
    )


def _deliver_access_token(
    request: Request,
    response: Response,
    access_token: str,
) -> str:
    """Keep browser JWTs HttpOnly while preserving native Bearer responses."""
    if wants_web_session(request):
        set_web_session_cookie(response, access_token)
        return WEB_SESSION_AUTH_SENTINEL
    return access_token


def _deliver_token(
    request: Request,
    response: Response,
    token: Token,
) -> Token:
    delivered_access_token = _deliver_access_token(
        request,
        response,
        token.access_token,
    )
    if delivered_access_token == token.access_token:
        return token
    return token.model_copy(update={"access_token": delivered_access_token})


def _unique_phone_username(db: Session, phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    base = f"phone_{digits[-11:] or digits}"
    username = base
    suffix = 1
    while auth_service.get_user_by_username(db, username):
        suffix += 1
        username = f"{base}_{suffix}"
    return username


def _ensure_active_approved(user: User) -> None:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )
    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户尚未通过管理员审核，请等待审核通过后再登录"
        )


@router.post("/register", summary="用户注册")
@limiter.limit("3/hour")  # 每小时最多3次注册尝试
async def register(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    用户注册（需要邀请码，注册后需管理员审核）

    - **username**: 用户名（3-50字符，唯一）
    - **email**: 邮箱（唯一）
    - **password**: 密码（至少6字符）
    - **name**: 姓名
    - **invite_code**: 邀请码（默认：LLM）

    限流：每小时最多3次注册尝试
    """
    from app.config import settings
    from app.models.invitation import InvitationCode

    # 验证邀请码：先检查数据库中的邀请码，再检查默认邀请码
    invite_code_upper = user_data.invite_code.upper()
    invite_valid = False

    # 查找数据库中的邀请码
    db_invite = db.query(InvitationCode).filter(
        InvitationCode.code == invite_code_upper
    ).first()

    if db_invite and db_invite.is_valid:
        invite_valid = True
        db_invite.used_count += 1
        logger.info(f"使用数据库邀请码: {invite_code_upper}, 已使用 {db_invite.used_count}/{db_invite.max_uses}")
    elif invite_code_upper == settings.default_invite_code.upper():
        invite_valid = True
        logger.info(f"使用默认邀请码: {invite_code_upper}")

    if not invite_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邀请码无效或已过期"
        )

    # 检查用户名是否已存在
    if auth_service.get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被注册"
        )

    # 检查邮箱是否已存在
    if auth_service.get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )

    # 创建用户（邀请码有效，自动审核通过）
    user = auth_service.create_user(
        db=db,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        name=user_data.name
    )

    # 设置邀请码和审核状态 — 有效邀请码自动通过
    user.invite_code = invite_code_upper
    user.is_approved = True
    db.commit()
    db.refresh(user)

    logger.info(f"新用户注册: {user.id} ({user.username}), 邀请码: {user.invite_code}, 自动审核通过")

    # 邀请码有效，自动通过，直接返回token
    access_token = auth_service.create_access_token({"sub": str(user.id)})
    delivered_access_token = _deliver_access_token(request, response, access_token)
    return {
        "message": "注册成功！邀请码验证通过，可以直接使用。",
        "user_id": user.id,
        "is_approved": True,
        "access_token": delivered_access_token,
        "token_type": "bearer"
    }


@router.post("/phone/code", response_model=PhoneCodeResponse, summary="发送手机号验证码")
@limiter.limit("10/minute")
async def send_phone_code(
    request: Request,
    payload: PhoneCodeRequest,
    db: Session = Depends(get_db),
):
    """发送手机号验证码，用于一期手机号一体化登录/注册。"""
    try:
        issued = issue_phone_code(
            db,
            payload.phone,
            purpose=payload.purpose,
            request_ip=request.client.host if request.client else None,
        )
    except InvalidPhoneNumber as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PhoneCodeCooldown as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except (PhoneCodeDeliveryFailed, PhoneCodeDeliveryNotConfigured) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return PhoneCodeResponse(
        message="验证码已发送",
        phone=issued.phone,
        expires_in_seconds=issued.expires_in_seconds,
        dev_code=issued.dev_code,
    )


@router.post("/phone/login", response_model=PhoneLoginToken, summary="手机号验证码登录或注册")
@limiter.limit("10/minute")
async def login_by_phone_code(
    request: Request,
    response: Response,
    payload: PhoneCodeLogin,
    db: Session = Depends(get_db),
):
    """验证码正确则登录；新手机号自动创建一个最小账号。"""
    try:
        phone = consume_phone_code(db, payload.phone, payload.code, purpose="login")
    except (InvalidPhoneNumber, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    user = auth_service.get_user_by_phone(db, phone)
    is_new_user = False
    if user is None:
        from app.config import settings

        user = User(
            username=_unique_phone_username(db, phone),
            email=None,
            hashed_password=None,
            name="小巴用户",
            phone=phone,
            phone_verified_at=now,
            is_active=True,
            is_approved=bool(settings.auth_phone_registration_auto_approve),
            onboarding_completed=False,
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError as exc:
            db.rollback()
            user = auth_service.get_user_by_phone(db, phone)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="手机号已被其他账号使用，请联系客服处理",
                ) from exc
        is_new_user = True
        logger.info("手机号新用户注册: user_id=%s phone=%s", user.id, mask_phone(phone))
    else:
        user.phone_verified_at = now
        db.commit()
        db.refresh(user)

    _ensure_active_approved(user)
    token = _issue_token_response(user, db)
    result = PhoneLoginToken(
        access_token=token.access_token,
        token_type=token.token_type,
        user=token.user,
        is_new_user=is_new_user,
    )
    delivered_access_token = _deliver_access_token(
        request,
        response,
        result.access_token,
    )
    return result.model_copy(update={"access_token": delivered_access_token})


@router.post("/login", response_model=Token, summary="用户登录")
@limiter.limit("5/minute")  # 每分钟最多5次登录尝试
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    用户登录（OAuth2密码流）

    - **username**: 用户名或邮箱
    - **password**: 密码

    注意：未通过管理员审核的用户无法登录
    限流：每分钟最多5次登录尝试，防止暴力破解
    """
    user = auth_service.authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    # 检查是否已通过审核
    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户尚未通过管理员审核，请等待审核通过后再登录"
        )

    return _deliver_token(request, response, _issue_token_response(user, db))


@router.post("/login/json", response_model=Token, summary="用户登录（JSON格式）")
@limiter.limit("5/minute")  # 每分钟最多5次登录尝试
async def login_json(
    request: Request,
    response: Response,
    login_data: UserLogin,
    db: Session = Depends(get_db),
):
    """
    用户登录（JSON格式）

    - **username**: 用户名或邮箱
    - **password**: 密码
    """
    user = auth_service.authenticate_user(db, login_data.username, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户尚未通过管理员审核，请等待审核通过后再登录"
        )

    return _deliver_token(request, response, _issue_token_response(user, db))


@router.post("/logout", summary="退出当前 Web 会话")
async def logout(
    response: Response,
    current_user: Optional[User] = Depends(get_current_user),
):
    clear_web_session_cookie(response)
    return {"message": "已退出登录"}


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前登录用户的信息（允许未审核用户查看自己的信息）"""
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
    # 允许未审核用户查看自己的信息，但不允许访问其他功能
    return user_to_response(current_user, db)


def _deletion_request_response(
    request: AccountDeletionRequest,
    *,
    existing: bool,
) -> dict:
    messages = {
        "requested": "删除请求已提交，我们会在 7 天内完成处理并保留必要审计记录。",
        "processing": "删除请求正在处理中。完成后账号将无法继续登录。",
        "completed": "账号与数据删除已完成。",
        "rejected": "删除请求未能完成，请联系 support@executor.life 了解原因。",
    }
    due_at = request.requested_at + timedelta(days=7) if request.requested_at else None
    return {
        "status": request.status,
        "user_id": request.user_id,
        "request_id": request.id,
        "audit_id": request.audit_id,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
        "due_at": due_at.isoformat() if due_at else None,
        "estimated_completion_days": 7,
        "existing": existing,
        "message": messages.get(request.status, messages["requested"]),
    }


@router.get("/me/deletion-request", summary="查询账号与数据删除请求")
async def get_account_deletion_request(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    request = (
        db.query(AccountDeletionRequest)
        .filter(AccountDeletionRequest.user_id == current_user.id)
        .order_by(AccountDeletionRequest.requested_at.desc(), AccountDeletionRequest.id.desc())
        .first()
    )
    if request is None:
        return {"status": "none", "user_id": current_user.id, "existing": False}
    return _deletion_request_response(request, existing=True)


@router.post("/me/deletion-request", summary="发起账号与数据删除请求")
async def request_account_deletion(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Let a signed-in user initiate account and health-data deletion.

    App Store account deletion rules require an in-app initiation path. Full
    deletion/anonymization touches many health tables, so this endpoint records a
    fail-loud auditable request for the deletion worker/admin process instead of
    silently pretending the account was deleted.
    """
    existing = (
        db.query(AccountDeletionRequest)
        .filter(AccountDeletionRequest.active_user_id == current_user.id)
        .first()
    )
    if existing is not None:
        return _deletion_request_response(existing, existing=True)

    requested_at = datetime.now(timezone.utc)
    deletion_request = AccountDeletionRequest(
        user_id=current_user.id,
        active_user_id=current_user.id,
        status="requested",
        channel="mobile_app",
        scope="account,health_data,device_connections",
        requested_at=requested_at,
    )
    audit = AgentAuditLog(
        user_id=current_user.id,
        agent_type="account_privacy",
        action="account_deletion_requested",
        result_summary="用户已在 App 内发起账号与数据删除请求",
        result_detail={
            "requested_by": "self",
            "channel": "mobile_app",
            "requested_at": requested_at.isoformat(),
            "estimated_completion_days": 7,
            "requires_manual_processing": True,
            "scope": ["account", "health_data", "device_connections"],
        },
    )
    try:
        db.add(deletion_request)
        db.add(audit)
        db.flush()
        deletion_request.audit_id = audit.id
        db.commit()
        db.refresh(deletion_request)
        db.refresh(audit)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(AccountDeletionRequest)
            .filter(AccountDeletionRequest.active_user_id == current_user.id)
            .first()
        )
        if existing is not None:
            return _deletion_request_response(existing, existing=True)
        logger.error("账号删除请求发生唯一约束冲突但未找到活动请求 - user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除请求未能记录，请稍后重试",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error(
            "账号删除请求记录失败 - user_id=%s, error=%s",
            current_user.id,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除请求未能记录，请稍后重试",
        ) from exc

    logger.warning(
        "用户 %s 发起账号与数据删除请求 request_id=%s audit_id=%s",
        current_user.id,
        deletion_request.id,
        audit.id,
    )
    return _deletion_request_response(deletion_request, existing=False)


@router.put("/me", response_model=UserResponse, summary="更新用户信息")
async def update_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新当前用户信息"""
    if user_update.name is not None:
        current_user.name = user_update.name
    if user_update.birth_date is not None:
        current_user.birth_date = user_update.birth_date
    if user_update.gender is not None:
        current_user.gender = user_update.gender

    db.commit()
    db.refresh(current_user)
    return user_to_response(current_user, db)


@router.post("/change-password", summary="修改密码")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """修改当前用户密码"""
    return _change_password(password_data, current_user, db)


@router.post("/password/set", summary="设置初始密码")
async def set_initial_password(
    password_data: PasswordSet,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """手机号/微信等无密码账号设置初始密码。"""
    if current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="账号已设置密码，请使用修改密码"
        )
    current_user.hashed_password = auth_service.get_password_hash(password_data.new_password)
    db.commit()
    return {"message": "密码设置成功"}


@router.post("/password/change", summary="修改密码")
async def change_password_alias(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """修改当前用户密码。新路径供移动端账号安全页使用。"""
    return _change_password(password_data, current_user, db)


def _change_password(
    password_data: PasswordChange,
    current_user: User,
    db: Session,
):
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前账号尚未设置密码"
        )
    if not auth_service.verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    current_user.hashed_password = auth_service.get_password_hash(password_data.new_password)
    db.commit()
    return {"message": "密码修改成功"}


@router.post("/bind-web-login", summary="绑定Web登录凭证")
async def bind_web_login(
    bind_data: BindWebLogin,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    微信用户绑定邮箱和密码，以便在Web端登录。
    仅适用于尚未设置邮箱的用户（如微信注册用户）。
    """
    # 已有邮箱的用户不允许重复绑定
    if current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="您已绑定邮箱，无需重复绑定"
        )

    # 检查邮箱是否已被其他用户使用
    existing = db.query(User).filter(User.email == bind_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被其他账号使用"
        )

    # 绑定邮箱和密码
    current_user.email = bind_data.email
    current_user.hashed_password = auth_service.get_password_hash(bind_data.password)
    db.commit()
    db.refresh(current_user)

    return {"message": "绑定成功，您现在可以使用邮箱和密码在Web端登录"}


# ========== Garmin凭证管理 ==========

@router.post("/garmin/credentials", response_model=GarminCredentialResponse, summary="保存Garmin凭证")
async def save_garmin_credentials(
    credentials: GarminCredentialCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    保存Garmin登录凭证

    凭证会被加密存储，用于后续自动同步Garmin数据

    - **is_cn**: 如果是中国用户(garmin.cn账号)，设置为 true
    """
    # 注意：这个接口是简单保存凭证，不做MFA检测
    # MFA检测在test-connection-with-credentials接口中进行
    credential = garmin_credential_service.save_credentials(
        db=db,
        user_id=current_user.id,
        garmin_email=credentials.garmin_email,
        garmin_password=credentials.garmin_password,
        is_cn=credentials.is_cn,
        requires_mfa=False  # 默认为False，将在test-connection时更新
    )
    return credential


@router.get("/garmin/credentials", response_model=GarminCredentialResponse, summary="获取Garmin凭证信息")
async def get_garmin_credentials(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的Garmin凭证信息（不包含密码）"""
    credential = garmin_credential_service.get_credentials(db, current_user.id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证"
        )
    return credential


@router.delete("/garmin/credentials", summary="删除Garmin凭证")
async def delete_garmin_credentials(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除当前用户的Garmin凭证"""
    if garmin_credential_service.delete_credentials(db, current_user.id):
        return {"message": "Garmin凭证已删除"}
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="未配置Garmin凭证"
    )


@router.post("/garmin/toggle-sync", summary="切换Garmin同步状态")
async def toggle_garmin_sync(
    enabled: bool,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    启用或禁用Garmin自动同步

    - **enabled**: True 启用同步，False 停止同步
    """
    credential = garmin_credential_service.get_credentials(db, current_user.id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证"
        )

    if garmin_credential_service.toggle_sync_enabled(db, current_user.id, enabled):
        return {
            "message": f"Garmin同步已{'启用' if enabled else '停止'}",
            "sync_enabled": enabled
        }
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="更新同步状态失败"
    )


@router.post("/garmin/sync", response_model=GarminSyncResponse, summary="同步Garmin数据")
@limiter.limit("5/minute")  # Garmin 同步每分钟最多5次
async def sync_garmin_data(
    request: Request,
    sync_request: GarminSyncRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    手动触发Garmin数据同步（同时同步健康数据和运动活动）

    - **days**: 同步最近N天的数据（默认7天，最多730天）
    """
    # 获取解密后的凭证
    credentials = garmin_credential_service.get_decrypted_credentials(db, current_user.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证，请先在设置中配置"
        )

    # 获取同步锁（防止并发同步）
    from app.services.sync_lock import acquire_sync_lock, release_sync_lock
    if not acquire_sync_lock(db, current_user.id):
        raise HTTPException(status_code=409, detail="同步正在进行中，请稍后再试")

    # 执行同步
    try:
        from app.services.data_collection.garmin_connect import GarminConnectService
        from app.services.workout_sync import WorkoutSyncService
        from datetime import date, timedelta

        # 创建Garmin服务实例（传入凭证，会自动登录）
        # 如果有mfa_session_id，传递给服务以复用已认证的会话
        garmin_service = GarminConnectService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=current_user.id,
            mfa_session_id=sync_request.mfa_session_id  # 传递MFA session ID
        )

        # 同步每日健康数据
        synced_days = 0
        failed_days = 0
        today = date.today()

        for i in range(sync_request.days):
            target_date = today - timedelta(days=i)
            try:
                garmin_service.sync_daily_data(db, current_user.id, target_date)
                synced_days += 1
            except Exception as e:
                # 检查是否是MFA错误
                error_msg = str(e).lower()
                if 'mfa' in error_msg or 'two-factor' in error_msg or '两步验证' in error_msg or 'verification' in error_msg:
                    logger.warning(f"[用户 {current_user.id}] 同步需要MFA验证")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="🔐 Garmin账号需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。"
                    ) from e
                logger.warning(f"同步 {target_date} 失败: {e}")
                failed_days += 1

        # 同步运动活动数据
        synced_activities = 0
        activities_error = None
        try:
            # 复用已认证的garmin_service的client（如果可用）
            workout_client = garmin_service.client if hasattr(garmin_service, 'client') and garmin_service.client else None
            workout_sync_service = WorkoutSyncService(
                email=credentials["email"],
                password=credentials["password"],
                is_cn=credentials.get("is_cn", False),
                user_id=current_user.id,
                client=workout_client  # 传递已认证的client
            )
            result = await workout_sync_service.sync_activities(db, current_user.id, sync_request.days)
            synced_activities = result.get("synced_count", 0)
            logger.info(f"[用户 {current_user.id}] 运动活动同步完成，共 {synced_activities} 条")
        except Exception as e:
            # 检查是否是MFA错误
            error_msg = str(e).lower()
            if 'mfa' in error_msg or 'two-factor' in error_msg or '两步验证' in error_msg or 'verification' in error_msg:
                logger.warning(f"[用户 {current_user.id}] 运动活动同步需要MFA验证")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="🔐 Garmin账号需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。"
                ) from e
            logger.warning(f"[用户 {current_user.id}] 运动活动同步失败: {e}", exc_info=True)
            activities_error = str(e)

        # 更新同步状态
        garmin_credential_service.update_sync_status(db, current_user.id)

        message = f"同步完成：健康数据 {synced_days} 天"
        if synced_activities > 0:
            message += f"，运动活动 {synced_activities} 条"
        if failed_days > 0:
            message += f"，失败 {failed_days} 天"
        if activities_error:
            message += f"，运动同步异常: {activities_error}"

        return GarminSyncResponse(
            success=True,
            message=message,
            synced_days=synced_days,
            failed_days=failed_days,
            activities_count=synced_activities,
            activities_error=activities_error
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Garmin同步失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步失败: {str(e)}"
        )
    finally:
        release_sync_lock(db, current_user.id)


@router.get("/garmin/sync-stream", summary="流式同步Garmin数据（带进度）")
@limiter.limit("5/minute")  # Garmin 流式同步每分钟最多5次
async def sync_garmin_data_stream(
    request: Request,
    days: int = 7,
    mfa_session_id: Optional[str] = Query(default=None, description="MFA会话ID（如果已完成MFA验证）"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    使用 Server-Sent Events 流式同步Garmin数据，实时返回进度

    参数：
    - days: 同步最近N天的数据
    - mfa_session_id: MFA会话ID（可选，如果已完成MFA验证可传入以复用认证状态）
    """
    # 获取解密后的凭证
    credentials = garmin_credential_service.get_decrypted_credentials(db, current_user.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证，请先在设置中配置"
        )

    def _sync_single_date_helper(garmin_service, user_id: int, target_date: date, date_str: str) -> dict:
        """在独立线程中同步单个日期的数据（辅助函数）"""
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            garmin_service.sync_daily_data(db, user_id, target_date)
            return {"success": True}
        except Exception as e:
            error_msg = str(e).lower()
            if 'mfa' in error_msg or 'two-factor' in error_msg or '两步验证' in error_msg or 'verification' in error_msg:
                return {"success": False, "mfa_required": True}
            logger.warning(f"同步 {date_str} 失败: {e}")
            return {"success": False}
        finally:
            db.close()

    async def generate_progress() -> AsyncGenerator[str, None]:
        from app.services.data_collection.garmin_connect import GarminConnectService

        synced_days = 0
        failed_days = 0
        today = date.today()

        # 发送开始消息
        yield f"data: {json.dumps({'type': 'start', 'total': days, 'message': '开始同步...'})}\n\n"

        try:
            # 先测试连接，检测是否需要MFA
            from app.services.data_collection.garmin_connect import GarminConnectService

            # 如果提供了mfa_session_id，尝试复用已认证的会话
            test_service = GarminConnectService(
                email=credentials["email"],
                password=credentials["password"],
                is_cn=credentials.get("is_cn", False),
                user_id=current_user.id,
                mfa_session_id=mfa_session_id  # 传递MFA会话ID
            )

            # 尝试测试连接来检测MFA
            try:
                test_result = test_service.test_connection_with_mfa()
                logger.info(f"测试连接结果: success={test_result.get('success')}, mfa_required={test_result.get('mfa_required')}, mfa_session_id={test_result.get('mfa_session_id')}")
                if test_result.get("mfa_required") and test_result.get("mfa_session_id"):
                    error_data = {
                        'type': 'error',
                        'message': '🔐 Garmin账号需要两步验证！请输入验证码完成验证。',
                        'mfa_required': True,
                        'mfa_session_id': test_result.get("mfa_session_id")
                    }
                    logger.info(f"发送MFA错误消息: {error_data}")
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
            except Exception as test_error:
                # 如果测试连接失败，检查是否是MFA错误或锁定错误
                error_msg = str(test_error).lower()
                original_msg = str(test_error)

                # 检查是否是登录锁定
                if '登录已被暂停' in original_msg or '分钟后再试' in original_msg:
                    error_data = {
                        'type': 'error',
                        'message': original_msg,
                        'locked': True
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return

                if 'mfa' in error_msg or 'two-factor' in error_msg or '两步验证' in error_msg or 'verification' in error_msg:
                    error_data = {
                        'type': 'error',
                        'message': '🔐 Garmin账号需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。',
                        'mfa_required': True
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return

                # 检查是否是登录失败（密码错误等）
                if any(kw in error_msg for kw in ['401', 'unauthorized', 'credential', 'password', 'login', 'auth', 'oauth', 'ticket']):
                    error_data = {
                        'type': 'error',
                        'message': '❌ 登录失败！请检查：1) 邮箱和密码是否正确 2) 是否选对了服务器（国际版/中国版）3) 先在 Garmin Connect 官网登录确认账号正常'
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return

                # 其他错误，继续尝试同步（可能是测试连接的问题，实际同步可能成功）
                logger.warning(f"测试连接失败，继续尝试同步: {test_error}")

            # 复用 test_service（已通过测试连接完成认证），避免重复登录触发 Garmin 限流
            garmin_service = test_service

            yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': days, 'message': 'Garmin连接成功'})}\n\n"

            # 使用线程池执行同步操作，避免阻塞事件循环
            import concurrent.futures
            from app.database import SessionLocal

            # 创建线程池（最多3个并发）
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = []

                for i in range(days):
                    target_date = today - timedelta(days=i)
                    date_str = target_date.strftime("%Y-%m-%d")

                    # 提交同步任务到线程池
                    future = executor.submit(
                        _sync_single_date_helper,
                        garmin_service,
                        current_user.id,
                        target_date,
                        date_str
                    )
                    futures.append((i, target_date, date_str, future))

                # 处理完成的任务
                for i, target_date, date_str, future in futures:
                    try:
                        # 等待任务完成，但设置超时避免卡死
                        result = future.result(timeout=30)  # 30秒超时
                        if result.get("success"):
                            synced_days += 1
                            status_msg = "success"
                        else:
                            failed_days += 1
                            status_msg = "failed"

                            # 检查是否是MFA错误
                            if result.get("mfa_required"):
                                error_data = {
                                    'type': 'error',
                                    'message': '🔐 Garmin账号需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。',
                                    'mfa_required': True
                                }
                                yield f"data: {json.dumps(error_data)}\n\n"
                                return
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"同步 {target_date} 超时")
                        failed_days += 1
                        status_msg = "timeout"
                    except Exception as e:
                        logger.warning(f"同步 {target_date} 失败: {e}")
                        failed_days += 1
                        status_msg = "failed"

                    # 发送进度更新
                    progress_data = {
                        'type': 'progress',
                        'current': i + 1,
                        'total': days,
                        'date': date_str,
                        'status': status_msg,
                        'synced': synced_days,
                        'failed': failed_days,
                        'message': f'正在同步 {date_str}...'
                    }
                    yield f"data: {json.dumps(progress_data)}\n\n"

                    # 小延迟，让前端有时间处理
                    await asyncio.sleep(0.05)  # 减少延迟时间

            # 同步运动活动数据
            synced_activities = 0
            try:
                yield f"data: {json.dumps({'type': 'progress', 'current': days, 'total': days, 'message': '开始同步运动活动数据...'})}\n\n"

                from app.services.workout_sync import WorkoutSyncService
                # 优先复用已认证的garmin_service的client，如果没有则使用MFA会话
                workout_sync_service = WorkoutSyncService(
                    email=credentials["email"],
                    password=credentials["password"],
                    is_cn=credentials.get("is_cn", False),
                    user_id=current_user.id,
                    mfa_session_id=mfa_session_id,  # 传递MFA会话ID以复用认证状态
                    client=garmin_service.client if garmin_service._authenticated and garmin_service.client else None  # 直接复用已认证的client
                )
                workout_result = await workout_sync_service.sync_activities(db, current_user.id, days)
                synced_activities = workout_result.get("synced_count", 0)
                logger.info(f"[用户 {current_user.id}] 运动活动同步完成，共 {synced_activities} 条")
            except Exception as e:
                # 检查是否是MFA错误
                error_msg = str(e).lower()
                if 'mfa' in error_msg or 'two-factor' in error_msg or '两步验证' in error_msg or 'verification' in error_msg:
                    logger.warning(f"[用户 {current_user.id}] 运动活动同步需要MFA验证")
                    error_data = {
                        'type': 'error',
                        'message': '🔐 运动活动同步需要两步验证！请先在设置页面完成MFA验证，然后再尝试同步。',
                        'mfa_required': True
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                logger.warning(f"[用户 {current_user.id}] 运动活动同步失败: {e}")
                # 运动活动同步失败不影响整体同步结果，继续执行

            # 更新同步状态
            garmin_credential_service.update_sync_status(db, current_user.id)

            # 发送完成消息
            complete_data = {
                'type': 'complete',
                'synced': synced_days,
                'failed': failed_days,
                'activities': synced_activities,
                'message': f'同步完成：成功 {synced_days} 天，失败 {failed_days} 天' + (f'，运动活动 {synced_activities} 条' if synced_activities > 0 else '')
            }
            yield f"data: {json.dumps(complete_data)}\n\n"

        except Exception as e:
            logger.error(f"Garmin同步失败: {e}", exc_info=True)
            error_data = {
                'type': 'error',
                'message': f'同步失败: {str(e)}'
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )


@router.post("/garmin/test-connection", response_model=GarminTestConnectionResponse, summary="测试Garmin连接")
async def test_garmin_connection(
    credentials: GarminCredentialCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    测试Garmin凭证是否有效（不保存）

    返回明确的提示信息：
    - 成功：✅ 密码正确，连接成功
    - 需要MFA：🔐 需要两步验证，请输入验证码
    - 失败：❌ 密码错误或账号无效

    注意：
    - 中国用户(garmin.cn)需要设置 is_cn=true
    - 如果账号开启了两步验证(MFA)，会返回 mfa_required=true 和 client_state
    """
    try:
        from app.services.data_collection.garmin_connect import GarminConnectService

        from app.utils.redact import mask_email
        server_type = "中国版(garmin.cn)" if credentials.is_cn else "国际版(garmin.com)"
        logger.info(f"测试Garmin连接 - 服务器: {server_type}, 邮箱: {mask_email(credentials.garmin_email)}")

        # 创建服务实例
        garmin_service = GarminConnectService(
            email=credentials.garmin_email,
            password=credentials.garmin_password,
            is_cn=credentials.is_cn,
            user_id=current_user.id
        )

        # 使用支持 MFA 的测试连接方法
        result = garmin_service.test_connection_with_mfa()

        # 如果检测到需要MFA，更新数据库中的requires_mfa字段
        if result.get("mfa_required"):
            try:
                garmin_credential_service.update_mfa_status(db, current_user.id, requires_mfa=True)
                logger.info(f"已更新用户 {current_user.id} 的MFA状态为需要MFA")
            except Exception as e:
                logger.warning(f"更新MFA状态失败: {e}")

        return GarminTestConnectionResponse(
            success=result.get("success", False),
            mfa_required=result.get("mfa_required", False),
            message=result.get("message", ""),
            mfa_session_id=result.get("mfa_session_id")
        )

    except Exception as e:
        logger.error(f"测试Garmin连接失败: {e}")
        error_msg = str(e).lower()
        original_msg = str(e)

        # 检查是否是登录锁定错误
        if '登录已被暂停' in original_msg or '分钟后再试' in original_msg:
            return GarminTestConnectionResponse(
                success=False,
                mfa_required=False,
                message=original_msg  # 直接使用原始的友好提示
            )

        # 检查是否需要设置密码
        if 'set password' in error_msg or 'unexpected title' in error_msg:
            return GarminTestConnectionResponse(
                success=False,
                mfa_required=False,
                message="⚠️ Garmin账号需要设置密码！请先访问 connect.garmin.com 登录并按提示完成密码设置。"
            )

        # 登录失败 - 提供更详细的提示
        if any(kw in error_msg for kw in ['401', 'unauthorized', 'credential', 'password', 'login', 'auth', 'oauth', 'ticket']):
            return GarminTestConnectionResponse(
                success=False,
                mfa_required=False,
                message="❌ 登录失败！请检查：1) 邮箱和密码是否正确 2) 是否选对了服务器（国际版/中国版）3) 先在 Garmin Connect 官网登录确认账号正常"
            )

        return GarminTestConnectionResponse(
            success=False,
            mfa_required=False,
            message=f"❌ 连接失败: {str(e)}"
        )


@router.post("/garmin/verify-mfa", response_model=GarminMFAVerifyResponse, summary="验证Garmin两步验证码")
async def verify_garmin_mfa(
    mfa_request: GarminMFAVerifyRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    使用两步验证码完成Garmin登录验证

    在调用 test-connection 返回 mfa_required=true 后，使用此接口提交验证码完成验证。

    参数：
    - mfa_code: 6位数字验证码（来自您的验证器应用）
    - mfa_session_id: test-connection 返回的会话ID
    """
    try:
        from app.services.data_collection.garmin_connect import verify_mfa_with_session

        logger.info(f"验证Garmin MFA - session_id: {mfa_request.mfa_session_id}")

        # 使用验证码恢复登录
        result = verify_mfa_with_session(
            session_id=mfa_request.mfa_session_id,
            mfa_code=mfa_request.mfa_code
        )

        # 如果验证成功，更新数据库中的requires_mfa字段为True
        if result.get("success") and result.get("session_id"):
            try:
                garmin_credential_service.update_mfa_status(db, current_user.id, requires_mfa=True)
                logger.info(f"MFA验证成功，已更新用户 {current_user.id} 的MFA状态为需要MFA")
            except Exception as e:
                logger.warning(f"更新MFA状态失败: {e}")

        return GarminMFAVerifyResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
            session_id=result.get("session_id")  # 返回session_id
        )

    except Exception as e:
        logger.error(f"验证Garmin MFA失败: {e}")
        return GarminMFAVerifyResponse(
            success=False,
            message=f"❌ 验证失败: {str(e)}"
        )
