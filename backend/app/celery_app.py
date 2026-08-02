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
        "app.tasks.system_knowledge_lifecycle",
        "app.tasks.insights",
        "app.tasks.monthly_report",
        "app.tasks.episode_scheduler",
        "app.tasks.episode_reflection",
        "app.tasks.live_run_narrative",
        "app.tasks.live_run_hr_replay",
        "app.tasks.snp_prewarm",
        "app.tasks.observability_digest",
        "app.tasks.longevity_watch",
        "app.tasks.trajectory_watch",
        "app.tasks.adherence_watch",
        "app.tasks.protocol_learning",
        "app.tasks.data_integrity_scan",
        "app.tasks.calendar_tasks",
        "app.tasks.event_reminders",
        "app.tasks.reorder_scan",
        "app.tasks.course_review_materialize",
        "app.tasks.checkup_plan_materialize",
        "app.tasks.write_autonomy_worker",
        "app.tasks.twin_snapshot",
        "app.tasks.contextual_heartbeat",
        "app.tasks.life_event_extraction",
        "app.tasks.aigc_media",
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

    # 每2小时同步 Garmin 数据(Agent Native: 趋势检测 + session 复用不限流)
    "sync-garmin-2hourly": {
        "task": "app.tasks.garmin_sync.sync_all_users_garmin",
        "schedule": crontab(hour="9,11,13,15,17,19,21,23", minute=1),  # 北京 09/11/13/15/17/19/21/23 点
    },

    # 每日 21:30 发送睡眠提醒: 默认 quiet hours 是 22:00, 提前到睡前准备窗口,
    # 避免入睡后 Apple Watch 被普通提醒打扰.
    "sleep-reminder": {
        "task": "app.tasks.notifications.send_sleep_reminders",
        "schedule": crontab(hour=21, minute=30),
    },

    # 每分钟扫描 medications.reminder_times，匹配就推 APNs（用户一键"已服用"）
    "medication-reminder-scan": {
        "task": "app.tasks.notifications.scan_medication_reminders",
        "schedule": crontab(minute="*"),
    },

    # 每分钟扫描"未来 N 分钟将开始的项"→ 事件前提醒(P1-B,会议-10/服药-15/补剂-15/锻炼-20)
    "scan-event-reminders": {
        "task": "app.tasks.event_reminders.scan_event_reminders",
        "schedule": crontab(minute="*"),
    },

    # 每 30 分钟同步各用户外部日历(CalDAV/.ics)→ CalendarEvent,让 timing-solver 忙闲常新
    "sync-all-calendars": {
        "task": "app.tasks.calendar_tasks.sync_all_calendars",
        "schedule": crontab(minute="*/30"),
    },

    # 每 5 分钟扫描静默时段延迟的推送, scheduled_at 到点就 fire
    # 严格不打扰睡眠 (2026-05-11): Critical 也走延迟队列, 紧急穿透走紧急联系人系统
    "flush-delayed-pushes": {
        "task": "app.tasks.notifications.flush_delayed_pushes",
        "schedule": crontab(minute="*/5"),
    },

    # 每小时检查: Critical 告警 24h 仍未决策 → 升级再推 (max 3 次)
    "escalate-critical-unresolved": {
        "task": "app.tasks.notifications.escalate_critical_unresolved",
        "schedule": crontab(minute=15),  # 每小时第 15 分钟跑, 错开整点
    },

    # 每周日 21:07 跑 WeeklyAdvisor — 给活跃用户产 3-5 条本周建议
    # 错开 weekly-report (周日 20:30), 让 weekly_report 的 Specialist 缓存先暖
    "weekly-advisor-run": {
        "task": "app.tasks.notifications.weekly_advisor_run",
        "schedule": crontab(hour=21, minute=7, day_of_week=0),  # 周日 21:07 北京时间
    },

    # 每天 02:30 SNP 详情 LLM 缓存预热 (A 优化, 2026-05-13)
    # 给活跃用户 top 10 高/中风险命中 SNP 调 LLM, 写入 Redis 24h 缓存.
    # 之后用户首次点开 /snp/{rsid} 从 ~15s → ~50ms.
    "snp-detail-prewarm": {
        "task": "app.tasks.snp_prewarm.prewarm_snp_details_for_active_users",
        "schedule": crontab(hour=2, minute=30),
    },

    # 每周日 20:30 生成升级版周报 (穿越式反馈引擎)
    # v2: 聚合数据 + 跨实体行动对照 + prediction 中期校验 + 基因对齐度评分
    "weekly-report": {
        "task": "app.tasks.health_analysis.generate_weekly_reports",
        "schedule": crontab(hour=20, minute=30, day_of_week=0),  # 周日 20:30 北京时间
    },

    # E 改进: 每周日 20:00 推送"本周聊聊?"邀请 → voice-chat 主动开口
    # 比 weekly-report 早 30 分钟, 让用户先听语音邀请, 没接的话 20:30 还有文字版兜底
    "weekly-review-invite": {
        "task": "app.tasks.notifications.send_weekly_review_invite",
        "schedule": crontab(hour=20, minute=0, day_of_week=0),  # 周日 20:00 北京时间
    },

    # 每日清理过期数据
    "cleanup-expired-data": {
        "task": "app.tasks.maintenance.cleanup_expired_data",
        "schedule": crontab(hour=3, minute=0),  # 凌晨3点
    },

    # 每分钟先回收失去 worker lease 的云端 Agent Run，再评估灰度熔断信号。
    # 任务仅在 Runtime off 时为空操作；不盲目重跑未决写操作。
    "recover-expired-agent-runs": {
        "task": "app.tasks.maintenance.recover_expired_agent_runs",
        "schedule": crontab(minute="*"),
    },

    # 每日 03:05 清除过期餐食监控原始帧图像 (L3 隐私, +7d TTL)
    # 紧随 03:00 数据清理, 让 finished-but-unconfirmed / abandoned session 的
    # 原始 base64 / image_uri 到期后真正归零 (唯一兜底路径)。
    "purge-meal-raw-media": {
        "task": "app.tasks.maintenance.purge_expired_meal_raw_media",
        "schedule": crontab(hour=3, minute=5),  # 凌晨3:05
    },

    # 每日数据完整性巡检(系统自我监控:量纲错/层断连/空目标静默损坏自曝)
    "data-integrity-scan": {
        "task": "app.tasks.data_integrity_scan.data_integrity_scan",
        "schedule": crontab(hour=4, minute=0),  # 凌晨4点
    },

    # 每日 09:10 推送今日计划提醒: 09:00 quiet-hours floor 后再启动,
    # 避免 07:00/08:00 附近任何用户可见通知影响睡眠。
    "plan-morning-reminder": {
        "task": "app.tasks.notifications.send_plan_morning_reminder",
        "schedule": crontab(hour=9, minute=10),
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

    # 每日 09:25 趋势摘要推送: 避开 07:00/08:00 睡眠保护窗口。
    "trend-morning-push": {
        "task": "app.tasks.notifications.send_trend_morning_push",
        "schedule": crontab(hour=9, minute=25),
    },

    # 每日 09:30 早安健康摘要(等 Garmin 09:01 同步完成后推送)
    "morning-health-summary": {
        "task": "app.tasks.notifications.send_morning_health_summary",
        "schedule": crontab(hour=9, minute=30),  # 北京 09:30
    },

    # 每12小时续期 Garmin OAuth session
    "renew-garmin-sessions": {
        "task": "app.tasks.garmin_sync.renew_garmin_sessions",
        "schedule": crontab(hour="*/12", minute=15),
    },

    # 每日 09:32 健康简报(写入 AI 对话,等 Garmin 同步后)
    "daily-briefing-message": {
        "task": "app.tasks.notifications.generate_daily_briefing_message",
        "schedule": crontab(hour=9, minute=32),  # 北京 09:32
    },

    # 每日 09:20 Insight 生成 (briefing 前跑, briefing 能读到最新 insight)
    "daily-insight-generate": {
        "task": "app.tasks.insights.generate_daily_insights_all_users",
        "schedule": crontab(hour=9, minute=20),  # 北京 09:20
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

    # 每周一 04:10 拉取在线 dedao-kbase export, 只写 draft artifacts, 等待人工 review。
    "dedao-kbase-export-sync": {
        "task": "app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_export_draft",
        "schedule": crontab(hour=4, minute=10, day_of_week=1),
    },

    # 每五分钟发送去标识化的实际引用和人工拒绝反馈；失败保留 outbox 游标供下次重试。
    "dedao-kbase-feedback-flush": {
        "task": "app.tasks.system_knowledge_lifecycle.flush_dedao_kbase_feedback",
        "schedule": crontab(minute="*/5"),
    },

    # 每周一 04:30 系统级 KB 生命周期维护:
    # lint + confidence decay + multi-user crystallize draft report.
    "system-kb-lifecycle": {
        "task": "app.tasks.system_knowledge_lifecycle.run_system_kb_lifecycle",
        "schedule": crontab(hour=4, minute=30, day_of_week=1),
    },

    # 每周一 04:50 重建系统级 KB 检索索引并落 pgvector health audit。
    # 位于 dedao export draft sync + lifecycle/eval 之后,让运营看板能直接看最新 serving 索引状态。
    "system-kb-reindex": {
        "task": "app.tasks.system_knowledge_lifecycle.run_system_kb_reindex",
        "schedule": crontab(hour=4, minute=50, day_of_week=1),
    },

    # 每天 23:55 检查 24h LLM 成本, 超阈值 log warning (Sentry breadcrumb)
    "llm-cost-daily-check": {
        "task": "app.tasks.maintenance.llm_cost_daily_check",
        "schedule": crontab(hour=23, minute=55),
    },

    # 每天 8:00 评分到期的 ActionCard (单一 outcome 评分路径, 写 accuracy_score + outcome + effect_size).
    # 2026-05-16 起 verify_outcomes 已并入此任务, 不再有双路径.
    "grade-action-cards": {
        "task": "app.tasks.outcome_grader.grade_due_action_cards",
        "schedule": crontab(hour=8, minute=0),
    },

    # 每天 09:15 (北京) 主动循环管理 — 扫所有用户的开放健康循环, 推 top 2 条 APNs
    # vertical health agent 的灵魂: AI 主动盯, 不再被动等问.
    # 时间点: 默认 quiet_hours 结束是 09:00, 留 15min 缓冲避免边界用户被打扰.
    "open-loop-manager": {
        "task": "app.tasks.open_loop_manager.run_open_loop_check",
        "schedule": crontab(hour=9, minute=15),
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

    # 月度复盘报告: 每月 1 日 09:12 生成上月报告, 不在早晨静默窗口内触发用户提醒。
    "monthly-report-generate": {
        "task": "app.tasks.monthly_report.generate_previous_month_reports",
        "schedule": crontab(hour=9, minute=12, day_of_month=1),
    },

    # Agent-Native v3 Increment 3 §3 — Episode action 时间窗扫描:
    # 每分钟扫一次, 推 due reminders + 翻 expired actions + 触发 auto-close.
    "episode-action-window-scan": {
        "task": "app.tasks.episode_scheduler.scan_episode_action_windows",
        "schedule": crontab(minute="*"),
    },

    # Agent-Native v3 Increment 4 §1 — Episode Reflection 回填:
    # 每天早上 09:43 北京 (Garmin 同步 09:01 完成后),
    # 对最近关闭的 Episode 拉次日 HRV/Sleep, 写 metrics_delta + summary.
    "episode-reflection": {
        "task": "app.tasks.episode_reflection.run_episode_reflection",
        "schedule": crontab(hour=9, minute=43),  # 北京 09:43
    },

    # 每周一 09:50 客户端遥测周报 — 聚合 client_events (starter CTR / 冷启动 p50p95 /
    # 行为计数) 并 log 结构化摘要, 让埋点数据有人看 (push 半, pull 半在 /admin/observability).
    "client-events-weekly-digest": {
        "task": "app.tasks.observability_digest.client_events_weekly_digest",
        "schedule": crontab(hour=9, minute=50, day_of_week=1),  # 北京 周一 09:50
    },

    # 抗衰主动 Agent: 每周日 10:10 扫生物年龄跨快照显著变化 (Phase2 W1)
    "longevity-watch-weekly": {
        "task": "app.tasks.longevity_watch.longevity_watch",
        "schedule": crontab(hour=10, minute=10, day_of_week=0),  # 北京 周日 10:10
    },

    # 主动化推广: 每周日 10:25 扫代谢/心血管指标跨快照显著变化 (Phase3)
    "trajectory-watch-weekly": {
        "task": "app.tasks.trajectory_watch.trajectory_watch",
        "schedule": crontab(hour=10, minute=25, day_of_week=0),  # 北京 周日 10:25
    },

    # 每日 09:35 生成周期 TwinSnapshot:Garmin 09:01 同步后形成时间序列锚点,
    # 让 trajectory_watch/longevity_watch 不再只依赖 intervention cycle 快照。
    "periodic-twin-snapshot-daily": {
        "task": "app.tasks.twin_snapshot.periodic_twin_snapshot",
        "schedule": crontab(hour=9, minute=35),  # 北京 09:35
    },

    # 依从性智能: 每周日 10:40 扫 N-of-1 掉队风险, 温和再激活 (Next Horizon)
    "adherence-watch-weekly": {
        "task": "app.tasks.adherence_watch.adherence_watch",
        "schedule": crontab(hour=10, minute=40, day_of_week=0),  # 北京 周日 10:40
    },

    # P6 学习闭环: 每周日 10:50 聚合协议完成/跳过/逾期 → 人体工学调参建议(SUGGEST-ONLY,
    # 落审计不推送不改协议不调药量;建议在 /corrections + 议程呈现,用户点 apply 才生效)
    "protocol-learning-watch-weekly": {
        "task": "app.tasks.protocol_learning.protocol_learning_watch",
        "schedule": crontab(hour=10, minute=50, day_of_week=0),  # 北京 周日 10:50
    },

    # P3(D1)每日复购扫描:补剂快用完 → 提议补货 write_intent + 稀缺门推送(不下单)
    "reorder-scan-daily": {
        "task": "app.tasks.reorder_scan.scan_reorder_nudges",
        "schedule": crontab(hour=9, minute=10),  # 北京 09:10
    },

    # 每日 06:10 物化「用药疗程结束 → 复查」日历(ReviewSchedule),让议程的药程复查投影有行可显。
    # 紧随 06:00 daily-plan;ensure_review_schedules 幂等((user_id, item_name, next_due_date)),
    # 每日重跑安全(不重复建,随疗程推进补建新进窗口的复查)。
    "materialize-course-reviews": {
        "task": "app.tasks.course_review_materialize.materialize_course_reviews",
        "schedule": crontab(hour=6, minute=10),  # 北京 06:10
    },

    # 每日 06:15 物化「按年龄·性别的人群筛查」复查计划(R7,ReviewSchedule),议程投影直接消费。
    # 幂等(同名未完成项即跳过),只扫有出生日期的用户;advisory 人群筛查,非处方/非诊断。
    "materialize-checkup-plans": {
        "task": "app.tasks.checkup_plan_materialize.materialize_checkup_plans",
        "schedule": crontab(hour=6, minute=15),  # 北京 06:15
    },

    # Write 自治层(B):每 30 分钟扫有 eligible pending(measurement_prompt)的用户,无人确认自动执行。
    # 把首切片挂在 GET /write-intents 懒路径上的自动执行解耦到后台(无 HTTP 请求事务 → safety gate
    # 里的 build_twin 安全);allowlist/每日上限原子槽/安全门/priority=low 全不变,与 GET 路径靠
    # cap 原子槽 + confirm 原子认领去重,不会双写。见 write_autonomy_worker.run_write_autonomy_sweep。
    "write-autonomy-sweep": {
        "task": "app.tasks.write_autonomy_worker.run_write_autonomy_sweep",
        "schedule": crontab(minute="*/30"),  # 每 30 分钟(Asia/Shanghai)
    },

    # 情境心跳(Slice 2, v1 零 LLM):每 30 分钟一 tick。beat 时区是 Asia/Shanghai,
    # 无条件 fire;白天窗(08–22)按**用户时区**在任务内 get_user_now → is_daytime 收口,
    # 夜间用户自动跳过。每 tick 读 Twin(缓存) → 4 条确定性触发规则 → 过打扰预算硬闸 → push。
    # 全天 fire 以覆盖非中国时区用户;绝大多数夜间 tick 在白天门前即跳过(不建 Twin)。
    "contextual-heartbeat": {
        "task": "app.tasks.contextual_heartbeat.contextual_heartbeat",
        "schedule": crontab(minute="0,30"),  # 每 30 分钟(Asia/Shanghai)
    },

    # Wan 短视频为异步任务；每分钟轮询 active 状态并把短期 Provider 结果转存为私有文件。
    "aigc-media-reconcile": {
        "task": "app.tasks.aigc_media.reconcile_aigc_media_jobs",
        "schedule": crontab(minute="*"),
    },
}

logger.info("Celery 配置加载完成")
