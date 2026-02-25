"""资产防御与布局 - 数据模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SecurityLifeProfile(Base):
    """用户资产防御配置"""
    __tablename__ = "security_life_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    monthly_expense = Column(Float, default=0)  # 家庭月支出
    risk_tolerance = Column(String(20), default="balanced")  # conservative/balanced/aggressive
    max_drawdown_percent = Column(Integer, default=30)  # 最大可承受回撤 %
    has_kids_education = Column(Boolean, default=False)  # 有孩子教育需求
    has_elderly_medical = Column(Boolean, default=False)  # 有老人医疗需求
    has_investment_property = Column(Boolean, default=False)  # 有投资房
    property_net_asset_ratio = Column(Float, nullable=True)  # 房产占净资产比例 %
    total_debt_ratio = Column(Float, nullable=True)  # 总负债率 %
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="security_life_profile")


class SecurityLifeAsset(Base):
    """两层资产（职业/股权 + 可投资金融资产）"""
    __tablename__ = "security_life_assets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    # 第一层：职业/股权
    career_description = Column(String(500), nullable=True)
    career_valuation = Column(Float, default=0)
    career_note = Column(Text, nullable=True)

    # 第二层：可投资金融资产
    second_layer_total = Column(Float, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="security_life_asset")
    properties = relationship("SecurityLifeProperty", back_populates="asset", cascade="all, delete-orphan")


class SecurityLifeProperty(Base):
    """房产条目"""
    __tablename__ = "security_life_properties"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("security_life_assets.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    type = Column(String(20), nullable=False)  # 自住核心区 / 投资非核心 / 西部避险
    address = Column(String(500), nullable=False)
    valuation = Column(Float, nullable=False, default=0)
    plan_to_dispose = Column(Boolean, default=False)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    asset = relationship("SecurityLifeAsset", back_populates="properties")


class SecurityLifeBasket(Base):
    """资产篮子（四大篮子）"""
    __tablename__ = "security_life_baskets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    basket_id = Column(String(30), nullable=False)  # survival_cash / global_growth / stable_anchor / extreme_hedge
    amount = Column(Float, default=0)
    custom_min_percent = Column(Float, nullable=True)  # 用户自定义目标下限
    custom_max_percent = Column(Float, nullable=True)  # 用户自定义目标上限

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="security_life_baskets")

    __table_args__ = (
        # 每个用户每种篮子只有一条记录
        {"sqlite_autoincrement": True},
    )


class SecurityLifeCashLayer(Base):
    """三层现金水库"""
    __tablename__ = "security_life_cash_layers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    layer = Column(String(10), nullable=False)  # T0 / T7 / T30
    amount = Column(Float, default=0)
    institution = Column(String(200), nullable=True)  # 存放机构
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="security_life_cash_layers")


class SecurityLifeChecklistItem(Base):
    """90天清单项（默认模板 + 用户自定义）"""
    __tablename__ = "security_life_checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    phase = Column(String(10), nullable=False)  # 0-2 / 3-6 / 7-12
    system_id = Column(Integer, nullable=False)  # 1-5 对应五大系统
    label = Column(String(500), nullable=False)
    detail = Column(Text, nullable=True)  # 详细说明
    is_default = Column(Boolean, default=False)  # 是否为默认模板项
    default_item_id = Column(String(20), nullable=True)  # 默认项的ID标识（如 c1, c2）

    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="security_life_checklist_items")


class SecurityLifeRedLineStatus(Base):
    """三条红线状态跟踪"""
    __tablename__ = "security_life_red_line_status"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    line_id = Column(Integer, nullable=False)  # 1: 现金流跑道 / 2: 迁移与医疗 / 3: 单点失败
    status = Column(String(10), default="unmet")  # met / unmet / partial
    value_json = Column(Text, nullable=True)  # JSON: 具体数值/说明
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="security_life_red_line_status")
