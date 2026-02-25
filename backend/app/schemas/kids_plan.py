"""Kids每日计划 schemas"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class PlanItemSchema(BaseModel):
    id: str
    emoji: str
    text: str
    done: bool = False
    startTime: Optional[str] = None
    endTime: Optional[str] = None


class KidsPlanSaveRequest(BaseModel):
    items: List[PlanItemSchema]


class KidsPlanResponse(BaseModel):
    plan_date: date
    items: List[PlanItemSchema]
    awarded_tier: int = 0
    points_awarded: int = 0  # 本次请求新增的积分
    total_kids_points: int = 0  # 用户当前总积分

    class Config:
        from_attributes = True


class KidsPlanCopyRequest(BaseModel):
    from_date: date
    to_date: date
