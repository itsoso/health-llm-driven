"""推送通知 API"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.notification import (
    UserNotificationSetting,
    ReminderConfig,
    NotificationLog,
    NotificationType
)
from app.services.notification.push_service import PushService, PREDEFINED_REMINDERS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification", tags=["notification"])


# ============ Pydantic Models ============

class NotificationSettingsUpdate(BaseModel):
    """推送设置更新"""
    enabled: Optional[bool] = None
    morning_briefing_enabled: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    health_alert_enabled: Optional[bool] = None
    ai_advice_enabled: Optional[bool] = None
    workout_analysis_enabled: Optional[bool] = None
    morning_briefing_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    wechat_enabled: Optional[bool] = None
    ios_push_enabled: Optional[bool] = None
    # H1-B: 告警阈值 + rule opt-out
    alert_severity_threshold: Optional[str] = Field(
        None, pattern=r"^(info|warning|critical)$",
    )
    alert_rule_opt_outs: Optional[List[str]] = None
    # L9 (Karpathy partial autonomy): 告警反应档位
    alert_clarify_mode: Optional[str] = Field(
        None, pattern=r"^(silent|notify|converse)$",
    )


class WeChatBindRequest(BaseModel):
    """微信绑定请求"""
    openid: str
    template_ids: Optional[dict] = None


class IOSDeviceBindRequest(BaseModel):
    """iOS 设备绑定请求"""
    device_token: str
    bundle_id: Optional[str] = None  # variant 后必传, 不传退回默认 life.executor.health


class ReminderCreate(BaseModel):
    """创建提醒"""
    reminder_type: str
    name: str
    reminder_times: List[str]  # ["07:30", "19:00"]
    days_of_week: Optional[List[int]] = [1, 2, 3, 4, 5, 6, 7]
    message: Optional[str] = None


class ReminderUpdate(BaseModel):
    """更新提醒"""
    name: Optional[str] = None
    reminder_times: Optional[List[str]] = None
    days_of_week: Optional[List[int]] = None
    message: Optional[str] = None
    enabled: Optional[bool] = None


class TestPushRequest(BaseModel):
    """测试推送请求"""
    title: str = "测试推送"
    content: str = "这是一条测试推送消息"
    channel: Optional[str] = None  # wechat, ios_apns


# ============ 推送设置 API ============

@router.get("/settings", summary="获取推送设置")
def get_notification_settings(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的推送设置"""
    push_service = PushService(db)
    settings = push_service.get_user_settings(current_user.id)

    if not settings:
        # 返回默认设置
        return {
            "enabled": True,
            "morning_briefing_enabled": True,
            "morning_briefing_time": "07:30",
            "reminder_enabled": True,
            "health_alert_enabled": True,
            "ai_advice_enabled": True,
            "workout_analysis_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "09:00",
            "wechat_enabled": True,
            "wechat_bound": False,
            "ios_push_enabled": True,
            "ios_bound": False,
            "alert_severity_threshold": "warning",
            "alert_rule_opt_outs": [],
            "alert_clarify_mode": "converse",
        }

    return {
        "enabled": settings.enabled,
        "morning_briefing_enabled": settings.morning_briefing_enabled,
        "morning_briefing_time": settings.morning_briefing_time,
        "reminder_enabled": settings.reminder_enabled,
        "health_alert_enabled": settings.health_alert_enabled,
        "ai_advice_enabled": settings.ai_advice_enabled,
        "workout_analysis_enabled": getattr(settings, "workout_analysis_enabled", True),
        "quiet_hours_start": settings.quiet_hours_start,
        "quiet_hours_end": settings.quiet_hours_end,
        "wechat_enabled": settings.wechat_enabled,
        "wechat_bound": bool(settings.wechat_openid),
        "ios_push_enabled": settings.ios_push_enabled,
        "ios_bound": bool(settings.ios_device_token),
        "alert_severity_threshold": settings.alert_severity_threshold or "warning",
        "alert_rule_opt_outs": settings.alert_rule_opt_outs or [],
        "alert_clarify_mode": getattr(settings, "alert_clarify_mode", None) or "converse",
    }


