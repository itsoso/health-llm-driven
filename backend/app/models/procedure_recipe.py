"""程序性记忆/配方(Harness 自由度升级 Slice 3)。

配方 = **确定性重放的工具序列**,不是程序、不是 LLM 现场生成:
- ``steps`` = ``[{"tool": ..., "args_template": {...}}]``,重放时逐步走
  AgentExecutor 既有工具执行路径(每步确认策略沿用该 kind 既有 confirm tier,
  typed_only / never_auto 原样生效 —— 配方**不绕任何确认门**)。
- ``args_template`` 只允许既有槽位的确定性填充(如 ``{{today}}`` = 重放当天),
  禁止 LLM 现场改参;confirmed/confirm 标志在存入前剥除(防继承一次性确认)。
- ``trigger_phrases`` 精确匹配(strip 后等值,先于 LLM,类似 fast-path),
  不做模糊匹配(控误触发)。

见 docs/plans/2026-07-07-agent-harness-freedom-upgrades.md §Slice 3。
"""
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base

_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class ProcedureRecipe(Base):
    __tablename__ = "procedure_recipes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # ["早餐打卡", ...] — strip 后精确等值匹配,不做模糊
    trigger_phrases = Column(_JSON_TYPE, nullable=False, default=list)
    # [{"tool": "health_record", "args_template": {...}}] — 确定性重放序列
    steps = Column(_JSON_TYPE, nullable=False, default=list)
    created_from_conversation_id = Column(Integer, nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
