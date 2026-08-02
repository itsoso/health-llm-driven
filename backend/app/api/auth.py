"""用户认证API"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional, AsyncGenerator
import json
import hmac
import re
from fastapi import APIRouter, Body, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import Field, ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app.models.user import User, GarminCredential
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import RegistrationAuthAttemptAudit
from app.models.account_deletion_request import AccountDeletionRequest
from app.schemas.auth import (
    UserRegister, UserLogin, Token, UserResponse, UserUpdate,
    PhoneCodeRequest, PhoneCodeResponse, PhoneCodeLogin, PhoneLoginToken,
    PhoneVerificationAuthenticated, PhoneVerificationInvitationRequired,
    InvitationCredentialInput, InvitationInspectResponse, InvitedRegistrationInput,
    PasswordChange, PasswordSet, BindWebLogin, GarminCredentialCreate, GarminCredentialResponse,
    GarminSyncRequest, GarminSyncResponse,
    GarminTestConnectionResponse, GarminMFAVerifyRequest, GarminMFAVerifyResponse
)
from app.services.auth import auth_service, garmin_credential_service, AuthService
from app.services.data_collection.garmin_executor import run_garmin_blocking
from app.services.phone_auth import (
    InvalidPhoneNumber,
    PhoneCodeCooldown,
    PhoneCodeDeliveryFailed,
    PhoneCodeDeliveryNotConfigured,
    consume_phone_code,
    issue_phone_code,
    mask_phone,
)
from app.services.registration_invitation import (
    create_phone_registration_grant,
    find_invitation_by_code,
    find_invitation_by_link_token,
    find_invitation_for_update,
    find_phone_registration_grant_for_update,
    registration_idempotency_digest,
    registration_source_hmac,
)
from app.api.deps import get_current_user, get_current_user_required
from app.services.web_session import (
    WEB_SESSION_AUTH_SENTINEL,
    clear_web_session_cookie,
    set_web_session_cookie,
    wants_web_session,
)
import logging
logger = logging.getLogger(__name__)

router = APIRouter()

# 配置限流器
limiter = Limiter(key_func=get_remote_address)

_URL_SAFE_CREDENTIAL_RE = re.compile(r"[A-Za-z0-9_-]{22,128}\Z")
_MANUAL_CODE_RE = re.compile(r"[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{8}\Z")
_IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9._:-]{16,128}\Z")


def _auth_error(http_status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    )


def _registration_expiry_is_future(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    else:
        normalized = normalized.astimezone(timezone.utc)
    return normalized > now


def _require_legacy_registration_open() -> None:
    """Block every legacy account-creation path once enforcement is active."""

    from app.config import settings

    if settings.registration_invitation_enforcement_enabled:
        raise _auth_error(
            status.HTTP_403_FORBIDDEN,
            "REGISTRATION_INVITATION_REQUIRED",
            "新用户需要管理员发送的手机号注册邀请",
        )


def _require_registration_rollout_open() -> None:
    """Fail closed when invited registration is paused for safe rollback."""

    from app.config import settings

    if not settings.registration_invitation_rollout_enabled:
        raise _auth_error(
            status.HTTP_403_FORBIDDEN,
            "REGISTRATION_CLOSED",
            "新用户注册暂时关闭，已注册用户仍可登录",
        )


def _safe_body(model: type, raw: Any):
    """Validate public credential bodies without FastAPI echoing rejected input."""

    try:
        return model.model_validate(raw)
    except (ValidationError, TypeError, ValueError) as exc:
        raise _auth_error(
            status.HTTP_400_BAD_REQUEST,
            "REGISTRATION_INPUT_INVALID",
            "注册凭据格式无效",
        ) from exc


def _secret_value(value: Any) -> str | None:
    return value.get_secret_value() if value is not None else None


def _validated_invitation_credentials(payload: InvitationCredentialInput) -> tuple[str | None, str | None]:
    manual_code = _secret_value(payload.manual_code)
    link_token = _secret_value(payload.link_token)
    if manual_code is not None:
        manual_code = manual_code.strip().upper()
        if not _MANUAL_CODE_RE.fullmatch(manual_code):
            raise _auth_error(400, "REGISTRATION_INPUT_INVALID", "注册凭据格式无效")
    if link_token is not None:
        link_token = link_token.strip()
        if not _URL_SAFE_CREDENTIAL_RE.fullmatch(link_token):
            raise _auth_error(400, "REGISTRATION_INPUT_INVALID", "注册凭据格式无效")
    return manual_code, link_token


def _audit_invited_registration(
    db: Session,
    *,
    user_id: int,
    action: str,
    invitation_id: int,
    grant_id: int,
    outcome: str,
) -> None:
    db.add(
        AgentAuditLog(
            user_id=user_id,
            agent_type="auth_registration",
            specialist_name="invited_phone_registration",
            action=action,
            result_summary=outcome,
            result_detail={
                "invitation_id": invitation_id,
                "grant_id": grant_id,
                "outcome": outcome,
            },
        )
    )


def _write_registration_terminal_audit(
    db: Session,
    *,
    outcome: str,
    error_code: str | None,
    invitation_id: int | None,
    grant_id: int | None,
    user_id: int | None,
    phone_masked: str | None,
    source_hmac: str | None,
) -> None:
    """Stage one bounded terminal attempt record in the current transaction."""

    db.add(
        RegistrationAuthAttemptAudit(
            outcome=outcome,
            error_code=error_code,
            invitation_id=invitation_id,
            grant_id=grant_id,
            user_id=user_id,
            phone_masked=phone_masked,
            source_hmac=source_hmac,
        )
    )
    db.flush()


def _persist_rejected_registration_audit(
    db: Session,
    *,
    error_code: str,
    context: dict[str, Any],
) -> None:
    """Persist rejection after the business transaction rolled back.

    Audit availability never changes the original safe business response.
    """

    try:
        _write_registration_terminal_audit(
            db,
            outcome="rejected",
            error_code=error_code[:64],
            invitation_id=context.get("invitation_id"),
            grant_id=context.get("grant_id"),
            user_id=context.get("user_id"),
            phone_masked=context.get("phone_masked"),
            source_hmac=context.get("source_hmac"),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.error("invited registration terminal audit unavailable")


def _registration_error_code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        if isinstance(code, str) and 1 <= len(code) <= 64:
            return code
    return "REGISTRATION_POLICY_REJECTED"


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

    _require_legacy_registration_open()

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
        logger.info(
            "使用数据库邀请码，已使用 %s/%s",
            db_invite.used_count,
            db_invite.max_uses,
        )
    elif invite_code_upper == settings.default_invite_code.upper():
        invite_valid = True
        logger.info("使用默认邀请码")

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

    logger.info("旧版邀请码新用户注册: user_id=%s", user.id)

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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None

    return PhoneCodeResponse(
        message="验证码已发送",
        phone=issued.phone,
        expires_in_seconds=issued.expires_in_seconds,
        dev_code=issued.dev_code,
    )


@router.post(
    "/phone/login",
    response_model=PhoneLoginToken,
    summary="手机号验证码登录或注册",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PhoneCodeLogin.model_json_schema()}},
        }
    },
)
@limiter.limit("10/minute")
async def login_by_phone_code(
    request: Request,
    response: Response,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
):
    """Legacy OTP login; enforcement blocks unknown-phone auto-registration."""
    parsed = _safe_body(PhoneCodeLogin, payload)
    try:
        phone = consume_phone_code(db, parsed.phone, parsed.code, purpose="login")
    except (InvalidPhoneNumber, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    user = auth_service.get_user_by_phone(db, phone)
    is_new_user = False
    if user is None:
        from app.config import settings

        if settings.registration_invitation_enforcement_enabled:
            raise _auth_error(
                status.HTTP_403_FORBIDDEN,
                "REGISTRATION_INVITATION_REQUIRED",
                "该手机号需要管理员邀请后才能注册",
            )

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


@router.post(
    "/phone/verify",
    response_model=Annotated[
        PhoneVerificationAuthenticated | PhoneVerificationInvitationRequired,
        Field(discriminator="outcome"),
    ],
    summary="验证手机号并区分登录或邀请注册",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PhoneCodeLogin.model_json_schema()}},
        }
    },
)
@limiter.limit("10/minute")
async def verify_phone_code(
    request: Request,
    response: Response,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
):
    """Consume an OTP exactly once without creating an unknown-phone user."""

    parsed = _safe_body(PhoneCodeLogin, payload)
    try:
        phone = consume_phone_code(
            db,
            parsed.phone,
            parsed.code,
            purpose="login",
            commit=False,
        )
        now = datetime.now(timezone.utc)
        user = auth_service.get_user_by_phone(db, phone)
        if user is not None:
            try:
                _ensure_active_approved(user)
            except HTTPException:
                # A valid OTP remains one-time even when account policy denies
                # token issuance.
                db.commit()
                raise
            user.phone_verified_at = now
            db.commit()
            db.refresh(user)
            token = _issue_token_response(user, db)
            result = PhoneVerificationAuthenticated(
                access_token=token.access_token,
                token_type=token.token_type,
                user=token.user,
                is_new_user=False,
            )
            return _deliver_token(request, response, result)

        from app.config import settings

        if not settings.registration_invitation_rollout_enabled:
            # A valid OTP remains one-time while rollback closes only new
            # registrations. Existing users above continue to authenticate.
            db.commit()
            raise _auth_error(
                status.HTTP_403_FORBIDDEN,
                "REGISTRATION_CLOSED",
                "新用户注册暂时关闭，已注册用户仍可登录",
            )
        issued = create_phone_registration_grant(db, phone, now=now)
        db.commit()
        expires_in = max(1, int((issued.expires_at - now).total_seconds()))
        return PhoneVerificationInvitationRequired(
            verified_phone_ticket=issued.token,
            expires_in_seconds=expires_in,
        )
    except HTTPException:
        db.rollback()
        raise
    except (InvalidPhoneNumber, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("phone verification persistence conflict")
        raise _auth_error(
            status.HTTP_409_CONFLICT,
            "PHONE_VERIFICATION_CONFLICT",
            "手机号验证状态冲突，请重新获取验证码",
        ) from exc


@router.post(
    "/invitations/inspect",
    response_model=InvitationInspectResponse,
    summary="检查注册邀请",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": InvitationCredentialInput.model_json_schema()
                }
            },
        }
    },
)
@limiter.limit("20/minute")
async def inspect_registration_invitation(
    request: Request,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
):
    _require_registration_rollout_open()
    parsed = _safe_body(InvitationCredentialInput, payload)
    manual_code, link_token = _validated_invitation_credentials(parsed)
    invitation = (
        find_invitation_by_code(db, manual_code)
        if manual_code is not None
        else find_invitation_by_link_token(db, link_token)
    )
    now = datetime.now(timezone.utc)
    if invitation is None or not invitation.is_usable(now):
        return InvitationInspectResponse(valid=False)
    return InvitationInspectResponse(
        valid=True,
        phone_masked=invitation.phone_masked,
        expires_at=invitation.expires_at,
    )


@router.post(
    "/invited-registration",
    response_model=PhoneLoginToken,
    summary="使用手机号验证票据与邀请完成注册",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": InvitedRegistrationInput.model_json_schema()
                }
            },
        }
    },
)
@limiter.limit("10/minute")
async def invited_phone_registration(
    request: Request,
    response: Response,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
):
    audit_context: dict[str, Any] = {
        "invitation_id": None,
        "grant_id": None,
        "user_id": None,
        "phone_masked": None,
        "source_hmac": registration_source_hmac(
            request.client.host if request.client is not None else None
        ),
    }
    try:
        _require_registration_rollout_open()
        parsed = _safe_body(InvitedRegistrationInput, payload)
        manual_code, link_token = _validated_invitation_credentials(parsed)
        ticket = parsed.verified_phone_ticket.get_secret_value().strip()
        idempotency_key = parsed.idempotency_key.get_secret_value().strip()
        if not _URL_SAFE_CREDENTIAL_RE.fullmatch(
            ticket
        ) or not _IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
            raise _auth_error(400, "REGISTRATION_INPUT_INVALID", "注册凭据格式无效")

        now = datetime.now(timezone.utc)
        idempotency_digest = registration_idempotency_digest(idempotency_key)
        grant = find_phone_registration_grant_for_update(db, ticket)
        invitation = find_invitation_for_update(
            db,
            manual_code=manual_code,
            link_token=link_token,
        )
        if grant is not None:
            audit_context["grant_id"] = grant.id
        if invitation is not None:
            audit_context["invitation_id"] = invitation.id
            audit_context["phone_masked"] = invitation.phone_masked
        if grant is None:
            raise _auth_error(
                400,
                "VERIFIED_PHONE_TICKET_EXPIRED",
                "手机号验证已失效，请重新验证",
            )
        if invitation is None:
            raise _auth_error(
                400,
                "INVITATION_INVALID",
                "邀请无效或已过期",
            )

        # A successful request can be safely replayed only with the same key.
        if grant.consumed_at is not None:
            if (
                grant.idempotency_key_digest == idempotency_digest
                and grant.consumed_by is not None
                and invitation.status == "consumed"
                and invitation.consumed_by == grant.consumed_by
            ):
                if not _registration_expiry_is_future(grant.expires_at, now):
                    raise _auth_error(
                        400,
                        "VERIFIED_PHONE_TICKET_EXPIRED",
                        "手机号验证已失效，请重新验证",
                    )
                if not _registration_expiry_is_future(invitation.expires_at, now):
                    raise _auth_error(
                        400,
                        "INVITATION_EXPIRED",
                        "邀请无效或已过期",
                    )
                user = db.get(User, grant.consumed_by)
                if user is None:
                    raise _auth_error(409, "REGISTRATION_STATE_CONFLICT", "注册状态冲突")
                _ensure_active_approved(user)
                audit_context["user_id"] = user.id
                token = _issue_token_response(user, db)
                result = PhoneLoginToken(
                    access_token=token.access_token,
                    token_type=token.token_type,
                    user=token.user,
                    is_new_user=False,
                )
                _write_registration_terminal_audit(
                    db,
                    outcome="success",
                    error_code=None,
                    invitation_id=invitation.id,
                    grant_id=grant.id,
                    user_id=user.id,
                    phone_masked=invitation.phone_masked,
                    source_hmac=audit_context["source_hmac"],
                )
                db.commit()
                delivered = _deliver_access_token(request, response, result.access_token)
                return result.model_copy(update={"access_token": delivered})
            raise _auth_error(
                409,
                "INVITATION_ALREADY_USED",
                "注册凭据已使用",
            )

        grant_expiry = grant.expires_at
        if grant_expiry.tzinfo is None:
            grant_expiry = grant_expiry.replace(tzinfo=timezone.utc)
        if grant_expiry <= now:
            raise _auth_error(
                400,
                "VERIFIED_PHONE_TICKET_EXPIRED",
                "手机号验证已失效，请重新验证",
            )
        if not invitation.is_usable(now):
            invitation_code = {
                "revoked": "INVITATION_REVOKED",
                "consumed": "INVITATION_ALREADY_USED",
                "expired": "INVITATION_EXPIRED",
            }.get(invitation.status, "INVITATION_EXPIRED")
            raise _auth_error(
                400,
                invitation_code,
                "邀请无效或已过期",
            )
        if not hmac.compare_digest(grant.phone_hmac, invitation.phone_hmac):
            raise _auth_error(
                400,
                "INVITATION_PHONE_MISMATCH",
                "邀请与已验证手机号不匹配",
            )

        phone = grant.phone_ciphertext
        if auth_service.get_user_by_phone(db, phone) is not None:
            raise _auth_error(
                409,
                "REGISTRATION_USER_ALREADY_EXISTS",
                "该手机号已注册，请直接登录",
            )

        user = User(
            username=_unique_phone_username(db, phone),
            email=None,
            hashed_password=None,
            name="小巴用户",
            phone=phone,
            phone_verified_at=now,
            is_active=True,
            is_approved=True,
            onboarding_completed=False,
        )
        db.add(user)
        db.flush()
        grant.consumed_at = now
        grant.consumed_by = user.id
        grant.idempotency_key_digest = idempotency_digest
        invitation.status = "consumed"
        invitation.consumed_at = now
        invitation.consumed_by = user.id
        _audit_invited_registration(
            db,
            user_id=user.id,
            action="invitation_consumed",
            invitation_id=invitation.id,
            grant_id=grant.id,
            outcome="success",
        )
        _write_registration_terminal_audit(
            db,
            outcome="success",
            error_code=None,
            invitation_id=invitation.id,
            grant_id=grant.id,
            user_id=user.id,
            phone_masked=invitation.phone_masked,
            source_hmac=audit_context["source_hmac"],
        )
        db.commit()
        db.refresh(user)
        token = _issue_token_response(user, db)
        result = PhoneLoginToken(
            access_token=token.access_token,
            token_type=token.token_type,
            user=token.user,
            is_new_user=True,
        )
        delivered = _deliver_access_token(request, response, result.access_token)
        return result.model_copy(update={"access_token": delivered})
    except HTTPException as exc:
        db.rollback()
        _persist_rejected_registration_audit(
            db,
            error_code=_registration_error_code(exc),
            context=audit_context,
        )
        raise
    except IntegrityError as exc:
        db.rollback()
        logger.warning("invited registration persistence conflict")
        safe_error = _auth_error(
            409,
            "REGISTRATION_STATE_CONFLICT",
            "注册状态冲突，请重试",
        )
        _persist_rejected_registration_audit(
            db,
            error_code="REGISTRATION_STATE_CONFLICT",
            context=audit_context,
        )
        raise safe_error from exc
    except Exception as exc:
        db.rollback()
        # Keep both the response and production logs free of exception text:
        # SQL drivers and downstream audit hooks may attach sensitive params.
        logger.error("invited registration persistence failed")
        safe_error = _auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "REGISTRATION_PERSISTENCE_FAILED",
            "注册服务暂时不可用，请稍后重试",
        )
        _persist_rejected_registration_audit(
            db,
            error_code="REGISTRATION_PERSISTENCE_FAILED",
            context=audit_context,
        )
        raise safe_error from exc


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

    try:
        from app.scheduler import sync_user_garmin_data

        result = await sync_user_garmin_data(
            db,
            current_user.id,
            credentials["email"],
            credentials["password"],
            days=sync_request.days,
            is_cn=credentials.get("is_cn", False),
        )
        if result.get("requires_mfa"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Garmin 需要两步验证，请完成验证码确认",
            )
        if result.get("is_auth_error"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Garmin 连接已失效，请重新连接账号",
            )
        if result.get("skipped"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Garmin 同步正在进行或暂时受限，请稍后再试",
            )
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Garmin 服务暂时不可用，请稍后再试",
            )

        return GarminSyncResponse(
            success=True,
            message=result.get("message", "Garmin 同步完成"),
            synced_days=result.get("success_count", 0),
            failed_days=result.get("error_count", 0),
            activities_count=result.get("activities_count", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Garmin同步失败 - user_id=%s, error_type=%s",
            current_user.id,
            type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Garmin 服务暂时不可用，请稍后再试",
        ) from e


@router.get("/garmin/sync-stream", summary="流式同步Garmin数据（带进度）")
@limiter.limit("5/minute")  # Garmin 流式同步每分钟最多5次
async def sync_garmin_data_stream(
    request: Request,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """用与 Mobile 相同的真值路径执行同步，并通过 SSE 返回终态。"""
    credentials = garmin_credential_service.get_decrypted_credentials(db, current_user.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证，请先在设置中配置"
        )

    async def generate_progress() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'start', 'total': days, 'message': '开始同步...'})}\n\n"
        yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': days, 'message': '正在连接 Garmin...'})}\n\n"

        try:
            from app.scheduler import sync_user_garmin_data

            result = await sync_user_garmin_data(
                db,
                current_user.id,
                credentials["email"],
                credentials["password"],
                days=days,
                is_cn=credentials.get("is_cn", False),
            )
            if result.get("requires_mfa"):
                error_data = {
                    "type": "error",
                    "message": "Garmin 需要两步验证，请输入验证码",
                    "mfa_required": True,
                }
                if result.get("mfa_session_id"):
                    error_data["mfa_session_id"] = result["mfa_session_id"]
                yield f"data: {json.dumps(error_data)}\n\n"
                return
            if result.get("is_auth_error"):
                yield f"data: {json.dumps({'type': 'error', 'message': 'Garmin 连接已失效，请重新连接账号'})}\n\n"
                return
            if result.get("skipped"):
                yield f"data: {json.dumps({'type': 'error', 'message': 'Garmin 同步正在进行或暂时受限，请稍后再试'})}\n\n"
                return
            if not result.get("success"):
                yield f"data: {json.dumps({'type': 'error', 'message': 'Garmin 服务暂时不可用，请稍后再试'})}\n\n"
                return

            synced_days = result.get("success_count", 0)
            synced_activities = result.get("activities_count", 0)
            message = result.get("message") or (
                "同步完成：未找到新数据"
                if synced_days == 0 and synced_activities == 0
                else "Garmin 同步完成"
            )
            complete_data = {
                "type": "complete",
                "synced": synced_days,
                "failed": 0,
                "activities": synced_activities,
                "message": message,
            }
            yield f"data: {json.dumps(complete_data)}\n\n"

        except Exception as e:
            logger.error(
                "Garmin流式同步失败 - user_id=%s, error_type=%s",
                current_user.id,
                type(e).__name__,
            )
            error_data = {"type": "error", "message": "Garmin 服务暂时不可用，请稍后再试"}
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


@router.post("/garmin/connect", response_model=GarminTestConnectionResponse, summary="原子连接Garmin账号")
@limiter.limit("3/minute")
async def connect_garmin_account(
    request: Request,
    credentials: GarminCredentialCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """先完成 Garmin 认证，再原子替换旧连接；失败时旧连接保持不变。"""
    try:
        from app.services.data_collection.garmin_connect import GarminConnectService

        service = GarminConnectService(
            email=credentials.garmin_email,
            password=credentials.garmin_password,
            is_cn=credentials.is_cn,
            user_id=current_user.id,
        )
        result = await run_garmin_blocking(service.connect_and_save, db)
        return GarminTestConnectionResponse(
            success=result.get("success", False),
            mfa_required=result.get("mfa_required", False),
            message=result.get("message", ""),
            mfa_session_id=result.get("mfa_session_id"),
        )
    except Exception as e:
        from app.services.data_collection.garmin_native_auth import safe_garmin_error_message

        logger.warning(
            "原子连接 Garmin 失败 - user_id=%s, error_type=%s",
            current_user.id,
            type(e).__name__,
        )
        return GarminTestConnectionResponse(
            success=False,
            mfa_required=False,
            message=safe_garmin_error_message(e),
        )


@router.post("/garmin/test-connection", response_model=GarminTestConnectionResponse, summary="测试Garmin连接")
@limiter.limit("3/minute")
async def test_garmin_connection(
    request: Request,
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
        result = await run_garmin_blocking(
            garmin_service.test_connection_with_mfa,
            db=None,
            mfa_purpose="test",
        )

        return GarminTestConnectionResponse(
            success=result.get("success", False),
            mfa_required=result.get("mfa_required", False),
            message=result.get("message", ""),
            mfa_session_id=result.get("mfa_session_id")
        )

    except Exception as e:
        from app.services.data_collection.garmin_native_auth import safe_garmin_error_message

        logger.error(
            "测试 Garmin 连接失败 - user_id=%s, error_type=%s",
            current_user.id,
            type(e).__name__,
        )
        return GarminTestConnectionResponse(
            success=False,
            mfa_required=False,
            message=safe_garmin_error_message(e),
        )


@router.post("/garmin/verify-mfa", response_model=GarminMFAVerifyResponse, summary="验证Garmin两步验证码")
@limiter.limit("5/minute")
async def verify_garmin_mfa(
    request: Request,
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

        logger.info(f"验证 Garmin MFA - user_id={current_user.id}")

        # 使用验证码恢复登录
        result = await run_garmin_blocking(
            verify_mfa_with_session,
            session_id=mfa_request.mfa_session_id,
            mfa_code=mfa_request.mfa_code,
            user_id=current_user.id,
            db=db,
        )

        if result.get("success"):
            logger.info(f"Garmin MFA 验证成功 user_id={current_user.id}")

        return GarminMFAVerifyResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
            session_id=result.get("session_id")  # 返回session_id
        )

    except Exception as e:
        from app.services.data_collection.garmin_native_auth import safe_garmin_error_message

        logger.error(
            "验证 Garmin MFA 失败 - user_id=%s, error_type=%s",
            current_user.id,
            type(e).__name__,
        )
        return GarminMFAVerifyResponse(
            success=False,
            message=safe_garmin_error_message(e),
        )
