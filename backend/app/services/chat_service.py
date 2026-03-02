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
from app.models.daily_health import GarminData, DietRecord, ExerciseRecord, WorkoutRecord, WaterIntake, WorkoutAnalysisResult
from app.models.checkin import CheckinRecord, CheckinTemplate
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.trip import Trip, TripItem
from app.models.illness import IllnessEpisode, IllnessUpdate
from app.models.health_checkin import HealthCheckin
from app.models.chat import ChatConversation, ChatMessage
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.disease_tracking import UserDiseaseProfile, SymptomLog
from app.models.excretion import ExcretionRecord
from app.models.sleep_record import SleepRecord
from app.models.activity_status import ActivityStatus
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.models.vocabulary import VocabularyWord
from app.services.environment.weather_service import weather_service
from app.services.ai.food_recognition import food_recognition_service
from app.services.quark_search import get_search_client

logger = logging.getLogger(__name__)

# 天气数据模块级缓存（每个 worker 进程独立，8小时 TTL）
_weather_cache: dict = {}  # key: city -> (timestamp, data)
_WEATHER_CACHE_TTL = 8 * 3600  # 8 小时

# OpenClaw 配置
OPENCLAW_BASE_URL = settings.openclaw_base_url
OPENCLAW_API_KEY = settings.openclaw_api_key or ""
OPENCLAW_MODEL = settings.openclaw_model


