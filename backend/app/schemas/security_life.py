"""资产防御与布局 - Pydantic 校验模型"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


# ── Profile ──────────────────────────────────────────────

class ProfileBase(BaseModel):
    monthly_expense: Optional[float] = 0
    risk_tolerance: Optional[str] = "balanced"
    max_drawdown_percent: Optional[int] = 30
    has_kids_education: Optional[bool] = False
    has_elderly_medical: Optional[bool] = False
    has_investment_property: Optional[bool] = False
    property_net_asset_ratio: Optional[float] = None
    total_debt_ratio: Optional[float] = None
    notes: Optional[str] = None


class ProfileUpdate(ProfileBase):
    pass


class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Asset (两层资产) ────────────────────────────────────

class AssetBase(BaseModel):
    career_description: Optional[str] = None
    career_valuation: Optional[float] = 0
    career_note: Optional[str] = None
    second_layer_total: Optional[float] = 0


class AssetUpdate(AssetBase):
    pass


class PropertyBase(BaseModel):
    type: str = Field(..., description="自住核心区 / 投资非核心 / 西部避险")
    address: str
    valuation: float = 0
    plan_to_dispose: bool = False
    note: Optional[str] = None


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    type: Optional[str] = None
    address: Optional[str] = None
    valuation: Optional[float] = None
    plan_to_dispose: Optional[bool] = None
    note: Optional[str] = None


class PropertyResponse(PropertyBase):
    id: int
    user_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AssetResponse(AssetBase):
    id: int
    user_id: int
    properties: List[PropertyResponse] = []
    first_layer_total: Optional[float] = None
    second_layer_share: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Basket (资产篮子) ──────────────────────────────────

class BasketUpdate(BaseModel):
    amount: Optional[float] = None
    custom_min_percent: Optional[float] = None
    custom_max_percent: Optional[float] = None


class BasketResponse(BaseModel):
    id: int
    user_id: int
    basket_id: str
    amount: float = 0
    custom_min_percent: Optional[float] = None
    custom_max_percent: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class BasketListResponse(BaseModel):
    baskets: List[BasketResponse]
    total: float = 0


# ── Cash Layer (三层现金水库) ──────────────────────────

class CashLayerItem(BaseModel):
    layer: str = Field(..., description="T0 / T7 / T30")
    amount: float = 0
    institution: Optional[str] = None
    note: Optional[str] = None


class CashLayerUpdate(BaseModel):
    layers: List[CashLayerItem]


class CashLayerResponse(CashLayerItem):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


# ── Checklist (90天清单) ───────────────────────────────

class ChecklistItemBase(BaseModel):
    phase: str = Field(..., description="0-2 / 3-6 / 7-12")
    system_id: int = Field(..., ge=1, le=5, description="1-5 对应五大系统")
    label: str
    detail: Optional[str] = None


class ChecklistItemCreate(ChecklistItemBase):
    pass


class ChecklistItemUpdate(BaseModel):
    label: Optional[str] = None
    detail: Optional[str] = None
    phase: Optional[str] = None
    system_id: Optional[int] = None
    completed: Optional[bool] = None
    sort_order: Optional[int] = None


class ChecklistItemResponse(ChecklistItemBase):
    id: int
    user_id: int
    is_default: bool = False
    default_item_id: Optional[str] = None
    completed: bool = False
    completed_at: Optional[datetime] = None
    sort_order: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChecklistListResponse(BaseModel):
    items: List[ChecklistItemResponse]
    total: int = 0
    completed_count: int = 0
    phases: dict = {}  # phase → {total, completed}
    systems: dict = {}  # system_id → {total, completed}


# ── Red Line (三条红线) ────────────────────────────────

class RedLineUpdate(BaseModel):
    status: str = Field(..., description="met / unmet / partial")
    value_json: Optional[str] = None


class RedLineResponse(BaseModel):
    id: int
    user_id: int
    line_id: int
    status: str = "unmet"
    value_json: Optional[str] = None
    checked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Dashboard (总览) ───────────────────────────────────

class DashboardResponse(BaseModel):
    # 红线
    red_lines: List[RedLineResponse] = []
    # 资产
    first_layer_total: float = 0
    second_layer_total: float = 0
    second_layer_share: Optional[float] = None
    # 篮子
    basket_total: float = 0
    baskets: List[BasketResponse] = []
    # 现金
    cash_layers: List[CashLayerResponse] = []
    cash_runway_months: Optional[float] = None
    # 清单
    checklist_total: int = 0
    checklist_completed: int = 0
    # Profile
    monthly_expense: float = 0
