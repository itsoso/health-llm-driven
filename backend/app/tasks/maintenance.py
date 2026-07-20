"""
系统维护任务
"""
import logging
from datetime import datetime, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


def _agent_runtime_unleased_grace_seconds() -> int:
    from app.config import settings

    configured = int(
        getattr(settings, "agent_runtime_unleased_grace_seconds", 420) or 420
    )
    deadline = int(getattr(settings, "agent_runtime_deadline_seconds", 300) or 300)
    return max(configured, deadline + 120)


@celery_app.task(
    time_limit=55,
    name="app.tasks.maintenance.recover_expired_agent_runs",
)
def recover_expired_agent_runs(*, now_iso: str | None = None):
    """Settle Agent Runs whose worker lease expired.

    The task is intentionally inert while the Runtime control plane is off.
    Recovery never restarts an Executor blindly: read-only runs
    become retryable failures, while uncertain writes require reconciliation.
    Recovery runs before canary circuit evaluation so recoverable leases do not
    create false-positive rollout pauses.
    """
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService,
        runtime_control_enabled,
    )

    if not runtime_control_enabled():
        return {"status": "disabled", "recovered": 0}

    now = datetime.fromisoformat(now_iso) if now_iso else None
    with SessionLocal() as db:
        recovered = AgentRuntimeCoordinator(db).recover_expired_runs(
            now=now,
            limit=100,
            unleased_grace_seconds=_agent_runtime_unleased_grace_seconds(),
        )
        rollout_evaluation = AgentRuntimeRolloutService(
            db
        ).evaluate_and_maybe_pause(now=now)

    failed = sum(item.status == "failed" for item in recovered)
    reconciliation_required = sum(
        item.status == "reconciliation_required" for item in recovered
    )
    logger.info(
        "[agent-runtime] recovered=%s failed=%s reconciliation_required=%s "
        "rollout_status=%s rollout_reason=%s",
        len(recovered),
        failed,
        reconciliation_required,
        rollout_evaluation.transition.status,
        rollout_evaluation.reason_code,
    )
    return {
        "status": "ok",
        "recovered": len(recovered),
        "failed": failed,
        "reconciliation_required": reconciliation_required,
        "rollout": {
            "changed": rollout_evaluation.transition.changed,
            "reason_code": rollout_evaluation.reason_code,
            "status": rollout_evaluation.transition.status,
            "snapshot": rollout_evaluation.snapshot.to_dict(),
        },
    }


@celery_app.task
def cleanup_expired_data():
    """
    清理过期数据（每日凌晨3:00执行）
    """
    logger.info("开始清理过期数据")

    with SessionLocal() as db:
        now = get_china_now()

        from app.api.diet import (
            purge_expired_diet_photo_drafts,
            reconcile_staged_diet_image_deletions,
        )
        purged_diet_photo_drafts = purge_expired_diet_photo_drafts(db)
        reconciled_diet_images = reconcile_staged_diet_image_deletions(db)

        # 清理90天前的已读通知
        from app.models.notification import NotificationLog
        cutoff_date = now - timedelta(days=90)
        deleted_notifications = db.query(NotificationLog).filter(
            NotificationLog.sent_at < cutoff_date
        ).delete()

        db.commit()

        logger.info(
            "清理了 %s 条过期通知、%s 张饮食草稿图片和 %s 个饮食图片 tombstone",
            deleted_notifications,
            purged_diet_photo_drafts,
            reconciled_diet_images,
        )

    return {
        "deleted_notifications": deleted_notifications,
        "purged_diet_photo_drafts": purged_diet_photo_drafts,
        "reconciled_diet_images": reconciled_diet_images,
        "cleanup_time": now.isoformat()
    }


@celery_app.task(name="app.tasks.maintenance.purge_expired_meal_raw_media")
def purge_expired_meal_raw_media():
    """每日 03:05 清除过期的餐食监控原始帧图像 (L3 隐私).

    ``MealMonitoringSession`` 的原始帧 (``VisualInputEvent.image_uri`` /
    ``meta.image_base64``) 在 ``raw_media_delete_at`` (+7d) 后必须物理删除。
    finished-but-unconfirmed / abandoned 的 session 永不调 confirm/abort,
    所以唯一的归零路径就是这个定时巡检。分析笔记 (recognition_result) 保留。

    Fail-loud: 异常向上抛 (会被 Celery 标记任务失败 + 进日志), 绝不静默吞掉 —
    隐私清理失败必须被看见。
    """
    from app.services.meal_monitoring import purge_expired_raw_media

    with SessionLocal() as db:
        purged = purge_expired_raw_media(db)
        logger.info(f"[meal raw-media purge] purged raw media for {purged} session(s)")
        return {"sessions_purged": purged}


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


@celery_app.task(time_limit=600, name="app.tasks.maintenance.rebuild_knowledge_index")
def rebuild_knowledge_index():
    """每周一 4:00 重建得到 wiki 知识库索引 (force=True).

    防止本地 wiki 更新后, ChromaDB 索引仍是旧快照导致 KnowledgeLibrarian
    检索到过期内容.
    """
    try:
        from app.agents.knowledge_librarian.indexer import build_index
        result = build_index(force=True)
        logger.info(f"[Knowledge Index] 重建完成: {result}")
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"[Knowledge Index] 重建失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(time_limit=120, name="app.tasks.maintenance.llm_cost_daily_check")
def llm_cost_daily_check():
    """每天 23:55 检查最近 24h LLM 成本, 超阈值 log warning.

    阈值: 默认 $1/天. 可通过 settings.llm_daily_cost_alert_usd 调整.
    超阈值时:
      1. logger.warning (会进 Sentry breadcrumb 如果配置了 DSN)
      2. 可选: 给 admin 推 APNs (如果 expo_push_token 配置)
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from app.config import settings
    from app.models.llm_usage import LlmUsageLog

    threshold = getattr(settings, "llm_daily_cost_alert_usd", 1.0)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    with SessionLocal() as db:
        row = db.query(
            func.coalesce(func.sum(LlmUsageLog.cost_usd), 0.0).label("cost"),
            func.count(LlmUsageLog.id).label("calls"),
        ).filter(LlmUsageLog.created_at >= since).one()

        cost = float(row.cost or 0.0)
        calls = int(row.calls or 0)

        # 找出最贵的 caller
        top_caller_row = db.query(
            LlmUsageLog.caller,
            func.coalesce(func.sum(LlmUsageLog.cost_usd), 0.0).label("c"),
        ).filter(
            LlmUsageLog.created_at >= since
        ).group_by(LlmUsageLog.caller).order_by(
            func.sum(LlmUsageLog.cost_usd).desc()
        ).first()
        top_caller = top_caller_row.caller if top_caller_row else "n/a"
        top_cost = float(top_caller_row.c) if top_caller_row else 0.0

        msg = (
            f"[LLM Cost] 24h: ${cost:.4f} / {calls} calls | "
            f"top: {top_caller} (${top_cost:.4f}) | threshold: ${threshold:.2f}"
        )
        if cost > threshold:
            logger.warning(f"⚠️  {msg} — 超过阈值")
        else:
            logger.info(msg)

        return {"cost_usd": round(cost, 4), "calls": calls, "threshold_usd": threshold,
                "exceeded": cost > threshold, "top_caller": top_caller}
