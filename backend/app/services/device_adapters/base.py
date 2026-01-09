"""
设备适配器基类

定义所有设备适配器的统一接口，实现插件化架构
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class DeviceType(str, Enum):
    """支持的设备类型"""
    GARMIN = "garmin"
    HUAWEI = "huawei"
    APPLE = "apple"
    XIAOMI = "xiaomi"
    FITBIT = "fitbit"
    MANUAL = "manual"  # 手动录入


class AuthType(str, Enum):
    """认证类型"""
    PASSWORD = "password"  # 账号密码 (Garmin)
    OAUTH2 = "oauth2"      # OAuth 2.0 (华为、Fitbit)
    FILE = "file"          # 文件导入 (Apple Health Export)
    TOKEN = "token"        # API Token


@dataclass
class NormalizedHealthData:
    """
    规范化的健康数据（适配器输出格式）
    
    所有设备适配器必须将原始数据转换为此格式
    """
    record_date: date
    source: str  # 数据来源设备类型
    
    # ===== 睡眠数据 =====
    sleep_score: Optional[int] = None           # 睡眠评分 0-100
    total_sleep_minutes: Optional[int] = None   # 总睡眠时长（分钟）
    deep_sleep_minutes: Optional[int] = None    # 深睡时长（分钟）
    rem_sleep_minutes: Optional[int] = None     # REM睡眠时长（分钟）
    light_sleep_minutes: Optional[int] = None   # 浅睡时长（分钟）
    awake_minutes: Optional[int] = None         # 清醒时长（分钟）
    sleep_start_time: Optional[time] = None     # 入睡时间
    sleep_end_time: Optional[time] = None       # 起床时间
    
    # ===== 心率数据 =====
    resting_heart_rate: Optional[int] = None    # 静息心率 (bpm)
    avg_heart_rate: Optional[int] = None        # 平均心率
    max_heart_rate: Optional[int] = None        # 最大心率
    min_heart_rate: Optional[int] = None        # 最小心率
    
    # ===== HRV (心率变异性) =====
    hrv: Optional[float] = None                 # HRV值 (ms)
    hrv_status: Optional[str] = None            # HRV状态: balanced, unbalanced, low
    
    # ===== 活动数据 =====
    steps: Optional[int] = None                 # 步数
    distance_meters: Optional[float] = None     # 距离（米）
    floors_climbed: Optional[int] = None        # 爬楼层数
    active_minutes: Optional[int] = None        # 活动分钟数
    calories_total: Optional[int] = None        # 总消耗卡路里
    calories_active: Optional[int] = None       # 活动卡路里
    
    # ===== 压力与恢复 =====
    stress_level: Optional[int] = None          # 压力水平 0-100
    body_battery_high: Optional[int] = None     # 身体电量最高值
    body_battery_low: Optional[int] = None      # 身体电量最低值
    
    # ===== 血氧 =====
    spo2_avg: Optional[float] = None            # 平均血氧饱和度 (%)
    spo2_min: Optional[float] = None            # 最低血氧
    
    # ===== 呼吸 =====
    respiration_rate_avg: Optional[float] = None  # 平均呼吸频率 (次/分钟)
    
    # ===== 原始数据 =====
    raw_data: Optional[Dict[str, Any]] = field(default_factory=dict)  # 完整原始数据（JSON）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "source": self.source,
            "sleep_score": self.sleep_score,
            "total_sleep_minutes": self.total_sleep_minutes,
            "deep_sleep_minutes": self.deep_sleep_minutes,
            "rem_sleep_minutes": self.rem_sleep_minutes,
            "light_sleep_minutes": self.light_sleep_minutes,
            "awake_minutes": self.awake_minutes,
            "resting_heart_rate": self.resting_heart_rate,
            "avg_heart_rate": self.avg_heart_rate,
            "max_heart_rate": self.max_heart_rate,
            "min_heart_rate": self.min_heart_rate,
            "hrv": self.hrv,
            "hrv_status": self.hrv_status,
            "steps": self.steps,
            "distance_meters": self.distance_meters,
            "floors_climbed": self.floors_climbed,
            "active_minutes": self.active_minutes,
            "calories_total": self.calories_total,
            "calories_active": self.calories_active,
            "stress_level": self.stress_level,
            "body_battery_high": self.body_battery_high,
            "body_battery_low": self.body_battery_low,
            "spo2_avg": self.spo2_avg,
            "spo2_min": self.spo2_min,
            "respiration_rate_avg": self.respiration_rate_avg,
        }


@dataclass
class HeartRateSample:
    """心率采样点"""
    timestamp: datetime
    heart_rate: int
    source: str = "unknown"


@dataclass 
class WorkoutData:
    """运动训练数据"""
    workout_date: date
    workout_type: str  # running, cycling, swimming, etc.
    duration_seconds: int
    distance_meters: Optional[float] = None
    calories: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    source: str = "unknown"
    external_id: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class DeviceAdapter(ABC):
    """
    设备适配器抽象基类
    
    所有设备（Garmin、华为、Apple等）必须实现此接口
    """
    
    @property
    @abstractmethod
    def device_type(self) -> DeviceType:
        """返回设备类型标识"""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """返回设备显示名称（用于UI展示）"""
        pass
    
    @property
    @abstractmethod
    def auth_type(self) -> AuthType:
        """返回认证类型"""
        pass
    
    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """
        验证设备凭证
        
        Args:
            credentials: 凭证信息，格式因设备而异
                - Garmin: {"email": "...", "password": "...", "is_cn": bool}
                - 华为: {"access_token": "...", "refresh_token": "..."}
                - Apple: {} (无需认证)
                
        Returns:
            认证是否成功
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试连接是否正常
        
        Returns:
            {
                "success": True/False,
                "message": "连接成功/失败原因",
                "user_info": {...}  # 可选，用户信息
            }
        """
        pass
    
    @abstractmethod
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """
        获取指定日期的健康数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            规范化的健康数据，无数据时返回 None
        """
        pass
    
    async def fetch_heart_rate_samples(
        self, 
        target_date: date
    ) -> List[HeartRateSample]:
        """
        获取心率采样数据（可选实现）
        
        Args:
            target_date: 目标日期
            
        Returns:
            心率采样点列表
        """
        return []
    
    async def fetch_workouts(
        self, 
        start_date: date, 
        end_date: date
    ) -> List[WorkoutData]:
        """
        获取运动记录（可选实现）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            运动记录列表
        """
        return []
    
    async def refresh_token(self) -> bool:
        """
        刷新 OAuth Token（OAuth2 设备需要实现）
        
        Returns:
            刷新是否成功
        """
        return True
    
    def get_oauth_url(self, redirect_uri: str, state: str) -> Optional[str]:
        """
        获取 OAuth 授权 URL（OAuth2 设备需要实现）
        
        Args:
            redirect_uri: 授权后的回调地址
            state: 状态参数，用于防止 CSRF
            
        Returns:
            授权 URL，不支持 OAuth 的设备返回 None
        """
        return None
