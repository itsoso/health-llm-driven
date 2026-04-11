"""健康咨询 Pydantic schemas"""
from datetime import date, datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------- item ----------

class ConsultationItemBase(BaseModel):
    item_type: str = Field(..., description="hypothesis|action|prediction|red_flag|note")
    item_code: Optional[str] = None
    priority: int = 3
    title: str
    content_markdown: Optional[str] = None
    meta: dict = {}
    due_date: Optional[date] = None


class ConsultationItemCreate(ConsultationItemBase):
    pass


class ConsultationItemUpdate(BaseModel):
    """用户/AI 对条目的状态变更"""
    status: Optional[str] = Field(None, description="pending|confirmed|refuted|completed|met|not_met 等")
    user_note: Optional[str] = None
    outcome: Optional[str] = None
    actual_value: Optional[str] = None
    meta_patch: Optional[dict] = None  # 增量合并到 meta


class ConsultationItemOut(ConsultationItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    consultation_id: int
    user_id: int
    status: str
    user_note: Optional[str] = None
    outcome: Optional[str] = None
    actual_value: Optional[str] = None
    verified_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ---------- consultation ----------

class HealthConsultationBase(BaseModel):
    title: str
    topic: Optional[str] = None
    consultation_type: str = "symptom_advisory"
    triggered_by: str = "manual"
    chief_complaint: Optional[str] = None
    input_snapshot: dict = {}
    rationale_markdown: str
    summary: Optional[str] = None
    verification_scheduled_at: Optional[date] = None
    generated_by: str = "manual"
    llm_model: Optional[str] = None


class HealthConsultationCreate(HealthConsultationBase):
    parent_consultation_id: Optional[int] = None
    items: List[ConsultationItemCreate] = []


class ConsultationListItem(BaseModel):
    """列表视图: 元信息 + 各类型统计"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    version: int
    title: str
    topic: Optional[str] = None
    consultation_type: str
    triggered_by: str
    status: str
    summary: Optional[str] = None
    verification_scheduled_at: Optional[date] = None
    created_at: datetime
    # 统计字段
    total_items: int = 0
    hypothesis_count: int = 0
    action_count: int = 0
    prediction_count: int = 0
    red_flag_count: int = 0
    pending_count: int = 0


class HealthConsultationDetail(HealthConsultationBase):
    """详情视图: 含完整 markdown + 全部 items"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    version: int
    status: str
    parent_consultation_id: Optional[int] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[ConsultationItemOut] = []
