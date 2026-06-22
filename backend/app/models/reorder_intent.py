"""P5(D2)复购下单 —— 财务一等对象 `ReorderIntent`(SCAFFOLD,不真下单)。

见 docs/prd/2026-06-19-proactive-planning-prd.md §3.D2 + §5、
docs/specs/active/2026-06-22-p5-reorder-ordering.md(一等对象准入 Gate)。

与 P3 的 `WriteIntent`/`reorder_nudge` 区分:那是「提醒」(良性写,confirm 只 acknowledge);
**本表是「下单」财务面**,要单独的状态机 + 审计 + 逐笔强确认,故立为独立一等对象。

⚠️ 财务硬边界(本期 = SCAFFOLD,过财务安全评审):
- 真正下单由**快手电商 OpenClaw skill**(另一团队开发,契约未就绪)执行,用用户自有快手账号。
- 本期到「调 skill」为止就 STOP:`kuaishou_skill_gateway.place_order` raise NotImplementedError,
  confirm 走到那一步 → API 返回 501;**绝不**标 `order_placed`、绝不有可执行的支付/扣款路径。
- 后端永不处理支付凭据、永不自动扣款、永不无逐笔确认下单。
- 自治阶梯 = T3(执行外部动作)+ 财务硬门。`auto_reorder_enabled` / `monthly_cap_cents` 仅落
  「常驻自动复购」的结构与额度护栏(确定性 cap-check),本期无任何真单触发它。

状态机:
  proposed ──confirm──▶ user_confirmed ──skill──▶ order_placed   (成功:有 kuaishou_order_id)
                                          └──────▶ order_failed    (KuaishouSkillError)
  proposed / user_confirmed ──cancel──▶ cancelled
  (本期 skill 未就绪:confirm 推进到 user_confirmed 后 place_order 抛 NotImplementedError,
   service 把状态回到安全态、API 报 501,**不**进入 order_placed。)

幂等 / 安全:
- propose 幂等:同 (user, supplement, status=proposed) 已有 → 返回既有,不重复建。
- confirm 原子门:仅 (id,user,status=proposed) → user_confirmed,rowcount 守 + confirmed_at。
- IDOR:全部查询按 user_id 过滤;supplement_id FK 校验须属调用方。
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

from app.database import Base


class ReorderIntent(Base):
    __tablename__ = "reorder_intents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplement_id = Column(
        Integer, ForeignKey("supplement_definitions.id"), nullable=False
    )

    quantity = Column(Integer, nullable=False)         # 下单数量(件/瓶/包)
    brand = Column(String(100), nullable=True)         # 品牌(下单参考,沿用库存登记)
    spec = Column(String(100), nullable=True)          # 规格

    # proposed → user_confirmed → order_placed | order_failed | cancelled
    status = Column(String(20), nullable=False, default="proposed", index=True)

    # 快手电商 skill 回参的订单号(仅 order_placed 时非空;本期恒 null —— skill 未就绪)
    kuaishou_order_id = Column(String(120), nullable=True)

    # 「常驻自动复购」结构(本期不放开:显式开 + 单品 + 月额上限 + 每单通知)
    auto_reorder_enabled = Column(Boolean, nullable=False, default=False)
    monthly_cap_cents = Column(Integer, nullable=True)  # 月额上限(分);None=未设上限

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)  # 用户逐笔确认时刻
    placed_at = Column(DateTime(timezone=True), nullable=True)     # skill 真下单成功时刻

    notes = Column(Text, nullable=True)  # 失败原因 / cap 拒因等(无 PII)

    __table_args__ = (
        Index("ix_reorder_intents_user_status", "user_id", "status"),
        Index("ix_reorder_intents_supplement", "supplement_id"),
    )
