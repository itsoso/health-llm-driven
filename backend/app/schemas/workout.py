"""运动训练记录 Schemas"""
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class WorkoutType(str, Enum):
    """运动类型"""
    RUNNING = "running"
    SWIMMING = "swimming"
    CYCLING = "cycling"
    HIIT = "hiit"
    CARDIO = "cardio"
    STRENGTH = "strength"
    YOGA = "yoga"
    WALKING = "walking"
    HIKING = "hiking"
    OTHER = "other"


class SwimStyle(str, Enum):
    """泳姿"""
    FREESTYLE = "freestyle"
    BACKSTROKE = "backstroke"
    BREASTSTROKE = "breaststroke"
    BUTTERFLY = "butterfly"
    MIXED = "mixed"


class Feeling(str, Enum):
    """运动感受"""
    GREAT = "great"
    GOOD = "good"
    NORMAL = "normal"
    TIRED = "tired"
    EXHAUSTED = "exhausted"


class HeartRatePoint(BaseModel):
    """心率数据点"""
    time: int  # 时间（秒，从运动开始）
    hr: int  # 心率


class PacePoint(BaseModel):
    """配速数据点"""
    time: int  # 时间（秒）
    pace: int  # 配速（秒/公里）


class ElevationPoint(BaseModel):
    """海拔数据点"""
    distance: float  # 距离（米）
    elevation: float  # 海拔（米）


class WorkoutRecordBase(BaseModel):
    """运动记录基础字段"""
    workout_date: date
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    workout_type: WorkoutType
    workout_name: Optional[str] = None
    
    # 时长
    duration_seconds: Optional[int] = None
    moving_duration_seconds: Optional[int] = None
    
    # 距离与配速
    distance_meters: Optional[float] = None
    avg_pace_seconds_per_km: Optional[int] = None
    best_pace_seconds_per_km: Optional[int] = None
    avg_speed_kmh: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    
    # 心率
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    hr_zone_1_seconds: Optional[int] = None
    hr_zone_2_seconds: Optional[int] = None
    hr_zone_3_seconds: Optional[int] = None
    hr_zone_4_seconds: Optional[int] = None
    hr_zone_5_seconds: Optional[int] = None
    
    # 卡路里
    calories: Optional[int] = None
    active_calories: Optional[int] = None
    
    # 跑步特有
    steps: Optional[int] = None
    avg_stride_length_cm: Optional[float] = None
    avg_cadence: Optional[int] = None
    max_cadence: Optional[int] = None
    
    # 骑车特有
    avg_power_watts: Optional[int] = None
    max_power_watts: Optional[int] = None
    normalized_power_watts: Optional[int] = None
    
    # 游泳特有
    pool_length_meters: Optional[int] = None
    laps: Optional[int] = None
    strokes: Optional[int] = None
    avg_strokes_per_length: Optional[float] = None
    swim_style: Optional[SwimStyle] = None
    
    # 高度
    elevation_gain_meters: Optional[float] = None
    elevation_loss_meters: Optional[float] = None
    min_elevation_meters: Optional[float] = None
    max_elevation_meters: Optional[float] = None
    
    # 训练效果
    training_effect_aerobic: Optional[float] = None
    training_effect_anaerobic: Optional[float] = None
    vo2max: Optional[float] = None
    training_load: Optional[int] = None
    
    # 感受
    perceived_exertion: Optional[int] = Field(None, ge=1, le=10)
    feeling: Optional[Feeling] = None
    notes: Optional[str] = None


class WorkoutRecordCreate(WorkoutRecordBase):
    """创建运动记录"""
    # 时间序列数据（可选，用于绘图）
    heart_rate_data: Optional[List[HeartRatePoint]] = None
    pace_data: Optional[List[PacePoint]] = None
    elevation_data: Optional[List[ElevationPoint]] = None


class WorkoutRecordUpdate(BaseModel):
    """更新运动记录"""
    workout_name: Optional[str] = None
    perceived_exertion: Optional[int] = Field(None, ge=1, le=10)
    feeling: Optional[Feeling] = None
    notes: Optional[str] = None


class WorkoutRecordResponse(WorkoutRecordBase):
    """运动记录响应"""
    id: int
    user_id: int
    source: str
    external_id: Optional[str] = None
    ai_analysis: Optional[str] = None
    heart_rate_data: Optional[str] = None
    pace_data: Optional[str] = None
    elevation_data: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class WorkoutSummary(BaseModel):
    """运动摘要（用于列表展示）"""
    id: int
    workout_date: date
    workout_type: str
    workout_name: Optional[str]
    duration_seconds: Optional[int]
    distance_meters: Optional[float]
    avg_heart_rate: Optional[int]
    calories: Optional[int]
    feeling: Optional[str]
    has_ai_analysis: bool


class WorkoutStats(BaseModel):
    """运动统计"""
    total_workouts: int
    total_duration_minutes: int
    total_distance_km: float
    total_calories: int
    avg_duration_minutes: float
    avg_distance_km: float
    workouts_by_type: dict
    recent_trend: str  # improving, stable, declining


class HeartRateZoneDistribution(BaseModel):
    """心率区间分布"""
    zone_1_percent: float  # 热身区 (50-60% max HR)
    zone_2_percent: float  # 燃脂区 (60-70%)
    zone_3_percent: float  # 有氧区 (70-80%)
    zone_4_percent: float  # 阈值区 (80-90%)
    zone_5_percent: float  # 极限区 (90-100%)


class WorkoutAnalysisRequest(BaseModel):
    """运动AI分析请求"""
    workout_id: int
    include_recommendations: bool = True
    compare_with_history: bool = True


class WorkoutAnalysisResponse(BaseModel):
    """运动AI分析响应"""
    workout_id: int
    analysis_date: datetime
    
    # 训练评估
    overall_rating: str  # excellent, good, moderate, needs_improvement
    intensity_assessment: str
    
    # 心率分析
    heart_rate_analysis: Optional[str]
    hr_zone_assessment: Optional[str]
    
    # 配速/速度分析
    pace_analysis: Optional[str]
    
    # 训练效果
    training_effect_summary: Optional[str]
    
    # 恢复建议
    recovery_recommendation: str
    next_workout_suggestion: str
    
    # 历史对比
    comparison_with_history: Optional[str]
    
    # 综合建议
    key_insights: List[str]
    improvement_tips: List[str]


class WorkoutChartData(BaseModel):
    """运动图表数据"""
    workout_id: int
    workout_type: str
    duration_seconds: int
    
    # 心率曲线
    heart_rate_timeline: Optional[List[HeartRatePoint]] = None
    heart_rate_zones: Optional[HeartRateZoneDistribution] = None
    
    # 配速曲线
    pace_timeline: Optional[List[PacePoint]] = None
    
    # 海拔曲线
    elevation_timeline: Optional[List[ElevationPoint]] = None
    
    # 汇总数据
    avg_heart_rate: Optional[int]
    max_heart_rate: Optional[int]
    avg_pace_display: Optional[str]  # "5:30/km"
    total_distance_km: Optional[float]
    calories: Optional[int]

