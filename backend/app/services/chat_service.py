"""
聊天服务 - 通过 OpenClaw 提供 AI 对话能力
利用 OpenClaw 的 OpenAI 兼容 API，注入用户健康上下文
"""
import logging
import asyncio
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.basic_health import BasicHealthData
from app.models.daily_health import GarminData, DietRecord, ExerciseRecord, WorkoutRecord
from app.models.checkin import CheckinRecord, CheckinTemplate
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.chat import ChatConversation, ChatMessage
from app.services.environment.weather_service import weather_service

logger = logging.getLogger(__name__)

# OpenClaw 配置
OPENCLAW_BASE_URL = settings.openclaw_base_url
OPENCLAW_API_KEY = settings.openclaw_api_key or ""
OPENCLAW_MODEL = settings.openclaw_model


class ChatService:
    """聊天服务"""

    def __init__(self, db: Session):
        self.db = db

    async def _build_health_context(self, user_id: int) -> str:
        """构建用户健康上下文，注入为 system prompt"""
        parts = []
        today = date.today()

        # 用户基本信息
        user = self.db.query(User).filter(User.id == user_id).first()
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        # 用户位置信息
        user_city = None
        if profile:
            # 优先使用手动设置的位置
            if profile.use_manual_location and profile.manual_city:
                user_city = profile.manual_city
                location_info = f"位置: {profile.manual_region or ''}{user_city}"
                parts.append(location_info)
            # 其次使用IP检测的位置
            elif profile.detected_city:
                user_city = profile.detected_city
                location_info = f"位置: {profile.detected_region or ''}{user_city}"
                parts.append(location_info)
            # 兜底使用city字段
            elif profile.city:
                user_city = profile.city
                parts.append(f"位置: {user_city}")

        # 获取当前天气信息（异步调用）
        if user_city:
            try:
                weather = await weather_service.get_current_weather(user_city)
                if weather:
                    weather_info = f"当前天气: {weather.get('text', '')}, 温度{weather.get('temp', '')}℃"
                    if weather.get('feelsLike'):
                        weather_info += f", 体感{weather.get('feelsLike')}℃"
                    if weather.get('humidity'):
                        weather_info += f", 湿度{weather.get('humidity')}%"
                    if weather.get('windDir') and weather.get('windScale'):
                        weather_info += f", {weather.get('windDir')}{weather.get('windScale')}级"
                    parts.append(weather_info)
            except Exception as e:
                logger.warning(f"获取天气信息失败: {e}")

        if user:
            info = f"用户: {user.name or user.username}"
            if user.gender:
                info += f", 性别: {user.gender}"
            if user.birth_date:
                age = today.year - user.birth_date.year
                # Adjust if birthday hasn't occurred yet this year
                if (today.month, today.day) < (user.birth_date.month, user.birth_date.day):
                    age -= 1
                info += f", 年龄: {age}岁"
                # 计算最大心率 (220 - 年龄)，用于运动强度分析
                max_heart_rate = 220 - age
                info += f", 最大心率: {max_heart_rate}bpm (220-年龄)"
            parts.append(info)

        if profile:
            if profile.height_cm:
                parts.append(f"身高: {profile.height_cm}cm")
            if profile.chronic_conditions:
                parts.append(f"慢性病: {', '.join(profile.chronic_conditions)}")
            if profile.allergies:
                parts.append(f"过敏: {', '.join(profile.allergies)}")
            if profile.current_medications:
                med_names = []
                for m in profile.current_medications:
                    if isinstance(m, dict):
                        med_names.append(m.get("name", str(m)))
                    else:
                        med_names.append(str(m))
                if med_names:
                    parts.append(f"用药: {', '.join(med_names)}")
            goals = []
            if profile.target_weight_kg:
                goals.append(f"目标体重{profile.target_weight_kg}kg")
            if profile.target_steps:
                goals.append(f"目标步数{profile.target_steps}")
            if profile.target_sleep_hours:
                goals.append(f"目标睡眠{profile.target_sleep_hours}h")
            if goals:
                parts.append(f"健康目标: {', '.join(goals)}")

        # 最近体重
        weight = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id
        ).order_by(WeightRecord.record_date.desc()).first()
        if weight:
            parts.append(f"最近体重: {weight.weight}kg ({weight.record_date})")

        # 最近血压
        bp = self.db.query(BloodPressureRecord).filter(
            BloodPressureRecord.user_id == user_id
        ).order_by(BloodPressureRecord.record_date.desc()).first()
        if bp:
            parts.append(f"最近血压: {bp.systolic}/{bp.diastolic}mmHg ({bp.record_date})")

        # 最近 Garmin 数据（今日）
        garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()
        if garmin:
            g_parts = [f"Garmin数据({garmin.record_date})"]
            if garmin.steps:
                g_parts.append(f"步数:{garmin.steps}")
            if garmin.resting_heart_rate:
                g_parts.append(f"静息心率:{garmin.resting_heart_rate}")
            if garmin.sleep_score:
                g_parts.append(f"睡眠分数:{garmin.sleep_score}")
            if garmin.stress_level:
                g_parts.append(f"压力水平:{garmin.stress_level}")
            if garmin.body_battery_most_charged:
                g_parts.append(f"身体电量峰值:{garmin.body_battery_most_charged}")
            parts.append(", ".join(g_parts))

        # 睡眠数据分析（最近3天、7天、30天）
        from datetime import timedelta

        # 最近3天详细数据
        three_days_ago = today - timedelta(days=3)
        sleep_3days = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= three_days_ago
        ).order_by(GarminData.record_date.desc()).limit(3).all()

        if sleep_3days:
            sleep_summary = ["最近3天睡眠:"]
            for record in sleep_3days:
                sleep_info = [f"{record.record_date}"]
                if record.sleep_score is not None:
                    sleep_info.append(f"分数{record.sleep_score}")
                if record.total_sleep_duration is not None:
                    hours = record.total_sleep_duration // 60
                    mins = record.total_sleep_duration % 60
                    sleep_info.append(f"总时长{hours}h{mins}min")
                if record.deep_sleep_duration is not None:
                    sleep_info.append(f"深睡{record.deep_sleep_duration}min")
                if record.rem_sleep_duration is not None:
                    sleep_info.append(f"REM{record.rem_sleep_duration}min")
                if record.light_sleep_duration is not None:
                    sleep_info.append(f"浅睡{record.light_sleep_duration}min")
                if record.awake_duration is not None:
                    sleep_info.append(f"清醒{record.awake_duration}min")
                if record.sleep_start_time and record.sleep_end_time:
                    # 处理时间字段可能是字符串或time对象的情况
                    start_time = record.sleep_start_time
                    end_time = record.sleep_end_time
                    if hasattr(start_time, 'strftime'):
                        start_time = start_time.strftime('%H:%M')
                    if hasattr(end_time, 'strftime'):
                        end_time = end_time.strftime('%H:%M')
                    sleep_info.append(f"时段{start_time}-{end_time}")
                sleep_summary.append(" ".join(sleep_info))
            parts.append("\n  ".join(sleep_summary))

        # 最近7天统计
        seven_days_ago = today - timedelta(days=7)
        sleep_7days = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= seven_days_ago
        ).all()

        if sleep_7days:
            scores = [r.sleep_score for r in sleep_7days if r.sleep_score is not None]
            durations = [r.total_sleep_duration for r in sleep_7days if r.total_sleep_duration is not None]
            deep_sleeps = [r.deep_sleep_duration for r in sleep_7days if r.deep_sleep_duration is not None]
            rem_sleeps = [r.rem_sleep_duration for r in sleep_7days if r.rem_sleep_duration is not None]

            stats_7d = [f"最近7天睡眠统计({len(sleep_7days)}天)"]
            if scores:
                avg_score = sum(scores) / len(scores)
                stats_7d.append(f"平均分数{avg_score:.1f}")
            if durations:
                avg_duration = sum(durations) / len(durations)
                avg_hours = int(avg_duration // 60)
                avg_mins = int(avg_duration % 60)
                stats_7d.append(f"平均时长{avg_hours}h{avg_mins}min")
            if deep_sleeps:
                avg_deep = sum(deep_sleeps) / len(deep_sleeps)
                stats_7d.append(f"平均深睡{avg_deep:.0f}min")
            if rem_sleeps:
                avg_rem = sum(rem_sleeps) / len(rem_sleeps)
                stats_7d.append(f"平均REM{avg_rem:.0f}min")
            parts.append(": ".join(stats_7d))

        # 最近30天统计
        thirty_days_ago = today - timedelta(days=30)
        sleep_30days = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= thirty_days_ago
        ).all()

        if sleep_30days:
            scores = [r.sleep_score for r in sleep_30days if r.sleep_score is not None]
            durations = [r.total_sleep_duration for r in sleep_30days if r.total_sleep_duration is not None]
            deep_sleeps = [r.deep_sleep_duration for r in sleep_30days if r.deep_sleep_duration is not None]
            rem_sleeps = [r.rem_sleep_duration for r in sleep_30days if r.rem_sleep_duration is not None]

            stats_30d = [f"最近30天睡眠统计({len(sleep_30days)}天)"]
            if scores:
                avg_score = sum(scores) / len(scores)
                stats_30d.append(f"平均分数{avg_score:.1f}")
            if durations:
                avg_duration = sum(durations) / len(durations)
                avg_hours = int(avg_duration // 60)
                avg_mins = int(avg_duration % 60)
                stats_30d.append(f"平均时长{avg_hours}h{avg_mins}min")
            if deep_sleeps:
                avg_deep = sum(deep_sleeps) / len(deep_sleeps)
                stats_30d.append(f"平均深睡{avg_deep:.0f}min")
            if rem_sleeps:
                avg_rem = sum(rem_sleeps) / len(rem_sleeps)
                stats_30d.append(f"平均REM{avg_rem:.0f}min")
            parts.append(": ".join(stats_30d))

        # 运动数据分析（最近7天、30天）
        # 最近7天运动数据
        exercise_7days = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= seven_days_ago
        ).all()

        if exercise_7days:
            steps_list = [r.steps for r in exercise_7days if r.steps is not None]
            calories_list = [r.calories_burned for r in exercise_7days if r.calories_burned is not None]
            active_mins = [r.vigorous_intensity_minutes + r.moderate_intensity_minutes
                          for r in exercise_7days
                          if r.vigorous_intensity_minutes is not None and r.moderate_intensity_minutes is not None]

            exercise_stats_7d = [f"最近7天运动统计({len(exercise_7days)}天)"]
            if steps_list:
                avg_steps = sum(steps_list) / len(steps_list)
                total_steps = sum(steps_list)
                exercise_stats_7d.append(f"平均步数{avg_steps:.0f}, 总计{total_steps}")
            if calories_list:
                avg_calories = sum(calories_list) / len(calories_list)
                exercise_stats_7d.append(f"平均消耗{avg_calories:.0f}卡")
            if active_mins:
                avg_active = sum(active_mins) / len(active_mins)
                exercise_stats_7d.append(f"平均活动{avg_active:.0f}分钟")
            parts.append(": ".join(exercise_stats_7d))

        # 最近30天运动数据
        exercise_30days = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= thirty_days_ago
        ).all()

        if exercise_30days:
            steps_list = [r.steps for r in exercise_30days if r.steps is not None]
            calories_list = [r.calories_burned for r in exercise_30days if r.calories_burned is not None]
            active_mins = [r.vigorous_intensity_minutes + r.moderate_intensity_minutes
                          for r in exercise_30days
                          if r.vigorous_intensity_minutes is not None and r.moderate_intensity_minutes is not None]

            exercise_stats_30d = [f"最近30天运动统计({len(exercise_30days)}天)"]
            if steps_list:
                avg_steps = sum(steps_list) / len(steps_list)
                total_steps = sum(steps_list)
                exercise_stats_30d.append(f"平均步数{avg_steps:.0f}, 总计{total_steps}")
            if calories_list:
                avg_calories = sum(calories_list) / len(calories_list)
                exercise_stats_30d.append(f"平均消耗{avg_calories:.0f}卡")
            if active_mins:
                avg_active = sum(active_mins) / len(active_mins)
                exercise_stats_30d.append(f"平均活动{avg_active:.0f}分钟")
            parts.append(": ".join(exercise_stats_30d))

        # 详细运动训练记录（最近30天）
        # 查询 WorkoutRecord（跑步、游泳、骑车等专项训练）
        workout_30days = self.db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= thirty_days_ago
        ).order_by(WorkoutRecord.workout_date.desc()).limit(20).all()

        if workout_30days:
            # 添加心率分析提示
            if user and user.birth_date:
                age = today.year - user.birth_date.year
                if (today.month, today.day) < (user.birth_date.month, user.birth_date.day):
                    age -= 1
                max_hr = 220 - age
                workout_summary = [
                    f"最近30天运动训练记录({len(workout_30days)}次):",
                    f"[心率分析参考: 最大心率{max_hr}bpm, 轻度<60%, 中度60-75%, 高强度75-85%, 极限>85%]"
                ]
            else:
                workout_summary = [f"最近30天运动训练记录({len(workout_30days)}次):"]
            for workout in workout_30days[:10]:  # 只显示最近10次
                workout_info = [f"{workout.workout_date}"]

                # 运动类型和名称
                workout_type_map = {
                    'running': '跑步', 'swimming': '游泳', 'cycling': '骑车',
                    'hiit': 'HIIT', 'cardio': '有氧', 'strength': '力量训练',
                    'yoga': '瑜伽', 'walking': '走路', 'hiking': '徒步'
                }
                type_name = workout_type_map.get(workout.workout_type, workout.workout_type)
                if workout.workout_name:
                    workout_info.append(f"{workout.workout_name}({type_name})")
                else:
                    workout_info.append(type_name)

                # 时长
                if workout.duration_seconds:
                    mins = workout.duration_seconds // 60
                    workout_info.append(f"{mins}分钟")

                # 距离
                if workout.distance_meters:
                    km = workout.distance_meters / 1000
                    workout_info.append(f"{km:.2f}公里")

                # 配速（跑步）
                if workout.avg_pace_seconds_per_km and workout.workout_type in ['running', 'walking']:
                    pace_min = workout.avg_pace_seconds_per_km // 60
                    pace_sec = workout.avg_pace_seconds_per_km % 60
                    workout_info.append(f"配速{pace_min}'{pace_sec}\"")

                # 心率
                if workout.avg_heart_rate:
                    workout_info.append(f"心率{workout.avg_heart_rate}bpm")

                # 卡路里
                if workout.calories:
                    workout_info.append(f"{workout.calories}卡")

                workout_summary.append(" ".join(workout_info))

            if len(workout_30days) > 10:
                workout_summary.append(f"...还有{len(workout_30days) - 10}次训练记录")
            parts.append("\n  ".join(workout_summary))

        # 查询 ExerciseRecord（日常锻炼记录）
        exercise_30days_detailed = self.db.query(ExerciseRecord).filter(
            ExerciseRecord.user_id == user_id,
            ExerciseRecord.record_date >= thirty_days_ago
        ).order_by(ExerciseRecord.record_date.desc()).limit(15).all()

        if exercise_30days_detailed:
            exercise_summary = [f"最近30天日常锻炼记录({len(exercise_30days_detailed)}次):"]
            for ex in exercise_30days_detailed[:10]:  # 只显示最近10次
                ex_info = [f"{ex.record_date} {ex.exercise_type}"]
                if ex.duration:
                    ex_info.append(f"{ex.duration}分钟")
                if ex.intensity:
                    ex_info.append(f"强度:{ex.intensity}")
                if ex.calories_burned:
                    ex_info.append(f"{ex.calories_burned}卡")
                if ex.distance:
                    ex_info.append(f"{ex.distance}km")
                if ex.notes:
                    ex_info.append(f"备注:{ex.notes}")
                exercise_summary.append(" ".join(ex_info))

            if len(exercise_30days_detailed) > 10:
                exercise_summary.append(f"...还有{len(exercise_30days_detailed) - 10}次锻炼记录")
            parts.append("\n  ".join(exercise_summary))

        # 饮食数据分析（最近3天、7天）
        # 最近3天详细饮食记录
        diet_3days = self.db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= three_days_ago
        ).order_by(DietRecord.record_date.desc(), DietRecord.meal_time.desc()).all()

        if diet_3days:
            diet_summary = ["最近3天饮食:"]
            # 按日期分组
            from collections import defaultdict
            by_date = defaultdict(list)
            for record in diet_3days:
                by_date[record.record_date].append(record)

            for date_key in sorted(by_date.keys(), reverse=True):
                day_records = by_date[date_key]
                day_info = [f"{date_key}"]

                # 统计当天的营养摄入
                total_calories = sum(r.calories for r in day_records if r.calories)
                total_protein = sum(r.protein for r in day_records if r.protein)
                total_carbs = sum(r.carbs for r in day_records if r.carbs)
                total_fat = sum(r.fat for r in day_records if r.fat)

                nutrition = []
                if total_calories:
                    nutrition.append(f"{total_calories:.0f}卡")
                if total_protein:
                    nutrition.append(f"蛋白质{total_protein:.0f}g")
                if total_carbs:
                    nutrition.append(f"碳水{total_carbs:.0f}g")
                if total_fat:
                    nutrition.append(f"脂肪{total_fat:.0f}g")

                if nutrition:
                    day_info.append(", ".join(nutrition))

                # 列出主要食物
                meals = [f"{r.meal_type}:{r.food_items or r.food_name}"
                        for r in day_records if r.food_items or r.food_name]
                if meals:
                    day_info.append(f"[{'; '.join(meals[:3])}{'...' if len(meals) > 3 else ''}]")

                diet_summary.append(" ".join(day_info))
            parts.append("\n  ".join(diet_summary))

        # 最近7天饮食统计
        diet_7days = self.db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= seven_days_ago
        ).all()

        if diet_7days:
            # 按日期分组统计
            from collections import defaultdict
            daily_nutrition = defaultdict(lambda: {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0})

            for record in diet_7days:
                date_key = record.record_date
                if record.calories:
                    daily_nutrition[date_key]['calories'] += record.calories
                if record.protein:
                    daily_nutrition[date_key]['protein'] += record.protein
                if record.carbs:
                    daily_nutrition[date_key]['carbs'] += record.carbs
                if record.fat:
                    daily_nutrition[date_key]['fat'] += record.fat

            if daily_nutrition:
                days_count = len(daily_nutrition)
                total_calories = sum(d['calories'] for d in daily_nutrition.values())
                total_protein = sum(d['protein'] for d in daily_nutrition.values())
                total_carbs = sum(d['carbs'] for d in daily_nutrition.values())
                total_fat = sum(d['fat'] for d in daily_nutrition.values())

                diet_stats_7d = [f"最近7天饮食统计({days_count}天)"]
                if total_calories:
                    avg_calories = total_calories / days_count
                    diet_stats_7d.append(f"平均{avg_calories:.0f}卡/天")
                if total_protein:
                    avg_protein = total_protein / days_count
                    diet_stats_7d.append(f"平均蛋白质{avg_protein:.0f}g/天")
                if total_carbs:
                    avg_carbs = total_carbs / days_count
                    diet_stats_7d.append(f"平均碳水{avg_carbs:.0f}g/天")
                if total_fat:
                    avg_fat = total_fat / days_count
                    diet_stats_7d.append(f"平均脂肪{avg_fat:.0f}g/天")
                parts.append(": ".join(diet_stats_7d))

        # 打卡数据分析（最近7天、30天）
        # 今日打卡记录
        checkins = self.db.query(CheckinRecord, CheckinTemplate).join(
            CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id
        ).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == today
        ).all()
        if checkins:
            checkin_items = [f"{t.name}({r.value}{t.unit})" for r, t in checkins]
            if checkin_items:
                parts.append(f"今日打卡: {', '.join(checkin_items)}")

        # 最近7天打卡统计
        checkins_7days = self.db.query(CheckinRecord, CheckinTemplate).join(
            CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id
        ).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date >= seven_days_ago
        ).all()

        if checkins_7days:
            # 按模板分组统计
            from collections import defaultdict
            template_stats = defaultdict(lambda: {'count': 0, 'total': 0, 'name': '', 'unit': ''})

            for record, template in checkins_7days:
                template_id = template.id
                template_stats[template_id]['name'] = template.name
                template_stats[template_id]['unit'] = template.unit
                template_stats[template_id]['count'] += 1
                if record.value:
                    template_stats[template_id]['total'] += record.value

            if template_stats:
                checkin_stats_7d = [f"最近7天打卡统计({len(checkins_7days)}次)"]
                for stats in template_stats.values():
                    avg_val = stats['total'] / stats['count'] if stats['count'] > 0 else 0
                    checkin_stats_7d.append(f"{stats['name']}:完成{stats['count']}天,平均{avg_val:.1f}{stats['unit']}")
                parts.append("; ".join(checkin_stats_7d))

        # 最近30天打卡统计
        checkins_30days = self.db.query(CheckinRecord, CheckinTemplate).join(
            CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id
        ).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date >= thirty_days_ago
        ).all()

        if checkins_30days:
            # 按模板分组统计
            from collections import defaultdict
            template_stats = defaultdict(lambda: {'count': 0, 'total': 0, 'name': '', 'unit': ''})

            for record, template in checkins_30days:
                template_id = template.id
                template_stats[template_id]['name'] = template.name
                template_stats[template_id]['unit'] = template.unit
                template_stats[template_id]['count'] += 1
                if record.value:
                    template_stats[template_id]['total'] += record.value

            if template_stats:
                checkin_stats_30d = [f"最近30天打卡统计({len(checkins_30days)}次)"]
                for stats in template_stats.values():
                    avg_val = stats['total'] / stats['count'] if stats['count'] > 0 else 0
                    checkin_stats_30d.append(f"{stats['name']}:完成{stats['count']}天,平均{avg_val:.1f}{stats['unit']}")
                parts.append("; ".join(checkin_stats_30d))

        if not parts:
            return ""

        return "以下是该用户的最新健康数据：\n" + "\n".join(parts)

    async def _get_system_prompt(self, user_id: int) -> str:
        """组装完整的 system prompt"""
        base = (
            "你是一个专业的私人健康顾问。你的名字叫「健康顾问」。\n"
            "请基于用户的健康数据，提供个性化、科学、实用的健康建议。\n"
            "回答要简洁友好，避免过度医学化。如涉及严重健康问题请建议就医。\n"
            "使用中文回答。"
        )

        health_ctx = await self._build_health_context(user_id)
        if health_ctx:
            return f"{base}\n\n{health_ctx}"
        return base

    async def send_message(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """发送消息到 OpenClaw 并返回回复"""

        # 获取或创建对话
        if conversation_id:
            conv = self.db.query(ChatConversation).filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            ).first()
            if not conv:
                raise ValueError("对话不存在")
        else:
            conv = ChatConversation(user_id=user_id, title=message[:50])
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)

        # 保存用户消息
        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        # 构建消息列表（最近 20 条作为上下文）
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()

        # 只取最近 20 条消息避免超长
        recent = history[-20:] if len(history) > 20 else history

        messages = [{"role": "system", "content": await self._get_system_prompt(user_id)}]
        for msg in recent:
            messages.append({"role": msg.role, "content": msg.content})

        # 调用 OpenClaw API
        try:
            reply_content = await self._call_openclaw(messages)
        except Exception as e:
            logger.error(f"OpenClaw 调用失败: {e}")
            reply_content = "抱歉，健康顾问暂时无法响应，请稍后再试。"

        # 保存 AI 回复
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=reply_content)
        self.db.add(ai_msg)

        # 更新对话标题（首次对话用用户消息做标题）
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        return {
            "conversation_id": conv.id,
            "reply": reply_content,
            "message_id": ai_msg.id
        }

    async def _call_openclaw(self, messages: list) -> str:
        """调用 OpenClaw 的 OpenAI 兼容 API"""
        url = f"{OPENCLAW_BASE_URL}/chat/completions"

        headers = {
            "Content-Type": "application/json",
        }
        if OPENCLAW_API_KEY:
            headers["Authorization"] = f"Bearer {OPENCLAW_API_KEY}"

        payload = {
            "model": OPENCLAW_MODEL,
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        return choice.get("message", {}).get("content", "").strip()

    def get_conversations(self, user_id: int, limit: int = 20) -> List[ChatConversation]:
        """获取用户的对话列表"""
        return self.db.query(ChatConversation).filter(
            ChatConversation.user_id == user_id
        ).order_by(ChatConversation.updated_at.desc()).limit(limit).all()

    def get_conversation_messages(self, user_id: int, conversation_id: int) -> Optional[ChatConversation]:
        """获取对话详情及所有消息"""
        return self.db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id
        ).first()

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        """删除对话"""
        conv = self.db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id
        ).first()
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True
