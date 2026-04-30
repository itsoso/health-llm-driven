"""Insight Celery tasks — 每日为所有活跃用户生成 DailyInsight."""
from __future__ import annotations

import logging
from datetime import date

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(time_limit=600, name="app.tasks.insights.generate_daily_insights_all_users")
def generate_daily_insights_all_users() -> dict:
    """扫所有活跃用户 (有 Garmin 凭证 or 最近 14 天有 garmin 数据), 生成当日 insight.

    幂等: insight_generator 内部已保证 (user, date) unique.
    """
    from app.services.insight_generator import generate_daily_insight
    from app.models.user import GarminCredential

    today = date.today()
    generated = 0
    skipped = 0
    failed = 0

    with SessionLocal() as db:
        # 有 Garmin 凭证的活跃用户 (同 doctor weekly 标准)
        creds = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True,
        ).all()
        user_ids = [c.user_id for c in creds]

        for uid in user_ids:
            try:
                insight_id = generate_daily_insight(db, uid, today)
                if insight_id:
                    generated += 1
                else:
                    skipped += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                logger.warning(f"[insight_task] user={uid} 失败: {e}")

    logger.info(
        f"[insight_task] 完成: 扫 {len(user_ids)} 个用户, "
        f"生成/已存在 {generated}, 无候选跳过 {skipped}, 失败 {failed}"
    )
    return {
        "users_scanned": len(user_ids),
        "generated": generated,
        "skipped_no_candidate": skipped,
        "failed": failed,
    }
