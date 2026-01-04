"""认证相关Schema"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, date


class UserRegister(BaseModel):
    """用户注册"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    name: str = Field(..., min_length=1, max_length=100, description="姓名")


class UserLogin(BaseModel):
    """用户登录"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class Token(BaseModel):
    """访问令牌"""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


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
    created_at: Optional[datetime] = None
    has_garmin_credentials: bool = False
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """用户信息更新"""
    name: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None


class PasswordChange(BaseModel):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class GarminCredentialCreate(BaseModel):
    """创建/更新Garmin凭证"""
    garmin_email: str = Field(..., description="Garmin账号邮箱")
    garmin_password: str = Field(..., description="Garmin账号密码")


class GarminCredentialResponse(BaseModel):
    """Garmin凭证响应（不包含密码）"""
    id: int
    garmin_email: str
    last_sync_at: Optional[datetime] = None
    sync_enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class GarminSyncRequest(BaseModel):
    """Garmin同步请求"""
    days: int = Field(default=7, ge=1, le=730, description="同步天数")


class GarminSyncResponse(BaseModel):
    """Garmin同步响应"""
    success: bool
    message: str
    synced_days: int = 0
    failed_days: int = 0


# 更新Token模型以避免循环引用
Token.model_rebuild()