class ChatService:
    """聊天服务"""

    def __init__(self, db: Session):
        self.db = db

    def _extract_city_from_location(self, location: str) -> str:
        """从地点字符串中提取城市名
        例：成都双流T2 → 成都，杭州萧山T4 → 杭州，成都东站 → 成都，江油 → 江油
        """
        import re
        if not location:
            return location
        loc = re.sub(r'T\d+$', '', location).strip()
        airport_codes = ['首都', '双流', '天府', '萧山', '浦东', '虹桥', '白云', '天河',
                         '禄口', '江北', '长水', '太平', '咸阳', '遥墙', '宝安', '流亭']
        station_suffixes = ['东站', '西站', '南站', '北站', '高铁站', '火车站']
        for suffix in airport_codes + station_suffixes:
            if loc.endswith(suffix) and len(loc) > len(suffix):
                loc = loc[:-len(suffix)]
                break
        return loc.strip() or location

    async def _get_weather_cached(self, city: str) -> dict:
        """获取天气综合数据，带 8 小时本地缓存"""
        import time
        now = time.time()
        if city in _weather_cache:
            ts, data = _weather_cache[city]
            if now - ts < _WEATHER_CACHE_TTL:
                logger.debug(f"天气缓存命中: {city}")
                return data
        try:
            data = await asyncio.wait_for(
                weather_service.get_comprehensive_context(city=city),
                timeout=10.0
            )
            _weather_cache[city] = (now, data)
            return data
        except asyncio.TimeoutError:
            logger.warning(f"天气API超时(10s): {city}")
            return {}
        except Exception as e:
            logger.warning(f"天气API失败: {type(e).__name__}: {e}")
            return {}

    async def _build_health_context(self, user_id: int) -> str:
        """构建用户健康上下文，注入为 system prompt"""
        parts = []
        now = datetime.now()
        today = now.date()
        hour = now.hour
        # 时段描述（帮助 AI 给出时间敏感建议，如睡前不宜高强度运动）
        if 5 <= hour < 9:
            time_period = "清晨"
        elif 9 <= hour < 12:
            time_period = "上午"
        elif 12 <= hour < 14:
            time_period = "午间"
        elif 14 <= hour < 18:
            time_period = "下午"
        elif 18 <= hour < 21:
            time_period = "傍晚"
        elif 21 <= hour < 23:
            time_period = "晚上（接近睡眠时间）"
        else:
            time_period = "深夜（应准备入睡）"
        parts.append(f"当前时间: {now.strftime('%H:%M')}（{time_period}）")

        # 用户基本信息
        user = self.db.query(User).filter(User.id == user_id).first()
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        # 检查是否在旅行中，推断当前所在城市（用于天气和地理相关建议）
        travel_city = None
        ongoing_trip_info = None
        try:
            ongoing_trip = self.db.query(Trip).filter(
                Trip.user_id == user_id,
                Trip.start_date <= today,
                Trip.end_date >= today,
            ).first()

            if ongoing_trip:
                today_items = self.db.query(TripItem).filter(
                    TripItem.trip_id == ongoing_trip.id,
                    TripItem.item_date == today,
                ).order_by(TripItem.item_order).all()

                # 优先：今天最后一个到达的交通项目目的地（用户当前落脚点）
                for item in reversed(today_items):
                    if item.item_type in ('flight', 'train', 'bus') and item.destination:
                        travel_city = self._extract_city_from_location(item.destination)
                        break

                # 次选：今天活动或住宿的位置
                if not travel_city:
                    for item in today_items:
                        if item.item_type in ('activity', 'hotel', 'other') and item.location:
                            travel_city = self._extract_city_from_location(item.location)
                            break

                # 兜底：行程目的地字段
                if not travel_city and ongoing_trip.destination:
                    travel_city = ongoing_trip.destination

                if travel_city:
                    ongoing_trip_info = ongoing_trip
        except Exception as e:
            logger.warning(f"获取旅行位置失败: {e}")

        # 用户位置信息（旅行中优先使用行程地点）
        user_city = None
        if travel_city and ongoing_trip_info:
            user_city = travel_city
            parts.append(f"当前位置: {travel_city}（旅行中：{ongoing_trip_info.trip_name}，归家城市不适用）")
        elif profile:
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

        # 提前异步获取天气（与后续数据库查询并行，使用本地缓存）
        weather_task = None
        weather_insert_pos = len(parts)  # 天气数据将插入到此位置（紧接位置信息之后）
        if user_city:
            weather_task = asyncio.create_task(self._get_weather_cached(user_city))

        if user:
            info = f"用户: {user.name or user.username}"
            if user.gender and user.gender not in ("未设置", ""):
                info += f", 性别: {user.gender}"
            # 优先使用 profile 中的 birth_date（用户可编辑），其次用 users 表的
            birth_date = (profile.birth_date if profile and profile.birth_date else None) or user.birth_date
            if birth_date:
                age = today.year - birth_date.year
                # Adjust if birthday hasn't occurred yet this year
                if (today.month, today.day) < (birth_date.month, birth_date.day):
                    age -= 1
                info += f", 年龄: {age}岁"
                # 计算最大心率 (220 - 年龄)，用于运动强度分析
                max_heart_rate = 220 - age
                info += f", 最大心率: {max_heart_rate}bpm (220-年龄)"
            else:
                info += ", 年龄: 未知（用户尚未填写出生日期）"
            parts.append(info)
            # 若缺失关键 profile 信息，提示 AI 引导用户完善
            if not birth_date or not (user.gender and user.gender not in ("未设置", "")):
                parts.append("⚠️ 该用户尚未完善个人资料（出生日期/性别），请在回答涉及年龄的建议时告知用户前往「设置 → 个人资料」填写，不要基于默认值推断年龄。")

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

        # 睡眠/运动数据分析（GarminData 一次性查询30天，Python中过滤，减少数据库往返）
        three_days_ago = today - timedelta(days=3)
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)
        _garmin_30d = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= thirty_days_ago
        ).order_by(GarminData.record_date.desc()).all()
        # 从30天数据中在Python中过滤各时间段
        sleep_3days = [r for r in _garmin_30d if r.record_date >= three_days_ago][:3]

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
        sleep_7days = [r for r in _garmin_30d if r.record_date >= seven_days_ago]

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
        sleep_30days = _garmin_30d

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

        # 运动数据分析（复用上面查询的 GarminData）
        # 最近7天运动数据
        exercise_7days = sleep_7days  # 同一份 7 天 GarminData

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
        exercise_30days = _garmin_30d  # 同一份 30 天 GarminData

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
            birth_date = (profile.birth_date if profile and profile.birth_date else None) or (user.birth_date if user else None)
            if birth_date:
                age = today.year - birth_date.year
                if (today.month, today.day) < (birth_date.month, birth_date.day):
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

        # 最近AI运动分析结论（多模型分析结果）
        recent_analyses = self.db.query(WorkoutAnalysisResult).filter(
            WorkoutAnalysisResult.user_id == user_id,
            WorkoutAnalysisResult.status == "completed",
            WorkoutAnalysisResult.created_at >= thirty_days_ago
        ).order_by(WorkoutAnalysisResult.created_at.desc()).limit(3).all()

        if recent_analyses:
            analysis_lines = ["最近AI运动分析结论:"]
            for ana in recent_analyses:
                agg = (ana.aggregation or "")[:500]
                if agg:
                    created = ana.created_at.strftime("%Y-%m-%d") if ana.created_at else ""
                    analysis_lines.append(f"  [{created}] {agg}")
            if len(analysis_lines) > 1:
                parts.append("\n".join(analysis_lines))

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

        # 饮食数据分析（一次性查询7天，Python中过滤3天，减少数据库往返）
        _diet_7d_all = self.db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= seven_days_ago
        ).order_by(DietRecord.record_date.desc(), DietRecord.meal_time.desc()).all()
        diet_3days = [r for r in _diet_7d_all if r.record_date >= three_days_ago]

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

        # 最近7天饮食统计（复用上面查询的数据）
        diet_7days = _diet_7d_all

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

        # 饮水数据（一次性查询7天，Python中过滤今日）
        _water_7d_all = self.db.query(WaterIntake).filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date >= seven_days_ago,
        ).all()
        water_today = [w for w in _water_7d_all if w.record_date == today]
        if water_today:
            total_ml = sum(w.amount_ml or 0 for w in water_today)
            drink_types = {}
            for w in water_today:
                dt = w.drink_type or "水"
                drink_types[dt] = drink_types.get(dt, 0) + (w.amount_ml or 0)
            type_detail = ", ".join(f"{k}{v}ml" for k, v in drink_types.items())
            target = 2000
            pct = round(total_ml / target * 100)
            parts.append(f"今日饮水: {total_ml}ml/{target}ml ({pct}%), 共{len(water_today)}次 [{type_detail}]")
        else:
            parts.append("今日饮水: 暂无记录")

        # 最近7天饮水统计（复用上面查询的数据）
        water_7days = _water_7d_all
        if water_7days:
            from collections import defaultdict
            daily_water = defaultdict(int)
            for w in water_7days:
                daily_water[w.record_date] += (w.amount_ml or 0)
            days_with_water = len(daily_water)
            total_7d = sum(daily_water.values())
            avg_daily = total_7d / days_with_water if days_with_water > 0 else 0
            target = 2000
            days_met = sum(1 for v in daily_water.values() if v >= target)
            parts.append(
                f"最近7天饮水统计: 有{days_with_water}天记录, "
                f"平均{avg_daily:.0f}ml/天, {days_met}天达标(≥{target}ml)"
            )

        # 打卡数据分析（一次性查询30天，Python中过滤今日/7天，减少数据库往返）
        _checkins_30d = self.db.query(CheckinRecord, CheckinTemplate).join(
            CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id
        ).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date >= thirty_days_ago
        ).all()
        checkins = [(r, t) for r, t in _checkins_30d if r.checkin_date == today]
        if checkins:
            checkin_items = [f"{t.name}({r.value}{t.unit})" for r, t in checkins]
            if checkin_items:
                parts.append(f"今日打卡: {', '.join(checkin_items)}")

        # 最近7天打卡统计（复用上面查询的数据）
        checkins_7days = [(r, t) for r, t in _checkins_30d if r.checkin_date >= seven_days_ago]

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

        # 最近30天打卡统计（复用上面查询的数据）
        checkins_30days = _checkins_30d

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

        # 行程数据分析
        try:
            # 当前进行中的行程
            current_trips = self.db.query(Trip).filter(
                Trip.user_id == user_id,
                Trip.start_date <= today,
                Trip.end_date >= today,
            ).all()

            # 最近90天的历史行程
            ninety_days_ago = today - timedelta(days=90)
            recent_trips = self.db.query(Trip).filter(
                Trip.user_id == user_id,
                Trip.end_date >= ninety_days_ago,
                Trip.end_date < today,
            ).order_by(Trip.start_date.desc()).limit(5).all()

            all_trips = current_trips + recent_trips
            if all_trips:
                for trip in all_trips:
                    is_current = trip.start_date <= today <= trip.end_date
                    prefix = "当前行程" if is_current else "近期行程"
                    trip_header = f"{prefix}: {trip.trip_name}({trip.start_date.strftime('%m/%d')}-{trip.end_date.strftime('%m/%d')})"
                    if trip.destination:
                        trip_header += f" 目的地:{trip.destination}"

                    # 查询该行程的所有明细
                    items = self.db.query(TripItem).filter(
                        TripItem.trip_id == trip.id
                    ).order_by(TripItem.item_date, TripItem.item_order).all()

                    if items:
                        from collections import defaultdict
                        day_items = defaultdict(list)
                        for item in items:
                            day_items[item.item_date].append(item)

                        day_lines = []
                        for d in sorted(day_items.keys()):
                            item_descs = []
                            for item in day_items[d]:
                                if item.item_type in ('flight', 'train', 'bus'):
                                    desc = ""
                                    if item.carrier:
                                        desc += item.carrier
                                    if item.transport_number:
                                        desc += item.transport_number
                                    desc += " "
                                    if item.origin:
                                        desc += item.origin
                                        if item.departure_terminal:
                                            desc += item.departure_terminal
                                    if item.departure_time:
                                        desc += f" {item.departure_time}"
                                    desc += "→"
                                    if item.destination:
                                        desc += item.destination
                                        if item.arrival_terminal:
                                            desc += item.arrival_terminal
                                    if item.arrival_time:
                                        desc += f" {item.arrival_time}"
                                    item_descs.append(desc.strip())
                                elif item.item_type == 'hotel':
                                    desc = f"住宿:{item.title}"
                                    if item.location:
                                        desc += f"({item.location})"
                                    item_descs.append(desc)
                                else:
                                    desc = item.title
                                    if item.location:
                                        desc += f"({item.location})"
                                    item_descs.append(desc)

                            day_lines.append(f"  {d.strftime('%m/%d')}: {'; '.join(item_descs)}")

                        parts.append(trip_header + "\n" + "\n".join(day_lines))
                    else:
                        parts.append(trip_header)
        except Exception as e:
            logger.warning(f"获取行程数据失败: {e}")

        # ── 排泄数据（最近7天） ──────────────────────────────────────
        try:
            excretion_records = self.db.query(ExcretionRecord).filter(
                ExcretionRecord.user_id == user_id,
                ExcretionRecord.record_date >= seven_days_ago,
            ).order_by(ExcretionRecord.record_date.desc()).all()

            if excretion_records:
                bowel_recs = [r for r in excretion_records if r.type == "bowel"]
                urine_recs = [r for r in excretion_records if r.type == "urine"]
                exc_parts = [f"最近7天排泄记录:"]
                if bowel_recs:
                    stool_types = [r.stool_type for r in bowel_recs if r.stool_type]
                    avg_st = round(sum(stool_types) / len(stool_types), 1) if stool_types else None
                    blood_cnt = sum(1 for r in bowel_recs if r.blood_present)
                    exc_parts.append(f"大便{len(bowel_recs)}次")
                    if avg_st:
                        exc_parts.append(f"平均Bristol{avg_st}")
                    if blood_cnt:
                        exc_parts.append(f"有血{blood_cnt}次(需关注)")
                if urine_recs:
                    exc_parts.append(f"小便{len(urine_recs)}次记录")
                parts.append(", ".join(exc_parts))
        except Exception as e:
            logger.warning(f"获取排泄数据失败: {e}")

        # ── 手动睡眠记录（最近7天，仅无Garmin睡眠数据时） ──────────────
        try:
            manual_sleep = self.db.query(SleepRecord).filter(
                SleepRecord.user_id == user_id,
                SleepRecord.record_date >= seven_days_ago,
            ).order_by(SleepRecord.record_date.desc()).all()

            if manual_sleep:
                sleep_lines = [f"最近7天手动睡眠记录({len(manual_sleep)}天):"]
                for sr in manual_sleep[:5]:
                    info = [f"{sr.record_date}"]
                    if sr.total_duration_minutes:
                        h = sr.total_duration_minutes // 60
                        m = sr.total_duration_minutes % 60
                        info.append(f"时长{h}h{m}min")
                    info.append(f"质量{sr.sleep_quality}/5")
                    if sr.wake_count:
                        info.append(f"夜醒{sr.wake_count}次")
                    if sr.morning_feeling:
                        info.append(f"醒后{sr.morning_feeling}/5")
                    sleep_lines.append("  " + " ".join(info))
                parts.append("\n".join(sleep_lines))
        except Exception as e:
            logger.warning(f"获取睡眠记录失败: {e}")

        # ── 当前病症 ──────────────────────────────────────────────────
        try:
            active_illnesses = self.db.query(IllnessEpisode).filter(
                IllnessEpisode.user_id == user_id,
                IllnessEpisode.status != "resolved",
            ).order_by(IllnessEpisode.start_date.desc()).all()

            if active_illnesses:
                status_label = {"active": "发作中", "improving": "好转中"}
                illness_lines = []
                for ep in active_illnesses:
                    days = (today - ep.start_date).days + 1
                    label = status_label.get(ep.status, ep.status)
                    illness_lines.append(
                        f"  {ep.name}(id={ep.id}, {label}, 严重度{ep.severity}/10, 已{days}天)"
                    )
                parts.append("当前病症:\n" + "\n".join(illness_lines))
        except Exception as e:
            logger.warning(f"获取病症数据失败: {e}")

        # ── 智能计划进度 ──────────────────────────────────────────────
        try:
            week_start = today - timedelta(days=today.weekday())
            active_plan = self.db.query(WeeklyPlan).filter(
                WeeklyPlan.user_id == user_id,
                WeeklyPlan.week_start == week_start,
                WeeklyPlan.status == "active"
            ).first()

            if active_plan:
                plan_lines = [f"本周智能计划({week_start} ~ {week_start + timedelta(days=6)}):"]
                plan_lines.append(f"  重点: {', '.join(active_plan.focus_areas or [])}")
                plan_lines.append(f"  总体完成率: {active_plan.completion_rate:.0f}%")

                day_of_week = today.weekday() + 1
                today_items = [i for i in active_plan.items if i.day_of_week == day_of_week]
                if today_items:
                    done = [i for i in today_items if i.is_completed]
                    undone = [i for i in today_items if not i.is_completed]
                    plan_lines.append(f"  今日计划({len(done)}/{len(today_items)}完成):")
                    for i in done:
                        plan_lines.append(f"    ✅ {i.title}")
                    for i in undone:
                        plan_lines.append(f"    ⬜ {i.title}")
                parts.append("\n".join(plan_lines))
        except Exception as e:
            logger.warning(f"获取智能计划数据失败: {e}")

        # 等待天气数据（此时数据库查询已全部完成，网络IO大概率已就绪）
        if weather_task:
            try:
                context = await weather_task
                weather_parts = []
                weather = context.get('weather')
                if weather:
                    weather_info = f"当前天气: {weather.get('text', '')}, 温度{weather.get('temp', '')}℃"
                    if weather.get('feelsLike'):
                        weather_info += f", 体感{weather.get('feelsLike')}℃"
                    if weather.get('humidity'):
                        weather_info += f", 湿度{weather.get('humidity')}%"
                    if weather.get('windDir') and weather.get('windScale'):
                        weather_info += f", {weather.get('windDir')}{weather.get('windScale')}级"
                    weather_parts.append(weather_info)
                air_quality = context.get('air_quality')
                if air_quality and air_quality.get('available'):
                    aqi = air_quality.get('aqi', 'N/A')
                    level = air_quality.get('aqi_description') or air_quality.get('level', '未知')
                    pm25 = air_quality.get('pm25')
                    primary = air_quality.get('primary_pollutant', '') or air_quality.get('station', '')
                    air_info = f"空气质量: AQI {aqi} ({level})"
                    if pm25 is not None and pm25 > 0:
                        air_info += f", PM2.5 {pm25:.0f}μg/m³"
                    if primary and primary not in ('无', ''):
                        air_info += f", 主要污染物: {primary}"
                    # 根据 AQI 给出户外运动建议（让 AI 知道是否适合户外跑步）
                    try:
                        aqi_val = int(aqi)
                        if aqi_val > 200:
                            air_info += " ⚠️ 严重污染，禁止户外运动"
                        elif aqi_val > 150:
                            air_info += " ⚠️ 污染较重，不建议户外跑步"
                        elif aqi_val > 100:
                            air_info += " ⚠️ 轻度污染，敏感人群避免户外长跑"
                    except (ValueError, TypeError):
                        pass
                    weather_parts.append(air_info)
                lifestyle = context.get('lifestyle_indices')
                if lifestyle and lifestyle.get('available'):
                    sport = lifestyle.get('1')  # 1 = 运动指数
                    if sport:
                        weather_parts.append(f"运动指数: {sport.get('category', '')} - {sport.get('text', '')}")
                # 将天气数据插入到位置信息之后
                for i, wp in enumerate(weather_parts):
                    parts.insert(weather_insert_pos + i, wp)
            except Exception as e:
                logger.warning(f"获取环境信息失败: {type(e).__name__}: {e}")

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

        # 当前活动状态
        try:
            active_status = self.db.query(ActivityStatus).filter(
                ActivityStatus.user_id == user_id,
                ActivityStatus.is_active == True,
            ).order_by(ActivityStatus.start_time.desc()).first()
            if active_status:
                status_info = f'当前活动状态: {active_status.status_text} (类别: {active_status.category})'
                if active_status.start_time:
                    status_info += f', 开始时间: {active_status.start_time.strftime("%H:%M")}'
                if active_status.estimated_duration_minutes:
                    status_info += f', 预计时长: {active_status.estimated_duration_minutes}分钟'
                parts.append(status_info)
        except Exception as e:
            logger.warning(f"查询活动状态失败(可忽略): {e}")

        return "\n\n".join(parts)

    async def _get_system_prompt(self, user_id: int, is_kids_mode: bool = False) -> str:
        """组装完整的 system prompt"""
        if is_kids_mode:
            base = (
                "你是一个有趣的健康学习小助手。你的名字叫「健康小老师」。\n"
                "你正在和一个小朋友聊天，请用简单易懂、活泼有趣的语言回答问题。\n\n"
                "## 你的角色\n"
                "- 你是小朋友的健康好伙伴，用讲故事、打比方的方式解释健康知识\n"
                "- 用鼓励和表扬的语气，让小朋友养成好习惯\n"
                "- 回答要简短有趣，适当使用emoji让对话更生动\n"
                "- 遇到复杂的医学问题，要告诉小朋友「这个问题要问爸爸妈妈哦」\n\n"
                "## 你擅长的话题\n"
                "- 为什么要多喝水、多吃蔬菜水果\n"
                "- 运动的好处和有趣的运动方式\n"
                "- 好的睡眠习惯和早睡早起的重要性\n"
                "- 个人卫生知识（洗手、刷牙等）\n"
                "- 食物营养知识（用小朋友能理解的方式）\n"
                "- 情绪管理和心理健康小知识\n"
                "- 回答小朋友关于身体的各种「为什么」\n\n"
                "## 注意事项\n"
                "- 不要使用专业医学术语，用比喻来解释\n"
                "- 不要给出具体的药物或治疗建议\n"
                "- 鼓励小朋友有问题要告诉爸爸妈妈\n"
                "- 使用中文回答\n\n"
                "你具有联网搜索能力。系统会自动为用户的问题搜索最新信息，搜索结果会附在用户消息后面的[参考资料]中。"
                "请自然地整合这些信息来回答，不要提及'搜索结果'、'参考资料'、'根据搜索'等字眼，也不要说自己没有搜索功能。\n\n"
                "你具有饮食记录和热量计算功能。当用户描述吃了什么食物时，系统会自动分析营养成分并保存饮食记录。"
                "如果消息中包含[系统提示]的营养分析结果，请用小朋友能理解的方式反馈营养信息，比如「哇，你吃的鸡蛋有好多蛋白质，可以让你长得更壮哦！」\n\n"
                "## 英语单词学习功能\n"
                "你还是一个英语学习小助手！当用户要求学习英语单词时，提供全面的单词练习。\n\n"
                "### 触发条件\n"
                "用户消息包含以下模式时触发：\n"
                "- \"学单词 xxx\" / \"学习单词 xxx\" / \"背单词 xxx\"\n"
                "- \"帮我学 xxx\" / \"help me learn xxx\"\n"
                "- \"xxx是什么意思\" / \"xxx怎么读\" / \"xxx怎么用\"\n\n"
                "### 回复格式\n"
                "请用以下结构回复（用中文讲解，适合初中生理解）：\n\n"
                "**1. 单词与发音** - 单词、美式和英式音标、中文释义（列出常见词性和含义）、发音技巧\n\n"
                "**2. 词根词缀** - 拆解单词构成，帮助记忆；相同词根的其他常见单词\n\n"
                "**3. 用法与例句** - 4-5个实用例句（中英对照，适合初中水平）；常见搭配\n\n"
                "**4. 近义词与反义词** - 列出2-3个近义词和反义词，简要说明区别\n\n"
                "**5. 小练习** - 一个填空题或翻译题，帮助巩固\n\n"
                "**6. 记忆技巧** - 联想记忆法或其他有趣的记忆方法\n\n"
                "### 单词记录标记\n"
                "当你为用户讲解了一个单词后，在回复末尾附加单词记录标记（与活动标记格式相同）：\n"
                '<<<ACTIONS:[{"type":"vocabulary","word":"单词","phonetic_us":"美式音标","phonetic_uk":"英式音标",'
                '"meanings":"[{\\"pos\\":\\"v.\\",\\"def\\":\\"中文释义\\"}]","synonyms":"近义词逗号分隔","antonyms":"反义词逗号分隔",'
                '"word_roots":"词根词缀说明","example_sentences":"[{\\"en\\":\\"English sentence.\\",\\"zh\\":\\"中文翻译\\"}]"}]>>>\n\n'
                "### 单词标记示例\n"
                "- \"学单词 abandon\" → 提供完整讲解 + vocabulary action标记\n"
                "- \"contribute是什么意思\" → 提供完整讲解 + vocabulary action标记\n\n"
                "### 注意\n"
                "- 讲解内容适合初中生水平，不要太难也不要太幼稚\n"
                "- 例句尽量贴近中学生活\n"
                "- 鼓励学习，适当给予表扬\n"
            )
        else:
            base = (
                "你是一个专业的私人智能助理。你的名字叫「智能助理」。\n"
                "请基于用户的健康数据，提供个性化、科学、实用的健康建议。\n"
                "回答要简洁友好，避免过度医学化。如涉及严重健康问题请建议就医。\n"
                "使用中文回答。\n\n"
                "你具有联网搜索能力。系统会自动为用户的问题搜索最新信息，搜索结果会附在用户消息后面的[参考资料]中。"
                "请自然地整合这些信息来回答，不要提及'搜索结果'、'参考资料'、'根据搜索'等字眼，也不要说自己没有搜索功能。\n\n"
                "你具有饮食记录和热量计算功能。当用户描述吃了什么食物时，系统会自动分析营养成分并保存饮食记录。"
                "如果消息中包含[系统提示]的营养分析结果，请基于这些数据给用户清晰的热量和营养反馈。\n\n"
                "如果用户有活跃的智能计划，你应该：\n"
                "- 了解用户今天的待办事项，提供针对性的建议\n"
                "- 鼓励用户完成未完成的计划项\n"
                "- 根据计划完成情况给出调整建议\n"
                "- 回答关于计划进度的问题\n"
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
            '{"type":"rhinitis","nasal_wash":次数或null,"nasal_wash_type":"wash或soak","sneeze_count":次数或null},'
            '{"type":"water","amount":毫升数,"drink_type":"水/茶/咖啡"},'
            '{"type":"supplement","supplement_id":ID,"supplement_name":"名称"},'
            '{"type":"symptom","profile_id":ID,"disease_name":"疾病名","overall_severity":0到10,"symptoms":[{"name":"症状","severity":1到10}]},'
            '{"type":"activity_status","activity_name":"活动名","category":"studying|working|exercising|resting|entertainment|other","estimated_duration_minutes":分钟数}]>>>\n\n'
            "### 活动状态说明\n"
            "当用户说\"我正在...\"或\"我开始...\"时，记录当前活动状态。这不同于已完成的活动，而是正在进行的状态。\n"
            "默认时长估算：学习/工作=120分钟，运动/锻炼=60分钟，休息/午睡=30分钟，阅读=60分钟，娱乐/游戏=60分钟，其他=60分钟\n"
            "当用户说\"学习完了\"\"不学了\"等表示结束当前活动时，也用activity_status记录，并附加\"end\":true\n\n"
            "### 示例\n"
            "- \"刚踢腿200下\" → checkin, 匹配踢腿模板, value=200\n"
            "- \"洗了鼻子\" → rhinitis, nasal_wash=1, nasal_wash_type=\"wash\"\n"
            "- \"泡鼻了\" → rhinitis, nasal_wash=1, nasal_wash_type=\"soak\"\n"
            "- \"今天打了好几个喷嚏\" → rhinitis, sneeze_count=估算数量(默认5)\n"
            "- \"打了3个喷嚏\" → rhinitis, sneeze_count=3\n"
            "- \"喝了一杯水\" → water, amount=250\n"
            "- \"喝了500ml水\" → water, amount=500\n"
            "- \"吃了维生素D\" → supplement\n"
            "- \"做了30个俯卧撑然后喝了杯水\" → 两个活动\n"
            "- \"我正在学习\" → activity_status, activity_name=\"学习\", category=\"studying\", estimated_duration_minutes=120\n"
            "- \"开始工作了\" → activity_status, activity_name=\"工作\", category=\"working\", estimated_duration_minutes=120\n"
            "- \"我去跑步了\" → activity_status, activity_name=\"跑步\", category=\"exercising\", estimated_duration_minutes=60\n"
            "- \"学习完了\" → activity_status, activity_name=\"学习\", end=true\n"
            "- \"休息一下\" → activity_status, activity_name=\"休息\", category=\"resting\", estimated_duration_minutes=30\n\n"
            "### 不应记录\n"
            "- \"我应该每天踢多少下？\" → 提问不记录\n"
            "- \"明天计划跑步\" → 计划不记录\n"
            "- \"帮我看看打卡情况\" → 查询不记录\n"
        )
        if activity_ctx:
            activity_prompt += f"\n### 用户数据\n{activity_ctx}\n"

        # 智能计划创建功能
        create_plan_prompt = (
            "\n\n## 智能计划创建功能\n"
            "当用户请求制定周计划时（如「帮我制定下周计划」「规划一下本周运动」「生成周计划」），"
            "你可以直接调用系统为用户在「智能计划」中生成计划。\n\n"
            "### 触发条件\n"
            "用户明确要求「制定计划」「生成计划」「做个周计划」「规划一下」时触发。\n\n"
            "### 格式\n"
            "在正常回复之后附加（用户不可见）：\n"
            '<<<ACTIONS:[{"type":"create_plan","target_week":"next或current","user_focus":["重点1","重点2"],'
            '"user_notes":"用户提到的特殊需求或限制，如周三出差","intensity":"light或moderate或challenge"}]>>>\n\n'
            "### 规则\n"
            "1. target_week: \"next\"=下周，\"current\"=本周，默认 \"next\"\n"
            "2. user_focus: 根据对话和健康数据提取 2-3 个重点方向（如[\"有氧运动\",\"体重控制\"]）\n"
            "3. user_notes: 用户提到的约束条件（如\"周三出差不能运动\"），无约束则空字符串\n"
            "4. intensity: 根据用户当前状态判断，默认 moderate\n"
            "5. 触发后在回复中明确告知用户：「正在为你生成计划，完成后可在「智能计划」页面查看」\n"
            "6. 不要询问用户是否需要写入，直接写入\n\n"
            "### 示例\n"
            "- \"帮我制定下周的锻炼计划\" → create_plan, target_week=\"next\", user_focus=[\"有氧运动\",\"力量训练\"]\n"
            "- \"规划一下本周，我周三有出差\" → create_plan, target_week=\"current\", user_notes=\"周三出差\"\n"
            "- \"做个减脂周计划\" → create_plan, target_week=\"next\", user_focus=[\"减脂\",\"饮食控制\"]\n"
        )

        # 运动完成分析功能
        workout_analyze_prompt = (
            "\n\n## 运动完成分析功能\n"
            "当用户表达运动/跑步/锻炼/训练完成的意图时，帮助用户同步数据并分析。\n\n"
            "### 触发条件\n"
            "用户说「跑完了」「运动结束」「锻炼完了」「训练结束了」「刚跑完步」"
            "「帮我分析刚才的运动」「同步一下运动数据」等表达已完成运动的意图时触发。\n\n"
            "### 格式\n"
            "在正常回复之后附加（用户不可见）：\n"
            '<<<ACTIONS:[{"type":"workout_analyze","workout_type":"运动类型"}]>>>\n\n'
            "### 规则\n"
            "1. workout_type 根据用户描述判断：running/cycling/swimming/hiit/strength/yoga/other\n"
            "2. 如用户未明确运动类型，使用 \"other\"，系统会自动检测最新记录的类型\n"
            "3. 触发后在回复中告知用户：「正在同步 Garmin 数据并分析你的运动，请稍等...」\n"
            "4. 只在用户表达**已完成**运动时触发，计划运动或询问不触发\n\n"
            "### 示例\n"
            "- \"我跑完了\" → workout_analyze, workout_type=\"running\"\n"
            "- \"刚骑完车\" → workout_analyze, workout_type=\"cycling\"\n"
            "- \"锻炼结束了，帮我看看数据\" → workout_analyze, workout_type=\"other\"\n"
            "- \"游泳完了，同步一下\" → workout_analyze, workout_type=\"swimming\"\n"
        )

        health_ctx = await self._build_health_context(user_id)
        prompt = base + activity_prompt + create_plan_prompt + workout_analyze_prompt
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

    def _should_search(self, message: str) -> bool:
        """检测消息是否需要联网搜索 - 默认搜索，只排除明确不需要的"""
        msg = message.strip()
        # 饮食记录消息不搜索
        if self._is_food_message(message):
            return False
        # 太短的消息不搜索（3个字以下）
        if len(msg) < 3:
            return False
        # 简单打招呼/确认不搜索
        no_search = ['你好', '嗨', '早上好', '晚上好', '下午好', '谢谢', '好的',
                     '嗯', '哦', '知道了', '明白', '收到', '好', '是的', '不是',
                     '对', '不对', '行', '可以', '不行', '没有', '有']
        if msg in no_search:
            return False
        # 纯活动记录陈述（已由活动系统处理）不搜索
        activity_only = ['刚', '做了', '喝了水', '吃了药', '洗了鼻']
        if len(msg) < 10 and any(msg.startswith(w) for w in activity_only):
            return False
        # 其余消息默认都搜索
        return True

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
                notes=f"通过智能助理对话自动记录: {message[:100]}",
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
                elif action_type == "rhinitis":
                    result = self._handle_rhinitis_action(user_id, action, today)
                elif action_type == "illness_create":
                    result = self._handle_illness_create(user_id, action, today)
                elif action_type == "illness_update":
                    result = self._handle_illness_update(user_id, action, today)
                elif action_type == "excretion":
                    result = self._handle_excretion_action(user_id, action, today, now)
                elif action_type == "sleep":
                    result = self._handle_sleep_action(user_id, action, today)
                elif action_type == "activity_status":
                    result = self._handle_activity_status_action(user_id, action, now)
                elif action_type == "vocabulary":
                    result = self._handle_vocabulary_action(user_id, action)
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
            notes="通过智能助理对话自动记录"
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

    def _handle_rhinitis_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理鼻炎活动（洗鼻/泡鼻/打喷嚏），直接写入 health_checkins 表"""
        nasal_wash = action.get("nasal_wash")          # 洗鼻次数，通常1
        nasal_wash_type = action.get("nasal_wash_type", "wash")  # "wash" 或 "soak"
        sneeze_count = action.get("sneeze_count")       # 喷嚏次数
        now_str = datetime.now().strftime("%H:%M")

        hc = self.db.query(HealthCheckin).filter(
            HealthCheckin.user_id == user_id,
            HealthCheckin.checkin_date == today,
        ).first()
        if not hc:
            hc = HealthCheckin(user_id=user_id, checkin_date=today)
            self.db.add(hc)

        msgs = []
        if nasal_wash:
            hc.nasal_wash_count = (hc.nasal_wash_count or 0) + int(nasal_wash)
            times = list(hc.nasal_wash_times or [])
            times.append({"time": now_str, "type": nasal_wash_type})
            hc.nasal_wash_times = times
            label = "泡鼻" if nasal_wash_type == "soak" else "洗鼻"
            msgs.append(f"🫧 {label} {hc.nasal_wash_count}次 已记录")

        if sneeze_count:
            hc.sneeze_count = (hc.sneeze_count or 0) + int(sneeze_count)
            times = list(hc.sneeze_times or [])
            times.append({"time": now_str, "count": int(sneeze_count)})
            hc.sneeze_times = times
            msgs.append(f"🤧 打喷嚏 {hc.sneeze_count}次 已记录")

        if not msgs:
            return None

        self.db.commit()
        return {"type": "rhinitis", "status": "saved", "message": "、".join(msgs)}

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
            notes="通过智能助理对话自动记录"
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
                "notes": "通过智能助理对话自动记录"
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
        conversation_id: Optional[int] = None,
        is_kids_mode: bool = False,
        image_base64: Optional[str] = None,
        image_type: Optional[str] = "jpeg",
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

        # 联网搜索增强
        search_context = ""
        if self._should_search(message):
            search_client = get_search_client()
            if search_client:
                try:
                    search_context = await search_client.search_with_context(message, max_results=3, context_length=500)
                    if search_context:
                        logger.info(f"夸克搜索命中: query={message[:50]}")
                except Exception as e:
                    logger.warning(f"夸克搜索异常: {e}")

        # 构建消息列表（最近 20 条作为上下文）
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()

        # 只取最近 20 条消息避免超长
        recent = history[-20:] if len(history) > 20 else history

        messages = [{"role": "system", "content": await self._get_system_prompt(user_id, is_kids_mode=is_kids_mode)}]
        for msg in recent:
            content = msg.content
            # 在最后一条用户消息中追加饮食上下文和搜索上下文
            if msg.id == user_msg.id:
                if diet_context:
                    content += diet_context
                if search_context:
                    content += f"\n\n[参考资料 - 来自网络搜索]\n{search_context}\n[请基于以上参考资料和你的专业知识回答用户问题，不要直接提及搜索结果或参考资料。]"
                # 多模态消息：附带图片
                if image_base64:
                    content_parts = [
                        {"type": "text", "text": content},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_type};base64,{image_base64}",
                            "detail": "high"
                        }}
                    ]
                    messages.append({"role": msg.role, "content": content_parts})
                    continue
            messages.append({"role": msg.role, "content": content})

        # 调用 OpenClaw API
        try:
            reply_content = await self._call_openclaw(messages)
        except Exception as e:
            logger.error(f"OpenClaw 调用失败: {type(e).__name__}: {e}")
            reply_content = "抱歉，智能助理暂时无法响应，请稍后再试。"

        # 解析活动标记
        clean_reply, actions = self._parse_actions(reply_content)
        activity_results = []
        if actions:
            # 异步 action 单独处理（create_plan, workout_analyze）
            plan_actions = [a for a in actions if a.get("type") == "create_plan"]
            workout_actions = [a for a in actions if a.get("type") == "workout_analyze"]
            other_actions = [a for a in actions if a.get("type") not in ("create_plan", "workout_analyze")]
            if other_actions:
                activity_results = self._execute_actions(user_id, other_actions)
            for pa in plan_actions:
                plan_result = await self._handle_create_plan_async(user_id, pa)
                if plan_result:
                    activity_results.append(plan_result)
            for wa in workout_actions:
                workout_result = await self._handle_workout_analyze_action(user_id, wa)
                if workout_result:
                    activity_results.append(workout_result)
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

        # 运动分析结果作为追加消息保存到对话历史
        workout_analysis_msg = None
        if activity_results:
            for ar in activity_results:
                if ar.get("type") == "workout_analyze" and ar.get("status") == "analyzed":
                    analysis_content = ar.get("message", "")
                    if analysis_content:
                        workout_analysis_msg = ChatMessage(
                            conversation_id=conv.id,
                            role="assistant",
                            content=analysis_content
                        )
                        self.db.add(workout_analysis_msg)
                        self.db.commit()
                        self.db.refresh(workout_analysis_msg)
                        result["workout_analysis"] = {
                            "message_id": workout_analysis_msg.id,
                            "content": analysis_content,
                            "workout_data": ar.get("workout_data"),
                        }
                    break

        # 添加饮食记录信息
        if diet_result:
            result["diet_saved"] = True
            result["diet_data"] = diet_result

        # 添加活动记录信息（排除workout_analyze，已单独处理）
        non_workout_activities = [a for a in activity_results if a.get("type") != "workout_analyze"] if activity_results else []
        if non_workout_activities:
            result["activities_saved"] = True
            result["activities"] = non_workout_activities

            # 检查是否有活动状态记录（需要设置提醒）
            for ar in activity_results:
                if ar.get("type") == "activity_status" and ar.get("status") == "saved":
                    reminder_mins = ar.get("reminder_minutes")
                    if reminder_mins and reminder_mins > 0:
                        result["reminder"] = {
                            "reminder_minutes": reminder_mins,
                            "reminder_message": ar.get("reminder_message", "该休息一下了"),
                            "activity_name": ar.get("activity_name", ""),
                        }
                        break

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

        async with httpx.AsyncClient(timeout=240.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        return choice.get("message", {}).get("content", "").strip()

    async def _call_openclaw_stream(self, messages: list):
        """调用 OpenClaw 流式 API，逐 token yield"""
        url = f"{OPENCLAW_BASE_URL}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if OPENCLAW_API_KEY:
            headers["Authorization"] = f"Bearer {OPENCLAW_API_KEY}"

        payload = {
            "model": OPENCLAW_MODEL,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=240.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def send_message_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        is_kids_mode: bool = False,
        image_base64: Optional[str] = None,
        image_type: Optional[str] = "jpeg",
    ):
        """流式发送消息，yield SSE 事件字典"""
        # 获取或创建对话
        if conversation_id:
            conv = self.db.query(ChatConversation).filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            ).first()
            if not conv:
                yield {"event": "error", "data": {"message": "对话不存在"}}
                return
        else:
            conv = ChatConversation(user_id=user_id, title=message[:50])
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)

        # 保存用户消息
        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        # 饮食检测
        diet_result = None
        diet_context = ""
        if self._is_food_message(message):
            try:
                nutrition_data = food_recognition_service.estimate_nutrition_from_text(message)
                if nutrition_data.get("success"):
                    diet_result = self._process_diet_record(user_id, message, nutrition_data)
                    if diet_result:
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
                            f"请基于以上数据给用户一个友好的饮食反馈。告知用户饮食已自动记录。]"
                        )
            except Exception as e:
                logger.warning(f"流式模式饮食检测异常: {e}")

        # 搜索上下文
        search_context = ""
        if not diet_context and not image_base64 and self._should_search(message):
            try:
                search_client = get_search_client()
                if search_client:
                    results = await search_client.search(message, max_results=3)
                    if results:
                        search_context = "\n".join([f"- {r.get('title', '')}: {r.get('content', '')[:500]}" for r in results])
            except Exception as e:
                logger.warning(f"流式模式搜索异常: {e}")

        # 构建消息列表
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()
        recent = history[-20:] if len(history) > 20 else history

        messages = [{"role": "system", "content": await self._get_system_prompt(user_id, is_kids_mode=is_kids_mode)}]
        for msg in recent:
            content = msg.content
            if msg.id == user_msg.id:
                if diet_context:
                    content += diet_context
                if search_context:
                    content += f"\n\n[参考资料 - 来自网络搜索]\n{search_context}\n[请基于以上参考资料和你的专业知识回答用户问题，不要直接提及搜索结果或参考资料。]"
                if image_base64:
                    content_parts = [
                        {"type": "text", "text": content},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_type};base64,{image_base64}",
                            "detail": "high"
                        }}
                    ]
                    messages.append({"role": msg.role, "content": content_parts})
                    continue
            messages.append({"role": msg.role, "content": content})

        # 流式调用 OpenClaw
        full_response = ""
        in_action_block = False
        try:
            async for token in self._call_openclaw_stream(messages):
                full_response += token
                # 检测 action 标记开始，停止向前端发送
                if "<<<ACTIONS:" in full_response and not in_action_block:
                    in_action_block = True
                    # 发送 action 标记前的最后一段文本
                    pre_action = full_response.split("<<<ACTIONS:")[0]
                    already_sent = full_response[:len(full_response) - len(token)]
                    remaining = pre_action[len(already_sent):]
                    if remaining:
                        yield {"event": "token", "data": {"content": remaining}}
                    continue
                if not in_action_block:
                    yield {"event": "token", "data": {"content": token}}
        except Exception as e:
            logger.error(f"OpenClaw 流式调用失败: {type(e).__name__}: {e}")
            full_response = "抱歉，智能助理暂时无法响应，请稍后再试。"
            yield {"event": "token", "data": {"content": full_response}}

        # 解析 actions
        clean_reply, actions = self._parse_actions(full_response)
        activity_results = []
        if actions:
            plan_actions = [a for a in actions if a.get("type") == "create_plan"]
            workout_actions = [a for a in actions if a.get("type") == "workout_analyze"]
            other_actions = [a for a in actions if a.get("type") not in ("create_plan", "workout_analyze")]
            if other_actions:
                activity_results = self._execute_actions(user_id, other_actions)
            for pa in plan_actions:
                plan_result = await self._handle_create_plan_async(user_id, pa)
                if plan_result:
                    activity_results.append(plan_result)
            for wa in workout_actions:
                workout_result = await self._handle_workout_analyze_action(user_id, wa)
                if workout_result:
                    activity_results.append(workout_result)

        # 保存 AI 回复
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=clean_reply)
        self.db.add(ai_msg)
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        # 构建完成事件
        result_data = {
            "conversation_id": conv.id,
            "message_id": ai_msg.id,
        }
        if diet_result:
            result_data["diet_saved"] = True
            result_data["diet_data"] = diet_result
        non_workout = [a for a in activity_results if a.get("type") != "workout_analyze"] if activity_results else []
        if non_workout:
            result_data["activities_saved"] = True
            result_data["activities"] = non_workout
        # 运动分析结果
        for ar in (activity_results or []):
            if ar.get("type") == "workout_analyze" and ar.get("status") == "analyzed":
                analysis_content = ar.get("message", "")
                if analysis_content:
                    workout_analysis_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=analysis_content)
                    self.db.add(workout_analysis_msg)
                    self.db.commit()
                    self.db.refresh(workout_analysis_msg)
                    result_data["workout_analysis"] = {
                        "message_id": workout_analysis_msg.id,
                        "content": analysis_content,
                    }
                break

        yield {"event": "done", "data": result_data}

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

    async def _handle_create_plan_async(self, user_id: int, action: dict) -> Optional[Dict]:
        """通过 AI 对话直接生成并写入智能计划"""
        from app.services.smart_plan_service import SmartPlanService
        target_week = action.get("target_week", "next")
        user_focus = action.get("user_focus") or []
        user_notes = action.get("user_notes") or ""
        intensity = action.get("intensity", "moderate")
        try:
            service = SmartPlanService(self.db)
            result = await service.generate_plan(
                user_id,
                target_week=target_week,
                user_focus=user_focus,
                user_notes=user_notes,
                intensity=intensity,
            )
            plan = result["plan"]
            week_label = "下周" if target_week == "next" else "本周"
            logger.info(f"用户{user_id} AI 自动生成{week_label}计划 plan_id={plan.id}")
            return {
                "type": "create_plan",
                "status": "saved",
                "plan_id": plan.id,
                "week_label": week_label,
                "item_count": len(plan.items),
                "message": f"已为你生成{week_label}计划，共 {len(plan.items)} 项行动，可在「智能计划」页面查看",
            }
        except Exception as e:
            logger.error(f"AI 自动生成计划失败: {type(e).__name__}: {e}")
            return {
                "type": "create_plan",
                "status": "failed",
                "message": "计划生成失败，请稍后在「智能计划」页面手动生成",
            }

    async def _handle_workout_analyze_action(self, user_id: int, action: dict) -> Optional[Dict]:
        """处理运动完成分析 action：同步Garmin → 检测运动 → 多模型分析"""
        workout_type = action.get("workout_type", "other")
        try:
            from app.services.post_run_analyze import PostRunAnalyzeService
            service = PostRunAnalyzeService(self.db)
            result = await service.analyze(
                user_id=user_id,
                workout_type=workout_type if workout_type != "other" else None,
                format="full",
            )
            if not result.get("success"):
                return {
                    "type": "workout_analyze",
                    "status": "no_data",
                    "message": result.get("message", "未检测到运动记录"),
                }

            workout = result.get("workout", {})
            analysis = result.get("multi_model_analysis", {})
            aggregation = analysis.get("aggregation", "")

            # Build workout summary line
            parts = []
            if workout.get("name"):
                parts.append(workout["name"])
            if workout.get("distance_km"):
                parts.append(f"{workout['distance_km']}km")
            if workout.get("duration_min"):
                parts.append(f"{workout['duration_min']}分钟")
            if workout.get("pace"):
                parts.append(f"配速{workout['pace']}")
            workout_line = " | ".join(parts)

            # Build model insights
            model_insights = ""
            model_results = analysis.get("model_results", [])
            if model_results:
                insights = []
                for mr in model_results:
                    site = mr.get("site", "")
                    content = mr.get("content", "")
                    display_name = site.replace("lb-", "").replace("-", " ").title()
                    if content:
                        preview = content[:300] + "..." if len(content) > 300 else content
                        insights.append(f"**{display_name}**:\n{preview}")
                if insights:
                    model_insights = "\n\n---\n\n".join(insights)

            analysis_text = ""
            if aggregation:
                analysis_text = f"\n\n**综合分析：**\n{aggregation}"
            if model_insights:
                analysis_text += f"\n\n**各模型视角：**\n\n{model_insights}"

            return {
                "type": "workout_analyze",
                "status": "analyzed",
                "message": f"运动分析完成：{workout_line}{analysis_text}",
                "workout_data": workout,
            }
        except Exception as e:
            logger.error(f"运动分析 action 处理失败: {e}", exc_info=True)
            return {
                "type": "workout_analyze",
                "status": "error",
                "message": f"运动分析失败: {str(e)}",
            }

    def _handle_illness_create(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """通过 AI 对话新建病症发作记录"""
        name = action.get("name", "").strip()
        if not name:
            return None
        severity = max(1, min(10, int(action.get("severity", 5))))
        notes = action.get("notes", "")
        start_date_str = action.get("start_date")
        try:
            from datetime import datetime as _dt
            start_date = _dt.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else today
        except Exception:
            start_date = today

        episode = IllnessEpisode(
            user_id=user_id,
            name=name,
            start_date=start_date,
            severity=severity,
            status="active",
            notes=notes or "通过智能助理对话记录",
        )
        self.db.add(episode)
        self.db.commit()
        logger.info(f"用户{user_id} 病症发作: {name}, 严重度{severity}")
        return {
            "type": "illness_create", "status": "saved",
            "message": f"🤒 {name}(严重度{severity}/10) 已记录，希望你早日康复！"
        }

    def _handle_illness_update(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """通过 AI 对话更新病症状态"""
        episode_id = action.get("episode_id")
        name = action.get("name", "").strip()

        episode = None
        if episode_id:
            episode = self.db.query(IllnessEpisode).filter(
                IllnessEpisode.id == episode_id,
                IllnessEpisode.user_id == user_id,
            ).first()
        if not episode and name:
            episode = self.db.query(IllnessEpisode).filter(
                IllnessEpisode.user_id == user_id,
                IllnessEpisode.name.ilike(f"%{name}%"),
                IllnessEpisode.status != "resolved",
            ).order_by(IllnessEpisode.start_date.desc()).first()

        if not episode:
            logger.warning(f"病症记录未找到: id={episode_id}, name={name}")
            return None

        new_status = action.get("status")
        new_severity = action.get("severity")
        notes = action.get("notes", "")

        if new_severity is not None:
            episode.severity = max(1, min(10, int(new_severity)))
        if new_status:
            episode.status = new_status
            if new_status == "resolved" and not episode.end_date:
                episode.end_date = today

        update = IllnessUpdate(
            episode_id=episode.id,
            user_id=user_id,
            update_date=today,
            severity=episode.severity,
            status=episode.status,
            notes=notes or f"通过智能助理对话更新",
        )
        self.db.add(update)
        self.db.commit()

        status_label = {"active": "发作中", "improving": "好转中", "resolved": "已痊愈"}
        label = status_label.get(episode.status, episode.status)
        msg = f"✅ {episode.name} 状态已更新：{label}，严重度{episode.severity}/10"
        if episode.status == "resolved":
            msg = f"🎉 {episode.name} 已痊愈！共持续{(today - episode.start_date).days + 1}天"
        logger.info(f"用户{user_id} 病症更新: {episode.name} → {episode.status}")
        return {"type": "illness_update", "status": "saved", "message": msg}

    def _handle_excretion_action(self, user_id: int, action: dict, today: date, now: datetime) -> Optional[Dict]:
        """通过 AI 对话记录排泄"""
        exc_type = action.get("excretion_type", "bowel")
        if exc_type not in ("bowel", "urine"):
            exc_type = "bowel"

        record = ExcretionRecord(
            user_id=user_id,
            record_date=today,
            record_time=now.time(),
            type=exc_type,
            stool_type=action.get("stool_type"),
            color=action.get("color"),
            amount=action.get("amount"),
            urine_color=action.get("urine_color"),
            urine_amount=action.get("urine_amount"),
            notes=action.get("notes"),
        )
        self.db.add(record)
        self.db.commit()

        label = "大便" if exc_type == "bowel" else "小便"
        logger.info(f"用户{user_id} AI记录排泄: {label}")
        return {"type": "excretion", "status": "saved", "message": f"已记录{label}"}

    def _handle_sleep_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """通过 AI 对话记录睡眠"""
        quality = action.get("sleep_quality", 3)
        bedtime_str = action.get("bedtime")
        wake_str = action.get("wake_time")

        if not bedtime_str or not wake_str:
            return None

        try:
            # 解析 HH:MM 格式的时间
            bh, bm = map(int, bedtime_str.split(":"))
            wh, wm = map(int, wake_str.split(":"))

            from datetime import timezone as tz
            # 入睡时间：如果是晚上（>=18点），算前一天
            bedtime_date = today - timedelta(days=1) if bh >= 18 else today
            bedtime = datetime(bedtime_date.year, bedtime_date.month, bedtime_date.day, bh, bm, tzinfo=tz.utc)
            wake_time = datetime(today.year, today.month, today.day, wh, wm, tzinfo=tz.utc)

            if wake_time <= bedtime:
                return None

            duration = int((wake_time - bedtime).total_seconds() // 60)

            record = SleepRecord(
                user_id=user_id,
                record_date=today,
                bedtime=bedtime,
                wake_time=wake_time,
                sleep_quality=max(1, min(5, int(quality))),
                total_duration_minutes=duration,
                wake_count=action.get("wake_count"),
            )
            self.db.add(record)
            self.db.commit()

            hours = duration // 60
            mins = duration % 60
            logger.info(f"用户{user_id} AI记录睡眠: {hours}h{mins}min")
            return {"type": "sleep", "status": "saved", "message": f"已记录睡眠{hours}小时{mins}分钟"}
        except Exception as e:
            logger.warning(f"解析睡眠时间失败: {e}")
            return None

    def _handle_activity_status_action(self, user_id: int, action: dict, now: datetime) -> Optional[Dict]:
        """通过 AI 对话记录当前活动状态"""
        # 结束当前活动
        if action.get("end"):
            active = self.db.query(ActivityStatus).filter(
                ActivityStatus.user_id == user_id,
                ActivityStatus.is_active == True,
            ).all()
            if not active:
                return {"type": "activity_status", "status": "no_active", "message": "当前没有进行中的活动"}
            from datetime import timezone as tz
            end_time = datetime.now(tz.utc)
            for a in active:
                a.is_active = False
                a.actual_end_time = end_time
            self.db.commit()
            names = "、".join(a.status_text for a in active)
            return {"type": "activity_status", "status": "ended", "message": f"已结束活动: {names}"}

        activity_name = action.get("activity_name", "").strip()
        if not activity_name:
            return None

        category = action.get("category", "other")
        valid_cats = {"studying", "working", "exercising", "resting", "entertainment", "other"}
        if category not in valid_cats:
            category = "other"

        estimated_minutes = action.get("estimated_duration_minutes")
        if estimated_minutes:
            estimated_minutes = max(1, min(720, int(estimated_minutes)))

        from datetime import timezone as tz
        now_utc = datetime.now(tz.utc)

        # 自动结束之前的活动
        prev_active = self.db.query(ActivityStatus).filter(
            ActivityStatus.user_id == user_id,
            ActivityStatus.is_active == True,
        ).all()
        for a in prev_active:
            a.is_active = False
            a.actual_end_time = now_utc

        estimated_end = None
        if estimated_minutes:
            estimated_end = now_utc + timedelta(minutes=estimated_minutes)

        record = ActivityStatus(
            user_id=user_id,
            status_text=activity_name,
            category=category,
            start_time=now_utc,
            estimated_duration_minutes=estimated_minutes,
            estimated_end_time=estimated_end,
            is_active=True,
            notes=action.get("notes"),
        )
        self.db.add(record)
        self.db.commit()

        dur_text = f"，预计{estimated_minutes}分钟" if estimated_minutes else ""
        logger.info(f"用户{user_id} AI记录活动状态: {activity_name}")

        # 计算提醒时间（活动预估时长后提醒休息）
        reminder_minutes = estimated_minutes if estimated_minutes else 0
        reminder_message = ""
        if reminder_minutes > 0:
            if category in ("studying", "working"):
                reminder_message = f"{activity_name}已经{reminder_minutes}分钟了，该休息一下，看看远方，活动活动身体吧！"
            elif category == "exercising":
                reminder_message = f"{activity_name}已经{reminder_minutes}分钟了，注意补充水分和适当休息！"
            else:
                reminder_message = f"{activity_name}已经{reminder_minutes}分钟了，该换换活动了！"

        return {
            "type": "activity_status", "status": "saved",
            "message": f"已开始{activity_name}{dur_text}",
            "activity_name": activity_name,
            "reminder_minutes": reminder_minutes,
            "reminder_message": reminder_message,
        }

    def _handle_vocabulary_action(self, user_id: int, action: dict) -> Optional[Dict]:
        """处理单词学习 - 保存到单词本"""
        word = action.get("word", "").strip().lower()
        if not word:
            return None

        existing = self.db.query(VocabularyWord).filter(
            VocabularyWord.user_id == user_id,
            VocabularyWord.word == word,
        ).first()

        if existing:
            existing.review_count = (existing.review_count or 0) + 1
            existing.last_reviewed_at = datetime.utcnow()
            for field in ("phonetic_us", "phonetic_uk", "meanings", "synonyms", "antonyms", "word_roots", "example_sentences"):
                if action.get(field):
                    setattr(existing, field, action[field])
            self.db.commit()
            logger.info(f"用户{user_id} 复习单词: {word} (第{existing.review_count}次)")
            return {
                "type": "vocabulary", "status": "updated",
                "message": f"单词 {word} 已更新，复习第{existing.review_count}次",
            }

        vocab = VocabularyWord(
            user_id=user_id,
            word=word,
            phonetic_us=action.get("phonetic_us"),
            phonetic_uk=action.get("phonetic_uk"),
            meanings=action.get("meanings"),
            example_sentences=action.get("example_sentences"),
            synonyms=action.get("synonyms"),
            antonyms=action.get("antonyms"),
            word_roots=action.get("word_roots"),
            notes=action.get("notes"),
            review_count=1,
            next_review_date=date.today() + timedelta(days=1),
        )
        self.db.add(vocab)
        self.db.commit()
        logger.info(f"用户{user_id} 学习新单词: {word}")
        return {
            "type": "vocabulary", "status": "saved",
            "message": f"单词 {word} 已加入单词本",
        }

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