@router.put("/settings", summary="更新推送设置")
def update_notification_settings(
    data: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新推送设置"""
    push_service = PushService(db)

    # 过滤掉 None 值
    updates = {k: v for k, v in data.dict().items() if v is not None}

    settings = push_service.create_or_update_settings(current_user.id, updates)

    return {"message": "设置已更新", "settings": settings}


@router.post("/bind/wechat", summary="绑定微信")
def bind_wechat(
    data: WeChatBindRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """绑定微信 OpenID（用于接收订阅消息）"""
    push_service = PushService(db)

    updates = {"wechat_openid": data.openid}
    if data.template_ids:
        updates["wechat_template_ids"] = data.template_ids

    push_service.create_or_update_settings(current_user.id, updates)

    return {"message": "微信绑定成功"}


@router.post("/bind/ios", summary="绑定 iOS 设备")
def bind_ios_device(
    data: IOSDeviceBindRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """绑定 iOS Device Token（用于接收推送通知）"""
    push_service = PushService(db)

    updates = {"ios_device_token": data.device_token}
    if data.bundle_id:
        updates["ios_bundle_id"] = data.bundle_id
    push_service.create_or_update_settings(current_user.id, updates)

    return {"message": "iOS 设备绑定成功"}


@router.delete("/unbind/wechat", summary="解绑微信")
def unbind_wechat(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """解绑微信"""
    push_service = PushService(db)
    push_service.create_or_update_settings(
        current_user.id,
        {"wechat_openid": None, "wechat_template_ids": None}
    )
    return {"message": "微信已解绑"}


@router.delete("/unbind/ios", summary="解绑 iOS 设备")
def unbind_ios_device(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """解绑 iOS 设备"""
    push_service = PushService(db)
    push_service.create_or_update_settings(
        current_user.id,
        {"ios_device_token": None}
    )
    return {"message": "iOS 设备已解绑"}


# ============ 提醒管理 API ============

@router.get("/reminders", summary="获取提醒列表")
def get_reminders(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的所有提醒"""
    reminders = db.query(ReminderConfig).filter(
        ReminderConfig.user_id == current_user.id
    ).all()

    return {
        "reminders": [
            {
                "id": r.id,
                "reminder_type": r.reminder_type,
                "name": r.name,
                "reminder_times": r.reminder_times,
                "days_of_week": r.days_of_week,
                "message": r.message,
                "enabled": r.enabled
            }
            for r in reminders
        ]
    }


@router.get("/reminders/templates", summary="获取预定义提醒模板")
def get_reminder_templates():
    """获取预定义的提醒类型模板"""
    return {
        "templates": [
            {
                "type": key,
                "name": value["name"],
                "default_times": value["default_times"],
                "default_message": value["message"]
            }
            for key, value in PREDEFINED_REMINDERS.items()
        ]
    }


@router.post("/reminders", summary="创建提醒")
def create_reminder(
    data: ReminderCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建新的提醒"""
    push_service = PushService(db)

    reminder = push_service.create_reminder(
        user_id=current_user.id,
        reminder_type=data.reminder_type,
        name=data.name,
        reminder_times=data.reminder_times,
        days_of_week=data.days_of_week,
        message=data.message
    )

    return {
        "message": "提醒创建成功",
        "reminder": {
            "id": reminder.id,
            "reminder_type": reminder.reminder_type,
            "name": reminder.name,
            "reminder_times": reminder.reminder_times
        }
    }


@router.put("/reminders/{reminder_id}", summary="更新提醒")
def update_reminder(
    reminder_id: int,
    data: ReminderUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新提醒配置"""
    push_service = PushService(db)

    updates = {k: v for k, v in data.dict().items() if v is not None}
    reminder = push_service.update_reminder(reminder_id, current_user.id, updates)

    if not reminder:
        raise HTTPException(status_code=404, detail="提醒不存在")

    return {"message": "提醒已更新"}


@router.delete("/reminders/{reminder_id}", summary="删除提醒")
def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除提醒"""
    push_service = PushService(db)

    if push_service.delete_reminder(reminder_id, current_user.id):
        return {"message": "提醒已删除"}
    else:
        raise HTTPException(status_code=404, detail="提醒不存在")


# ============ 推送历史 API ============

@router.get("/logs", summary="获取推送历史")
def get_notification_logs(
    limit: int = 50,
    notification_type: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取推送历史记录"""
    push_service = PushService(db)
    logs = push_service.get_notification_logs(
        current_user.id,
        limit=limit,
        notification_type=notification_type
    )

    return {
        "logs": [
            {
                "id": log.id,
                "notification_type": log.notification_type,
                "channel": log.channel,
                "title": log.title,
                "content": log.content,
                "status": log.status,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "data": log.data or {},
                "deep_link": (log.data or {}).get("deep_link"),
                # 新结构: channels JSON 列, 为空则前端 fallback 按 channel 列展示 (兼容旧 row)
                "channels": getattr(log, "channels", None),
            }
            for log in logs
        ]
    }


# ============ 测试推送 API ============

@router.post("/test", summary="发送测试推送")
async def send_test_push(
    data: TestPushRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """发送测试推送（用于验证配置）"""
    push_service = PushService(db)

    channels = [data.channel] if data.channel else None

    result = await push_service.send_notification(
        user_id=current_user.id,
        notification_type="test",
        title=data.title,
        content=data.content,
        channels=channels,
        respect_quiet_hours=False
    )

    return result


# ============ 手动触发 API（管理员） ============

@router.post("/trigger/morning-briefing", summary="手动触发早间简报")
async def trigger_morning_briefing(
    user_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """手动触发发送早间简报（管理员功能）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    target_user_id = user_id or current_user.id

    push_service = PushService(db)

    # 生成早间简报
    from app.services.ai_scheduler import AISchedulerService
    ai_scheduler = AISchedulerService(db, target_user_id)
    briefing = ai_scheduler.get_morning_briefing()

    if not briefing:
        return {"success": False, "message": "无法生成早间简报"}

    # 发送推送
    result = await push_service.send_notification(
        user_id=target_user_id,
        notification_type=NotificationType.MORNING_BRIEFING.value,
        title=briefing.get("greeting", "☀️ 早安！"),
        content="点击查看今日健康简报",
        data={"briefing": briefing},
        respect_quiet_hours=False
    )

    return result
