"""数据完整性巡检 —— 系统自我监控(止血:让管线静默损坏自曝,而非等用户发现)。

每日扫描近期活跃用户,跑 data_integrity 检查,把发现的问题(量纲错/层断连/空目标)
写日志 + 埋点。是"盲点制造机"的解药:这次 session 的 6 个 bug 它本可提前抓。
"""
import logging
from datetime import UTC, datetime, timedelta

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task
def data_integrity_scan():
    """扫描近 30 天有 garmin/化验数据的用户,汇总数据完整性问题。"""
    from sqlalchemy import text
    from app.services.data_integrity import integrity_summary

    logger.info("[数据完整性巡检] 开始")
    with SessionLocal() as db:
        cutoff = (datetime.now(UTC) - timedelta(days=30)).date()
        try:
            rows = db.execute(text(
                "SELECT DISTINCT user_id FROM garmin_data WHERE record_date >= :cut "
                "UNION SELECT DISTINCT user_id FROM medical_indicators"
            ), {"cut": cutoff}).fetchall()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[数据完整性巡检] 取用户失败: {e}")
            return {"error": str(e)}

        user_ids = [int(r[0]) for r in rows if r[0] is not None]
        summary = integrity_summary(db, user_ids)

    if summary["affected_users"]:
        logger.warning(
            f"[数据完整性巡检] ⚠️ {summary['affected_users']}/{summary['scanned']} 用户有问题; "
            f"分类: {summary['by_code']}"
        )
        # 高频问题逐条 warning,便于运维直接看到
        for item in summary["details"][:20]:
            for iss in item["issues"]:
                logger.warning(
                    f"[数据完整性] user={item['user_id']} [{iss['severity']}] "
                    f"{iss['code']}: {iss['detail']} → {iss['fix_hint']}"
                )
    else:
        logger.info(f"[数据完整性巡检] ✅ {summary['scanned']} 用户全部正常")
    return summary
