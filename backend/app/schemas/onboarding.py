"""新手引导请求/响应模型"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# 主目标白名单 — 给前端单选用 (跟 user_profile.primary_goal 对应)
PRIMARY_GOALS = ['weight_loss', 'glucose', 'blood_pressure', 'sleep', 'hrv', 'rhinitis', 'general']


class ProfileData(BaseModel):
    """已有的用户档案数据"""
    height_cm: Optional[float] = None
    current_weight_kg: Optional[float] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    target_steps: int = 8000
    target_sleep_hours: float = 7.5
    target_water_ml: int = 2000
    target_exercise_minutes: int = 30
    primary_goal: Optional[str] = None


class OnboardingStatusResponse(BaseModel):
    onboarding_completed: bool
    has_profile: bool
    has_health_goals: bool
    has_checkin_templates: bool
    profile_data: Optional[ProfileData] = None


class OnboardingStep1Request(BaseModel):
    """基本信息"""
    height_cm: Optional[float] = Field(None, ge=50, le=250)
    current_weight_kg: Optional[float] = Field(None, ge=20, le=300)
    gender: Optional[str] = None
    birth_date: Optional[str] = None  # YYYY-MM-DD


class OnboardingStep2Request(BaseModel):
    """健康目标"""
    target_steps: int = Field(default=8000, ge=1000, le=100000)
    target_sleep_hours: float = Field(default=7.5, ge=4, le=12)
    target_water_ml: int = Field(default=2000, ge=500, le=10000)
    target_exercise_minutes: int = Field(default=30, ge=10, le=300)


class OnboardingStep5Request(BaseModel):
    """主目标 (2026-05-14): 用户最想改善的 1 件事."""
    primary_goal: Literal['weight_loss', 'glucose', 'blood_pressure', 'sleep', 'hrv', 'rhinitis', 'general']


class OnboardingCompleteRequest(BaseModel):
    """完成引导"""
    init_default_templates: bool = True
    selected_template_names: Optional[List[str]] = None
