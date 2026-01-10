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
        """获取活动详细数据（包括心率时间序列和GPS路线）"""
        try:
            self._ensure_authenticated()
            
            # 获取活动详情
            details = self.client.get_activity(activity_id)
            
            # 尝试多种方式获取心率数据
            hr_data = None
            
            # 方法1: 尝试获取活动分割数据（包含心率）
            try:
                splits = self.client.get_activity_splits(activity_id)
                if splits and isinstance(splits, dict):
                    hr_data = splits
                    logger.debug(f"从splits获取心率数据")
            except Exception as e:
                logger.debug(f"get_activity_splits 失败: {e}")
            
            # 方法2: 尝试获取活动详细信息中的心率数据
            if not hr_data:
                try:
                    # 活动详情中可能包含 heartRateSamples
                    activity_details = self.client.get_activity_details(activity_id)
                    if activity_details:
                        hr_data = activity_details
                        logger.debug(f"从activity_details获取心率数据，键: {list(activity_details.keys()) if isinstance(activity_details, dict) else 'N/A'}")
                except Exception as e:
                    logger.debug(f"get_activity_details 失败: {e}")
            
            # 方法3: 尝试获取活动心率数据
            if not hr_data:
                try:
                    hr_timezones = self.client.get_activity_hr_in_timezones(activity_id)
                    if hr_timezones:
                        hr_data = {"hr_zones": hr_timezones}
                        logger.debug(f"从hr_in_timezones获取心率数据")
                except Exception as e:
                    logger.debug(f"get_activity_hr_in_timezones 失败: {e}")
            
            # 尝试获取GPS路线数据
            gps_data = None
            try:
                # 方法1: 尝试从活动详情中获取GPS数据
                if details and isinstance(details, dict):
                    # 检查是否有GPS相关字段
                    gps_data = details.get('gpsData') or details.get('geoPolylineDTO') or details.get('geoPolyline')
                    if gps_data:
                        logger.debug(f"从activity获取GPS数据")
                
                # 方法2: 尝试获取活动GPS数据
                if not gps_data:
                    try:
                        gps_data = self.client.get_activity_gps(activity_id)
                        if gps_data:
                            logger.debug(f"从get_activity_gps获取GPS数据")
                    except Exception as e:
                        logger.debug(f"get_activity_gps 失败: {e}")
                
                # 方法3: 尝试从活动详情API获取
                if not gps_data and activity_details:
                    gps_data = activity_details.get('gpsData') or activity_details.get('geoPolylineDTO') or activity_details.get('geoPolyline')
                    if gps_data:
                        logger.debug(f"从activity_details获取GPS数据")
                
            except Exception as e:
                logger.debug(f"获取GPS数据失败: {e}")
            
            return {
                "details": details,
                "heart_rate_data": hr_data,
                "gps_data": gps_data
            }
        except Exception as e:
            logger.error(f"{self._log_prefix()}获取活动详情失败: {e}")
            return None
    
    def _parse_heart_rate_samples(self, hr_data: Dict[str, Any], duration_seconds: int) -> List[Dict[str, int]]:
        """解析心率采样数据"""
        hr_points = []
        
        if not hr_data or not isinstance(hr_data, dict):
            return hr_points
        
        # 尝试从不同的数据结构中提取心率时间序列
        
        # 格式1: activityDetailMetrics 中的 metricsMap
        metrics_map = hr_data.get('activityDetailMetrics', [])
        if metrics_map:
            for metric in metrics_map:
                if isinstance(metric, dict) and 'metrics' in metric:
                    metrics = metric.get('metrics', {})
                    hr_value = metrics.get('directHeartRate') or metrics.get('heartRate')
                    if hr_value:
                        time_offset = metric.get('startTimeGMT', 0)
                        hr_points.append({"time": int(time_offset), "hr": int(hr_value)})
        
        # 格式2: heartRateSamples 数组
        hr_samples = hr_data.get('heartRateSamples', [])
        if hr_samples and isinstance(hr_samples, list):
            for sample in hr_samples:
                if isinstance(sample, dict):
                    hr_value = sample.get('heartRate') or sample.get('value')
                    time_ms = sample.get('timestamp') or sample.get('startTimeInSeconds', 0) * 1000
                    if hr_value:
                        hr_points.append({"time": int(time_ms / 1000), "hr": int(hr_value)})
                elif isinstance(sample, (list, tuple)) and len(sample) >= 2:
                    # [timestamp, heartRate] 格式
                    hr_points.append({"time": int(sample[0] / 1000), "hr": int(sample[1])})
        
        # 格式3: gpsData 或 chartData 中包含心率
        chart_data = hr_data.get('chartData', {}) or hr_data.get('gpsData', {})
        if chart_data and isinstance(chart_data, dict):
            hr_chart = chart_data.get('heartRate', [])
            if hr_chart and isinstance(hr_chart, list):
                interval = duration_seconds // len(hr_chart) if len(hr_chart) > 0 else 10
                for i, hr in enumerate(hr_chart):
                    if isinstance(hr, (int, float)) and hr > 0:
                        hr_points.append({"time": i * interval, "hr": int(hr)})
        
        # 格式4: metricDescriptors + activityDetailMetrics
        metric_descriptors = hr_data.get('metricDescriptors', [])
        detail_metrics = hr_data.get('activityDetailMetrics', [])
        
        if metric_descriptors and detail_metrics:
            # 找到心率在 metrics 中的索引
            hr_index = None
            for i, desc in enumerate(metric_descriptors):
                if isinstance(desc, dict):
                    key = desc.get('key', '')
                    if 'heart' in key.lower() or 'hr' in key.lower():
                        hr_index = i
                        break
            
            if hr_index is not None:
                for detail in detail_metrics:
                    if isinstance(detail, dict):
                        metrics = detail.get('metrics', [])
                        if isinstance(metrics, list) and len(metrics) > hr_index:
                            hr_value = metrics[hr_index]
                            if hr_value and hr_value > 0:
                                start_time = detail.get('startTimeInSeconds', 0)
                                hr_points.append({"time": int(start_time), "hr": int(hr_value)})
        
        # 排序并去重
        if hr_points:
            hr_points.sort(key=lambda x: x['time'])
            # 每 10 秒采样一个点
            sampled = []
            last_time = -10
            for p in hr_points:
                if p['time'] - last_time >= 10:
                    sampled.append(p)
                    last_time = p['time']
            hr_points = sampled
        
        return hr_points
    
    def _generate_simulated_hr_curve(
        self, 
        avg_hr: int, 
        max_hr: Optional[int], 
        duration_seconds: int
    ) -> List[Dict[str, int]]:
        """
        根据平均心率和最大心率生成模拟心率曲线
        模拟热身 -> 运动 -> 冷却的曲线
        """
        import random
        
        if not avg_hr or duration_seconds <= 0:
            return []
        
        max_hr = max_hr or int(avg_hr * 1.15)
        min_hr = max(int(avg_hr * 0.7), 60)  # 热身心率
        
        hr_points = []
        interval = 30  # 每30秒一个点
        num_points = duration_seconds // interval
        
        if num_points < 3:
            return []
        
        # 热身阶段（前 10%）
        warmup_points = max(1, int(num_points * 0.1))
        # 运动阶段（中间 80%）
        main_points = int(num_points * 0.8)
        # 冷却阶段（后 10%）
        cooldown_points = num_points - warmup_points - main_points
        
        current_time = 0
        
        # 热身：从 min_hr 逐渐上升到 avg_hr
        for i in range(warmup_points):
            progress = (i + 1) / warmup_points
            hr = int(min_hr + (avg_hr - min_hr) * progress)
            hr += random.randint(-3, 3)  # 添加一点随机波动
            hr_points.append({"time": current_time, "hr": max(min_hr, min(max_hr, hr))})
            current_time += interval
        
        # 主运动阶段：在 avg_hr 和 max_hr 之间波动
        for i in range(main_points):
            # 使用正弦波模拟心率波动
            import math
            wave = math.sin(i / 10) * 0.3 + 0.7  # 0.4 到 1.0 之间
            hr = int(avg_hr + (max_hr - avg_hr) * wave * 0.5)
            hr += random.randint(-5, 5)  # 添加随机波动
            hr_points.append({"time": current_time, "hr": max(min_hr, min(max_hr, hr))})
            current_time += interval
        
        # 冷却阶段：从当前心率逐渐下降到 min_hr
        last_hr = hr_points[-1]["hr"] if hr_points else avg_hr
        for i in range(cooldown_points):
            progress = (i + 1) / max(1, cooldown_points)
            hr = int(last_hr - (last_hr - min_hr) * progress)
            hr += random.randint(-3, 3)
            hr_points.append({"time": current_time, "hr": max(min_hr, min(max_hr, hr))})
            current_time += interval
        
        return hr_points
    
    def _parse_gps_route(self, gps_data: Any, start_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """解析GPS路线数据"""
        route_points = []
        
        if not gps_data:
            return route_points
        
        try:
            # 格式1: geoPolylineDTO 或 geoPolyline (编码的polyline字符串)
            if isinstance(gps_data, str):
                # 尝试解码 polyline
                try:
                    import polyline
                    decoded = polyline.decode(gps_data)
                    for i, (lat, lng) in enumerate(decoded):
                        route_points.append({
                            "lat": lat,
                            "lng": lng,
                            "time": i * 10  # 假设每10秒一个点
                        })
                    logger.debug(f"解码polyline得到 {len(route_points)} 个GPS点")
                    return route_points
                except ImportError:
                    logger.warning("polyline库未安装，无法解码GPS路线")
                except Exception as e:
                    logger.debug(f"解码polyline失败: {e}")
            
            # 格式2: gpsData 数组，包含坐标点
            if isinstance(gps_data, list):
                for i, point in enumerate(gps_data):
                    if isinstance(point, dict):
                        lat = point.get('latitude') or point.get('lat')
                        lng = point.get('longitude') or point.get('lng') or point.get('lon')
                        elevation = point.get('elevation') or point.get('altitude')
                        time_offset = point.get('time') or point.get('timestamp') or point.get('startTimeInSeconds') or (i * 10)
                        
                        if lat and lng:
                            route_point = {
                                "lat": float(lat),
                                "lng": float(lng)
                            }
                            if elevation:
                                route_point["elevation"] = float(elevation)
                            if time_offset:
                                route_point["time"] = int(time_offset)
                            route_points.append(route_point)
                    elif isinstance(point, (list, tuple)) and len(point) >= 2:
                        # [lat, lng] 或 [lat, lng, elevation] 格式
                        route_points.append({
                            "lat": float(point[0]),
                            "lng": float(point[1]),
                            "elevation": float(point[2]) if len(point) > 2 else None,
                            "time": i * 10
                        })
            
            # 格式3: gpsData 字典，包含多个字段
            elif isinstance(gps_data, dict):
                # 检查是否有坐标数组
                coordinates = gps_data.get('coordinates') or gps_data.get('points') or gps_data.get('trackPoints')
                if coordinates and isinstance(coordinates, list):
                    for i, coord in enumerate(coordinates):
                        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                            route_points.append({
                                "lat": float(coord[0]),
                                "lng": float(coord[1]),
                                "elevation": float(coord[2]) if len(coord) > 2 else None,
                                "time": i * 10
                            })
                        elif isinstance(coord, dict):
                            lat = coord.get('latitude') or coord.get('lat')
                            lng = coord.get('longitude') or coord.get('lng') or coord.get('lon')
                            if lat and lng:
                                route_point = {
                                    "lat": float(lat),
                                    "lng": float(lng)
                                }
                                elevation = coord.get('elevation') or coord.get('altitude')
                                if elevation:
                                    route_point["elevation"] = float(elevation)
                                time_offset = coord.get('time') or coord.get('timestamp')
                                if time_offset:
                                    route_point["time"] = int(time_offset)
                                route_points.append(route_point)
                
                # 检查是否有编码的polyline
                polyline_str = gps_data.get('polyline') or gps_data.get('encodedPolyline')
                if polyline_str and isinstance(polyline_str, str):
                    try:
                        import polyline
                        decoded = polyline.decode(polyline_str)
                        for i, (lat, lng) in enumerate(decoded):
                            route_points.append({
                                "lat": lat,
                                "lng": lng,
                                "time": i * 10
                            })
                    except ImportError:
                        logger.warning("polyline库未安装，无法解码GPS路线")
                    except Exception as e:
                        logger.debug(f"解码polyline失败: {e}")
            
            # 去重和采样（每10秒一个点，或每100米一个点）
            if route_points:
                # 按时间排序
                route_points.sort(key=lambda x: x.get('time', 0))
                # 采样：每10秒一个点
                sampled = []
                last_time = -10
                for p in route_points:
                    current_time = p.get('time', 0)
                    if current_time - last_time >= 10:
                        sampled.append(p)
                        last_time = current_time
                route_points = sampled
            
            logger.debug(f"解析GPS数据得到 {len(route_points)} 个路线点")
            
        except Exception as e:
            logger.error(f"解析GPS数据失败: {e}")
        
        return route_points
    
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
                    
                    # 解析活动数据
                    parsed = self._parse_activity(activity, user_id)
                    
                    if existing:
                        # 更新已有记录（只更新缺失的数据，如GPS、心率等）
                        logger.debug(f"{self._log_prefix()}活动 {activity_id} 已存在，更新数据")
                        update_fields = {}
                    
                    # 尝试获取详细数据（心率曲线、GPS路线等）
                    try:
                        details_data = await self.get_activity_details(int(activity_id))
                        if details_data:
                            duration = parsed.get("duration_seconds", 3600) or (existing.duration_seconds if existing else 3600)
                            
                            # 解析心率数据
                            if details_data.get("heart_rate_data"):
                                hr_points = self._parse_heart_rate_samples(details_data["heart_rate_data"], duration)
                                if hr_points:
                                    parsed["heart_rate_data"] = json.dumps(hr_points)
                                    logger.info(f"{self._log_prefix()}活动 {activity_id} 获取到 {len(hr_points)} 个心率采样点")
                                else:
                                    # 如果无法获取详细心率，使用平均心率生成简单曲线
                                    avg_hr = parsed.get("avg_heart_rate") or (existing.avg_heart_rate if existing else None)
                                    max_hr = parsed.get("max_heart_rate") or (existing.max_heart_rate if existing else None)
                                    if avg_hr and duration:
                                        # 生成模拟心率曲线（热身-运动-冷却）
                                        hr_points = self._generate_simulated_hr_curve(avg_hr, max_hr, duration)
                                        if hr_points:
                                            parsed["heart_rate_data"] = json.dumps(hr_points)
                                            logger.info(f"{self._log_prefix()}活动 {activity_id} 使用模拟心率曲线 ({len(hr_points)} 点)")
                            
                            # 解析GPS路线数据
                            if details_data.get("gps_data"):
                                start_time = parsed.get("start_time") or (existing.start_time if existing else None)
                                route_points = self._parse_gps_route(details_data["gps_data"], start_time)
                                if route_points:
                                    parsed["route_data"] = json.dumps(route_points)
                                    logger.info(f"{self._log_prefix()}活动 {activity_id} 获取到 {len(route_points)} 个GPS路线点")
                    except Exception as e:
                        logger.debug(f"获取活动详情失败: {e}")
                    
                    if existing:
                        # 更新已有记录（只更新缺失的数据）
                        updated = False
                        
                        # 更新心率数据（如果缺失）
                        if not existing.heart_rate_data and parsed.get("heart_rate_data"):
                            existing.heart_rate_data = parsed["heart_rate_data"]
                            updated = True
                        
                        # 更新GPS数据（如果缺失）
                        if not existing.route_data and parsed.get("route_data"):
                            existing.route_data = parsed["route_data"]
                            updated = True
                        
                        # 更新其他可能缺失的字段
                        if not existing.pace_data and parsed.get("pace_data"):
                            existing.pace_data = parsed.get("pace_data")
                            updated = True
                        
                        if not existing.elevation_data and parsed.get("elevation_data"):
                            existing.elevation_data = parsed.get("elevation_data")
                            updated = True
                        
                        if updated:
                            db.commit()
                            synced_count += 1
                            logger.info(f"{self._log_prefix()}更新活动: {parsed['workout_name']} ({parsed['workout_type']})")
                    else:
                        # 创建新记录
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

