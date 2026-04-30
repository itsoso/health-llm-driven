"""每日 Insight 模型.

区别 DailyRecommendation (actionable 建议) — Insight 是**跨事件模式洞察**:
不是"今天做什么", 而是"我发现你 X 和 Y 有关联".

数据源优先级 (分层):
  Tier 1 (rule-based): 基因×用药×化验的确定性规则
  Tier 2 (timeseries): 跨 Garmin/Diet/Checkin 时序的 pattern 匹配
  Tier 3 (llm, v2 再做): LLM 给 KG + 最近数据让它找 pattern

幂等: 同 (user, insight_date) 只写一条, 由 daily task 06:30 跑.
"""
from datetime import UTC, datetime
from sqlalchemy import (
    Column, DateTime, Date, Float, ForeignKey, Index, Integer, String, Text, JSON
)
from sqlalchemy.sql import func

from app.database import Base


class DailyInsight(Base):
    """每日 Insight — 跨事件 pattern 洞察."""
    __tablename__ = "daily_insights"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    insight_date = Column(Date, nullable=False, index=True)

    # 生成分层
    kind = Column(String(50), nullable=False, index=True)
    # 具体规则 id: 'pgx_medication_caution' / 'abnormal_lab_trend' /
    # 'hrv_stressor_pattern' / ...
    rule_id = Column(String(80))

    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)

    # 引用: 让用户/B 端能追溯 "这个洞察基于什么数据"
    # 建议字段: memory_fact_ids / entity_ids / metrics / cite
    evidence = Column(JSON, default=dict)

    # 置信度 [0,1], 严重度 info/low/medium (不用 high/critical — 那是告警领域)
    confidence = Column(Float, nullable=False, default=0.7)
    severity = Column(String(20), nullable=False, default="info")

    # 反馈 (为 #2 Trust Loop 反馈按钮预留)
    user_feedback = Column(String(20), index=True)
    # NULL / helpful / not_helpful / irrelevant / already_knew
    feedback_note = Column(Text)
    feedback_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_insights_user_date', 'user_id', 'insight_date', unique=True),
        Index('ix_insights_user_feedback', 'user_id', 'user_feedback'),
    )

    def __repr__(self):
        return f"<DailyInsight {self.id} user={self.user_id} {self.insight_date} {self.rule_id}>"
