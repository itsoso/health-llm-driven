"""
User Judgment Feedback — 用户对 AI 任意判断的**秒级反馈**.

区别于 ActionCard outcome_grader (N 天后自动评分):
  这是**用户当场点"对/不对"**的直觉反馈.

Polymorphic 设计:
  target_type = insight / anomaly_alert / action_card / safety_alert /
                llm_arbitration / specialist_finding
  target_id = 对应表的 id

用途:
  1. orchestrator 合成 prompt 注入"最近用户否定的 N 条判断" 作负样本
  2. specialist_hit_rate 额外考虑用户反馈 (非 outcome_grader 专利)
  3. 告警降噪: 用户明确"不相关"的 rule_id 自动 suppress 7 天
  4. 给 B 端: 可量化 "AI 建议接受率"
"""
from datetime import UTC, datetime
from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text
)
from sqlalchemy.sql import func

from app.database import Base


# 允许的反馈值 (和 DailyInsight.user_feedback 保持一致)
FEEDBACK_VALUES = {
    "helpful",       # 👍 有用
    "not_helpful",   # 👎 不对 / 不同意
    "irrelevant",    # 这事跟我没关系
    "already_knew",  # 我早知道了 (不扣分, 但别再重复推)
}

# 允许的 target_type (目前 6 类)
TARGET_TYPES = {
    "insight",              # DailyInsight
    "anomaly_alert",        # AnomalyAlert
    "action_card",          # ActionCard
    "safety_alert",         # SafetyGuardian rule-triggered
    "llm_arbitration",      # agent_audit_logs(agent_type=llm_arbitrator)
    "specialist_finding",   # orchestrator 返回的某条 finding
}


class UserJudgmentFeedback(Base):
    """用户对任意 AI 决策的反馈. Polymorphic: target_type + target_id 指向具体记录."""
    __tablename__ = "user_judgment_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Polymorphic 关联
    target_type = Column(String(40), nullable=False, index=True)
    target_id = Column(Integer, nullable=False)  # 对应 {target_type} 表的 id

    # 反馈
    feedback = Column(String(20), nullable=False, index=True)  # FEEDBACK_VALUES
    note = Column(Text)  # 可选的详细说明

    # Context (用于 LLM prompt 注入时还原现场)
    # 例: {"title": "HRV 偏低告警", "message": "...", "rule_id": "hrv_drop"}
    snapshot = Column(Text)  # JSON 字符串 or 简短摘要

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_feedback_user_target", "user_id", "target_type", "target_id", unique=True),
        Index("ix_feedback_user_time", "user_id", "created_at"),
        Index("ix_feedback_user_value", "user_id", "feedback"),
    )

    def __repr__(self):
        return (
            f"<Feedback {self.id} u={self.user_id} "
            f"{self.target_type}#{self.target_id} = {self.feedback}>"
        )
