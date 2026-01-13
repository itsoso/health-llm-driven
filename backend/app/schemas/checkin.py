"""
打卡系统 API Schemas - executor.life
"""
from datetime import date, datetime, time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# =====================================================
# 打卡模板 Schemas
# =====================================================

class CheckinTemplateBase(BaseModel):
    """打卡模板基础字段"""
    name: str = Field(..., max_length=100, description="打卡项目名称")
    description: Optional[str] = Field(None, description="描述")
    icon: str = Field("✅", description="图标emoji")
    color: str = Field("#4f46e5", description="主题色")
    category: str = Field(..., description="分类: exercise/health/habit/medicine/custom")
    
    # 计量配置
    unit: str = Field("次", description="单位")
    default_target: float = Field(1, ge=0, description="默认目标值")
    min_value: float = Field(0, ge=0, description="最小值")
    max_value: Optional[float] = Field(None, description="最大值")
    step_value: float = Field(1, ge=0.1, description="步进值")
    
    # 提醒配置
    reminder_enabled: bool = Field(False, description="是否开启提醒")
    reminder_time: Optional[str] = Field(None, description="提醒时间 HH:MM")
    reminder_days: List[int] = Field(default_factory=list, description="提醒日期 [1-7]")
    
    # 频率配置
    frequency: str = Field("daily", description="频率: daily/weekly/monthly")
    frequency_target: int = Field(1, ge=1, description="每周期目标次数")


class CheckinTemplateCreate(CheckinTemplateBase):
    """创建打卡模板"""
    pass


class CheckinTemplateUpdate(BaseModel):
    """更新打卡模板"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    default_target: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_value: Optional[float] = None
    reminder_enabled: Optional[bool] = None
    reminder_time: Optional[str] = None
    reminder_days: Optional[List[int]] = None
    frequency: Optional[str] = None
    frequency_target: Optional[int] = None
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None
    sort_order: Optional[int] = None


class CheckinTemplateResponse(CheckinTemplateBase):
    """打卡模板响应"""
    id: int
    user_id: int
    
    # 统计数据
    total_checkins: int = 0
    total_value: float = 0
    current_streak: int = 0
    best_streak: int = 0
    last_checkin_date: Optional[date] = None
    
    # 状态
    is_active: bool = True
    is_archived: bool = False
    sort_order: int = 0
    
    # 时间戳
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # 计算字段
    today_completed: bool = Field(False, description="今日是否已完成")
    completion_rate_week: Optional[float] = Field(None, description="本周完成率")
    completion_rate_month: Optional[float] = Field(None, description="本月完成率")
    
    class Config:
        from_attributes = True


class CheckinTemplateListResponse(BaseModel):
    """打卡模板列表响应"""
    templates: List[CheckinTemplateResponse]
    total: int
    categories: Dict[str, int]  # 各分类数量统计


# =====================================================
# 打卡记录 Schemas
# =====================================================

class CheckinRecordBase(BaseModel):
    """打卡记录基础字段"""
    template_id: int = Field(..., description="打卡模板ID")
    checkin_date: date = Field(..., description="打卡日期")
    value: float = Field(..., ge=0, description="完成量")
    target: Optional[float] = Field(None, description="当日目标")
    
    # 附加数据
    duration_seconds: Optional[int] = Field(None, ge=0, description="持续时间(秒)")
    calories_burned: Optional[float] = Field(None, ge=0, description="消耗卡路里")
    heart_rate_avg: Optional[int] = Field(None, ge=30, le=250, description="平均心率")
    
    # 主观感受
    difficulty: Optional[str] = Field(None, description="难度: easy/normal/hard/very_hard")
    mood_before: Optional[str] = Field(None, description="打卡前心情")
    mood_after: Optional[str] = Field(None, description="打卡后心情")
    energy_level: Optional[int] = Field(None, ge=1, le=10, description="精力等级")
    
    # 备注
    notes: Optional[str] = Field(None, description="备注")
    tags: List[str] = Field(default_factory=list, description="标签")
    
    # 位置
    location: Optional[str] = Field(None, description="位置")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")


class CheckinRecordCreate(CheckinRecordBase):
    """创建打卡记录"""
    pass


class CheckinRecordQuick(BaseModel):
    """快速打卡（简化版）"""
    template_id: int = Field(..., description="打卡模板ID")
    value: Optional[float] = Field(None, description="完成量，为空则使用默认目标")
    notes: Optional[str] = Field(None, description="备注")


class CheckinRecordUpdate(BaseModel):
    """更新打卡记录"""
    value: Optional[float] = None
    target: Optional[float] = None
    duration_seconds: Optional[int] = None
    calories_burned: Optional[float] = None
    heart_rate_avg: Optional[int] = None
    difficulty: Optional[str] = None
    mood_before: Optional[str] = None
    mood_after: Optional[str] = None
    energy_level: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class CheckinRecordResponse(CheckinRecordBase):
    """打卡记录响应"""
    id: int
    user_id: int
    checkin_time: datetime
    completion_rate: Optional[float] = None
    photos: List[str] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # 关联数据
    template_name: Optional[str] = Field(None, description="模板名称")
    template_icon: Optional[str] = Field(None, description="模板图标")
    template_category: Optional[str] = Field(None, description="模板分类")
    
    class Config:
        from_attributes = True


# =====================================================
# 打卡统计 Schemas
# =====================================================

class CheckinDailySummary(BaseModel):
    """每日打卡汇总"""
    date: date
    total_templates: int = Field(0, description="打卡项目总数")
    completed_templates: int = Field(0, description="已完成项目数")
    completion_rate: float = Field(0, description="完成率")
    records: List[CheckinRecordResponse] = []


class CheckinWeeklySummary(BaseModel):
    """每周打卡汇总"""
    week_start: date
    week_end: date
    daily_summaries: List[CheckinDailySummary]
    total_checkins: int
    average_completion_rate: float
    best_day: Optional[date] = None
    missed_days: int = 0


class CheckinStats(BaseModel):
    """打卡统计"""
    # 总体统计
    total_checkins: int = 0
    total_templates: int = 0
    active_templates: int = 0
    
    # 连续打卡
    current_streak: int = 0
    best_streak: int = 0
    
    # 时间统计
    checkins_today: int = 0
    checkins_this_week: int = 0
    checkins_this_month: int = 0
    
    # 完成率
    completion_rate_today: float = 0
    completion_rate_week: float = 0
    completion_rate_month: float = 0
    
    # 分类统计
    by_category: Dict[str, Dict[str, Any]] = {}
    
    # 趋势数据（最近7天）
    daily_trend: List[Dict[str, Any]] = []


class CheckinCalendar(BaseModel):
    """打卡日历"""
    year: int
    month: int
    days: Dict[int, Dict[str, Any]]  # day -> {completed: bool, rate: float, records: int}
    total_days: int
    completed_days: int
    completion_rate: float
