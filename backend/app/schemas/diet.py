"""饮食记录模式"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, time
import enum


class MealType(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    EXTRA = "extra"


class DietRecordBase(BaseModel):
    """饮食记录基础"""
    record_date: date
    meal_type: MealType
    meal_time: Optional[time] = None
    food_items: str  # 食物列表，逗号分隔
    calories: Optional[int] = None  # 热量 (kcal)
    protein: Optional[float] = None  # 蛋白质 (g)
    carbs: Optional[float] = None  # 碳水化合物 (g)
    fat: Optional[float] = None  # 脂肪 (g)
    fiber: Optional[float] = None  # 膳食纤维 (g)
    notes: Optional[str] = None


class DietRecordCreate(DietRecordBase):
    """创建饮食记录"""
    user_id: Optional[int] = None  # 可选，后端会使用当前登录用户ID


class DietRecordUpdate(BaseModel):
    """更新饮食记录"""
    meal_type: Optional[MealType] = None
    meal_time: Optional[time] = None
    food_items: Optional[str] = None
    calories: Optional[int] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    notes: Optional[str] = None


class DietRecordResponse(DietRecordBase):
    """饮食记录响应"""
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DailyDietSummary(BaseModel):
    """每日饮食汇总"""
    record_date: date
    total_calories: int = 0
    total_protein: float = 0
    total_carbs: float = 0
    total_fat: float = 0
    total_fiber: float = 0
    meals_count: int = 0
    meals: List[DietRecordResponse] = []


class DietStats(BaseModel):
    """饮食统计"""
    average_daily_calories: Optional[float] = None
    average_daily_protein: Optional[float] = None
    average_daily_carbs: Optional[float] = None
    average_daily_fat: Optional[float] = None
    total_records: int = 0
    days_recorded: int = 0

