"""Garmin Connect数据收集服务（使用社区库garminconnect）"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.schemas.daily_health import GarminDataCreate
import logging

logger = logging.getLogger(__name__)

try:
    from garminconnect import Garmin
    GARMINCONNECT_AVAILABLE = True
except ImportError:
    GARMINCONNECT_AVAILABLE = False
    logger.warning("garminconnect库未安装，请运行: pip install garminconnect")


class GarminConnectService:
    """
    Garmin Connect数据收集服务
    
    使用社区库 garminconnect (https://github.com/cyberjunky/python-garminconnect)
    这个库通过模拟浏览器登录Garmin Connect来获取数据，不需要官方API密钥
    
    安装: pip install garminconnect
    """
    
    def __init__(self, email: str, password: str):
        """
        初始化Garmin Connect服务
        
        Args:
            email: Garmin Connect账号邮箱
            password: Garmin Connect账号密码
        """
        if not GARMINCONNECT_AVAILABLE:
            raise ImportError(
                "garminconnect库未安装。请运行: pip install garminconnect\n"
                "GitHub: https://github.com/cyberjunky/python-garminconnect"
            )
        
        self.email = email
        self.password = password
        self.client: Optional[Garmin] = None
        self._authenticated = False
    
    def _ensure_authenticated(self):
        """确保已认证"""
        if not self._authenticated or self.client is None:
            self.client = Garmin(self.email, self.password)
            self.client.login()
            self._authenticated = True
            logger.info("Garmin Connect登录成功")
    
    def get_user_summary(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取指定日期的每日摘要数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            包含所有健康数据的字典，如果失败返回None
        """
        try:
            self._ensure_authenticated()
            
            # 使用get_user_summary获取每日摘要（garminconnect库的实际方法名）
            summary = self.client.get_user_summary(target_date.isoformat())
            
            if summary:
                logger.info(f"成功获取 {target_date} 的Garmin数据")
                return summary
            else:
                logger.warning(f"未找到 {target_date} 的数据")
                return None
                
        except Exception as e:
            logger.error(f"获取Garmin数据失败: {str(e)}")
            return None
    
    def get_sleep_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取睡眠数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            睡眠数据字典
        """
        try:
            self._ensure_authenticated()
            sleep_data = self.client.get_sleep_data(target_date.isoformat())
            return sleep_data
        except Exception as e:
            logger.error(f"获取睡眠数据失败: {str(e)}")
            return None
    
    def get_heart_rates(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取心率数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            心率数据字典
        """
        try:
            self._ensure_authenticated()
            hr_data = self.client.get_heart_rates(target_date.isoformat())
            return hr_data
        except Exception as e:
            logger.error(f"获取心率数据失败: {str(e)}")
            return None
    
    def get_body_battery(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取身体电量数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            身体电量数据字典
        """
        try:
            self._ensure_authenticated()
            battery_data = self.client.get_body_battery(target_date.isoformat())
            return battery_data
        except Exception as e:
            logger.error(f"获取身体电量数据失败: {str(e)}")
            return None
    
    def get_stress_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取压力数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            压力数据字典
        """
        try:
            self._ensure_authenticated()
            # 使用get_all_day_stress获取压力数据（garminconnect库的实际方法名）
            stress_data = self.client.get_all_day_stress(target_date.isoformat())
            return stress_data
        except Exception as e:
            logger.error(f"获取压力数据失败: {str(e)}")
            return None
    
    def get_all_daily_data(self, target_date: date) -> Dict[str, Any]:
        """
        获取指定日期的所有数据（汇总）
        
        Args:
            target_date: 目标日期
            
        Returns:
            包含所有数据的字典
        """
        result = {}
        
        # 获取用户摘要（包含大部分数据）
        summary = self.get_user_summary(target_date)
        if summary:
            if isinstance(summary, dict):
                result.update(summary)
                logger.debug(f"从get_user_summary获取的数据键: {list(summary.keys())[:20]}")
            else:
                logger.warning(f"get_user_summary返回的不是字典类型: {type(summary)}")
        
        # 获取睡眠数据（优先使用独立API，数据更详细）
        sleep_data = self.get_sleep_data(target_date)
        if sleep_data:
            result['sleep'] = sleep_data
            if isinstance(sleep_data, dict):
                logger.debug(f"从get_sleep_data获取的数据键: {list(sleep_data.keys())[:20]}")
            elif isinstance(sleep_data, list):
                logger.debug(f"从get_sleep_data获取的是列表，长度: {len(sleep_data)}")
            else:
                logger.debug(f"从get_sleep_data获取的数据类型: {type(sleep_data)}")
        elif isinstance(summary, dict) and ('sleepScore' in summary or 'sleepScores' in summary):
            # 如果独立API没有数据，但summary中有睡眠数据，使用summary的
            logger.info("使用summary中的睡眠数据")
        
        # 获取心率数据（优先使用独立API）
        hr_data = self.get_heart_rates(target_date)
        if hr_data:
            result['heart_rate'] = hr_data
            if isinstance(hr_data, dict):
                logger.debug(f"从get_heart_rates获取的数据键: {list(hr_data.keys())[:20]}")
            elif isinstance(hr_data, list):
                logger.debug(f"从get_heart_rates获取的是列表，长度: {len(hr_data)}")
            else:
                logger.debug(f"从get_heart_rates获取的数据类型: {type(hr_data)}")
        elif isinstance(summary, dict) and ('averageHeartRate' in summary or 'avgHeartRate' in summary):
            # 如果独立API没有数据，但summary中有心率数据，使用summary的
            logger.info("使用summary中的心率数据")
        
        # 获取身体电量
        battery_data = self.get_body_battery(target_date)
        if battery_data:
            result['body_battery'] = battery_data
            if isinstance(battery_data, list):
                logger.debug(f"从get_body_battery获取的是列表，长度: {len(battery_data)}")
            elif isinstance(battery_data, dict):
                logger.debug(f"从get_body_battery获取的数据键: {list(battery_data.keys())[:20]}")
        
        # 获取压力数据
        stress_data = self.get_stress_data(target_date)
        if stress_data:
            result['stress'] = stress_data
            if isinstance(stress_data, list):
                logger.debug(f"从get_stress_data获取的是列表，长度: {len(stress_data)}")
            elif isinstance(stress_data, dict):
                logger.debug(f"从get_stress_data获取的数据键: {list(stress_data.keys())[:20]}")
        
        return result
    
    def parse_to_garmin_data_create(
        self,
        raw_data: Dict[str, Any],
        user_id: int,
        record_date: date
    ) -> GarminDataCreate:
        """
        将Garmin Connect返回的原始数据解析为GarminDataCreate
        
        Args:
            raw_data: Garmin Connect返回的原始数据（可能包含summary、sleep、heart_rate等）
            user_id: 用户ID
            record_date: 记录日期
            
        Returns:
            GarminDataCreate对象
        """
        # 调试：打印原始数据结构（仅前1000字符）
        import json
        raw_data_str = json.dumps(raw_data, indent=2, default=str)[:2000]
        logger.debug(f"解析Garmin数据，原始数据结构（前2000字符）:\n{raw_data_str}")
        
        # 从get_user_summary获取的数据在根级别
        summary = raw_data.copy() if isinstance(raw_data, dict) else {}
        
        # 处理睡眠数据（可能来自get_sleep_data或summary）
        sleep_data_raw = raw_data.get('sleep') if isinstance(raw_data, dict) else None
        
        # 如果sleep_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(sleep_data_raw, list) and sleep_data_raw:
            sleep_data = sleep_data_raw[0] if isinstance(sleep_data_raw[0], dict) else {}
        elif isinstance(sleep_data_raw, dict):
            sleep_data = sleep_data_raw
        else:
            sleep_data = {}
        
        # 辅助函数：安全获取嵌套字典值（支持多层嵌套）
        def safe_get_nested(data, *keys, default=None):
            """安全获取多层嵌套字典值"""
            if not isinstance(data, dict):
                return default
            for key in keys:
                if not isinstance(data, dict):
                    return default
                data = data.get(key)
                if data is None:
                    return default
            return data if data is not None else default
        
        # 尝试多种方式获取睡眠分数
        sleep_score = None
        sleep_duration_seconds = 0
        deep_sleep_seconds = 0
        rem_sleep_seconds = 0
        light_sleep_seconds = 0
        awake_seconds = 0
        avg_heart_rate_during_sleep = None
        
        if isinstance(sleep_data, dict) and sleep_data:
            # Garmin睡眠数据结构:
            # sleep_data = {
            #   'dailySleepDTO': {
            #     'sleepTimeSeconds': 29280,
            #     'sleepScores': {'overall': {'value': 87}},
            #     'deepSleepSeconds': 3720,
            #     ...
            #   },
            #   'restingHeartRate': 51,
            #   ...
            # }
            
            # 获取 dailySleepDTO
            daily_sleep_dto = sleep_data.get('dailySleepDTO', {})
            if not isinstance(daily_sleep_dto, dict):
                daily_sleep_dto = {}
            
            logger.debug(f"dailySleepDTO 键: {list(daily_sleep_dto.keys()) if daily_sleep_dto else '无'}")
            
            # 获取睡眠分数 - 正确的路径是 dailySleepDTO.sleepScores.overall.value
            sleep_score = (
                safe_get_nested(daily_sleep_dto, 'sleepScores', 'overall', 'value') or
                safe_get_nested(sleep_data, 'sleepScores', 'overall', 'value') or
                daily_sleep_dto.get('sleepScore') or
                sleep_data.get('sleepScore') or
                safe_get_nested(daily_sleep_dto, 'sleepScores', 'overall') or
                sleep_data.get('overallSleepScore')
            )
            
            # 如果sleep_score是字典（如 {'value': 87, 'qualifierKey': 'GOOD'}），提取value
            if isinstance(sleep_score, dict):
                sleep_score = sleep_score.get('value')
            
            logger.debug(f"提取的睡眠分数: {sleep_score}")
            
            # 睡眠时长（秒）- 从 dailySleepDTO 获取
            sleep_duration_seconds = (
                daily_sleep_dto.get('sleepTimeSeconds') or
                sleep_data.get('sleepTimeSeconds') or
                0
            )
            
            # 睡眠阶段数据 - 从 dailySleepDTO 获取
            deep_sleep_seconds = daily_sleep_dto.get('deepSleepSeconds', 0) or 0
            rem_sleep_seconds = daily_sleep_dto.get('remSleepSeconds', 0) or 0
            light_sleep_seconds = daily_sleep_dto.get('lightSleepSeconds', 0) or 0
            awake_seconds = daily_sleep_dto.get('awakeSleepSeconds', 0) or 0
            
            # 睡眠期间平均心率
            avg_heart_rate_during_sleep = (
                daily_sleep_dto.get('avgHeartRate') or
                sleep_data.get('restingHeartRate')
            )
            
            logger.debug(f"睡眠数据: 分数={sleep_score}, 时长秒={sleep_duration_seconds}, 深睡={deep_sleep_seconds}, REM={rem_sleep_seconds}")
        
        # 如果从sleep_data没有获取到，尝试从summary获取
        if isinstance(summary, dict):
            if sleep_score is None:
                score_val = (
                    summary.get('sleepScore') or
                    safe_get_nested(summary, 'sleepScores', 'overall', 'value') or
                    safe_get_nested(summary, 'sleepScores', 'overall') or
                    summary.get('overallSleepScore') or
                    summary.get('sleepQualityScore')
                )
                # 如果是字典，提取value
                if isinstance(score_val, dict):
                    sleep_score = score_val.get('value')
                else:
                    sleep_score = score_val
            if sleep_duration_seconds == 0:
                sleep_millis = summary.get('sleepTimeMillis')
                sleep_duration_seconds = (
                    summary.get('sleepTimeSeconds') or
                    summary.get('sleepDurationSeconds') or
                    summary.get('sleepingSeconds') or
                    (sleep_millis / 1000 if sleep_millis else 0) or
                    summary.get('totalSleepTimeSeconds') or
                    0
                )
            if deep_sleep_seconds == 0:
                deep_sleep_seconds = summary.get('deepSleepSeconds', 0) or summary.get('deepSleepSecondsOvernight', 0) or 0
            if rem_sleep_seconds == 0:
                rem_sleep_seconds = summary.get('remSleepSeconds', 0) or summary.get('remSleepSecondsOvernight', 0) or 0
            if light_sleep_seconds == 0:
                light_sleep_seconds = summary.get('lightSleepSeconds', 0) or summary.get('lightSleepSecondsOvernight', 0) or 0
            if awake_seconds == 0:
                awake_seconds = summary.get('awakeSleepSeconds', 0) or summary.get('awakeSleepSecondsOvernight', 0) or 0
        
        # 处理心率数据（可能来自get_heart_rates或summary）
        hr_data_raw = None
        if isinstance(raw_data, dict):
            hr_data_raw = raw_data.get('heart_rate') or raw_data.get('heartRates')
        
        # 如果hr_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(hr_data_raw, list) and hr_data_raw:
            hr_data = hr_data_raw[0] if isinstance(hr_data_raw[0], dict) else {}
        elif isinstance(hr_data_raw, dict):
            hr_data = hr_data_raw
        else:
            hr_data = {}
        
        avg_hr = None
        resting_hr = None
        max_hr = None
        min_hr = None
        
        if isinstance(hr_data, dict) and hr_data:
            # 从独立的heart_rate数据中提取
            hr_values = hr_data.get('heartRateValues')
            first_hr_value = None
            if isinstance(hr_values, list) and hr_values and isinstance(hr_values[0], dict):
                first_hr_value = hr_values[0].get('value')
            
            avg_hr = (
                hr_data.get('averageHeartRate') or
                hr_data.get('avg') or
                hr_data.get('avgHeartRate') or
                hr_data.get('average') or
                first_hr_value
            )
            resting_hr = (
                hr_data.get('restingHeartRate') or
                hr_data.get('resting') or
                hr_data.get('restingHeartRateValue')
            )
            max_hr = hr_data.get('maxHeartRate') or hr_data.get('max')
            min_hr = hr_data.get('minHeartRate') or hr_data.get('min')
        
        # 如果从hr_data没有获取到，尝试从summary获取
        if isinstance(summary, dict):
            if avg_hr is None:
                avg_hr = (
                    summary.get('averageHeartRate') or
                    summary.get('avgHeartRate') or
                    summary.get('avg') or
                    summary.get('average') or
                    summary.get('heartRateAverage')
                )
            if resting_hr is None:
                resting_hr = (
                    summary.get('restingHeartRate') or
                    summary.get('resting') or
                    summary.get('restingHeartRateValue')
                )
            if max_hr is None:
                max_hr = summary.get('maxHeartRate') or summary.get('max')
            if min_hr is None:
                min_hr = summary.get('minHeartRate') or summary.get('min')
        
        # HRV数据
        hrv = None
        if isinstance(summary, dict):
            hrv = summary.get('hrv') or safe_get_nested(summary, 'hrvStatus', 'hrv')
        
        # 身体电量数据（可能来自get_body_battery或summary）
        battery_data_raw = None
        if isinstance(raw_data, dict):
            battery_data_raw = raw_data.get('body_battery') or raw_data.get('bodyBattery')
        
        # 如果battery_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(battery_data_raw, list) and battery_data_raw:
            battery_data = battery_data_raw[0] if isinstance(battery_data_raw[0], dict) else {}
        elif isinstance(battery_data_raw, dict):
            battery_data = battery_data_raw
        else:
            battery_data = {}
        
        charged = None
        drained = None
        most_charged = None
        lowest = None
        
        if isinstance(battery_data, dict) and battery_data:
            charged = battery_data.get('charged') or battery_data.get('bodyBatteryCharged') or battery_data.get('chargedValue')
            drained = battery_data.get('drained') or battery_data.get('bodyBatteryDrained') or battery_data.get('drainedValue')
            most_charged = battery_data.get('mostCharged') or battery_data.get('bodyBatteryMostCharged') or battery_data.get('mostChargedValue')
            lowest = battery_data.get('lowest') or battery_data.get('bodyBatteryLowest') or battery_data.get('lowestValue')
        elif isinstance(summary, dict):
            charged = summary.get('bodyBatteryCharged') or summary.get('bodyBatteryChargedValue') or summary.get('charged')
            drained = summary.get('bodyBatteryDrained') or summary.get('bodyBatteryDrainedValue') or summary.get('drained')
            most_charged = summary.get('bodyBatteryMostCharged') or summary.get('bodyBatteryMostChargedValue') or summary.get('mostCharged')
            lowest = summary.get('bodyBatteryLowest') or summary.get('bodyBatteryLowestValue') or summary.get('lowest')
        
        # 压力数据（可能来自get_all_day_stress或summary）
        stress_data_raw = None
        if isinstance(raw_data, dict):
            stress_data_raw = raw_data.get('stress')
        
        stress_level = None
        if isinstance(stress_data_raw, list) and stress_data_raw:
            # get_all_day_stress返回的是数组，需要计算平均值
            stress_values = [s.get('stressLevelValue', s.get('value', 0)) for s in stress_data_raw if isinstance(s, dict)]
            stress_level = sum(stress_values) / len(stress_values) if stress_values else None
        elif isinstance(stress_data_raw, dict) and stress_data_raw:
            stress_level = stress_data_raw.get('stressLevel', stress_data_raw.get('value', stress_data_raw.get('stressLevelValue')))
        
        # 如果从stress数据中没有获取到，尝试从summary获取
        if stress_level is None and isinstance(summary, dict):
            stress_level = summary.get('stressLevel', summary.get('stress', summary.get('averageStressLevel')))
        
        # 活动数据（从summary获取）
        steps = None
        calories = None
        active_minutes = None
        
        if isinstance(summary, dict):
            # 步数：优先使用totalSteps
            steps = (
                summary.get('totalSteps') or 
                summary.get('steps') or 
                safe_get_nested(summary, 'stepGoal', 'steps')
            )
            # 卡路里：优先使用totalKilocalories
            calories = (
                summary.get('totalKilocalories') or
                summary.get('activeKilocalories') or
                summary.get('calories') or 
                summary.get('caloriesBurned') or 
                summary.get('totalCalories') or
                safe_get_nested(summary, 'netCalorieGoal', 'calories')
            )
            moderate_mins = summary.get('moderateIntensityMinutes', 0) or summary.get('moderateActivityMinutes', 0) or 0
            vigorous_mins = summary.get('vigorousIntensityMinutes', 0) or summary.get('vigorousActivityMinutes', 0) or 0
            active_minutes = summary.get('activeMinutes') or summary.get('highlyActiveSeconds', 0) // 60 or (moderate_mins + vigorous_mins) or 0
        
        # 安全的数值转换函数
        def safe_int(value):
            """安全地将值转换为整数，如果是字典或列表则返回None"""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    return None
            # 如果是字典或列表，尝试提取数值
            if isinstance(value, dict):
                # 尝试常见的数值字段名
                for key in ['value', 'amount', 'count', 'total', 'average', 'avg']:
                    if key in value and isinstance(value[key], (int, float)):
                        return int(value[key])
                return None
            return None
        
        def safe_float(value):
            """安全地将值转换为浮点数，如果是字典或列表则返回None"""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            if isinstance(value, dict):
                for key in ['value', 'amount', 'average', 'avg']:
                    if key in value and isinstance(value[key], (int, float)):
                        return float(value[key])
                return None
            return None
        
        # 睡眠时间转换（秒转分钟，处理毫秒）
        def seconds_to_minutes(value):
            if not value:
                return None
            if isinstance(value, (int, float)):
                # 如果是毫秒，先转换为秒
                if value > 86400:  # 如果大于一天的秒数，可能是毫秒
                    value = value / 1000
                return int(value // 60)
            return None
        
        # 记录解析结果用于调试
        logger.info(f"解析结果 - 睡眠分数: {sleep_score} (类型: {type(sleep_score).__name__}), 睡眠时长(秒): {sleep_duration_seconds}, 平均心率: {avg_hr} (类型: {type(avg_hr).__name__})")
        
        result = GarminDataCreate(
            user_id=user_id,
            record_date=record_date,
            avg_heart_rate=safe_int(avg_hr),
            max_heart_rate=safe_int(max_hr),
            min_heart_rate=safe_int(min_hr),
            resting_heart_rate=safe_int(resting_hr),
            hrv=safe_float(hrv),
            sleep_score=safe_int(sleep_score),
            total_sleep_duration=seconds_to_minutes(sleep_duration_seconds),
            deep_sleep_duration=seconds_to_minutes(deep_sleep_seconds),
            rem_sleep_duration=seconds_to_minutes(rem_sleep_seconds),
            light_sleep_duration=seconds_to_minutes(light_sleep_seconds),
            awake_duration=seconds_to_minutes(awake_seconds),
            body_battery_charged=safe_int(charged),
            body_battery_drained=safe_int(drained),
            body_battery_most_charged=safe_int(most_charged),
            body_battery_lowest=safe_int(lowest),
            stress_level=safe_int(stress_level),
            steps=safe_int(steps),
            calories_burned=safe_int(calories),
            active_minutes=safe_int(active_minutes),
        )
        
        return result
    
    def sync_daily_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[GarminData]:
        """
        同步指定日期的数据到数据库
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期
            
        Returns:
            保存的GarminData对象，如果失败返回None
        """
        try:
            # 获取所有数据
            logger.info(f"开始获取 {target_date} 的数据...")
            raw_data = self.get_all_daily_data(target_date)
            
            if not raw_data:
                logger.warning(f"未获取到 {target_date} 的数据（raw_data为空）")
                return None
            
            logger.info(f"获取到 {target_date} 的原始数据，键数量: {len(raw_data) if isinstance(raw_data, dict) else 'N/A'}")
            
            # 解析数据
            logger.info(f"开始解析 {target_date} 的数据...")
            garmin_data = self.parse_to_garmin_data_create(raw_data, user_id, target_date)
            
            logger.info(f"解析完成，步数: {garmin_data.steps}, 心率: {garmin_data.resting_heart_rate}")
            
            # 保存到数据库
            logger.info(f"开始保存 {target_date} 的数据到数据库...")
            from app.services.data_collection.garmin_service import GarminService
            garmin_service = GarminService()
            result = garmin_service.save_garmin_data(db, garmin_data)
            
            logger.info(f"成功保存 {target_date} 的数据，ID: {result.id}")
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"同步Garmin数据失败: {str(e)}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
    
    def sync_date_range(
        self,
        db: Session,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        批量同步日期范围的数据
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            同步结果统计
        """
        results = []
        errors = []
        current_date = start_date
        
        while current_date <= end_date:
            try:
                result = self.sync_daily_data(db, user_id, current_date)
                if result:
                    results.append({
                        "date": current_date.isoformat(),
                        "status": "success",
                        "data_id": result.id
                    })
                else:
                    errors.append({
                        "date": current_date.isoformat(),
                        "status": "no_data"
                    })
            except Exception as e:
                errors.append({
                    "date": current_date.isoformat(),
                    "status": "error",
                    "error": str(e)
                })
            
            current_date += timedelta(days=1)
            
            # 避免请求过快，添加小延迟
            import time
            time.sleep(0.8)  # 稍微增加延迟，避免被Garmin限制
        
        return {
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors
        }

