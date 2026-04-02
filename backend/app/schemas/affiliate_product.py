"""联盟产品 schemas"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AffiliateProductBase(BaseModel):
    name: str
    brand: Optional[str] = None
    image_url: Optional[str] = None
    supplement_name: str
    category: str = "basic"
    keywords: list[str] = []
    platform: str = "iherb"
    affiliate_url: str
    price_display: Optional[str] = None
    currency: str = "CNY"
    gene_tags: list[str] = []
    gene_description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    notes: Optional[str] = None


class AffiliateProductCreate(AffiliateProductBase):
    pass


class AffiliateProductUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None
    supplement_name: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[list[str]] = None
    platform: Optional[str] = None
    affiliate_url: Optional[str] = None
    price_display: Optional[str] = None
    currency: Optional[str] = None
    gene_tags: Optional[list[str]] = None
    gene_description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class AffiliateProductResponse(AffiliateProductBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductMatchResult(BaseModel):
    """匹配结果 — 产品 + 匹配分数 + 基因匹配标记"""
    id: int
    name: str
    brand: Optional[str] = None
    image_url: Optional[str] = None
    platform: str
    affiliate_url: str
    price_display: Optional[str] = None
    currency: str = "CNY"
    gene_match: bool = False
    gene_description: Optional[str] = None
    match_score: int = 0
