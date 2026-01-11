"""微信小程序认证API"""
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException
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


class WechatLoginResponse(BaseModel):
    """微信登录响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: int
    is_new_user: bool
    nickname: Optional[str]
    merged_user_id: Optional[int] = None  # 如果合并了PC用户，返回PC用户ID


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
    
    # 2. 查找或创建用户
    user = db.query(User).filter(User.wechat_openid == openid).first()
    is_new_user = False
    merged_user_id = None
    
    if not user:
        # 新用户 - 检查是否有匹配的PC用户可以合并
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
            # 没有匹配的用户，创建新用户
            is_new_user = True
            nickname = request.nickname or f"微信用户_{openid[-6:]}"
            
            user = User(
                wechat_openid=openid,
                wechat_unionid=unionid,
                wechat_session_key=session_key,
                name=nickname,
                avatar_url=request.avatar_url,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            logger.info(f"创建新微信用户: {user.id} ({nickname})")
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
    
    # 3. 生成 token
    access_token = create_access_token(user.id)
    
    return WechatLoginResponse(
        access_token=access_token,
        user_id=user.id,
        is_new_user=is_new_user,
        nickname=user.name,
        merged_user_id=merged_user_id
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

