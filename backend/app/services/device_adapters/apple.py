"""
Apple Health 适配器

支持从 iPhone 健康 App 导出的 XML 文件导入数据

数据获取方式：
1. 用户从 iPhone 健康 App 导出 XML 数据
   - 打开"健康" App → 右上角头像 → "导出健康数据"
2. 用户上传 XML 文件到服务器
3. 解析并规范化数据，存储到数据库

支持的 HealthKit 数据类型：
- HKQuantityTypeIdentifierStepCount (步数)
- HKQuantityTypeIdentifierHeartRate (心率)
- HKQuantityTypeIdentifierActiveEnergyBurned (活动卡路里)
- HKQuantityTypeIdentifierBasalEnergyBurned (基础代谢卡路里)
- HKCategoryTypeIdentifierSleepAnalysis (睡眠)
- HKQuantityTypeIdentifierOxygenSaturation (血氧)
- HKQuantityTypeIdentifierRespiratoryRate (呼吸频率)
- HKWorkoutTypeIdentifier (运动记录)

未来可扩展：
- 通过 HealthKit 直接读取（需要 iOS App）
- 通过 Apple Health Records API
"""

import xml.etree.ElementTree as ET
import logging
from datetime import date, datetime, time, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict
import json

from .base import (
    DeviceAdapter,
    DeviceType,
    AuthType,
    NormalizedHealthData,
    HeartRateSample,
    WorkoutData
)

logger = logging.getLogger(__name__)


