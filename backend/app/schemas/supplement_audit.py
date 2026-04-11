"""补剂审计 Pydantic schemas"""
from datetime import date, datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------- item ----------

class SupplementAuditItemBase(BaseModel):
    action_type: str = Field(..., description="keep|add|upgrade|remove|monitor|warning")
    priority: int = 3
    title: str
    product_id: Optional[int] = None
    supplement_definition_id: Optional[int] = None
    target_metric: Optional[str] = None
    rationale_markdown: str
    evidence_refs: List[Any] = []
    warnings: List[Any] = []


class SupplementAuditItemCreate(SupplementAuditItemBase):
    pass


class SupplementAuditItemUpdate(BaseModel):
    """用户对单条 item 的状态变更：accept/reject/complete"""
    status: Optional[str] = Field(None, description="pending|accepted|rejected|completed")
    user_note: Optional[str] = None
    rejected_reason: Optional[str] = None


class SupplementAuditItemOut(SupplementAuditItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: int
    user_id: int
    status: str
    user_note: Optional[str] = None
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ---------- audit ----------

class SupplementAuditBase(BaseModel):
    title: str
    triggered_by: str = Field("manual", description="manual|new_exam|new_gene|scheduled|changed_conditions")
    data_period_start: Optional[date] = None
    data_period_end: Optional[date] = None
    rationale_markdown: str
    summary: Optional[str] = None
    input_snapshot: dict = {}
    next_review_at: Optional[date] = None
    generated_by: str = "manual"
    llm_model: Optional[str] = None


class SupplementAuditCreate(SupplementAuditBase):
    items: List[SupplementAuditItemCreate] = []
    parent_audit_id: Optional[int] = None


class SupplementAuditListItem(BaseModel):
    """列表视图：不带完整 markdown，只返回元信息 + item 统计"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    version: int
    title: str
    status: str
    triggered_by: str
    summary: Optional[str] = None
    data_period_start: Optional[date] = None
    data_period_end: Optional[date] = None
    next_review_at: Optional[date] = None
    created_at: datetime
    # 统计字段，service 层填充
    items_count: int = 0
    pending_count: int = 0


class SupplementAuditDetail(SupplementAuditBase):
    """详情视图：完整 markdown + items"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    version: int
    status: str
    parent_audit_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[SupplementAuditItemOut] = []
