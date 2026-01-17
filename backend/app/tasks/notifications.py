"""
通知推送任务
"""
import logging
from datetime import datetime
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.notification import UserNotificationSetting
from app.services.notification.push_service import PushService
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


@celery_app.task
def send_sleep_reminders():
    """
    发送睡眠提醒（每晚22:00执行）
    """
    logger.info("开始发送睡眠提醒")
    
    with SessionLocal() as db:
        # 获取启用了睡眠提醒的用户
        settings_list = db.query(UserNotificationSetting).filter(
            UserNotificationSetting.enable_sleep_reminder == True,
            UserNotificationSetting.enable_push_notifications == True
        ).all()
        
        push_service = PushService(db)
        sent_count = 0
        
        for setting in settings_list:
            try:
                push_service.send_notification(
                    user_id=setting.user_id,
                    title="💤 睡眠提醒",
                    body="该准备睡觉了，保证充足睡眠，明天精神饱满！"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"发送睡眠提醒失败 (user_id={setting.user_id}): {e}")
    
    logger.info(f"睡眠提醒发送完成，共发送 {sent_count} 条")
    return {"sent_count": sent_count}


@celery_app.task
def send_water_reminder(user_id: int):
    """
    发送喝水提醒
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        push_service.send_notification(
            user_id=user_id,
            title="💧 喝水提醒",
            body="别忘了喝水，保持身体水分充足！"
        )
    
    return {"user_id": user_id, "type": "water_reminder"}


@celery_app.task
def send_exercise_reminder(user_id: int):
    """
    发送运动提醒
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        push_service.send_notification(
            user_id=user_id,
            title="🏃 运动提醒",
            body="是时候活动一下了，去完成今天的运动目标吧！"
        )
    
    return {"user_id": user_id, "type": "exercise_reminder"}


@celery_app.task
def send_custom_notification(user_id: int, title: str, body: str):
    """
    发送自定义通知
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        push_service.send_notification(
            user_id=user_id,
            title=title,
            body=body
        )
    
    return {"user_id": user_id, "title": title}
