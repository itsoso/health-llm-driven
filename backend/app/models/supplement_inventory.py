"""D1 补剂库存 —— 复购检测的存量来源(P3:检测 + 提醒,**不下单**)。

一行 = 一个用户的一种补剂的剩余量。复购检测从这里读 units_remaining,配合
SupplementRecord 估的日消耗算 days_remaining;低于阈值 → 提议「该补货了」write_intent。

边界(safety):本表只承载「还剩多少 / 一包多少 / 上次补货何时」这类**物流事实**,
不含价格/支付/订单/购买动作 —— 那是 PRD §3.D2(P5)的财务面,要过 governance Gate +
财务安全评审,本期严禁触及(不建 ReorderIntent 一等对象)。

幂等:一行一 (user_id, supplement_id),UniqueConstraint 兜底;restock 走原子读-改-写,
manual set 直接覆盖 units_remaining。supplement_id FK 已是用户域。
"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.database import Base


class SupplementInventory(Base):
    __tablename__ = "supplement_inventory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplement_id = Column(
        Integer, ForeignKey("supplement_definitions.id"), nullable=False
    )

    units_remaining = Column(Integer, nullable=True)   # 剩余单位数(粒/片/ml),可空=未登记
    package_units = Column(Integer, nullable=True)     # 每包单位数(补货参考),可空
    brand = Column(String(100), nullable=True)         # 品牌(备货时带给提醒,便于复购)
    spec = Column(String(100), nullable=True)          # 规格

    last_restock_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        # 一个用户的一种补剂只存一行(restock 累加 / manual set 覆盖,幂等去重)
        UniqueConstraint("supplement_id", name="uq_supp_inventory_supplement"),
        Index("ix_supp_inventory_user", "user_id"),
    )
