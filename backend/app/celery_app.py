"""
Celery 配置

用于异步任务和定时任务调度
"""
import logging
from celery import Celery
from celery.schedules import crontab
from app.config import settings

logger = logging.getLogger(__name__)

# 创建 Celery 应用
celery_app = Celery(
    "health_app",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.garmin_sync",
        "app.tasks.notifications",
        "app.tasks.health_analysis",
    ]
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,
    
    # 任务超时
    task_time_limit=300,  # 5分钟
    task_soft_time_limit=240,  # 4分钟软超时
    
    # 结果过期
    result_expires=3600,  # 1小时
    
    # 并发配置
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    
    # 任务重试
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# 定时任务配置 (Beat Schedule)
celery_app.conf.beat_schedule = {
    # 每日 6:00 生成今日计划
    "generate-daily-plan": {
        "task": "app.tasks.health_analysis.generate_daily_plan_for_all",
        "schedule": crontab(hour=6, minute=0),
    },
    
    # 每6小时同步 Garmin 数据（降低频率，避免被封）
    "sync-garmin-6hourly": {
        "task": "app.tasks.garmin_sync.sync_all_users_garmin",
        "schedule": crontab(hour="*/6", minute=0),  # 0:00, 6:00, 12:00, 18:00
    },
    
    # 每日 22:00 发送睡眠提醒
    "sleep-reminder": {
        "task": "app.tasks.notifications.send_sleep_reminders",
        "schedule": crontab(hour=22, minute=0),
    },
    
    # 每周一 9:00 生成周报
    "weekly-report": {
        "task": "app.tasks.health_analysis.generate_weekly_reports",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    
    # 每日清理过期数据
    "cleanup-expired-data": {
        "task": "app.tasks.maintenance.cleanup_expired_data",
        "schedule": crontab(hour=3, minute=0),  # 凌晨3点
    },

    # 每日 08:00 推送今日计划提醒
    "plan-morning-reminder": {
        "task": "app.tasks.notifications.send_plan_morning_reminder",
        "schedule": crontab(hour=8, minute=0),
    },

    # 每日 20:00 推送计划进度总结
    "plan-evening-summary": {
        "task": "app.tasks.notifications.send_plan_evening_summary",
        "schedule": crontab(hour=20, minute=0),
    },

    # 每30分钟检查计划分时提醒
    "plan-item-reminders": {
        "task": "app.tasks.notifications.send_plan_item_reminders",
        "schedule": crontab(minute="0,30"),
    },

    # 每日 20:30 多模型健康复盘
    "daily-health-insights": {
        "task": "app.tasks.notifications.generate_daily_insights_for_all",
        "schedule": crontab(hour=20, minute=30),
    },
}

logger.info("Celery 配置加载完成")
