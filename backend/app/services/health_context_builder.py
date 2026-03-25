"""
健康上下文构建器 - 从 chat_service.py 提取

负责构建用户健康数据上下文，注入为 AI 对话的 system prompt。
包含天气缓存、健康数据聚合、交叉分析、趋势分析等功能。
"""
import json
import logging
import re
import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.basic_health import BasicHealthData
from app.models.daily_health import (
    GarminData, DietRecord, ExerciseRecord, WorkoutRecord,
    WaterIntake, WorkoutAnalysisResult,
)
from app.models.checkin import CheckinRecord, CheckinTemplate
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.trip import Trip, TripItem
from app.models.illness import IllnessEpisode
from app.models.health_checkin import HealthCheckin
from app.models.supplement import SupplementDefinition
from app.models.disease_tracking import UserDiseaseProfile
from app.models.excretion import ExcretionRecord
from app.models.sleep_record import SleepRecord
from app.models.anomaly_alert import AnomalyAlert
from app.models.activity_status import ActivityStatus
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.services.environment.weather_service import weather_service

logger = logging.getLogger(__name__)

# 天气数据模块级缓存（每个 worker 进程独立，8小时 TTL）
_weather_cache: dict = {}  # key: city -> (timestamp, data)
_WEATHER_CACHE_TTL = 8 * 3600  # 8 小时


