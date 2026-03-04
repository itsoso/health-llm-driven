"""
行程记录 API Schemas
"""
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


# =====================================================
# 行程明细 Schemas
# =====================================================

class TripItemBase(BaseModel):
    """行程明细基础字段"""
    item_date: date = Field(..., description="日期")
    item_order: int = Field(0, description="当日排序")
    item_type: str = Field(..., description="类型: flight/train/bus/taxi/hotel/activity/other")
    title: str = Field(..., max_length=200, description="标题")

    # 交通相关
    origin: Optional[str] = Field(None, max_length=100, description="出发地")
    destination: Optional[str] = Field(None, max_length=100, description="目的地")
    departure_time: Optional[str] = Field(None, max_length=10, description="出发时间，如09:30")
    arrival_time: Optional[str] = Field(None, max_length=10, description="到达时间，如12:40")
    transport_number: Optional[str] = Field(None, max_length=50, description="航班号/车次")
    carrier: Optional[str] = Field(None, max_length=100, description="承运方")
    departure_terminal: Optional[str] = Field(None, max_length=20, description="出发航站楼")
    arrival_terminal: Optional[str] = Field(None, max_length=20, description="到达航站楼")

    # 活动/酒店相关
    location: Optional[str] = Field(None, max_length=200, description="地点")
    description: Optional[str] = Field(None, description="描述")


class TripItemCreate(TripItemBase):
    """创建行程明细"""
    pass


class TripItemUpdate(BaseModel):
    """更新行程明细"""
    item_date: Optional[date] = None
    item_order: Optional[int] = None
    item_type: Optional[str] = None
    title: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    transport_number: Optional[str] = None
    carrier: Optional[str] = None
    departure_terminal: Optional[str] = None
    arrival_terminal: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class TripItemResponse(TripItemBase):
    """行程明细响应"""
    id: int
    trip_id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# 行程 Schemas
# =====================================================

class TripBase(BaseModel):
    """行程基础字段"""
    trip_name: str = Field(..., max_length=200, description="行程名称")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    destination: Optional[str] = Field(None, max_length=200, description="主要目的地")
    notes: Optional[str] = Field(None, description="备注")


class TripCreate(TripBase):
    """创建行程（可携带明细）"""
    items: Optional[List[TripItemCreate]] = Field(None, description="行程明细列表")


class TripUpdate(BaseModel):
    """更新行程"""
    trip_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    destination: Optional[str] = None
    notes: Optional[str] = None


class TripListResponse(TripBase):
    """行程列表响应（不含明细）"""
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TripResponse(TripBase):
    """行程详情响应（含明细）"""
    id: int
    user_id: int
    items: List[TripItemResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
