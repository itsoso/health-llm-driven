"""
聊天服务 - 通过 OpenClaw 提供 AI 对话能力
利用 OpenClaw 的 OpenAI 兼容 API，注入用户健康上下文
"""
import json
import logging
import re
import asyncio
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.basic_health import BasicHealthData
from datetime import timedelta
from app.models.daily_health import GarminData, DietRecord, ExerciseRecord, WorkoutRecord, WaterIntake
from app.models.checkin import CheckinRecord, CheckinTemplate
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.chat import ChatConversation, ChatMessage
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.disease_tracking import UserDiseaseProfile, SymptomLog
from app.services.environment.weather_service import weather_service
from app.services.ai.food_recognition import food_recognition_service

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

        # 获取当前天气和空气质量信息（异步调用）
        if user_city:
            try:
                # 使用综合上下文API，同时获取天气、空气质量和生活指数
                context = await weather_service.get_comprehensive_context(city=user_city)

                # 天气信息
                weather = context.get('weather')
                if weather:
                    weather_info = f"当前天气: {weather.get('text', '')}, 温度{weather.get('temp', '')}℃"
                    if weather.get('feelsLike'):
                        weather_info += f", 体感{weather.get('feelsLike')}℃"
                    if weather.get('humidity'):
                        weather_info += f", 湿度{weather.get('humidity')}%"
                    if weather.get('windDir') and weather.get('windScale'):
                        weather_info += f", {weather.get('windDir')}{weather.get('windScale')}级"
                    parts.append(weather_info)

                # 空气质量信息
                air_quality = context.get('air_quality')
                if air_quality and air_quality.get('available'):
                    aqi = air_quality.get('aqi', 'N/A')
                    level = air_quality.get('level', '未知')
                    primary = air_quality.get('primary_pollutant', '无')
                    air_info = f"空气质量: AQI {aqi} ({level})"
                    if primary and primary != '无':
                        air_info += f", 主要污染物: {primary}"
                    parts.append(air_info)

                # 生活指数（如果可用）
                lifestyle = context.get('lifestyle_indices')
                if lifestyle and lifestyle.get('available'):
                    # 运动指数
                    sport = lifestyle.get('1')  # 1 = 运动指数
                    if sport:
                        sport_info = f"运动指数: {sport.get('category', '')} - {sport.get('text', '')}"
                        parts.append(sport_info)
            except Exception as e:
                logger.warning(f"获取环境信息失败: {e}")

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

    def _build_activity_context(self, user_id: int) -> str:
        """构建用户可记录的活动上下文（打卡模板、补剂、疾病档案）"""
        parts = []

        # 打卡模板
        templates = self.db.query(CheckinTemplate).filter(
            CheckinTemplate.user_id == user_id,
            CheckinTemplate.is_active == True,
            CheckinTemplate.is_archived == False
        ).all()
        if templates:
            tpl_list = [f'  - id={t.id}, name="{t.name}", unit="{t.unit}", default={t.default_target}'
                        for t in templates]
            parts.append("用户的打卡模板:\n" + "\n".join(tpl_list))

        # 补剂定义
        supplements = self.db.query(SupplementDefinition).filter(
            SupplementDefinition.user_id == user_id,
            SupplementDefinition.is_active == True
        ).all()
        if supplements:
            supp_list = [f'  - id={s.id}, name="{s.name}", dosage="{s.dosage or ""}"'
                         for s in supplements]
            parts.append("用户的补剂列表:\n" + "\n".join(supp_list))

        # 疾病档案（数据库表结构可能尚未迁移，安全查询）
        try:
            from sqlalchemy import text as sa_text
            rows = self.db.execute(sa_text(
                "SELECT id, disease_id, severity FROM user_disease_profiles "
                "WHERE user_id = :uid AND is_active = true"
            ), {"uid": user_id}).fetchall()
            if rows:
                # 尝试关联 disease_templates 获取名称
                disease_ids = [r[1] for r in rows if r[1]]
                name_map = {}
                if disease_ids:
                    dt_rows = self.db.execute(sa_text(
                        "SELECT id, display_name FROM disease_templates WHERE id = ANY(:ids)"
                    ), {"ids": disease_ids}).fetchall()
                    name_map = {r[0]: r[1] for r in dt_rows}
                prof_list = []
                for r in rows:
                    name = name_map.get(r[1], f"疾病{r[1]}")
                    prof_list.append(f'  - id={r[0]}, disease="{name}", severity="{r[2]}"')
                parts.append("用户的疾病档案:\n" + "\n".join(prof_list))
        except Exception as e:
            logger.warning(f"查询疾病档案失败(可忽略): {e}")
            self.db.rollback()

        return "\n\n".join(parts)

    async def _get_system_prompt(self, user_id: int) -> str:
        """组装完整的 system prompt"""
        base = (
            "你是一个专业的私人健康顾问。你的名字叫「健康顾问」。\n"
            "请基于用户的健康数据，提供个性化、科学、实用的健康建议。\n"
            "回答要简洁友好，避免过度医学化。如涉及严重健康问题请建议就医。\n"
            "使用中文回答。\n\n"
            "你具有饮食记录和热量计算功能。当用户描述吃了什么食物时，系统会自动分析营养成分并保存饮食记录。"
            "如果消息中包含[系统提示]的营养分析结果，请基于这些数据给用户清晰的热量和营养反馈。"
        )

        # 活动记录能力
        activity_ctx = self._build_activity_context(user_id)
        activity_prompt = (
            "\n\n## 活动记录功能\n"
            "你可以帮用户自动记录健康活动。当用户消息描述了**已经完成**的活动时，"
            "请在回复末尾附加活动数据标记。\n\n"
            "### 规则\n"
            "1. 只在用户**陈述已完成**的活动时记录（如\"刚做了50个俯卧撑\"）\n"
            "2. 提问/计划/咨询建议不要记录（如\"俯卧撑怎么做？\"\"明天计划跑步\"）\n"
            "3. 一条消息可包含多个活动\n"
            "4. 饮食由系统另外处理，不要在活动标记中包含饮食\n\n"
            "### 格式\n"
            "在正常回复之后附加（用户不可见）：\n"
            '<<<ACTIONS:[{"type":"checkin","template_id":ID,"template_name":"名称","value":数值或null,"notes":"备注或null"},'
            '{"type":"water","amount":毫升数,"drink_type":"水/茶/咖啡"},'
            '{"type":"supplement","supplement_id":ID,"supplement_name":"名称"},'
            '{"type":"symptom","profile_id":ID,"disease_name":"疾病名","overall_severity":0到10,"symptoms":[{"name":"症状","severity":1到10}]}]>>>\n\n'
            "### 示例\n"
            "- \"刚踢腿200下\" → checkin, 匹配踢腿模板, value=200\n"
            "- \"洗了鼻子\" → checkin, 匹配洗鼻模板, value=null(用默认值)\n"
            "- \"喝了一杯水\" → water, amount=250\n"
            "- \"喝了500ml水\" → water, amount=500\n"
            "- \"吃了维生素D\" → supplement\n"
            "- \"今天打了好几个喷嚏\" → symptom, 匹配鼻炎档案\n"
            "- \"做了30个俯卧撑然后喝了杯水\" → 两个活动\n\n"
            "### 不应记录\n"
            "- \"我应该每天踢多少下？\" → 提问不记录\n"
            "- \"明天计划跑步\" → 计划不记录\n"
            "- \"帮我看看打卡情况\" → 查询不记录\n"
        )
        if activity_ctx:
            activity_prompt += f"\n### 用户数据\n{activity_ctx}\n"

        health_ctx = await self._build_health_context(user_id)
        prompt = base + activity_prompt
        if health_ctx:
            prompt += f"\n\n{health_ctx}"
        return prompt

    def _is_food_message(self, message: str) -> bool:
        """检测消息是否是记录饮食的内容"""
        # 量词列表
        quantity_words = '个只条碗盘杯片块份根勺两斤克袋瓶罐把串盒听颗粒'
        pattern = rf'[一二三四五六七八九十百千万半\d]+\s*[{quantity_words}]'
        matches = re.findall(pattern, message)

        # 2个以上量词模式，很可能是食物列表
        if len(matches) >= 2:
            return True

        # 显式饮食记录关键词
        food_action_keywords = ['计算热量', '记录饮食', '热量计算', '算一下热量', '算热量',
                                '多少卡', '多少热量', '多少卡路里', '记一下饮食']
        if any(kw in message for kw in food_action_keywords):
            return True

        # 饮食上下文关键词 + 至少1个量词
        food_context_keywords = ['吃了', '吃的', '早餐', '午餐', '晚餐', '夜宵',
                                 '早饭', '中饭', '晚饭', '喝了', '加餐']
        if len(matches) >= 1 and any(kw in message for kw in food_context_keywords):
            return True

        return False

    def _get_meal_type_by_time(self) -> str:
        """根据当前时间推断餐次"""
        hour = datetime.now().hour
        if hour < 10:
            return "breakfast"
        elif hour < 14:
            return "lunch"
        elif hour < 17:
            return "snack"
        elif hour < 21:
            return "dinner"
        else:
            return "snack"

    def _process_diet_record(self, user_id: int, message: str, nutrition_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将营养数据保存为饮食记录"""
        try:
            foods = nutrition_data.get("foods", [])
            if not foods:
                return None

            # 组合食物名称
            food_items = ", ".join([
                f"{f.get('name', '')}({f.get('quantity', '')})" if f.get('quantity') else f.get('name', '')
                for f in foods
            ])
            food_name = food_items[:100] if len(food_items) > 100 else food_items

            meal_type = self._get_meal_type_by_time()
            today = date.today()

            db_record = DietRecord(
                user_id=user_id,
                record_date=today,
                meal_type=meal_type,
                food_name=food_name,
                food_items=food_items,
                calories=nutrition_data.get("total_calories"),
                protein=nutrition_data.get("total_protein"),
                carbs=nutrition_data.get("total_carbs"),
                fat=nutrition_data.get("total_fat"),
                notes=f"通过健康顾问对话自动记录: {message[:100]}",
                ai_recognized=True,
                ai_raw_result=json.dumps(nutrition_data, ensure_ascii=False),
                health_tips=nutrition_data.get("health_tips"),
            )
            self.db.add(db_record)
            self.db.commit()
            self.db.refresh(db_record)

            logger.info(f"用户 {user_id} 通过对话自动保存饮食记录: id={db_record.id}, {food_items}")

            return {
                "record_id": db_record.id,
                "food_items": food_items,
                "total_calories": nutrition_data.get("total_calories"),
                "total_protein": nutrition_data.get("total_protein"),
                "total_carbs": nutrition_data.get("total_carbs"),
                "total_fat": nutrition_data.get("total_fat"),
                "meal_type": meal_type,
                "record_date": str(today),
            }
        except Exception as e:
            logger.error(f"自动保存饮食记录失败: {e}")
            self.db.rollback()
            return None

    def _parse_actions(self, reply: str) -> tuple:
        """从AI回复中解析活动标记，返回 (clean_reply, actions_list)"""
        pattern = r'<<<ACTIONS:\s*(\[[\s\S]*?\])\s*>>>'
        match = re.search(pattern, reply)
        if not match:
            return reply, []
        clean_reply = reply[:match.start()].rstrip()
        try:
            actions = json.loads(match.group(1))
            if not isinstance(actions, list):
                return clean_reply, []
            return clean_reply, actions
        except json.JSONDecodeError as e:
            logger.warning(f"解析活动JSON失败: {e}")
            return clean_reply, []

    def _execute_actions(self, user_id: int, actions: list) -> list:
        """执行检测到的活动并返回结果列表"""
        results = []
        today = date.today()
        now = datetime.now()
        for action in actions:
            action_type = action.get("type")
            try:
                if action_type == "checkin":
                    result = self._handle_checkin_action(user_id, action, today)
                elif action_type == "water":
                    result = self._handle_water_action(user_id, action, today, now)
                elif action_type == "supplement":
                    result = self._handle_supplement_action(user_id, action, today)
                elif action_type == "symptom":
                    result = self._handle_symptom_action(user_id, action, today)
                else:
                    logger.warning(f"未知活动类型: {action_type}")
                    continue
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"执行{action_type}活动失败: {e}")
                self.db.rollback()
        return results

    def _handle_checkin_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理打卡活动"""
        template_id = action.get("template_id")
        template_name = action.get("template_name")
        value = action.get("value")

        # 按ID查找模板，失败则按名称
        template = None
        if template_id:
            template = self.db.query(CheckinTemplate).filter(
                CheckinTemplate.id == template_id,
                CheckinTemplate.user_id == user_id,
                CheckinTemplate.is_active == True
            ).first()
        if not template and template_name:
            template = self.db.query(CheckinTemplate).filter(
                CheckinTemplate.user_id == user_id,
                CheckinTemplate.name.ilike(f"%{template_name}%"),
                CheckinTemplate.is_active == True
            ).first()
        if not template:
            logger.warning(f"打卡模板未找到: id={template_id}, name={template_name}")
            return None

        # 检查今日是否已打卡
        existing = self.db.query(CheckinRecord).filter(
            CheckinRecord.template_id == template.id,
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == today
        ).first()

        actual_value = value if value is not None else template.default_target

        if existing:
            # 如果已打卡，累加数值
            existing.value = (existing.value or 0) + actual_value
            existing.completion_rate = (existing.value / template.default_target * 100) if template.default_target > 0 else 100
            template.total_value = (template.total_value or 0) + actual_value
            self.db.commit()
            return {
                "type": "checkin", "status": "updated",
                "message": f"{template.icon} {template.name} 累计{existing.value}{template.unit} 已更新"
            }

        completion_rate = (actual_value / template.default_target * 100) if template.default_target > 0 else 100
        record = CheckinRecord(
            template_id=template.id, user_id=user_id,
            checkin_date=today, value=actual_value,
            target=template.default_target, completion_rate=completion_rate,
            notes="通过健康顾问对话自动记录"
        )
        self.db.add(record)

        # 更新模板统计
        template.total_checkins = (template.total_checkins or 0) + 1
        template.total_value = (template.total_value or 0) + actual_value
        yesterday = today - timedelta(days=1)
        if template.last_checkin_date == yesterday:
            template.current_streak = (template.current_streak or 0) + 1
        elif template.last_checkin_date != today:
            template.current_streak = 1
        template.last_checkin_date = today
        if (template.current_streak or 0) > (template.best_streak or 0):
            template.best_streak = template.current_streak

        self.db.commit()
        logger.info(f"用户{user_id} 打卡: {template.name} {actual_value}{template.unit}")
        return {
            "type": "checkin", "status": "saved",
            "message": f"{template.icon} {template.name} {actual_value}{template.unit} 已记录"
        }

    def _handle_water_action(self, user_id: int, action: dict, today: date, now: datetime) -> Optional[Dict]:
        """处理喝水活动"""
        amount = action.get("amount", 250)
        drink_type = action.get("drink_type", "水")
        record = WaterIntake(
            user_id=user_id, record_date=today,
            amount_ml=amount, intake_time=now, drink_type=drink_type,
        )
        self.db.add(record)
        self.db.commit()
        logger.info(f"用户{user_id} 喝水: {amount}ml {drink_type}")
        return {
            "type": "water", "status": "saved",
            "message": f"💧 {drink_type} {amount}ml 已记录"
        }

    def _handle_supplement_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理补剂活动"""
        supplement_id = action.get("supplement_id")
        supplement_name = action.get("supplement_name")

        supplement = None
        if supplement_id:
            supplement = self.db.query(SupplementDefinition).filter(
                SupplementDefinition.id == supplement_id,
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.is_active == True
            ).first()
        if not supplement and supplement_name:
            supplement = self.db.query(SupplementDefinition).filter(
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.name.ilike(f"%{supplement_name}%"),
                SupplementDefinition.is_active == True
            ).first()
        if not supplement:
            logger.warning(f"补剂未找到: id={supplement_id}, name={supplement_name}")
            return None

        existing = self.db.query(SupplementRecord).filter(
            SupplementRecord.supplement_id == supplement.id,
            SupplementRecord.user_id == user_id,
            SupplementRecord.record_date == today
        ).first()
        if existing:
            existing.taken = True
            self.db.commit()
            return {
                "type": "supplement", "status": "updated",
                "message": f"💊 {supplement.name} 已标记为已服用"
            }

        record = SupplementRecord(
            supplement_id=supplement.id, user_id=user_id,
            record_date=today, taken=True,
            notes="通过健康顾问对话自动记录"
        )
        self.db.add(record)
        self.db.commit()
        logger.info(f"用户{user_id} 补剂: {supplement.name}")
        return {
            "type": "supplement", "status": "saved",
            "message": f"💊 {supplement.name} 已记录"
        }

    def _handle_symptom_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理症状记录活动"""
        from sqlalchemy import text as sa_text
        profile_id = action.get("profile_id")
        disease_name = action.get("disease_name")
        overall_severity = action.get("overall_severity", 3)
        symptoms = action.get("symptoms", [])

        try:
            row = None
            if profile_id:
                row = self.db.execute(sa_text(
                    "SELECT p.id, COALESCE(dt.display_name, dt.name, '未知疾病') as disease_name "
                    "FROM user_disease_profiles p "
                    "LEFT JOIN disease_templates dt ON dt.id = p.disease_id "
                    "WHERE p.id = :pid AND p.user_id = :uid"
                ), {"pid": profile_id, "uid": user_id}).first()
            if not row and disease_name:
                row = self.db.execute(sa_text(
                    "SELECT p.id, COALESCE(dt.display_name, dt.name, '未知疾病') as disease_name "
                    "FROM user_disease_profiles p "
                    "LEFT JOIN disease_templates dt ON dt.id = p.disease_id "
                    "WHERE p.user_id = :uid AND (dt.display_name ILIKE :name OR dt.name ILIKE :name)"
                ), {"uid": user_id, "name": f"%{disease_name}%"}).first()
            if not row:
                logger.warning(f"疾病档案未找到: id={profile_id}, name={disease_name}")
                return None

            p_id, p_disease_name = row[0], row[1]
            # 使用原始SQL插入，避免ORM模型与数据库字段不匹配
            symptom_type = symptoms[0]["name"] if symptoms else p_disease_name
            severity_val = overall_severity
            self.db.execute(sa_text(
                "INSERT INTO symptom_logs (user_id, disease_profile_id, log_date, symptom_type, severity, notes, created_at) "
                "VALUES (:uid, :pid, :log_date, :stype, :sev, :notes, NOW())"
            ), {
                "uid": user_id, "pid": p_id, "log_date": today,
                "stype": symptom_type, "sev": severity_val,
                "notes": "通过健康顾问对话自动记录"
            })
            self.db.commit()
            logger.info(f"用户{user_id} 症状: {p_disease_name} 严重度{overall_severity}")
            return {
                "type": "symptom", "status": "saved",
                "message": f"🏥 {p_disease_name}症状(严重度{overall_severity}/10) 已记录"
            }
        except Exception as e:
            logger.error(f"症状记录失败: {e}")
            self.db.rollback()
            return None

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

        # 检测是否是饮食记录消息
        diet_result = None
        diet_context = ""
        if self._is_food_message(message):
            logger.info(f"检测到饮食记录消息: {message[:80]}")
            try:
                nutrition_data = food_recognition_service.estimate_nutrition_from_text(message)
                if nutrition_data.get("success"):
                    # 保存饮食记录
                    diet_result = self._process_diet_record(user_id, message, nutrition_data)
                    if diet_result:
                        # 构建营养数据上下文，让AI基于此回复
                        foods_detail = "\n".join([
                            f"- {f.get('name', '')}: {f.get('quantity', '')}, {f.get('calories', 0)}kcal, "
                            f"蛋白质{f.get('protein', 0)}g, 碳水{f.get('carbs', 0)}g, 脂肪{f.get('fat', 0)}g"
                            for f in nutrition_data.get("foods", [])
                        ])
                        meal_type_cn = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}.get(diet_result["meal_type"], "加餐")
                        diet_context = (
                            f"\n\n[系统提示：已自动分析用户的饮食并保存为{meal_type_cn}记录。营养分析结果：\n"
                            f"食物明细：\n{foods_detail}\n"
                            f"总热量：{nutrition_data.get('total_calories', 0)}kcal\n"
                            f"总蛋白质：{nutrition_data.get('total_protein', 0)}g\n"
                            f"总碳水：{nutrition_data.get('total_carbs', 0)}g\n"
                            f"总脂肪：{nutrition_data.get('total_fat', 0)}g\n"
                            f"请基于以上数据给用户一个友好的饮食反馈，包含各食物热量明细、总热量、营养评价和建议。"
                            f"告知用户饮食已自动记录。]"
                        )
                else:
                    logger.warning(f"营养估算失败: {nutrition_data.get('error')}")
            except Exception as e:
                logger.error(f"饮食检测处理失败: {e}")

        # 构建消息列表（最近 20 条作为上下文）
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()

        # 只取最近 20 条消息避免超长
        recent = history[-20:] if len(history) > 20 else history

        messages = [{"role": "system", "content": await self._get_system_prompt(user_id)}]
        for msg in recent:
            content = msg.content
            # 在最后一条用户消息中追加饮食上下文
            if msg.id == user_msg.id and diet_context:
                content += diet_context
            messages.append({"role": msg.role, "content": content})

        # 调用 OpenClaw API
        try:
            reply_content = await self._call_openclaw(messages)
        except Exception as e:
            logger.error(f"OpenClaw 调用失败: {e}")
            reply_content = "抱歉，健康顾问暂时无法响应，请稍后再试。"

        # 解析活动标记
        clean_reply, actions = self._parse_actions(reply_content)
        activity_results = []
        if actions:
            activity_results = self._execute_actions(user_id, actions)
            logger.info(f"用户{user_id} 执行了{len(activity_results)}个活动")

        # 保存 AI 回复（使用清理后的内容）
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=clean_reply)
        self.db.add(ai_msg)

        # 更新对话标题（首次对话用用户消息做标题）
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        result = {
            "conversation_id": conv.id,
            "reply": clean_reply,
            "message_id": ai_msg.id
        }

        # 添加饮食记录信息
        if diet_result:
            result["diet_saved"] = True
            result["diet_data"] = diet_result

        # 添加活动记录信息
        if activity_results:
            result["activities_saved"] = True
            result["activities"] = activity_results

        return result

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
