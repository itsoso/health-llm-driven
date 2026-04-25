"""补剂管理 Schemas"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import date, time, datetime
from decimal import Decimal


# ========== 公共产品库 ==========
class SupplementProductBase(BaseModel):
    name: str
    brand: str
    category: Optional[str] = None
    description: Optional[str] = None
    serving_size: Optional[str] = None
    servings_per_container: Optional[int] = None
    container_count: Optional[int] = None
    ingredients: Optional[List[Dict[str, Any]]] = None
    price_cny: Optional[Decimal] = None
    price_per_serving: Optional[Decimal] = None
    currency: str = "CNY"
    purchase_url: Optional[str] = None
    platform: str = "iherb"
    image_url: Optional[str] = None
    certifications: Optional[List[str]] = None
    capsule_type: Optional[str] = None
    usage_advice: Optional[str] = None
    precautions: Optional[str] = None
    gene_relevance: Optional[List[Dict[str, Any]]] = None
    health_tags: Optional[List[str]] = None
    rating: Optional[Decimal] = None
    review_count: Optional[int] = None
    is_active: bool = True


class SupplementProductCreate(SupplementProductBase):
    pass


class SupplementProductUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    serving_size: Optional[str] = None
    servings_per_container: Optional[int] = None
    container_count: Optional[int] = None
    ingredients: Optional[List[Dict[str, Any]]] = None
    price_cny: Optional[Decimal] = None
    price_per_serving: Optional[Decimal] = None
    purchase_url: Optional[str] = None
    platform: Optional[str] = None
    image_url: Optional[str] = None
    certifications: Optional[List[str]] = None
    capsule_type: Optional[str] = None
    usage_advice: Optional[str] = None
    precautions: Optional[str] = None
    gene_relevance: Optional[List[Dict[str, Any]]] = None
    health_tags: Optional[List[str]] = None
    rating: Optional[Decimal] = None
    review_count: Optional[int] = None
    is_active: Optional[bool] = None


class SupplementProductResponse(SupplementProductBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class SupplementProductListResponse(BaseModel):
    items: List[SupplementProductResponse]
    total: int


# ========== 补剂定义 ==========
class SupplementDefinitionBase(BaseModel):
    name: str
    dosage: Optional[str] = None
    timing: Optional[str] = None  # morning/noon/evening/bedtime
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class SupplementDefinitionCreate(SupplementDefinitionBase):
    user_id: Optional[int] = None
    product_id: Optional[int] = None  # 关联产品库


class SupplementDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    timing: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    product_id: Optional[int] = None  # 关联产品库


class SupplementDefinitionResponse(SupplementDefinitionBase):
    id: int
    user_id: int
    product_id: Optional[int] = None
    product: Optional[SupplementProductResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# 补剂打卡记录
class SupplementRecordBase(BaseModel):
    record_date: date
    taken: bool = False
    taken_time: Optional[time] = None
    notes: Optional[str] = None


class SupplementRecordCreate(SupplementRecordBase):
    supplement_id: int
    user_id: int


class SupplementRecordResponse(SupplementRecordBase):
    id: int
    supplement_id: int
    user_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# 批量打卡请求
class SupplementBatchCheckin(BaseModel):
    user_id: Optional[int] = None  # 可选，如果不提供则使用当前登录用户
    record_date: date
    checkins: List[dict]  # [{"supplement_id": 1, "taken": true}, ...]


# 带记录的补剂响应
class SupplementWithRecord(BaseModel):
    supplement: SupplementDefinitionResponse
    record: Optional[SupplementRecordResponse] = None