class HealthContextBuilder:
    """健康上下文构建器"""

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

    async def build_health_context(self, user_id: int, user_question: str = "") -> str:
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
            if garmin.hrv:
                hrv_info = f"HRV:{garmin.hrv}ms"
                if garmin.hrv_status:
                    hrv_info += f"({garmin.hrv_status})"
                if garmin.hrv_7day_avg:
                    hrv_info += f",7日均值:{garmin.hrv_7day_avg}ms"
                g_parts.append(hrv_info)
            if garmin.spo2_avg:
                spo2_info = f"血氧SpO2:均值{garmin.spo2_avg}%"
                if garmin.spo2_min:
                    spo2_info += f",最低{garmin.spo2_min}%"
                if garmin.spo2_max:
                    spo2_info += f",最高{garmin.spo2_max}%"
                g_parts.append(spo2_info)
            parts.append(", ".join(g_parts))

        # 健康目标与进度（在 garmin/weight 之后计算，可显示进度）
        if profile:
            goals = []
            if profile.target_weight_kg:
                g = f"目标体重{profile.target_weight_kg}kg"
                if weight:
                    diff = weight.weight - profile.target_weight_kg
                    g += f"(当前{weight.weight}kg, {'超出' if diff > 0 else '还差'}{abs(diff):.1f}kg)"
                goals.append(g)
            if profile.target_steps:
                g = f"目标步数{profile.target_steps}"
                if garmin and garmin.steps:
                    pct = round(garmin.steps / profile.target_steps * 100)
                    g += f"(今日{garmin.steps}步, {pct}%)"
                goals.append(g)
            if profile.target_sleep_hours:
                g = f"目标睡眠{profile.target_sleep_hours}h"
                if garmin and garmin.total_sleep_duration:
                    actual_h = garmin.total_sleep_duration / 60
                    g += f"(昨晚{actual_h:.1f}h)"
                goals.append(g)
            if goals:
                parts.append(f"健康目标与进度: {', '.join(goals)}")

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

        # HRV 7天趋势（复用已查询的 sleep_7days）
        hrv_7days = [r for r in (sleep_7days or []) if r.hrv is not None]
        if hrv_7days:
            hrv_vals = [r.hrv for r in hrv_7days]
            low_days = sum(1 for r in hrv_7days if r.hrv_status == "low")
            hrv_avg = sum(hrv_vals) / len(hrv_vals)
            hrv_trend_parts = [f"最近7天HRV趋势({len(hrv_7days)}天)"]
            for r in hrv_7days[:5]:
                status_tag = f"({r.hrv_status})" if r.hrv_status else ""
                hrv_trend_parts.append(f"  {r.record_date}: {r.hrv}ms{status_tag}")
            hrv_trend_parts.append(f"  均值:{hrv_avg:.1f}ms, 最高:{max(hrv_vals)}ms, 最低:{min(hrv_vals)}ms")
            if low_days:
                hrv_trend_parts.append(f"  ⚠️ 有{low_days}天HRV状态为low")
            parts.append("\n".join(hrv_trend_parts))

        # SpO2 7天趋势
        spo2_7days = [r for r in (sleep_7days or []) if r.spo2_avg is not None]
        if spo2_7days:
            spo2_avgs = [r.spo2_avg for r in spo2_7days]
            spo2_mins = [r.spo2_min for r in spo2_7days if r.spo2_min is not None]
            below_95 = sum(1 for v in spo2_mins if v < 95) if spo2_mins else 0
            spo2_trend_parts = [f"最近7天SpO2趋势({len(spo2_7days)}天)"]
            for r in spo2_7days[:5]:
                min_tag = f"(最低{r.spo2_min}%)" if r.spo2_min else ""
                spo2_trend_parts.append(f"  {r.record_date}: 均值{r.spo2_avg}%{min_tag}")
            spo2_trend_parts.append(f"  总均值:{sum(spo2_avgs)/len(spo2_avgs):.1f}%")
            if spo2_mins:
                spo2_trend_parts.append(f"  期间最低:{min(spo2_mins)}%")
            if below_95:
                spo2_trend_parts.append(f"  ⚠️ 有{below_95}天最低SpO2低于95%")
            parts.append("\n".join(spo2_trend_parts))

        # 运动数据分析（复用上面查询的 GarminData）
        # 最近7天运动数据
        exercise_7days = sleep_7days  # 同一份 7 天 GarminData

        if exercise_7days:
            steps_list = [r.steps for r in exercise_7days if r.steps is not None]
            calories_list = [r.calories_burned for r in exercise_7days if r.calories_burned is not None]
            # 活动时长：优先用 workout_records 的实际运动时间（而非 Garmin 强度分钟数）
            _workout_7d = self.db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= date.today() - timedelta(days=7),
            ).all()
            _workout_dur_7d = {}
            for w in _workout_7d:
                if w.duration_seconds:
                    _workout_dur_7d[w.workout_date] = _workout_dur_7d.get(w.workout_date, 0) + w.duration_seconds // 60
            active_mins = []
            for r in exercise_7days:
                garmin_active = (r.vigorous_intensity_minutes or 0) + (r.moderate_intensity_minutes or 0)
                workout_active = _workout_dur_7d.get(r.record_date, 0)
                active_mins.append(max(garmin_active, workout_active))

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

        # 习惯洞察（基于30天打卡数据）
        if checkins_30days:
            habit_insights = self._analyze_checkin_patterns(checkins_30days)
            if habit_insights:
                parts.append(habit_insights)

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

        # 健康趋势
        trend_context = self._get_trend_context(user_id)
        if trend_context:
            parts.append(trend_context)

        # 健康评分
        score_context = self._get_health_score_context(user_id)
        if score_context:
            parts.append(score_context)

        # 异常预警
        alerts_context = self._get_anomaly_alerts_context(user_id)
        if alerts_context:
            parts.append(alerts_context)

        # 对话记忆
        try:
            from app.services.conversation_memory_service import get_relevant_memories
            memory_context = get_relevant_memories(self.db, user_id, limit=5)
            if memory_context:
                parts.append(memory_context)
        except Exception as e:
            logger.warning(f"获取对话记忆失败: {e}")

        # 交叉分析
        water_ml = sum(w.amount_ml or 0 for w in water_today) if water_today else 0
        cross_context = self._build_cross_analysis_context(
            garmin, sleep_7days, _diet_7d_all, water_ml, weight, profile
        )
        if cross_context:
            parts.append(cross_context)

        if not parts:
            return ""

        # 动态裁剪：根据用户问题聚焦相关板块
        if user_question:
            parts = self._trim_context_by_relevance(parts, user_question)

        return "以下是该用户的最新健康数据：\n" + "\n".join(parts)

    SECTION_KEYWORDS = {
        "sleep": ["睡眠", "sleep", "失眠", "入睡", "深睡", "做梦", "早起", "熬夜", "睡觉", "REM", "浅睡"],
        "exercise": ["运动", "跑步", "健身", "步数", "训练", "锻炼", "游泳", "骑", "活动", "走路", "散步"],
        "diet": ["饮食", "吃", "热量", "卡路里", "营养", "蛋白", "减脂", "早餐", "午餐", "晚餐", "碳水", "脂肪"],
        "heart": ["心率", "HRV", "心脏", "血压", "血氧", "SpO2", "心跳"],
        "water": ["喝水", "饮水", "水", "补水"],
        "stress": ["压力", "焦虑", "放松", "恢复", "电量", "body battery"],
        "weight": ["体重", "减肥", "增重", "BMI", "体脂"],
        "checkin": ["打卡", "习惯", "坚持", "连续"],
        "supplement": ["补剂", "维生素", "营养素"],
    }

    def _trim_context_by_relevance(self, parts: list, user_question: str) -> list:
        """根据用户问题裁剪上下文，保留相关板块全文，其他截断为首行摘要"""
        q = user_question.lower()

        # 找出匹配的分类
        matched_categories = set()
        for cat, keywords in self.SECTION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in q:
                    matched_categories.add(cat)
                    break

        # 无匹配：不裁剪（通用问题如"我的健康状况"）
        if not matched_categories:
            return parts

        # 分类→板块关键词映射
        category_markers = {
            "sleep": ["睡眠", "sleep", "深睡", "REM", "浅睡"],
            "exercise": ["运动", "步数", "活动", "锻炼", "Garmin"],
            "diet": ["饮食", "营养", "卡路里", "热量"],
            "heart": ["心率", "HRV", "血压", "血氧", "SpO2"],
            "water": ["饮水"],
            "stress": ["压力", "电量", "body battery", "恢复就绪"],
            "weight": ["体重"],
            "checkin": ["打卡"],
            "supplement": ["补剂"],
        }

        trimmed = []
        for part in parts:
            # 判断该板块是否属于匹配分类
            is_relevant = False
            for cat in matched_categories:
                markers = category_markers.get(cat, [])
                for marker in markers:
                    if marker.lower() in part.lower():
                        is_relevant = True
                        break
                if is_relevant:
                    break

            if is_relevant:
                trimmed.append(part)  # 保留全文
            else:
                # 截断为首行摘要
                first_line = part.split('\n')[0]
                if len(first_line) > 80:
                    first_line = first_line[:80] + "..."
                trimmed.append(first_line)

        return trimmed

    def _get_trend_context(self, user_id: int) -> str:
        """获取用户最新趋势数据，注入到聊天上下文"""
        from app.models.health_trend import HealthTrendReport
        reports = self.db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == user_id,
            HealthTrendReport.period == "7d",
        ).order_by(HealthTrendReport.report_date.desc()).limit(4).all()

        if not reports:
            return ""

        dim_labels = {"weight": "体重", "sleep": "睡眠", "exercise": "运动", "overall": "综合"}
        lines = [f"\n## 健康趋势（{reports[0].report_date}）"]
        for r in reports:
            label = dim_labels.get(r.dimension, r.dimension)
            direction_cn = {"improving": "改善中", "declining": "下降中", "stable": "平稳"}.get(r.trend_direction, "未知")
            lines.append(f"- {label}: {direction_cn}")
            if r.insights:
                for insight in r.insights[:2]:
                    lines.append(f"  - {insight}")
        return "\n".join(lines)

    def _get_health_score_context(self, user_id: int) -> str:
        """获取健康评分上下文"""
        try:
            from app.services.health_score_service import health_score_service
            result = health_score_service.calculate_daily_score(self.db, user_id)
            if result.get("status") != "ok":
                return ""
            score = result["total_score"]
            grade = result["grade"]
            dims = result.get("dimensions", [])
            dim_strs = [f"{d['name']}{d['score']}" for d in dims if d.get("score")]
            suggestions = result.get("suggestions", [])
            line = f"今日健康评分: {score}分({grade})"
            if dim_strs:
                line += f" — {'/'.join(dim_strs)}"
            if suggestions:
                line += f" | 建议: {suggestions[0]}"
            return line
        except Exception as e:
            logger.warning(f"获取健康评分失败: {e}")
            return ""

    def _get_anomaly_alerts_context(self, user_id: int) -> str:
        """获取未确认的异常预警上下文"""
        try:
            seven_days_ago = date.today() - timedelta(days=7)
            alerts = self.db.query(AnomalyAlert).filter(
                AnomalyAlert.user_id == user_id,
                AnomalyAlert.acknowledged == False,
                AnomalyAlert.detection_date >= seven_days_ago
            ).order_by(AnomalyAlert.detection_date.desc()).limit(5).all()
            if not alerts:
                return ""
            severity_order = {"critical": 0, "warning": 1, "info": 2}
            alerts.sort(key=lambda a: severity_order.get(a.severity, 9))
            items = []
            for a in alerts:
                items.append(f"[{a.severity}] {a.detection_date.strftime('%m/%d')} {a.message}")
            return f"近期健康预警({len(alerts)}条): " + " | ".join(items)
        except Exception as e:
            logger.warning(f"获取异常预警失败: {e}")
            return ""

    def _build_cross_analysis_context(self, garmin, sleep_7days, diet_7d, water_today_ml, weight, profile) -> str:
        """构建跨数据交叉分析上下文"""
        parts = []

        # 睡眠↔运动关联
        if sleep_7days and len(sleep_7days) >= 3:
            active_deep = []
            rest_deep = []
            for r in sleep_7days:
                if r.deep_sleep_duration is not None:
                    is_active = (r.steps and r.steps > 8000) or (r.active_minutes and r.active_minutes > 30)
                    if is_active:
                        active_deep.append(r.deep_sleep_duration)
                    else:
                        rest_deep.append(r.deep_sleep_duration)
            if active_deep and rest_deep:
                avg_active = sum(active_deep) / len(active_deep)
                avg_rest = sum(rest_deep) / len(rest_deep)
                diff = avg_active - avg_rest
                if abs(diff) > 5 and avg_rest > 0:
                    pct = round(diff / avg_rest * 100)
                    if diff > 0:
                        parts.append(f"运动与睡眠: 活跃日平均深睡{avg_active:.0f}min, 比静息日多{diff:.0f}min(+{pct}%)")
                    else:
                        parts.append(f"运动与睡眠: 活跃日平均深睡{avg_active:.0f}min, 比静息日少{abs(diff):.0f}min({pct}%)")

        # 恢复就绪度
        if garmin:
            recovery_parts = []
            recovery_score = 0
            has_data = False

            if garmin.hrv and garmin.hrv_7day_avg and garmin.hrv_7day_avg > 0:
                hrv_ratio = garmin.hrv / garmin.hrv_7day_avg
                recovery_score += hrv_ratio * 40
                recovery_parts.append(f"HRV{'正常' if 0.85 <= hrv_ratio <= 1.15 else '偏低' if hrv_ratio < 0.85 else '偏高'}")
                has_data = True

            if garmin.body_battery_most_charged:
                battery = garmin.body_battery_most_charged
                recovery_score += battery * 0.3
                recovery_parts.append(f"电量{'充足' if battery >= 60 else '中等' if battery >= 30 else '不足'}")
                has_data = True

            if garmin.stress_level:
                stress = garmin.stress_level
                recovery_score += (100 - stress) * 0.3
                recovery_parts.append(f"压力{'低' if stress < 40 else '中等' if stress < 60 else '偏高'}")
                has_data = True

            if has_data:
                grade = "优秀" if recovery_score >= 80 else "良好" if recovery_score >= 60 else "一般" if recovery_score >= 40 else "较差"
                suggestion = "适合高强度训练" if recovery_score >= 70 else "建议中等强度运动" if recovery_score >= 50 else "建议轻度活动或休息"
                parts.append(f"恢复就绪度: {recovery_score:.0f}%({grade}) — {', '.join(recovery_parts)} → {suggestion}")

        # 能量平衡
        if diet_7d and weight and profile:
            days_with_calories = {}
            for r in diet_7d:
                if r.calories:
                    d = r.record_date
                    days_with_calories[d] = days_with_calories.get(d, 0) + r.calories
            if len(days_with_calories) >= 3:
                avg_intake = sum(days_with_calories.values()) / len(days_with_calories)
                if profile.height_cm and weight:
                    w = weight.weight
                    h = profile.height_cm
                    age = None
                    if profile.birth_date:
                        age = (date.today() - profile.birth_date).days // 365
                    if age:
                        if profile.gender == 'male':
                            bmr = 10 * w + 6.25 * h - 5 * age + 5
                        else:
                            bmr = 10 * w + 6.25 * h - 5 * age - 161
                        tdee = bmr * 1.4
                        gap = avg_intake - tdee
                        parts.append(f"能量平衡: {len(days_with_calories)}日均摄入{avg_intake:.0f}kcal, 估算消耗{tdee:.0f}kcal → 日均{'盈余' if gap > 0 else '缺口'}{abs(gap):.0f}kcal")

        # 饮水充足度
        if water_today_ml and water_today_ml > 0:
            target = 2000
            if garmin and garmin.active_minutes and garmin.active_minutes > 30:
                target = 2500
                parts.append(f"饮水: 今日{water_today_ml}ml, 活跃日建议{target}ml, {'已达标' if water_today_ml >= target else f'还需{target - water_today_ml}ml'}")
            elif water_today_ml < target:
                parts.append(f"饮水提醒: 今日{water_today_ml}ml, 建议{target}ml, 还需{target - water_today_ml}ml")

        if not parts:
            return ""
        return "\n## 交叉分析\n" + "\n".join(parts)

    def _analyze_checkin_patterns(self, checkins_30d) -> str:
        """分析30天打卡习惯模式"""
        from collections import defaultdict
        if not checkins_30d:
            return ""

        insights = []

        # 计算当前连续打卡天数 (streak)
        dates = sorted(set(r.checkin_date for r, _ in checkins_30d), reverse=True)
        if dates:
            streak = 1
            for i in range(1, len(dates)):
                if (dates[i - 1] - dates[i]).days == 1:
                    streak += 1
                else:
                    break
            if streak >= 3:
                insights.append(f"当前连续打卡{streak}天")

        # 星期模式
        weekday_counts = defaultdict(int)
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for r, _ in checkins_30d:
            weekday_counts[r.checkin_date.weekday()] += 1
        if weekday_counts:
            most_active = max(weekday_counts, key=weekday_counts.get)
            least_active = min(weekday_counts, key=weekday_counts.get)
            if weekday_counts[most_active] > weekday_counts[least_active] + 2:
                insights.append(f"{weekday_names[most_active]}最活跃, {weekday_names[least_active]}最易中断")

        # 数值趋势（按模板分组，比较前后两周）
        template_values = defaultdict(list)
        for r, t in checkins_30d:
            if r.value:
                template_values[t.name].append((r.checkin_date, r.value))
        for name, values in template_values.items():
            if len(values) < 6:
                continue
            values.sort(key=lambda x: x[0])
            mid = len(values) // 2
            first_half_avg = sum(v for _, v in values[:mid]) / mid
            second_half_avg = sum(v for _, v in values[mid:]) / (len(values) - mid)
            if first_half_avg > 0:
                change_pct = (second_half_avg - first_half_avg) / first_half_avg * 100
                if abs(change_pct) > 10:
                    direction = "递增" if change_pct > 0 else "递减"
                    insights.append(f"{name}近期{direction}({change_pct:+.0f}%)")

        if not insights:
            return ""
        return "习惯洞察: " + ", ".join(insights)

    def build_activity_context(self, user_id: int) -> str:
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

    async def build_system_prompt(self, user_id: int, is_kids_mode: bool = False, user_question: str = "") -> str:
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
                "- 回答关于计划进度的问题\n\n"
                "## HRV与血氧主动提醒规则\n"
                "- 当用户数据显示HRV状态为'low'时，在回答开头主动提醒用户注意休息和恢复\n"
                "- 当用户数据显示SpO2最低值低于95%时，在回答开头提醒用户关注血氧，必要时就医\n"
                "- HRV（心率变异性）越高通常代表身体恢复状态越好，持续低HRV可能提示过度训练或压力过大\n"
                "- 正常SpO2范围为95-100%，低于95%需要关注，低于90%建议立即就医\n"
                "\n## 交叉分析与运动处方规则\n"
                "- 恢复就绪度<50%时，主动建议降低运动强度或休息\n"
                "- 恢复充分(≥70%)时，可推荐高强度训练\n"
                "- 饮食热量持续盈余+体重上升时，主动提醒调整饮食\n"
                "- 当用户数据中包含异常预警时，在回答中优先关注预警指标\n"
                "- 健康评分低于60分时，主动提醒用户关注薄弱维度\n"
            )

        # 活动记录能力
        activity_ctx = self.build_activity_context(user_id)
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

        health_ctx = await self.build_health_context(user_id, user_question=user_question)
        prompt = base + activity_prompt + create_plan_prompt + workout_analyze_prompt
        if health_ctx:
            prompt += f"\n\n{health_ctx}"
        return prompt

