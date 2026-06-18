"""日历定时同步(Celery beat)。

把各用户已启用的外部日历源(CalDAV/.ics)周期性拉进 CalendarEvent,让 timing-solver 的
今日忙闲块始终新鲜(不依赖用户手动/开屏触发)。fail-soft:单用户失败不影响其他用户。
"""
import logging

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task
def sync_all_calendars():
    """同步所有「有启用日历源」用户的外部日历(每 30 分钟)。单用户失败 fail-soft。"""
    from app.models.calendar_sync import CalendarSource
    from app.services.caldav_sync import sync_all_sources

    with SessionLocal() as db:
        user_ids = [
            uid for (uid,) in db.query(CalendarSource.user_id)
            .filter(CalendarSource.sync_enabled.is_(True))
            .distinct()
            .all()
        ]

    ok, failed = 0, 0
    for uid in user_ids:
        try:
            with SessionLocal() as db:  # 每用户独立会话,失败回滚不污染他人
                sync_all_sources(db, uid)
                ok += 1
        except Exception as e:  # fail-soft:单用户炸不影响批量
            failed += 1
            logger.warning("[calendar-autosync] user=%s 同步失败: %s", uid, e)

    logger.info("[calendar-autosync] 完成 users=%s ok=%s failed=%s", len(user_ids), ok, failed)
    return {"users": len(user_ids), "ok": ok, "failed": failed}
