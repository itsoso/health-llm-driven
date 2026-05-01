"""月度复盘报告批量生成任务.

每月 1 日 08:10 运行: 为每个有 Garmin 授权的用户生成上月报告.
"""
import logging
from datetime import date
from calendar import monthrange

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.services.monthly_report_service import MonthlyReportService

logger = logging.getLogger(__name__)


def _previous_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


@celery_app.task(name="app.tasks.monthly_report.generate_previous_month_reports")
def generate_previous_month_reports() -> dict:
    """为所有活跃用户生成上月报告.

    幂等: 若已存在则跳过 (不 force regen), 手动重建用 API.
    """
    today = date.today()
    year, month = _previous_month(today)

    db = SessionLocal()
    svc = MonthlyReportService()
    ok = 0
    skipped = 0
    failed = 0
    try:
        users = db.query(User.id).filter(User.is_active.is_(True)).all()
        for (user_id,) in users:
            try:
                from app.models.monthly_report import MonthlyReport
                existing = db.query(MonthlyReport).filter_by(
                    user_id=user_id, year=year, month=month,
                ).first()
                if existing:
                    skipped += 1
                    continue
                svc.get_or_generate(db, user_id, year, month)
                ok += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[monthly_report] user={user_id} failed: {e}")
                db.rollback()
                failed += 1
    finally:
        db.close()

    summary = {"year": year, "month": month, "generated": ok,
               "skipped": skipped, "failed": failed}
    logger.info(f"[monthly_report] {summary}")
    return summary
