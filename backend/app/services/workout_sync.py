"""Garmin运动活动同步服务"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import json
import logging

from app.models.daily_health import WorkoutRecord

logger = logging.getLogger(__name__)

try:
    from garminconnect import Garmin
    GARMINCONNECT_AVAILABLE = True
except ImportError:
    GARMINCONNECT_AVAILABLE = False


# 运动类型映射（Garmin类型 -> 系统类型）
GARMIN_ACTIVITY_TYPE_MAP = {
    "running": "running",
    "trail_running": "running",
    "treadmill_running": "running",
    "indoor_running": "running",
    "cycling": "cycling",
    "road_biking": "cycling",
    "mountain_biking": "cycling",
    "indoor_cycling": "cycling",
    "virtual_ride": "cycling",
    "swimming": "swimming",
    "lap_swimming": "swimming",
    "open_water_swimming": "swimming",
    "pool_swimming": "swimming",
    "walking": "walking",
    "hiking": "hiking",
    "cardio": "cardio",
    "fitness_equipment": "cardio",
    "elliptical": "cardio",
    "stair_climbing": "cardio",
    "indoor_cardio": "cardio",
    "hiit": "hiit",
    "strength_training": "strength",
    "yoga": "yoga",
    "other": "other"
}


class WorkoutSyncService:
    """Garmin运动活动同步服务"""
    
    def __init__(self, email: str, password: str, is_cn: bool = False, user_id: int = None):
        if not GARMINCONNECT_AVAILABLE:
            raise ImportError("garminconnect库未安装")
        
        self.email = email
        self.password = password
        self.is_cn = is_cn
        self.user_id = user_id
        self.client: Optional[Garmin] = None
        self._authenticated = False
    
    def _log_prefix(self) -> str:
        return f"[用户 {self.user_id}] " if self.user_id else ""
    
    def _ensure_authenticated(self):
        """确保已认证"""
        if not self._authenticated or self.client is None:
            self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
            self.client.login()
            self._authenticated = True
            logger.info(f"{self._log_prefix()}Garmin Connect登录成功")
    
    def _map_activity_type(self, garmin_type: str) -> str:
        """将Garmin活动类型映射到系统类型"""
        garmin_type_lower = garmin_type.lower().replace(" ", "_") if garmin_type else "other"
        return GARMIN_ACTIVITY_TYPE_MAP.get(garmin_type_lower, "other")
    
    def _parse_activity(self, activity: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """解析Garmin活动数据"""
        # 基本信息
        activity_id = activity.get("activityId")
        activity_name = activity.get("activityName", "")
        activity_type = activity.get("activityType", {})
        type_key = activity_type.get("typeKey", "other") if isinstance(activity_type, dict) else "other"
        
        # 时间
        start_time_local = activity.get("startTimeLocal")
        start_time = None
        if start_time_local:
            try:
                start_time = datetime.fromisoformat(start_time_local.replace("Z", "+00:00"))
            except:
                pass
        
        duration_seconds = int(activity.get("duration", 0))
        moving_duration = int(activity.get("movingDuration", 0))
        
        # 距离
        distance = activity.get("distance", 0)  # 米
        
        # 配速/速度
        avg_speed = activity.get("averageSpeed")  # m/s
        max_speed = activity.get("maxSpeed")  # m/s
        
        avg_pace = None
        if avg_speed and avg_speed > 0:
            avg_pace = int(1000 / avg_speed)  # 秒/公里
        
        # 心率
        avg_hr = activity.get("averageHR")
        max_hr = activity.get("maxHR")
        
        # 卡路里
        calories = activity.get("calories", 0)
        
        # 步数和步频（跑步/步行）
        steps = activity.get("steps")
        avg_cadence = activity.get("averageRunningCadenceInStepsPerMinute")
        max_cadence = activity.get("maxRunningCadenceInStepsPerMinute")
        
        # 海拔
        elevation_gain = activity.get("elevationGain")
        elevation_loss = activity.get("elevationLoss")
        min_elevation = activity.get("minElevation")
        max_elevation = activity.get("maxElevation")
        
        # 训练效果
        aerobic_te = activity.get("aerobicTrainingEffect")
        anaerobic_te = activity.get("anaerobicTrainingEffect")
        vo2max = activity.get("vO2MaxValue")
        training_load = activity.get("trainingLoad") or activity.get("activityTrainingLoad")
        
        # 心率区间
        hr_zones = activity.get("hrTimeInZones", [])
        zone_seconds = [0, 0, 0, 0, 0]
        if hr_zones and isinstance(hr_zones, list):
            for i, zone in enumerate(hr_zones[:5]):
                if isinstance(zone, dict):
                    zone_seconds[i] = int(zone.get("secsInZone", 0))
                elif isinstance(zone, (int, float)):
                    zone_seconds[i] = int(zone)
        
        # 游泳特有
        pool_length = activity.get("poolLength")
        laps = activity.get("numberOfLaps") or activity.get("lapCount")
        strokes = activity.get("totalStrokes") or activity.get("strokes")
        avg_strokes = activity.get("avgStrokesPerLength")
        
        # 骑车功率
        avg_power = activity.get("avgPower")
        max_power = activity.get("maxPower")
        normalized_power = activity.get("normPower")
        
        workout_date = start_time.date() if start_time else date.today()
        
        return {
            "user_id": user_id,
            "workout_date": workout_date,
            "start_time": start_time,
            "end_time": start_time + timedelta(seconds=duration_seconds) if start_time else None,
            "workout_type": self._map_activity_type(type_key),
            "workout_name": activity_name,
            "duration_seconds": duration_seconds,
            "moving_duration_seconds": moving_duration,
            "distance_meters": distance,
            "avg_pace_seconds_per_km": avg_pace,
            "avg_speed_kmh": round(avg_speed * 3.6, 2) if avg_speed else None,
            "max_speed_kmh": round(max_speed * 3.6, 2) if max_speed else None,
            "avg_heart_rate": int(avg_hr) if avg_hr else None,
            "max_heart_rate": int(max_hr) if max_hr else None,
            "hr_zone_1_seconds": zone_seconds[0],
            "hr_zone_2_seconds": zone_seconds[1],
            "hr_zone_3_seconds": zone_seconds[2],
            "hr_zone_4_seconds": zone_seconds[3],
            "hr_zone_5_seconds": zone_seconds[4],
            "calories": int(calories) if calories else None,
            "steps": int(steps) if steps else None,
            "avg_cadence": int(avg_cadence) if avg_cadence else None,
            "max_cadence": int(max_cadence) if max_cadence else None,
            "elevation_gain_meters": elevation_gain,
            "elevation_loss_meters": elevation_loss,
            "min_elevation_meters": min_elevation,
            "max_elevation_meters": max_elevation,
            "training_effect_aerobic": aerobic_te,
            "training_effect_anaerobic": anaerobic_te,
            "vo2max": vo2max,
            "training_load": int(training_load) if training_load else None,
            "pool_length_meters": pool_length,
            "laps": laps,
            "strokes": strokes,
            "avg_strokes_per_length": avg_strokes,
            "avg_power_watts": avg_power,
            "max_power_watts": max_power,
            "normalized_power_watts": normalized_power,
            "source": "garmin",
            "external_id": str(activity_id)
        }
    
    async def get_activity_details(self, activity_id: int) -> Optional[Dict[str, Any]]:
        """获取活动详细数据（包括心率时间序列）"""
        try:
            self._ensure_authenticated()
            
            # 获取活动详情
            details = self.client.get_activity(activity_id)
            
            # 获取心率数据
            hr_data = None
            try:
                hr_data = self.client.get_activity_hr_in_timezones(activity_id)
            except:
                pass
            
            return {
                "details": details,
                "heart_rate_data": hr_data
            }
        except Exception as e:
            logger.error(f"{self._log_prefix()}获取活动详情失败: {e}")
            return None
    
    async def sync_activities(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """同步Garmin活动到数据库"""
        self._ensure_authenticated()
        
        start_date = (date.today() - timedelta(days=days)).isoformat()
        end_date = date.today().isoformat()
        
        logger.info(f"{self._log_prefix()}开始同步活动 {start_date} 到 {end_date}")
        
        try:
            # 获取活动列表
            activities = self.client.get_activities_by_date(start_date, end_date)
            
            if not activities:
                logger.info(f"{self._log_prefix()}没有找到活动")
                return {"synced_count": 0}
            
            synced_count = 0
            
            for activity in activities:
                try:
                    activity_id = str(activity.get("activityId"))
                    
                    # 检查是否已存在
                    existing = db.query(WorkoutRecord).filter(
                        WorkoutRecord.user_id == user_id,
                        WorkoutRecord.external_id == activity_id
                    ).first()
                    
                    if existing:
                        logger.debug(f"{self._log_prefix()}活动 {activity_id} 已存在，跳过")
                        continue
                    
                    # 解析活动数据
                    parsed = self._parse_activity(activity, user_id)
                    
                    # 尝试获取详细数据（心率曲线等）
                    try:
                        details_data = await self.get_activity_details(int(activity_id))
                        if details_data and details_data.get("heart_rate_data"):
                            hr_points = []
                            hr_data = details_data["heart_rate_data"]
                            if isinstance(hr_data, list):
                                for i, point in enumerate(hr_data):
                                    if isinstance(point, dict):
                                        hr_points.append({
                                            "time": i * 10,  # 假设10秒间隔
                                            "hr": point.get("heartRate", 0)
                                        })
                            if hr_points:
                                parsed["heart_rate_data"] = json.dumps(hr_points)
                    except Exception as e:
                        logger.debug(f"获取活动详情失败: {e}")
                    
                    # 创建记录
                    db_record = WorkoutRecord(**parsed)
                    db.add(db_record)
                    synced_count += 1
                    
                    logger.info(f"{self._log_prefix()}同步活动: {parsed['workout_name']} ({parsed['workout_type']})")
                    
                except Exception as e:
                    logger.error(f"{self._log_prefix()}解析活动失败: {e}")
                    continue
            
            db.commit()
            logger.info(f"{self._log_prefix()}同步完成，共 {synced_count} 条活动")
            
            return {"synced_count": synced_count}
            
        except Exception as e:
            logger.error(f"{self._log_prefix()}同步活动失败: {e}")
            raise

