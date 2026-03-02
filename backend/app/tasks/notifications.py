"""
通知推送任务
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.notification import UserNotificationSetting
from app.models.smart_plan import WeeklyPlan
from app.services.notification.push_service import PushService
from app.utils.timezone import get_china_now

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
            UserNotificationSetting.enable_sleep_reminder == True,
            UserNotificationSetting.enable_push_notifications == True
        ).all()
        
        push_service = PushService(db)
        sent_count = 0
        
        for setting in settings_list:
            try:
                push_service.send_notification(
                    user_id=setting.user_id,
                    title="💤 睡眠提醒",
                    body="该准备睡觉了，保证充足睡眠，明天精神饱满！"
                )
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
        push_service.send_notification(
            user_id=user_id,
            title="💧 喝水提醒",
            body="别忘了喝水，保持身体水分充足！"
        )
    
    return {"user_id": user_id, "type": "water_reminder"}


@celery_app.task
def send_exercise_reminder(user_id: int):
    """
    发送运动提醒
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        push_service.send_notification(
            user_id=user_id,
            title="🏃 运动提醒",
            body="是时候活动一下了，去完成今天的运动目标吧！"
        )
    
    return {"user_id": user_id, "type": "exercise_reminder"}


@celery_app.task
def send_custom_notification(user_id: int, title: str, body: str):
    """
    发送自定义通知
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        push_service.send_notification(
            user_id=user_id,
            title=title,
            body=body
        )
    
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

        plans = db.query(WeeklyPlan).filter(
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

        plans = db.query(WeeklyPlan).filter(
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

                try:
                    asyncio.get_event_loop().run_until_complete(
                        push_service.send_notification(
                            user_id=plan.user_id,
                            notification_type="plan_reminder",
                            title=f"{emoji} 计划提醒",
                            content=body,
                        )
                    )
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(
                        push_service.send_notification(
                            user_id=plan.user_id,
                            notification_type="plan_reminder",
                            title=f"{emoji} 计划提醒",
                            content=body,
                        )
                    )
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

        if len(parts) <= 1:
            logger.info(f"[健康复盘] 用户 {user_id} 无足够数据，跳过")
            return

        prompt = "\n\n".join(parts)

        # 调用 OpenClaw 多模型分析
        client = OpenClawAnalyzeClient()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            analysis = loop.run_until_complete(client.analyze(prompt))
        finally:
            loop.close()

        # 推送通知
        aggregation = (analysis.get("aggregation") or "")[:200]
        content = aggregation or "今日健康数据已分析完成"
        push_service = PushService(db)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                push_service.send_notification(
                    user_id=user_id,
                    notification_type="daily_insights",
                    title="📊 今日健康复盘",
                    content=content,
                )
            )
            loop.close()
        except Exception as e:
            logger.warning(f"[健康复盘] 推送失败 user={user_id}: {e}")
