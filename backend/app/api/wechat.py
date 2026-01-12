"""微信小程序认证API"""
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from jose import jwt

from app.database import get_db
from app.models.user import User
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# JWT 配置
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


class WechatLoginRequest(BaseModel):
    """微信登录请求"""
    code: str  # wx.login() 获取的临时登录凭证
    nickname: Optional[str] = None  # 用户昵称
    avatar_url: Optional[str] = None  # 头像URL
    invite_code: Optional[str] = None  # 邀请码（新用户注册时必需，老用户登录时可选）


class WechatLoginResponse(BaseModel):
    """微信登录响应"""
    access_token: Optional[str] = None  # 如果未审核，则为None
    token_type: str = "bearer"
    user_id: int
    is_new_user: bool
    nickname: Optional[str]
    merged_user_id: Optional[int] = None  # 如果合并了PC用户，返回PC用户ID
    is_approved: bool = False  # 是否已通过审核
    message: Optional[str] = None  # 提示信息


class WechatUserInfo(BaseModel):
    """微信用户信息（用于更新）"""
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None


def create_access_token(user_id: int) -> str:
    """创建 JWT access token - 使用与 auth.py 相同的密钥"""
    from app.services.auth import auth_service
    return auth_service.create_access_token({"sub": str(user_id)})


async def get_wechat_session(code: str) -> dict:
    """
    用 code 换取微信 session_key 和 openid
    
    微信接口文档: https://developers.weixin.qq.com/miniprogram/dev/api-backend/open-api/login/auth.code2Session.html
    """
    if not settings.wechat_appid or not settings.wechat_secret:
        raise HTTPException(
            status_code=500,
            detail="微信小程序未配置，请在 .env 中设置 WECHAT_APPID 和 WECHAT_SECRET"
        )
    
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_appid,
        "secret": settings.wechat_secret,
        "js_code": code,
        "grant_type": "authorization_code"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
    
    logger.info(f"微信登录响应: {data}")
    
    if "errcode" in data and data["errcode"] != 0:
        error_msg = data.get("errmsg", "未知错误")
        logger.error(f"微信登录失败: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail=f"微信登录失败: {error_msg}"
        )
    
    return data


@router.post("/login", response_model=WechatLoginResponse, summary="微信小程序登录")
async def wechat_login(
    request: WechatLoginRequest,
    db: Session = Depends(get_db)
):
    """
    微信小程序登录
    
    流程:
    1. 前端调用 wx.login() 获取 code
    2. 前端将 code 发送到此接口
    3. 后端用 code 换取 openid 和 session_key
    4. 查找或创建用户
    5. 返回 JWT token
    """
    # 1. 用 code 换取 openid
    wechat_data = await get_wechat_session(request.code)
    
    openid = wechat_data.get("openid")
    session_key = wechat_data.get("session_key")
    unionid = wechat_data.get("unionid")  # 只有绑定了开放平台才有
    
    if not openid:
        raise HTTPException(status_code=400, detail="获取微信 openid 失败")
    
    # 2. 验证邀请码（新用户需要）
    from app.config import settings
    
    # 查找用户
    user = db.query(User).filter(User.wechat_openid == openid).first()
    is_new_user = False
    merged_user_id = None
    
    if not user:
        # 新用户 - 验证邀请码
        if not request.invite_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"新用户注册需要邀请码，请输入邀请码"
            )
        if request.invite_code.upper() != settings.default_invite_code.upper():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"邀请码错误，请输入正确的邀请码"
            )
        
        # 检查是否有匹配的PC用户可以合并
        from app.services.user_merge import UserMergeService
        
        # 先创建临时用户对象用于匹配
        temp_user = User(
            wechat_openid=openid,
            wechat_unionid=unionid,
            wechat_session_key=session_key,
            name=request.nickname or f"微信用户_{openid[-6:]}",
            avatar_url=request.avatar_url,
            is_active=True
        )
        
        # 查找匹配的PC用户
        candidates = UserMergeService.find_potential_merge_candidates(db, temp_user)
        
        if candidates:
            # 找到匹配的用户，合并到第一个匹配的用户
            pc_user = candidates[0]
            logger.info(f"🔗 发现匹配的PC用户 {pc_user.id}，准备合并...")
            
            # 将微信信息添加到PC用户
            pc_user.wechat_openid = openid
            pc_user.wechat_unionid = unionid
            pc_user.wechat_session_key = session_key
            if request.nickname and (not pc_user.name or pc_user.name.startswith("微信用户")):
                pc_user.name = request.nickname
            if request.avatar_url and not pc_user.avatar_url:
                pc_user.avatar_url = request.avatar_url
            
            db.commit()
            db.refresh(pc_user)
            user = pc_user
            merged_user_id = pc_user.id
            logger.info(f"✅ 已合并微信用户到PC用户 {pc_user.id}")
        else:
            # 没有匹配的用户，创建新用户（未审核状态）
            is_new_user = True
            nickname = request.nickname or f"微信用户_{openid[-6:]}"
            
            user = User(
                wechat_openid=openid,
                wechat_unionid=unionid,
                wechat_session_key=session_key,
                name=nickname,
                avatar_url=request.avatar_url,
                is_active=True,
                is_approved=False,  # 需要管理员审核
                invite_code=request.invite_code.upper()
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            logger.info(f"创建新微信用户: {user.id} ({nickname}), 邀请码: {user.invite_code}, 待审核")
    else:
        # 已存在的微信用户 - 更新信息
        user.wechat_session_key = session_key
        if unionid:
            user.wechat_unionid = unionid
        if request.nickname:
            user.name = request.nickname
        if request.avatar_url:
            user.avatar_url = request.avatar_url
        db.commit()
        logger.info(f"微信用户登录: {user.id} ({user.name})")
    
    # 3. 检查审核状态
    if not user.is_approved:
        return WechatLoginResponse(
            access_token=None,
            user_id=user.id,
            is_new_user=is_new_user,
            nickname=user.name,
            merged_user_id=merged_user_id,
            is_approved=False,
            message="注册成功！请等待管理员审核通过后即可使用。"
        )
    
    # 4. 生成 token（已审核用户）
    access_token = create_access_token(user.id)
    
    return WechatLoginResponse(
        access_token=access_token,
        user_id=user.id,
        is_new_user=is_new_user,
        nickname=user.name,
        merged_user_id=merged_user_id,
        is_approved=True,
        message=None
    )


@router.put("/user/info", summary="更新微信用户信息")
async def update_wechat_user_info(
    user_info: WechatUserInfo,
    db: Session = Depends(get_db),
    # 这里应该从 token 中获取当前用户，简化起见先用 openid
):
    """更新用户信息（昵称、头像等）"""
    # TODO: 从 token 中获取用户 ID
    pass


@router.get("/check-bindding/{user_id}", summary="检查用户是否绑定了Garmin")
async def check_garmin_bindding(
    user_id: int,
    db: Session = Depends(get_db)
):
    """检查微信用户是否已绑定 Garmin 账号"""
    from app.models.user import GarminCredential
    
    credential = db.query(GarminCredential).filter(
        GarminCredential.user_id == user_id
    ).first()
    
    return {
        "has_garmin": credential is not None,
        "garmin_email": credential.garmin_email if credential else None,
        "sync_enabled": credential.sync_enabled if credential else False,
        "credentials_valid": credential.credentials_valid if credential else False
    }