class AppleHealthAdapter(DeviceAdapter):
    """Apple Health 适配器"""
    
    def __init__(self, imported_data: Optional[Dict[str, Any]] = None, **kwargs):
        """
        初始化适配器
        
        Args:
            imported_data: 已导入的数据字典，格式：
                {
                    "2024-01-01": {
                        "steps": 10000,
                        "heart_rate": [...],
                        ...
                    }
                }
            **kwargs: 其他参数（兼容性）
        """
        # 如果 kwargs 中有 imported_data，优先使用
        self.imported_data = kwargs.get("imported_data") or imported_data or {}
    
    @property
    def device_type(self) -> DeviceType:
        return DeviceType.APPLE
    
    @property
    def display_name(self) -> str:
        return "Apple Watch"
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.FILE
    
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """
        Apple Health 通过文件导入，无需认证
        
        但可以检查是否有已导入的数据
        """
        return bool(self.imported_data)
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试连接（检查是否有已导入的数据）"""
        if not self.imported_data:
            return {
                "success": False,
                "message": "未导入健康数据，请先上传 Apple Health 导出文件"
            }
        
        # 统计导入的数据范围
        dates = sorted(self.imported_data.keys())
        return {
            "success": True,
            "message": f"已导入 {len(dates)} 天的健康数据",
            "user_info": {
                "data_range": {
                    "start": dates[0] if dates else None,
                    "end": dates[-1] if dates else None,
                    "days": len(dates)
                }
            }
        }
    
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """
        从已导入的数据中获取指定日期的健康数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            规范化的健康数据，无数据时返回 None
        """
        date_str = target_date.isoformat()
        day_data = self.imported_data.get(date_str)
        
        if not day_data:
            return None
        
        # 构建规范化数据
        return NormalizedHealthData(
            record_date=target_date,
            source=DeviceType.APPLE.value,
            
            # 睡眠数据
            sleep_score=self._calculate_sleep_score(day_data.get("sleep", [])),
            total_sleep_minutes=self._calculate_total_sleep(day_data.get("sleep", [])),
            deep_sleep_minutes=self._calculate_deep_sleep(day_data.get("sleep", [])),
            rem_sleep_minutes=self._calculate_rem_sleep(day_data.get("sleep", [])),
            light_sleep_minutes=self._calculate_light_sleep(day_data.get("sleep", [])),
            sleep_start_time=self._get_sleep_start_time(day_data.get("sleep", [])),
            sleep_end_time=self._get_sleep_end_time(day_data.get("sleep", [])),
            
            # 心率数据
            resting_heart_rate=day_data.get("resting_heart_rate"),
            avg_heart_rate=day_data.get("avg_heart_rate"),
            max_heart_rate=day_data.get("max_heart_rate"),
            min_heart_rate=day_data.get("min_heart_rate"),
            
            # HRV（Apple Watch Series 4+ 支持）
            hrv=day_data.get("hrv"),
            
            # 活动数据
            steps=day_data.get("steps"),
            distance_meters=day_data.get("distance_meters"),
            calories_active=day_data.get("calories_active"),
            calories_total=day_data.get("calories_total"),
            active_minutes=day_data.get("active_minutes"),
            
            # 血氧
            spo2_avg=day_data.get("spo2_avg"),
            spo2_min=day_data.get("spo2_min"),
            
            # 呼吸频率
            respiration_rate_avg=day_data.get("respiration_rate_avg"),
            
            # 原始数据
            raw_data=day_data
        )
    
    async def fetch_heart_rate_samples(self, target_date: date) -> List[HeartRateSample]:
        """获取心率采样数据"""
        date_str = target_date.isoformat()
        day_data = self.imported_data.get(date_str)
        
        if not day_data:
            return []
        
        samples = []
        for hr_data in day_data.get("heart_rate_samples", []):
            try:
                timestamp = datetime.fromisoformat(hr_data["timestamp"].replace("Z", "+00:00"))
                samples.append(HeartRateSample(
                    timestamp=timestamp,
                    heart_rate=hr_data["value"],
                    source=DeviceType.APPLE.value
                ))
            except Exception as e:
                logger.warning(f"解析心率采样数据失败: {e}")
        
        return samples
    
    async def fetch_workouts(self, start_date: date, end_date: date) -> List[WorkoutData]:
        """获取运动记录"""
        workouts = []
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.isoformat()
            day_data = self.imported_data.get(date_str)
            
            if day_data:
                for workout in day_data.get("workouts", []):
                    try:
                        workouts.append(WorkoutData(
                            workout_date=current_date,
                            workout_type=workout.get("type", "unknown"),
                            duration_seconds=workout.get("duration", 0),
                            distance_meters=workout.get("distance"),
                            calories=workout.get("calories"),
                            avg_heart_rate=workout.get("avg_heart_rate"),
                            max_heart_rate=workout.get("max_heart_rate"),
                            source=DeviceType.APPLE.value,
                            external_id=workout.get("id"),
                            raw_data=workout
                        ))
                    except Exception as e:
                        logger.warning(f"解析运动记录失败: {e}")
            
            current_date += timedelta(days=1)
        
        return workouts
    
    @staticmethod
    def parse_health_xml(xml_content: str) -> Dict[str, Any]:
        """
        解析 Apple Health 导出的 XML 文件
        
        Args:
            xml_content: XML 文件内容
            
        Returns:
            按日期组织的数据字典：
            {
                "2024-01-01": {
                    "steps": 10000,
                    "heart_rate_samples": [...],
                    "sleep": [...],
                    ...
                }
            }
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"XML 解析失败: {e}")
            raise ValueError(f"无效的 XML 文件: {e}")
        
        # 按日期组织数据
        daily_data = defaultdict(lambda: {
            "steps": 0,
            "heart_rate_samples": [],
            "sleep": [],
            "workouts": [],
            "calories_active": 0,
            "calories_total": 0,
            "distance_meters": 0.0,
            "spo2_samples": [],
            "respiration_samples": [],
            "hrv_samples": []
        })
        
        # 解析记录
        for record in root.findall(".//Record"):
            record_type = record.get("type")
            value = record.get("value")
            start_date = record.get("startDate")
            end_date = record.get("endDate")
            
            if not start_date:
                continue
            
            try:
                # 解析日期
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                date_key = start_dt.date().isoformat()
                
                if record_type == "HKQuantityTypeIdentifierStepCount":
                    # 步数（累加）
                    if value:
                        daily_data[date_key]["steps"] += int(float(value))
                
                elif record_type == "HKQuantityTypeIdentifierHeartRate":
                    # 心率采样
                    if value:
                        daily_data[date_key]["heart_rate_samples"].append({
                            "timestamp": start_date,
                            "value": int(float(value))
                        })
                
                elif record_type == "HKQuantityTypeIdentifierActiveEnergyBurned":
                    # 活动卡路里（累加）
                    if value:
                        daily_data[date_key]["calories_active"] += float(value)
                
                elif record_type == "HKQuantityTypeIdentifierBasalEnergyBurned":
                    # 基础代谢卡路里（累加）
                    if value:
                        daily_data[date_key]["calories_total"] += float(value)
                
                elif record_type == "HKQuantityTypeIdentifierDistanceWalkingRunning":
                    # 步行/跑步距离（累加）
                    if value:
                        daily_data[date_key]["distance_meters"] += float(value) * 1000  # 转换为米
                
                elif record_type == "HKCategoryTypeIdentifierSleepAnalysis":
                    # 睡眠分析
                    sleep_value = record.get("value")
                    if sleep_value and end_date:
                        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
                        
                        daily_data[date_key]["sleep"].append({
                            "type": sleep_value,  # "ASLEEP", "AWAKE", "INBED"
                            "start": start_date,
                            "end": end_date,
                            "duration_minutes": duration_minutes
                        })
                
                elif record_type == "HKQuantityTypeIdentifierOxygenSaturation":
                    # 血氧饱和度
                    if value:
                        daily_data[date_key]["spo2_samples"].append({
                            "timestamp": start_date,
                            "value": float(value) * 100  # 转换为百分比
                        })
                
                elif record_type == "HKQuantityTypeIdentifierRespiratoryRate":
                    # 呼吸频率
                    if value:
                        daily_data[date_key]["respiration_samples"].append({
                            "timestamp": start_date,
                            "value": float(value)
                        })
                
                elif record_type == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
                    # HRV (SDNN)
                    if value:
                        daily_data[date_key]["hrv_samples"].append({
                            "timestamp": start_date,
                            "value": float(value) * 1000  # 转换为毫秒
                        })
            
            except Exception as e:
                logger.warning(f"解析记录失败 (type={record_type}): {e}")
                continue
        
        # 解析运动记录
        for workout in root.findall(".//Workout"):
            workout_type = workout.get("workoutActivityType")
            start_date = workout.get("startDate")
            
            if not start_date:
                continue
            
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                date_key = start_dt.date().isoformat()
                
                end_date = workout.get("endDate")
                duration = 0
                if end_date:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    duration = int((end_dt - start_dt).total_seconds())
                
                # 提取运动数据
                total_energy = workout.find(".//MetadataEntry[@key='HKTotalEnergyBurned']")
                total_distance = workout.find(".//MetadataEntry[@key='HKTotalDistance']")
                
                daily_data[date_key]["workouts"].append({
                    "id": workout.get("sourceName", ""),
                    "type": AppleHealthAdapter._map_workout_type(workout_type),
                    "start": start_date,
                    "end": end_date,
                    "duration": duration,
                    "calories": float(total_energy.get("value")) if total_energy is not None else None,
                    "distance": float(total_distance.get("value")) * 1000 if total_distance is not None else None,  # 转换为米
                })
            
            except Exception as e:
                logger.warning(f"解析运动记录失败: {e}")
                continue
        
        # 聚合每日数据
        result = {}
        for date_key, data in daily_data.items():
            # 计算心率统计
            hr_samples = data["heart_rate_samples"]
            if hr_samples:
                hr_values = [s["value"] for s in hr_samples]
                data["avg_heart_rate"] = int(sum(hr_values) / len(hr_values))
                data["max_heart_rate"] = max(hr_values)
                data["min_heart_rate"] = min(hr_values)
                # 静息心率通常是最小值或早上的平均值
                morning_hrs = [s["value"] for s in hr_samples 
                              if datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).hour < 8]
                data["resting_heart_rate"] = int(sum(morning_hrs) / len(morning_hrs)) if morning_hrs else min(hr_values)
            
            # 计算血氧统计
            spo2_samples = data["spo2_samples"]
            if spo2_samples:
                spo2_values = [s["value"] for s in spo2_samples]
                data["spo2_avg"] = sum(spo2_values) / len(spo2_values)
                data["spo2_min"] = min(spo2_values)
            
            # 计算呼吸频率统计
            resp_samples = data["respiration_samples"]
            if resp_samples:
                resp_values = [s["value"] for s in resp_samples]
                data["respiration_rate_avg"] = sum(resp_values) / len(resp_values)
            
            # 计算 HRV 平均值
            hrv_samples = data["hrv_samples"]
            if hrv_samples:
                hrv_values = [s["value"] for s in hrv_samples]
                data["hrv"] = sum(hrv_values) / len(hrv_values)
            
            # 计算活动分钟数（粗略估算）
            if data["steps"] > 0:
                # 假设每分钟至少 60 步才算活动
                data["active_minutes"] = min(data["steps"] // 60, 1440)  # 最多 24 小时
            
            result[date_key] = dict(data)
        
        return result
    
    @staticmethod
    def _map_workout_type(activity_type: str) -> str:
        """映射 Apple 运动类型到通用类型"""
        # Apple 运动类型是数字代码
        # 常见类型映射
        workout_map = {
            "1": "running",      # Running
            "2": "cycling",      # Cycling
            "3": "walking",      # Walking
            "4": "swimming",     # Swimming
            "5": "hiking",       # Hiking
            "16": "yoga",        # Yoga
            "37": "strength",    # Traditional Strength Training
        }
        return workout_map.get(activity_type, "other")
    
    def _calculate_sleep_score(self, sleep_records: List[Dict]) -> Optional[int]:
        """计算睡眠评分（简化算法）"""
        if not sleep_records:
            return None
        
        total_sleep = self._calculate_total_sleep(sleep_records)
        if total_sleep < 360:  # 少于 6 小时
            return 50
        elif total_sleep < 420:  # 6-7 小时
            return 70
        elif total_sleep < 540:  # 7-9 小时
            return 90
        else:  # 超过 9 小时
            return 80
    
    def _calculate_total_sleep(self, sleep_records: List[Dict]) -> Optional[int]:
        """计算总睡眠时长（分钟）"""
        if not sleep_records:
            return None
        
        total = 0
        for record in sleep_records:
            if record.get("type") == "ASLEEP":
                total += record.get("duration_minutes", 0)
        return total if total > 0 else None
    
    def _calculate_deep_sleep(self, sleep_records: List[Dict]) -> Optional[int]:
        """计算深睡时长（Apple Health 不直接提供，估算）"""
        # Apple Health 的睡眠分析通常只有 ASLEEP/AWAKE/INBED
        # 深睡通常占总睡眠的 15-20%
        total = self._calculate_total_sleep(sleep_records)
        if total:
            return int(total * 0.17)  # 估算 17%
        return None
    
    def _calculate_rem_sleep(self, sleep_records: List[Dict]) -> Optional[int]:
        """计算 REM 睡眠时长（估算）"""
        total = self._calculate_total_sleep(sleep_records)
        if total:
            return int(total * 0.20)  # 估算 20%
        return None
    
    def _calculate_light_sleep(self, sleep_records: List[Dict]) -> Optional[int]:
        """计算浅睡时长（估算）"""
        total = self._calculate_total_sleep(sleep_records)
        deep = self._calculate_deep_sleep(sleep_records) or 0
        rem = self._calculate_rem_sleep(sleep_records) or 0
        if total:
            return total - deep - rem
        return None
    
    def _get_sleep_start_time(self, sleep_records: List[Dict]) -> Optional[time]:
        """获取入睡时间"""
        if not sleep_records:
            return None
        
        asleep_records = [r for r in sleep_records if r.get("type") == "ASLEEP"]
        if not asleep_records:
            return None
        
        earliest = min(asleep_records, key=lambda x: x.get("start", ""))
        try:
            dt = datetime.fromisoformat(earliest["start"].replace("Z", "+00:00"))
            return dt.time()
        except:
            return None
    
    def _get_sleep_end_time(self, sleep_records: List[Dict]) -> Optional[time]:
        """获取起床时间"""
        if not sleep_records:
            return None
        
        asleep_records = [r for r in sleep_records if r.get("type") == "ASLEEP"]
        if not asleep_records:
            return None
        
        latest = max(asleep_records, key=lambda x: x.get("end", ""))
        try:
            dt = datetime.fromisoformat(latest["end"].replace("Z", "+00:00"))
            return dt.time()
        except:
            return None
