"""认证相关Schema"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator
from typing import Literal, Optional
from datetime import datetime, date


class UserRegister(BaseModel):
    """用户注册"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    invite_code: str = Field(..., description="邀请码")


class UserLogin(BaseModel):
    """用户登录"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class Token(BaseModel):
    """访问令牌"""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class PhoneCodeRequest(BaseModel):
    """请求手机号验证码"""
    phone: str = Field(..., min_length=5, max_length=32, description="手机号")
    purpose: str = Field(default="login", pattern="^login$", description="验证码用途")


class PhoneCodeResponse(BaseModel):
    """手机号验证码发送结果"""
    message: str
    phone: str
    expires_in_seconds: int
    dev_code: Optional[str] = None


class PhoneCodeLogin(BaseModel):
    """手机号验证码登录/注册"""
    phone: str = Field(..., min_length=5, max_length=32, description="手机号")
    code: str = Field(
        ...,
        min_length=4,
        max_length=12,
        description="验证码",
        json_schema_extra={"writeOnly": True},
    )


class PhoneLoginToken(Token):
    """手机号登录结果"""
    is_new_user: bool = False


class TokenData(BaseModel):
    """令牌数据"""
    user_id: Optional[int] = None
    username: Optional[str] = None


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: Optional[str] = None
    email: Optional[str] = None
    name: str
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    is_approved: bool = False
    created_at: Optional[datetime] = None
    has_garmin_credentials: bool = False
    avatar_url: Optional[str] = None
    onboarding_completed: bool = False
    phone: Optional[str] = None
    phone_verified_at: Optional[datetime] = None
    has_password: bool = False

    model_config = ConfigDict(from_attributes=True)


class PhoneVerificationAuthenticated(PhoneLoginToken):
    outcome: Literal["authenticated"] = "authenticated"


class PhoneVerificationInvitationRequired(BaseModel):
    outcome: Literal["invitation_required"] = "invitation_required"
    verified_phone_ticket: str
    expires_in_seconds: int


class InvitationCredentialInput(BaseModel):
    manual_code: Optional[SecretStr] = None
    link_token: Optional[SecretStr] = None

    @model_validator(mode="after")
    def require_exactly_one_credential(self):
        if (self.manual_code is None) == (self.link_token is None):
            raise ValueError("exactly one invitation credential is required")
        return self


class InvitationInspectResponse(BaseModel):
    valid: bool
    phone_masked: Optional[str] = None
    expires_at: Optional[datetime] = None


class InvitedRegistrationInput(InvitationCredentialInput):
    verified_phone_ticket: SecretStr
    idempotency_key: SecretStr


class UserUpdate(BaseModel):
    """用户信息更新"""
    name: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None


class PasswordChange(BaseModel):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class PasswordSet(BaseModel):
    """设置初始密码"""
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class BindWebLogin(BaseModel):
    """微信用户绑定Web登录凭证"""
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, max_length=100, description="登录密码")


class GarminCredentialCreate(BaseModel):
    """创建/更新Garmin凭证"""
    garmin_email: str = Field(..., description="Garmin账号邮箱")
    garmin_password: str = Field(..., description="Garmin账号密码")
    is_cn: bool = Field(default=False, description="是否使用中国服务器(garmin.cn)")


class GarminCredentialResponse(BaseModel):
    """Garmin凭证响应（不包含密码）"""
    id: int
    garmin_email: str
    is_cn: bool = False
    last_sync_at: Optional[datetime] = None
    sync_enabled: bool = True
    credentials_valid: bool = True  # 凭证是否有效
    requires_mfa: bool = False  # 是否需要两步验证
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GarminSyncRequest(BaseModel):
    """Garmin同步请求"""
    days: int = Field(default=7, ge=1, le=730, description="同步天数")
    mfa_session_id: Optional[str] = Field(default=None, description="MFA会话ID（如果已完成MFA验证）")


class GarminSyncResponse(BaseModel):
    """Garmin同步响应"""
    success: bool
    message: str
    synced_days: int = 0
    failed_days: int = 0
    activities_count: int = 0
    activities_error: Optional[str] = None


class GarminTestConnectionResponse(BaseModel):
    """Garmin测试连接响应"""
    success: bool
    mfa_required: bool = False
    message: str
    mfa_session_id: Optional[str] = None  # MFA 时返回的会话ID


class GarminMFAVerifyRequest(BaseModel):
    """Garmin MFA验证请求"""
    mfa_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6位MFA验证码",
    )
    mfa_session_id: str = Field(..., description="测试连接时返回的MFA会话ID")


class GarminMFAVerifyResponse(BaseModel):
    """Garmin MFA验证响应"""
    success: bool
    message: str
    session_id: Optional[str] = None  # 验证成功后返回的session_id，用于后续同步复用


# 更新Token模型以避免循环引用
Token.model_rebuild()
