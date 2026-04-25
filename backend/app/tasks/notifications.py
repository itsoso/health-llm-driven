"""
通知推送任务
"""
import logging
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import func as sa_func
from sqlalchemy.orm import selectinload
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.notification import UserNotificationSetting
from app.models.smart_plan import WeeklyPlan
from app.services.notification.push_service import PushService
from app.utils.timezone import get_china_now
from app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

# 计划类别 → 提醒时间（中国时间 HH:MM）
PLAN_CATEGORY_TIMES = {
    "exercise": ["17:30"],
    "diet": ["07:30", "11:30", "17:30"],
    "sleep": ["21:30"],
    "health": ["09:00"],
    "mindfulness": ["08:00"],
}


@celery_app.task
def send_sleep_reminders():
    """
    发送睡眠提醒（每晚22:00执行）
    """
    logger.info("开始发送睡眠提醒")

    with SessionLocal() as db:
        # 获取启用了睡眠提醒的用户
        settings_list = db.query(UserNotificationSetting).filter(
            UserNotificationSetting.reminder_enabled == True,
            UserNotificationSetting.enabled == True
        ).all()

        push_service = PushService(db)
        sent_count = 0

        for setting in settings_list:
            try:
                run_async(push_service.send_notification(
                    user_id=setting.user_id,
                    notification_type="reminder",
                    title="💤 睡眠提醒",
                    content="该准备睡觉了，保证充足睡眠，明天精神饱满！"
                ))
                sent_count += 1
            except Exception as e:
                logger.error(f"发送睡眠提醒失败 (user_id={setting.user_id}): {e}")

    logger.info(f"睡眠提醒发送完成，共发送 {sent_count} 条")
    return {"sent_count": sent_count}


@celery_app.task
def send_water_reminder(user_id: int):
    """
    发送喝水提醒
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        run_async(push_service.send_notification(
            user_id=user_id,
            notification_type="reminder",
            title="💧 喝水提醒",
            content="别忘了喝水，保持身体水分充足！"
        ))

    return {"user_id": user_id, "type": "water_reminder"}


@celery_app.task
def send_exercise_reminder(user_id: int):
    """
    发送运动提醒
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        run_async(push_service.send_notification(
            user_id=user_id,
            notification_type="reminder",
            title="🏃 运动提醒",
            content="是时候活动一下了，去完成今天的运动目标吧！"
        ))

    return {"user_id": user_id, "type": "exercise_reminder"}


