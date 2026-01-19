"""
复盘相关的 Pydantic Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from enum import Enum


class ReviewPeriodType(str, Enum):
    """复盘周期类型"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# ========== 每日复盘 ==========

class DailyReviewBase(BaseModel):
    """每日复盘基础字段"""
    review_date: date
    
    # 用户手动输入
    mood_score: Optional[int] = Field(None, ge=1, le=5, description="心情评分1-5")
    energy_score: Optional[int] = Field(None, ge=1, le=5, description="精力评分1-5")
    productivity_score: Optional[int] = Field(None, ge=1, le=5, description="效率评分1-5")
    
    highlights: Optional[str] = Field(None, description="今日亮点/成就")
    challenges: Optional[str] = Field(None, description="今日挑战/困难")
    learnings: Optional[str] = Field(None, description="今日收获/学习")
    gratitude: Optional[str] = Field(None, description="感恩的事")
    tomorrow_plan: Optional[str] = Field(None, description="明日计划")
    summary: Optional[str] = Field(None, description="用户手写总结")


class DailyReviewCreate(DailyReviewBase):
    """创建每日复盘"""
    pass


class DailyReviewUpdate(BaseModel):
    """更新每日复盘"""
    mood_score: Optional[int] = Field(None, ge=1, le=5)
    energy_score: Optional[int] = Field(None, ge=1, le=5)
    productivity_score: Optional[int] = Field(None, ge=1, le=5)
    
    highlights: Optional[str] = None
    challenges: Optional[str] = None
    learnings: Optional[str] = None
    gratitude: Optional[str] = None
    tomorrow_plan: Optional[str] = None
    summary: Optional[str] = None
    is_completed: Optional[bool] = None


class DailyReviewResponse(DailyReviewBase):
    """每日复盘响应"""
    id: int
    user_id: int
    
    # 自动汇总的健康数据
    sleep_score: Optional[int] = None
    sleep_duration_hours: Optional[float] = None
    sleep_quality: Optional[str] = None
    
    workout_count: int = 0
    workout_duration_minutes: int = 0
    workout_calories: int = 0
    workout_types: Optional[str] = None
    
    nap_count: int = 0
    nap_duration_minutes: int = 0
    
    steps: int = 0
    active_calories: int = 0
    
    meals_count: int = 0
    total_calories_in: int = 0
    total_protein: float = 0
    total_carbs: float = 0
    total_fat: float = 0
    
    water_intake_ml: int = 0
    water_goal_met: bool = False
    
    nasal_wash_count: int = 0
    nasal_wash_done: bool = False
    
    checkin_completed: int = 0
    checkin_total: int = 0
    checkin_items: Optional[str] = None
    
    supplements_taken: int = 0
    supplements_list: Optional[str] = None
    
    body_battery_high: Optional[int] = None
    body_battery_low: Optional[int] = None
    stress_avg: Optional[int] = None
    resting_hr: Optional[int] = None
    
    ai_summary: Optional[str] = None
    is_completed: bool = False
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ========== 周期复盘 ==========

class PeriodReviewBase(BaseModel):
    """周期复盘基础字段"""
    period_type: ReviewPeriodType
    start_date: date
    end_date: date
    
    # 用户输入
    achievements: Optional[str] = Field(None, description="本周期成就")
    challenges: Optional[str] = Field(None, description="本周期挑战")
    learnings: Optional[str] = Field(None, description="本周期收获")
    goals_review: Optional[str] = Field(None, description="目标回顾")
    next_period_goals: Optional[str] = Field(None, description="下周期目标")
    summary: Optional[str] = Field(None, description="用户手写总结")


class PeriodReviewCreate(PeriodReviewBase):
    """创建周期复盘"""
    pass


class PeriodReviewUpdate(BaseModel):
    """更新周期复盘"""
    achievements: Optional[str] = None
    challenges: Optional[str] = None
    learnings: Optional[str] = None
    goals_review: Optional[str] = None
    next_period_goals: Optional[str] = None
    summary: Optional[str] = None
    is_completed: Optional[bool] = None


class PeriodReviewResponse(PeriodReviewBase):
    """周期复盘响应"""
    id: int
    user_id: int
    period_label: Optional[str] = None
    
    # 汇总统计
    avg_sleep_score: Optional[float] = None
    avg_sleep_duration: Optional[float] = None
    best_sleep_date: Optional[date] = None
    worst_sleep_date: Optional[date] = None
    
    total_workouts: int = 0
    total_workout_minutes: int = 0
    total_workout_calories: int = 0
    workout_days: int = 0
    
    total_steps: int = 0
    avg_steps: int = 0
    best_steps_date: Optional[date] = None
    
    avg_calories_in: int = 0
    avg_protein: float = 0
    
    avg_water_intake: int = 0
    water_goal_days: int = 0
    
    avg_checkin_rate: Optional[float] = None
    perfect_days: int = 0
    
    review_days: int = 0
    total_days: int = 0
    
    ai_summary: Optional[str] = None
    is_completed: bool = False
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ========== 复盘数据汇总 ==========

class DailyHealthSummary(BaseModel):
    """每日健康数据汇总（用于复盘展示）"""
    date: date
    
    # 睡眠
    sleep_score: Optional[int] = None
    sleep_duration_hours: Optional[float] = None
    
    # 运动
    workouts: List[Dict[str, Any]] = []
    total_workout_minutes: int = 0
    total_workout_calories: int = 0
    
    # 小睡
    naps: List[Dict[str, Any]] = []
    
    # 步数
    steps: int = 0
    active_calories: int = 0
    
    # 饮食
    meals: List[Dict[str, Any]] = []
    total_calories: int = 0
    total_protein: float = 0
    total_carbs: float = 0
    total_fat: float = 0
    
    # 饮水
    water_intake_ml: int = 0
    water_records: List[Dict[str, Any]] = []
    
    # 洗鼻
    nasal_wash_done: bool = False
    nasal_wash_count: int = 0
    
    # 打卡
    checkins: List[Dict[str, Any]] = []
    checkin_completed: int = 0
    checkin_total: int = 0
    
    # 补剂
    supplements: List[Dict[str, Any]] = []
    
    # 身体状态
    body_battery_high: Optional[int] = None
    body_battery_low: Optional[int] = None
    stress_avg: Optional[int] = None
    resting_hr: Optional[int] = None


class ReviewListItem(BaseModel):
    """复盘列表项"""
    id: int
    review_date: date
    is_completed: bool
    mood_score: Optional[int] = None
    summary_preview: Optional[str] = None  # 总结预览（前50字）
    
    class Config:
        from_attributes = True
