"""微信小程序认证API"""
import json
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.user import User
from app.models.notification import UserNotificationSetting
from app.config import settings
from app.api.deps import get_current_user_required
from app.services.notification.push_service import normalize_morning_sleep_floor_time

logger = logging.getLogger(__name__)
router = APIRouter()

# 配置限流器
limiter = Limiter(key_func=get_remote_address)

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

    async with httpx.AsyncClient(timeout=10.0) as client:
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
@limiter.limit("10/minute")  # 微信登录每分钟最多10次
async def wechat_login(
    request: Request,
    login_request: WechatLoginRequest,
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
    wechat_data = await get_wechat_session(login_request.code)

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
        if settings.registration_invitation_enforcement_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "REGISTRATION_INVITATION_REQUIRED",
                    "message": "新用户需要管理员发送的手机号注册邀请",
                },
            )
        # 新用户 - 验证邀请码
        if not login_request.invite_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新用户注册需要邀请码，请输入邀请码"
            )

        # 验证邀请码：先检查数据库中的邀请码，再检查默认邀请码
        from app.models.invitation import InvitationCode
        invite_code_upper = login_request.invite_code.upper()

        # 查找数据库中的邀请码
        db_invite = db.query(InvitationCode).filter(
            InvitationCode.code == invite_code_upper
        ).first()

        invite_valid = False
        if db_invite and db_invite.is_valid:
            # 数据库邀请码有效
            invite_valid = True
            # 增加使用次数
            db_invite.used_count += 1
            db.commit()
            logger.info(
                "使用数据库邀请码，已使用 %s/%s",
                db_invite.used_count,
                db_invite.max_uses,
            )
        elif invite_code_upper == settings.default_invite_code.upper():
            # 默认邀请码有效
            invite_valid = True
            logger.info("使用默认邀请码")

        if not invite_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邀请码无效或已过期，请输入正确的邀请码"
            )

        # 检查是否有匹配的PC用户可以合并
        from app.services.user_merge import UserMergeService

        # 先创建临时用户对象用于匹配
        temp_user = User(
            wechat_openid=openid,
            wechat_unionid=unionid,
            wechat_session_key=session_key,
            name=login_request.nickname or f"微信用户_{openid[-6:]}",
            avatar_url=login_request.avatar_url,
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
            if login_request.nickname and (not pc_user.name or pc_user.name.startswith("微信用户")):
                pc_user.name = login_request.nickname
            if login_request.avatar_url and not pc_user.avatar_url:
                pc_user.avatar_url = login_request.avatar_url

            db.commit()
            db.refresh(pc_user)
            user = pc_user
            merged_user_id = pc_user.id
            logger.info(f"✅ 已合并微信用户到PC用户 {pc_user.id}")
        else:
            # 没有匹配的用户，创建新用户
            # 邀请码已验证有效，自动审核通过
            is_new_user = True
            nickname = login_request.nickname or f"微信用户_{openid[-6:]}"

            user = User(
                wechat_openid=openid,
                wechat_unionid=unionid,
                wechat_session_key=session_key,
                name=nickname,
                avatar_url=login_request.avatar_url,
                is_active=True,
                is_approved=True,  # 邀请码有效，自动审核通过
                invite_code=login_request.invite_code.upper()
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            logger.info("旧版邀请码创建微信用户: user_id=%s", user.id)
    else:
        # 已存在的微信用户 - 更新信息
        user.wechat_session_key = session_key
        if unionid:
            user.wechat_unionid = unionid
        if login_request.nickname:
            user.name = login_request.nickname
        if login_request.avatar_url:
            user.avatar_url = login_request.avatar_url
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
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新用户信息（昵称、头像等）"""
    update_fields: Dict[str, str] = {}

    if user_info.nickname is not None:
        nickname = user_info.nickname.strip()
        if nickname:
            current_user.name = nickname
            update_fields["nickname"] = nickname

    if user_info.avatar_url is not None:
        avatar_url = user_info.avatar_url.strip()
        if avatar_url:
            current_user.avatar_url = avatar_url
            update_fields["avatar_url"] = avatar_url

    if user_info.gender is not None:
        gender = user_info.gender.strip()
        if gender:
            current_user.gender = gender
            update_fields["gender"] = gender

    if user_info.phone is not None:
        phone = user_info.phone.strip()
        if phone:
            current_user.phone = phone
            update_fields["phone"] = phone

    db.commit()
    db.refresh(current_user)

    logger.info(f"微信用户更新资料: user_id={current_user.id}, fields={sorted(update_fields.keys())}")

    return {
        "success": True,
        "user": {
            "user_id": current_user.id,
            "nickname": current_user.name,
            "avatar_url": current_user.avatar_url,
            "gender": current_user.gender,
            "phone": current_user.phone,
        },
    }


@router.get("/check-bindding/{user_id}", summary="检查用户是否绑定了Garmin")
async def check_garmin_bindding(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """检查微信用户是否已绑定 Garmin 账号"""
    from app.models.user import GarminCredential

    if current_user.id != user_id and not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="无权限查看该用户绑定状态")

    credential = db.query(GarminCredential).filter(
        GarminCredential.user_id == user_id
    ).first()

    return {
        "has_garmin": credential is not None,
        "garmin_email": credential.garmin_email if credential else None,
        "sync_enabled": credential.sync_enabled if credential else False,
        "credentials_valid": credential.credentials_valid if credential else False
    }


# ============ 订阅消息设置 API ============

class SubscribeSettingsRequest(BaseModel):
    """订阅设置请求"""
    template_ids: Dict[str, str]  # {"reminder": "xxx", "morning_briefing": "xxx"}
    enabled: bool = True


class SubscribeSettingsResponse(BaseModel):
    """订阅设置响应"""
    enabled: bool
    wechat_enabled: bool
    template_ids: Optional[Dict[str, str]]
    morning_briefing_enabled: bool
    reminder_enabled: bool
    health_alert_enabled: bool
    ai_advice_enabled: bool
    morning_briefing_time: Optional[str]
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]


@router.post("/subscribe/settings", summary="保存小程序订阅设置")
async def save_subscribe_settings(
    request: SubscribeSettingsRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    保存用户订阅的模板ID

    小程序端调用 wx.requestSubscribeMessage 获取用户授权后，
    将授权的模板ID发送到此接口保存
    """
    # 查找或创建用户通知设置
    settings_record = db.query(UserNotificationSetting).filter(
        UserNotificationSetting.user_id == current_user.id
    ).first()

    if not settings_record:
        settings_record = UserNotificationSetting(
            user_id=current_user.id,
            enabled=request.enabled,
            wechat_enabled=True,
            wechat_openid=current_user.wechat_openid,
            wechat_template_ids=request.template_ids
        )
        db.add(settings_record)
    else:
        # 更新现有设置
        settings_record.enabled = request.enabled
        settings_record.wechat_enabled = True
        if current_user.wechat_openid:
            settings_record.wechat_openid = current_user.wechat_openid

        # 合并模板ID（保留已有的，添加新的）
        existing_templates = settings_record.wechat_template_ids or {}
        # 处理数据库中存储为字符串的JSON
        if isinstance(existing_templates, str):
            try:
                existing_templates = json.loads(existing_templates)
            except (json.JSONDecodeError, TypeError):
                existing_templates = {}
        existing_templates.update(request.template_ids)
        settings_record.wechat_template_ids = existing_templates

    db.commit()
    db.refresh(settings_record)

    logger.info(f"用户 {current_user.id} 保存订阅设置: {request.template_ids}")

    return {
        "success": True,
        "message": "订阅设置已保存",
        "template_count": len(settings_record.wechat_template_ids or {})
    }


@router.get("/subscribe/settings", response_model=SubscribeSettingsResponse, summary="获取订阅设置")
async def get_subscribe_settings(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的订阅设置"""
    settings_record = db.query(UserNotificationSetting).filter(
        UserNotificationSetting.user_id == current_user.id
    ).first()

    if not settings_record:
        # 返回默认设置
        return SubscribeSettingsResponse(
            enabled=False,
            wechat_enabled=False,
            template_ids=None,
            morning_briefing_enabled=True,
            reminder_enabled=True,
            health_alert_enabled=True,
            ai_advice_enabled=True,
            morning_briefing_time="09:00",
            quiet_hours_start="22:00",
            quiet_hours_end="09:00"
        )

    # 处理 JSON 字段（数据库中可能是字符串）
    template_ids = settings_record.wechat_template_ids
    if isinstance(template_ids, str):
        try:
            template_ids = json.loads(template_ids)
        except (json.JSONDecodeError, TypeError):
            template_ids = None

    return SubscribeSettingsResponse(
        enabled=settings_record.enabled,
        wechat_enabled=settings_record.wechat_enabled,
        template_ids=template_ids,
        morning_briefing_enabled=settings_record.morning_briefing_enabled,
        reminder_enabled=settings_record.reminder_enabled,
        health_alert_enabled=settings_record.health_alert_enabled,
        ai_advice_enabled=settings_record.ai_advice_enabled,
        morning_briefing_time=normalize_morning_sleep_floor_time(
            settings_record.morning_briefing_time
        ),
        quiet_hours_start=settings_record.quiet_hours_start,
        quiet_hours_end=normalize_morning_sleep_floor_time(
            settings_record.quiet_hours_end
        )
    )


class UpdateNotificationSettingsRequest(BaseModel):
    """更新通知设置请求"""
    enabled: Optional[bool] = None
    morning_briefing_enabled: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    health_alert_enabled: Optional[bool] = None
    ai_advice_enabled: Optional[bool] = None
    morning_briefing_time: Optional[str] = None  # HH:MM 格式
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


@router.put("/subscribe/settings", summary="更新通知设置")
async def update_notification_settings(
    request: UpdateNotificationSettingsRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新用户的通知设置（开关、时间等）"""
    settings_record = db.query(UserNotificationSetting).filter(
        UserNotificationSetting.user_id == current_user.id
    ).first()

    if not settings_record:
        settings_record = UserNotificationSetting(
            user_id=current_user.id,
            wechat_openid=current_user.wechat_openid
        )
        db.add(settings_record)

    # 更新非空字段
    update_fields = request.dict(exclude_unset=True)
    for key in ("morning_briefing_time", "quiet_hours_end"):
        if key in update_fields and update_fields[key] is not None:
            update_fields[key] = normalize_morning_sleep_floor_time(update_fields[key])
    for field, value in update_fields.items():
        if value is not None and hasattr(settings_record, field):
            setattr(settings_record, field, value)

    db.commit()
    db.refresh(settings_record)

    logger.info(f"用户 {current_user.id} 更新通知设置: {update_fields}")

    return {
        "success": True,
        "message": "设置已更新"
    }