@celery_app.task
def send_custom_notification(user_id: int, title: str, body: str):
    """
    发送自定义通知
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        run_async(push_service.send_notification(
            user_id=user_id,
            notification_type="custom",
            title=title,
            content=body
        ))

    return {"user_id": user_id, "title": title}


@celery_app.task
def send_plan_morning_reminder():
    """
    发送今日计划提醒（每天 08:00 执行）
    """
    logger.info("开始发送今日计划提醒")

    with SessionLocal() as db:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        day_of_week = today.weekday() + 1

        # N+1 修复: selectinload 一次拉所有 plans + items, 避免每个 plan 触发懒加载
        plans = db.query(WeeklyPlan).options(selectinload(WeeklyPlan.items)).filter(
            WeeklyPlan.week_start == week_start,
            WeeklyPlan.status == "active"
        ).all()

        push_service = PushService(db)
        sent_count = 0

        for plan in plans:
            try:
                today_items = [i for i in plan.items if i.day_of_week == day_of_week and not i.is_completed]
                if not today_items:
                    continue
                titles = [i.title for i in today_items[:3]]
                body = f"今日 {len(today_items)} 项待完成：{', '.join(titles)}"
                if len(today_items) > 3:
                    body += f" 等{len(today_items)}项"
                push_service.send_notification(
                    user_id=plan.user_id,
                    title="📋 今日计划",
                    body=body
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"发送计划提醒失败 (user_id={plan.user_id}): {e}")

    logger.info(f"今日计划提醒发送完成，共发送 {sent_count} 条")
    return {"sent_count": sent_count}


@celery_app.task
def send_plan_evening_summary():
    """
    发送今日计划进度总结（每天 20:00 执行）
    """
    logger.info("开始发送计划进度总结")

    with SessionLocal() as db:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        day_of_week = today.weekday() + 1

        # N+1 修复: selectinload 一次拉所有 plans + items
        plans = db.query(WeeklyPlan).options(selectinload(WeeklyPlan.items)).filter(
            WeeklyPlan.week_start == week_start,
            WeeklyPlan.status == "active"
        ).all()

        push_service = PushService(db)
        sent_count = 0

        for plan in plans:
            try:
                today_items = [i for i in plan.items if i.day_of_week == day_of_week]
                if not today_items:
                    continue
                done = sum(1 for i in today_items if i.is_completed)
                total = len(today_items)
                undone = [i.title for i in today_items if not i.is_completed]

                if done == total:
                    body = f"今日 {total} 项计划全部完成，太棒了！本周完成率 {plan.completion_rate:.0f}%"
                else:
                    body = f"今日完成 {done}/{total} 项"
                    if undone:
                        body += f"，未完成：{', '.join(undone[:3])}"
                push_service.send_notification(
                    user_id=plan.user_id,
                    title="📊 今日进度",
                    body=body
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"发送进度总结失败 (user_id={plan.user_id}): {e}")

    logger.info(f"计划进度总结发送完成，共发送 {sent_count} 条")
    return {"sent_count": sent_count}


@celery_app.task
def send_plan_item_reminders():
    """
    计划分时提醒（每30分钟执行）
    根据计划项的类别，在对应时间点发送提醒。
    """
    now_cn = get_china_now()
    current_hm = now_cn.strftime("%H:%M")
    logger.info(f"[分时提醒] 检查时间 {current_hm}")

    # 判断当前时间匹配哪些类别
    matched_categories = []
    for category, times in PLAN_CATEGORY_TIMES.items():
        if current_hm in times:
            matched_categories.append(category)

    if not matched_categories:
        logger.info(f"[分时提醒] {current_hm} 无匹配类别")
        return {"sent_count": 0, "matched_categories": []}

    logger.info(f"[分时提醒] 匹配类别: {matched_categories}")

    with SessionLocal() as db:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        day_of_week = today.weekday() + 1  # 1=Mon ... 7=Sun

        plans = db.query(WeeklyPlan).filter(
            WeeklyPlan.week_start == week_start,
            WeeklyPlan.status == "active"
        ).all()

        push_service = PushService(db)
        sent_count = 0

        for plan in plans:
            try:
                # 查找今天未完成且匹配类别的 items
                items = [
                    i for i in plan.items
                    if i.day_of_week == day_of_week
                    and not i.is_completed
                    and i.category in matched_categories
                ]
                if not items:
                    continue

                category_emoji = {
                    "exercise": "🏃",
                    "diet": "🍽",
                    "sleep": "💤",
                    "health": "❤️",
                    "mindfulness": "🧘",
                }
                titles = [i.title for i in items[:3]]
                emoji = category_emoji.get(items[0].category, "📋")
                body = f"{', '.join(titles)}"
                if len(items) > 3:
                    body += f" 等{len(items)}项"

                run_async(push_service.send_notification(
                    user_id=plan.user_id,
                    notification_type="plan_reminder",
                    title=f"{emoji} 计划提醒",
                    content=body,
                ))
                sent_count += 1
            except Exception as e:
                logger.error(f"[分时提醒] 发送失败 (user_id={plan.user_id}): {e}")

    logger.info(f"[分时提醒] 完成，发送 {sent_count} 条")
    return {"sent_count": sent_count, "matched_categories": matched_categories}


@celery_app.task(time_limit=600)
def generate_daily_insights_for_all():
    """
    每日多模型健康复盘（20:30执行）
    为当天有 Garmin 数据的活跃用户生成多维度健康分析。
    """
    from app.models.daily_health import GarminData, DietRecord, WorkoutRecord
    from app.services.openclaw_analyze import OpenClawAnalyzeClient

    logger.info("[健康复盘] 开始")
    today = date.today()

    with SessionLocal() as db:
        # 查询今天有 Garmin 数据的用户
        user_ids = [
            r[0] for r in db.query(GarminData.user_id).filter(
                GarminData.record_date == today
            ).distinct().all()
        ]

    logger.info(f"[健康复盘] 发现 {len(user_ids)} 个用户有今日数据")
    analyzed_count = 0

    for user_id in user_ids:
        try:
            _generate_daily_insight_for_user(user_id, today)
            analyzed_count += 1
        except Exception as e:
            logger.error(f"[健康复盘] 用户 {user_id} 失败: {e}")

    logger.info(f"[健康复盘] 完成，分析 {analyzed_count}/{len(user_ids)} 用户")
    return {"analyzed_count": analyzed_count, "total_users": len(user_ids)}


def _generate_daily_insight_for_user(user_id: int, today: date):
    """为单个用户生成每日健康复盘"""
    from app.models.daily_health import GarminData, DietRecord, WorkoutRecord
    from app.services.openclaw_analyze import OpenClawAnalyzeClient

    with SessionLocal() as db:
        # 聚合当日 Garmin 数据
        garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == today
        ).first()

        # 当日饮食
        diets = db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == today
        ).all()

        # 当日运动
        workouts = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.start_time >= datetime.combine(today, datetime.min.time()),
            WorkoutRecord.start_time < datetime.combine(today + timedelta(days=1), datetime.min.time()),
        ).all()

        # 构建分析 prompt
        parts = [f"请对以下用户 {today.strftime('%Y-%m-%d')} 的健康数据进行综合复盘分析，给出亮点、不足和明日建议。\n"]

        if garmin:
            g_lines = ["## Garmin 可穿戴数据"]
            if garmin.steps: g_lines.append(f"- 步数: {garmin.steps}")
            if garmin.avg_heart_rate: g_lines.append(f"- 平均心率: {garmin.avg_heart_rate} bpm")
            if garmin.resting_heart_rate: g_lines.append(f"- 静息心率: {garmin.resting_heart_rate} bpm")
            if garmin.hrv: g_lines.append(f"- HRV: {garmin.hrv}ms ({garmin.hrv_status or ''})")
            if garmin.sleep_score: g_lines.append(f"- 睡眠分数: {garmin.sleep_score}/100")
            if garmin.total_sleep_duration: g_lines.append(f"- 睡眠时长: {garmin.total_sleep_duration}分钟 (深睡{garmin.deep_sleep_duration or 0}分 REM{garmin.rem_sleep_duration or 0}分)")
            if garmin.body_battery_current: g_lines.append(f"- Body Battery: 当前{garmin.body_battery_current} 最高{garmin.body_battery_most_charged or '-'} 最低{garmin.body_battery_lowest or '-'}")
            if garmin.stress_level: g_lines.append(f"- 压力水平: {garmin.stress_level}/100")
            if garmin.calories_burned: g_lines.append(f"- 总消耗: {garmin.calories_burned}kcal (活动{garmin.active_calories or 0}kcal)")
            if garmin.active_minutes: g_lines.append(f"- 活动时间: {garmin.active_minutes}分钟")
            parts.append("\n".join(g_lines))

        if diets:
            d_lines = ["## 饮食记录"]
            total_cal = 0
            for d in diets:
                meal_cn = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}.get(d.meal_type, d.meal_type)
                cal = d.total_calories or 0
                total_cal += cal
                d_lines.append(f"- {meal_cn}: {d.food_items[:100]} ({cal:.0f}kcal)")
            d_lines.append(f"- 合计: {total_cal:.0f}kcal")
            parts.append("\n".join(d_lines))

        if workouts:
            w_lines = ["## 运动记录"]
            for w in workouts:
                dur = f"{w.duration_seconds // 60}分钟" if w.duration_seconds else ""
                dist = f"{w.distance_meters / 1000:.1f}km" if w.distance_meters else ""
                w_lines.append(f"- {w.activity_type}: {dist} {dur} 消耗{w.calories or 0}kcal")
            parts.append("\n".join(w_lines))

        # 基因数据
        try:
            from app.models.genetic_data import GeneticVariant
            variants = db.query(GeneticVariant).filter(
                GeneticVariant.user_id == user_id
            ).order_by(GeneticVariant.risk_level.desc()).all()
            if variants:
                g_lines = ["## 基因检测画像（请结合基因数据给出个性化建议）"]
                for v in variants:
                    risk_tag = {'high': '⚠️', 'medium': '⚡', 'low': '✅'}.get(v.risk_level, '')
                    line = f"- {risk_tag} {v.gene_name}"
                    if v.genotype:
                        line += f" ({v.genotype})"
                    if v.result_label:
                        line += f": {v.result_label}"
                    if v.description:
                        line += f" — {v.description[:80]}"
                    g_lines.append(line)
                parts.append("\n".join(g_lines))
        except Exception as e:
            logger.warning(f"[健康复盘] 获取基因数据失败: {e}")

        if len(parts) <= 1:
            logger.info(f"[健康复盘] 用户 {user_id} 无足够数据，跳过")
            return

        prompt = "\n\n".join(parts)

        # 调用 OpenClaw 多模型分析
        client = OpenClawAnalyzeClient()
        analysis = run_async(client.analyze(prompt))

        # 推送通知
        aggregation = (analysis.get("aggregation") or "")[:200]
        content = aggregation or "今日健康数据已分析完成"
        push_service = PushService(db)
        try:
            run_async(push_service.send_notification(
                user_id=user_id,
                notification_type="daily_insights",
                title="📊 今日健康复盘",
                content=content,
            ))
        except Exception as e:
            logger.warning(f"[健康复盘] 推送失败 user={user_id}: {e}")


@celery_app.task
def daily_anomaly_check():
    """
    每日健康异常检测（23:00执行）
    遍历活跃用户检测健康指标异常
    """
    logger.info("[异常检测] 开始每日健康异常检测")

    from app.models.user import GarminCredential
    from app.services.anomaly_detection_service import AnomalyDetectionService
    from app.utils.timezone import get_china_today

    with SessionLocal() as db:
        # 获取有Garmin设备的活跃用户
        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True
        ).all()
        user_ids = [c.user_id for c in credentials]

        today = get_china_today()
        total_alerts = 0

        for user_id in user_ids:
            try:
                svc = AnomalyDetectionService(db)
                alerts = svc.detect_anomalies(user_id, today)
                if alerts:
                    total_alerts += len(alerts)
                    logger.info(f"[异常检测] 用户 {user_id} 检测到 {len(alerts)} 个异常")
                    try:
                        run_async(svc.send_alerts(user_id, alerts))
                    except Exception as e:
                        logger.warning(f"[异常检测] 推送失败 user={user_id}: {e}")
            except Exception as e:
                logger.error(f"[异常检测] 用户 {user_id} 检测失败: {e}")

    logger.info(f"[异常检测] 完成，共检测 {len(user_ids)} 个用户，发现 {total_alerts} 个异常")

    # Phase 1 Safety Guardian 集成：基于 Twin 的确定性规则裁决
    safety_total = 0
    try:
        from app.agents.safety_guardian import evaluate_safety
        from app.twin.builder import build_twin

        with SessionLocal() as db2:
            for user_id in user_ids:
                try:
                    twin = build_twin(db2, user_id, use_cache=False)
                    report = evaluate_safety(twin)
                    if report.critical_count > 0 or report.high_count > 0:
                        safety_total += report.critical_count + report.high_count
                        logger.warning(
                            f"[Safety Guardian] 用户 {user_id} 发现 "
                            f"{report.critical_count} CRITICAL / {report.high_count} HIGH 告警"
                        )
                        # 写入审计日志
                        try:
                            from app.agents.audit import log_safety_evaluation
                            log_safety_evaluation(
                                db=db2,
                                user_id=user_id,
                                alerts_count=len(report.alerts),
                                result_summary=f"scheduled: {report.critical_count}C/{report.high_count}H/{report.medium_count}M",
                                twin_build_ms=report.twin_build_ms,
                                evaluate_ms=report.evaluate_ms,
                                twin_sources=twin.meta.data_sources,
                            )
                        except Exception:
                            pass

                        # Push CRITICAL/HIGH alerts to user
                        try:
                            push_service = PushService(db2)
                            for alert in report.alerts:
                                if alert.severity.value >= 3:  # HIGH=3, CRITICAL=4
                                    run_async(push_service.send_notification(
                                        user_id=user_id,
                                        notification_type="health_alert",
                                        title=f"⚠️ {alert.title}",
                                        content=alert.message[:120],
                                        data={"screen": "alerts"},
                                    ))
                            logger.info(f"[Safety Guardian] 用户 {user_id} 已推送告警")
                        except Exception as e:
                            logger.warning(f"[Safety Guardian] 用户 {user_id} 推送失败: {e}")
                except Exception as e:
                    logger.error(f"[Safety Guardian] 用户 {user_id} 评估失败: {e}")
    except Exception as e:
        logger.error(f"[Safety Guardian] 模块加载失败: {e}")

    logger.info(f"[Safety Guardian] 定时评估完成，{safety_total} 条高优先级告警")


@celery_app.task(time_limit=600)
def daily_trend_analysis():
    """
    每日健康趋势分析（22:00执行）
    为活跃用户生成各维度健康趋势报告。
    """
    from app.models.user import GarminCredential
    from app.services.health_trend_service import HealthTrendService

    logger.info("[趋势分析] 开始每日趋势分析")

    with SessionLocal() as db:
        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True
        ).all()
        user_ids = [c.user_id for c in credentials]

    logger.info(f"[趋势分析] 发现 {len(user_ids)} 个活跃用户")
    analyzed_count = 0

    for user_id in user_ids:
        try:
            with SessionLocal() as db:
                svc = HealthTrendService(db)
                dims = run_async(svc.analyze_trends(user_id))
                if dims:
                    analyzed_count += 1
                    logger.info(f"[趋势分析] 用户 {user_id} 完成: {dims}")
        except Exception as e:
            logger.error(f"[趋势分析] 用户 {user_id} 失败: {e}")

    logger.info(f"[趋势分析] 完成，分析 {analyzed_count}/{len(user_ids)} 用户")
    return {"analyzed_count": analyzed_count, "total_users": len(user_ids)}


@celery_app.task
def send_trend_morning_push():
    """
    早间趋势摘要推送（08:30执行）
    推送昨日生成的趋势报告摘要。
    """
    from app.models.health_trend import HealthTrendReport

    logger.info("[趋势推送] 开始早间推送")

    with SessionLocal() as db:
        today = date.today()
        yesterday = today - timedelta(days=1)

        reports = db.query(HealthTrendReport).filter(
            HealthTrendReport.report_date == yesterday,
            HealthTrendReport.period == "7d",
        ).all()

        user_reports = {}
        for r in reports:
            user_reports.setdefault(r.user_id, []).append(r)

        push_service = PushService(db)
        sent_count = 0

        for user_id, user_rpts in user_reports.items():
            try:
                risk_items = [r for r in user_rpts if r.risk_alerts]
                if risk_items:
                    body = f"⚠️ {risk_items[0].risk_alerts[0]}"
                else:
                    improving = [r for r in user_rpts if r.trend_direction == "improving"]
                    declining = [r for r in user_rpts if r.trend_direction == "declining"]
                    dim_labels = {"weight": "体重", "sleep": "睡眠", "exercise": "运动", "overall": "综合"}
                    parts = []
                    if improving:
                        parts.append("↑ " + "、".join(dim_labels.get(r.dimension, r.dimension) for r in improving))
                    if declining:
                        parts.append("↓ " + "、".join(dim_labels.get(r.dimension, r.dimension) for r in declining))
                    body = " | ".join(parts) if parts else "各项指标平稳"

                run_async(push_service.send_notification(
                    user_id=user_id,
                    notification_type="trend_report",
                    title="📈 健康趋势",
                    content=body[:200],
                ))
                sent_count += 1
            except Exception as e:
                logger.error(f"[趋势推送] 用户 {user_id} 推送失败: {e}")

    logger.info(f"[趋势推送] 完成，推送 {sent_count} 条")
    return {"sent_count": sent_count}


@celery_app.task
def send_morning_health_summary():
    """
    每日早安健康摘要推送（07:30执行）
    综合昨日健康评分+预警，给用户一条晨间健康问候。
    """
    from app.models.user import GarminCredential
    from app.services.health_score_service import health_score_service
    from app.models.anomaly_alert import AnomalyAlert

    logger.info("[早安推送] 开始每日早安健康摘要")
    yesterday = date.today() - timedelta(days=1)

    with SessionLocal() as db:
        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True
        ).all()
        user_ids = [c.user_id for c in credentials]

        push_service = PushService(db)
        sent_count = 0

        for user_id in user_ids:
            try:
                # 获取昨日健康评分
                result = health_score_service.calculate_daily_score(db, user_id, target_date=yesterday)
                score_part = ""
                if result.get("status") == "ok":
                    score_part = f"昨日健康评分 {result['total_score']}分({result['grade']})"

                # 获取昨晚预警
                alerts = db.query(AnomalyAlert).filter(
                    AnomalyAlert.user_id == user_id,
                    AnomalyAlert.detection_date == yesterday,
                ).all()
                alert_part = ""
                critical = [a for a in alerts if a.severity == "critical"]
                if critical:
                    alert_part = f"⚠️ {critical[0].message}"
                elif alerts:
                    alert_part = f"有{len(alerts)}条健康提醒"

                # 组合消息
                parts = ["早安！"]
                if score_part:
                    parts.append(score_part)
                if alert_part:
                    parts.append(alert_part)
                if not score_part and not alert_part:
                    continue  # 无数据不推送

                body = "，".join(parts) + "。"

                run_async(push_service.send_notification(
                    user_id=user_id,
                    notification_type="morning_summary",
                    title="🌅 早安健康",
                    content=body[:200],
                ))
                sent_count += 1
            except Exception as e:
                logger.error(f"[早安推送] 用户 {user_id} 推送失败: {e}")

    logger.info(f"[早安推送] 完成，推送 {sent_count} 条")
    return {"sent_count": sent_count}


# ---------------------------------------------------------------------------
# 工具函数：写入 OpenClaw "每日健康简报" 对话
# ---------------------------------------------------------------------------

BRIEFING_CONVERSATION_TITLE = "每日健康简报"


def _get_or_create_briefing_conversation(db, user_id: int):
    """获取或创建用户的「每日健康简报」对话"""
    from app.models.openclaw import OpenClawConversation

    conv = db.query(OpenClawConversation).filter(
        OpenClawConversation.user_id == user_id,
        OpenClawConversation.title == BRIEFING_CONVERSATION_TITLE,
    ).first()

    if not conv:
        conv = OpenClawConversation(
            user_id=user_id,
            title=BRIEFING_CONVERSATION_TITLE,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    return conv


def _write_briefing_message(db, user_id: int, content: str):
    """将日报内容作为 assistant 消息写入「每日健康简报」对话"""
    from app.models.openclaw import OpenClawMessage

    conv = _get_or_create_briefing_conversation(db, user_id)
    msg = OpenClawMessage(
        conversation_id=conv.id,
        role="assistant",
        content=content,
    )
    db.add(msg)
    conv.updated_at = datetime.now(UTC)
    db.commit()


WEEKLY_REPORT_TITLE = "每周健康周报"


def _get_or_create_weekly_conversation(db, user_id: int):
    """获取或创建用户的「每周健康周报」独立对话"""
    from app.models.openclaw import OpenClawConversation
    conv = db.query(OpenClawConversation).filter(
        OpenClawConversation.user_id == user_id,
        OpenClawConversation.title == WEEKLY_REPORT_TITLE,
    ).first()
    if not conv:
        conv = OpenClawConversation(user_id=user_id, title=WEEKLY_REPORT_TITLE)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def _write_weekly_report_message(db, user_id: int, content: str):
    """将周报内容写入独立「每周健康周报」对话，与日报分开"""
    from app.models.openclaw import OpenClawMessage
    conv = _get_or_create_weekly_conversation(db, user_id)
    msg = OpenClawMessage(conversation_id=conv.id, role="assistant", content=content)
    db.add(msg)
    conv.updated_at = datetime.now(UTC)
    db.commit()


def _status_emoji(value, good_threshold, bad_threshold, higher_is_better=True):
    """根据阈值返回状态 emoji"""
    if value is None:
        return "❓"
    if higher_is_better:
        return "✅" if value >= good_threshold else ("⚠️" if value >= bad_threshold else "🔴")
    else:
        return "✅" if value <= good_threshold else ("⚠️" if value <= bad_threshold else "🔴")


# ---------------------------------------------------------------------------
# Feature 1: 每日健康简报（写入 AI 对话）
# ---------------------------------------------------------------------------

@celery_app.task(time_limit=120, name="app.tasks.notifications.regenerate_briefing_for_user")
def regenerate_briefing_for_user(user_id: int):
    """
    Garmin 同步完成后为单个用户重新生成今日简报。
    确保简报包含最新同步数据，而不是 07:35 时的旧数据。
    """
    from app.utils.timezone import get_china_today
    today = get_china_today()
    logger.info(f"[简报重生成] 用户 {user_id} — {today}")
    try:
        _generate_daily_briefing_for_user(user_id, today)
    except Exception as e:
        logger.error(f"[简报重生成] 用户 {user_id} 失败: {e}")

    # 同步后实时安全评估
    evaluate_and_push_safety.delay(user_id)


@celery_app.task(time_limit=60, name="app.tasks.notifications.evaluate_and_push_safety")
def evaluate_and_push_safety(user_id: int):
    """
    实时 Safety Guardian 评估：构建 Twin → 运行 47 条规则 → 推送 HIGH/CRITICAL 告警。
    在 Garmin 同步后、数据变更后调用，确保异常第一时间触达用户。
    """
    try:
        from app.agents.safety_guardian import evaluate_safety
        from app.twin.builder import build_twin

        with SessionLocal() as db:
            twin = build_twin(db, user_id, use_cache=False)
            report = evaluate_safety(twin)

            if report.critical_count == 0 and report.high_count == 0:
                return

            logger.warning(
                f"[实时安全评估] 用户 {user_id}: "
                f"{report.critical_count} CRITICAL / {report.high_count} HIGH"
            )

            # 写入审计日志
            try:
                from app.agents.audit import log_safety_evaluation
                log_safety_evaluation(
                    db=db,
                    user_id=user_id,
                    alerts_count=len(report.alerts),
                    result_summary=f"realtime: {report.critical_count}C/{report.high_count}H",
                    twin_build_ms=report.twin_build_ms,
                    evaluate_ms=report.evaluate_ms,
                    twin_sources=twin.meta.data_sources,
                )
            except Exception:
                pass

            # 推送告警
            push_service = PushService(db)
            for alert in report.alerts:
                if alert.severity.value >= 3:
                    try:
                        # 根据规则类型决定 deep_link
                        # SpO2 / 呼吸相关 → 跳夜间血氧分析页
                        # 其他 → 默认跳 /alerts
                        rule_id = alert.rule_id or ""
                        deep_link = "/(tabs)/alerts"
                        if rule_id.startswith("vitals.spo2") or "respiratory" in rule_id:
                            from app.utils.timezone import get_china_now
                            night_date = get_china_now().date().isoformat()
                            deep_link = f"/sleep-spo2-analysis?night_date={night_date}"

                        run_async(push_service.send_notification(
                            user_id=user_id,
                            notification_type="health_alert",
                            title=f"⚠️ {alert.title}",
                            content=alert.message[:120],
                            data={
                                "screen": "alerts",  # legacy fallback
                                "deep_link": deep_link,
                                "rule_id": alert.rule_id,
                            },
                        ))
                    except Exception as e:
                        logger.warning(f"[实时安全评估] 推送失败 user={user_id}: {e}")

    except Exception as e:
        logger.error(f"[实时安全评估] 用户 {user_id} 评估失败: {e}")


@celery_app.task(time_limit=600)
def generate_daily_briefing_message():
    """
    每日健康简报（07:35 执行）
    为有 Garmin 设备的活跃用户生成简报并写入 OpenClaw 对话。
    """
    from app.models.user import GarminCredential
    from app.models.daily_health import GarminData, DietRecord, WaterIntake
    from app.models.anomaly_alert import AnomalyAlert
    from app.models.genetic_data import GeneticVariant
    from app.models.user_profile import UserProfile
    from app.services.health_score_service import health_score_service
    from app.utils.timezone import get_china_today

    logger.info("[每日简报] 开始生成")
    today = get_china_today()
    yesterday = today - timedelta(days=1)

    with SessionLocal() as db:
        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True,
        ).all()
        user_ids = [c.user_id for c in credentials]

    logger.info(f"[每日简报] 发现 {len(user_ids)} 个活跃用户")
    generated_count = 0

    for user_id in user_ids:
        try:
            _generate_daily_briefing_for_user(user_id, yesterday)
            generated_count += 1
        except Exception as e:
            logger.error(f"[每日简报] 用户 {user_id} 失败: {e}")

    logger.info(f"[每日简报] 完成，生成 {generated_count}/{len(user_ids)} 份")
    return {"generated_count": generated_count, "total_users": len(user_ids)}


def _generate_daily_briefing_for_user(user_id: int, target_date: date):
    """为单个用户生成每日健康简报"""
    from app.models.daily_health import GarminData, DietRecord, WaterIntake
    from app.models.anomaly_alert import AnomalyAlert
    from app.models.genetic_data import GeneticVariant
    from app.models.user_profile import UserProfile
    from app.services.health_score_service import health_score_service

    with SessionLocal() as db:
        # 1. Garmin 数据
        garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date,
        ).first()

        if not garmin:
            logger.info(f"[每日简报] 用户 {user_id} 无 {target_date} Garmin 数据，写占位简报")
            date_str = target_date.strftime("%-m月%-d日")
            placeholder = (
                f"🌅 **{date_str} 健康简报**\n\n"
                f"今日 Garmin 数据尚未同步，简报将在数据到位后更新。\n\n"
                f"如需手动同步，可以在 AI 助手中发送「同步 Garmin」。"
            )
            _write_briefing_message(db, user_id, placeholder)
            return

        # 2. 7 日 HRV 均值（用于比较）
        week_ago = target_date - timedelta(days=7)
        hrv_7d_avg = db.query(sa_func.avg(GarminData.hrv)).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= week_ago,
            GarminData.record_date < target_date,
            GarminData.hrv.isnot(None),
        ).scalar()

        # 3. 饮食卡路里
        diet_calories = db.query(sa_func.sum(DietRecord.calories)).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == target_date,
        ).scalar() or 0

        # 4. 饮水量
        water_total = db.query(sa_func.sum(WaterIntake.amount_ml)).filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date == target_date,
        ).scalar() or 0

        # 5. 健康评分
        score_result = health_score_service.calculate_daily_score(db, user_id, target_date=target_date)
        total_score = score_result.get("total_score", "-") if score_result.get("status") == "ok" else "-"

        # 6. 异常预警
        alerts = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.detection_date == target_date,
        ).all()

        # 7. 基因高风险位点（最多 3 个）
        gene_risks = db.query(GeneticVariant).filter(
            GeneticVariant.user_id == user_id,
            GeneticVariant.risk_level == "high",
        ).limit(3).all()

        # 8. 用户健康目标
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id,
        ).first()

        target_steps = profile.target_steps if profile else 8000
        target_water = profile.target_water_ml if profile else 2000

        # --- 构建 Markdown ---
        date_str = target_date.strftime("%-m月%-d日")
        lines = [f"🌅 **{date_str} 健康简报**\n"]

        # 综合评分
        lines.append(f"**综合评分：{total_score}/100**\n")

        # 指标表格
        lines.append("| 指标 | 数值 | 状态 |")
        lines.append("|------|------|------|")

        # 睡眠
        sleep = garmin.sleep_score
        sleep_label = "优秀" if (sleep and sleep >= 80) else ("良好" if (sleep and sleep >= 60) else "待改善")
        sleep_emoji = _status_emoji(sleep, 80, 60, higher_is_better=True)
        lines.append(f"| 睡眠 | {sleep or '-'}分 | {sleep_emoji} {sleep_label} |")

        # HRV
        hrv_val = garmin.hrv
        hrv_line = f"{hrv_val}ms" if hrv_val else "-"
        if hrv_val and hrv_7d_avg and hrv_7d_avg > 0:
            pct_change = ((hrv_val - hrv_7d_avg) / hrv_7d_avg) * 100
            direction = "↑" if pct_change > 0 else "↓"
            hrv_status = f"较7日均值{direction}{abs(pct_change):.0f}%"
            hrv_emoji = "✅" if pct_change >= -5 else "⚠️"
        else:
            hrv_status = ""
            hrv_emoji = "✅" if hrv_val else "❓"
        hrv_display = f"{hrv_line}" + (f" {hrv_status}" if hrv_status else "")
        lines.append(f"| HRV | {hrv_display} | {hrv_emoji} |")

        # 步数
        steps = garmin.steps or 0
        steps_pct = int((steps / target_steps * 100)) if target_steps > 0 else 0
        steps_emoji = "✅" if steps_pct >= 100 else "⚠️"
        steps_label = f"达标{steps_pct}%" if steps_pct >= 100 else f"{steps_pct}%"
        lines.append(f"| 步数 | {steps:,} | {steps_emoji} {steps_label} |")

        # 压力
        stress = garmin.stress_level
        stress_emoji = _status_emoji(stress, 40, 60, higher_is_better=False)
        stress_label = "正常" if (stress and stress <= 40) else ("偏高" if (stress and stress <= 60) else "高")
        lines.append(f"| 压力 | {stress or '-'} | {stress_emoji} {stress_label} |")

        # 身体电量
        battery = garmin.body_battery_most_charged
        battery_emoji = _status_emoji(battery, 80, 50, higher_is_better=True)
        battery_label = "充沛" if (battery and battery >= 80) else ("中等" if (battery and battery >= 50) else "偏低")
        lines.append(f"| 身体电量 | 峰值{battery or '-'} | {battery_emoji} {battery_label} |")

        # 饮水
        water_pct = int((water_total / target_water * 100)) if target_water > 0 else 0
        water_emoji = "✅" if water_pct >= 100 else "⚠️"
        lines.append(f"| 饮水 | {water_total}ml/{target_water}ml | {water_emoji} {water_pct}% |")

        # 今日建议
        suggestions = []

        # HRV 建议
        if hrv_val and hrv_7d_avg and ((hrv_val - hrv_7d_avg) / hrv_7d_avg) < -0.05:
            suggestions.append("HRV轻度下降，建议今天以恢复性运动为主")

        # 饮水建议
        if water_pct < 100:
            deficit = target_water - water_total
            suggestions.append(f"饮水未达标，上午补充{min(deficit, 500)}ml")

        # 基因建议
        for gv in gene_risks:
            desc = gv.description or gv.result_label or ""
            suggestions.append(f"基因提示：{gv.gene_name} {gv.genotype} {desc[:30]}")

        # 异常预警建议
        for alert in alerts[:2]:
            suggestions.append(f"预警：{alert.message[:50]}")

        if suggestions:
            lines.append("\n**📌 今日建议：**")
            for i, s in enumerate(suggestions[:5], 1):
                lines.append(f"{i}. {s}")

        briefing_md = "\n".join(lines)

        # AI 叙事：用 LLM 把数据转为一段自然语言分析
        try:
            from app.services.llm.factory import get_llm_provider
            provider = get_llm_provider()

            data_summary = (
                f"用户昨日数据：睡眠{sleep or '无'}分，HRV {hrv_val or '无'}ms"
                f"（7日均值{hrv_7d_avg:.0f}ms），步数{steps}，压力{stress or '无'}，"
                f"身体电量峰值{battery or '无'}，饮水{water_total}ml/{target_water}ml，"
                f"饮食{diet_calories:.0f}kcal。综合评分{total_score}/100。"
            )
            if gene_risks:
                data_summary += f" 基因高风险：{'、'.join(f'{g.gene_name} {g.genotype}({g.result_label})' for g in gene_risks)}。"
            if alerts:
                data_summary += f" 预警：{'、'.join(a.message[:30] for a in alerts[:2])}。"

            ai_prompt = (
                f"你是一位私人健康顾问。根据以下数据，用3-4句中文写一段温暖、具体、有行动建议的健康分析。"
                f"不要重复数字，而是解读含义和给出建议。语气像朋友聊天，不要太正式。\n\n{data_summary}"
            )

            ai_narrative = run_async(provider.chat(ai_prompt))
            if ai_narrative and len(ai_narrative) > 20:
                briefing_md += f"\n\n---\n\n💬 **AI 解读：**\n{ai_narrative.strip()}"
        except Exception as e:
            logger.warning(f"[每日简报] 用户 {user_id} AI 叙事生成失败（不影响简报）: {e}")

        # 写入对话
        _write_briefing_message(db, user_id, briefing_md)
        logger.info(f"[每日简报] 用户 {user_id} 简报已写入对话")


# ---------------------------------------------------------------------------
# Feature 3: 每周健康报告（写入 AI 对话）
# ---------------------------------------------------------------------------

@celery_app.task(time_limit=600)
def generate_weekly_report_message():
    """
    每周健康报告（周一 09:05 执行）
    收集 7 天数据生成周报并写入 OpenClaw 对话。
    """
    from app.models.user import GarminCredential
    from app.utils.timezone import get_china_today

    logger.info("[周报简报] 开始生成")
    today = get_china_today()

    with SessionLocal() as db:
        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True,
        ).all()
        user_ids = [c.user_id for c in credentials]

    logger.info(f"[周报简报] 发现 {len(user_ids)} 个活跃用户")
    generated_count = 0

    for user_id in user_ids:
        try:
            _generate_weekly_report_for_user(user_id, today)
            generated_count += 1
        except Exception as e:
            logger.error(f"[周报简报] 用户 {user_id} 失败: {e}")

    logger.info(f"[周报简报] 完成，生成 {generated_count}/{len(user_ids)} 份")
    return {"generated_count": generated_count, "total_users": len(user_ids)}


def _generate_weekly_report_for_user(user_id: int, today: date):
    """为单个用户生成周报"""
    from app.models.daily_health import GarminData, DietRecord, WaterIntake, WorkoutRecord
    from app.models.weight import WeightRecord

    this_week_end = today
    this_week_start = today - timedelta(days=7)
    last_week_end = this_week_start
    last_week_start = this_week_start - timedelta(days=7)

    with SessionLocal() as db:
        # --- 本周数据 ---
        this_garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= this_week_start,
            GarminData.record_date < this_week_end,
        ).all()

        if not this_garmin:
            logger.info(f"[周报简报] 用户 {user_id} 本周无 Garmin 数据，跳过")
            return

        # 本周平均值
        def avg_field(records, field):
            vals = [getattr(r, field) for r in records if getattr(r, field) is not None]
            return sum(vals) / len(vals) if vals else None

        tw_steps = avg_field(this_garmin, "steps")
        tw_sleep = avg_field(this_garmin, "sleep_score")
        tw_hrv = avg_field(this_garmin, "hrv")
        tw_rhr = avg_field(this_garmin, "resting_heart_rate")

        # --- 上周数据 ---
        last_garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= last_week_start,
            GarminData.record_date < last_week_end,
        ).all()

        lw_steps = avg_field(last_garmin, "steps")
        lw_sleep = avg_field(last_garmin, "sleep_score")
        lw_hrv = avg_field(last_garmin, "hrv")
        lw_rhr = avg_field(last_garmin, "resting_heart_rate")

        # 运动次数
        workout_count = db.query(sa_func.count(WorkoutRecord.id)).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= this_week_start,
            WorkoutRecord.workout_date < this_week_end,
        ).scalar() or 0

        # 总饮水量
        water_total = db.query(sa_func.sum(WaterIntake.amount_ml)).filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date >= this_week_start,
            WaterIntake.record_date < this_week_end,
        ).scalar() or 0

        # 饮食记录数
        diet_count = db.query(sa_func.count(DietRecord.id)).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= this_week_start,
            DietRecord.record_date < this_week_end,
        ).scalar() or 0

        # 体重变化
        first_weight = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= this_week_start,
            WeightRecord.record_date < this_week_end,
        ).order_by(WeightRecord.record_date.asc()).first()

        last_weight = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= this_week_start,
            WeightRecord.record_date < this_week_end,
        ).order_by(WeightRecord.record_date.desc()).first()

        weight_change = None
        if first_weight and last_weight and first_weight.id != last_weight.id:
            weight_change = last_weight.weight - first_weight.weight

        # --- 构建 Markdown ---
        date_range = f"{this_week_start.strftime('%-m/%-d')}~{(this_week_end - timedelta(days=1)).strftime('%-m/%-d')}"
        lines = [f"📊 **周报 ({date_range})**\n"]

        def _compare(current, previous, unit="", higher_is_better=True):
            """生成对比文字"""
            if current is None:
                return "-"
            text = f"{current:.0f}{unit}"
            if previous is not None and previous > 0:
                pct = ((current - previous) / previous) * 100
                arrow = "↑" if pct > 0 else "↓"
                emoji = ""
                if abs(pct) >= 3:
                    is_good = (pct > 0) == higher_is_better
                    emoji = " ✅" if is_good else " ⚠️"
                text += f" ({arrow}{abs(pct):.0f}%{emoji})"
            return text

        lines.append("| 指标 | 本周均值 | 上周对比 |")
        lines.append("|------|----------|----------|")
        lines.append(f"| 日均步数 | {_compare(tw_steps, None)} | {_compare(tw_steps, lw_steps, higher_is_better=True)} |")
        lines.append(f"| 睡眠评分 | {_compare(tw_sleep, None)}分 | {_compare(tw_sleep, lw_sleep, '分', higher_is_better=True)} |")
        lines.append(f"| HRV | {_compare(tw_hrv, None)}ms | {_compare(tw_hrv, lw_hrv, 'ms', higher_is_better=True)} |")
        lines.append(f"| 静息心率 | {_compare(tw_rhr, None)}bpm | {_compare(tw_rhr, lw_rhr, 'bpm', higher_is_better=False)} |")

        lines.append("")
        lines.append("**📋 本周概览：**")
        lines.append(f"- 运动 {workout_count} 次")
        lines.append(f"- 总饮水 {water_total}ml（日均 {water_total // 7}ml）")
        lines.append(f"- 饮食记录 {diet_count} 条")

        if weight_change is not None:
            direction = "增" if weight_change > 0 else "减"
            lines.append(f"- 体重变化：{direction}{abs(weight_change):.1f}kg（{first_weight.weight:.1f} → {last_weight.weight:.1f}）")

        report_md = "\n".join(lines)

        # 写入独立「每周健康周报」对话（与日报分开，避免混排）
        _write_weekly_report_message(db, user_id, report_md)
        logger.info(f"[周报简报] 用户 {user_id} 周报已写入对话")


# ─────────────────── Agent Native: 随访提醒 ───────────────────


@celery_app.task(time_limit=120)
def check_action_card_followups():
    """
    扫描 ActionCard 待办项，对超期未完成的卡片推送随访提醒。

    规则：
    - card_type='guide' 且 status='active' 且 content 含「待办」段落
    - 创建超过 7 天仍 active 的 recommendation/plan 卡片
    - 每张卡片每 7 天最多提醒 1 次（防骚扰）
    """
    import asyncio
    from app.models.action_card import ActionCard
    from app.models.notification import NotificationLog
    from app.services.notification.push_service import PushService

    logger.info("[随访提醒] 开始扫描")

    now = datetime.now(UTC)
    stale_threshold = now - timedelta(days=7)
    reminder_cooldown = now - timedelta(days=7)

    with SessionLocal() as db:
        # 查找超过7天未完成的 active 卡片
        stale_cards = db.query(ActionCard).filter(
            ActionCard.status == "active",
            ActionCard.card_type.in_(["guide", "plan", "recommendation"]),
            ActionCard.created_at <= stale_threshold,
        ).all()

        if not stale_cards:
            logger.info("[随访提醒] 无超期卡片")
            return {"reminded": 0}

        push_svc = PushService(db)
        reminded = 0

        for card in stale_cards:
            # 检查是否最近已提醒过（通过 notification_log 去重）
            recent_reminder = db.query(NotificationLog).filter(
                NotificationLog.user_id == card.user_id,
                NotificationLog.notification_type == "ai_advice",
                NotificationLog.title.contains(f"卡片#{card.id}"),
                NotificationLog.created_at >= reminder_cooldown,
            ).first()
            if recent_reminder:
                continue

            days_ago = (now - card.created_at.replace(tzinfo=None)).days if card.created_at else 0
            title = f"随访提醒 · 卡片#{card.id}"
            content = f"「{card.title}」已创建 {days_ago} 天，还有未完成的待办事项。打开查看进度。"

            try:
                asyncio.run(push_svc.send_notification(
                    user_id=card.user_id,
                    notification_type="ai_advice",
                    title=title,
                    content=content,
                    data={"card_id": card.id, "card_type": card.card_type},
                ))
                reminded += 1
            except Exception as e:
                logger.warning(f"[随访提醒] 卡片 {card.id} 提醒失败: {e}")

    logger.info(f"[随访提醒] 完成，提醒 {reminded} 张卡片")
    return {"reminded": reminded}


# ─────────────────── Agent Native: 保健医生周报 ───────────────────


@celery_app.task(time_limit=300)
def generate_doctor_weekly_report():
    """
    生成保健医生周报 — 每周一自动运行。

    聚合过去 7 天的健康数据，生成结构化摘要，
    通过 Telegram 推送。便于保健医生快速了解用户状况。
    """
    import asyncio
    from app.models.daily_health import GarminData
    from app.services.notification.telegram_push import TelegramPushService

    logger.info("[医生周报] 开始生成")

    today = date.today()
    week_ago = today - timedelta(days=7)

    with SessionLocal() as db:
        from app.models.user import GarminCredential

        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True,
        ).all()

        telegram = TelegramPushService()
        if not telegram.configured:
            logger.info("[医生周报] Telegram 未配置，跳过")
            return {"status": "skipped", "reason": "telegram_not_configured"}

        generated = 0
        for cred in credentials:
            user_id = cred.user_id
            try:
                user = db.query(User).filter(User.id == user_id).first()
                user_name = user.name if user else f"用户{user_id}"

                # 获取 7 天 Garmin 数据
                garmin_data = db.query(GarminData).filter(
                    GarminData.user_id == user_id,
                    GarminData.record_date >= week_ago,
                    GarminData.record_date <= today,
                ).order_by(GarminData.record_date).all()

                if not garmin_data:
                    continue

                # 计算周均值
                def _avg(attr):
                    vals = [getattr(g, attr) for g in garmin_data if getattr(g, attr) is not None]
                    return round(sum(vals) / len(vals), 1) if vals else None

                def _trend(attr):
                    vals = [getattr(g, attr) for g in garmin_data if getattr(g, attr) is not None]
                    if len(vals) < 3:
                        return "数据不足"
                    first_half = sum(vals[:len(vals)//2]) / (len(vals)//2)
                    second_half = sum(vals[len(vals)//2:]) / (len(vals) - len(vals)//2)
                    diff_pct = (second_half - first_half) / first_half * 100 if first_half else 0
                    if diff_pct > 5:
                        return "↑上升"
                    elif diff_pct < -5:
                        return "↓下降"
                    return "→稳定"

                avg_rhr = _avg("resting_heart_rate")
                avg_hrv = _avg("hrv")
                avg_sleep = _avg("sleep_score")
                avg_stress = _avg("stress_level")
                avg_steps = _avg("steps")
                avg_spo2 = _avg("spo2_avg")

                # 检查本周告警
                from app.models.anomaly_alert import AnomalyAlert
                week_alerts = db.query(AnomalyAlert).filter(
                    AnomalyAlert.user_id == user_id,
                    AnomalyAlert.detection_date >= week_ago,
                ).all()
                alert_summary = f"{len(week_alerts)} 条告警" if week_alerts else "无告警"
                alert_types = list(set(a.alert_type for a in week_alerts))

                report = (
                    f"📊 *{user_name} 周报* ({week_ago} ~ {today})\n\n"
                    f"❤️ 静息心率: {avg_rhr or '-'} bpm ({_trend('resting_heart_rate')})\n"
                    f"💚 HRV: {avg_hrv or '-'} ms ({_trend('hrv')})\n"
                    f"😴 睡眠评分: {avg_sleep or '-'} ({_trend('sleep_score')})\n"
                    f"😤 压力: {avg_stress or '-'} ({_trend('stress_level')})\n"
                    f"👣 日均步数: {int(avg_steps) if avg_steps else '-'}\n"
                    f"🫁 血氧: {avg_spo2 or '-'}%\n\n"
                    f"⚠️ 本周告警: {alert_summary}\n"
                )
                if alert_types:
                    report += f"  类型: {', '.join(alert_types)}\n"

                # 标注关注点
                concerns = []
                if avg_hrv and avg_hrv < 40:
                    concerns.append("HRV 偏低，关注自主神经调节")
                if avg_sleep and avg_sleep < 60:
                    concerns.append("睡眠评分偏低")
                if avg_stress and avg_stress > 50:
                    concerns.append("压力持续偏高")
                if avg_rhr and avg_rhr > 75:
                    concerns.append("静息心率偏高")

                if concerns:
                    report += "\n🔍 *关注点:*\n" + "\n".join(f"  • {c}" for c in concerns)
                else:
                    report += "\n✅ 本周各项指标正常"

                asyncio.run(telegram.send_message(report))
                generated += 1
                logger.info(f"[医生周报] 用户 {user_id} 周报已发送 Telegram")

            except Exception as e:
                logger.warning(f"[医生周报] 用户 {user_id} 生成失败: {e}")

    logger.info(f"[医生周报] 完成，生成 {generated} 份")
    return {"generated": generated}


# ─────────────────────── 用药定时提醒 ────────────────────────

@celery_app.task
def scan_medication_reminders():
    """每分钟扫描 active medications，匹配当前 HH:MM（北京时间）的推 APNs。

    - reminder_times 是 JSONB 数组，例 ["09:00", "14:00", "21:00"]
    - 不去重：只要时间对上就推，一分钟内跑完。下一分钟不会再匹配
    - 失败不影响其他用户 / 药
    """
    from app.models.medication import Medication

    now_cn = get_china_now()
    cur_hhmm = now_cn.strftime("%H:%M")
    today_date = now_cn.date().isoformat()

    sent = 0
    with SessionLocal() as db:
        meds = (
            db.query(Medication)
            .filter(Medication.is_active.is_(True))
            .all()
        )
        push_service = PushService(db)

        for med in meds:
            try:
                times = med.reminder_times or []
                if not isinstance(times, list):
                    continue
                if cur_hhmm not in times:
                    continue

                title = f"💊 用药提醒：{med.name}"
                body_parts = [med.dosage] if med.dosage else []
                body_parts.append(f"现在 {cur_hhmm}，点「已服用」自动打卡。")
                body = "，".join(body_parts)

                run_async(push_service.send_notification(
                    user_id=med.user_id,
                    notification_type="reminder",
                    title=title,
                    content=body,
                    data={
                        "category": "MEDICATION_REMINDER",
                        "reminder_type": "medication",
                        "medication_id": med.id,
                        "medication_name": med.name,
                        "scheduled_time": cur_hhmm,
                        "deep_link": "/(tabs)/record",
                    },
                ))
                sent += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[MedicationReminder] user={med.user_id} med={med.id} 失败: {e}")

    if sent:
        logger.info(f"[MedicationReminder] {today_date} {cur_hhmm} 发送 {sent} 条")
    return {"scheduled_time": cur_hhmm, "sent": sent}
