"""补剂管理模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Boolean, Time, Numeric, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SupplementProduct(Base):
    """公共补剂产品库 — 管理员维护，所有用户共享"""
    __tablename__ = "supplement_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # 产品名
    brand = Column(String(100), nullable=False)  # 品牌
    category = Column(String(50))  # vitamin/mineral/antioxidant/amino/herb/other
    description = Column(Text)  # 产品描述

    # 规格
    serving_size = Column(String(100))  # "2 Vegetarian Capsules"
    servings_per_container = Column(Integer)  # 30
    container_count = Column(Integer)  # 60

    # 成分表 JSON
    ingredients = Column(JSON, default=list)
    # [{"name":"Vitamin B6","form":"P-5-P","amount":"10mg","daily_value_pct":588}]

    # 价格
    price_cny = Column(Numeric(10, 2))  # 人民币价格
    price_per_serving = Column(Numeric(10, 2))  # 每份价格
    currency = Column(String(10), default="CNY")

    # 购买渠道
    purchase_url = Column(String(500))
    platform = Column(String(50), default="iherb")  # iherb/amazon/jd
    image_url = Column(String(500))

    # 产品属性
    certifications = Column(JSON, default=list)  # ["Non-GMO","Gluten Free"]
    capsule_type = Column(String(30))  # vegetarian/gelatin/softgel/liquid

    # 服用指导
    usage_advice = Column(Text)
    precautions = Column(Text)

    # 深度分析（AI 洞察：机制/独特价值/适用人群/避坑/搭配）
    analysis = Column(Text)

    # 基因 & 健康关联
    gene_relevance = Column(JSON, default=list)
    # [{"gene":"MTHFR","genotype":"CT/TT","relevance":"需要活性叶酸5-MTHF"}]
    health_tags = Column(JSON, default=list)  # ["睡眠","压力","甲基化"]

    # 评分
    rating = Column(Numeric(3, 1))  # iHerb 评分
    review_count = Column(Integer)

    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SupplementDefinition(Base):
    """补剂定义 - 用户的补剂列表"""
    __tablename__ = "supplement_definitions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("supplement_products.id"), nullable=True)  # 关联产品库

    name = Column(String, nullable=False)  # 补剂名称
    dosage = Column(String)  # 剂量（如：100mg, 5000IU）
    timing = Column(String)  # 服用时间（morning/noon/evening/bedtime）
    category = Column(String)  # 分类（维生素/矿物质/抗氧化/中药等）

    description = Column(Text)  # 描述/备注
    is_active = Column(Boolean, default=True)  # 是否启用
    sort_order = Column(Integer, default=0)  # 排序顺序

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="supplement_definitions")
    product = relationship("SupplementProduct", lazy="joined")
    records = relationship("SupplementRecord", back_populates="supplement", cascade="all, delete-orphan")


class SupplementRecord(Base):
    """补剂打卡记录"""
    __tablename__ = "supplement_records"
    
    id = Column(Integer, primary_key=True, index=True)
    supplement_id = Column(Integer, ForeignKey("supplement_definitions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    taken = Column(Boolean, default=False)  # 是否已服用
    taken_time = Column(Time)  # 实际服用时间
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    supplement = relationship("SupplementDefinition", back_populates="records")
    user = relationship("User", backref="supplement_records")

