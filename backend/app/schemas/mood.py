"""情绪追踪 API Schemas"""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


# =====================================================
# 情绪记录 Schemas
# =====================================================

class MoodRecordBase(BaseModel):
    """情绪记录基础字段"""
    record_date: date = Field(..., description="记录日期")
    mood_score: int = Field(..., ge=1, le=5, description="情绪评分 1-5")
    mood_tags: List[str] = Field(default_factory=list, description="情绪标签")
    energy_level: Optional[int] = Field(None, ge=1, le=5, description="精力等级 1-5")
    stress_level: Optional[int] = Field(None, ge=1, le=5, description="压力等级 1-5")
    anxiety_level: Optional[int] = Field(None, ge=1, le=5, description="焦虑等级 1-5")
    sleep_quality: Optional[int] = Field(None, ge=1, le=5, description="睡眠质量 1-5")
    journal: Optional[str] = Field(None, max_length=2000, description="情绪日记")
    triggers: List[str] = Field(default_factory=list, description="触发因素")
    coping_methods: List[str] = Field(default_factory=list, description="应对方式")


class MoodRecordCreate(MoodRecordBase):
    """创建情绪记录"""
    pass


class MoodRecordUpdate(BaseModel):
    """更新情绪记录"""
    mood_score: Optional[int] = Field(None, ge=1, le=5)
    mood_tags: Optional[List[str]] = None
    energy_level: Optional[int] = Field(None, ge=1, le=5)
    stress_level: Optional[int] = Field(None, ge=1, le=5)
    anxiety_level: Optional[int] = Field(None, ge=1, le=5)
    sleep_quality: Optional[int] = Field(None, ge=1, le=5)
    journal: Optional[str] = Field(None, max_length=2000)
    triggers: Optional[List[str]] = None
    coping_methods: Optional[List[str]] = None


class MoodRecordResponse(MoodRecordBase):
    """情绪记录响应"""
    id: int
    user_id: int
    record_time: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# 情绪统计 Schemas
# =====================================================

class MoodDailyTrend(BaseModel):
    """每日情绪趋势"""
    date: date
    mood_score: float
    energy_level: Optional[float] = None
    stress_level: Optional[float] = None
    anxiety_level: Optional[float] = None
    record_count: int = 0


class MoodStats(BaseModel):
    """情绪统计"""
    # 基础统计
    total_records: int = 0
    avg_mood_score: Optional[float] = None
    avg_energy_level: Optional[float] = None
    avg_stress_level: Optional[float] = None
    avg_anxiety_level: Optional[float] = None

    # 情绪分布 (score -> count)
    mood_distribution: Dict[int, int] = Field(
        default_factory=dict, description="情绪评分分布 {1: 2, 2: 3, ...}"
    )

    # 最常见的情绪标签 (tag -> count)
    top_mood_tags: Dict[str, int] = Field(
        default_factory=dict, description="情绪标签频率"
    )

    # 最常见的触发因素
    top_triggers: Dict[str, int] = Field(
        default_factory=dict, description="触发因素频率"
    )

    # 最常用的应对方式
    top_coping_methods: Dict[str, int] = Field(
        default_factory=dict, description="应对方式频率"
    )

    # 趋势（近7天）
    daily_trend: List[MoodDailyTrend] = Field(
        default_factory=list, description="每日趋势"
    )

    # 情绪与其他指标的关联
    mood_sleep_correlation: Optional[float] = Field(
        None, description="情绪与睡眠质量的相关系数"
    )
    mood_energy_correlation: Optional[float] = Field(
        None, description="情绪与精力的相关系数"
    )


class MoodCalendar(BaseModel):
    """情绪日历"""
    year: int
    month: int
    days: Dict[int, Dict[str, Any]] = Field(
        default_factory=dict,
        description="day -> {mood_score, mood_tags, has_journal}"
    )
    total_days: int = 0
    recorded_days: int = 0
    avg_mood_score: Optional[float] = None
