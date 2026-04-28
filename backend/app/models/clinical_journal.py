"""
Clinical Journal — Agent 的 "记得你" 层.

每次 orchestrator 跑完后异步产一条 SOAP entry, 按 case_thread 聚合.
Specialist 下次评估时, 优先注入相关 case 最近 3 条 entry 摘要 → AI 真正"记得".

case_thread = 按主题/疾病/指标聚合的长期 timeline:
  鼻炎 case      (theme=rhinitis,    metric_key=symptom)
  睡眠呼吸 case  (theme=sleep_osahs, metric_key=spo2_min_nocturnal)
  肝功能 case    (theme=liver,       metric_key=alt)
  减重 case      (theme=weight_loss, metric_key=weight)
  ...
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CaseThread(Base):
    """一条按主题聚合的 case timeline."""
    __tablename__ = "case_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # theme: 业务主题 — 'rhinitis' / 'sleep_osahs' / 'liver' / 'weight_loss' / 'metabolic' / ...
    theme = Column(String(40), nullable=False, index=True)
    # metric_key: 主指标 — 与 ActionCard.metric_key / outcome_grader 一致, 用于 join
    metric_key = Column(String(50), index=True)

    title = Column(String(200))             # 用户可读: "我的鼻炎"
    summary = Column(Text)                  # AI 生成的 case 一句话当前态势
    status = Column(String(20), default="active", index=True)  # active / monitoring / resolved
    severity = Column(String(20))           # mild / moderate / severe / unknown

    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                             onupdate=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    entries = relationship("ClinicalJournalEntry", back_populates="case_thread",
                          cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_case_thread_user_status', 'user_id', 'status'),
        Index('idx_case_thread_user_theme', 'user_id', 'theme'),
    )


class ClinicalJournalEntry(Base):
    """单条 SOAP-note (Subjective/Objective/Assessment/Plan).

    旁路写入 — orchestrator 跑完异步产, 出错只 log.
    """
    __tablename__ = "clinical_journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    case_thread_id = Column(Integer, ForeignKey("case_threads.id"), nullable=True, index=True)

    # SOAP 四段
    subjective = Column(Text)    # 主诉: 用户的话, 症状, 感受
    objective = Column(Text)     # 数据: HRV / labs / 当时 Twin snapshot 关键数字
    assessment = Column(Text)    # AI/specialist 评估
    plan = Column(Text)          # 行动建议 / 复查日期

    # 来源溯源 (用于回放)
    source_conversation_id = Column(Integer, index=True)  # OpenClawConversation.id
    source_message_id = Column(Integer)                   # 触发的 message.id
    used_specialists = Column(String(200))                # 'recovery_coach,fuel_strategist'

    # 关联本次产出的 ActionCard (proposed_cards 的落地 id)
    related_action_card_ids = Column(String(120))         # comma-sep ids

    generated_at = Column(DateTime(timezone=True), server_default=func.now(),
                         nullable=False, index=True)
    # who: 'orchestrator' / 'briefing_task' / 'manual' (用户自己写的笔记)
    created_by = Column(String(40), default="orchestrator")

    case_thread = relationship("CaseThread", back_populates="entries")

    __table_args__ = (
        Index('idx_journal_user_generated', 'user_id', 'generated_at'),
    )
