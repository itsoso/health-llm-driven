"""联盟产品目录模型"""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class AffiliateProduct(Base):
    """联盟产品 — 管理员维护的全局产品目录"""
    __tablename__ = "affiliate_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    brand = Column(String(100))
    image_url = Column(String(500))

    # 匹配字段
    supplement_name = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=False, default="basic")
    keywords = Column(JSON, default=list)

    # 联盟链接
    platform = Column(String(50), nullable=False, default="iherb")
    affiliate_url = Column(String(500), nullable=False)
    price_display = Column(String(50))
    currency = Column(String(10), default="CNY")

    # 基因标签
    gene_tags = Column(JSON, default=list)
    gene_description = Column(String(200))

    # 管理
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
