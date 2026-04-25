"""
系统维护任务
"""
import logging
from datetime import datetime, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.notification import Notification
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


@celery_app.task
def cleanup_expired_data():
    """
    清理过期数据（每日凌晨3:00执行）
    """
    logger.info("开始清理过期数据")

    with SessionLocal() as db:
        now = get_china_now()

        # 清理90天前的已读通知
        cutoff_date = now - timedelta(days=90)
        deleted_notifications = db.query(Notification).filter(
            Notification.is_read == True,
            Notification.sent_at < cutoff_date
        ).delete()

        db.commit()

        logger.info(f"清理了 {deleted_notifications} 条过期通知")

    return {
        "deleted_notifications": deleted_notifications,
        "cleanup_time": now.isoformat()
    }


@celery_app.task
def health_check():
    """
    系统健康检查
    """
    logger.info("执行系统健康检查")

    checks = {
        "database": False,
        "redis": False,
        "timestamp": get_china_now().isoformat()
    }

    # 检查数据库连接
    try:
        with SessionLocal() as db:
            db.execute("SELECT 1")
            checks["database"] = True
    except Exception as e:
        logger.error(f"数据库检查失败: {e}")

    # 检查 Redis 连接
    try:
        from app.celery_app import celery_app
        celery_app.backend.client.ping()
        checks["redis"] = True
    except Exception as e:
        logger.error(f"Redis 检查失败: {e}")

    return checks
