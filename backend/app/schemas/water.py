"""饮水追踪模式"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, time


class WaterRecordBase(BaseModel):
    """饮水记录基础"""
    record_date: date
    amount: int  # 饮水量 (ml)
    drink_time: Optional[time] = None
    drink_type: Optional[str] = None  # 饮品类型：水、茶、咖啡等
    notes: Optional[str] = None


class WaterRecordCreate(WaterRecordBase):
    """创建饮水记录"""
    user_id: int


class WaterRecordUpdate(BaseModel):
    """更新饮水记录"""
    amount: Optional[int] = None
    drink_time: Optional[time] = None
    drink_type: Optional[str] = None
    notes: Optional[str] = None


class WaterRecordResponse(WaterRecordBase):
    """饮水记录响应"""
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DailyWaterSummary(BaseModel):
    """每日饮水汇总"""
    record_date: date
    total_amount: int = 0  # 总饮水量 (ml)
    target_amount: int = 2000  # 目标饮水量 (ml)
    progress_percentage: float = 0  # 完成百分比
    records_count: int = 0
    records: List[WaterRecordResponse] = []


class WaterStats(BaseModel):
    """饮水统计"""
    average_daily_amount: Optional[float] = None
    highest_daily_amount: Optional[int] = None
    lowest_daily_amount: Optional[int] = None
    total_records: int = 0
    days_recorded: int = 0
    days_reached_target: int = 0  # 达标天数
    target_percentage: float = 0  # 达标率

