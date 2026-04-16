"""Garmin 同步去重锁 — 防止多个入口并发同步同一用户"""
import logging
from datetime import UTC, datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SYNC_LOCK_TIMEOUT_MINUTES = 15  # 超时自动释放（防止进程崩溃后死锁）


def acquire_sync_lock(db: Session, user_id: int) -> bool:
    """
    原子性地获取用户同步锁。

    Returns:
        True: 获取成功，可以开始同步
        False: 另一个同步正在进行中
    """
    timeout_threshold = datetime.now(UTC) - timedelta(minutes=SYNC_LOCK_TIMEOUT_MINUTES)

    try:
        result = db.execute(
            text(
                "UPDATE garmin_credentials "
                "SET sync_in_progress = true, sync_started_at = :now "
                "WHERE user_id = :uid "
                "AND (sync_in_progress = false OR sync_started_at < :timeout OR sync_started_at IS NULL)"
            ),
            {"uid": user_id, "now": datetime.now(UTC), "timeout": timeout_threshold}
        )
        db.commit()
        acquired = result.rowcount == 1
        if not acquired:
            logger.warning(f"[用户 {user_id}] 同步锁获取失败：另一个同步正在进行中")
        return acquired
    except Exception as e:
        logger.warning(f"[用户 {user_id}] 同步锁获取异常: {e}")
        db.rollback()
        return False


def release_sync_lock(db: Session, user_id: int):
    """释放用户同步锁"""
    try:
        db.execute(
            text(
                "UPDATE garmin_credentials "
                "SET sync_in_progress = false, sync_started_at = NULL "
                "WHERE user_id = :uid"
            ),
            {"uid": user_id}
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[用户 {user_id}] 同步锁释放异常: {e}")
        db.rollback()
