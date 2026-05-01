"""
Celery 配置

用于异步任务和定时任务调度
"""
import logging
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# 确保所有 ORM 模型在 Celery worker 启动时被加载，
# 避免 relationship() lazy resolution 失败（如 UserApiKey）
import app.models.user_api_key  # noqa: F401

# Patch garth 使用 Chrome TLS 指纹（Celery worker 也需要）
from app.services.garmin_cffi_patch import patch_garth_with_cffi
patch_garth_with_cffi()

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
        "app.tasks.intervention_assessment",
        "app.tasks.maintenance",
        "app.tasks.outcome_grader",
        "app.tasks.open_loop_manager",
        "app.tasks.memory_lifecycle",
        "app.tasks.insights",
        "app.tasks.monthly_report",
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

    # 每2小时同步 Garmin 数据（Agent Native: 趋势检测 + session 复用不限流）
    "sync-garmin-2hourly": {
        "task": "app.tasks.garmin_sync.sync_all_users_garmin",
        "schedule": crontab(hour="1,3,5,7,9,11,13,15", minute=1),  # UTC → 北京 09/11/13/15/17/19/21/23 点
    },

    # 每日 22:00 发送睡眠提醒
    "sleep-reminder": {
        "task": "app.tasks.notifications.send_sleep_reminders",
        "schedule": crontab(hour=22, minute=0),
    },

    # 每分钟扫描 medications.reminder_times，匹配就推 APNs（用户一键"已服用"）
    "medication-reminder-scan": {
        "task": "app.tasks.notifications.scan_medication_reminders",
        "schedule": crontab(minute="*"),
    },

    # 每周日 20:30 生成升级版周报 (穿越式反馈引擎)
    # v2: 聚合数据 + 跨实体行动对照 + prediction 中期校验 + 基因对齐度评分
    "weekly-report": {
        "task": "app.tasks.health_analysis.generate_weekly_reports",
        "schedule": crontab(hour=20, minute=30, day_of_week=0),  # 周日 20:30 北京时间
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

    # 每日 23:00 健康异常检测
    "daily-anomaly-check": {
        "task": "app.tasks.notifications.daily_anomaly_check",
        "schedule": crontab(hour=23, minute=0),
    },

    # 每日 22:00 健康趋势分析
    "daily-trend-analysis": {
        "task": "app.tasks.notifications.daily_trend_analysis",
        "schedule": crontab(hour=22, minute=0),
    },

    # 每日 08:30 趋势摘要推送
    "trend-morning-push": {
        "task": "app.tasks.notifications.send_trend_morning_push",
        "schedule": crontab(hour=8, minute=30),
    },

    # 每日 09:30 早安健康摘要（等 Garmin 09:01 同步完成后推送）
    "morning-health-summary": {
        "task": "app.tasks.notifications.send_morning_health_summary",
        "schedule": crontab(hour=1, minute=30),  # UTC 01:30 = 北京 09:30
    },

    # 每12小时续期 Garmin OAuth session
    "renew-garmin-sessions": {
        "task": "app.tasks.garmin_sync.renew_garmin_sessions",
        "schedule": crontab(hour="*/12", minute=15),
    },

    # 每日 09:32 健康简报（写入 AI 对话，等 Garmin 同步后）
    "daily-briefing-message": {
        "task": "app.tasks.notifications.generate_daily_briefing_message",
        "schedule": crontab(hour=1, minute=32),  # UTC 01:32 = 北京 09:32
    },

    # 每日 09:20 Insight 生成 (briefing 前跑, briefing 能读到最新 insight)
    "daily-insight-generate": {
        "task": "app.tasks.insights.generate_daily_insights_all_users",
        "schedule": crontab(hour=1, minute=20),  # UTC 01:20 = 北京 09:20
    },

    # 每周一 09:05 周报（写入 AI 对话）
    "weekly-report-message": {
        "task": "app.tasks.notifications.generate_weekly_report_message",
        "schedule": crontab(hour=9, minute=5, day_of_week=1),
    },

    # Agent Native: 随访提醒（每天 10:00 扫描超期 ActionCard）
    "action-card-followup": {
        "task": "app.tasks.notifications.check_action_card_followups",
        "schedule": crontab(hour=10, minute=0),
    },

    # 保健顾问周度数据摘要 (2026-04-29 重新启用):
    # 推送对象是用户授权的 Telegram advisor_chat_id (单点定向, 不对外广播).
    # 内容为数据摘要 (Garmin 周均值 + 告警 + ActionCard 命中率 + 用药依从 + Journal),
    # 明文标注"不构成医疗建议". 若后续与持证医师合作, 再切换到 email 通道.
    "doctor-weekly-report": {
        "task": "app.tasks.notifications.generate_doctor_weekly_report",
        "schedule": crontab(hour=9, minute=15, day_of_week=1),
    },

    # Agent Native: 干预效果评估（每周一 11:00 LLM 评估 ActionCard 效果）
    "intervention-assessment": {
        "task": "app.tasks.intervention_assessment.assess_active_interventions",
        "schedule": crontab(hour=11, minute=0, day_of_week=1),
    },

    # 每周一 4:00 重建 dedao wiki 知识库索引 (force=True)
    # 防止 wiki 内容更新后 ChromaDB 索引漂移
    "rebuild-knowledge-index": {
        "task": "app.tasks.maintenance.rebuild_knowledge_index",
        "schedule": crontab(hour=4, minute=0, day_of_week=1),
    },

    # 每天 23:55 检查 24h LLM 成本, 超阈值 log warning (Sentry breadcrumb)
    "llm-cost-daily-check": {
        "task": "app.tasks.maintenance.llm_cost_daily_check",
        "schedule": crontab(hour=23, minute=55),
    },

    # 每天 8:00 评分到期的 ActionCard (Specialist 信任循环)
    "grade-action-cards": {
        "task": "app.tasks.outcome_grader.grade_due_action_cards",
        "schedule": crontab(hour=8, minute=0),
    },

    # 每天 7:00 (北京) 主动循环管理 — 扫所有用户的开放健康循环, 推 top 2 条 APNs
    # vertical health agent 的灵魂: AI 主动盯, 不再被动等问.
    "open-loop-manager": {
        "task": "app.tasks.open_loop_manager.run_open_loop_check",
        "schedule": crontab(hour=7, minute=0),
    },

    # 每天 4:00 LLM Wiki v2 lifecycle: decay + crystallization
    # 应用遗忘曲线 + 多次出现的 working facts 升级到 episodic/semantic
    "memory-lifecycle": {
        "task": "app.tasks.memory_lifecycle.run_memory_lifecycle",
        "schedule": crontab(hour=4, minute=0),
    },

    # 周度 Eval Golden Set: 跑 orchestrator suite (调真实 LLM, ~$0.005/次),
    # 监测 LLM 合成质量回归. 失败/regression Telegram 告警.
    "eval-orchestrator-weekly": {
        "task": "app.tasks.eval_runner.run_orchestrator_eval_weekly",
        "schedule": crontab(hour=3, minute=27, day_of_week=0),  # 周日凌晨 03:27
    },

    # 月度复盘报告: 每月 1 日 08:10 生成上月报告
    "monthly-report-generate": {
        "task": "app.tasks.monthly_report.generate_previous_month_reports",
        "schedule": crontab(hour=8, minute=10, day_of_month=1),
    },
}

logger.info("Celery 配置加载完成")
